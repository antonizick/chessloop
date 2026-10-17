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

echo "deploy.sh helpers: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
