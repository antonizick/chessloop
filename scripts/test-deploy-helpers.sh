#!/usr/bin/env bash
# Unit tests for the small helper functions in deploy.sh (no Docker, no
# network, no sudo). Usage: scripts/test-deploy-helpers.sh
# deploy.sh is loaded with CHESSLOOP_SOURCE_ONLY=1, so nothing is installed.
# shellcheck disable=SC1091,SC2034  # deploy.sh is sourced: its functions read these globals
# shellcheck disable=SC2015,SC2016,SC1003  # test one-liners and literal strings, on purpose
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
ROOT=$PWD
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

CHESSLOOP_SOURCE_ONLY=1 source "$ROOT/deploy.sh"
set +e   # count failures instead of stopping at the first one
trap - ERR

PASS=0 FAIL=0
pass() { PASS=$((PASS + 1)); }
fail() { FAIL=$((FAIL + 1)); echo "FAIL: $*" >&2; }
# check "name" expected actual
check() { if [ "$2" == "$3" ]; then pass; else fail "$1: expected [$2], got [$3]"; fi; }
yes_() { if "$@"; then pass; else fail "expected success: $*"; fi; }
no_() { if "$@"; then fail "expected failure: $*"; else pass; fi; }

# ── ports ───────────────────────────────────────────────────────────────
for p in 1 80 8090 65535; do yes_ valid_port "$p"; done
for p in 0 65536 080 "" abc 8090x " 8090" -1 99999; do no_ valid_port "$p"; done

# ── access question → bind address and email-link address (ADR-0010) ────
check "access 1" local "$(normalize_access 1)"
check "access lan" lan "$(normalize_access LAN)"
check "access 3" domain "$(normalize_access 3)"
check "access bad" "" "$(normalize_access 4)"
check "bind local" 127.0.0.1 "$(bind_addr_for local)"
check "bind lan" 0.0.0.0 "$(bind_addr_for lan)"
check "bind domain" 127.0.0.1 "$(bind_addr_for domain)"
check "url local" http://localhost:8090 "$(frontend_url_for local 8090 "" 192.168.1.20)"
check "url lan" http://192.168.1.20:8091 "$(frontend_url_for lan 8091 "" 192.168.1.20)"
check "url lan, no ip" http://localhost:8091 "$(frontend_url_for lan 8091 "" "")"
check "url domain" https://chess.example.org "$(frontend_url_for domain 8090 chess.example.org 10.0.0.2)"

# ── public address detection (S3 warning) ──────────────────────────────
for ip in 10.77.0.5 192.168.1.20 172.16.0.1 172.31.255.1 127.0.0.1 169.254.1.1 100.64.0.1 100.127.1.1; do
    no_ is_public_ipv4 "$ip"
done
for ip in 8.8.8.8 172.32.0.1 100.128.0.1 203.0.113.9 51.15.0.1; do yes_ is_public_ipv4 "$ip"; done
no_ is_public_ipv4 "not-an-ip"

# ── platforms (ADR-0004, ADR-0018) ──────────────────────────────────────
check "ubuntu 24.04" supported "$(os_support ubuntu 24.04 debian)"
check "ubuntu 26.04" supported "$(os_support ubuntu 26.04 debian)"
check "debian 12" supported "$(os_support debian 12 "")"
check "debian 13" supported "$(os_support debian 13 "")"
check "ubuntu 22.04" untested-debian "$(os_support ubuntu 22.04 debian)"
check "mint" untested-debian "$(os_support linuxmint 22 "ubuntu debian")"
check "raspbian" untested-debian "$(os_support raspbian 12 debian)"
check "fedora" unsupported "$(os_support fedora 42 "")"
check "arch" unsupported "$(os_support arch "" "")"
cat > "$TMP/os-release" <<'EOF'
PRETTY_NAME="Ubuntu Resolute Raccoon (development branch)"
NAME="Ubuntu"
VERSION_ID="26.04"
ID=ubuntu
ID_LIKE=debian
VERSION_CODENAME=resolute
UBUNTU_CODENAME=resolute
EOF
read_os_release "$TMP/os-release"
check "os-release id" ubuntu "$OS_ID"
check "os-release version" 26.04 "$OS_VERSION"
check "os-release codename" resolute "$OS_UBUNTU_CODENAME"
check "os-release support" supported "$OS_SUPPORT"

# ── WSL detection with fake /proc trees ─────────────────────────────────
mkdir -p "$TMP/linux/proc/sys/kernel" "$TMP/wsl/proc/sys/fs/binfmt_misc" "$TMP/wsl2/proc/sys/kernel"
echo "6.8.0-45-generic" > "$TMP/linux/proc/sys/kernel/osrelease"
: > "$TMP/wsl/proc/sys/fs/binfmt_misc/WSLInterop"
echo "6.18.54.1-microsoft-standard-WSL2" > "$TMP/wsl2/proc/sys/kernel/osrelease"
no_ is_wsl "$TMP/linux"
yes_ is_wsl "$TMP/wsl"
yes_ is_wsl "$TMP/wsl2"

# ── which Docker (F-041) ────────────────────────────────────────────────
check "no docker" none "$(docker_kind_of "")"
check "engine" engine "$(docker_kind_of /usr/bin/true)"
check "desktop shim" desktop-shim "$(docker_kind_of "/mnt/c/Program Files/Docker/Docker/resources/bin/docker")"
check "desktop integration" desktop "$(docker_kind_of /mnt/wsl/docker-desktop/cli-tools/usr/bin/docker)"
ln -s "/mnt/wsl/docker-desktop/cli-tools/usr/bin/docker" "$TMP/docker-link"
check "desktop via link" desktop "$(docker_kind_of "$TMP/docker-link")"

check "desktop running" running "$(desktop_state_from 'Docker Desktop.exe            6484 Console                    1    187,020 K')"
check "desktop stopped" stopped "$(desktop_state_from 'INFO: No tasks are running which match the specified criteria.')"
check "desktop unknown" unknown "$(desktop_state_from '')"

# ── answers ──────────────────────────────────────────────────────────────
yes_ valid_email sam@example.com
yes_ valid_email first.last+chess@mail.example.co.uk
for e in "" sam "sam@" "@example.com" "sam@example" "sam @example.com" "a'b@example.com"; do no_ valid_email "$e"; done
yes_ valid_domain chess.example.com
yes_ valid_domain xn--schach-xxa.example
for d in "" localhost "chess example.com" "https://chess.example.com" "-a.example.com" "chess.example.com/"; do no_ valid_domain "$d"; done
for _ in 1 2 3 4 5; do
    pw="$(gen_password)"
    check "password length" 29 "${#pw}"
    [[ "$pw" =~ ^[A-Za-z2-9]{4}(-[A-Za-z2-9]{4}){5}$ ]] && pass || fail "password format: $pw"
done
[ "$(gen_password)" != "$(gen_password)" ] && pass || fail "two generated passwords are equal"
secret="$(gen_jwt_secret)"
[ "${#secret}" -ge 32 ] && pass || fail "jwt secret too short: ${#secret}"
check "json plain" 'abc' "$(json_escape 'abc')"
check "json quote" 'a\"b\\c' "$(json_escape 'a"b\c')"
check "json newline" 'a\nb' "$(json_escape $'a\nb')"
check "secs" "45 s" "$(fmt_secs 45)"
check "mins" "2 min 05 s" "$(fmt_secs 125)"

# ── .env writing (R6, S2) ────────────────────────────────────────────────
check "quote plain" 'abc+/=' "$(env_quote 'abc+/=')"
check "quote email" 'sam@example.com' "$(env_quote 'sam@example.com')"
check "quote space" "'ChessLoop <c@x.org>'" "$(env_quote 'ChessLoop <c@x.org>')"
check "quote dollar" "'p\$ss#1'" "$(env_quote 'p$ss#1')"
check "quote quote" "'it\\'s'" "$(env_quote "it's")"
no_ env_quote 'ends\'
no_ env_quote $'two\nlines'
cp "$ROOT/chessloop/.env.example" "$TMP/env"
chmod 600 "$TMP/env"
env_set "$TMP/env" JWT_SECRET "abc/def+ghi=" || fail "env_set JWT_SECRET"
env_set "$TMP/env" BIND_ADDR 0.0.0.0 || fail "env_set BIND_ADDR"
env_set "$TMP/env" SMTP_PASSWORD 'p$ss word#1' || fail "env_set SMTP_PASSWORD"
env_set "$TMP/env" NEW_KEY x || fail "env_set NEW_KEY"
check "env_get JWT" "abc/def+ghi=" "$(env_get "$TMP/env" JWT_SECRET)"
check "env_get BIND (was commented out)" 0.0.0.0 "$(env_get "$TMP/env" BIND_ADDR)"
check "env_get quoted" 'p$ss word#1' "$(env_get "$TMP/env" SMTP_PASSWORD)"
check "env_get appended" x "$(env_get "$TMP/env" NEW_KEY)"
check "env_get absent" "" "$(env_get "$TMP/env" DOMAIN)"
check "one JWT line" 1 "$(grep -c '^JWT_SECRET=' "$TMP/env")"
check "placeholder gone" 0 "$(grep -c 'replace-with-openssl' "$TMP/env")"
check "comments kept" "$(grep -c '^#' "$ROOT/chessloop/.env.example")" "$(( $(grep -c '^#' "$TMP/env") + 2 ))"
check "mode kept" 600 "$(stat -c %a "$TMP/env")"
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    # Docker Compose must read back exactly what env_set wrote.
    got="$(docker compose --env-file "$TMP/env" -f "$ROOT/chessloop/docker-compose.prod.yml" config --format json 2>/dev/null \
        | python3 -I -c 'import json,sys; e=json.load(sys.stdin)["services"]["backend"]["environment"]; print(e["CHESSLOOP_SMTP_PASSWORD"].replace("$$","$"), e["CHESSLOOP_JWT_SECRET"])')"
    check "compose reads .env" 'p$ss word#1 abc/def+ghi=' "$got"
fi

# write_config: a fresh .env from .env.example, mode 600 (H18, F-022)
mkdir -p "$TMP/install/chessloop"
cp "$ROOT/chessloop/.env.example" "$TMP/install/chessloop/"
INSTALL_DIR="$TMP/install" SUBDIR="$TMP/install/chessloop" STATE_FILE="$TMP/install/$STATE_NAME"
ACCESS=lan PORT=8091 LAN_IP=192.168.1.20 DOMAIN="" IS_WSL=0 EMAIL_ON=1
SMTP_HOST=smtp.example.com SMTP_PORT=587 SMTP_USER=sam@example.com SMTP_PASSWORD='s3cret pw' SMTP_FROM="" SMTP_USE_TLS=true
RESUME=0 OWNER="$(id -un)"
( umask 022; write_config ) 2>/dev/null || fail "write_config"
e="$TMP/install/chessloop/.env"
check ".env mode" 600 "$(stat -c %a "$e")"
check ".env port" 8091 "$(env_get "$e" PUBLIC_PORT)"
check ".env bind" 0.0.0.0 "$(env_get "$e" BIND_ADDR)"
check ".env url" http://192.168.1.20:8091 "$(env_get "$e" FRONTEND_URL)"
check ".env smtp pw" 's3cret pw' "$(env_get "$e" SMTP_PASSWORD)"
s="$(env_get "$e" JWT_SECRET)"
[ "${#s}" -ge 32 ] && [ "$s" != replace-with-openssl-rand-base64-32 ] && pass || fail ".env JWT_SECRET not generated"
check "state" "done" "$(env_get "$STATE_FILE" config)"
check "no temp files" 0 "$(find "$TMP/install/chessloop" -name '.env.new.*' | wc -l)"
IS_WSL=1 ACCESS=lan
rm -f "$e"; write_config 2>/dev/null || fail "write_config wsl"
check "wsl url" http://localhost:8091 "$(env_get "$e" FRONTEND_URL)"

# ── .wslconfig merge (ADR-0017): keep what is there, CRLF out ──────────
crlf() { sed 's/$/\r/'; }
out="$(ini_set general instanceIdleTimeout -1 </dev/null | tr -d '\r')"
check "new wslconfig" $'[general]\ninstanceIdleTimeout=-1' "$out"
out="$(printf '[wsl2]\r\nmemory=4GB\r\n' | ini_set general instanceIdleTimeout -1 | tr -d '\r')"
check "append section" $'[wsl2]\nmemory=4GB\n[general]\ninstanceIdleTimeout=-1' "$out"
out="$(printf '[general]\ninstanceIdleTimeout=60000\nfoo=1\n[wsl2]\nmemory=4GB\n' | ini_set general instanceIdleTimeout -1 | tr -d '\r')"
check "replace value" $'[general]\ninstanceIdleTimeout=-1\nfoo=1\n[wsl2]\nmemory=4GB' "$out"
out="$(printf '[General]\nfoo=1\n\n[wsl2]\nmemory=4GB\n' | ini_set general instanceIdleTimeout -1 | tr -d '\r')"
check "insert into section" $'[General]\nfoo=1\n\ninstanceIdleTimeout=-1\n[wsl2]\nmemory=4GB' "$out"
out="$(printf '[wsl2]\nmemory=4GB\n' | ini_set wsl2 networkingMode mirrored | tr -d '\r')"
check "mirrored" $'[wsl2]\nmemory=4GB\nnetworkingMode=mirrored' "$out"
out="$(printf '\xef\xbb\xbf[general]\r\nfoo=1\r\n' | ini_set general instanceIdleTimeout -1 | tr -d '\r')"
check "utf-8 BOM dropped, section found" $'[general]\nfoo=1\ninstanceIdleTimeout=-1' "$out"
check "ini_get after BOM" 1 "$(printf '\xef\xbb\xbf[general]\nfoo=1\n' | ini_get general foo)"
printf '[\x00w\x00s\x00l\x002\x00]\x00' > "$TMP/utf16.wslconfig"
wslconfig_set "$TMP/utf16.wslconfig" general instanceIdleTimeout -1; check "utf-16 file left alone (rc)" 2 "$?"
check "utf-16 file unchanged" 12 "$(stat -c %s "$TMP/utf16.wslconfig")"
check "crlf" 3 "$(printf '[x]\n' | ini_set general a b | grep -c $'\r$')"
check "ini_get" 60000 "$(printf '[general]\r\ninstanceIdleTimeout = 60000\r\n' | ini_get general instanceidletimeout)"
check "ini_get other section" "" "$(printf '[wsl2]\ninstanceIdleTimeout=1\n' | ini_get general instanceIdleTimeout)"
printf '[wsl2]\nmemory=4GB\n' | crlf > "$TMP/.wslconfig"
wslconfig_set "$TMP/.wslconfig" general instanceIdleTimeout -1
check "file merged" "-1" "$(ini_get general instanceIdleTimeout < "$TMP/.wslconfig")"
check "file kept memory" 4GB "$(ini_get wsl2 memory < "$TMP/.wslconfig")"
check "backup made" 1 "$(find "$TMP" -maxdepth 1 -name '.wslconfig.chessloop-backup-*' | wc -l)"
wslconfig_set "$TMP/.wslconfig" general instanceIdleTimeout -1
check "no second backup when unchanged" 1 "$(find "$TMP" -maxdepth 1 -name '.wslconfig.chessloop-backup-*' | wc -l)"

# ── Update, backup, restore, uninstall (Phase 09, ADR-0028) ────────────
check "ref: asked for" v1.2.0 "$(update_ref_for v1.2.0 main)"
check "ref: install's branch" deploy/x "$(update_ref_for "" deploy/x)"
check "ref: detached" main "$(update_ref_for "" "")"

vols=$'chessloop_chessloop-data\nother'
no_ volume_listed chessloop-data <<<"$vols"          # F-011: no substring match
yes_ volume_listed chessloop_chessloop-data <<<"$vols"
yes_ volume_listed chessloop-data <<<$'chessloop-data\nchessloop_chessloop-data'
no_ volume_listed chessloop-data <<<""

want=$'user=3\nlibrary=17\nline=40\nbackup=0'
yes_ counts_diff "$want" $'backup=0\nline=40\nlibrary=17\nuser=3'
yes_ counts_diff "$want" $'user=3\nlibrary=17\nline=40\nbackup=0\nnew_table=5'   # a newer version's table
check "counts differ" "line: 40 in the backup, 39 now" "$(counts_diff "$want" $'user=3\nlibrary=17\nline=39\nbackup=0')"
check "counts missing table" $'backup: 0 in the backup, missing now\nuser: 3 in the backup, missing now' \
    "$(counts_diff $'user=3\nbackup=0' $'library=1')"
no_ counts_diff "$want" "" >/dev/null
check "count_of" 17 "$(count_of "$want" library)"
check "count_of absent" "?" "$(count_of "$want" game)"
check "count_of no prefix match" 3 "$(count_of $'superuser=9\nuser=3' user)"

mkdir -p "$TMP/bk"
printf 'archive' | gzip > "$TMP/bk/a.tar.gz"
( cd "$TMP/bk" && sha256sum a.tar.gz > a.tar.gz.sha256 )
check "checksum ok" ok "$(checksum_state "$TMP/bk/a.tar.gz")"
cp "$TMP/bk/a.tar.gz" "$TMP/bk/b.tar.gz"; cp "$TMP/bk/a.tar.gz.sha256" "$TMP/bk/b.tar.gz.sha256"
printf 'x' >> "$TMP/bk/b.tar.gz"
check "checksum bad" bad "$(checksum_state "$TMP/bk/b.tar.gz")"
cp "$TMP/bk/a.tar.gz" "$TMP/bk/c.tar.gz"
check "checksum none" none "$(checksum_state "$TMP/bk/c.tar.gz")"
check "kind archive" archive "$(backup_kind_of "$TMP/bk/a.tar.gz")"
printf 'SQLite format 3\000rest' > "$TMP/bk/full.db"
check "kind sqlite" sqlite "$(backup_kind_of "$TMP/bk/full.db")"
echo "hello" > "$TMP/bk/notes.txt"
check "kind unknown" unknown "$(backup_kind_of "$TMP/bk/notes.txt")"
check "kind missing" unknown "$(backup_kind_of "$TMP/bk/nope")"
check "backup name" chessloop-20261017-153000-pre-update.tar.gz "$(backup_file_name pre-update 20261017-153000)"
check "backup name plain" chessloop-20261017-153000.tar.gz "$(backup_file_name "" 20261017-153000)"
[[ "$(backup_file_name "")" =~ ^chessloop-[0-9]{8}-[0-9]{6}\.tar\.gz$ ]] && pass || fail "backup name now"
check "size B" "512 B" "$(human_size 512)"
check "size KB" "290.0 KB" "$(human_size 296960)"
check "size GB" "1.5 GB" "$(human_size 1610612736)"

out="$(printf '[general]\r\ninstanceIdleTimeout=-1\r\nfoo=1\r\n[wsl2]\r\nnetworkingMode=mirrored\r\nmemory=4GB\r\n' | ini_del general instanceIdleTimeout -1 | tr -d '\r')"
check "ini_del removes" $'[general]\nfoo=1\n[wsl2]\nnetworkingMode=mirrored\nmemory=4GB' "$out"
out="$(printf '[general]\ninstanceIdleTimeout=60000\n' | ini_del general instanceIdleTimeout -1 | tr -d '\r')"
check "ini_del keeps a value the user changed" $'[general]\ninstanceIdleTimeout=60000' "$out"
out="$(printf '[wsl2]\ninstanceIdleTimeout=-1\n' | ini_del general instanceIdleTimeout -1 | tr -d '\r')"
check "ini_del other section untouched" $'[wsl2]\ninstanceIdleTimeout=-1' "$out"
check "ini_del crlf" 2 "$(printf '[general]\nfoo=1\n' | ini_del general foo 2 | grep -c $'\r$')"

cat > "$TMP/old.service" <<'EOF2'
[Unit]
Description=ChessLoop Chess Training System
Documentation=https://github.com/antonizick/chessloop
[Service]
ExecStartPre=/usr/bin/docker compose -f docker-compose.prod.yml pull --quiet 2>/dev/null || true
EOF2
yes_ is_old_unit "$TMP/old.service"
printf '[Unit]\nDescription=Something else\n' > "$TMP/other.service"
no_ is_old_unit "$TMP/other.service"
no_ is_old_unit "$TMP/missing.service"

mkdir -p "$TMP/inst/chessloop" "$TMP/notinst"
touch "$TMP/inst/chessloop/docker-compose.prod.yml"
yes_ safe_to_delete "$TMP/inst"
no_ safe_to_delete "$TMP/notinst"
for d in / /home /opt /usr /etc relative/path ""; do no_ safe_to_delete "$d"; done
HOME="$TMP/inst" no_ safe_to_delete "$TMP/inst"

# The backup, restore and count scripts that run in the backend container,
# against a small database in a temporary /data (needs Docker; skipped without).
PYIMG=python:3.12.15-slim-trixie   # the backend's base image
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    D="$TMP/data"; mkdir -p "$D/backups"
    py() { docker run --rm -i -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$D:/data" "$@"; }
    py "$PYIMG" python -c '
import sqlite3
c = sqlite3.connect("/data/chessloop.db"); c.execute("pragma journal_mode=wal")
c.execute("create table user (id integer primary key, email text)")
c.execute("create table library (id integer primary key, name text)")
c.executemany("insert into user (email) values (?)", [("a@x.org",), ("b@x.org",)])
c.executemany("insert into library (name) values (?)", [("Italian",), ("Sicilian",), ("French",)])
c.commit()' 2>/dev/null
    printf 'SQLite format 3\000panel' > "$D/backups/full_20261017_000000_x.db"
    printf 'JWT_SECRET=from-env-file\n' > "$TMP/env.in"
    py -e CL_WITH_ENV=1 -e CL_COMMIT=abc1234 "$PYIMG" python -c "$PY_BACKUP" < "$TMP/env.in" > "$TMP/b.tar.gz" 2> "$TMP/b.err"
    check "backup: ok line" "CL: ok" "$(tail -n 1 "$TMP/b.err")"
    check "backup: counts" $'library=3\nuser=2' "$(sed -n 's/^CL: count //p' "$TMP/b.err")"
    check "backup: members" $'manifest.json\nchessloop.db\nbackups/full_20261017_000000_x.db\nsettings.env' "$(tar -tzf "$TMP/b.tar.gz")"
    check "backup: member modes" 4 "$(tar -tvzf "$TMP/b.tar.gz" | grep -c '^-rw-------')"
    check "backup: settings inside" "JWT_SECRET=from-env-file" "$(tar -xzOf "$TMP/b.tar.gz" settings.env)"
    py "$PYIMG" python -c "$PY_BACKUP" < /dev/null > "$TMP/n.tar.gz" 2>/dev/null
    check "backup without settings" 0 "$(tar -tzf "$TMP/n.tar.gz" | grep -c settings.env)"
    # change the live data, then restore the backup
    py "$PYIMG" python -c 'import sqlite3; c = sqlite3.connect("/data/chessloop.db"); c.execute("delete from library"); c.commit()'
    check "live changed" $'library=0\nuser=2' "$(py "$PYIMG" python -c "$PY_COUNTS")"
    py -e CL_KIND=archive "$PYIMG" python -c "$PY_STAGE" < "$TMP/b.tar.gz" > /dev/null 2> "$TMP/s.err"
    check "stage: ok" "CL: ok" "$(tail -n 1 "$TMP/s.err")"
    check "stage: settings flag" 1 "$(grep -c '^CL: settings yes' "$TMP/s.err")"
    rm -f "$D/backups/full_20261017_000000_x.db"
    py "$PYIMG" python -c "$PY_SWAP" 2> "$TMP/w.err"
    check "swap: ok" "CL: ok" "$(tail -n 1 "$TMP/w.err")"
    check "restored counts" $'library=3\nuser=2' "$(py "$PYIMG" python -c "$PY_COUNTS")"
    check "panel backup restored" 1 "$(find "$D/backups" -name 'full_*' | wc -l)"
    check "staging removed" 0 "$(find "$D" -name .restore | wc -l)"
    # a damaged archive, a partial database, a raw panel download
    python3 -I - "$TMP/b.tar.gz" "$TMP/bad.tar.gz" <<'PY'
import io, sys, tarfile
src, dst = sys.argv[1:]
with tarfile.open(src) as t, tarfile.open(dst, "w:gz") as o:
    for m in t.getmembers():
        data = t.extractfile(m).read()
        if m.name == "chessloop.db":
            data = data[:-1] + bytes([data[-1] ^ 1])
        m.size = len(data); o.addfile(m, io.BytesIO(data))
PY
    py -e CL_KIND=archive "$PYIMG" python -c "$PY_STAGE" < "$TMP/bad.tar.gz" > /dev/null 2> "$TMP/s2.err"
    check "stage: tampered db refused" 1 "$(grep -c 'checksum mismatch' "$TMP/s2.err")"
    py "$PYIMG" python -c 'import sqlite3; c = sqlite3.connect("/data/empty.db"); c.execute("create table user (id integer)"); c.commit()'
    py -e CL_KIND=sqlite "$PYIMG" python -c "$PY_STAGE" < "$D/empty.db" > /dev/null 2> "$TMP/s3.err"
    check "stage: no accounts refused" 1 "$(grep -c 'no user accounts' "$TMP/s3.err")"
    py -e CL_KIND=sqlite "$PYIMG" python -c "$PY_STAGE" < "$D/chessloop.db" > /dev/null 2> "$TMP/s4.err"
    check "stage: panel download accepted" "CL: ok" "$(tail -n 1 "$TMP/s4.err")"
    printf 'not a tar' | gzip > "$TMP/junk.tar.gz"
    py -e CL_KIND=archive "$PYIMG" python -c "$PY_STAGE" < "$TMP/junk.tar.gz" > /dev/null 2> "$TMP/s5.err"
    check "stage: junk refused" 1 "$(grep -c '^CL: error' "$TMP/s5.err")"
    rm -f "$D/chessloop.db"*
    py "$PYIMG" python -c "$PY_BACKUP" < /dev/null > /dev/null 2> "$TMP/b2.err"
    check "backup: no database yet" 1 "$(grep -c '^CL: error: no database yet' "$TMP/b2.err")"
else
    echo "(Docker not available: skipped the backup/restore round trip)" >&2
fi

# ── update: how many starter lines were added ──────────────────────────
check "lines added: 12" 12 "$(starter_lines_added $'Added 12 lines to the starter libraries.')"
check "lines added: none" 0 "$(starter_lines_added "")"
check "lines added: noise" 0 "$(starter_lines_added $'Traceback...\nAdded lines')"
check "lines added: after other output" 111 "$(starter_lines_added $'something\nAdded 111 lines to the starter libraries.')"

# ── where to open ChessLoop after start/restore (F-070) ──────────────────
mkdir -p "$TMP/oa"
printf 'PUBLIC_PORT=8091\nBIND_ADDR=0.0.0.0\n' > "$TMP/oa/.env"
detect_lan_ip() { echo 192.168.1.20; }
is_wsl() { return 1; }
out="$(SUBDIR=$TMP/oa PORT=8091 open_addresses 2>&1)"
check "open: localhost" 1 "$(grep -c 'http://localhost:8091' <<<"$out")"
check "open: lan" 1 "$(grep -c 'http://192.168.1.20:8091' <<<"$out")"
is_wsl() { return 0; }
out="$(SUBDIR=$TMP/oa PORT=8091 open_addresses 2>&1)"
check "open: no lan address on wsl" 0 "$(grep -c '192.168' <<<"$out")"
printf 'PUBLIC_PORT=8091\nBIND_ADDR=127.0.0.1\n' > "$TMP/oa/.env"
is_wsl() { return 1; }
out="$(SUBDIR=$TMP/oa PORT=8091 open_addresses 2>&1)"
check "open: local only" 0 "$(grep -c '192.168' <<<"$out")"
unset -f detect_lan_ip is_wsl
CHESSLOOP_SOURCE_ONLY=1 source "$ROOT/deploy.sh"; set +e; trap - ERR

# ── Docker's apt signing key is checked before apt trusts it ────────────
# testdata/docker-apt-key.asc: download.docker.com/linux/debian/gpg, 2026-10-18.
if command -v gpg > /dev/null; then
    yes_ docker_key_ok "$ROOT/scripts/testdata/docker-apt-key.asc"
    gh_home=$(mktemp -d)
    GNUPGHOME="$gh_home" gpg --batch --quiet --passphrase '' --quick-gen-key 'Not Docker <x@example.org>' ed25519 sign never 2> /dev/null
    GNUPGHOME="$gh_home" gpg --batch --armor --export > "$TMP/other.asc" 2> /dev/null
    GNUPGHOME="$gh_home" gpgconf --kill gpg-agent 2> /dev/null || true
    rm -rf "$gh_home"
    no_ docker_key_ok "$TMP/other.asc"
    cat "$ROOT/scripts/testdata/docker-apt-key.asc" "$TMP/other.asc" > "$TMP/both.asc"
    no_ docker_key_ok "$TMP/both.asc"
    echo "<html>captive portal</html>" > "$TMP/html.asc"
    no_ docker_key_ok "$TMP/html.asc"
    no_ docker_key_ok "$TMP/missing.asc"
    check "docker key: no ~/.gnupg made" 0 "$(HOME=$TMP/h; mkdir -p "$HOME"; docker_key_ok "$ROOT/scripts/testdata/docker-apt-key.asc"; find "$HOME" -mindepth 1 | wc -l)"
else
    echo "(gpg not available: skipped the Docker key check)" >&2
fi

# ── no terminal and no --yes: refuse with two plain lines (F-059) ────────
# setsid drops the controlling terminal, so /dev/tty cannot be opened.
if command -v setsid > /dev/null; then
    for act in install update backup restore uninstall; do
        setsid -w bash "$ROOT/deploy.sh" "$act" < /dev/null > "$TMP/nt.out" 2> "$TMP/nt.err"
        rc=$?
        check "no terminal ($act): exit 1" 1 "$rc"
        check "no terminal ($act): says use --yes" 1 "$(grep -c 'use --yes' "$TMP/nt.err")"
        check "no terminal ($act): two lines only" 2 "$(wc -l < "$TMP/nt.err")"
        check "no terminal ($act): no 'went wrong'" 0 "$(cat "$TMP/nt.out" "$TMP/nt.err" | grep -ci 'went wrong\|install problem')"
    done
else
    echo "(setsid not available: skipped the no-terminal check)" >&2
fi

echo "deploy.sh helpers: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
