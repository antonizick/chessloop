#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  ChessLoop — Interactive Deploy Script
#
#  Usage (fresh machine):
#    curl -fsSL https://raw.githubusercontent.com/antonizick/chessloop/main/deploy.sh | bash
#
#  Usage (local):
#    bash deploy.sh
#
#  Three modes:
#    1) Install   — clone repo, install deps, configure ports, build, start
#    2) Update    — pull latest code from GitHub, rebuild (data preserved)
#    3) Uninstall — containers-only, containers+images, or full wipe
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ── Interactive stdin fix (for curl | bash) ───────────────────────────────
# Never redirect global stdin — that breaks the pipe while curl is still
# writing. Instead, detect the pipe once and route each read to /dev/tty.
_PIPED=0
if [ ! -t 0 ]; then
    if [ -e /dev/tty ]; then
        _PIPED=1
    else
        echo "ERROR: This script requires an interactive terminal." >&2
        echo "       Run: bash deploy.sh   (not via pipe)" >&2
        exit 1
    fi
fi
_read() { if [ "$_PIPED" -eq 1 ]; then read "$@" </dev/tty; else read "$@"; fi; }

# ── Colors ────────────────────────────────────────────────────────────────
if command -v tput &>/dev/null && tput colors &>/dev/null && [ "$(tput colors)" -ge 8 ]; then
    R=$'\033[0;31m' G=$'\033[0;32m' Y=$'\033[1;33m'
    C=$'\033[0;36m' DIM=$'\033[2m' BOLD=$'\033[1m' RST=$'\033[0m'
else
    R='' G='' Y='' C='' DIM='' BOLD='' RST=''
fi

# ── Globals (set during install/detect) ──────────────────────────────────
GITHUB_URL="https://github.com/antonizick/chessloop"
DEFAULT_INSTALL_DIR="/opt/chessloop"
DEFAULT_PORT=8090
SYSTEMD_SERVICE_NAME="chessloop"
SYSTEMD_SERVICE_PATH="/etc/systemd/system/${SYSTEMD_SERVICE_NAME}.service"
SUDO=""
DOCKER_CMD="docker"
OS=""
OS_FAMILY=""

# ── Logging helpers ───────────────────────────────────────────────────────
info()    { echo -e "  ${C}→${RST}  $*" >&2; }
ok()      { echo -e "  ${G}✓${RST}  $*" >&2; }
warn()    { echo -e "  ${Y}⚠${RST}  $*" >&2; }
err()     { echo -e "  ${R}✗${RST}  $*" >&2; }
fatal()   { err "$*"; exit 1; }
header()  { echo -e "\n  ${C}${BOLD}$*${RST}\n  $(printf '─%.0s' {1..54})\n" >&2; }
sep()     { echo -e "  ${DIM}$(printf '─%.0s' {1..54})${RST}" >&2; }
blank()   { echo "" >&2; }

# ═══════════════════════════════════════════════════════════════════════════
#  PLATFORM DETECTION
# ═══════════════════════════════════════════════════════════════════════════
detect_platform() {
    if [ -f /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        OS="${ID:-unknown}"
        local like="${ID_LIKE:-}"
        case "$OS $like" in
            *ubuntu*|*debian*|*mint*|*pop*|*elementary*|*kali*|*raspbian*)
                OS_FAMILY="debian" ;;
            *rhel*|*centos*|*fedora*|*rocky*|*alma*|*oracle*|*amzn*)
                OS_FAMILY="rhel" ;;
            *arch*|*manjaro*|*endeavour*|*garuda*)
                OS_FAMILY="arch" ;;
            *)
                OS_FAMILY="unknown" ;;
        esac
    elif command -v lsb_release &>/dev/null; then
        OS=$(lsb_release -si | tr '[:upper:]' '[:lower:]')
        OS_FAMILY="debian"
    else
        OS="unknown"; OS_FAMILY="unknown"
    fi
    info "Platform: ${OS} (family: ${OS_FAMILY})"
}

# ═══════════════════════════════════════════════════════════════════════════
#  SUDO / ROOT SETUP
# ═══════════════════════════════════════════════════════════════════════════
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

# ═══════════════════════════════════════════════════════════════════════════
#  PORT UTILITIES
# ═══════════════════════════════════════════════════════════════════════════
port_in_use() {
    local port="$1"
    if command -v ss &>/dev/null; then
        ss -tlnp 2>/dev/null | grep -qE ":${port}[ \t]"
        return $?
    elif command -v netstat &>/dev/null; then
        netstat -tlnp 2>/dev/null | grep -qE ":${port}[ \t]"
        return $?
    else
        # Fallback: TCP connection probe
        (echo >/dev/tcp/127.0.0.1/"$port") 2>/dev/null
        return $?
    fi
}

list_used_ports() {
    if command -v ss &>/dev/null; then
        ss -tlnp 2>/dev/null | awk 'NR>1 {print $4}' | grep -oE '[0-9]+$' | sort -n | uniq | tr '\n' ' '
    elif command -v netstat &>/dev/null; then
        netstat -tlnp 2>/dev/null | awk 'NR>2 {print $4}' | grep -oE '[0-9]+$' | sort -n | uniq | tr '\n' ' '
    fi
}

find_free_port() {
    local port="${1:-$DEFAULT_PORT}"
    local max=$((port + 200))
    while [ "$port" -lt "$max" ]; do
        if ! port_in_use "$port"; then
            echo "$port"
            return 0
        fi
        ((port++))
    done
    echo "$DEFAULT_PORT"
}

prompt_port() {
    local label="$1"
    local default="${2:-$DEFAULT_PORT}"

    info "Scanning listening ports…"
    local used_ports
    used_ports=$(list_used_ports 2>/dev/null || echo "")
    if [ -n "$used_ports" ]; then
        echo -e "  ${DIM}  In use: $used_ports${RST}" >&2
    fi

    local suggested
    suggested=$(find_free_port "$default")

    if port_in_use "$default"; then
        warn "Port $default is in use. Suggested free port: ${BOLD}${suggested}${RST}"
    else
        ok "Port $default is free."
        suggested="$default"
    fi

    blank
    local user_port
    _read -rp "  ${BOLD}$label${RST} [default: $suggested]: " user_port
    user_port="${user_port:-$suggested}"

    # Validate
    if ! [[ "$user_port" =~ ^[0-9]+$ ]] || [ "$user_port" -lt 1 ] || [ "$user_port" -gt 65535 ]; then
        warn "Invalid port '$user_port', using $suggested"
        user_port="$suggested"
    fi

    if port_in_use "$user_port"; then
        warn "Port $user_port is still in use — services may fail to start."
    fi

    echo "$user_port"
}

# ═══════════════════════════════════════════════════════════════════════════
#  DEPENDENCY INSTALLATION
# ═══════════════════════════════════════════════════════════════════════════
_pkg_install() {
    local pkg="$1"
    info "Installing $pkg…"
    case "$OS_FAMILY" in
        debian)
            $SUDO apt-get install -y "$pkg" >/dev/null 2>&1 || fatal "Failed to install $pkg"
            ;;
        rhel)
            if command -v dnf &>/dev/null; then
                $SUDO dnf install -y "$pkg" >/dev/null 2>&1
            else
                $SUDO yum install -y "$pkg" >/dev/null 2>&1
            fi || fatal "Failed to install $pkg"
            ;;
        arch)
            $SUDO pacman -Sy --noconfirm "$pkg" >/dev/null 2>&1 || fatal "Failed to install $pkg"
            ;;
        *)
            fatal "Cannot auto-install on $OS_FAMILY. Please install '$pkg' manually and re-run."
            ;;
    esac
    ok "$pkg installed."
}

_install_docker() {
    info "Installing Docker via get.docker.com…"
    case "$OS_FAMILY" in
        debian|rhel)
            curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
            $SUDO bash /tmp/get-docker.sh >/dev/null 2>&1
            rm -f /tmp/get-docker.sh
            ;;
        arch)
            $SUDO pacman -Sy --noconfirm docker >/dev/null 2>&1
            ;;
        *)
            fatal "Cannot auto-install Docker on $OS_FAMILY. See: https://docs.docker.com/engine/install/"
            ;;
    esac
    $SUDO systemctl enable --now docker >/dev/null 2>&1 || true

    # Add current user to docker group so future sessions don't need sudo
    if [ -n "$SUDO" ] && [ "$(id -u)" -ne 0 ]; then
        $SUDO usermod -aG docker "$USER" 2>/dev/null || true
        warn "Added $USER to docker group. You'll need to log out/in for it to apply."
        warn "For this session, docker will run via sudo."
        DOCKER_CMD="sudo docker"
    fi
    ok "Docker installed."
}

ensure_deps() {
    header "Checking prerequisites"
    detect_platform
    setup_sudo

    local pkg_updated=false

    # git
    if ! command -v git &>/dev/null; then
        [ "$OS_FAMILY" = "debian" ] && ! $pkg_updated && { $SUDO apt-get update -qq; pkg_updated=true; }
        _pkg_install git
    else
        ok "git $(git --version | awk '{print $3}')"
    fi

    # curl
    if ! command -v curl &>/dev/null; then
        _pkg_install curl
    else
        ok "curl $(curl --version | head -1 | awk '{print $2}')"
    fi

    # openssl (for JWT secret generation)
    if ! command -v openssl &>/dev/null; then
        _pkg_install openssl 2>/dev/null || true
    fi

    # docker
    if ! command -v docker &>/dev/null; then
        [ "$OS_FAMILY" = "debian" ] && ! $pkg_updated && { $SUDO apt-get update -qq; pkg_updated=true; }
        _install_docker
    else
        ok "docker $(docker --version | awk '{print $3}' | tr -d ',')"
        # Check if current user can run docker without sudo
        if ! docker info &>/dev/null 2>&1; then
            if sudo docker info &>/dev/null 2>&1; then
                DOCKER_CMD="sudo docker"
                warn "Docker requires sudo for this user. Using sudo."
            else
                # Daemon not running — try to start it
                info "Docker daemon not running. Attempting to start…"
                if command -v systemctl &>/dev/null && systemctl --version &>/dev/null 2>&1 && [ "$(cat /proc/1/comm 2>/dev/null)" = "systemd" ]; then
                    $SUDO systemctl start docker 2>/dev/null || true
                elif command -v service &>/dev/null; then
                    $SUDO service docker start 2>/dev/null || true
                fi
                # Re-check after start attempt
                if sudo docker info &>/dev/null 2>&1; then
                    DOCKER_CMD="sudo docker"
                    warn "Docker requires sudo for this user. Using sudo."
                else
                    fatal "Docker daemon could not be started. On WSL2: sudo service docker start  |  On systemd: sudo systemctl start docker"
                fi
            fi
        fi
    fi

    # docker compose
    if ! $DOCKER_CMD compose version &>/dev/null 2>&1; then
        info "Installing docker compose plugin…"
        case "$OS_FAMILY" in
            debian)
                [ "$pkg_updated" = false ] && { $SUDO apt-get update -qq; pkg_updated=true; }
                $SUDO apt-get install -y docker-compose-plugin >/dev/null 2>&1 || \
                    warn "docker-compose-plugin not available via apt. Trying binary download."
                ;;
        esac
        # Fallback: download compose binary
        if ! $DOCKER_CMD compose version &>/dev/null 2>&1; then
            local compose_url
            compose_url="https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)"
            $SUDO curl -fsSL "$compose_url" -o /usr/local/bin/docker-compose && \
                $SUDO chmod +x /usr/local/bin/docker-compose || \
                fatal "Could not install docker compose. See: https://docs.docker.com/compose/install/"
        fi
    fi

    if $DOCKER_CMD compose version &>/dev/null 2>&1; then
        ok "docker compose $($DOCKER_CMD compose version --short 2>/dev/null || echo 'ok')"
    else
        fatal "docker compose is not available after install attempt."
    fi

    blank
}

# ═══════════════════════════════════════════════════════════════════════════
#  FIND EXISTING INSTALL
# ═══════════════════════════════════════════════════════════════════════════
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
#  SYSTEMD SERVICE
# ═══════════════════════════════════════════════════════════════════════════
setup_systemd() {
    local subdir="$1"
    header "Systemd autostart"

    if ! command -v systemctl &>/dev/null; then
        warn "systemd not found on this system — skipping autostart."
        return 0
    fi

    local docker_bin
    docker_bin=$(command -v docker)

    cat > /tmp/chessloop.service <<EOF
[Unit]
Description=ChessLoop Chess Training System
Documentation=https://github.com/antonizick/chessloop
After=docker.service network-online.target
Requires=docker.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${subdir}
EnvironmentFile=${subdir}/.env
ExecStartPre=${docker_bin} compose -f docker-compose.prod.yml pull --quiet 2>/dev/null || true
ExecStart=${docker_bin} compose -f docker-compose.prod.yml up
ExecStop=${docker_bin} compose -f docker-compose.prod.yml down
Restart=always
RestartSec=10
User=${USER}

[Install]
WantedBy=multi-user.target
EOF

    $SUDO mv /tmp/chessloop.service "$SYSTEMD_SERVICE_PATH"
    $SUDO systemctl daemon-reload
    $SUDO systemctl enable "$SYSTEMD_SERVICE_NAME"
    ok "Systemd service enabled."
    info "  systemctl start   chessloop"
    info "  systemctl stop    chessloop"
    info "  systemctl status  chessloop"
}

# ═══════════════════════════════════════════════════════════════════════════
#  INSTALL SUMMARY
# ═══════════════════════════════════════════════════════════════════════════
print_summary() {
    local port="$1"
    local install_dir="$2"
    local subdir="$3"
    local server_ip
    server_ip=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "your-server-ip")

    blank
    echo -e "  ${G}${BOLD}╔═══════════════════════════════════════════════════════╗${RST}"
    echo -e "  ${G}${BOLD}║         ✓  ChessLoop is live!                         ║${RST}"
    echo -e "  ${G}${BOLD}╚═══════════════════════════════════════════════════════╝${RST}"
    blank
    echo -e "  ${BOLD}Access:${RST}"
    echo -e "    http://localhost:$port"
    echo -e "    http://$server_ip:$port"
    blank
    echo -e "  ${BOLD}First login:${RST}"
    echo -e "    1. Open the URL above"
    echo -e "    2. Click Register → create your account"
    echo -e "    3. To promote to admin, use the CLI:"
    echo -e "    ${DIM}$DOCKER_CMD compose -f $subdir/docker-compose.prod.yml \\"
    echo -e "      exec backend python -c \\"
    echo -e "      \"from database import get_db; from sqlmodel import Session, select; \\"
    echo -e "       from models.user import User; db=next(get_db()); \\"
    echo -e "       u=db.exec(select(User).where(User.username=='YOUR_USERNAME')).first(); \\"
    echo -e "       u.role='admin'; db.add(u); db.commit()\"${RST}"
    blank
    echo -e "  ${BOLD}Service management:${RST}"
    echo -e "    Start:   systemctl start chessloop"
    echo -e "    Stop:    systemctl stop chessloop"
    echo -e "    Restart: systemctl restart chessloop"
    echo -e "    Logs:    $DOCKER_CMD compose -f $subdir/docker-compose.prod.yml logs -f"
    blank
    echo -e "  ${BOLD}Update ChessLoop later:${RST}"
    echo -e "    bash $install_dir/deploy.sh  → choose ${BOLD}Update${RST}"
    blank
    echo -e "  ${BOLD}Backups:${RST}"
    echo -e "    Admin panel → Admin → Database backups"
    echo -e "    Manual:  $DOCKER_CMD run --rm -v chessloop-data:/src -v \$(pwd):/out alpine \\"
    echo -e "             tar czf /out/backup-\$(date +%F).tar.gz -C /src ."
    blank
}

# ═══════════════════════════════════════════════════════════════════════════
#  INSTALL
# ═══════════════════════════════════════════════════════════════════════════
do_install() {
    header "Fresh Installation"

    # ── Install directory ──────────────────────────────────────────────────
    blank
    local install_dir
    _read -rp "  ${BOLD}Install directory${RST} [default: $DEFAULT_INSTALL_DIR]: " install_dir
    install_dir="${install_dir:-$DEFAULT_INSTALL_DIR}"
    local subdir="$install_dir/chessloop"

    if [ -f "$subdir/docker-compose.prod.yml" ]; then
        fatal "ChessLoop is already installed at $install_dir. Use ${BOLD}Update${RST} instead."
    fi

    # ── Dependencies ──────────────────────────────────────────────────────
    ensure_deps

    # ── Clone repo ────────────────────────────────────────────────────────
    header "Cloning repository"
    if [ -d "$install_dir/.git" ]; then
        warn "Git repo already exists at $install_dir. Pulling latest instead…"
        cd "$install_dir" && git pull
    else
        info "Cloning $GITHUB_URL → $install_dir"
        if [ -n "$SUDO" ]; then
            $SUDO git clone "$GITHUB_URL" "$install_dir"
            $SUDO chown -R "$USER:$(id -gn 2>/dev/null || echo "$USER")" "$install_dir" 2>/dev/null || true
        else
            git clone "$GITHUB_URL" "$install_dir"
        fi
    fi
    ok "Repository ready at $install_dir"

    cd "$subdir"

    # ── Port configuration ────────────────────────────────────────────────
    header "Port configuration"
    local public_port
    public_port=$(prompt_port "Public web port (HTTP access)")

    # ── Bind address ──────────────────────────────────────────────────────
    header "Network access"
    echo -e "  How should ChessLoop be accessible on this machine?"
    blank
    echo -e "  ${BOLD}${G}Option 1 — Localhost only${RST}  ${DIM}(recommended for internet-facing servers)${RST}"
    echo -e "  ${DIM}────────────────────────────────────────────────────${RST}"
    echo -e "  ChessLoop listens on ${BOLD}127.0.0.1${RST} (the loopback interface only)."
    echo -e "  It is ${BOLD}not directly reachable${RST} from any other machine."
    echo -e "  You put a reverse proxy (Caddy, Nginx, Cloudflare Tunnel, Tailscale"
    echo -e "  Funnel) in front — it handles HTTPS/SSL and forwards traffic to"
    echo -e "  localhost:${public_port}."
    blank
    echo -e "    ${G}+${RST} Passwords are never sent in plain text (SSL from the proxy)"
    echo -e "    ${G}+${RST} The app is not directly exposed to port scanners or the internet"
    echo -e "    ${G}+${RST} Required if you plan to use a domain name with a real SSL cert"
    echo -e "    ${Y}–${RST} Requires one extra step: install Caddy or configure your proxy"
    blank
    echo -e "    ${DIM}Best for: VPS/cloud servers, anyone with a domain name${RST}"
    blank
    echo -e "  ${BOLD}${Y}Option 2 — All interfaces${RST}  ${DIM}(simplest for home/LAN use)${RST}"
    echo -e "  ${DIM}────────────────────────────────────────────────────${RST}"
    echo -e "  ChessLoop listens on ${BOLD}0.0.0.0${RST} (every network interface)."
    echo -e "  Any device on your network (or the internet, if your firewall"
    echo -e "  allows it) can reach ChessLoop directly at http://IP:${public_port}."
    blank
    echo -e "    ${G}+${RST} No extra software needed — works immediately after install"
    echo -e "    ${G}+${RST} Easy for home network or LAN use"
    echo -e "    ${R}–${RST} HTTP only — passwords travel in plain text over the network"
    echo -e "    ${R}–${RST} ChessLoop is directly exposed; relies on your firewall for protection"
    echo -e "    ${Y}–${RST} Not recommended if this server is reachable from the internet"
    blank
    echo -e "    ${DIM}Best for: Raspberry Pi, home server, LAN-only access${RST}"
    blank
    sep
    blank
    echo -e "  ${BOLD}Which would you like?${RST}"
    echo -e "    ${BOLD}1)${RST}  ${G}Localhost only${RST}  ${DIM}(recommended — add a proxy for SSL later)${RST}"
    echo -e "    ${BOLD}2)${RST}  ${Y}All interfaces${RST}  ${DIM}(direct HTTP access, home/LAN)${RST}"
    blank
    local bind_choice
    _read -rp "  Choice [1/2, default 1]: " bind_choice
    local bind_addr
    case "${bind_choice:-1}" in
        2)
            bind_addr="0.0.0.0"
            blank
            warn "All-interfaces mode selected."
            warn "ChessLoop will be reachable at http://$(hostname -I | awk '{print $1}'):${public_port}"
            warn "Traffic is unencrypted (HTTP). Do not use over untrusted networks."
            warn "To add HTTPS later, switch to localhost mode and add Caddy or Nginx."
            ;;
        *)
            bind_addr="127.0.0.1"
            blank
            ok "Localhost-only mode selected."
            info "ChessLoop will only be reachable from this machine directly."
            info "To access it from other devices, add a reverse proxy."
            info "Quickest option: install Caddy and point it at localhost:${public_port}"
            ;;
    esac
    blank
    ok "Will bind to ${bind_addr}:${public_port}"

    # ── CORS origins ──────────────────────────────────────────────────────
    blank
    local domain
    _read -rp "  ${BOLD}Domain name${RST} (e.g. chess.example.com — leave blank for localhost/IP only): " domain
    domain="${domain:-}"

    local cors_origins
    if [ -n "$domain" ]; then
        cors_origins="https://$domain,http://$domain,http://localhost:$public_port"
    else
        cors_origins="*"
    fi

    # ── JWT secret ────────────────────────────────────────────────────────
    local jwt_secret
    if command -v openssl &>/dev/null; then
        jwt_secret=$(openssl rand -base64 32)
    else
        jwt_secret=$(head -c 48 /dev/urandom | base64 | tr -d '\n/+=' | cut -c1-43)
    fi

    # ── Write .env ────────────────────────────────────────────────────────
    header "Writing configuration"
    local env_file="$subdir/.env"
    {
        echo "# ChessLoop configuration"
        echo "# Generated: $(date)"
        echo ""
        echo "# Port the web UI listens on"
        echo "PUBLIC_PORT=$public_port"
        echo ""
        echo "# Bind address: 127.0.0.1 (localhost only) or 0.0.0.0 (all interfaces)"
        echo "BIND_ADDR=$bind_addr"
        echo ""
        echo "# JWT signing secret — keep private"
        echo "JWT_SECRET=$jwt_secret"
        echo ""
        if [ -n "$domain" ]; then
            echo "# Domain name for SSL/CORS"
            echo "DOMAIN=$domain"
            echo ""
        fi
        echo "# CORS allowed origins"
        echo "CORS_ORIGINS=$cors_origins"
    } > "$env_file"
    ok "Config written to $env_file"

    # ── Build & start ─────────────────────────────────────────────────────
    header "Building and starting containers"
    info "First build can take 3-10 minutes — downloading and compiling…"
    blank
    $DOCKER_CMD compose -f docker-compose.prod.yml up -d --build
    ok "Containers started."

    # ── Health check ──────────────────────────────────────────────────────
    header "Verifying health"
    health_check "$public_port" "$subdir" || true

    # ── Systemd ───────────────────────────────────────────────────────────
    blank
    local sysd
    _read -rp "  Enable autostart on boot (recommended)? [Y/n]: " sysd
    if [[ "${sysd:-y}" =~ ^[Yy]$ ]]; then
        setup_systemd "$subdir"
    fi

    print_summary "$public_port" "$install_dir" "$subdir"
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
    local backup_name="backup-pre-update-$(date +%Y%m%d-%H%M%S).tar.gz"
    if $DOCKER_CMD volume ls --format '{{.Name}}' 2>/dev/null | grep -q 'chessloop-data'; then
        info "Snapshotting chessloop-data volume → $install_dir/$backup_name"
        $DOCKER_CMD run --rm \
            -v chessloop-data:/src \
            -v "$install_dir":/out \
            alpine tar czf "/out/$backup_name" -C /src . 2>/dev/null && \
            ok "Backup saved: $install_dir/$backup_name" || \
            warn "Backup failed — continuing. Manually back up if you have important data."
    else
        warn "chessloop-data volume not found — skipping backup."
    fi

    # ── Git pull ──────────────────────────────────────────────────────────
    header "Pulling latest code"
    cd "$install_dir"

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
    cd "$subdir"
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
            $DOCKER_CMD compose -f docker-compose.prod.yml down 2>/dev/null && \
                ok "Containers stopped and removed." || \
                warn "docker compose down failed (containers may already be stopped)."
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
                $DOCKER_CMD rmi "$img" 2>/dev/null && ok "Removed image: $img" || \
                    warn "Could not remove image $img (may be in use)"
            fi
        done
    fi

    # ── Remove data volume ────────────────────────────────────────────────
    if [ "$level" -ge 3 ] && command -v docker &>/dev/null; then
        header "Removing data volume"
        if $DOCKER_CMD volume ls --format '{{.Name}}' 2>/dev/null | grep -q 'chessloop-data'; then
            $DOCKER_CMD volume rm chessloop-data 2>/dev/null && \
                ok "Removed volume: chessloop-data" || \
                warn "Could not remove volume. Try: sudo docker volume rm chessloop-data"
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
#  MAIN MENU
# ═══════════════════════════════════════════════════════════════════════════
print_banner() {
    clear
    echo ""
    echo -e "  ${C}${BOLD}╔═══════════════════════════════════════════════════════╗${RST}"
    echo -e "  ${C}${BOLD}║              ♞  ChessLoop  Deployer  v2              ║${RST}"
    echo -e "  ${C}${BOLD}╚═══════════════════════════════════════════════════════╝${RST}"
    echo ""
}

main_menu() {
    print_banner

    # Show install status
    local install_dir
    install_dir=$(find_install_dir)
    if [ -n "$install_dir" ]; then
        echo -e "  ${G}${BOLD}Existing install detected:${RST} $install_dir"
        # Show running state if docker available
        if command -v docker &>/dev/null; then
            local running
            running=$(docker ps --filter 'name=chessloop' --format '{{.Names}}' 2>/dev/null | wc -l || true)
            if [ "$running" -gt 0 ]; then
                echo -e "  ${G}●${RST} ${running} container(s) running"
            else
                echo -e "  ${R}●${RST} containers not running"
            fi
        fi
    else
        echo -e "  ${DIM}No existing install detected.${RST}"
    fi

    blank
    sep
    blank
    echo -e "  ${BOLD}What would you like to do?${RST}"
    blank
    echo -e "    ${BOLD}1)${RST}  ${G}Install${RST}    — Fresh install on this machine"
    echo -e "    ${BOLD}2)${RST}  ${C}Update${RST}     — Pull latest from GitHub, rebuild (data preserved)"
    echo -e "    ${BOLD}3)${RST}  ${R}Uninstall${RST}  — Remove ChessLoop (selective or full wipe)"
    echo -e "    ${BOLD}4)${RST}  ${DIM}Exit${RST}"
    blank
    sep
    blank

    local choice
    _read -rp "  Choice [1-4]: " choice
    blank

    case "${choice:-4}" in
        1) do_install ;;
        2) do_update ;;
        3) do_uninstall ;;
        4|q|Q|"")
            echo -e "  ${DIM}Goodbye.${RST}"
            blank
            exit 0
            ;;
        *)
            warn "Invalid choice '${choice}'. Please enter 1–4."
            sleep 1
            main_menu
            ;;
    esac
}

# ── Entry point ───────────────────────────────────────────────────────────
main_menu
