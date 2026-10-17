#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  ChessLoop — Install, Update and Uninstall
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
HTTPS_GUIDE_URL="$GITHUB_URL#adding-https-after-localhost-only-install"
WSL_LAN_GUIDE_URL="https://learn.microsoft.com/windows/wsl/networking#mirrored-mode-networking"
MIN_RAM_MIB=1800      # a "2 GB" machine reports about 1.9 GiB; 2 GiB builds fine (Phase 04)
MIN_DISK_MIB=3072     # an install adds about 2.6 GB (Phase 04)
WANT_DISK_MIB=5120

# Legacy names, still used by Update and Uninstall (rewritten in a later release)
SYSTEMD_SERVICE_NAME="chessloop"
SYSTEMD_SERVICE_PATH="/etc/systemd/system/${SYSTEMD_SERVICE_NAME}.service"
SUDO=""
DOCKER_CMD="docker"

# ── Run state ─────────────────────────────────────────────────────────────
NONINTERACTIVE="${CHESSLOOP_NONINTERACTIVE:-0}"
ACTION=""                 # install | update | uninstall | "" (menu)
LOG_FILE=""
CURRENT_STEP="starting"
ERR_CMD=""
ERR_LINE=""
FATAL_SHOWN=0
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
header()  { blank; _say "  ${C}${BOLD}$*${RST}"; _say "  $(printf '─%.0s' {1..60})"; }
sep()     { _say "  ${DIM}$(printf '─%.0s' {1..60})${RST}"; }

# step "Title": a new section; its name is shown if something fails in it.
step() { CURRENT_STEP="$1"; header "$1"; }

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
        err "$label: failed (exit code $rc, after $(fmt_secs $((SECONDS - t0))))."
        show_log_tail 15
    fi
    return "$rc"
}

show_log_tail() {
    [ -n "$LOG_FILE" ] || return 0
    _say "  ${DIM}Last lines of the log:${RST}"
    tail -n 200 "$LOG_FILE" | tr '\r' '\n' | sed -E 's/\x1b\[[0-9;?]*[A-Za-z]//g' \
        | grep -av '^[[:space:]]*$' | tail -n "${1:-15}" | sed 's/^/      /' >&2 || true
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
    [ "$rc" -eq 0 ] && return 0
    blank
    if [ "$rc" -eq 130 ]; then
        err "Stopped (Ctrl+C) during: ${BOLD}$CURRENT_STEP${RST}"
    elif [ "$FATAL_SHOWN" -eq 0 ]; then
        err "Something went wrong during: ${BOLD}$CURRENT_STEP${RST}"
        [ -n "$ERR_CMD" ] && note "${DIM}command: $ERR_CMD (deploy.sh line $ERR_LINE, exit code $rc)${RST}"
        show_log_tail 15
    fi
    if [ "$ACTION" = install ]; then
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

# gen_password: 24 random letters and digits in groups of 4 (about 140 bits).
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

# ini_set SECTION KEY VALUE < in > out: set KEY=VALUE in [SECTION] of a
# Windows-style ini file (.wslconfig), keeping everything else; output CRLF.
ini_set() {
    SEC="$1" KEY="$2" VAL="$3" awk '
        BEGIN { sec = tolower(ENVIRON["SEC"]); key = tolower(ENVIRON["KEY"]); line = ENVIRON["KEY"] "=" ENVIRON["VAL"]; in_sec = 0; done = 0 }
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
        { sub(/\r$/, "") }
        /^[ \t]*\[/ { h = tolower($0); gsub(/[ \t]/, "", h); in_sec = (h == "[" sec "]"); next }
        in_sec && /=/ {
            k = tolower($0); sub(/[ \t]*=.*/, "", k); gsub(/^[ \t]+/, "", k)
            if (k == key) { v = $0; sub(/^[^=]*=[ \t]*/, "", v); sub(/[ \t]+$/, "", v); val = v }
        }
        END { print val }
    '
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

# What Docker is there? Sets DOCKER_KIND, NEED_DOCKER_INSTALL, NEED_COMPOSE_FIX.
check_docker() {
    DOCKER_KIND="$(docker_kind_of "$(command -v docker 2>/dev/null || true)")"
    case "$DOCKER_KIND" in
        desktop-shim)
            err "Docker Desktop is installed in Windows, but this Ubuntu can't use it yet."
            note "In Docker Desktop: Settings > Resources > WSL integration, switch on"
            note "\"${WSL_DISTRO:-this distribution}\", click Apply & restart, then run the installer again."
            note "(Or uninstall Docker Desktop, and the installer sets up Docker inside Ubuntu instead.)"
            FATAL_SHOWN=1; exit 1
            ;;
        desktop)
            if docker info >/dev/null 2>&1; then
                ok "Docker: Docker Desktop (WSL integration), $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo running)"
            else
                fatal "Docker Desktop's WSL integration is on, but Docker Desktop isn't running. Start Docker Desktop in Windows, wait until it says \"Engine running\", then run the installer again."
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

default_access() {
    if [ "$IS_WSL" = 1 ] || [ "$HAS_PUBLIC_IP" = 1 ]; then echo local; else echo lan; fi
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
setup_root() {
    [ "${#AS_ROOT[@]}" -gt 0 ] && return 0
    if [ "$(id -u)" -eq 0 ]; then AS_ROOT=(); return 0; fi
    command -v sudo >/dev/null 2>&1 || fatal "The installer needs administrator rights (sudo), and sudo isn't installed. Run it as root, or install sudo."
    AS_ROOT=(sudo)
    if ! sudo -n true 2>/dev/null; then
        info "The installer needs administrator rights to install system software and to"
        note "create $INSTALL_DIR. Type ${BOLD}your own password${RST} for $CL_USER when asked."
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
    note "This is usually a network problem: check this computer's internet connection,"
    note "then run the installer again. It continues where it stopped."
    FATAL_SHOWN=1; exit 1
}

install_packages() {
    [ "${#NEED_PKGS[@]}" -gt 0 ] || return 0
    step "Installing system packages"
    apt_update_once
    run "Installing ${NEED_PKGS[*]}" apt_get install --no-install-recommends "${NEED_PKGS[@]}" || explain_network_failure
}

# Docker's apt repository, as in docs.docker.com/engine/install/{ubuntu,debian}
# (deb822 .sources file, key in /etc/apt/keyrings; checked 2026-10-17).
add_docker_repo() {
    local distro codename arch tmp
    [ -f /etc/apt/sources.list.d/docker.sources ] && return 0
    if [ "$OS_ID" = ubuntu ] || [ -n "$OS_UBUNTU_CODENAME" ]; then
        distro=ubuntu; codename="${OS_UBUNTU_CODENAME:-$OS_CODENAME}"
    else
        distro=debian; codename="$OS_CODENAME"
    fi
    [ -n "$codename" ] || fatal "Can't tell which $distro release this is (no VERSION_CODENAME in /etc/os-release)."
    arch="$(dpkg --print-architecture)"
    run "Creating /etc/apt/keyrings" "${AS_ROOT[@]}" install -m 0755 -d /etc/apt/keyrings
    run "Downloading Docker's signing key" "${AS_ROOT[@]}" curl -fsSL "https://download.docker.com/linux/$distro/gpg" -o /etc/apt/keyrings/docker.asc \
        || explain_network_failure
    "${AS_ROOT[@]}" chmod a+r /etc/apt/keyrings/docker.asc
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
        run "Removing ${CONFLICT_PKGS[*]} (replaced by Docker's packages)" apt_get remove "${CONFLICT_PKGS[@]}"
    fi
    add_docker_repo
    run "Installing Docker Engine (about 1 minute)" apt_get install \
        docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin || explain_network_failure
}

# Docker from the distribution (docker.io) without "docker compose" (F-013).
install_compose_plugin() {
    step "Adding Docker's compose plugin"
    apt_update_once
    if dpkg-query -W -f='${Status}' docker.io 2>/dev/null | grep -q 'install ok installed' \
        && [ -n "$(apt-cache policy docker-compose-v2 2>/dev/null | awk '/Candidate:/ && $2 != "(none)" {print $2}')" ]; then
        # Ubuntu packages compose for its own docker.io
        run "Installing docker-compose-v2 (matches the docker.io package)" apt_get install docker-compose-v2 || explain_network_failure
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
as_owner() {
    if [ "$(id -u)" -eq 0 ] && [ "$OWNER" != root ]; then sudo -u "$OWNER" -H "$@"; else "$@"; fi
}

get_source() {
    [ "$RESUME" = 1 ] || [ "$REUSE_CLONE" = 1 ] && return 0
    step "Downloading ChessLoop"
    if [ ! -d "$INSTALL_DIR" ]; then
        "${AS_ROOT[@]}" install -d -m 0755 -o "$OWNER" -g "$(id -gn "$OWNER" 2>/dev/null || echo "$OWNER")" "$INSTALL_DIR" \
            || fatal "Couldn't create $INSTALL_DIR."
    fi
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

explain_build_failure() {
    local tail
    tail="$(tail -n 60 "${LOG_FILE:-/dev/null}" 2>/dev/null || true)"
    if grep -qiE 'registry-1\.docker\.io|TLS handshake timeout|no such host|i/o timeout|connection reset|temporary failure in name resolution|failed to (fetch|resolve|do request)|network is unreachable' <<<"$tail"; then
        note "Downloading from the internet failed (Docker Hub or a package server)."
        explain_network_failure
    fi
    if grep -qiE 'no space left on device' <<<"$tail"; then
        note "The disk is full. Free up space (at least 3 GB), then run the installer again."
        FATAL_SHOWN=1; exit 1
    fi
    if grep -qiE 'killed|out of memory|exit code: 137' <<<"$tail"; then
        note "The build ran out of memory. ChessLoop needs about 2 GB of RAM to build."
        FATAL_SHOWN=1; exit 1
    fi
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
    if [ "$WSL_KEEPALIVE" = 1 ]; then
        wslconfig_set "$wslconfig" general instanceIdleTimeout -1
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
docker_words() { if [ "${DOCKER[0]}" = sudo ]; then echo "sudo docker"; else echo "docker"; fi; }

print_summary() {
    local d url lan_ok=0
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
            note "Next step: put an HTTPS server (Caddy is the easiest) in front of"
            note "http://localhost:$PORT and point $DOMAIN at this computer. Guide:"
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
    _say "  ${BOLD}Manage it${RST} ${DIM}(type these in a terminal)${RST}"
    note "cd $SUBDIR"
    note "Stop:     $d compose -f docker-compose.prod.yml stop"
    note "Start:    $d compose -f docker-compose.prod.yml up -d"
    note "Messages: $d compose -f docker-compose.prod.yml logs --tail 100"
    note "Update or uninstall:  bash $INSTALL_DIR/deploy.sh"
    if [ "${DOCKER[0]}" = sudo ] && [ "$(id -u)" -ne 0 ]; then
        note "${DIM}After you log out and in again, you can leave out \"sudo\" before docker.${RST}"
    fi
    blank
    note "Data: Docker volume ${BOLD}$VOLUME_NAME${RST} (back it up from Admin → Backups)."
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
    state_set complete "$(date -Is)"
    CURRENT_STEP="finishing"
    print_summary
}

# ═══════════════════════════════════════════════════════════════════════════
#  UPDATE AND UNINSTALL (unchanged behaviour; Phase 09 rewrites them)
# ═══════════════════════════════════════════════════════════════════════════
# shellcheck disable=SC2162  # every caller passes -r
_read() { read "$@" </dev/tty; }

setup_sudo() {
    if [ "$(id -u)" -eq 0 ]; then
        SUDO=""
    elif command -v sudo &>/dev/null; then
        SUDO="sudo"
        if ! sudo -n true 2>/dev/null; then
            info "This script needs sudo for system-level actions."
            sudo -v || fatal "sudo authentication failed."
        fi
    else
        fatal "root or sudo required. Neither is available."
    fi
}

find_install_dir() {
    local candidates=("$DEFAULT_INSTALL_DIR" "/home/$USER/chessloop" "$HOME/chessloop" "$(pwd)" "$(pwd)/..")
    for dir in "${candidates[@]}"; do
        # Resolve to absolute path
        dir="$(cd "$dir" 2>/dev/null && pwd || echo "")"
        [ -z "$dir" ] && continue
        if [ -f "$dir/chessloop/docker-compose.prod.yml" ]; then
            echo "$dir"
            return 0
        fi
    done
    echo ""
}

# ═══════════════════════════════════════════════════════════════════════════
#  HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════════════
health_check() {
    local port="$1"
    local subdir="$2"
    info "Waiting for ChessLoop to be ready (max 90s)…"
    local ok_flag=false
    local i=1
    while [ "$i" -le 45 ]; do
        if curl -sf "http://localhost:${port}/api/health" >/dev/null 2>&1; then
            ok_flag=true
            break
        fi
        printf "  ${DIM}  ping %d/45…${RST}\r" "$i"
        sleep 2
        ((i++))
    done
    echo ""
    if $ok_flag; then
        ok "ChessLoop is healthy on port $port"
    else
        warn "Health check timed out. Services may still be starting."
        info "Check logs: $DOCKER_CMD compose -f $subdir/docker-compose.prod.yml logs -f"
        return 1
    fi
}

# ═══════════════════════════════════════════════════════════════════════════
#  UPDATE
# ═══════════════════════════════════════════════════════════════════════════
do_update() {
    header "Update ChessLoop"

    # ── Find install ──────────────────────────────────────────────────────
    local install_dir
    install_dir=$(find_install_dir)
    if [ -z "$install_dir" ]; then
        blank
        _read -rp "  ${BOLD}Install directory${RST} [default: $DEFAULT_INSTALL_DIR]: " install_dir
        install_dir="${install_dir:-$DEFAULT_INSTALL_DIR}"
    else
        ok "Found existing install: $install_dir"
    fi

    local subdir="$install_dir/chessloop"
    [ -f "$subdir/docker-compose.prod.yml" ] || fatal "No ChessLoop install found at $install_dir"

    setup_sudo
    if ! command -v docker &>/dev/null; then fatal "Docker is not installed."; fi
    if ! docker info &>/dev/null 2>&1; then DOCKER_CMD="sudo docker"; fi

    # ── Backup first ──────────────────────────────────────────────────────
    header "Pre-update backup"
    local backup_name
    backup_name="backup-pre-update-$(date +%Y%m%d-%H%M%S).tar.gz"
    if $DOCKER_CMD volume ls --format '{{.Name}}' 2>/dev/null | grep -q 'chessloop-data'; then
        info "Snapshotting chessloop-data volume → $install_dir/$backup_name"
        if $DOCKER_CMD run --rm \
            -v chessloop-data:/src \
            -v "$install_dir":/out \
            alpine tar czf "/out/$backup_name" -C /src . 2>/dev/null; then
            ok "Backup saved: $install_dir/$backup_name"
        else
            warn "Backup failed — continuing. Manually back up if you have important data."
        fi
    else
        warn "chessloop-data volume not found — skipping backup."
    fi

    # ── Git pull ──────────────────────────────────────────────────────────
    header "Pulling latest code"
    cd "$install_dir" || fatal "Cannot open $install_dir"

    local current_hash
    current_hash=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    info "Current commit: $current_hash"

    git fetch origin main 2>&1 | sed 's/^/    /'

    local remote_hash
    remote_hash=$(git rev-parse --short origin/main 2>/dev/null || echo "unknown")
    info "Latest commit:  $remote_hash"

    if [ "$current_hash" = "$remote_hash" ]; then
        ok "Already up to date ($current_hash)."
        blank
        local force
        _read -rp "  Force rebuild anyway? [y/N]: " force
        if [[ ! "${force:-n}" =~ ^[Yy]$ ]]; then
            info "Nothing to do. Exiting."
            return 0
        fi
    else
        git pull origin main 2>&1 | sed 's/^/    /'
        ok "Updated to $(git rev-parse --short HEAD 2>/dev/null)"
    fi

    # ── Rebuild ───────────────────────────────────────────────────────────
    header "Rebuilding containers"
    cd "$subdir" || fatal "Cannot open $subdir"
    $DOCKER_CMD compose -f docker-compose.prod.yml up -d --build --remove-orphans
    ok "Containers rebuilt. Data volume preserved."

    # ── Health check ──────────────────────────────────────────────────────
    local port=8090
    if [ -f "$subdir/.env" ]; then
        local env_port
        env_port=$(grep -E '^PUBLIC_PORT=' "$subdir/.env" 2>/dev/null | cut -d= -f2 | tr -d '"' || true)
        port="${env_port:-8090}"
    fi

    header "Verifying health"
    health_check "$port" "$subdir" || true

    blank
    ok "ChessLoop updated successfully!"
    info "Access: http://localhost:$port"
    blank
}

# ═══════════════════════════════════════════════════════════════════════════
#  UNINSTALL
# ═══════════════════════════════════════════════════════════════════════════
do_uninstall() {
    header "Uninstall ChessLoop"

    local install_dir
    install_dir=$(find_install_dir)
    if [ -z "$install_dir" ]; then
        blank
        _read -rp "  ${BOLD}Install directory${RST} [default: $DEFAULT_INSTALL_DIR]: " install_dir
        install_dir="${install_dir:-$DEFAULT_INSTALL_DIR}"
    else
        ok "Found existing install: $install_dir"
    fi

    local subdir="$install_dir/chessloop"

    setup_sudo
    if ! command -v docker &>/dev/null; then
        warn "Docker not found. Skipping container removal."
    else
        if ! docker info &>/dev/null 2>&1; then DOCKER_CMD="sudo docker"; fi
    fi

    blank
    echo -e "  ${BOLD}Select removal level:${RST}"
    blank
    echo -e "    ${BOLD}1)${RST}  ${Y}Containers only${RST}"
    echo -e "         Stop and remove containers; keep Docker images and all data"
    blank
    echo -e "    ${BOLD}2)${RST}  ${Y}Containers + images${RST}"
    echo -e "         Remove containers and Docker images; keep database and files"
    blank
    echo -e "    ${BOLD}3)${RST}  ${R}Full uninstall${RST}"
    echo -e "         Remove everything: containers, images, database, files, systemd"
    echo -e "         ${R}${BOLD}This deletes all user accounts, libraries, and data permanently.${RST}"
    blank
    echo -e "    ${BOLD}4)${RST}  Cancel"
    blank
    local level
    _read -rp "  Choice [1-4]: " level

    case "${level:-4}" in
        1|2|3) : ;;
        *)
            info "Uninstall cancelled."
            return 0
            ;;
    esac

    # ── Confirmation gates ────────────────────────────────────────────────
    blank
    if [ "$level" -eq 3 ]; then
        warn "${BOLD}FULL UNINSTALL: all data will be permanently destroyed.${RST}"
        blank
        local c1
        _read -rp "  Type ${BOLD}DELETE${RST} to confirm: " c1
        [ "$c1" = "DELETE" ] || { info "Cancelled."; return 0; }
        blank
        local c2
        _read -rp "  Final check — type ${BOLD}YES${RST} to proceed: " c2
        [ "$c2" = "YES" ] || { info "Cancelled."; return 0; }
    elif [ "$level" -eq 2 ]; then
        local c1
        _read -rp "  Remove images? This cannot be undone. [y/N]: " c1
        [[ "${c1:-n}" =~ ^[Yy]$ ]] || { info "Cancelled."; return 0; }
    fi

    blank

    # ── Stop & remove containers ──────────────────────────────────────────
    header "Stopping containers"
    if command -v docker &>/dev/null; then
        if [ -f "$subdir/docker-compose.prod.yml" ]; then
            cd "$subdir" 2>/dev/null || true
            if $DOCKER_CMD compose -f docker-compose.prod.yml down 2>/dev/null; then
                ok "Containers stopped and removed."
            else
                warn "docker compose down failed (containers may already be stopped)."
            fi
        else
            for c in chessloop-nginx chessloop-frontend chessloop-backend; do
                if $DOCKER_CMD ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${c}$"; then
                    $DOCKER_CMD stop "$c" 2>/dev/null || true
                    $DOCKER_CMD rm   "$c" 2>/dev/null || true
                    ok "Removed container: $c"
                fi
            done
        fi
    fi

    # ── Remove images ─────────────────────────────────────────────────────
    if [ "$level" -ge 2 ] && command -v docker &>/dev/null; then
        header "Removing Docker images"
        for img in chessloop-backend chessloop-frontend; do
            if $DOCKER_CMD image inspect "$img" &>/dev/null 2>&1; then
                if $DOCKER_CMD rmi "$img" 2>/dev/null; then ok "Removed image: $img"
                else warn "Could not remove image $img (may be in use)"; fi
            fi
        done
    fi

    # ── Remove data volume ────────────────────────────────────────────────
    if [ "$level" -ge 3 ] && command -v docker &>/dev/null; then
        header "Removing data volume"
        if $DOCKER_CMD volume ls --format '{{.Name}}' 2>/dev/null | grep -q 'chessloop-data'; then
            if $DOCKER_CMD volume rm chessloop-data 2>/dev/null; then
                ok "Removed volume: chessloop-data"
            else
                warn "Could not remove volume. Try: sudo docker volume rm chessloop-data"
            fi
        else
            info "Volume chessloop-data not found — already removed or never created."
        fi
    fi

    # ── Remove systemd service ────────────────────────────────────────────
    if [ -f "$SYSTEMD_SERVICE_PATH" ] && command -v systemctl &>/dev/null; then
        header "Removing systemd service"
        $SUDO systemctl stop  "$SYSTEMD_SERVICE_NAME" 2>/dev/null || true
        $SUDO systemctl disable "$SYSTEMD_SERVICE_NAME" 2>/dev/null || true
        $SUDO rm -f "$SYSTEMD_SERVICE_PATH"
        $SUDO systemctl daemon-reload 2>/dev/null || true
        ok "Systemd service removed."
    fi

    # ── Remove install directory ──────────────────────────────────────────
    if [ "$level" -ge 3 ] && [ -d "$install_dir" ]; then
        header "Removing files"
        $SUDO rm -rf "$install_dir"
        ok "Removed: $install_dir"
    fi

    blank
    ok "ChessLoop uninstalled (level $level)."
    if [ "$level" -lt 3 ]; then
        info "Files remain at: $install_dir"
        if [ "$level" -lt 2 ]; then
            info "Docker images and data volume are intact."
        else
            info "Data volume is intact."
        fi
        info "To fully remove later, run this script again and choose ${BOLD}Full uninstall${RST}."
    fi
    blank
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

main_menu() {
    print_banner
    local install_dir running
    install_dir=$(find_install_dir)
    if [ -n "$install_dir" ]; then
        echo -e "  ${G}${BOLD}Existing install:${RST} $install_dir" >&2
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
    echo -e "    ${BOLD}2)${RST}  ${C}Update${RST}     — Get the latest version (your data is kept)" >&2
    echo -e "    ${BOLD}3)${RST}  ${R}Uninstall${RST}  — Remove ChessLoop (choose how much)" >&2
    echo -e "    ${BOLD}4)${RST}  ${DIM}Exit${RST}" >&2
    blank
    local choice
    _read -rp "  Choice [1-4]: " choice
    blank
    case "${choice:-4}" in
        1) do_install ;;
        2) ACTION=update; setup_log update; do_update ;;
        3) ACTION=uninstall; setup_log uninstall; do_uninstall ;;
        4|q|Q) echo -e "  ${DIM}Goodbye.${RST}" >&2; exit 0 ;;
        *) warn "Please type a number from 1 to 4."; sleep 1; main_menu ;;
    esac
}

usage() {
    cat <<USAGE
ChessLoop installer

Usage:
  bash deploy.sh               menu: Install, Update or Uninstall
  bash deploy.sh install       go straight to Install
  bash deploy.sh --yes         install without questions, using the settings below
  bash deploy.sh --help        this text
  curl -fsSL https://raw.githubusercontent.com/antonizick/chessloop/main/deploy.sh | bash -s -- --yes

Settings for --yes (environment variables; the defaults are in brackets):
  CHESSLOOP_ADMIN_EMAIL      admin email address (required)
  CHESSLOOP_ADMIN_PASSWORD   admin password, 12+ characters [generated and shown once]
  CHESSLOOP_ADMIN_USERNAME   admin display name [admin]
  CHESSLOOP_ACCESS           local (this computer), lan (home network) or domain
                             [local on WSL or with a public IP address, else lan]
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
  CHESSLOOP_REF              branch, tag or commit [main]
  CHESSLOOP_ALLOW_UNTESTED=1       continue on an untested system or processor
  CHESSLOOP_ALLOW_LOW_RESOURCES=1  continue with little memory or disk
  CHESSLOOP_ALLOW_PUBLIC_LAN=1     allow "lan" on a machine with a public IP address
  CHESSLOOP_PROGRESS=plain         stream command output instead of a progress line

Interactive mode asks for all of these. sudo may still ask for your password.
Every run writes a log to ~/chessloop-<action>-<date>.log (passwords are never in it).
USAGE
}

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            -y|--yes|--non-interactive) NONINTERACTIVE=1 ;;
            -h|--help) usage; exit 0 ;;
            install|update|uninstall) ACTION="$1" ;;
            *) echo "Unknown option: $1 (see: bash deploy.sh --help)" >&2; exit 2 ;;
        esac
        shift
    done
    [ "$NONINTERACTIVE" = 1 ] && [ -z "$ACTION" ] && ACTION=install
    if [ "$NONINTERACTIVE" = 1 ] && [ "$ACTION" != install ]; then
        echo "--yes works with Install only for now." >&2; exit 2
    fi
    return 0
}

main() {
    parse_args "$@"
    setup_colors
    trap 'on_err "$BASH_COMMAND" "$LINENO"' ERR
    trap on_exit EXIT
    trap 'exit 130' INT
    if [ "$NONINTERACTIVE" != 1 ] && ! tty_ok; then
        echo "This installer asks questions, so it needs a terminal." >&2
        echo "For an unattended install use --yes (see: bash deploy.sh --help)." >&2
        exit 1
    fi
    # Under "curl | bash" stdin is the script itself: no command may read it.
    # Questions read /dev/tty instead.
    exec </dev/null
    case "$ACTION" in
        install) do_install ;;
        update) setup_log update; do_update ;;
        uninstall) setup_log uninstall; do_uninstall ;;
        *) main_menu ;;
    esac
}

# Sourcing with CHESSLOOP_SOURCE_ONLY=1 loads the functions without running
# anything (scripts/test-deploy-helpers.sh). This must stay the last line.
[ -n "${CHESSLOOP_SOURCE_ONLY:-}" ] || main "$@"
