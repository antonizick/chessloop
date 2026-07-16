#!/usr/bin/env bash
# ChessLoop service manager — interactive menu
# Run with:  ./manage.sh
# ──────────────────────────────────────────────────────────────────────────────
# Updated for Docker Compose setup

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CHESSLOOP_DIR="$SCRIPT_DIR/chessloop"

# JWT signing secret must be supplied via env — no hardcoded fallback.
# (A previous version of this script had a hardcoded default that was committed
# to a public repo; treat that value as permanently compromised.)
if [ -z "$JWT_SECRET" ]; then
  echo "ERROR: \$JWT_SECRET is not set. Generate one (e.g. openssl rand -base64 32)" >&2
  echo "and export it before running this script." >&2
  exit 1
fi

# Docker setup
PUBLIC_PORT=8090
NETWORK=chessloop-net

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; DIM='\033[2m'; BOLD='\033[1m'; RESET='\033[0m'

# ── Helpers ───────────────────────────────────────────────────────────────────

container_running() {
  docker ps --filter "name=$1" --format "{{.Status}}" 2>/dev/null | grep -q "Up"
}

container_exists() {
  docker ps -a --filter "name=$1" --format "{{.Names}}" 2>/dev/null | grep -q "^$1$"
}

get_running_image() {
  local container="$1"
  docker inspect "$container" --format "{{.Image}}" 2>/dev/null | sed 's/.*@sha256://' | cut -c1-12
}

get_latest_image_id() {
  local image="$1"
  docker inspect "$image:latest" --format "{{.ID}}" 2>/dev/null | sed 's/.*:sha256://' | cut -c1-12
}

check_image_versions() {
  local backend_running=$(get_running_image "chessloop-backend" 2>/dev/null)
  local backend_latest=$(get_latest_image_id "chessloop-backend" 2>/dev/null)
  local frontend_running=$(get_running_image "chessloop-frontend" 2>/dev/null)
  local frontend_latest=$(get_latest_image_id "chessloop-frontend" 2>/dev/null)

  echo ""
  echo -e "${DIM}Image versions:${RESET}"

  if [[ -n "$backend_running" && -n "$backend_latest" ]]; then
    if [[ "$backend_running" == "$backend_latest" ]]; then
      echo -e "  ${GREEN}✓${RESET} Backend is up to date"
    else
      echo -e "  ${YELLOW}⚠${RESET} Backend image is ${RED}outdated${RESET} — run option 5 to rebuild"
    fi
  else
    echo -e "  ${DIM}○${RESET} Backend image check unavailable"
  fi

  if [[ -n "$frontend_running" && -n "$frontend_latest" ]]; then
    if [[ "$frontend_running" == "$frontend_latest" ]]; then
      echo -e "  ${GREEN}✓${RESET} Frontend is up to date"
    else
      echo -e "  ${YELLOW}⚠${RESET} Frontend image is ${RED}outdated${RESET} — run option 5 to rebuild"
    fi
  else
    echo -e "  ${DIM}○${RESET} Frontend image check unavailable"
  fi
}

status_line() {
  local name="$1" container="$2"
  if container_running "$container"; then
    local status=$(docker ps --filter "name=$container" --format "{{.Status}}")
    echo -e "  ${GREEN}●${RESET} ${BOLD}$name${RESET}  ${DIM}$status${RESET}"
  else
    echo -e "  ${RED}●${RESET} ${BOLD}$name${RESET}  ${DIM}stopped${RESET}"
  fi
}

# ── Status ────────────────────────────────────────────────────────────────────

show_status() {
  echo ""
  echo -e "${CYAN}${BOLD}  ChessLoop — Docker service status${RESET}"
  echo    "  ──────────────────────────────────────"
  status_line "Backend  (FastAPI) " "chessloop-backend"
  status_line "Frontend (Nginx)   " "chessloop-frontend"
  status_line "Proxy    (Nginx)   " "chessloop-nginx"
  echo -e "  ${DIM}Web UI: http://localhost:$PUBLIC_PORT${RESET}"
  check_image_versions
  echo ""
}

# ── Stop ──────────────────────────────────────────────────────────────────────

stop_container() {
  local name="$1" container="$2"
  if ! container_running "$container"; then
    echo -e "  $name is not running"
    return
  fi
  echo -e "  ${YELLOW}Stopping${RESET} $name…"
  docker stop "$container" >/dev/null 2>&1
  echo -e "  ${RED}●${RESET} $name stopped"
}

do_stop() {
  echo ""
  echo -e "${CYAN}${BOLD}  Stopping services…${RESET}"
  stop_container "Backend"  "chessloop-backend"
  stop_container "Frontend" "chessloop-frontend"
  stop_container "Nginx"    "chessloop-nginx"
  echo ""
}

# ── Start ─────────────────────────────────────────────────────────────────────

start_containers() {
  echo ""
  echo -e "${CYAN}${BOLD}  Starting services…${RESET}"

  # Load environment variables
  if [[ -f "$CHESSLOOP_DIR/.env" ]]; then
    set -a
    source "$CHESSLOOP_DIR/.env"
    set +a
  fi

  # Create network if it doesn't exist
  docker network create "$NETWORK" 2>/dev/null || true

  # Backend
  if container_running "chessloop-backend"; then
    echo -e "  Backend already running"
  else
    echo -e "  ${YELLOW}Starting${RESET} backend…"
    # Remove existing stopped container if it exists
    docker rm -f chessloop-backend >/dev/null 2>&1 || true
    docker run -d \
      --name chessloop-backend \
      --restart always \
      --network "$NETWORK" \
      -v "$CHESSLOOP_DIR/data:/data" \
      -e "CHESSLOOP_DB_PATH=/data/chessloop.db" \
      -e "CHESSLOOP_JWT_SECRET=${JWT_SECRET}" \
      -e "CHESSLOOP_ACCESS_TTL_MIN=15" \
      -e "CHESSLOOP_REFRESH_TTL_DAYS=30" \
      -e "CHESSLOOP_CORS_ORIGINS=${CORS_ORIGINS:-*}" \
      chessloop-backend:latest >/dev/null 2>&1 && echo -e "  ${GREEN}●${RESET} Backend up" || echo -e "  ${RED}●${RESET} Backend failed"
  fi

  # Frontend
  if container_running "chessloop-frontend"; then
    echo -e "  Frontend already running"
  else
    echo -e "  ${YELLOW}Starting${RESET} frontend…"
    # Remove existing stopped container if it exists
    docker rm -f chessloop-frontend >/dev/null 2>&1 || true
    docker run -d \
      --name chessloop-frontend \
      --restart always \
      --network "$NETWORK" \
      chessloop-frontend:latest >/dev/null 2>&1 && echo -e "  ${GREEN}●${RESET} Frontend up" || echo -e "  ${RED}●${RESET} Frontend failed"
  fi

  # Nginx
  if container_running "chessloop-nginx"; then
    echo -e "  Nginx already running"
  else
    echo -e "  ${YELLOW}Starting${RESET} nginx…"
    # Remove existing stopped container if it exists
    docker rm -f chessloop-nginx >/dev/null 2>&1 || true
    docker run -d \
      --name chessloop-nginx \
      --restart always \
      --network "$NETWORK" \
      --link chessloop-backend:backend \
      --link chessloop-frontend:frontend \
      -p "$PUBLIC_PORT:80" \
      -v "$CHESSLOOP_DIR/nginx/default.conf:/etc/nginx/conf.d/default.conf:ro" \
      nginx:alpine >/dev/null 2>&1 && echo -e "  ${GREEN}●${RESET} Nginx up" || echo -e "  ${RED}●${RESET} Nginx failed"
  fi

  echo ""
  echo -e "  ${GREEN}${BOLD}Ready!${RESET}  → http://localhost:$PUBLIC_PORT"
  echo ""
}

do_start() {
  start_containers
}

# ── Rebuild ───────────────────────────────────────────────────────────────────

do_rebuild() {
  echo ""
  echo -e "${CYAN}${BOLD}  Rebuilding Docker images…${RESET}"
  echo ""

  # Stop services first
  if container_running "chessloop-backend" || container_running "chessloop-frontend" || container_running "chessloop-nginx"; then
    echo -e "  ${YELLOW}Stopping services…${RESET}"
    do_stop
  fi

  # Rebuild backend
  echo -e "  ${YELLOW}Building${RESET} backend…"
  if (cd "$CHESSLOOP_DIR/backend" && docker build --no-cache -t chessloop-backend:latest . >/dev/null 2>&1); then
    echo -e "  ${GREEN}●${RESET} Backend built and tagged as :latest"
  else
    echo -e "  ${RED}●${RESET} Backend build failed"
    return 1
  fi

  # Rebuild frontend
  echo -e "  ${YELLOW}Building${RESET} frontend…"
  if (cd "$CHESSLOOP_DIR/frontend" && docker build --no-cache -t chessloop-frontend:latest . >/dev/null 2>&1); then
    echo -e "  ${GREEN}●${RESET} Frontend built and tagged as :latest"
  else
    echo -e "  ${RED}●${RESET} Frontend build failed"
    return 1
  fi

  echo ""
  echo -e "  ${YELLOW}Starting services…${RESET}"
  start_containers
  echo -e "  ${GREEN}${BOLD}Rebuild complete!${RESET}"
  echo ""
}

# ── Menu ──────────────────────────────────────────────────────────────────────

draw_menu() {
  clear
  echo ""
  echo -e "  ${CYAN}${BOLD}╔══════════════════════════════════════╗${RESET}"
  echo -e "  ${CYAN}${BOLD}║       ChessLoop  Service Manager     ║${RESET}"
  echo -e "  ${CYAN}${BOLD}╚══════════════════════════════════════╝${RESET}"
  show_status
  echo -e "  ${BOLD}What would you like to do?${RESET}"
  echo ""
  echo -e "    ${BOLD}1)${RESET}  Refresh status"
  echo -e "    ${BOLD}2)${RESET}  Start services"
  echo -e "    ${BOLD}3)${RESET}  Stop services"
  echo -e "    ${BOLD}4)${RESET}  Restart services  (stop → start)"
  echo -e "    ${BOLD}5)${RESET}  Rebuild & restart  (rebuild images, auto-tags :latest)"
  echo -e "    ${BOLD}6)${RESET}  View backend logs  (Ctrl-C to return)"
  echo -e "    ${BOLD}7)${RESET}  View frontend logs"
  echo -e "    ${BOLD}8)${RESET}  View nginx logs"
  echo -e "    ${BOLD}9)${RESET}  Exit"
  echo ""
}

run_menu() {
  while true; do
    draw_menu
    read -rp "  Enter choice [1-9]: " choice
    echo ""
    case "$choice" in
      1)  : ;; # just redraw
      2)  do_start; echo ""; read -rp "  Press Enter to continue…" ;;
      3)  do_stop;  echo ""; read -rp "  Press Enter to continue…" ;;
      4)  do_stop; do_start; echo ""; read -rp "  Press Enter to continue…" ;;
      5)  do_rebuild; read -rp "  Press Enter to continue…" ;;
      6)
        echo -e "  ${DIM}Backend logs — press Ctrl-C to return${RESET}"
        trap 'echo ""' INT
        docker logs -f chessloop-backend 2>/dev/null || echo "  (backend not running)"
        trap - INT
        ;;
      7)
        echo -e "  ${DIM}Frontend logs — press Ctrl-C to return${RESET}"
        trap 'echo ""' INT
        docker logs -f chessloop-frontend 2>/dev/null || echo "  (frontend not running)"
        trap - INT
        ;;
      8)
        echo -e "  ${DIM}Nginx logs — press Ctrl-C to return${RESET}"
        trap 'echo ""' INT
        docker logs -f chessloop-nginx 2>/dev/null || echo "  (nginx not running)"
        trap - INT
        ;;
      9|q|Q)
        echo -e "  ${DIM}Goodbye.${RESET}"
        echo ""
        exit 0
        ;;
      *)
        echo -e "  ${RED}Invalid choice '$choice' — enter 1-9${RESET}"
        sleep 1
        ;;
    esac
  done
}

run_menu
