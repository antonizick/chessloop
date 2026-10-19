#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  ChessLoop — Install, Update, Back up, Restore and Uninstall
#
#  Install on a fresh machine (Ubuntu 24.04/26.04, Debian 12/13, or Ubuntu in
#  WSL 2 on Windows 11):
#    curl -fsSL https://raw.githubusercontent.com/antonizick/chessloop/main/deploy.sh | bash
#
#  Prefer to read it first? Download, look, then run:
#    curl -fsSLO https://raw.githubusercontent.com/antonizick/chessloop/main/deploy.sh
#    less deploy.sh
#    bash deploy.sh
#
#  Unattended (lab, CI): bash deploy.sh --yes   (settings from CHESSLOOP_* variables)
#  All options:          bash deploy.sh --help
#  After the install the same script is the "chessloop" command
#  (chessloop status, backup, restore, update, uninstall, …).
# ═══════════════════════════════════════════════════════════════════════════
set -Eeuo pipefail

# ── Settings (each can be set from the environment; see --help) ───────────
GITHUB_URL="https://github.com/antonizick/chessloop"
CL_REPO="${CHESSLOOP_REPO:-$GITHUB_URL}"
CL_REF="${CHESSLOOP_REF:-main}"
DEFAULT_INSTALL_DIR="/opt/chessloop"
INSTALL_DIR="${CHESSLOOP_INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"
DEFAULT_PORT=8090
VOLUME_NAME="chessloop_chessloop-data"     # pinned in docker-compose.prod.yml (ADR-0009)
STATE_NAME=".chessloop-install"            # progress of an install, so a re-run can continue
ISSUE_URL="$GITHUB_URL/issues/new?template=install_problem.yml"
HTTPS_GUIDE_URL="$GITHUB_URL#not-covered-hosting-chessloop-on-the-internet"
WSL_LAN_GUIDE_URL="https://learn.microsoft.com/windows/wsl/networking#mirrored-mode-networking"
MIN_RAM_MIB=1800      # a "2 GB" machine reports about 1.9 GiB; 2 GiB builds fine (Phase 04)
MIN_DISK_MIB=3072     # an install adds about 2.6 GB (Phase 04)
WANT_DISK_MIB=5120

STRAY_VOLUME="chessloop-data"             # an extra, normally empty volume older versions made (F-011)
OLD_UNIT_PATH="/etc/systemd/system/chessloop.service"   # written before 2026-10; broken (F-012)
COMMAND_LINK="/usr/local/bin/chessloop"    # the chessloop command: a link to deploy.sh (ADR-0027)
BACKUP_DIR=""                              # ~/chessloop-backups of the install's owner (setup_backup_dir)

# ── Run state ─────────────────────────────────────────────────────────────
NONINTERACTIVE="${CHESSLOOP_NONINTERACTIVE:-0}"
ACTION=""                 # install | update | backup | restore | uninstall | status | … | "" (menu)
LOG_FILE=""
CURRENT_STEP="starting"
ERR_CMD=""
ERR_LINE=""
FATAL_SHOWN=0
WORK_STARTED=0            # 1 once the user confirmed and the installer began changing things
SUDO_KEEPALIVE_PID=""
AS_ROOT=()                # (sudo) or () when running as root
DOCKER=(docker)           # (sudo docker) until the user's docker group applies
CL_USER="$(id -un 2>/dev/null || echo "${USER:-user}")"
OWNER="${SUDO_USER:-$CL_USER}"   # who owns the install folder

# Facts found by the preflight
OS_ID="" OS_VERSION="" OS_LIKE="" OS_CODENAME="" OS_UBUNTU_CODENAME="" OS_PRETTY=""
OS_SUPPORT=""             # supported | untested-debian | unsupported
IS_WSL=0
WSL_DISTRO=""
WSL_NET_MODE=""           # nat | mirrored | "" (unknown)
HAS_SYSTEMD=0
DOCKER_KIND=""            # none | engine | desktop | desktop-shim
NEED_DOCKER_INSTALL=0
NEED_COMPOSE_FIX=0
NEED_PKGS=()
CONFLICT_PKGS=()
HAS_PUBLIC_IP=0
LAN_IP=""

# Answers
ACCESS=""                 # local | lan | domain
PORT=""
DOMAIN=""
ADMIN_EMAIL=""
ADMIN_PASSWORD=""
ADMIN_USERNAME="${CHESSLOOP_ADMIN_USERNAME:-admin}"
PASSWORD_GENERATED=0
EMAIL_ON=0
SMTP_HOST="" SMTP_PORT="" SMTP_USER="" SMTP_PASSWORD="" SMTP_FROM="" SMTP_USE_TLS=""
SEED=1
WSL_KEEPALIVE=0
WSL_MIRRORED=0
RESUME=0
REUSE_CLONE=0

SUBDIR=""                 # $INSTALL_DIR/chessloop
STATE_FILE=""

# ═══════════════════════════════════════════════════════════════════════════
#  OUTPUT AND LOG
# ═══════════════════════════════════════════════════════════════════════════
R='' G='' Y='' C='' DIM='' BOLD='' RST=''
setup_colors() {
    if [ -t 2 ] && command -v tput >/dev/null 2>&1 && [ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]; then
        R=$'\033[0;31m' G=$'\033[0;32m' Y=$'\033[1;33m'
        C=$'\033[0;36m' DIM=$'\033[2m' BOLD=$'\033[1m' RST=$'\033[0m'
    fi
}

# Everything shown on screen is also written to the log, without colours.
# Secrets are never passed to these helpers (see show_password_once).
_log() {
    [ -n "$LOG_FILE" ] || return 0
    printf '%s\n' "$*" | sed -E 's/\x1b\[[0-9;]*[A-Za-z]//g' >> "$LOG_FILE" 2>/dev/null || true
}
_say() { local line; line="$(echo -e "$*")"; printf '%s\n' "$line" >&2; _log "$line"; }
info()    { _say "  ${C}→${RST}  $*"; }
ok()      { _say "  ${G}✓${RST}  $*"; }
warn()    { _say "  ${Y}⚠${RST}  $*"; }
err()     { _say "  ${R}✗${RST}  $*"; }
note()    { _say "     $*"; }
fatal()   { err "$*"; FATAL_SHOWN=1; exit 1; }
blank()   { echo "" >&2; _log ""; }
header()  { CURRENT_STEP="$*"; blank; _say "  ${C}${BOLD}$*${RST}"; _say "  $(printf '─%.0s' {1..60})"; }
sep()     { _say "  ${DIM}$(printf '─%.0s' {1..60})${RST}"; }

# step "Title": a new section; its name is shown if something fails in it.
step() { header "$1"; }

setup_log() {
    local name="$1" dir="${HOME:-/tmp}"
    { [ -d "$dir" ] && [ -w "$dir" ]; } || dir=/tmp
    LOG_FILE="$dir/chessloop-$name-$(date +%Y%m%d-%H%M%S).log"
    ( umask 077; : > "$LOG_FILE" ) 2>/dev/null || LOG_FILE=""
    _log "ChessLoop deploy.sh $name, $(date -Is), user $CL_USER, repo $CL_REPO, ref $CL_REF"
}

fmt_secs() {
    local s="$1"
    if [ "$s" -ge 60 ]; then printf '%d min %02d s' $((s / 60)) $((s % 60)); else printf '%d s' "$s"; fi
}

# Last line of the log, cleaned up, for the progress line.
_last_log_line() {
    [ -n "$LOG_FILE" ] || return 0
    tail -c 4000 "$LOG_FILE" 2>/dev/null | tr '\r' '\n' | sed -E 's/\x1b\[[0-9;?]*[A-Za-z]//g' \
        | grep -av '^[[:space:]]*$' | tail -n 1 | cut -c "1-${1:-40}" || true
}

# run "What it does" command...
# Runs a command with its output in the log. On a terminal a one-line progress
# display shows the time taken and the latest output line; otherwise (CI) the
# output is streamed. Never pass a secret as an argument.
run() {
    local label="$1"; shift
    local t0=$SECONDS rc=0
    _log "\$ $*"
    if [ -t 2 ] && [ "${CHESSLOOP_PROGRESS:-auto}" != plain ]; then
        "$@" </dev/null >> "${LOG_FILE:-/dev/null}" 2>&1 &
        # shellcheck disable=SC1003  # the backslash is one of the spinner frames
        local pid=$! frames='|/-\' i=0 cols width
        cols=$(tput cols 2>/dev/null || echo 80)
        width=$(( cols - ${#label} - 22 ))
        [ "$width" -lt 10 ] && width=10
        while kill -0 "$pid" 2>/dev/null; do
            printf '\r\033[K  %s  %s %s  %s' "${frames:i++%4:1}" "$label" \
                "${DIM}($(fmt_secs $((SECONDS - t0))))" "$(_last_log_line "$width")${RST}" >&2
            sleep 1
        done
        wait "$pid" || rc=$?
        printf '\r\033[K' >&2
    else
        info "$label…"
        set +e
        "$@" </dev/null 2>&1 | tee -a "${LOG_FILE:-/dev/null}" | sed 's/^/      /' >&2
        rc=${PIPESTATUS[0]}
        set -e
    fi
    if [ "$rc" -eq 0 ]; then
        ok "$label ${DIM}($(fmt_secs $((SECONDS - t0))))${RST}"
    else
        local tail_lines
        tail_lines="$(log_tail 15)"   # before our own message lands in the log
        err "$label: failed (exit code $rc, after $(fmt_secs $((SECONDS - t0))))."
        if [ -n "$tail_lines" ]; then
            _say "  ${DIM}Last lines of the log:${RST}"
            printf '%s\n' "$tail_lines" | sed 's/^/      /' >&2
        fi
    fi
    return "$rc"
}

log_tail() {
    [ -n "$LOG_FILE" ] || return 0
    tail -n 200 "$LOG_FILE" | tr '\r' '\n' | sed -E 's/\x1b\[[0-9;?]*[A-Za-z]//g' \
        | grep -av '^[[:space:]]*$' | tail -n "${1:-15}" || true
}

show_log_tail() {
    [ -n "$LOG_FILE" ] || return 0
    _say "  ${DIM}Last lines of the log:${RST}"
    log_tail "${1:-15}" | sed 's/^/      /' >&2
}

# A password chosen by the installer is shown once, on the screen only: it is
# written to the terminal, never to the log.
show_password_once() {
    {
        echo ""
        echo -e "  ${Y}${BOLD}┌──────────────────────────────────────────────────────────┐${RST}"
        echo -e "  ${Y}${BOLD}│  Your admin password, shown only this once.              │${RST}"
        echo -e "  ${Y}${BOLD}│  Save it now, for example in a password manager.         │${RST}"
        echo -e "  ${Y}${BOLD}└──────────────────────────────────────────────────────────┘${RST}"
        echo ""
        echo -e "      Email:     ${BOLD}$ADMIN_EMAIL${RST}"
        echo -e "      Password:  ${BOLD}$ADMIN_PASSWORD${RST}"
        echo ""
    } >&2
    _log "  (the generated admin password was shown on screen; it is not in this log)"
}

# ═══════════════════════════════════════════════════════════════════════════
#  FAILURES
# ═══════════════════════════════════════════════════════════════════════════
on_err() { ERR_CMD="$1"; ERR_LINE="$2"; }

on_exit() {
    local rc=$?
    stop_sudo_keepalive
    # A half-written settings file holds the JWT secret: never leave one behind.
    [ -n "$SUBDIR" ] && rm -f "$SUBDIR"/.env.new.* 2>/dev/null
    [ "$rc" -eq 0 ] && return 0
    [ "$FATAL_SHOWN" -eq 2 ] && return 0   # refused cleanly (no terminal): the two plain lines are enough
    blank
    if [ "$rc" -eq 130 ]; then
        err "Stopped (Ctrl+C) during: ${BOLD}$CURRENT_STEP${RST}"
    elif [ "$FATAL_SHOWN" -eq 0 ]; then
        err "Something went wrong during: ${BOLD}$CURRENT_STEP${RST}"
        [ -n "$ERR_CMD" ] && note "${DIM}command: $ERR_CMD (deploy.sh line $ERR_LINE, exit code $rc)${RST}"
        show_log_tail 15
    fi
    if [ "$ACTION" = install ] && [ "$WORK_STARTED" = 1 ]; then
        note "When the problem is fixed, run the installer again: it continues where it stopped."
    fi
    [ -n "$LOG_FILE" ] && note "Full log: ${BOLD}$LOG_FILE${RST}"
    note "Need help? Open an \"Install problem\" issue and attach the log:"
    note "  $ISSUE_URL"
    blank
}

# ═══════════════════════════════════════════════════════════════════════════
#  QUESTIONS (interactive mode reads from the terminal, even under curl | bash)
# ═══════════════════════════════════════════════════════════════════════════
tty_ok() { { : </dev/tty; } 2>/dev/null; }

# ask VAR "Question" [default]
ask() {
    local __var="$1" label="$2" def="${3-}" ans="" hint=""
    [ -n "$def" ] && hint=" [$def]"
    IFS= read -r -p "  ${BOLD}${label}${RST}${hint}: " ans </dev/tty || fatal "No answer (input closed)."
    ans="${ans:-$def}"
    _log "  ? $label: $ans"
    printf -v "$__var" '%s' "$ans"
}

# ask_secret VAR "Question": typing is hidden; the answer is never logged.
ask_secret() {
    local __var="$1" label="$2" ans=""
    IFS= read -r -s -p "  ${BOLD}${label}${RST}: " ans </dev/tty || fatal "No answer (input closed)."
    echo "" >&2
    _log "  ? $label: (hidden)"
    printf -v "$__var" '%s' "$ans"
}

# ask_yn "Question" Y|N: returns 0 for yes.
ask_yn() {
    local label="$1" def="${2:-Y}" ans hint
    if [ "$def" = Y ]; then hint="Y/n"; else hint="y/N"; fi
    while true; do
        IFS= read -r -p "  ${BOLD}${label}${RST} [$hint]: " ans </dev/tty || fatal "No answer (input closed)."
        ans="${ans:-$def}"
        _log "  ? $label: $ans"
        case "$ans" in
            [Yy]|[Yy][Ee][Ss]) return 0 ;;
            [Nn]|[Nn][Oo]) return 1 ;;
            *) warn "Please type y or n." ;;
        esac
    done
}

# confirm_or_stop "Question" "what --yes needs": asks in interactive mode; in
# --yes mode it continues only if the named setting allows it.
confirm_or_stop() {
    local label="$1" setting="$2"
    if [ "$NONINTERACTIVE" = 1 ]; then
        [ "${!setting:-0}" = 1 ] && { info "$setting=1: continuing."; return 0; }
        fatal "Stopped. To continue anyway in --yes mode, set $setting=1."
    fi
    ask_yn "$label" N || fatal "Stopped. Nothing was changed."
}

# ═══════════════════════════════════════════════════════════════════════════
#  SMALL HELPERS (no side effects; tested by scripts/test-deploy-helpers.sh)
# ═══════════════════════════════════════════════════════════════════════════
# is_wsl [root]: true inside WSL. root is a fake / for tests.
is_wsl() {
    local root="${1:-}"
    [ -e "$root/proc/sys/fs/binfmt_misc/WSLInterop" ] && return 0
    [ -e "$root/proc/sys/fs/binfmt_misc/WSLInterop-late" ] && return 0
    grep -qi microsoft "$root/proc/sys/kernel/osrelease" 2>/dev/null
}

valid_port() { [[ "$1" =~ ^[1-9][0-9]{0,4}$ ]] && [ "$1" -le 65535 ]; }

valid_email() { [[ "$1" =~ ^[^@[:space:]\"\']+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; }

valid_domain() {
    [[ "$1" =~ ^([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}$ ]]
}

# normalize_access local|lan|domain|1|2|3 → local|lan|domain ("" if unknown)
normalize_access() {
    case "${1,,}" in
        1|local|localhost|this) echo local ;;
        2|lan|home|network) echo lan ;;
        3|domain|internet|https) echo domain ;;
        *) echo "" ;;
    esac
}

# bind_addr_for ACCESS: the address the web port listens on.
bind_addr_for() {
    case "$1" in
        lan) echo "0.0.0.0" ;;
        *) echo "127.0.0.1" ;;   # local, and domain (an HTTPS proxy on this machine forwards to it)
    esac
}

# frontend_url_for ACCESS PORT DOMAIN LAN_IP: the address people open (used in email links).
frontend_url_for() {
    local access="$1" port="$2" domain="$3" lan_ip="$4"
    case "$access" in
        domain) echo "https://$domain" ;;
        lan) if [ -n "$lan_ip" ]; then echo "http://$lan_ip:$port"; else echo "http://localhost:$port"; fi ;;
        *) echo "http://localhost:$port" ;;
    esac
}

# is_public_ipv4 IP: not private, loopback, link-local, CGNAT/Tailscale or test-net.
is_public_ipv4() {
    local ip="$1" a b
    [[ "$ip" =~ ^([0-9]{1,3})\.([0-9]{1,3})\.[0-9]{1,3}\.[0-9]{1,3}$ ]] || return 1
    a=${BASH_REMATCH[1]} b=${BASH_REMATCH[2]}
    case "$a" in
        0|10|127) return 1 ;;
        100) [ "$b" -ge 64 ] && [ "$b" -le 127 ] && return 1 ;;
        169) [ "$b" -eq 254 ] && return 1 ;;
        172) [ "$b" -ge 16 ] && [ "$b" -le 31 ] && return 1 ;;
        192) [ "$b" -eq 168 ] && return 1 ;;
    esac
    [ "$a" -ge 224 ] && return 1
    return 0
}

# os_support ID VERSION_ID ID_LIKE → supported | untested-debian | unsupported (ADR-0004, ADR-0018)
os_support() {
    local id="$1" ver="$2" like="$3"
    case "$id:$ver" in
        ubuntu:24.04|ubuntu:26.04|debian:12|debian:13) echo supported; return ;;
    esac
    case " $id $like " in
        *" debian "*|*" ubuntu "*) echo untested-debian ;;
        *) echo unsupported ;;
    esac
}

# docker_kind_of PATH: what `command -v docker` found (empty = nothing).
#   desktop-shim  Docker Desktop's Windows program, seen through WSL's PATH (F-041)
#   desktop       Docker Desktop's WSL integration
#   engine        a docker command inside this Linux system
docker_kind_of() {
    local p="$1" real
    [ -n "$p" ] || { echo none; return; }
    real="$(readlink -m "$p" 2>/dev/null || echo "$p")"
    case "$real" in
        /mnt/[a-z]/*) echo desktop-shim ;;
        /mnt/wsl/docker-desktop/*) echo desktop ;;
        *) echo engine ;;
    esac
}

# desktop_state_from TASKLIST_OUTPUT → running | stopped | unknown
desktop_state_from() {
    if grep -qi 'Docker Desktop\.exe' <<<"$1"; then echo running
    elif grep -qi 'No tasks are running' <<<"$1"; then echo stopped
    else echo unknown; fi
}

# gen_password: 24 random letters and digits in groups of 4 (about 138 bits).
gen_password() {
    local raw
    raw="$(LC_ALL=C tr -dc 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789' </dev/urandom 2>/dev/null | head -c 24 || true)"
    printf '%s-%s-%s-%s-%s-%s\n' "${raw:0:4}" "${raw:4:4}" "${raw:8:4}" "${raw:12:4}" "${raw:16:4}" "${raw:20:4}"
}

gen_jwt_secret() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -base64 32
    else
        head -c 32 /dev/urandom | base64 | tr -d '\n'; echo
    fi
}

json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"; s="${s//\"/\\\"}"
    s="${s//$'\t'/\\t}"; s="${s//$'\n'/\\n}"; s="${s//$'\r'/\\r}"
    printf '%s' "$s"
}

# env_quote VALUE: the value as Docker Compose reads it from .env. Plain
# values stay unquoted; anything else is single-quoted (literal: no $, # or
# space surprises). Fails for a value Compose can't store reliably.
env_quote() {
    local v="$1"
    if [[ "$v" =~ ^[A-Za-z0-9._@:/+=,%-]*$ ]]; then printf '%s' "$v"; return 0; fi
    [[ "$v" == *$'\n'* || "$v" == *"\\" || "$v" == *"\\'"* ]] && return 1
    printf "'%s'" "${v//\'/\\\'}"
}

# env_set FILE KEY VALUE: set KEY in a .env-style file, replacing "KEY=…" or a
# commented-out "# KEY=…" line in place (so .env keeps .env.example's notes),
# else appending. Keeps the file's mode.
env_set() {
    local file="$1" key="$2" value quoted tmp
    value="$3"
    quoted="$(env_quote "$value")" || return 1
    tmp="$(mktemp "$file.XXXXXX")"
    KEY="$key" LINE="$key=$quoted" awk '
        BEGIN { key = ENVIRON["KEY"]; line = ENVIRON["LINE"]; done = 0 }
        {
            t = $0; sub(/^[ \t]*#?[ \t]*/, "", t)
            if (!done && index(t, key "=") == 1) { print line; done = 1; next }
            if (done && index($0, key "=") == 1) next   # drop later duplicates
            print
        }
        END { if (!done) print line }
    ' "$file" > "$tmp"
    chmod --reference="$file" "$tmp" 2>/dev/null || chmod 600 "$tmp"
    mv "$tmp" "$file"
}

# env_get FILE KEY: the value of an uncommented KEY= line (quotes removed).
env_get() {
    local file="$1" key="$2" v
    [ -f "$file" ] || return 0
    v="$(grep -E "^${key}=" "$file" 2>/dev/null | tail -n 1 | cut -d= -f2-)" || true
    v="${v%$'\r'}"
    if [[ "$v" == \'*\' ]]; then v="${v:1:${#v}-2}"; v="${v//\\\'/\'}";
    elif [[ "$v" == \"*\" ]]; then v="${v:1:${#v}-2}"; fi
    printf '%s' "$v"
}

# has_nul FILE: the file contains NUL bytes (UTF-16 text, for example).
has_nul() { [ "$(tr -d '\000' < "$1" | wc -c)" != "$(wc -c < "$1")" ]; }

# ini_set SECTION KEY VALUE < in > out: set KEY=VALUE in [SECTION] of a
# Windows-style ini file (.wslconfig), keeping everything else; output CRLF.
ini_set() {
    SEC="$1" KEY="$2" VAL="$3" awk '
        BEGIN { sec = tolower(ENVIRON["SEC"]); key = tolower(ENVIRON["KEY"]); line = ENVIRON["KEY"] "=" ENVIRON["VAL"]; in_sec = 0; done = 0 }
        NR == 1 { sub(/^\xef\xbb\xbf/, "") }   # a UTF-8 BOM (Notepad) would hide the first section
        { sub(/\r$/, "") }
        /^[ \t]*\[/ {
            if (in_sec && !done) { print line; done = 1 }
            h = tolower($0); gsub(/[ \t]/, "", h)
            in_sec = (h == "[" sec "]")
            print; next
        }
        in_sec {
            k = tolower($0); sub(/[ \t]*=.*/, "", k); gsub(/^[ \t]+/, "", k)
            if (k == key) { if (!done) { print line; done = 1 }; next }
        }
        { print }
        END {
            if (in_sec && !done) { print line; done = 1 }
            if (!done) { print "[" ENVIRON["SEC"] "]"; print line }
        }
    ' | sed 's/$/\r/'
}

# ini_get SECTION KEY < in: the value of KEY in [SECTION] ("" if absent).
ini_get() {
    SEC="$1" KEY="$2" awk '
        BEGIN { sec = tolower(ENVIRON["SEC"]); key = tolower(ENVIRON["KEY"]) }
        NR == 1 { sub(/^\xef\xbb\xbf/, "") }
        { sub(/\r$/, "") }
        /^[ \t]*\[/ { h = tolower($0); gsub(/[ \t]/, "", h); in_sec = (h == "[" sec "]"); next }
        in_sec && /=/ {
            k = tolower($0); sub(/[ \t]*=.*/, "", k); gsub(/^[ \t]+/, "", k)
            if (k == key) { v = $0; sub(/^[^=]*=[ \t]*/, "", v); sub(/[ \t]+$/, "", v); val = v }
        }
        END { print val }
    '
}

# ini_del SECTION KEY VALUE < in > out: removes KEY from [SECTION], but only
# while it still has VALUE (what the installer wrote); keeps the rest; CRLF out.
ini_del() {
    SEC="$1" KEY="$2" VAL="$3" awk '
        BEGIN { sec = tolower(ENVIRON["SEC"]); key = tolower(ENVIRON["KEY"]); val = ENVIRON["VAL"] }
        NR == 1 { sub(/^\xef\xbb\xbf/, "") }
        { sub(/\r$/, "") }
        /^[ \t]*\[/ { h = tolower($0); gsub(/[ \t]/, "", h); in_sec = (h == "[" sec "]"); print; next }
        in_sec && /=/ {
            k = tolower($0); sub(/[ \t]*=.*/, "", k); gsub(/^[ \t]+/, "", k)
            v = $0; sub(/^[^=]*=[ \t]*/, "", v); sub(/[ \t]+$/, "", v)
            if (k == key && v == val) next
        }
        { print }
    ' | sed 's/$/\r/'
}

# update_ref_for CHESSLOOP_REF BRANCH [CURRENT_TAG [LATEST_TAG]]: what Update
# follows (ADR-0028, ADR-0036): the ref asked for, else the branch the install
# is on, else (an install pinned to a release) the newest release, or the
# release it has when that can't be looked up, else main.
update_ref_for() {
    if [ -n "$1" ]; then echo "$1"
    elif [ -n "$2" ]; then echo "$2"
    elif [ -n "${3:-}" ]; then echo "${4:-$3}"
    else echo main; fi
}

# release_tag_from_json: the tag (v1.2.3 only) in GitHub's "latest release"
# answer on stdin, or nothing. No jq: one field of a small, fixed document.
release_tag_from_json() {
    sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\(v[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\)".*/\1/p' | head -n 1
}

# latest_release_tag: looks up the newest release of ChessLoop. Sets LATEST_TAG
# (v1.2.3, or empty) and RELEASE_LOOKUP (ok, none = the project has no release
# yet, or failed). Only asks GitHub about the real repository, never about a
# CHESSLOOP_REPO override. Sets globals (no output), so call it without $( ).
LATEST_TAG="" RELEASE_LOOKUP=""
latest_release_tag() {
    local answer code body
    LATEST_TAG="" RELEASE_LOOKUP=failed
    [ "$CL_REPO" = "$GITHUB_URL" ] || { RELEASE_LOOKUP=none; return 0; }
    answer="$(curl -sS --max-time 10 -H 'Accept: application/vnd.github+json' -w '\n%{http_code}' \
        "https://api.github.com/repos/${GITHUB_URL#https://github.com/}/releases/latest" 2>/dev/null)" || return 0
    code="${answer##*$'\n'}"
    body="${answer%$'\n'*}"
    case "$code" in
        200) LATEST_TAG="$(release_tag_from_json <<<"$body")"; RELEASE_LOOKUP=ok ;;
        404) RELEASE_LOOKUP=none ;;
    esac
    return 0
}

# use_latest_release: when no version was asked for (CHESSLOOP_REF), install the
# newest release instead of whatever main is today (ADR-0036). If the lookup
# fails, install main and say so.
use_latest_release() {
    [ -z "${CHESSLOOP_REF:-}" ] || return 0
    latest_release_tag
    if [ -n "$LATEST_TAG" ]; then
        CL_REF="$LATEST_TAG"
    elif [ "$RELEASE_LOOKUP" = failed ]; then
        warn "Couldn't look up the latest ChessLoop release, so this installs the newest development version (main) instead."
    fi
}

# volume_listed NAME < "docker volume ls -q": an exact match. (F-011: grep
# 'chessloop-data' also matched chessloop_chessloop-data.)
volume_listed() { grep -qxF -- "$1"; }

# counts_diff EXPECTED ACTUAL: row counts as "table=count" lines. Prints each
# table of EXPECTED whose count is different in ACTUAL (sorted) and fails if
# there is one. Tables only in ACTUAL (added by a newer version) don't count.
counts_diff() {
    local out
    out="$(awk -F= '
        NR == FNR { if (NF == 2) want[$1] = $2; next }
        NF == 2 { have[$1] = $2 }
        END { for (t in want) { h = (t in have) ? have[t] : "missing"; if (h != want[t]) printf "%s: %s in the backup, %s now\n", t, want[t], h } }
    ' <(printf '%s\n' "$1") <(printf '%s\n' "$2") | sort)"
    [ -z "$out" ] && return 0
    printf '%s\n' "$out"
    return 1
}

# count_of COUNTS TABLE: one table's row count ("?" if it isn't there).
count_of() {
    local v
    v="$(sed -n "s/^$2=//p" <<<"$1" | head -n 1)"
    echo "${v:-?}"
}

# checksum_state FILE: ok, bad, or none (there is no FILE.sha256).
checksum_state() {
    local f="$1" want have
    [ -f "$f.sha256" ] || { echo none; return 0; }
    want="$(awk 'NR == 1 {print $1}' "$f.sha256")"
    have="$(sha256sum "$f" 2>/dev/null | awk '{print $1}')"
    if [ -n "$want" ] && [ "$want" = "$have" ]; then echo ok; else echo bad; fi
}

# backup_kind_of FILE: archive (from "deploy.sh backup"), sqlite (a download
# from Admin → Backups) or unknown.
backup_kind_of() {
    local f="$1"
    [ -f "$f" ] || { echo unknown; return 0; }
    if [ "$(head -c 15 "$f" 2>/dev/null | tr -d '\000')" = "SQLite format 3" ]; then echo sqlite
    elif gzip -t "$f" 2>/dev/null; then echo archive
    else echo unknown; fi
}

# backup_file_name [KIND] [DATE]: chessloop-20261017-153000[-KIND].tar.gz
backup_file_name() { echo "chessloop-${2:-$(date +%Y%m%d-%H%M%S)}${1:+-$1}.tar.gz"; }

human_size() {
    awk -v b="${1:-0}" 'BEGIN { n = split("B KB MB GB TB", u, " "); i = 1
        while (b >= 1024 && i < n) { b /= 1024; i++ }
        if (i == 1) printf "%d %s\n", b, u[i]; else printf "%.1f %s\n", b, u[i] }'
}

# is_old_unit FILE: the chessloop.service deploy.sh wrote before 2026-10 (F-012).
is_old_unit() { grep -q '^Description=ChessLoop' "$1" 2>/dev/null; }

# safe_to_delete DIR: an absolute path to a ChessLoop install folder, and not
# a system folder or a home folder.
safe_to_delete() {
    local d="$1"
    case "$d" in /*) ;; *) return 1 ;; esac
    case "$d" in /|/home|/root|/opt|/srv|/usr|/usr/*|/etc|/etc/*|/var|/var/lib|/mnt|/mnt/*/) return 1 ;; esac
    [ "$(dirname "$d")" != /home ] || return 1
    [ "$d" != "${HOME:-}" ] || return 1
    [ -f "$d/chessloop/docker-compose.prod.yml" ]
}

# ═══════════════════════════════════════════════════════════════════════════
#  PORTS AND NETWORK
# ═══════════════════════════════════════════════════════════════════════════
port_in_use() {
    local port="$1"
    if command -v ss >/dev/null 2>&1; then
        [ -n "$(ss -Htln "sport = :$port" 2>/dev/null)" ]
    else
        (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null
    fi
}

find_free_port() {
    local port="${1:-$DEFAULT_PORT}" max
    max=$((port + 200))
    while [ "$port" -lt "$max" ]; do
        port_in_use "$port" || { echo "$port"; return 0; }
        port=$((port + 1))
    done
    echo "${1:-$DEFAULT_PORT}"
}

# The address other devices use to reach this machine.
detect_lan_ip() {
    local ip=""
    if command -v ip >/dev/null 2>&1; then
        ip="$(ip -4 route get 1.1.1.1 2>/dev/null | sed -nE 's/.* src ([0-9.]+).*/\1/p' | head -n 1)"
    fi
    [ -n "$ip" ] || ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
    echo "$ip"
}

detect_public_ip() {
    local a
    command -v ip >/dev/null 2>&1 || return 1
    for a in $(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1); do
        is_public_ipv4 "$a" && return 0
    done
    return 1
}

# can_reach HOST: can this machine open an HTTPS connection to HOST?
can_reach() {
    local host="$1"
    if command -v curl >/dev/null 2>&1; then
        curl -sS -o /dev/null -m 15 "https://$host/" 2>/dev/null && return 0
        # Any HTTP answer (even 4xx) proves the connection works.
        [ "$(curl -s -o /dev/null -m 15 -w '%{http_code}' "https://$host/" 2>/dev/null)" != 000 ]
    else
        timeout 10 bash -c "exec 3<>/dev/tcp/$host/443" 2>/dev/null
    fi
}

# ═══════════════════════════════════════════════════════════════════════════
#  PREFLIGHT (looks only; changes nothing)
# ═══════════════════════════════════════════════════════════════════════════
read_os_release() {
    local f="${1:-/etc/os-release}"
    [ -f "$f" ] || { OS_ID=unknown; OS_SUPPORT=unsupported; return; }
    # shellcheck disable=SC1090
    OS_ID="$(. "$f"; echo "${ID:-unknown}")"
    # shellcheck disable=SC1090
    OS_VERSION="$(. "$f"; echo "${VERSION_ID:-}")"
    # shellcheck disable=SC1090
    OS_LIKE="$(. "$f"; echo "${ID_LIKE:-}")"
    # shellcheck disable=SC1090
    OS_CODENAME="$(. "$f"; echo "${VERSION_CODENAME:-}")"
    # shellcheck disable=SC1090
    OS_UBUNTU_CODENAME="$(. "$f"; echo "${UBUNTU_CODENAME:-}")"
    # shellcheck disable=SC1090
    OS_PRETTY="$(. "$f"; echo "${PRETTY_NAME:-$OS_ID $OS_VERSION}")"
    OS_SUPPORT="$(os_support "$OS_ID" "$OS_VERSION" "$OS_LIKE")"
}

check_os() {
    read_os_release
    case "$OS_SUPPORT" in
        supported) ok "System: $OS_PRETTY" ;;
        untested-debian)
            warn "System: $OS_PRETTY. ChessLoop is tested on Ubuntu 24.04 and 26.04, and Debian 12 and 13."
            note "It may work here, but it has not been tested."
            confirm_or_stop "Continue anyway, at your own risk?" CHESSLOOP_ALLOW_UNTESTED
            ;;
        *)
            warn "System: $OS_PRETTY. ChessLoop is tested on Ubuntu 24.04 and 26.04, and Debian 12 and 13."
            note "On this system the installer can't install Docker or other software for you."
            note "If Docker Engine and its compose plugin are already installed, it can continue."
            confirm_or_stop "Continue anyway, not tested, at your own risk?" CHESSLOOP_ALLOW_UNTESTED
            ;;
    esac
}

check_arch() {
    local m
    m="$(uname -m)"
    case "$m" in
        x86_64|amd64) ok "Processor: $m" ;;
        aarch64|arm64)
            warn "Processor: $m (ARM). ChessLoop is tested on x86_64 (Intel/AMD) only."
            confirm_or_stop "Continue anyway, at your own risk?" CHESSLOOP_ALLOW_UNTESTED
            ;;
        *) fatal "Processor: $m. ChessLoop needs a 64-bit Intel/AMD (x86_64) machine." ;;
    esac
}

check_memory() {
    local mib
    mib="$(awk '/^MemTotal:/ {print int($2 / 1024)}' /proc/meminfo 2>/dev/null || echo 0)"
    if [ "$mib" -ge "$MIN_RAM_MIB" ]; then
        ok "Memory: $((mib / 1024)).$(( (mib % 1024) * 10 / 1024 )) GB"
    else
        warn "Memory: $mib MB. ChessLoop needs about 2 GB to build; with less, the build may fail."
        confirm_or_stop "Continue anyway?" CHESSLOOP_ALLOW_LOW_RESOURCES
    fi
}

# Free space (MB) on the filesystem that holds PATH (or its nearest parent).
free_mib() {
    local p="$1"
    while [ ! -e "$p" ] && [ "$p" != / ]; do p="$(dirname "$p")"; done
    df -Pm "$p" 2>/dev/null | awk 'NR == 2 {print $4}'
}

check_disk() {
    local where="/var/lib" mib
    [ "$DOCKER_KIND" = desktop ] && where="$INSTALL_DIR"   # Docker Desktop keeps images in its own VM
    mib="$(free_mib "$where")"; mib="${mib:-0}"
    local other
    other="$(free_mib "$INSTALL_DIR")"; other="${other:-0}"
    [ "$other" -lt "$mib" ] && mib="$other"
    if [ "$mib" -ge "$WANT_DISK_MIB" ]; then
        ok "Free disk space: $((mib / 1024)) GB"
    elif [ "$mib" -ge "$MIN_DISK_MIB" ]; then
        warn "Free disk space: $((mib / 1024)) GB. An install needs about 3 GB; 5 GB or more is recommended."
        confirm_or_stop "Continue anyway?" CHESSLOOP_ALLOW_LOW_RESOURCES
    else
        fatal "Free disk space: $mib MB. ChessLoop needs at least 3 GB free (Docker images and the build). Free up space, then run the installer again."
    fi
}

check_network() {
    local hosts=() h failed=()
    case "$CL_REPO" in https://github.com/*) hosts+=(github.com) ;; esac
    hosts+=(registry-1.docker.io)
    [ "$NEED_DOCKER_INSTALL" = 1 ] || [ "$NEED_COMPOSE_FIX" = 1 ] && hosts+=(download.docker.com)
    for h in "${hosts[@]}"; do can_reach "$h" || failed+=("$h"); done
    if [ "${#failed[@]}" -eq 0 ]; then
        ok "Internet: can reach ${hosts[*]}"
        return 0
    fi
    err "This computer can't reach: ${failed[*]}"
    note "The installer downloads ChessLoop and Docker from the internet."
    note "Check that this computer is online (open a web page, or run: ping -c 3 github.com)."
    note "Behind a company proxy or firewall? Allow those addresses, then run the installer again."
    FATAL_SHOWN=1; exit 1
}

check_wsl() {
    IS_WSL=0
    is_wsl || return 0
    IS_WSL=1
    WSL_DISTRO="${WSL_DISTRO_NAME:-}"
    WSL_NET_MODE=""
    if command -v wslinfo >/dev/null 2>&1; then
        WSL_NET_MODE="$(wslinfo --networking-mode 2>/dev/null | tr -d '\r' || true)"
    fi
    ok "Windows Subsystem for Linux (WSL): ${WSL_DISTRO:-yes}${WSL_NET_MODE:+, networking: $WSL_NET_MODE}"
}

check_systemd() {
    HAS_SYSTEMD=0
    [ "$(cat /proc/1/comm 2>/dev/null)" = systemd ] && HAS_SYSTEMD=1
    [ "$HAS_SYSTEMD" = 1 ] && return 0
    # Docker Engine needs systemd here (WSL turns it on by default since 2023).
    [ "$IS_WSL" = 1 ] && [ "$DOCKER_KIND" != desktop ] || return 0
    err "systemd is turned off in this WSL Ubuntu, and Docker needs it."
    note "The fix: turn systemd on in /etc/wsl.conf, then restart WSL."
    if [ "$NONINTERACTIVE" != 1 ] && ask_yn "Turn systemd on now (writes /etc/wsl.conf; asks for your password)?" Y; then
        setup_root
        local tmp
        tmp="$(mktemp)"
        { cat /etc/wsl.conf 2>/dev/null || true; } | ini_set boot systemd true | tr -d '\r' > "$tmp"
        "${AS_ROOT[@]}" install -m 0644 "$tmp" /etc/wsl.conf
        rm -f "$tmp"
        ok "systemd turned on in /etc/wsl.conf."
    else
        note "Add these two lines to /etc/wsl.conf (sudo nano /etc/wsl.conf):"
        note "  [boot]"
        note "  systemd=true"
    fi
    note "Now close this window, open ${BOLD}PowerShell${RST} in Windows and run:  ${BOLD}wsl --shutdown${RST}"
    note "Then open Ubuntu again and run the installer again."
    FATAL_SHOWN=1; exit 1
}

# Is Docker Desktop running in Windows? Asks Windows through WSL interop.
docker_desktop_state() {
    command -v tasklist.exe >/dev/null 2>&1 || { echo unknown; return 0; }
    desktop_state_from "$(cd /mnt/c 2>/dev/null && tasklist.exe /FI "IMAGENAME eq Docker Desktop.exe" /NH 2>/dev/null | tr -d '\r' || true)"
}

# Only Docker Desktop's Windows program is visible from Ubuntu (F-041): it is
# either not running (as after every Windows restart), or running without WSL
# integration for this distribution. Never suggest installing Docker Engine
# next to it (Docker: "Running both can cause conflicts").
explain_desktop_shim() {
    local distro="${WSL_DISTRO:-this Ubuntu}"
    case "$(docker_desktop_state)" in
        stopped)
            err "Docker Desktop is installed in Windows, but it isn't running."
            note "Start Docker Desktop from the Windows Start menu, wait until it says"
            note "\"Engine running\", then run the installer again."
            note "If you then see this message again: in Docker Desktop, Settings > Resources >"
            note "WSL integration, switch on \"$distro\" and click Apply & restart."
            ;;
        running)
            err "Docker Desktop is running in Windows, but this Ubuntu can't use it yet."
            note "If Docker Desktop has only just started, wait until it says \"Engine running\""
            note "and run the installer again. Otherwise, in Docker Desktop: Settings > Resources >"
            note "WSL integration, switch on \"$distro\", click Apply & restart, then run the installer again."
            ;;
        *)
            err "Docker Desktop is installed in Windows, but this Ubuntu can't use it yet."
            note "1. Start Docker Desktop and wait until it says \"Engine running\"."
            note "2. In Docker Desktop: Settings > Resources > WSL integration, switch on \"$distro\","
            note "   and click Apply & restart."
            note "Then run the installer again."
            ;;
    esac
    note "(Or uninstall Docker Desktop: the installer then sets up Docker inside Ubuntu instead.)"
}

# What Docker is there? Sets DOCKER_KIND, NEED_DOCKER_INSTALL, NEED_COMPOSE_FIX.
check_docker() {
    DOCKER_KIND="$(docker_kind_of "$(command -v docker 2>/dev/null || true)")"
    case "$DOCKER_KIND" in
        desktop-shim)
            explain_desktop_shim
            FATAL_SHOWN=1; exit 1
            ;;
        desktop)
            if docker info >/dev/null 2>&1; then
                ok "Docker: Docker Desktop (WSL integration), $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo running)"
            else
                # Docker Desktop's command is here (a link into /mnt/wsl, which every
                # distribution sees), but no engine answers: Desktop is stopped, still
                # starting, or its integration is off for this distribution (no
                # /var/run/docker.sock).
                explain_desktop_shim
                FATAL_SHOWN=1; exit 1
            fi
            ;;
        none)
            NEED_DOCKER_INSTALL=1
            info "Docker: not installed yet (the installer adds Docker Engine from Docker's official repository)."
            ;;
        engine)
            ok "Docker: $(docker --version 2>/dev/null | sed 's/,.*//' || echo installed)"
            ;;
    esac
    if [ "$DOCKER_KIND" = engine ] && ! docker compose version >/dev/null 2>&1; then
        NEED_COMPOSE_FIX=1
        warn "Docker's compose plugin is missing (\"docker compose\" doesn't work); the installer adds it."
    fi
    if [ "$NEED_DOCKER_INSTALL" = 1 ] || [ "$NEED_COMPOSE_FIX" = 1 ]; then
        [ "$OS_SUPPORT" = unsupported ] && fatal "Install Docker Engine and its compose plugin yourself (https://docs.docker.com/engine/install/), then run the installer again."
    fi
    if [ "$NEED_DOCKER_INSTALL" = 1 ]; then
        local p
        for p in docker.io docker-compose docker-compose-v2 docker-doc docker-buildx podman-docker containerd runc; do
            dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q 'install ok installed' && CONFLICT_PKGS+=("$p")
        done
        return 0
    fi
}

check_packages() {
    local p
    NEED_PKGS=()
    for p in git curl; do command -v "$p" >/dev/null 2>&1 || NEED_PKGS+=("$p"); done
    if [ "$NEED_DOCKER_INSTALL" = 1 ] || [ "$NEED_COMPOSE_FIX" = 1 ]; then
        dpkg-query -W -f='${Status}' ca-certificates 2>/dev/null | grep -q 'install ok installed' || NEED_PKGS+=(ca-certificates)
        # gpg checks Docker's signing key before apt trusts it (docker_key_ok).
        command -v gpg >/dev/null 2>&1 || NEED_PKGS+=(gpg)
    fi
    if [ "${#NEED_PKGS[@]}" -gt 0 ] && [ "$OS_SUPPORT" = unsupported ]; then
        fatal "Please install ${NEED_PKGS[*]} with your system's package manager, then run the installer again."
    fi
    [ "${#NEED_PKGS[@]}" -eq 0 ] || info "Also needed: ${NEED_PKGS[*]} (installed from $OS_ID's packages)."
}

preflight() {
    step "Checking this computer"
    check_os
    check_arch
    check_wsl
    check_docker
    check_systemd
    check_memory
    check_disk
    check_packages
    check_network
    LAN_IP="$(detect_lan_ip)"
    detect_public_ip && HAS_PUBLIC_IP=1
    return 0
}

# ═══════════════════════════════════════════════════════════════════════════
#  AN EARLIER INSTALL?
# ═══════════════════════════════════════════════════════════════════════════
state_get() { env_get "$STATE_FILE" "$1"; }
state_set() {
    [ -f "$STATE_FILE" ] || ( umask 077; : > "$STATE_FILE" )
    env_set "$STATE_FILE" "$1" "$2"
    # Run with sudo: the install's owner must be able to read it on the next run.
    if [ "$(id -u)" -eq 0 ] && [ "$OWNER" != root ]; then chown "$OWNER" "$STATE_FILE" 2>/dev/null || true; fi
}

# Sets RESUME / REUSE_CLONE, or offers Update and stops.
check_existing_install() {
    SUBDIR="$INSTALL_DIR/chessloop"
    STATE_FILE="$INSTALL_DIR/$STATE_NAME"
    if [ -f "$SUBDIR/docker-compose.prod.yml" ]; then
        if [ ! -f "$SUBDIR/.env" ]; then
            REUSE_CLONE=1
            info "ChessLoop's files are already in $INSTALL_DIR (an earlier install stopped early); using them."
            return 0
        fi
        if [ -f "$STATE_FILE" ] && [ -z "$(state_get complete)" ]; then
            RESUME=1
            warn "An earlier install in $INSTALL_DIR didn't finish."
            note "The installer continues it: it keeps your settings and any data, starts ChessLoop,"
            note "and does the steps that are still missing."
            if [ "$NONINTERACTIVE" != 1 ]; then
                ask_yn "Continue the earlier install?" Y || fatal "Stopped. Nothing was changed."
            fi
            return 0
        fi
        ok "ChessLoop is already installed in $INSTALL_DIR."
        note "To get the latest version, use ${BOLD}Update${RST}. Your data is kept."
        if [ "$NONINTERACTIVE" != 1 ] && ask_yn "Run Update now?" Y; then
            ACTION=update
            do_update
        fi
        exit 0
    fi
    if [ -d "$INSTALL_DIR" ] && [ -n "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
        fatal "The folder $INSTALL_DIR already exists and isn't a ChessLoop install. Move it away, or choose another folder: CHESSLOOP_INSTALL_DIR=/path bash deploy.sh"
    fi
}

# open_addresses: where to open ChessLoop, from the install's own settings
# (used after start and restore, when the install questions weren't asked).
open_addresses() {
    local env="$SUBDIR/.env" domain bind ip
    domain="$(env_get "$env" DOMAIN)"
    bind="$(env_get "$env" BIND_ADDR)"
    note "Open ChessLoop: http://localhost:$PORT"
    [ -n "$domain" ] && note "  or through your own web address: https://$domain"
    # On WSL the address inside Linux is not one other devices can use (F-040).
    if [ "$bind" = "0.0.0.0" ] && ! is_wsl; then
        ip="$(detect_lan_ip)"
        [ -n "$ip" ] && note "  or from other devices on your network: http://$ip:$PORT"
    fi
    return 0
}

load_resume_answers() {
    local env="$SUBDIR/.env" bind
    PORT="$(env_get "$env" PUBLIC_PORT)"; PORT="${PORT:-$DEFAULT_PORT}"
    DOMAIN="$(env_get "$env" DOMAIN)"
    bind="$(env_get "$env" BIND_ADDR)"
    if [ -n "$DOMAIN" ]; then ACCESS=domain
    elif [ "$bind" = "0.0.0.0" ]; then ACCESS=lan
    else ACCESS=local; fi
    [ -n "$(env_get "$env" SMTP_HOST)" ] && EMAIL_ON=1
    ADMIN_EMAIL="$(state_get admin_email)"
    info "Using the settings from the earlier install: port $PORT, access: $(access_words "$ACCESS")."
}

# ═══════════════════════════════════════════════════════════════════════════
#  QUESTIONS (ADR-0010)
# ═══════════════════════════════════════════════════════════════════════════
access_words() {
    case "$1" in
        local) if [ "$IS_WSL" = 1 ]; then echo "this Windows PC only"; else echo "this computer only"; fi ;;
        lan) echo "this computer and other devices on your home network" ;;
        domain) echo "the internet, through your own domain with HTTPS" ;;
    esac
}

# Private by default: opening ChessLoop to other devices is a choice, because it uses
# plain http:// (Phase 11, F-076). The guides say "if you are not sure, choose 1".
default_access() {
    echo local
}

ask_access() {
    local def choice n
    def="$(default_access)"
    if [ "$NONINTERACTIVE" = 1 ]; then
        ACCESS="$(normalize_access "${CHESSLOOP_ACCESS:-$def}")"
        [ -n "$ACCESS" ] || fatal "CHESSLOOP_ACCESS must be local, lan or domain (got '${CHESSLOOP_ACCESS:-}')."
    else
        header "Where will you open ChessLoop?"
        if [ "$IS_WSL" = 1 ]; then
            _say "    ${BOLD}1)${RST} Only on this Windows PC ${DIM}(in Edge, Chrome or Firefox)${RST}"
        else
            _say "    ${BOLD}1)${RST} Only on this computer"
            _say "       ${DIM}Also the right choice if you will put your own HTTPS proxy in front.${RST}"
        fi
        _say "    ${BOLD}2)${RST} Also on other devices in my home network ${DIM}(phone, tablet, laptop)${RST}"
        _say "       ${DIM}They open a plain http:// address. Use it only on a network you trust.${RST}"
        _say "    ${BOLD}3)${RST} From anywhere on the internet, with my own domain name (HTTPS)"
        _say "       ${DIM}ChessLoop stays private on this computer; you then add an HTTPS server.${RST}"
        n=$([ "$def" = local ] && echo 1 || echo 2)
        blank
        while true; do
            ask choice "Access [1-3]" "$n"
            ACCESS="$(normalize_access "$choice")"
            [ -n "$ACCESS" ] && break
            warn "Please type 1, 2 or 3."
        done
    fi
    if [ "$ACCESS" = lan ] && [ "$HAS_PUBLIC_IP" = 1 ]; then
        warn "This computer has a public internet address. With choice 2, anyone on the"
        note "internet who finds it can open ChessLoop over plain http:// (passwords are not"
        note "encrypted). Choice 3 (your own domain with HTTPS) is safer for a server."
        confirm_or_stop "Use choice 2 anyway?" CHESSLOOP_ALLOW_PUBLIC_LAN
    fi
    if [ "$ACCESS" = lan ] && [ "$IS_WSL" = 1 ]; then
        ask_wsl_lan
    fi
    if [ "$ACCESS" = domain ]; then
        ask_domain
    fi
}

ask_domain() {
    if [ "$NONINTERACTIVE" = 1 ]; then
        DOMAIN="${CHESSLOOP_DOMAIN:-}"
        valid_domain "$DOMAIN" || fatal "CHESSLOOP_DOMAIN must be a domain name like chess.example.com (got '$DOMAIN')."
        return 0
    fi
    note "Type the domain name you will use, for example chess.example.com."
    while true; do
        ask DOMAIN "Domain name" "${CHESSLOOP_DOMAIN:-}"
        DOMAIN="${DOMAIN,,}"; DOMAIN="${DOMAIN#https://}"; DOMAIN="${DOMAIN#http://}"; DOMAIN="${DOMAIN%/}"
        valid_domain "$DOMAIN" && break
        warn "That doesn't look like a domain name (for example chess.example.com)."
    done
}

# LAN access from WSL needs Windows to pass connections in (F-040, ADR-0017).
ask_wsl_lan() {
    [ "$DOCKER_KIND" = desktop ] && return 0     # Docker Desktop listens on Windows itself
    [ "$WSL_NET_MODE" = mirrored ] && return 0
    blank
    info "WSL normally keeps Ubuntu's network private to this PC. For phones and other"
    note "devices to connect, WSL's \"mirrored\" networking must be on (a setting in your"
    note "Windows user's .wslconfig file) and Windows' firewall must allow the port."
    if [ "$NONINTERACTIVE" = 1 ]; then
        [ "${CHESSLOOP_WSL_MIRRORED:-0}" = 1 ] && WSL_MIRRORED=1
    elif ask_yn "Turn on mirrored networking for WSL now? (recommended for choice 2)" Y; then
        WSL_MIRRORED=1
    fi
    return 0
}

ask_port() {
    local suggested p
    if [ "$NONINTERACTIVE" = 1 ]; then
        PORT="${CHESSLOOP_PORT:-$DEFAULT_PORT}"
        valid_port "$PORT" || fatal "CHESSLOOP_PORT must be a number from 1 to 65535 (got '$PORT')."
        port_in_use "$PORT" && fatal "Port $PORT is already used by another program. Set CHESSLOOP_PORT to a free port (for example $(find_free_port "$PORT"))."
        return 0
    fi
    suggested="${CHESSLOOP_PORT:-$DEFAULT_PORT}"
    if port_in_use "$suggested"; then
        p="$(find_free_port "$suggested")"
        warn "Port $suggested is already used by another program; $p is free."
        suggested="$p"
    fi
    header "Port"
    note "ChessLoop's address ends with a port number, like http://localhost:${suggested}."
    note "Press Enter to use $suggested unless you know you need another one."
    while true; do
        ask PORT "Port" "$suggested"
        if ! valid_port "$PORT"; then warn "Please type a number from 1 to 65535."; continue; fi
        if port_in_use "$PORT"; then warn "Port $PORT is in use by another program. Try $(find_free_port "$PORT")."; continue; fi
        break
    done
}

ask_admin() {
    if [ "$NONINTERACTIVE" = 1 ]; then
        ADMIN_EMAIL="${CHESSLOOP_ADMIN_EMAIL:-}"
        valid_email "$ADMIN_EMAIL" || fatal "Set CHESSLOOP_ADMIN_EMAIL to the admin's email address (got '$ADMIN_EMAIL')."
        ADMIN_PASSWORD="${CHESSLOOP_ADMIN_PASSWORD:-}"
        if [ -z "$ADMIN_PASSWORD" ]; then
            ADMIN_PASSWORD="$(gen_password)"; PASSWORD_GENERATED=1
        elif [ "${#ADMIN_PASSWORD}" -lt 12 ]; then
            fatal "CHESSLOOP_ADMIN_PASSWORD must have at least 12 characters."
        fi
        return 0
    fi
    header "Your admin account"
    note "You sign in to ChessLoop with this email address. ChessLoop doesn't send it"
    note "anywhere; it doesn't even need to receive mail unless you turn on email below."
    while true; do
        ask ADMIN_EMAIL "Admin email" "${CHESSLOOP_ADMIN_EMAIL:-}"
        valid_email "$ADMIN_EMAIL" && break
        warn "That doesn't look like an email address (for example sam@example.com)."
    done
    ask_admin_password
}

ask_admin_password() {
    local again
    blank
    note "Choose a password with at least 12 characters (typing is hidden),"
    note "or just press Enter and the installer creates a strong one for you."
    while true; do
        ask_secret ADMIN_PASSWORD "Admin password"
        if [ -z "$ADMIN_PASSWORD" ]; then
            ADMIN_PASSWORD="$(gen_password)"; PASSWORD_GENERATED=1
            ok "A strong password will be created. It is shown once at the end: have a place ready to save it."
            return 0
        fi
        if [ "${#ADMIN_PASSWORD}" -lt 12 ]; then warn "That has ${#ADMIN_PASSWORD} characters; it needs at least 12."; continue; fi
        if [ "${#ADMIN_PASSWORD}" -gt 128 ]; then warn "That is longer than 128 characters."; continue; fi
        ask_secret again "Same password again"
        [ "$again" = "$ADMIN_PASSWORD" ] && { PASSWORD_GENERATED=0; return 0; }
        warn "The two passwords are different. Please try again."
    done
}

ask_email() {
    if [ "$NONINTERACTIVE" = 1 ]; then
        SMTP_HOST="${CHESSLOOP_SMTP_HOST:-}"
        [ -n "$SMTP_HOST" ] || { EMAIL_ON=0; return 0; }
        EMAIL_ON=1
        SMTP_PORT="${CHESSLOOP_SMTP_PORT:-587}"
        SMTP_USER="${CHESSLOOP_SMTP_USER:-}"
        SMTP_PASSWORD="${CHESSLOOP_SMTP_PASSWORD:-}"
        SMTP_FROM="${CHESSLOOP_SMTP_FROM:-}"
        SMTP_USE_TLS="${CHESSLOOP_SMTP_USE_TLS:-true}"
        valid_port "$SMTP_PORT" || fatal "CHESSLOOP_SMTP_PORT must be a port number."
        return 0
    fi
    header "Email (optional)"
    note "ChessLoop can send emails: a link to confirm a new account, and password resets."
    note "For that it needs your mail provider's SMTP details."
    note "Without email, new users can sign in right away and you, the admin, reset"
    note "passwords in Admin → Users. You can add email later in ${SUBDIR:-the}/.env."
    blank
    _say "    ${BOLD}1)${RST} No, skip email for now ${DIM}(recommended if you're not sure)${RST}"
    _say "    ${BOLD}2)${RST} Yes, I have SMTP details"
    local choice
    while true; do
        ask choice "Email [1-2]" 1
        case "$choice" in 1) EMAIL_ON=0; return 0 ;; 2) break ;; *) warn "Please type 1 or 2." ;; esac
    done
    EMAIL_ON=1
    ask_smtp_details
}

ask_smtp_details() {
    local tls
    ask SMTP_HOST "SMTP server (for example smtp.gmail.com)" "${SMTP_HOST:-}"
    while true; do
        ask SMTP_PORT "SMTP port" "${SMTP_PORT:-587}"
        valid_port "$SMTP_PORT" && break
        warn "Please type a port number (often 587)."
    done
    ask SMTP_USER "SMTP username (often your email address; Enter if none)" "${SMTP_USER:-}"
    if [ -n "$SMTP_USER" ]; then
        ask_secret SMTP_PASSWORD "SMTP password (for Gmail: an app password)"
    fi
    ask SMTP_FROM "Sender address (Enter = the username)" "${SMTP_FROM:-}"
    if ask_yn "Use STARTTLS encryption (say yes unless your provider says otherwise)?" Y; then tls=true; else tls=false; fi
    SMTP_USE_TLS="$tls"
}

ask_seed() {
    if [ "$NONINTERACTIVE" = 1 ]; then
        case "${CHESSLOOP_SEED:-1}" in 0|no|false) SEED=0 ;; *) SEED=1 ;; esac
        return 0
    fi
    header "Starter content"
    note "ChessLoop comes with 16 starter opening libraries (Ruy López, Sicilian, …)."
    if ask_yn "Load the starter opening libraries? (recommended)" Y; then SEED=1; else SEED=0; fi
}

ask_wsl_keepalive() {
    WSL_KEEPALIVE=0
    [ "$IS_WSL" = 1 ] && [ "$DOCKER_KIND" != desktop ] || return 0
    if [ "$NONINTERACTIVE" = 1 ]; then
        case "${CHESSLOOP_WSL_KEEPALIVE:-1}" in 0|no|false) WSL_KEEPALIVE=0 ;; *) WSL_KEEPALIVE=1 ;; esac
        return 0
    fi
    header "Keep ChessLoop running on Windows"
    note "Windows stops Ubuntu (and ChessLoop with it) about 15 seconds after you close"
    note "the last Ubuntu window, and doesn't start it again when Windows restarts."
    note "The installer can change two settings for your Windows user (no admin rights needed):"
    note "  • keep Ubuntu running when its window is closed (.wslconfig)"
    note "  • start Ubuntu when you sign in to Windows (a small ChessLoop.cmd in Startup)"
    if ask_yn "Keep ChessLoop running this way? (recommended)" Y; then WSL_KEEPALIVE=1; fi
}

# ═══════════════════════════════════════════════════════════════════════════
#  PLAN
# ═══════════════════════════════════════════════════════════════════════════
show_plan_and_confirm() {
    header "Ready to install"
    note "This is what happens next:"
    [ "${#NEED_PKGS[@]}" -gt 0 ] && note "  • Install ${NEED_PKGS[*]} (system packages)"
    if [ "${#CONFLICT_PKGS[@]}" -gt 0 ]; then
        note "  • ${Y}Remove${RST} ${CONFLICT_PKGS[*]}: Docker's own packages replace them (Docker's instructions say so)"
    fi
    [ "$NEED_DOCKER_INSTALL" = 1 ] && note "  • Install Docker Engine from Docker's official repository (download.docker.com)"
    [ "$NEED_COMPOSE_FIX" = 1 ] && note "  • Add Docker's compose plugin"
    if [ "$RESUME" = 1 ] || [ "$REUSE_CLONE" = 1 ]; then
        note "  • Use the ChessLoop files already in $INSTALL_DIR"
    else
        note "  • Download ChessLoop into $INSTALL_DIR (owned by $OWNER)"
    fi
    note "  • Build and start ChessLoop on port $PORT, for $(access_words "$ACCESS")"
    [ "$(state_get admin)" = "done" ] || note "  • Create the admin account $ADMIN_EMAIL"
    [ "$EMAIL_ON" = 1 ] && [ -n "$SMTP_HOST" ] && note "  • Send a test email to $ADMIN_EMAIL through $SMTP_HOST"
    [ "$SEED" = 1 ] && [ "$(state_get seed)" != "done" ] && note "  • Load the starter opening libraries"
    [ "$WSL_KEEPALIVE" = 1 ] && note "  • Keep Ubuntu running and start it with Windows (.wslconfig, Startup\\ChessLoop.cmd)"
    [ "$WSL_MIRRORED" = 1 ] && note "  • Turn on WSL mirrored networking (.wslconfig)"
    blank
    note "It takes about 3 to 10 minutes, mostly downloading and building, and uses about 3 GB of disk."
    note "You can leave it running: there are no more questions after this one."
    [ -n "$LOG_FILE" ] && note "${DIM}Everything is also written to $LOG_FILE${RST}"
    blank
    if [ "$NONINTERACTIVE" = 1 ]; then return 0; fi
    ask_yn "Continue?" Y || fatal "Stopped. Nothing was changed."
}

# ═══════════════════════════════════════════════════════════════════════════
#  ADMINISTRATOR RIGHTS
# ═══════════════════════════════════════════════════════════════════════════
# setup_root ["why"]: sudo from here on (asks for the password once, if needed).
setup_root() {
    local why="${1:-to install system software and to create $INSTALL_DIR}"
    [ "${#AS_ROOT[@]}" -gt 0 ] && return 0
    if [ "$(id -u)" -eq 0 ]; then AS_ROOT=(); return 0; fi
    command -v sudo >/dev/null 2>&1 || fatal "This needs administrator rights (sudo) $why, and sudo isn't installed. Run it as root, or install sudo."
    AS_ROOT=(sudo)
    if ! sudo -n true 2>/dev/null; then
        info "Administrator rights are needed $why."
        note "Type ${BOLD}your own password${RST} for $CL_USER when asked."
        note "Nothing appears while you type; that's normal. Press Enter when done."
        if [ "$NONINTERACTIVE" = 1 ] && ! tty_ok; then
            fatal "sudo needs a password, and there is no terminal to type it in. Run as root, or allow $CL_USER to use sudo without a password."
        fi
        sudo -v || fatal "sudo didn't accept the password (or $CL_USER isn't allowed to use sudo). Ask whoever set up this computer to add $CL_USER to the 'sudo' group."
    fi
    start_sudo_keepalive
}

# Keeps sudo's timestamp fresh, so a long build never stops for a password.
start_sudo_keepalive() {
    [ -z "$SUDO_KEEPALIVE_PID" ] || return 0
    ( while kill -0 "$$" 2>/dev/null; do sudo -n -v 2>/dev/null || exit 0; sleep 50; done ) &
    SUDO_KEEPALIVE_PID=$!
}

stop_sudo_keepalive() {
    [ -n "$SUDO_KEEPALIVE_PID" ] || return 0
    kill "$SUDO_KEEPALIVE_PID" 2>/dev/null || true
    SUDO_KEEPALIVE_PID=""
}

# ═══════════════════════════════════════════════════════════════════════════
#  SOFTWARE: packages and Docker
# ═══════════════════════════════════════════════════════════════════════════
apt_get() {
    "${AS_ROOT[@]}" env DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=300 -y "$@"
}

APT_UPDATED=0
apt_update_once() {
    [ "$APT_UPDATED" = 1 ] && return 0
    run "Updating the list of available packages" apt_get update || explain_network_failure
    APT_UPDATED=1
}

explain_network_failure() {
    note "This is usually a network problem: check this computer's internet connection."
    FATAL_SHOWN=1; exit 1
}

install_packages() {
    [ "${#NEED_PKGS[@]}" -gt 0 ] || return 0
    step "Installing system packages"
    apt_update_once
    run "Installing ${NEED_PKGS[*]}" apt_get install --no-install-recommends "${NEED_PKGS[@]}" || explain_network_failure
}

# Fingerprint of Docker's apt signing key ("Docker Release (CE deb)", created
# 2017-02-22), as Docker's install docs published it (github.com/docker/docs,
# install/linux/docker-ce/debian.md at faff4a3) and as download.docker.com
# served it for Ubuntu and Debian on 2026-10-18. apt trusts whatever key is in
# docker.asc, so a key from a tampered download would let it install anything.
DOCKER_KEY_FPR=9DC858229FC7DD38854AE2D88D81803C0EBFCD88

# docker_key_ok FILE: FILE holds exactly one key, and it is Docker's.
docker_key_ok() {
    local home fprs rc=0
    home="$(mktemp -d)"   # gpg would otherwise create ~/.gnupg
    fprs="$(GNUPGHOME="$home" gpg --batch --show-keys --with-colons "$1" 2>/dev/null \
        | awk -F: '$1 == "pub" { want = 1; next } want && $1 == "fpr" { print $10; want = 0 }')" || rc=$?
    rm -rf "$home"
    [ "$rc" -eq 0 ] && [ "$fprs" = "$DOCKER_KEY_FPR" ]
}

# Docker's apt repository, as in docs.docker.com/engine/install/{ubuntu,debian}
# (deb822 .sources file, key in /etc/apt/keyrings; checked 2026-10-17).
add_docker_repo() {
    local distro codename arch tmp key
    [ -f /etc/apt/sources.list.d/docker.sources ] && return 0
    if [ "$OS_ID" = ubuntu ] || [ -n "$OS_UBUNTU_CODENAME" ]; then
        distro=ubuntu; codename="${OS_UBUNTU_CODENAME:-$OS_CODENAME}"
    else
        distro=debian; codename="$OS_CODENAME"
    fi
    [ -n "$codename" ] || fatal "Can't tell which $distro release this is (no VERSION_CODENAME in /etc/os-release)."
    arch="$(dpkg --print-architecture)"
    run "Creating /etc/apt/keyrings" "${AS_ROOT[@]}" install -m 0755 -d /etc/apt/keyrings
    key="$(mktemp)"
    run "Downloading Docker's signing key" curl -fsSL "https://download.docker.com/linux/$distro/gpg" -o "$key" \
        || { rm -f "$key"; explain_network_failure; }
    if ! docker_key_ok "$key"; then
        rm -f "$key"
        fatal "The signing key downloaded from download.docker.com is not Docker's known key (fingerprint $DOCKER_KEY_FPR), so the installer stopped before trusting it. Something between this computer and Docker may have changed the download. Try again later or on another network; if it keeps happening, please report it."
    fi
    "${AS_ROOT[@]}" install -m 0644 "$key" /etc/apt/keyrings/docker.asc
    rm -f "$key"
    tmp="$(mktemp)"
    printf 'Types: deb\nURIs: https://download.docker.com/linux/%s\nSuites: %s\nComponents: stable\nArchitectures: %s\nSigned-By: /etc/apt/keyrings/docker.asc\n' \
        "$distro" "$codename" "$arch" > "$tmp"
    "${AS_ROOT[@]}" install -m 0644 "$tmp" /etc/apt/sources.list.d/docker.sources
    rm -f "$tmp"
    ok "Added Docker's repository ($distro $codename)"
    APT_UPDATED=0
    apt_update_once
}

install_docker_engine() {
    step "Installing Docker"
    note "Docker runs ChessLoop in sealed boxes (\"containers\"), so nothing else on this"
    note "computer is changed. It comes from Docker's official repository."
    apt_update_once
    if [ "${#CONFLICT_PKGS[@]}" -gt 0 ]; then
        run "Removing ${CONFLICT_PKGS[*]} (replaced by Docker's packages)" apt_get remove "${CONFLICT_PKGS[@]}" \
            || fatal "Couldn't remove ${CONFLICT_PKGS[*]}. See the log."
    fi
    add_docker_repo
    run "Installing Docker Engine (about 1 minute)" apt_get install \
        docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin || explain_network_failure
}

# apt_candidate PKG: the version apt would install, or nothing.
apt_candidate() {
    apt-cache policy "$1" 2>/dev/null | awk '/Candidate:/ && $2 != "(none)" {print $2; exit}'
}

# distro_compose_pkg: the distribution's compose v2 package for its docker.io:
# docker-compose-v2 (Ubuntu) or docker-compose 2.x (Debian 13; Debian 12's is
# the old 1.x tool, which is not "docker compose"). Nothing if none fits.
distro_compose_pkg() {
    local v
    dpkg-query -W -f='${Status}' docker.io 2>/dev/null | grep -q 'install ok installed' || return 0
    if [ -n "$(apt_candidate docker-compose-v2)" ]; then echo docker-compose-v2; return 0; fi
    v="$(apt_candidate docker-compose)"
    v="${v#*:}"   # drop an epoch
    [ "${v%%.*}" -ge 2 ] 2>/dev/null && echo docker-compose
    return 0
}

# Docker from the distribution (docker.io) without "docker compose" (F-013).
install_compose_plugin() {
    step "Adding Docker's compose plugin"
    apt_update_once
    local pkg
    pkg="$(distro_compose_pkg)"
    if [ -n "$pkg" ]; then
        # The distribution packages compose v2 for its own docker.io. Docker's
        # plugin would also pull in docker-buildx-plugin, which collides with the
        # distribution's docker-buildx (Debian 13, F-087).
        run "Installing $pkg (matches the docker.io package)" apt_get install "$pkg" || explain_network_failure
    else
        add_docker_repo
        run "Installing docker-compose-plugin from Docker's repository" apt_get install docker-compose-plugin || explain_network_failure
    fi
    if ! docker buildx version >/dev/null 2>&1; then
        if [ -n "$(apt-cache policy docker-buildx 2>/dev/null | awk '/Candidate:/ && $2 != "(none)" {print $2}')" ] \
            && dpkg-query -W -f='${Status}' docker.io 2>/dev/null | grep -q 'install ok installed'; then
            run "Installing docker-buildx (needed to build ChessLoop)" apt_get install docker-buildx || true
        else
            add_docker_repo
            run "Installing docker-buildx-plugin (needed to build ChessLoop)" apt_get install docker-buildx-plugin || true
        fi
    fi
}

start_docker() {
    local i
    if [ "$DOCKER_KIND" = desktop ]; then DOCKER=(docker); return 0; fi
    if [ "$HAS_SYSTEMD" = 1 ]; then
        # Docker starts at boot and brings ChessLoop back (restart: always).
        run "Starting Docker and turning on start at boot" "${AS_ROOT[@]}" systemctl enable --now docker.service containerd.service \
            || fatal "Docker didn't start. See: sudo systemctl status docker"
    elif command -v service >/dev/null 2>&1; then
        "${AS_ROOT[@]}" service docker start >/dev/null 2>&1 || true
    fi
    for i in 1 2 3 4 5 6 7 8 9 10; do
        if docker info >/dev/null 2>&1; then DOCKER=(docker); break; fi
        if "${AS_ROOT[@]}" docker info >/dev/null 2>&1; then DOCKER=("${AS_ROOT[@]}" docker); break; fi
        [ "$i" -eq 10 ] && fatal "Docker is installed but not running. See: sudo systemctl status docker"
        sleep 2
    done
    # Let the user run docker without sudo after logging in again (F-029).
    if [ "$(id -u)" -ne 0 ] && ! id -nG "$CL_USER" 2>/dev/null | tr ' ' '\n' | grep -qx docker; then
        "${AS_ROOT[@]}" usermod -aG docker "$CL_USER" \
            && ok "Added $CL_USER to the \"docker\" group (lets you run docker commands without sudo after you log out and in again)."
    fi
    "${DOCKER[@]}" compose version >/dev/null 2>&1 || fatal "\"docker compose\" still doesn't work. Please report this, with the log."
    ok "Docker $("${DOCKER[@]}" version --format '{{.Server.Version}}' 2>/dev/null), Compose $("${DOCKER[@]}" compose version --short 2>/dev/null)"
}

setup_software() {
    install_packages
    if [ "$NEED_DOCKER_INSTALL" = 1 ]; then install_docker_engine
    elif [ "$NEED_COMPOSE_FIX" = 1 ]; then install_compose_plugin; fi
    step "Starting Docker"
    start_docker
}

# ═══════════════════════════════════════════════════════════════════════════
#  CHESSLOOP: files, settings, build
# ═══════════════════════════════════════════════════════════════════════════
# as_owner COMMAND...: runs COMMAND as the user who owns the install folder.
as_owner() {
    if [ "$OWNER" = "$CL_USER" ]; then
        "$@"
    elif [ "$(id -u)" -eq 0 ]; then
        sudo -u "$OWNER" -H "$@"
    else
        setup_root "to work in $INSTALL_DIR, which belongs to $OWNER"
        sudo -u "$OWNER" -H "$@"
    fi
}

get_source() {
    [ "$RESUME" = 1 ] || [ "$REUSE_CLONE" = 1 ] && return 0
    step "Downloading ChessLoop"
    if [ ! -d "$INSTALL_DIR" ]; then
        "${AS_ROOT[@]}" install -d -m 0755 -o "$OWNER" -g "$(id -gn "$OWNER" 2>/dev/null || echo "$OWNER")" "$INSTALL_DIR" \
            || fatal "Couldn't create $INSTALL_DIR."
    fi
    use_latest_release
    run "Downloading ChessLoop ($CL_REF) into $INSTALL_DIR" as_owner git clone --quiet "$CL_REPO" "$INSTALL_DIR" \
        || { note "Couldn't download $CL_REPO."; explain_network_failure; }
    if [ "$CL_REF" != main ] || [ -n "${CHESSLOOP_REF:-}" ]; then
        as_owner git -C "$INSTALL_DIR" checkout --quiet "$CL_REF" >> "${LOG_FILE:-/dev/null}" 2>&1 \
            || fatal "The version '$CL_REF' doesn't exist in $CL_REPO (CHESSLOOP_REF)."
    fi
    ok "ChessLoop $(as_owner git -C "$INSTALL_DIR" log -1 --format='%h (%cs)' 2>/dev/null || true) in $INSTALL_DIR"
}

dc() {
    "${DOCKER[@]}" compose --project-directory "$SUBDIR" -f "$SUBDIR/docker-compose.prod.yml" "$@"
}

# Writes chessloop/.env from .env.example (every key documented there), mode 600.
write_config() {
    [ "$RESUME" = 1 ] && return 0
    step "Writing the settings"
    local env="$SUBDIR/.env" tmp frontend
    [ -f "$SUBDIR/.env.example" ] || fatal "$SUBDIR/.env.example is missing; the download looks incomplete."
    frontend="$(frontend_url_for "$ACCESS" "$PORT" "$DOMAIN" "$LAN_IP")"
    [ "$IS_WSL" = 1 ] && [ "$ACCESS" != domain ] && frontend="http://localhost:$PORT"
    tmp="$(umask 077; mktemp "$SUBDIR/.env.new.XXXXXX")"
    {
        echo "# Written by deploy.sh on $(date '+%Y-%m-%d %H:%M'). Keep this file private."
        echo "# After a change, run: cd $SUBDIR && sudo docker compose -f docker-compose.prod.yml up -d"
        echo ""
        cat "$SUBDIR/.env.example"
    } > "$tmp"
    chmod 600 "$tmp"
    env_set "$tmp" JWT_SECRET "$(gen_jwt_secret)"
    env_set "$tmp" PUBLIC_PORT "$PORT"
    env_set "$tmp" BIND_ADDR "$(bind_addr_for "$ACCESS")"
    env_set "$tmp" FRONTEND_URL "$frontend"
    [ "$ACCESS" = domain ] && env_set "$tmp" DOMAIN "$DOMAIN"
    if [ "$EMAIL_ON" = 1 ]; then
        env_set "$tmp" SMTP_HOST "$SMTP_HOST"
        env_set "$tmp" SMTP_PORT "$SMTP_PORT"
        [ -n "$SMTP_USER" ] && env_set "$tmp" SMTP_USER "$SMTP_USER"
        if [ -n "$SMTP_PASSWORD" ]; then
            env_set "$tmp" SMTP_PASSWORD "$SMTP_PASSWORD" \
                || fatal "The SMTP password contains characters the settings file can't store (a backslash before a quote, or at the end). Add it to $env by hand later."
        fi
        [ -n "$SMTP_FROM" ] && { env_set "$tmp" SMTP_FROM "$SMTP_FROM" || fatal "The sender address can't be stored; use a plain address."; }
        env_set "$tmp" SMTP_USE_TLS "$SMTP_USE_TLS"
    fi
    mv "$tmp" "$env"
    [ "$(id -u)" -eq 0 ] && [ "$OWNER" != root ] && chown "$OWNER" "$env"
    state_set config "done"
    ok "Settings written to $env (only $OWNER can read it)"
}

# Why did the build fail? network | disk | memory | "" (from the end of the log)
build_failure_reason() {
    local tail
    tail="$(tail -n 60 "${LOG_FILE:-/dev/null}" 2>/dev/null || true)"
    # Docker Hub answers 429 when one internet address downloads too much (F-088).
    if grep -qiE '429 Too Many Requests|toomanyrequests|pull rate limit' <<<"$tail"; then
        echo ratelimit
    elif grep -qiE 'registry-1\.docker\.io|TLS handshake timeout|no such host|i/o timeout|connection reset|temporary failure in name resolution|failed to (fetch|resolve|do request)|network is unreachable' <<<"$tail"; then
        echo network
    elif grep -qiE 'no space left on device' <<<"$tail"; then
        echo disk
    elif grep -qiE 'killed|out of memory|exit code: 137' <<<"$tail"; then
        echo memory
    fi
    return 0
}

explain_rate_limit() {
    note "Docker Hub, where ChessLoop's building blocks come from, is limiting downloads"
    note "from your internet address for now (\"429 Too Many Requests\"). This is not a"
    note "problem with this computer. Wait about an hour, then run the same command again;"
    note "nothing has to be undone."
}

explain_build_failure() {
    case "$(build_failure_reason)" in
        ratelimit)
            explain_rate_limit
            FATAL_SHOWN=1; exit 1 ;;
        network)
            note "Downloading from the internet failed (Docker Hub or a package server)."
            explain_network_failure ;;
        disk)
            note "The disk is full. Free up space (at least 3 GB), then run the installer again."
            FATAL_SHOWN=1; exit 1 ;;
        memory)
            note "The build ran out of memory. ChessLoop needs about 2 GB of RAM to build."
            FATAL_SHOWN=1; exit 1 ;;
    esac
}

build_and_start() {
    step "Building ChessLoop"
    note "The first build downloads and builds ChessLoop's parts: usually 2 to 8 minutes"
    note "(about 2 minutes on a fast connection). The line below shows what it is doing."
    run "Building ChessLoop" dc build || { explain_build_failure; fatal "The build failed. See the lines above and the log."; }

    step "Starting ChessLoop"
    if ! run "Starting ChessLoop and waiting until it is healthy" dc up -d --wait --wait-timeout 300; then
        explain_build_failure
        err "ChessLoop didn't become healthy within 5 minutes."
        note "Container status:"
        dc ps -a 2>&1 | sed 's/^/      /' >&2 || true
        note "Recent messages from the server part (backend):"
        dc logs --tail 25 backend 2>&1 | sed 's/^/      /' >&2 || true
        note "More: cd $SUBDIR && sudo docker compose -f docker-compose.prod.yml logs"
        FATAL_SHOWN=1; exit 1
    fi
    local i code=000
    for i in $(seq 1 20); do
        code="$(curl -s -o /dev/null -m 5 -w '%{http_code}' "http://127.0.0.1:$PORT/api/health" 2>/dev/null || true)"
        [ "$code" = 200 ] && break
        sleep 3
    done
    [ "$code" = 200 ] || fatal "ChessLoop's containers are healthy, but http://127.0.0.1:$PORT doesn't answer (last HTTP status $code). Is another program using port $PORT?"
    ok "ChessLoop answers on port $PORT"
}

# ═══════════════════════════════════════════════════════════════════════════
#  ADMIN ACCOUNT, EMAIL TEST, STARTER CONTENT
# ═══════════════════════════════════════════════════════════════════════════
# create_admin.py gets the password on stdin, never as an argument (ADR-0008).
run_create_admin() {
    local extra=()
    [ -n "${1:-}" ] && extra=("$1")
    printf '%s\n' "$ADMIN_PASSWORD" | dc exec -T \
        -e CHESSLOOP_ADMIN_EMAIL="$ADMIN_EMAIL" -e CHESSLOOP_ADMIN_USERNAME="$ADMIN_USERNAME" \
        backend python seeds/create_admin.py --password-stdin "${extra[@]}" 2>&1
}

# Signs in through the web port, exactly as the browser will.
verify_admin_login() {
    local body resp code
    body="{\"email\":\"$(json_escape "$ADMIN_EMAIL")\",\"password\":\"$(json_escape "$ADMIN_PASSWORD")\"}"
    resp="$(printf '%s' "$body" | curl -s -m 20 -w '\n%{http_code}' -H 'Content-Type: application/json' \
        --data-binary @- "http://127.0.0.1:$PORT/api/auth/login" 2>/dev/null || true)"
    code="${resp##*$'\n'}"
    [ "$code" = 200 ] && grep -q '"access_token"' <<<"$resp"
}

create_admin_account() {
    [ "$(state_get admin)" = "done" ] && { ok "Admin account: already created earlier ($(state_get admin_email))."; return 0; }
    step "Creating your admin account"
    local out rc tries=0
    while true; do
        tries=$((tries + 1))
        rc=0; out="$(run_create_admin)" || rc=$?
        _log "$out"
        if [ "$rc" -eq 0 ] && grep -q "existing password was kept" <<<"$out"; then
            # The account exists from an earlier, interrupted run: use the password chosen now.
            rc=0; out="$(run_create_admin --reset-password)" || rc=$?
            _log "$out"
        fi
        [ "$rc" -eq 0 ] && break
        if [ "$rc" -eq 2 ] && grep -qi "username" <<<"$out" && [ "$tries" -lt 3 ]; then
            ADMIN_USERNAME="$(printf '%s' "${ADMIN_EMAIL%%@*}" | tr -cd 'A-Za-z0-9_.-' | cut -c1-24)"
            [ "${#ADMIN_USERNAME}" -ge 3 ] || ADMIN_USERNAME="owner"
            ADMIN_USERNAME="$ADMIN_USERNAME-$(LC_ALL=C tr -dc 'a-z0-9' </dev/urandom 2>/dev/null | head -c 4 || true)"
            info "The username 'admin' is taken; using '$ADMIN_USERNAME' instead."
            continue
        fi
        err "Creating the admin account failed:"
        printf '%s\n' "$out" | sed 's/^/      /' >&2
        if [ "$rc" -eq 2 ] && [ "$NONINTERACTIVE" != 1 ]; then
            if grep -qi "email" <<<"$out"; then
                ask ADMIN_EMAIL "Admin email" ""
            else
                ask_admin_password
            fi
            continue
        fi
        fatal "Couldn't create the admin account (exit code $rc)."
    done
    ok "$(tail -n 1 <<<"$out")"
    if ! verify_admin_login; then
        fatal "The admin account was created, but signing in with it through http://127.0.0.1:$PORT failed. Please report this, with the log."
    fi
    ok "Checked: $ADMIN_EMAIL can sign in."
    state_set admin "done"
    state_set admin_email "$ADMIN_EMAIL"
}

# Sends one test email with the SMTP settings in .env (prints the error if any).
send_test_email() {
    dc exec -T -e TO="$ADMIN_EMAIL" backend python -c '
import os, smtplib, sys
from email.mime.text import MIMEText
from config import settings
m = MIMEText("This is a test email from the ChessLoop installer. Email works.")
m["Subject"] = "ChessLoop test email"
m["From"] = settings.smtp_from
m["To"] = os.environ["TO"]
try:
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
        if settings.smtp_use_tls:
            s.starttls()
        if settings.smtp_user:
            s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(m)
except Exception as e:
    print(f"{type(e).__name__}: {e}")
    sys.exit(1)
print("sent")' 2>&1
}

disable_email() {
    local env="$SUBDIR/.env" k
    for k in SMTP_HOST SMTP_PORT SMTP_USER SMTP_PASSWORD SMTP_FROM SMTP_USE_TLS; do
        env_set "$env" "$k" "" || true
    done
    EMAIL_ON=0
    run "Restarting ChessLoop without email" dc up -d --wait --wait-timeout 180 || true
}

test_email() {
    [ "$EMAIL_ON" = 1 ] || return 0
    [ "$(state_get email)" = "done" ] && return 0
    step "Testing email"
    local out
    while true; do
        if out="$(send_test_email)"; then
            ok "Test email sent to $ADMIN_EMAIL. Check that inbox (and the spam folder)."
            state_set email "done"
            return 0
        fi
        _log "$out"
        err "The test email couldn't be sent: $(tail -n 1 <<<"$out")"
        note "Without working email, new users who register would wait for an email that never comes."
        if [ "$NONINTERACTIVE" = 1 ]; then
            warn "Turning email off (--yes). Fix the SMTP_* lines in $SUBDIR/.env and restart ChessLoop later."
            disable_email
            return 0
        fi
        _say "    ${BOLD}1)${RST} Change the email settings and try again"
        _say "    ${BOLD}2)${RST} Turn email off for now ${DIM}(you can set it up later in $SUBDIR/.env)${RST}"
        local choice
        ask choice "Email problem [1-2]" 2
        if [ "$choice" = 1 ]; then
            ask_smtp_details
            local env="$SUBDIR/.env"
            env_set "$env" SMTP_HOST "$SMTP_HOST"; env_set "$env" SMTP_PORT "$SMTP_PORT"
            env_set "$env" SMTP_USER "$SMTP_USER"; env_set "$env" SMTP_PASSWORD "$SMTP_PASSWORD" || fatal "That SMTP password can't be stored; add it to $env by hand."
            env_set "$env" SMTP_FROM "$SMTP_FROM" || true; env_set "$env" SMTP_USE_TLS "$SMTP_USE_TLS"
            run "Restarting ChessLoop with the new email settings" dc up -d --wait --wait-timeout 180 || true
        else
            disable_email
            return 0
        fi
    done
}

load_starter_content() {
    [ "$SEED" = 1 ] || return 0
    [ "$(state_get seed)" = "done" ] && return 0
    step "Loading the starter opening libraries"
    local out
    if out="$(dc exec -T backend python seeds/seed_libraries.py 2>&1)"; then
        _log "$out"
        ok "$(grep -E '^Done' <<<"$out" | tail -n 1 || echo "Starter libraries loaded.")"
        state_set seed "done"
    else
        _log "$out"
        warn "Loading the starter libraries failed: $(tail -n 1 <<<"$out")"
        note "ChessLoop works without them. To try again later:"
        note "  cd $SUBDIR && sudo docker compose -f docker-compose.prod.yml exec backend python seeds/seed_libraries.py"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════
#  KEEP RUNNING (Docker's restart policy; on WSL also ADR-0017's keep-alive)
# ═══════════════════════════════════════════════════════════════════════════
# win_path_of VAR: a Windows environment variable (USERPROFILE, APPDATA) as a
# Linux path, through WSL's Windows interop ("" if that isn't available).
win_path_of() {
    local v
    command -v cmd.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1 || return 0
    # cmd.exe complains about a Linux current directory, so start it from C:
    v="$(cd /mnt/c 2>/dev/null && cmd.exe /c "echo %$1%" 2>/dev/null | tr -d '\r' | tail -n 1 || true)"
    [ -n "$v" ] && [ "$v" != "%$1%" ] || return 0
    wslpath -u "$v" 2>/dev/null || true
}

# Writes KEY=VALUE into [SECTION] of the Windows user's .wslconfig, keeping
# everything else (a copy of the old file is kept next to it).
wslconfig_set() {
    local file="$1" section="$2" key="$3" value="$4" tmp
    # PowerShell 5.1's ">" writes UTF-16: editing that as text would break it.
    if [ -f "$file" ] && has_nul "$file"; then return 2; fi
    tmp="$(mktemp)"
    if [ -f "$file" ]; then
        [ "$(ini_get "$section" "$key" < "$file")" = "$value" ] && { rm -f "$tmp"; return 0; }
        cp "$file" "$file.chessloop-backup-$(date +%Y%m%d-%H%M%S)"
        ini_set "$section" "$key" "$value" < "$file" > "$tmp"
    else
        ini_set "$section" "$key" "$value" < /dev/null > "$tmp"
    fi
    cat "$tmp" > "$file"
    rm -f "$tmp"
}

setup_wsl_windows_side() {
    [ "$WSL_KEEPALIVE" = 1 ] || [ "$WSL_MIRRORED" = 1 ] || return 0
    step "Windows settings for WSL"
    local profile appdata wslconfig startup
    profile="$(win_path_of USERPROFILE)"
    appdata="$(win_path_of APPDATA)"
    if [ -z "$profile" ] || [ ! -d "$profile" ]; then
        warn "Couldn't reach your Windows user folder from Ubuntu (Windows interop is off?)."
        print_wsl_manual_steps
        return 0
    fi
    wslconfig="$profile/.wslconfig"
    if [ -f "$wslconfig" ] && has_nul "$wslconfig"; then
        warn "Your Windows .wslconfig is saved in a format (UTF-16) the installer won't edit."
        note "Open it in Notepad (in PowerShell: notepad \$env:USERPROFILE\\.wslconfig), add these"
        note "two lines at the end, save, then run wsl --shutdown:"
        note "  [general]"
        note "  instanceIdleTimeout=-1"
        [ "$WSL_MIRRORED" = 1 ] && note "For phone access, also add networkingMode=mirrored under its [wsl2] line."
        if [ "$WSL_KEEPALIVE" = 1 ] && [ -n "$WSL_DISTRO" ]; then
            local su="${appdata:-$profile/AppData/Roaming}/Microsoft/Windows/Start Menu/Programs/Startup"
            if [ -d "$su" ]; then
                printf 'wsl.exe -d %s --exec /bin/true\r\n' "$WSL_DISTRO" > "$su/ChessLoop.cmd"
                ok "Ubuntu starts when you sign in to Windows (Startup\\ChessLoop.cmd)"
            fi
        fi
        return 0
    fi
    if [ "$WSL_KEEPALIVE" = 1 ]; then
        wslconfig_set "$wslconfig" general instanceIdleTimeout -1
        state_set wsl_keepalive "done"
        ok "Ubuntu keeps running when its window is closed ([general] instanceIdleTimeout=-1 in .wslconfig)"
        startup="${appdata:-$profile/AppData/Roaming}/Microsoft/Windows/Start Menu/Programs/Startup"
        if [ -d "$startup" ] && [ -n "$WSL_DISTRO" ]; then
            printf 'wsl.exe -d %s --exec /bin/true\r\n' "$WSL_DISTRO" > "$startup/ChessLoop.cmd"
            ok "Ubuntu starts when you sign in to Windows (Startup\\ChessLoop.cmd)"
        else
            warn "Couldn't find your Windows Startup folder; ChessLoop won't start by itself after a Windows restart."
        fi
    fi
    if [ "$WSL_MIRRORED" = 1 ]; then
        wslconfig_set "$wslconfig" wsl2 networkingMode mirrored
        state_set wsl_mirrored "done"
        ok "WSL mirrored networking turned on ([wsl2] networkingMode=mirrored in .wslconfig)"
    fi
    note "These settings apply after WSL restarts: restart Windows, or close Ubuntu and run"
    note "${BOLD}wsl --shutdown${RST} in PowerShell, then open Ubuntu once. Until then, closing"
    note "the Ubuntu window still stops ChessLoop."
}

print_wsl_manual_steps() {
    note "To set it up by hand, in Windows PowerShell (not as admin):"
    note "  Add-Content \"\$env:USERPROFILE\\.wslconfig\" \"[general]\`r\`ninstanceIdleTimeout=-1\""
    note "  Set-Content \"\$env:APPDATA\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\ChessLoop.cmd\" \"wsl.exe -d ${WSL_DISTRO:-Ubuntu} --exec /bin/true\""
    note "  wsl --shutdown"
}

# ═══════════════════════════════════════════════════════════════════════════
#  SUMMARY (shown only when the admin really can sign in)
# ═══════════════════════════════════════════════════════════════════════════
docker_words() {
    # Run as root through sudo: the install's owner still needs sudo until the docker group applies.
    if [ "${DOCKER[0]}" = sudo ] || { [ "$(id -u)" -eq 0 ] && [ "$OWNER" != root ]; }; then echo "sudo docker"; else echo "docker"; fi
}

print_summary() {
    local d url lan_ok=0 p
    d="$(docker_words)"
    blank
    _say "  ${G}${BOLD}╔══════════════════════════════════════════════════════════╗${RST}"
    _say "  ${G}${BOLD}║   ✓  ChessLoop is installed and running                  ║${RST}"
    _say "  ${G}${BOLD}╚══════════════════════════════════════════════════════════╝${RST}"
    blank
    _say "  ${BOLD}Open ChessLoop${RST}"
    if [ "$IS_WSL" = 1 ]; then
        _say "    In your Windows browser (Edge, Chrome, Firefox):  ${BOLD}http://localhost:$PORT${RST}"
    else
        _say "    On this computer:  ${BOLD}http://localhost:$PORT${RST}"
    fi
    case "$ACCESS" in
        lan)
            if [ "$IS_WSL" = 1 ] && [ "$DOCKER_KIND" = desktop ]; then
                _say "    On other devices in your network:  ${BOLD}http://YOUR-PC-ADDRESS:$PORT${RST}"
                note "YOUR-PC-ADDRESS is the IPv4 address in Windows Settings > Network & internet >"
                note "(your connection) > Properties. Windows' firewall must allow Docker Desktop on"
                note "that network: if a phone can't connect, check the \"Docker Desktop Backend\" rules."
            elif [ "$IS_WSL" = 1 ] && [ "$WSL_NET_MODE" != mirrored ]; then
                print_wsl_lan_steps
            else
                url="http://${LAN_IP:-THIS-COMPUTERS-ADDRESS}:$PORT"; lan_ok=1
                _say "    On other devices in your network:  ${BOLD}$url${RST}"
                if [ "$IS_WSL" = 1 ]; then
                    note "Windows' firewall must allow port $PORT. In PowerShell as administrator:"
                    note "  New-NetFirewallHyperVRule -Name ChessLoop -DisplayName ChessLoop -Direction Inbound -VMCreatorId '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' -Protocol TCP -LocalPorts $PORT"
                fi
            fi
            ;;
        domain)
            _say "    On the internet, after you set up HTTPS:  ${BOLD}https://$DOMAIN${RST}"
            note "ChessLoop itself only listens on this computer. Setting up HTTPS and"
            note "publishing it on the internet is not covered by this project:"
            note "  $HTTPS_GUIDE_URL"
            ;;
    esac
    [ "$lan_ok" = 1 ] && note "${DIM}(The address uses plain http://: only use it on a network you trust.)${RST}"
    blank
    _say "  ${BOLD}Sign in${RST} with ${BOLD}$ADMIN_EMAIL${RST}"
    if [ "$PASSWORD_GENERATED" = 1 ]; then
        show_password_once
    elif [ -n "$ADMIN_PASSWORD" ]; then
        note "and the password you chose. You can change it in Settings → Account."
    fi
    if [ "$EMAIL_ON" != 1 ]; then
        note "Email is off: people who register can sign in at once; you reset forgotten"
        note "passwords in Admin → Users. To add email later, see $SUBDIR/.env."
    fi
    blank
    _say "  ${BOLD}Keeps running${RST}"
    if [ "$DOCKER_KIND" = desktop ]; then
        note "While Docker Desktop runs. In Docker Desktop: Settings > General > \"Start Docker"
        note "Desktop when you sign in\" brings ChessLoop back after a Windows restart."
    elif [ "$IS_WSL" = 1 ]; then
        if [ "$WSL_KEEPALIVE" = 1 ]; then
            note "Also when the Ubuntu window is closed, and after a Windows restart (once the"
            note "new WSL settings apply; see above)."
        else
            note "Only while an Ubuntu window is open. To change that, run the installer's"
            note "keep-alive step by hand:"
            print_wsl_manual_steps
        fi
    else
        note "Docker starts at boot and starts ChessLoop again by itself."
    fi
    blank
    p="$(prog_name)"
    _say "  ${BOLD}Manage it${RST} ${DIM}(type these in a terminal)${RST}"
    note "$p status     is it running? (address, version, latest backup)"
    note "$p backup     save all data to a file in ~/chessloop-backups"
    note "$p update     get the latest version (backs up first)"
    note "$p help       everything else: restore, stop, start, logs, uninstall"
    if [ "${DOCKER[0]}" = sudo ] && [ "$(id -u)" -ne 0 ]; then
        note "${DIM}Until you log out and in again, Docker commands need \"sudo\" ($d …).${RST}"
    fi
    blank
    note "Data: Docker volume ${BOLD}$VOLUME_NAME${RST}. Back it up with \"$p backup\" or in Admin → Backups."
    [ -n "$LOG_FILE" ] && note "Install log: $LOG_FILE"
    blank
}

print_wsl_lan_steps() {
    note "Other devices can't reach ChessLoop yet: WSL keeps Ubuntu's network private."
    note "To allow it (Microsoft's guide: $WSL_LAN_GUIDE_URL):"
    if [ "$WSL_MIRRORED" = 1 ]; then
        note "  1. Restart WSL so mirrored networking applies: in PowerShell, ${BOLD}wsl --shutdown${RST}"
    else
        note "  1. Add these lines to %UserProfile%\\.wslconfig, then run ${BOLD}wsl --shutdown${RST}:"
        note "       [wsl2]"
        note "       networkingMode=mirrored"
    fi
    note "  2. In PowerShell as administrator, allow the port through Windows' firewall:"
    note "       New-NetFirewallHyperVRule -Name ChessLoop -DisplayName ChessLoop -Direction Inbound -VMCreatorId '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' -Protocol TCP -LocalPorts $PORT"
    note "  3. Open Ubuntu and run: ${BOLD}hostname -I${RST}   Use the first address on your phone:"
    note "       http://THAT-ADDRESS:$PORT"
}

# ═══════════════════════════════════════════════════════════════════════════
#  INSTALL
# ═══════════════════════════════════════════════════════════════════════════
do_install() {
    ACTION=install
    [ -n "$LOG_FILE" ] || setup_log install
    header "Install ChessLoop"
    note "The installer checks this computer, asks a few questions, then sets everything up."
    note "Nothing is changed until you confirm."
    preflight
    check_existing_install
    if [ "${#CONFLICT_PKGS[@]}" -gt 0 ] && [ "$NONINTERACTIVE" = 1 ] && [ "${CHESSLOOP_ALLOW_PACKAGE_REMOVAL:-0}" != 1 ]; then
        fatal "Docker's instructions say to remove ${CONFLICT_PKGS[*]} first, and other software may use them. To allow that in --yes mode, set CHESSLOOP_ALLOW_PACKAGE_REMOVAL=1."
    fi

    if [ "$RESUME" = 1 ]; then
        load_resume_answers
        [ "$(state_get admin)" = "done" ] || ask_admin
        [ "$(state_get seed)" = "done" ] || ask_seed
    else
        ask_access
        ask_port
        ask_admin
        ask_email
        ask_seed
    fi
    ask_wsl_keepalive
    show_plan_and_confirm
    WORK_STARTED=1

    setup_root
    setup_software
    get_source
    write_config
    [ -f "$STATE_FILE" ] || state_set config "done"
    build_and_start
    create_admin_account
    test_email
    load_starter_content
    setup_wsl_windows_side
    install_command_link
    state_set ref "$CL_REF"
    state_set complete "$(date -Is)"
    CURRENT_STEP="finishing"
    print_summary
}

# ═══════════════════════════════════════════════════════════════════════════
#  AFTER THE INSTALL: finding it, Docker, the backend container
#  (shared by Update, Back up, Restore, Uninstall and the chessloop command)
# ═══════════════════════════════════════════════════════════════════════════
# The folder this script is in, when run from an install (bash
# /opt/chessloop/deploy.sh, or the chessloop command); "" under curl | bash.
script_dir() {
    local self
    self="$(readlink -f "${BASH_SOURCE[0]:-}" 2>/dev/null || true)"
    [ -f "$self" ] && dirname "$self"
    return 0
}

# locate_install: finds the install (CHESSLOOP_INSTALL_DIR; else /opt/chessloop,
# the folder of this script, or ~/chessloop) and sets INSTALL_DIR, SUBDIR,
# STATE_FILE, OWNER and PORT.
locate_install() {
    local d cands=("$INSTALL_DIR")
    [ -n "${CHESSLOOP_INSTALL_DIR:-}" ] || cands+=("$(script_dir)" "${HOME:-/nonexistent}/chessloop")
    for d in "${cands[@]}"; do
        [ -n "$d" ] && [ -f "$d/chessloop/docker-compose.prod.yml" ] || continue
        INSTALL_DIR="$(cd "$d" && pwd)"
        SUBDIR="$INSTALL_DIR/chessloop"
        STATE_FILE="$INSTALL_DIR/$STATE_NAME"
        OWNER="$(stat -c %U "$INSTALL_DIR" 2>/dev/null || echo "$OWNER")"
        PORT="$(env_get "$SUBDIR/.env" PUBLIC_PORT)"; PORT="${PORT:-$DEFAULT_PORT}"
        return 0
    done
    return 1
}

require_install() {
    if locate_install; then ok "ChessLoop install: $INSTALL_DIR"; return 0; fi
    fatal "No ChessLoop install found in $INSTALL_DIR. If it is in another folder: CHESSLOOP_INSTALL_DIR=/that/folder $(prog_name) $ACTION"
}

# docker_access: sets DOCKER to (docker), or (sudo docker) while the user isn't
# in the docker group yet; starts Docker if it is installed but stopped.
docker_access() {
    local i
    command -v docker >/dev/null 2>&1 || fatal "Docker isn't installed, so ChessLoop can't run here. To set everything up again: bash deploy.sh install"
    DOCKER_KIND="$(docker_kind_of "$(command -v docker)")"
    if docker info >/dev/null 2>&1; then DOCKER=(docker); return 0; fi
    if [ "$DOCKER_KIND" = desktop ] || [ "$DOCKER_KIND" = desktop-shim ]; then
        WSL_DISTRO="${WSL_DISTRO_NAME:-}"
        explain_desktop_shim
        FATAL_SHOWN=1; exit 1
    fi
    if [ "$(id -u)" -ne 0 ]; then
        setup_root "to use Docker (your user can use it without sudo only after logging out and in again)"
        if sudo docker info >/dev/null 2>&1; then DOCKER=(sudo docker); return 0; fi
    fi
    if [ "$(cat /proc/1/comm 2>/dev/null)" = systemd ]; then
        setup_root "to start Docker"
        run "Starting Docker" "${AS_ROOT[@]}" systemctl start docker.service || true
        for i in 1 2 3 4 5; do
            if docker info >/dev/null 2>&1; then DOCKER=(docker); return 0; fi
            if "${AS_ROOT[@]}" docker info >/dev/null 2>&1; then DOCKER=("${AS_ROOT[@]}" docker); return 0; fi
            sleep 2
        done
    fi
    fatal "Docker is installed but isn't running. Start it (sudo systemctl start docker), then try again."
}

backend_running() { [ -n "$(dc ps --status running -q backend 2>/dev/null)" ]; }

# in_backend [-e KEY=VALUE]... COMMAND...: runs COMMAND in the backend container
# (stdin is passed through), or in a one-off container from the same image when
# ChessLoop isn't running. The data volume is /data in both.
in_backend() {
    local envs=()
    while [ "${1:-}" = -e ]; do envs+=(-e "$2"); shift 2; done
    if backend_running; then
        dc exec -T "${envs[@]}" backend "$@"
    else
        fix_data_owner
        dc run --rm --no-deps -T "${envs[@]}" backend "$@"
    fi
}

# The backend runs as uid 10001 (S7). `up` hands older, root-owned data to it
# through the data-owner service; a one-off `run --no-deps` skips that, so do
# it here first. Versions without the service need nothing.
fix_data_owner() {
    dc config --services 2>/dev/null | grep -qx data-owner || return 0
    # stdin from /dev/null: the caller's stdin may be a backup being streamed
    # into the next command (stage_restore), and "compose run" would read it.
    dc run --rm --no-deps -T data-owner < /dev/null >> "${LOG_FILE:-/dev/null}" 2>&1 \
        || warn "Couldn't hand the data files to the ChessLoop user; the next step may fail."
}

describe_commit() {
    as_owner git -C "$INSTALL_DIR" log -1 --format='%h (%cs)' "$1" 2>/dev/null || echo "${1:0:7}"
}

# chessloop, or how to run this script when the command isn't there.
prog_name() {
    if [ "$(basename "$0" 2>/dev/null)" = chessloop ] || [ "$(readlink "$COMMAND_LINK" 2>/dev/null)" = "$INSTALL_DIR/deploy.sh" ]; then
        echo chessloop
    else
        echo "bash $INSTALL_DIR/deploy.sh"
    fi
}

# Starts ChessLoop and waits until it answers on its port.
start_chessloop() {
    run "${1:-Starting ChessLoop} and waiting until it is healthy" dc up -d --wait --wait-timeout 300 --remove-orphans || return 1
    wait_for_http
}

http_ok() {
    [ "$(curl -s -o /dev/null -m 5 -w '%{http_code}' "http://127.0.0.1:$PORT/api/health" 2>/dev/null || true)" = 200 ]
}

wait_for_http() {
    local i
    for i in $(seq 1 20); do
        http_ok && return 0
        sleep 3
    done
    err "ChessLoop's containers are running, but http://127.0.0.1:$PORT doesn't answer."
    return 1
}

# The backend's last messages, for an explanation after a failed start.
show_backend_messages() {
    note "Recent messages from the server part (backend):"
    dc logs --no-color --tail 20 backend 2>&1 | tee -a "${LOG_FILE:-/dev/null}" | sed 's/^/      /' >&2 || true
    if dc logs --no-color --tail 60 backend 2>/dev/null | grep -q 'JWT_SECRET'; then
        note "The backend refused the JWT_SECRET in $SUBDIR/.env: the message above says how to fix it."
    fi
}

# ═══════════════════════════════════════════════════════════════════════════
#  BACKUP AND RESTORE (ADR-0028). The work on the database happens in the
#  backend container (Python's sqlite3), so the host needs no SQLite tools.
# ═══════════════════════════════════════════════════════════════════════════
# Writes a backup archive to stdout: chessloop.db (a consistent copy made with
# SQLite's backup API while ChessLoop runs), the Admin-panel backups, a
# manifest with row counts and checksum, and, with CL_WITH_ENV=1, the settings
# file read from stdin. Messages for deploy.sh go to stderr as "CL: ...".
# shellcheck disable=SC2016  # Python code, not shell
PY_BACKUP='
import hashlib, io, json, os, sqlite3, sys, tarfile, tempfile, time
DB = "/data/chessloop.db"
def say(m): print("CL: " + m, file=sys.stderr, flush=True)
if not os.path.isfile(DB):
    say("error: no database yet (/data/chessloop.db)"); sys.exit(3)
tmp = tempfile.mkdtemp()
snap = os.path.join(tmp, "chessloop.db")
src = sqlite3.connect(DB, timeout=60); dst = sqlite3.connect(snap)
src.backup(dst); src.close()
check = dst.execute("pragma integrity_check").fetchone()[0]
tables = [r[0] for r in dst.execute("select name from sqlite_master where type = '"'"'table'"'"' and name not like '"'"'sqlite_%'"'"' order by name")]
counts = {t: dst.execute("select count(*) from \"%s\"" % t.replace("\"", "\"\"")).fetchone()[0] for t in tables}
dst.close()
if check != "ok":
    say("error: the database is damaged (integrity check: %s)" % check); sys.exit(4)
h = hashlib.sha256()
with open(snap, "rb") as f:
    for block in iter(lambda: f.read(1 << 20), b""): h.update(block)
env = sys.stdin.buffer.read() if os.environ.get("CL_WITH_ENV") == "1" else b""
manifest = {"format": 1, "created": time.strftime("%Y-%m-%d %H:%M:%S %z"),
            "chessloop_commit": os.environ.get("CL_COMMIT", ""), "db_sha256": h.hexdigest(),
            "counts": counts, "settings_included": bool(env)}
def add(tar, name, path=None, data=None):
    ti = tarfile.TarInfo(name); ti.mode = 0o600; ti.mtime = int(time.time())
    if path is None:
        ti.size = len(data); tar.addfile(ti, io.BytesIO(data))
    else:
        ti.size = os.path.getsize(path)
        with open(path, "rb") as f: tar.addfile(ti, f)
with tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz") as tar:
    add(tar, "manifest.json", data=json.dumps(manifest, indent=2).encode())
    add(tar, "chessloop.db", path=snap)
    if os.path.isdir("/data/backups"):
        for n in sorted(os.listdir("/data/backups")):
            p = os.path.join("/data/backups", n)
            if os.path.isfile(p): add(tar, "backups/" + n, path=p)
    if env: add(tar, "settings.env", data=env)
sys.stdout.buffer.flush()
for t in tables: say("count %s=%d" % (t, counts[t]))
say("ok")
'

# Reads a backup (CL_KIND=archive or sqlite) from stdin into /data/.restore,
# checks it (manifest checksum, SQLite integrity, row counts, has accounts) and
# reports its row counts. Changes nothing else.
# shellcheck disable=SC2016
PY_STAGE='
import hashlib, json, os, shutil, sqlite3, sys, tarfile
R = "/data/.restore"
def say(m): print("CL: " + m, file=sys.stderr, flush=True)
def fail(m): say("error: " + m); shutil.rmtree(R, ignore_errors=True); sys.exit(4)
shutil.rmtree(R, ignore_errors=True)
os.makedirs(R + "/backups", mode=0o700)
db = R + "/chessloop.db"; manifest = None
try:
    if os.environ.get("CL_KIND") == "sqlite":
        with open(db, "wb") as f: shutil.copyfileobj(sys.stdin.buffer, f)
    else:
        with tarfile.open(fileobj=sys.stdin.buffer, mode="r|gz") as tar:
            for m in tar:
                if not m.isfile(): continue
                name = m.name[2:] if m.name.startswith("./") else m.name
                if name == "manifest.json":
                    manifest = json.load(tar.extractfile(m)); continue
                if name == "chessloop.db": dest = db
                elif name.startswith("backups/") and "/" not in name[8:] and name[8:] not in ("", ".", ".."):
                    dest = os.path.join(R, name)
                else: continue
                with open(dest, "wb") as f: shutil.copyfileobj(tar.extractfile(m), f)
except (tarfile.TarError, OSError, EOFError, ValueError) as e:
    fail("the file can not be read (%s)" % e)
if os.environ.get("CL_KIND") != "sqlite" and manifest is None:
    fail("this archive has no manifest.json, so it was not made by deploy.sh backup")
if not os.path.isfile(db): fail("there is no database in this backup")
if manifest:
    h = hashlib.sha256()
    with open(db, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""): h.update(block)
    if manifest.get("db_sha256") != h.hexdigest(): fail("the database in the backup is damaged (checksum mismatch)")
try:
    c = sqlite3.connect(db)
    check = c.execute("pragma integrity_check").fetchone()[0]
    tables = [r[0] for r in c.execute("select name from sqlite_master where type = '"'"'table'"'"' and name not like '"'"'sqlite_%'"'"' order by name")]
    counts = {t: c.execute("select count(*) from \"%s\"" % t.replace("\"", "\"\"")).fetchone()[0] for t in tables}
    c.close()
except sqlite3.DatabaseError as e:
    fail("it is not a usable ChessLoop database (%s)" % e)
if check != "ok": fail("the database is damaged (integrity check: %s)" % check)
if not counts.get("user"):
    fail("it has no user accounts, so it is not a full ChessLoop backup")
if manifest and manifest.get("counts") not in (None, counts):
    fail("its row counts differ from its manifest")
for t in tables: say("count %s=%d" % (t, counts[t]))
if manifest:
    say("created " + str(manifest.get("created", "")))
    say("settings " + ("yes" if manifest.get("settings_included") else "no"))
say("ok")
'

# With ChessLoop stopped: puts the staged database in place (same owner and
# mode as the old one) and adds the staged Admin-panel backups that are missing.
# shellcheck disable=SC2016
PY_SWAP='
import os, shutil, sys
D = "/data"; R = D + "/.restore"; DB = D + "/chessloop.db"
if not os.path.isfile(R + "/chessloop.db"):
    print("CL: error: nothing to restore", file=sys.stderr); sys.exit(4)
st = os.stat(DB) if os.path.exists(DB) else None
for s in ("-wal", "-shm", "-journal"):
    if os.path.exists(DB + s): os.remove(DB + s)
os.replace(R + "/chessloop.db", DB)
if st:
    os.chown(DB, st.st_uid, st.st_gid); os.chmod(DB, st.st_mode & 0o777)
os.makedirs(D + "/backups", exist_ok=True)
for n in os.listdir(R + "/backups"):
    dest = os.path.join(D, "backups", n)
    if not os.path.exists(dest):
        shutil.move(os.path.join(R, "backups", n), dest); os.chmod(dest, 0o600)
shutil.rmtree(R, ignore_errors=True)
print("CL: ok", file=sys.stderr)
'

# Row counts of the live database, "table=count" per line.
# shellcheck disable=SC2016
PY_COUNTS='
import os, sqlite3, sys
if not os.path.isfile("/data/chessloop.db"): sys.exit(3)
c = sqlite3.connect("/data/chessloop.db", timeout=60)
for (t,) in c.execute("select name from sqlite_master where type = '"'"'table'"'"' and name not like '"'"'sqlite_%'"'"' order by name"):
    print("%s=%d" % (t, c.execute("select count(*) from \"%s\"" % t.replace("\"", "\"\"")).fetchone()[0]))
'

BACKUP_COUNTS=""
BACKUP_ERROR=""
RESTORE_COUNTS=""
RESTORE_ERROR=""
RESTORE_CREATED=""
RESTORE_HAS_SETTINGS=0

# Backups go to the install owner's home, also when run with sudo.
setup_backup_dir() {
    local home
    [ -n "$BACKUP_DIR" ] && return 0
    home="$(getent passwd "$OWNER" 2>/dev/null | cut -d: -f6 || true)"
    BACKUP_DIR="${CHESSLOOP_BACKUP_DIR:-${home:-${HOME:-/tmp}}/chessloop-backups}"
    [ -d "$BACKUP_DIR" ] && return 0
    as_owner install -d -m 700 "$BACKUP_DIR" 2>/dev/null || install -d -m 700 "$BACKUP_DIR" \
        || fatal "Couldn't create the backup folder $BACKUP_DIR."
}

# make_backup FILE WITH_SETTINGS(0/1): FILE (mode 600) and FILE.sha256.
# Sets BACKUP_COUNTS, or BACKUP_ERROR and fails.
make_backup() {
    local file="$1" with="$2" part errf rc=0 commit input=/dev/null
    part="$file.part"
    errf="$(mktemp)"
    commit="$(as_owner git -C "$INSTALL_DIR" log -1 --format=%h 2>/dev/null || true)"
    [ "$with" = 1 ] && input="$SUBDIR/.env"
    ( umask 077; in_backend -e "CL_WITH_ENV=$with" -e "CL_COMMIT=$commit" python -c "$PY_BACKUP" \
        < "$input" > "$part" 2> "$errf" ) || rc=$?
    sed 's/^/    /' "$errf" >> "${LOG_FILE:-/dev/null}" 2>/dev/null || true
    BACKUP_COUNTS="$(sed -n 's/^CL: count //p' "$errf")"
    if [ "$rc" -ne 0 ] || ! grep -qx 'CL: ok' "$errf" || ! gzip -t "$part" 2>/dev/null; then
        BACKUP_ERROR="$(sed -n 's/^CL: error: //p' "$errf" | tail -n 1)"
        [ -n "$BACKUP_ERROR" ] || BACKUP_ERROR="$(grep -v '^CL: ' "$errf" | grep -v '^[[:space:]]*$' | tail -n 1 || true)"
        BACKUP_ERROR="${BACKUP_ERROR:-unknown error (exit code $rc)}"
        rm -f "$part" "$errf"
        return 1
    fi
    rm -f "$errf"
    mv "$part" "$file"
    ( cd "$(dirname "$file")" && umask 077 && sha256sum "$(basename "$file")" > "$(basename "$file").sha256" )
    chmod 600 "$file" "$file.sha256"
    if [ "$(id -u)" -eq 0 ] && [ "$OWNER" != root ]; then chown "$OWNER" "$file" "$file.sha256" 2>/dev/null || true; fi
    _log "  backup written: $file ($(stat -c %s "$file") bytes)"
}

# stage_restore FILE KIND: copies the backup into the data volume (/data/.restore)
# and checks it. Sets RESTORE_COUNTS, RESTORE_CREATED, RESTORE_HAS_SETTINGS, or
# RESTORE_ERROR and fails.
stage_restore() {
    local file="$1" kind="$2" errf rc=0
    errf="$(mktemp)"
    in_backend -e "CL_KIND=$kind" python -c "$PY_STAGE" < "$file" > /dev/null 2> "$errf" || rc=$?
    sed 's/^/    /' "$errf" >> "${LOG_FILE:-/dev/null}" 2>/dev/null || true
    RESTORE_COUNTS="$(sed -n 's/^CL: count //p' "$errf")"
    RESTORE_CREATED="$(sed -n 's/^CL: created //p' "$errf" | head -n 1)"
    RESTORE_HAS_SETTINGS=0
    grep -qx 'CL: settings yes' "$errf" && RESTORE_HAS_SETTINGS=1
    if [ "$rc" -ne 0 ] || ! grep -qx 'CL: ok' "$errf"; then
        RESTORE_ERROR="$(sed -n 's/^CL: error: //p' "$errf" | tail -n 1)"
        [ -n "$RESTORE_ERROR" ] || RESTORE_ERROR="$(grep -v '^CL: ' "$errf" | grep -v '^[[:space:]]*$' | tail -n 1 || true)"
        RESTORE_ERROR="${RESTORE_ERROR:-unknown error (exit code $rc)}"
        rm -f "$errf"
        return 1
    fi
    rm -f "$errf"
}

discard_staged_restore() {
    in_backend python -c 'import shutil; shutil.rmtree("/data/.restore", True)' >/dev/null 2>&1 || true
}

# With ChessLoop stopped, puts the staged data in place.
swap_in_staged_data() {
    run "Stopping ChessLoop" dc stop || return 1
    fix_data_owner
    run "Putting the backup's data in place" dc run --rm --no-deps -T backend python -c "$PY_SWAP"
}

current_counts() { in_backend python -c "$PY_COUNTS" 2>/dev/null; }

counts_words() {
    echo "accounts: $(count_of "$1" user), libraries: $(count_of "$1" library), lines: $(count_of "$1" line)"
}

# check_counts EXPECTED: the live database has exactly these row counts.
check_counts() {
    local expected="$1" actual diff
    actual="$(current_counts || true)"
    if diff="$(counts_diff "$expected" "$actual")"; then
        ok "Checked: every table has the same number of rows as the backup ($(counts_words "$expected"))."
        return 0
    fi
    err "The data doesn't match the backup:"
    printf '%s\n' "$diff" | sed 's/^/      /' >&2
    _log "$diff"
    return 1
}

do_backup() {
    ACTION=backup
    [ -n "$LOG_FILE" ] || setup_log backup
    header "Back up ChessLoop"
    require_install
    docker_access
    setup_backup_dir
    local file="${BACKUP_TARGET:-}" with=0
    if [ -z "$file" ]; then file="$BACKUP_DIR/$(backup_file_name "")"
    elif [ -d "$file" ]; then file="${file%/}/$(backup_file_name "")"; fi
    case "$file" in /*) ;; *) file="$PWD/$file" ;; esac
    [ -e "$file" ] && fatal "$file already exists. Choose another name."
    [ -d "$(dirname "$file")" ] || fatal "The folder $(dirname "$file") doesn't exist."
    if [ "${CHESSLOOP_BACKUP_SETTINGS:-0}" = 1 ]; then
        with=1
    elif [ "$NONINTERACTIVE" != 1 ]; then
        note "The backup holds all accounts, libraries and progress. It can also hold the"
        note "settings file (.env) with your secret key and email password, which you only"
        note "need to set up the same settings on another computer."
        ask_yn "Also put the settings file in the backup?" N && with=1
    fi
    info "Backing up (ChessLoop keeps running)…"
    make_backup "$file" "$with" || fatal "The backup failed: $BACKUP_ERROR. Nothing was saved."
    ok "Backup saved: ${BOLD}$file${RST} ($(human_size "$(stat -c %s "$file")"))"
    note "It holds $(counts_words "$BACKUP_COUNTS")$([ "$with" = 1 ] && echo ", and the settings file")."
    note "Its checksum is in $(basename "$file").sha256: keep the two files together."
    note "Keep it private: it holds password hashes and two-factor secrets$([ "$with" = 1 ] && echo ", and your secret key")."
    note "Copy it to another computer or a USB stick: a backup on the same disk is lost with the disk."
    note "To restore it later:  $(prog_name) restore $file"
}

choose_backup_file() {
    local files=() f i=0 choice
    [ "$NONINTERACTIVE" = 1 ] && fatal "Name the backup to restore: $(prog_name) restore FILE --yes"
    # shellcheck disable=SC2012  # file names the script chose; newest first
    mapfile -t files < <(ls -1t "$BACKUP_DIR"/chessloop-*.tar.gz 2>/dev/null | head -n 9 || true)
    if [ "${#files[@]}" -eq 0 ]; then
        note "There are no backups in $BACKUP_DIR."
        ask RESTORE_FILE "Path of the backup file" ""
        return 0
    fi
    note "Backups in $BACKUP_DIR, newest first:"
    for f in "${files[@]}"; do
        i=$((i + 1))
        _say "    ${BOLD}$i)${RST} $(basename "$f")  ${DIM}($(human_size "$(stat -c %s "$f")"))${RST}"
    done
    _say "    ${BOLD}0)${RST} Another file (you type its path)"
    while true; do
        ask choice "Backup [0-$i]" 1
        if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "$i" ]; then
            RESTORE_FILE="${files[$((choice - 1))]}"; return 0
        fi
        if [ "$choice" = 0 ]; then ask RESTORE_FILE "Path of the backup file" ""; return 0; fi
        warn "Please type a number from 0 to $i."
    done
}

do_restore() {
    ACTION=restore
    [ -n "$LOG_FILE" ] || setup_log restore
    header "Restore ChessLoop from a backup"
    require_install
    docker_access
    setup_backup_dir
    [ -n "${RESTORE_FILE:-}" ] || choose_backup_file
    local file="${RESTORE_FILE/#\~/$HOME}" kind expected current safety=""
    case "$file" in /*) ;; *) file="$PWD/$file" ;; esac
    [ -f "$file" ] || fatal "There is no file $file."
    kind="$(backup_kind_of "$file")"
    [ "$kind" != unknown ] || fatal "$file isn't a ChessLoop backup (a .tar.gz from \"$(prog_name) backup\", or a database downloaded from Admin → Backups)."
    case "$(checksum_state "$file")" in
        ok) ok "The file matches its checksum ($(basename "$file").sha256)." ;;
        bad) fatal "The file is damaged: it doesn't match its checksum ($file.sha256). Copy it again from where you keep your backups." ;;
        none) [ "$kind" = archive ] && info "There is no checksum file next to it; checking its contents instead." ;;
    esac
    info "Checking the backup…"
    stage_restore "$file" "$kind" || fatal "This backup can't be used: $RESTORE_ERROR. Nothing was changed."
    expected="$RESTORE_COUNTS"
    ok "The backup is complete and undamaged${RESTORE_CREATED:+ (made $RESTORE_CREATED)}."
    note "It holds $(counts_words "$expected")."
    current="$(current_counts || true)"
    [ -n "$current" ] && note "ChessLoop has $(counts_words "$current") now. These are replaced."
    note "First, a safety backup of the current data is saved in $BACKUP_DIR."
    if [ "$NONINTERACTIVE" != 1 ] && ! ask_yn "Replace ChessLoop's data with this backup?" N; then
        discard_staged_restore
        cancel "Stopped. Nothing was changed."
    fi
    WORK_STARTED=1
    if [ -n "$current" ]; then
        safety="$BACKUP_DIR/$(backup_file_name before-restore)"
        info "Saving a safety backup of the current data…"
        if make_backup "$safety" 0; then
            ok "Safety backup: $safety"
        elif [ "${CHESSLOOP_SKIP_BACKUP:-0}" = 1 ]; then
            warn "No safety backup ($BACKUP_ERROR); continuing because of --no-backup."; safety=""
        else
            discard_staged_restore
            fatal "Couldn't save a safety backup of the current data ($BACKUP_ERROR), so nothing was changed. To restore without one, add --no-backup."
        fi
    fi
    step "Restoring"
    if ! swap_in_staged_data; then
        err "Putting the backup's data in place failed."
        [ -n "$safety" ] && note "The data from before is in $safety."
        start_chessloop "Starting ChessLoop again" || true
        FATAL_SHOWN=1; exit 1
    fi
    if ! start_chessloop "Starting ChessLoop"; then
        show_backend_messages
        [ -n "$safety" ] && note "To go back to the data from before: $(prog_name) restore $safety"
        FATAL_SHOWN=1; exit 1
    fi
    check_counts "$expected" || { [ -n "$safety" ] && note "The data from before is in $safety."; FATAL_SHOWN=1; exit 1; }
    blank
    ok "${BOLD}Restored.${RST} ChessLoop is running with the data from the backup."
    note "Sign in with an account from the backup. If the backup came from another"
    note "computer, everyone has to sign in again (each install has its own secret key)."
    note "The settings on this computer ($SUBDIR/.env) were not changed."
    if [ "$RESTORE_HAS_SETTINGS" = 1 ]; then
        note "The backup also holds the old settings file. To read it:  tar -xzOf $file settings.env"
    fi
    [ -n "$safety" ] && note "The data from before the restore: $safety"
    open_addresses
}

# ═══════════════════════════════════════════════════════════════════════════
#  TIDYING UP AFTER OLDER VERSIONS (Update and Uninstall)
# ═══════════════════════════════════════════════════════════════════════════
# F-012, ADR-0026: the unit written before 2026-10 crash-loops and isn't needed:
# Docker starts at boot and brings ChessLoop back (restart: always). It is
# disabled and deleted without "systemctl stop": its ExecStop would run
# "docker compose down".
remove_old_unit() {
    [ -f "$OLD_UNIT_PATH" ] && is_old_unit "$OLD_UNIT_PATH" || return 0
    setup_root "to remove the old autostart service"
    "${AS_ROOT[@]}" systemctl disable chessloop.service >> "${LOG_FILE:-/dev/null}" 2>&1 || true
    "${AS_ROOT[@]}" rm -f "$OLD_UNIT_PATH"
    "${AS_ROOT[@]}" systemctl daemon-reload >> "${LOG_FILE:-/dev/null}" 2>&1 || true
    "${AS_ROOT[@]}" systemctl reset-failed chessloop.service >/dev/null 2>&1 || true
    ok "Removed the old autostart service (chessloop.service). It never worked, and"
    note "isn't needed: Docker starts at boot and starts ChessLoop again by itself."
}

# Docker must start at boot for ChessLoop to come back after a restart.
ensure_docker_at_boot() {
    [ "$DOCKER_KIND" = engine ] && [ "$(cat /proc/1/comm 2>/dev/null)" = systemd ] || return 0
    [ "$(systemctl is-enabled docker.service 2>/dev/null || true)" = enabled ] && return 0
    setup_root "to start Docker at boot"
    run "Turning on Docker's start at boot (ChessLoop then starts by itself)" \
        "${AS_ROOT[@]}" systemctl enable docker.service || warn "Couldn't turn it on: ChessLoop may not start after a restart."
}

backend_image() {
    "${DOCKER[@]}" image inspect chessloop-backend >/dev/null 2>&1 && echo chessloop-backend
    return 0
}

# volume_state NAME: empty, data or unknown.
volume_state() {
    local v="$1" img out mp
    img="$(backend_image)"
    if [ -n "$img" ] && out="$("${DOCKER[@]}" run --rm --network none --user 0 -v "$v:/v:ro" "$img" \
            find /v -mindepth 1 -maxdepth 2 2>/dev/null)"; then
        if [ -z "$out" ]; then echo empty; else echo data; fi
        return 0
    fi
    if [ "$DOCKER_KIND" = engine ]; then
        mp="$("${DOCKER[@]}" volume inspect -f '{{.Mountpoint}}' "$v" 2>/dev/null || true)"
        setup_root "to look inside a Docker volume"
        if [ -n "$mp" ] && out="$("${AS_ROOT[@]}" find "$mp" -mindepth 1 -maxdepth 2 2>/dev/null)"; then
            if [ -z "$out" ]; then echo empty; else echo data; fi
            return 0
        fi
    fi
    echo unknown
}

stray_volume_exists() { "${DOCKER[@]}" volume ls -q 2>/dev/null | volume_listed "$STRAY_VOLUME"; }

# F-011, ADR-0009: older Update and README commands created an extra volume
# "chessloop-data" next to the real one. Empty: offered for removal. With
# files in it: never deleted or merged, only explained.
handle_stray_volume() {
    stray_volume_exists || return 0
    case "$(volume_state "$STRAY_VOLUME")" in
        empty)
            info "There is an extra, empty Docker volume \"$STRAY_VOLUME\", left by an older"
            note "version. ChessLoop's data is in \"$VOLUME_NAME\"; the extra one never held data."
            if [ "$NONINTERACTIVE" = 1 ] || ask_yn "Remove the empty volume \"$STRAY_VOLUME\"?" Y; then
                if "${DOCKER[@]}" volume rm "$STRAY_VOLUME" >> "${LOG_FILE:-/dev/null}" 2>&1; then
                    ok "Removed the empty volume $STRAY_VOLUME."
                else
                    warn "Couldn't remove it (a container may use it): sudo docker volume rm $STRAY_VOLUME"
                fi
            fi
            ;;
        data)
            warn "There is an extra Docker volume \"$STRAY_VOLUME\", and it has files in it."
            note "ChessLoop doesn't use it: ChessLoop's data is in \"$VOLUME_NAME\". Older README"
            note "steps restored backups into \"$STRAY_VOLUME\", so it may hold data you want."
            note "It is left exactly as it is. To see what is in it:"
            note "  sudo docker run --rm -v $STRAY_VOLUME:/v:ro $(backend_image || true) ls -laR /v"
            note "Not sure what to do? Ask in an issue: $GITHUB_URL/issues"
            ;;
        *)
            warn "There is an extra Docker volume \"$STRAY_VOLUME\" that ChessLoop doesn't use. It was left alone."
            ;;
    esac
}

# Older updates left backup-pre-update-*.tar.gz in the install folder; they
# hold nothing (F-011), so empty ones are deleted.
remove_empty_old_backups() {
    local f n=0
    for f in "$INSTALL_DIR"/backup-pre-update-*.tar.gz; do
        [ -f "$f" ] || continue
        [ "$(stat -c %s "$f")" -lt 4096 ] || continue
        [ -z "$(tar -tzf "$f" 2>/dev/null | grep -vx '\./' || true)" ] || continue
        as_owner rm -f "$f" 2>/dev/null && n=$((n + 1))
    done
    [ "$n" -eq 0 ] || info "Deleted $n empty backup-pre-update-….tar.gz file(s) that older updates left in $INSTALL_DIR."
}

# The "chessloop" command: a link to this install's deploy.sh (ADR-0027).
install_command_link() {
    local target="$INSTALL_DIR/deploy.sh" cur
    [ -f "$target" ] || return 0
    cur="$(readlink "$COMMAND_LINK" 2>/dev/null || true)"
    [ "$cur" = "$target" ] && return 0
    if [ -e "$COMMAND_LINK" ] && [ -z "$cur" ]; then
        warn "$COMMAND_LINK already exists and isn't ChessLoop's, so the chessloop command wasn't added."
        return 0
    fi
    setup_root "to add the chessloop command"
    if "${AS_ROOT[@]}" ln -sfn "$target" "$COMMAND_LINK" 2>> "${LOG_FILE:-/dev/null}"; then
        ok "Added the command ${BOLD}chessloop${RST} (for example: chessloop status)"
    else
        warn "Couldn't add the chessloop command; use bash $target instead."
    fi
}

# legacy_admin [--delete|--lock]: seeds/legacy_admin.py in the running backend.
legacy_admin() { dc exec -T backend python seeds/legacy_admin.py "$@" 2>&1; }

# starter_lines_added OUTPUT: the number in "Added N lines to the starter libraries."
# (seeds/seed_libraries.py), or 0.
starter_lines_added() { sed -n 's/^Added \([0-9][0-9]*\) lines to the starter libraries\.$/\1/p' <<<"$1" | tail -n 1 | grep . || echo 0; }

# After an update: a new version may ship more lines for the starter libraries.
# Only touches an install that has them (the script does nothing otherwise).
top_up_starter_content() {
    local out n
    if ! out="$(dc exec -T backend python seeds/seed_libraries.py --top-up-only 2>&1)"; then
        _log "seed_libraries.py --top-up-only: $out"
        warn "Couldn't add the new starter lines (your data is fine). To try again later: $(prog_name) update"
        return 0
    fi
    _log "$out"
    n="$(starter_lines_added "$out")"
    [ "$n" -gt 0 ] && ok "Added $n lines to the starter libraries."
    return 0
}

# After an update: the old default admin (Phase 06 notes), an install without
# any admin (F-026), and email verification left on without email.
check_accounts() {
    local out found libs others
    out="$(legacy_admin)" || { _log "legacy_admin.py: $out"; return 0; }
    found="$(sed -n 's/^default_admin=//p' <<<"$out")"
    libs="$(sed -n 's/^libraries=//p' <<<"$out")"
    others="$(sed -n 's/^other_admins=//p' <<<"$out")"
    if [ "$found" = 1 ]; then
        warn "This install still has the old default account admin@example.com with the"
        note "password \"admin\", from versions before 2026-10. It can't sign in, but its"
        note "password is publicly known, so it shouldn't stay an admin account."
        if [ "${libs:-0}" = 0 ]; then
            if [ "$NONINTERACTIVE" = 1 ] || ask_yn "Remove this unused account?" Y; then
                if out="$(legacy_admin --delete)"; then ok "Removed the old account admin@example.com."
                else warn "Couldn't remove it: $(tail -n 1 <<<"$out")"; fi
            fi
        else
            note "Libraries it owns: $libs."
            if [ "$NONINTERACTIVE" = 1 ] || ask_yn "Lock it (a random password nobody knows; its libraries stay)?" Y; then
                if out="$(legacy_admin --lock)"; then ok "Locked the old account admin@example.com."
                else warn "Couldn't lock it: $(tail -n 1 <<<"$out")"; fi
            fi
        fi
    fi
    if [ "${others:-1}" = 0 ]; then
        warn "This install has no admin account that anyone can sign in with."
        offer_admin_account
    fi
    note_verification_without_email
}

offer_admin_account() {
    if [ "$NONINTERACTIVE" = 1 ]; then
        if [ -z "${CHESSLOOP_ADMIN_EMAIL:-}" ]; then
            note "To create one: CHESSLOOP_ADMIN_EMAIL=you@example.com $(prog_name) update --yes --force"
            return 0
        fi
    elif ! ask_yn "Create your admin account now?" Y; then
        note "You can do it later by running Update again."
        return 0
    fi
    ask_admin
    [ -f "$STATE_FILE" ] && state_set admin ""
    create_admin_account
    [ "$PASSWORD_GENERATED" = 1 ] && show_password_once
    return 0
}

# Phase 06: an admin who once opened Admin → System settings left a row that
# keeps email verification on, even when no email is set up.
note_verification_without_email() {
    [ -z "$(env_get "$SUBDIR/.env" SMTP_HOST)" ] || return 0
    local on
    on="$(dc exec -T backend python -c 'import sqlite3; c = sqlite3.connect("/data/chessloop.db"); print(int(any(r[0] for r in c.execute("select enforce_email_verification from system_settings"))))' 2>/dev/null || true)"
    [ "$on" = 1 ] || return 0
    warn "Email isn't set up, but new accounts must still confirm their email (a setting"
    note "saved in Admin → System settings). They can't, so they can't sign in. To fix it,"
    note "open Admin → System settings and choose \"Use the server setting\"."
}

# ═══════════════════════════════════════════════════════════════════════════
#  UPDATE (ADR-0028)
# ═══════════════════════════════════════════════════════════════════════════
UPDATE_FORCE="${CHESSLOOP_FORCE_REBUILD:-0}"
UPDATE_BRANCH=""
UPDATE_STASHED=0
PRE_UPDATE_BACKUP=""
PRE_UPDATE_COUNTS=""

# Shows the CHANGELOG.md lines that are new between two versions.
show_changes() {
    local lines n
    if ! git_owner cat-file -e "$1:CHANGELOG.md" 2>/dev/null; then
        git_owner cat-file -e "$2:CHANGELOG.md" 2>/dev/null \
            && note "What's new: see $INSTALL_DIR/CHANGELOG.md after the update."
        return 0
    fi
    lines="$(as_owner git -C "$INSTALL_DIR" diff --unified=0 "$1" "$2" -- CHANGELOG.md 2>/dev/null \
        | grep '^+' | grep -v '^+++' | sed 's/^+//' | grep -v '^[[:space:]]*$' || true)"
    [ -n "$lines" ] || return 0
    n="$(wc -l <<<"$lines")"
    note "What's new (from CHANGELOG.md):"
    head -n 25 <<<"$lines" | sed 's/^/        /' >&2
    _log "$lines"
    [ "$n" -le 25 ] || note "  … and more: $INSTALL_DIR/CHANGELOG.md"
}

git_owner() {
    as_owner git -c user.name=ChessLoop -c user.email=chessloop@localhost -C "$INSTALL_DIR" "$@"
}

# Puts changes to ChessLoop's own files aside (git stash) instead of failing.
stash_local_changes() {
    local changes
    changes="$(git_owner status --porcelain --untracked-files=no 2>/dev/null || true)"
    [ -n "$changes" ] || return 0
    warn "Some of ChessLoop's files were changed on this computer:"
    printf '%s\n' "$changes" | sed 's/^/        /' >&2
    _log "$changes"
    run "Putting those changes aside (git stash)" git_owner stash push --quiet -m "chessloop update $(date '+%Y-%m-%d %H:%M')" \
        || fatal "Couldn't put the changed files aside, so nothing was updated. See the log."
    UPDATE_STASHED=1
    note "They are kept: to see them, cd $INSTALL_DIR && git stash show -p"
    note "Settings belong in $SUBDIR/.env, which updates never change."
}

# checkout_version COMMIT: follows the branch when there is one, else detaches.
checkout_version() {
    if [ -n "$UPDATE_BRANCH" ]; then
        git_owner checkout --quiet -B "$UPDATE_BRANCH" "$1"
    else
        git_owner checkout --quiet --detach "$1"
    fi
}

# Back to the version that ran before: its code, its images and, when the new
# version may have changed the data, the data from the pre-update backup.
roll_back() {
    local old="$1" restore_data="$2" why="$3"
    err "The update didn't work: $why."
    step "Going back to the previous version"
    git_owner checkout --quiet --force "$old" 2>> "${LOG_FILE:-/dev/null}" || true
    [ -n "$UPDATE_BRANCH" ] && git_owner checkout --quiet -B "$UPDATE_BRANCH" "$old" 2>> "${LOG_FILE:-/dev/null}"
    if [ "$UPDATE_STASHED" = 1 ]; then
        git_owner stash pop --quiet >> "${LOG_FILE:-/dev/null}" 2>&1 || note "Your own changes are still in git's stash (git stash list)."
    fi
    ok "Files: back to $(describe_commit "$old")"
    if ! run "Rebuilding the previous version" dc build; then
        err "The previous version didn't build either."
        note "Your data is safe in the volume $VOLUME_NAME${PRE_UPDATE_BACKUP:+ and in $PRE_UPDATE_BACKUP}."
        note "When the problem is fixed (see the log), run: $(prog_name) update"
        FATAL_SHOWN=1; exit 1
    fi
    local data_ok=1
    if [ "$restore_data" = 1 ] && [ -n "$PRE_UPDATE_BACKUP" ]; then
        info "Putting back the data from before the update…"
        # Stopped first: a backend that keeps crashing can't be used to stage the data.
        run "Stopping the new version" dc stop || true
        if stage_restore "$PRE_UPDATE_BACKUP" archive && swap_in_staged_data; then
            ok "Data: back to the backup from before the update."
        else
            data_ok=0
            err "Couldn't put back the data from before the update (${RESTORE_ERROR:-see the log})."
        fi
    fi
    if start_chessloop "Starting the previous version"; then
        if [ "$restore_data" = 1 ] && [ -n "$PRE_UPDATE_COUNTS" ] && [ "$data_ok" = 1 ]; then
            check_counts "$PRE_UPDATE_COUNTS" || data_ok=0
        fi
        blank
        if [ "$data_ok" = 1 ]; then
            ok "ChessLoop is running the previous version again, $(describe_commit "$old"), with your data."
        else
            warn "ChessLoop is running the previous version again, $(describe_commit "$old"), but its data may not be"
            warn "what you had before the update. Your data from before the update is safe in the backup:"
            note "  $(prog_name) restore $PRE_UPDATE_BACKUP"
        fi
    else
        err "The previous version didn't start either."
        show_backend_messages
        [ -n "$PRE_UPDATE_BACKUP" ] && note "Your data from before the update: $PRE_UPDATE_BACKUP"
    fi
    note "Why the update failed: $why. The details are in the log."
    note "You can try again later: $(prog_name) update"
    FATAL_SHOWN=1; exit 1
}

# WSL (F-036, ADR-0017): installs made before the keep-alive existed stop
# whenever Ubuntu's window closes. Update offers what Install does now.
offer_wsl_keepalive() {
    local profile appdata cmd
    is_wsl && [ "$DOCKER_KIND" = engine ] || return 0
    IS_WSL=1; WSL_DISTRO="${WSL_DISTRO_NAME:-}"
    profile="$(win_path_of USERPROFILE)"
    [ -n "$profile" ] && [ -d "$profile" ] || return 0
    appdata="$(win_path_of APPDATA)"
    cmd="${appdata:-$profile/AppData/Roaming}/Microsoft/Windows/Start Menu/Programs/Startup/ChessLoop.cmd"
    if [ -f "$cmd" ] && [ -f "$profile/.wslconfig" ] && ! has_nul "$profile/.wslconfig" \
        && [ "$(ini_get general instanceIdleTimeout < "$profile/.wslconfig")" = "-1" ]; then
        return 0
    fi
    ask_wsl_keepalive
    WSL_MIRRORED=0
    setup_wsl_windows_side
}

# The checks done on every Update, also when there is nothing new.
tidy_up() {
    remove_old_unit
    ensure_docker_at_boot
    handle_stray_volume
    remove_empty_old_backups
    install_command_link
    offer_wsl_keepalive
}

record_update() {
    state_set ref "$1"
    [ -n "$(state_get config)" ] || state_set config "done"
    [ -n "$(state_get complete)" ] || state_set complete "$(date -Is)"
}

ensure_running() {
    if [ "$(dc ps --status running -q 2>/dev/null | wc -l)" -ge 3 ] && http_ok; then
        ok "ChessLoop is running."
        return 0
    fi
    info "ChessLoop isn't running; starting it."
    start_chessloop "Starting ChessLoop" || { show_backend_messages; fatal "ChessLoop didn't start. See the log."; }
}

do_update() {
    ACTION=update
    [ -n "$LOG_FILE" ] || setup_log update
    header "Update ChessLoop"
    require_install
    docker_access
    setup_backup_dir
    local ref old new old_desc new_desc newer=1
    UPDATE_BRANCH="$(git_owner symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
    local current_tag="" latest_tag=""
    if [ -z "${CHESSLOOP_REF:-}" ] && [ -z "$UPDATE_BRANCH" ]; then
        current_tag="$(git_owner describe --tags --exact-match HEAD 2>/dev/null | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | head -n 1 || true)"
        if [ -n "$current_tag" ]; then latest_release_tag; latest_tag="$LATEST_TAG"; fi
    fi
    ref="$(update_ref_for "${CHESSLOOP_REF:-}" "$UPDATE_BRANCH" "$current_tag" "$latest_tag")"
    [ -n "${CHESSLOOP_REF:-}" ] && UPDATE_BRANCH=""   # set again below if the ref is a branch
    old="$(git_owner rev-parse HEAD)"
    old_desc="$(describe_commit "$old")"
    ok "Installed version: $old_desc"
    run "Checking for a new version ($ref)" git_owner fetch --quiet --tags origin "$ref" \
        || fatal "Couldn't get '$ref' from $(git_owner remote get-url origin 2>/dev/null || echo "the ChessLoop repository"). Check the internet connection, and that this branch or tag exists."
    new="$(git_owner rev-parse 'FETCH_HEAD^{commit}')"
    git_owner rev-parse -q --verify "refs/remotes/origin/$ref" >/dev/null 2>&1 && UPDATE_BRANCH="$ref"
    tidy_up
    if [ "$new" = "$old" ] || git_owner merge-base --is-ancestor "$new" "$old" 2>/dev/null; then
        newer=0
        ok "ChessLoop is up to date: $old_desc."
        if [ "$UPDATE_FORCE" != 1 ] && { [ "$NONINTERACTIVE" = 1 ] || ! ask_yn "Rebuild it anyway? (builds the same version again; only needed if something is broken)" N; }; then
            ensure_running
            # An install updated by an older script has the new code but never ran its top-up.
            top_up_starter_content
            check_accounts
            record_update "$ref"
            return 0
        fi
        info "Rebuilding the installed version."
    else
        new_desc="$(describe_commit "$new")"
        info "New version: $new_desc"
        show_changes "$old" "$new"
    fi
    if [ "$NONINTERACTIVE" != 1 ]; then
        note "First, a backup of your data is saved in $BACKUP_DIR. If the new version"
        note "doesn't start, the installer goes back to this version and this data."
        ask_yn "Update now?" Y || cancel "Stopped. Nothing was changed."
    fi
    WORK_STARTED=1

    step "Backing up before the update"
    PRE_UPDATE_BACKUP="$BACKUP_DIR/$(backup_file_name pre-update)"
    if make_backup "$PRE_UPDATE_BACKUP" 0; then
        PRE_UPDATE_COUNTS="$BACKUP_COUNTS"
        ok "Backup: $PRE_UPDATE_BACKUP ($(human_size "$(stat -c %s "$PRE_UPDATE_BACKUP")"), $(counts_words "$BACKUP_COUNTS"))"
    elif [[ "$BACKUP_ERROR" == "no database yet"* ]]; then
        PRE_UPDATE_BACKUP=""
        info "There is no data yet, so there is nothing to back up."
    elif [ "${CHESSLOOP_SKIP_BACKUP:-0}" = 1 ]; then
        PRE_UPDATE_BACKUP=""
        warn "The backup failed ($BACKUP_ERROR); continuing without one because of --no-backup."
    else
        if grep -qiE '429 Too Many Requests|toomanyrequests' <<<"$BACKUP_ERROR"; then
            err "The backup before the update couldn't start: Docker Hub refused a download. Nothing was changed."
            explain_rate_limit
            FATAL_SHOWN=1; exit 1
        fi
        fatal "The backup before the update failed: $BACKUP_ERROR. Nothing was changed. (To update without a backup, add --no-backup.)"
    fi

    step "Updating"
    if [ "$newer" = 1 ]; then
        stash_local_changes
        if ! run "Switching to the new version" checkout_version "$new"; then
            [ "$UPDATE_STASHED" = 1 ] && git_owner stash pop --quiet >> "${LOG_FILE:-/dev/null}" 2>&1
            fatal "Couldn't switch to the new version (see the log). Nothing else was changed."
        fi
        state_set previous_commit "$old"
    fi
    if ! run "Building the new version (usually 1 to 5 minutes)" dc build; then
        case "$(build_failure_reason)" in
            ratelimit) roll_back "$old" 0 "Docker Hub is limiting downloads from your internet address for now (wait about an hour, then run the update again)" ;;
            network) roll_back "$old" 0 "downloading during the build failed (check the internet connection)" ;;
            disk) roll_back "$old" 0 "the disk is full (free up at least 3 GB)" ;;
            memory) roll_back "$old" 0 "the build ran out of memory" ;;
            *) roll_back "$old" 0 "the new version didn't build" ;;
        esac
    fi
    if ! start_chessloop "Starting the new version"; then
        show_backend_messages
        roll_back "$old" 1 "the new version didn't start"
    fi
    if [ "$old" = "$new" ]; then
        ok "Rebuilt $old_desc (it was already the newest version)."
    else
        ok "Updated: $old_desc → $(describe_commit "$new")"
    fi
    top_up_starter_content
    check_accounts
    record_update "$ref"
    print_update_summary
}

print_update_summary() {
    blank
    _say "  ${G}${BOLD}✓  ChessLoop is updated and running.${RST}"
    note "Open it: http://localhost:$PORT"
    if [ -n "$PRE_UPDATE_BACKUP" ]; then
        note "Your data from before the update: $PRE_UPDATE_BACKUP"
        note "If something isn't right:  $(prog_name) restore $PRE_UPDATE_BACKUP"
    fi
    note "Backups are in $BACKUP_DIR ($(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)); delete old ones you no longer need."
    [ -n "$LOG_FILE" ] && note "Update log: $LOG_FILE"
    blank
}

# ═══════════════════════════════════════════════════════════════════════════
#  UNINSTALL (ADR-0028)
# ═══════════════════════════════════════════════════════════════════════════
INV_CONTAINERS=""
INV_IMAGES=()
INV_IMAGES_BYTES=0
INV_VOLUME=0
INV_VOLUME_BYTES=""
INV_STRAY=""          # "" | empty | data | unknown
INV_DIR_SIZE=""
INV_UNIT=0
INV_LINK=0
INV_WSL_CMD=""        # Startup\ChessLoop.cmd as a Linux path, if it exists
INV_WSLCONFIG=""      # .wslconfig as a Linux path, if it has our values
INV_WSL_IDLE=0
INV_WSL_MIRRORED=0
INV_OLD_IMAGES=()     # general images versions before 2026-10 pulled (kept; listed with the command)

# What ChessLoop has on this computer.
collect_inventory() {
    local img b mp profile appdata f
    INV_CONTAINERS="$("${DOCKER[@]}" ps -a --filter label=com.docker.compose.project=chessloop --format '{{.Names}}' 2>/dev/null | sort | paste -sd ' ' - || true)"
    INV_IMAGES=(); INV_IMAGES_BYTES=0
    # Images built for this stack, and older builds of them that updates left behind
    while IFS= read -r img; do
        [ -n "$img" ] || continue
        INV_IMAGES+=("$img")
        b="$("${DOCKER[@]}" image inspect -f '{{.Size}}' "$img" 2>/dev/null || echo 0)"
        INV_IMAGES_BYTES=$((INV_IMAGES_BYTES + b))
    done < <( { "${DOCKER[@]}" images -q --filter label=com.docker.compose.project=chessloop 2>/dev/null
                for img in chessloop-backend chessloop-frontend chessloop-nginx; do
                    "${DOCKER[@]}" image inspect -f '{{.Id}}' "$img" 2>/dev/null
                done; } | sed 's/^sha256://' | cut -c1-12 | sort -u)
    INV_VOLUME=0; INV_VOLUME_BYTES=""
    if "${DOCKER[@]}" volume ls -q 2>/dev/null | volume_listed "$VOLUME_NAME"; then
        INV_VOLUME=1
        if [ "$DOCKER_KIND" = engine ]; then
            setup_root "to see how much space ChessLoop's data uses"
            mp="$("${DOCKER[@]}" volume inspect -f '{{.Mountpoint}}' "$VOLUME_NAME" 2>/dev/null || true)"
            [ -n "$mp" ] && INV_VOLUME_BYTES="$("${AS_ROOT[@]}" du -sb "$mp" 2>/dev/null | cut -f1 || true)"
        fi
    fi
    INV_STRAY=""
    stray_volume_exists && INV_STRAY="$(volume_state "$STRAY_VOLUME")"
    INV_OLD_IMAGES=()
    # ace261a ran stock nginx:1.27-alpine; its Update and README backups pulled alpine
    for img in nginx:1.27-alpine alpine:latest; do
        "${DOCKER[@]}" image inspect "$img" >/dev/null 2>&1 && INV_OLD_IMAGES+=("$img")
    done
    INV_DIR_SIZE="$(du -sh "$INSTALL_DIR" 2>/dev/null | cut -f1 || true)"
    INV_UNIT=0; [ -f "$OLD_UNIT_PATH" ] && is_old_unit "$OLD_UNIT_PATH" && INV_UNIT=1
    INV_LINK=0; [ "$(readlink "$COMMAND_LINK" 2>/dev/null)" = "$INSTALL_DIR/deploy.sh" ] && INV_LINK=1
    INV_WSL_CMD=""; INV_WSLCONFIG=""; INV_WSL_IDLE=0; INV_WSL_MIRRORED=0
    if is_wsl; then
        profile="$(win_path_of USERPROFILE)"; appdata="$(win_path_of APPDATA)"
        if [ -n "$profile" ] && [ -d "$profile" ]; then
            f="${appdata:-$profile/AppData/Roaming}/Microsoft/Windows/Start Menu/Programs/Startup/ChessLoop.cmd"
            [ -f "$f" ] && INV_WSL_CMD="$f"
            f="$profile/.wslconfig"
            if [ -f "$f" ] && ! has_nul "$f"; then
                [ "$(ini_get general instanceIdleTimeout < "$f")" = "-1" ] && INV_WSL_IDLE=1
                [ "$(ini_get wsl2 networkingMode < "$f")" = mirrored ] && INV_WSL_MIRRORED=1
                [ "$INV_WSL_IDLE" = 1 ] || [ "$INV_WSL_MIRRORED" = 1 ] && INV_WSLCONFIG="$f"
            fi
        fi
    fi
    _log "inventory: containers=[$INV_CONTAINERS] images=[${INV_IMAGES[*]}] volume=$INV_VOLUME stray=$INV_STRAY unit=$INV_UNIT link=$INV_LINK wsl_cmd=${INV_WSL_CMD:+yes} wsl_idle=$INV_WSL_IDLE wsl_mirrored=$INV_WSL_MIRRORED"
}

volume_words() {
    if [ -n "$INV_VOLUME_BYTES" ]; then human_size "$INV_VOLUME_BYTES"; else echo "size unknown"; fi
}

choose_uninstall_level() {
    local choice
    if [ "$NONINTERACTIVE" = 1 ]; then
        UNINSTALL_LEVEL="${CHESSLOOP_UNINSTALL_LEVEL:-}"
        case "$UNINSTALL_LEVEL" in
            1|2) ;;
            3) [ "${CHESSLOOP_ALLOW_DATA_DELETE:-0}" = 1 ] || fatal "Level 3 deletes all ChessLoop data. To allow that in --yes mode, set CHESSLOOP_ALLOW_DATA_DELETE=1." ;;
            *) fatal "Choose what to remove with --level 1, 2 or 3 (see: $(prog_name) --help)." ;;
        esac
        return 0
    fi
    blank
    _say "  ${BOLD}How much do you want to remove?${RST}"
    blank
    _say "    ${BOLD}1)${RST} ${Y}Stop ChessLoop${RST} and remove its containers"
    _say "       ${DIM}Keeps your data, settings, files and Docker images. Start it again any time.${RST}"
    _say "    ${BOLD}2)${RST} ${Y}Also remove ChessLoop's Docker images${RST} ($(human_size "$INV_IMAGES_BYTES"))"
    _say "       ${DIM}Keeps your data, settings and files. Starting again rebuilds the images.${RST}"
    _say "    ${BOLD}3)${RST} ${R}Remove ChessLoop completely${RST}"
    _say "       ${DIM}Deletes all accounts, libraries and progress, the settings and $INSTALL_DIR.${RST}"
    _say "       ${DIM}You can save a final backup first.${RST}"
    _say "    ${BOLD}4)${RST} Cancel"
    blank
    while true; do
        ask choice "Remove [1-4]" 4
        case "$choice" in
            1|2|3) UNINSTALL_LEVEL="$choice"; return 0 ;;
            4) cancel "Cancelled. Nothing was changed." ;;
            *) warn "Please type a number from 1 to 4." ;;
        esac
    done
}

show_uninstall_plan() {
    local level="$1"
    header "What level $level does"
    _say "  ${BOLD}Removed:${RST}"
    note "• Containers: ${INV_CONTAINERS:-none}"
    if [ "$level" -ge 2 ]; then
        note "• ChessLoop's Docker images: ${#INV_IMAGES[@]} ($(human_size "$INV_IMAGES_BYTES"))"
    fi
    if [ "$level" -ge 3 ]; then
        [ "$INV_VOLUME" = 1 ] && note "• ${R}All ChessLoop data${RST}: Docker volume $VOLUME_NAME ($(volume_words)): accounts, libraries, progress, Admin-panel backups"
        [ "$INV_STRAY" = empty ] && note "• The extra, empty Docker volume $STRAY_VOLUME"
        note "• The folder $INSTALL_DIR (${INV_DIR_SIZE:-?}): ChessLoop's files and the settings file .env"
        [ "$INV_LINK" = 1 ] && note "• The command chessloop ($COMMAND_LINK)"
    fi
    [ "$INV_UNIT" = 1 ] && note "• The old autostart service chessloop.service (it never worked; F-012)"
    _say "  ${BOLD}Kept:${RST}"
    if [ "$level" -lt 3 ]; then
        [ "$level" -lt 2 ] && note "• ChessLoop's Docker images"
        note "• Your data (Docker volume $VOLUME_NAME), the settings and $INSTALL_DIR"
    fi
    [ "$INV_STRAY" = data ] && note "• The extra Docker volume $STRAY_VOLUME: it has files in it, so it is never deleted here"
    [ "${#INV_OLD_IMAGES[@]}" -gt 0 ] && note "• General Docker images older versions downloaded: ${INV_OLD_IMAGES[*]} (other programs may use them)"
    [ "$INV_STRAY" = unknown ] && note "• The extra Docker volume $STRAY_VOLUME (couldn't look inside it)"
    note "• Your backups in $BACKUP_DIR and the logs (~/chessloop-*.log)"
    note "• Docker itself (other programs may use it)"
    if [ "$level" -ge 3 ] && { [ -n "$INV_WSL_CMD" ] || [ -n "$INV_WSLCONFIG" ]; }; then
        note "• The Windows settings that keep Ubuntu running: you are asked about them next"
    fi
}

confirm_uninstall() {
    local level="$1" typed
    if [ "$NONINTERACTIVE" = 1 ]; then return 0; fi
    blank
    if [ "$level" -lt 3 ]; then
        ask_yn "Remove these?" N || cancel "Cancelled. Nothing was changed."
        return 0
    fi
    if ask_yn "Save a final backup of all data first? (recommended)" Y; then FINAL_BACKUP=1; else FINAL_BACKUP=0; fi
    warn "${BOLD}This deletes all ChessLoop accounts, libraries and progress.${RST}"
    ask typed "Type DELETE to remove ChessLoop completely" ""
    [ "$typed" = DELETE ] || cancel "Cancelled. Nothing was changed."
}

FINAL_BACKUP="${CHESSLOOP_FINAL_BACKUP:-1}"

# Undo the installer's WSL keep-alive (ADR-0017): Startup\ChessLoop.cmd and the
# values it put in .wslconfig, only while they still have those values.
remove_wsl_keepalive() {
    local f="$INV_WSLCONFIG" tmp mirrored=0
    [ -n "$INV_WSL_CMD" ] || [ -n "$f" ] || return 0
    blank
    info "The installer set up Windows to keep Ubuntu running (so ChessLoop stays on):"
    [ -n "$INV_WSL_CMD" ] && note "• Startup\\ChessLoop.cmd starts Ubuntu when you sign in to Windows"
    [ "$INV_WSL_IDLE" = 1 ] && note "• instanceIdleTimeout=-1 in .wslconfig keeps it running when its window is closed"
    if [ "$NONINTERACTIVE" != 1 ] && ! ask_yn "Undo these Windows settings?" Y; then
        note "Kept. Ubuntu keeps running in the background; it uses some memory."
        return 0
    fi
    if [ "$INV_WSL_MIRRORED" = 1 ]; then
        if [ "$NONINTERACTIVE" = 1 ]; then
            [ "$(state_get wsl_mirrored)" = "done" ] && mirrored=1
        else
            note "WSL's mirrored networking is on too (lets phones reach Ubuntu). Other programs may need it."
            ask_yn "Turn mirrored networking off as well?" N && mirrored=1
        fi
    fi
    if [ -n "$INV_WSL_CMD" ]; then
        rm -f "$INV_WSL_CMD" && ok "Removed Startup\\ChessLoop.cmd"
    fi
    if [ -n "$f" ]; then
        tmp="$(mktemp)"
        ini_del general instanceIdleTimeout -1 < "$f" > "$tmp"
        if [ "$mirrored" = 1 ]; then ini_del wsl2 networkingMode mirrored < "$tmp" > "$tmp.2" && mv "$tmp.2" "$tmp"; fi
        if ! cmp -s "$tmp" "$f"; then
            cp "$f" "$f.chessloop-backup-$(date +%Y%m%d-%H%M%S)"
            cat "$tmp" > "$f"
            ok "Removed ChessLoop's values from .wslconfig (a copy of the old file is next to it)."
        fi
        rm -f "$tmp"
    fi
    note "Windows applies this after WSL restarts (wsl --shutdown in PowerShell, or a restart)."
}

do_uninstall() {
    ACTION=uninstall
    [ -n "$LOG_FILE" ] || setup_log uninstall
    header "Uninstall ChessLoop"
    require_install
    docker_access
    setup_backup_dir
    collect_inventory
    choose_uninstall_level
    local level="$UNINSTALL_LEVEL" final="" img
    show_uninstall_plan "$level"
    confirm_uninstall "$level"
    WORK_STARTED=1

    if [ "$level" = 3 ] && [ "$FINAL_BACKUP" = 1 ] && [ "$INV_VOLUME" = 1 ]; then
        step "Final backup"
        final="$BACKUP_DIR/$(backup_file_name final)"
        if make_backup "$final" 1; then
            ok "Final backup (with the settings file): $final"
        else
            fatal "The final backup failed ($BACKUP_ERROR), so nothing was removed. To remove ChessLoop without one, set CHESSLOOP_FINAL_BACKUP=0."
        fi
    fi

    step "Removing (level $level)"
    if [ -n "$INV_CONTAINERS" ]; then
        if ! run "Stopping ChessLoop and removing its containers" dc down --remove-orphans; then
            # e.g. .env is gone, so Compose can't read the file: remove them by name
            # shellcheck disable=SC2086  # a list of names
            run "Removing the containers by name" "${DOCKER[@]}" rm -f $INV_CONTAINERS || true
            "${DOCKER[@]}" network rm chessloop_default >/dev/null 2>&1 || true
        fi
    fi
    remove_old_unit
    if [ "$level" -ge 2 ] && [ "${#INV_IMAGES[@]}" -gt 0 ]; then
        for img in chessloop-backend chessloop-frontend chessloop-nginx; do
            "${DOCKER[@]}" image rm "$img" >> "${LOG_FILE:-/dev/null}" 2>&1 || true
        done
        for img in "${INV_IMAGES[@]}"; do
            "${DOCKER[@]}" image rm "$img" >> "${LOG_FILE:-/dev/null}" 2>&1 || true
        done
        ok "Removed ChessLoop's Docker images ($(human_size "$INV_IMAGES_BYTES"))."
    fi
    if [ "$level" = 3 ]; then
        if [ "$INV_VOLUME" = 1 ]; then
            "${DOCKER[@]}" volume rm "$VOLUME_NAME" >> "${LOG_FILE:-/dev/null}" 2>&1 \
                || fatal "Couldn't delete the data volume $VOLUME_NAME (see the log). The files in $INSTALL_DIR were kept."
            ok "Deleted the data volume $VOLUME_NAME."
        fi
        if [ "$INV_STRAY" = empty ]; then
            "${DOCKER[@]}" volume rm "$STRAY_VOLUME" >> "${LOG_FILE:-/dev/null}" 2>&1 && ok "Deleted the empty volume $STRAY_VOLUME."
        fi
        if [ "$INV_LINK" = 1 ]; then
            setup_root "to remove the chessloop command"
            "${AS_ROOT[@]}" rm -f "$COMMAND_LINK" && ok "Removed the chessloop command."
        fi
        remove_wsl_keepalive
        safe_to_delete "$INSTALL_DIR" || fatal "Refusing to delete $INSTALL_DIR: it doesn't look like a ChessLoop install folder."
        cd / 2>/dev/null || true
        if ! rm -rf "$INSTALL_DIR" 2>> "${LOG_FILE:-/dev/null}"; then
            setup_root "to delete $INSTALL_DIR"
            "${AS_ROOT[@]}" rm -rf "$INSTALL_DIR"
        fi
        ok "Deleted $INSTALL_DIR."
    fi

    blank
    ok "${BOLD}Done (level $level).${RST}"
    case "$level" in
        1|2)
            note "Your data and settings are kept. To start ChessLoop again:  $(prog_name) start"
            [ "$level" = 2 ] && note "(That builds the images again first: a few minutes.)"
            ;;
        3)
            [ -n "$final" ] && note "Final backup: $final (it holds everything, including the settings)."
            note "To install ChessLoop again later: see $GITHUB_URL"
            ;;
    esac
    note "Docker is still installed. To remove it too (if nothing else uses it):"
    note "  sudo apt-get purge docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin"
    if [ "$level" -ge 2 ]; then
        note "Docker keeps a build cache; to free that disk space:  sudo docker builder prune"
    fi
    [ "$INV_STRAY" = data ] && note "The extra volume $STRAY_VOLUME (with files) is still there; see above."
    if [ "$level" -ge 2 ] && [ "${#INV_OLD_IMAGES[@]}" -gt 0 ]; then
        note "Older versions also downloaded ${INV_OLD_IMAGES[*]}. If nothing else uses them:"
        note "  sudo docker image rm ${INV_OLD_IMAGES[*]}"
    fi
    blank
}

# ═══════════════════════════════════════════════════════════════════════════
#  EVERYDAY COMMANDS: chessloop status | start | stop | restart | logs
# ═══════════════════════════════════════════════════════════════════════════
do_status() {
    require_install
    docker_access
    setup_backup_dir
    local latest
    note "Version:  $(describe_commit HEAD)"
    note "Address:  http://localhost:$PORT"
    blank
    # data-owner runs once at start and exits; it isn't one of the three parts.
    dc ps --all --format 'table {{.Service}}\t{{.Status}}' backend frontend nginx 2>&1 | sed 's/^/      /' >&2 || true
    blank
    if http_ok; then ok "ChessLoop answers on port $PORT."; else err "ChessLoop doesn't answer on port $PORT. Try: $(prog_name) start"; fi
    if "${DOCKER[@]}" volume ls -q 2>/dev/null | volume_listed "$VOLUME_NAME"; then
        ok "Data: Docker volume $VOLUME_NAME"
    else
        warn "The data volume $VOLUME_NAME doesn't exist yet."
    fi
    # shellcheck disable=SC2012  # file names the script chose; newest first
    latest="$(ls -1t "$BACKUP_DIR"/chessloop-*.tar.gz 2>/dev/null | head -n 1 || true)"
    if [ -n "$latest" ]; then
        note "Latest backup: $latest ($(date -r "$latest" '+%Y-%m-%d %H:%M'))"
    else
        note "No backups in $BACKUP_DIR yet. Make one:  $(prog_name) backup"
    fi
}

do_start() {
    ACTION=start
    [ -n "$LOG_FILE" ] || setup_log start
    require_install
    docker_access
    start_chessloop "Starting ChessLoop" || { show_backend_messages; fatal "ChessLoop didn't start."; }
    ok "ChessLoop is running."
    open_addresses
}

do_stop() {
    require_install
    docker_access
    run "Stopping ChessLoop" dc stop || fatal "Couldn't stop ChessLoop."
    note "Docker starts it again when this computer restarts. To start it now:  $(prog_name) start"
}

do_restart() {
    ACTION=restart
    [ -n "$LOG_FILE" ] || setup_log restart
    require_install
    docker_access
    run "Restarting ChessLoop" dc restart || fatal "Couldn't restart ChessLoop."
    start_chessloop "Checking ChessLoop" || { show_backend_messages; fatal "ChessLoop didn't come back."; }
    ok "ChessLoop is running: http://localhost:$PORT"
}

do_logs() {
    locate_install || require_install
    docker_access
    if [ "${LOGS_FOLLOW:-0}" = 1 ]; then dc logs --tail 100 -f; else dc logs --tail 100; fi
}

# ═══════════════════════════════════════════════════════════════════════════
#  MENU, OPTIONS, START
# ═══════════════════════════════════════════════════════════════════════════
print_banner() {
    [ "$NONINTERACTIVE" = 1 ] || clear 2>/dev/null || true
    echo "" >&2
    echo -e "  ${C}${BOLD}╔══════════════════════════════════════════════════════════╗${RST}" >&2
    echo -e "  ${C}${BOLD}║               ♞  ChessLoop  Installer                    ║${RST}" >&2
    echo -e "  ${C}${BOLD}╚══════════════════════════════════════════════════════════╝${RST}" >&2
}

# Containers running? Without sudo if possible, never asking for a password (F-029).
running_containers() {
    local out
    out="$(docker ps --filter 'name=chessloop' --format '{{.Names}}' 2>/dev/null)" \
        || out="$(sudo -n docker ps --filter 'name=chessloop' --format '{{.Names}}' 2>/dev/null)" \
        || { echo "?"; return 0; }
    grep -c . <<<"$out" || true
}

cancel() { info "$*"; exit 0; }

main_menu() {
    print_banner
    local running choice
    if locate_install; then
        echo -e "  ${G}${BOLD}Existing install:${RST} $INSTALL_DIR" >&2
        if command -v docker >/dev/null 2>&1; then
            running="$(running_containers)"
            case "$running" in
                "?") echo -e "  ${DIM}●${RST} container status: unknown (needs sudo)" >&2 ;;
                0) echo -e "  ${R}●${RST} containers not running" >&2 ;;
                *) echo -e "  ${G}●${RST} ${running} container(s) running" >&2 ;;
            esac
        fi
    else
        echo -e "  ${DIM}No existing install found.${RST}" >&2
    fi
    blank
    echo -e "  ${BOLD}What would you like to do?${RST}" >&2
    blank
    echo -e "    ${BOLD}1)${RST}  ${G}Install${RST}    — Set up ChessLoop on this computer" >&2
    echo -e "    ${BOLD}2)${RST}  ${C}Update${RST}     — Get the latest version (backs up your data first)" >&2
    echo -e "    ${BOLD}3)${RST}  ${C}Back up${RST}    — Save all ChessLoop data to a file" >&2
    echo -e "    ${BOLD}4)${RST}  ${C}Restore${RST}    — Put back the data from a backup file" >&2
    echo -e "    ${BOLD}5)${RST}  ${R}Uninstall${RST}  — Remove ChessLoop (choose how much)" >&2
    echo -e "    ${BOLD}6)${RST}  ${DIM}Exit${RST}" >&2
    blank
    while true; do
        ask choice "Choice [1-6]" ""
        case "$choice" in
            1) do_install; return ;;
            2) do_update; return ;;
            3) do_backup; return ;;
            4) do_restore; return ;;
            5) do_uninstall; return ;;
            6|q|Q|"") echo -e "  ${DIM}Goodbye.${RST}" >&2; exit 0 ;;
            *) warn "Please type a number from 1 to 6." ;;
        esac
    done
}

usage() {
    cat <<USAGE
ChessLoop: install, update, back up, restore and uninstall

Usage (after the install, "chessloop" works too, for example: chessloop status):
  bash deploy.sh                 menu
  bash deploy.sh install         install ChessLoop
  bash deploy.sh update          get the latest version; backs up first, goes back if it fails
  bash deploy.sh backup [FILE]   save all data to ~/chessloop-backups (or FILE)
  bash deploy.sh restore [FILE]  replace the data with a backup (a safety backup is made first)
  bash deploy.sh uninstall       remove ChessLoop; you choose how much
  bash deploy.sh status          is it running? version, address, latest backup
  bash deploy.sh start | stop | restart
  bash deploy.sh logs [-f]       the last messages (-f: keep following)
  bash deploy.sh --help          this text
  curl -fsSL https://raw.githubusercontent.com/antonizick/chessloop/main/deploy.sh | bash -s -- --yes

Options:
  --yes             no questions: settings come from the variables below
  --force           update: rebuild even when there is nothing new
  --no-backup       update, restore: continue even if the backup first fails
  --with-settings   backup: also save the settings file (.env; it holds secrets)
  --level 1|2|3     uninstall with --yes: 1 containers, 2 also images, 3 everything

Settings for install --yes (environment variables; the defaults are in brackets):
  CHESSLOOP_ADMIN_EMAIL      admin email address (required)
  CHESSLOOP_ADMIN_PASSWORD   admin password, 12+ characters [generated and shown once]
  CHESSLOOP_ADMIN_USERNAME   admin display name [admin]
  CHESSLOOP_ACCESS           local (this computer), lan (home network) or domain
                             [local]
  CHESSLOOP_PORT             web port [8090]
  CHESSLOOP_DOMAIN           domain name, for CHESSLOOP_ACCESS=domain
  CHESSLOOP_SEED             1 = load the starter opening libraries, 0 = don't [1]
  CHESSLOOP_SMTP_HOST        SMTP server; empty = no email [empty]
  CHESSLOOP_SMTP_PORT, CHESSLOOP_SMTP_USER, CHESSLOOP_SMTP_PASSWORD,
  CHESSLOOP_SMTP_FROM, CHESSLOOP_SMTP_USE_TLS (true/false) [587, -, -, -, true]
  CHESSLOOP_WSL_KEEPALIVE    WSL only: 1 = keep Ubuntu running and start it with Windows [1]
  CHESSLOOP_WSL_MIRRORED     WSL only, with lan: 1 = turn on mirrored networking [0]
  CHESSLOOP_INSTALL_DIR      install folder [$DEFAULT_INSTALL_DIR]
  CHESSLOOP_REPO             git repository to install from [$GITHUB_URL]
  CHESSLOOP_REF              branch, tag or commit to install, or to update to
                             (default: the latest release; main if that can't be looked up)
                             [main; update: the branch the install is on]
  CHESSLOOP_ALLOW_UNTESTED=1       continue on an untested system or processor
  CHESSLOOP_ALLOW_LOW_RESOURCES=1  continue with little memory or disk
  CHESSLOOP_ALLOW_PUBLIC_LAN=1     allow "lan" on a machine with a public IP address
  CHESSLOOP_ALLOW_PACKAGE_REMOVAL=1  remove packages Docker conflicts with (containerd, runc, …)
  CHESSLOOP_PROGRESS=plain         stream command output instead of a progress line
Other settings:
  CHESSLOOP_BACKUP_DIR             where backups go [~/chessloop-backups]
  CHESSLOOP_UNINSTALL_LEVEL        same as --level
  CHESSLOOP_ALLOW_DATA_DELETE=1    allow uninstall level 3 with --yes
  CHESSLOOP_FINAL_BACKUP=0         uninstall level 3: no final backup [1]

Interactive mode asks for all of these. sudo may still ask for your password.
Every run writes a log to ~/chessloop-<action>-<date>.log (passwords are never in it).
Backups hold password hashes: they are saved with mode 600 (only you can read them).
USAGE
}

LOGS_FOLLOW=0
BACKUP_TARGET=""
RESTORE_FILE=""
UNINSTALL_LEVEL=""

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            -y|--yes|--non-interactive) NONINTERACTIVE=1 ;;
            -h|--help|help) usage; exit 0 ;;
            --force) UPDATE_FORCE=1 ;;
            --no-backup) CHESSLOOP_SKIP_BACKUP=1 ;;
            --with-settings) CHESSLOOP_BACKUP_SETTINGS=1 ;;
            --level) shift; CHESSLOOP_UNINSTALL_LEVEL="${1:-}" ;;
            --level=*) CHESSLOOP_UNINSTALL_LEVEL="${1#*=}" ;;
            -f|--follow) LOGS_FOLLOW=1 ;;
            install|update|uninstall|backup|restore|status|start|stop|restart|logs)
                if [ -n "$ACTION" ]; then echo "One action at a time (got '$ACTION' and '$1')." >&2; exit 2; fi
                ACTION="$1" ;;
            -*) echo "Unknown option: $1 (see: bash deploy.sh --help)" >&2; exit 2 ;;
            *)
                case "$ACTION" in
                    backup) BACKUP_TARGET="$1" ;;
                    restore) RESTORE_FILE="$1" ;;
                    *) echo "Unknown argument: $1 (see: bash deploy.sh --help)" >&2; exit 2 ;;
                esac ;;
        esac
        shift
    done
    [ "$NONINTERACTIVE" = 1 ] && [ -z "$ACTION" ] && ACTION=install
    return 0
}

main() {
    parse_args "$@"
    setup_colors
    trap 'on_err "$BASH_COMMAND" "$LINENO"' ERR
    trap on_exit EXIT
    trap 'exit 130' INT
    case "$ACTION" in
        status|start|stop|restart|logs) ;;   # no questions (sudo may still ask for a password)
        *)
            if [ "$NONINTERACTIVE" != 1 ] && ! tty_ok; then
                echo "This installer asks questions, so it needs a terminal." >&2
                echo "To run it without questions use --yes (see: bash deploy.sh --help)." >&2
                FATAL_SHOWN=2   # nothing went wrong: on_exit prints nothing more (F-059)
                exit 1
            fi
            ;;
    esac
    # Under "curl | bash" stdin is the script itself: no command may read it.
    # Questions read /dev/tty instead.
    exec </dev/null
    case "$ACTION" in
        install) do_install ;;
        update) do_update ;;
        uninstall) do_uninstall ;;
        backup) do_backup ;;
        restore) do_restore ;;
        status) do_status ;;
        start) do_start ;;
        stop) do_stop ;;
        restart) do_restart ;;
        logs) do_logs ;;
        *) main_menu ;;
    esac
}

# Sourcing with CHESSLOOP_SOURCE_ONLY=1 loads the functions without running
# anything (scripts/test-deploy-helpers.sh). The braces make bash read this
# whole line before running it, so an update that replaces this file while it
# runs can't make bash read the new file from the middle. Keep it the last line.
[ -n "${CHESSLOOP_SOURCE_ONLY:-}" ] || { main "$@"; exit $?; }
