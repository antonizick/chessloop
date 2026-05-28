#!/usr/bin/env bash
# ChessLoop service manager — interactive menu
# Run with:  ./manage.sh
# ──────────────────────────────────────────────────────────────────────────────
# Updated for Docker Compose setup

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CHESSLOOP_DIR="$SCRIPT_DIR/chessloop"

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
    docker run -d \
      --name chessloop-backend \
      --network "$NETWORK" \
      -v chessloop-data:/data \
      -e "CHESSLOOP_DB_PATH=/data/chessloop.db" \
      -e "CHESSLOOP_JWT_SECRET=${JWT_SECRET:-***REMOVED-COMPROMISED-JWT-SECRET***}" \
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
    docker run -d \
      --name chessloop-frontend \
      --network "$NETWORK" \
      chessloop-frontend:latest >/dev/null 2>&1 && echo -e "  ${GREEN}●${RESET} Frontend up" || echo -e "  ${RED}●${RESET} Frontend failed"
  fi

  # Nginx
  if container_running "chessloop-nginx"; then
    echo -e "  Nginx already running"
  else
    echo -e "  ${YELLOW}Starting${RESET} nginx…"
    docker run -d \
      --name chessloop-nginx \
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
  echo -e "    ${BOLD}5)${RESET}  View backend logs  (Ctrl-C to return)"
  echo -e "    ${BOLD}6)${RESET}  View frontend logs"
  echo -e "    ${BOLD}7)${RESET}  View nginx logs"
  echo -e "    ${BOLD}8)${RESET}  Exit"
  echo ""
}

run_menu() {
  while true; do
    draw_menu
    read -rp "  Enter choice [1-8]: " choice
    echo ""
    case "$choice" in
      1)  : ;; # just redraw
      2)  do_start; echo ""; read -rp "  Press Enter to continue…" ;;
      3)  do_stop;  echo ""; read -rp "  Press Enter to continue…" ;;
      4)  do_stop; do_start; echo ""; read -rp "  Press Enter to continue…" ;;
      5)
        echo -e "  ${DIM}Backend logs — press Ctrl-C to return${RESET}"
        trap 'echo ""' INT
        docker logs -f chessloop-backend 2>/dev/null || echo "  (backend not running)"
        trap - INT
        ;;
      6)
        echo -e "  ${DIM}Frontend logs — press Ctrl-C to return${RESET}"
        trap 'echo ""' INT
        docker logs -f chessloop-frontend 2>/dev/null || echo "  (frontend not running)"
        trap - INT
        ;;
      7)
        echo -e "  ${DIM}Nginx logs — press Ctrl-C to return${RESET}"
        trap 'echo ""' INT
        docker logs -f chessloop-nginx 2>/dev/null || echo "  (nginx not running)"
        trap - INT
        ;;
      8|q|Q)
        echo -e "  ${DIM}Goodbye.${RESET}"
        echo ""
        exit 0
        ;;
      *)
        echo -e "  ${RED}Invalid choice '$choice' — enter 1-8${RESET}"
        sleep 1
        ;;
    esac
  done
}

run_menu
