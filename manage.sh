#!/usr/bin/env bash
# ChessLoop service manager — interactive menu
# Run with:  ./manage.sh
# ──────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/chessloop/backend"
FRONTEND_DIR="$SCRIPT_DIR/chessloop/frontend"

BACKEND_PORT=8100
FRONTEND_PORT=8090
BACKEND_LOG=/tmp/chessloop-backend.log
FRONTEND_LOG=/tmp/chessloop-frontend.log

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; DIM='\033[2m'; BOLD='\033[1m'; RESET='\033[0m'

# ── Helpers ───────────────────────────────────────────────────────────────────

pid_on_port() {
  ss -tlnp 2>/dev/null | awk -v p=":$1" '$4 ~ p {
    match($0, /pid=([0-9]+)/, a); if (a[1]) print a[1]
  }' | head -1
}

svc_running() { pid_on_port "$1" | grep -q .; }

status_line() {
  local name="$1" port="$2"
  local pid; pid=$(pid_on_port "$port")
  if [[ -n "$pid" ]]; then
    echo -e "  ${GREEN}●${RESET} ${BOLD}$name${RESET}  pid $pid  :$port"
  else
    echo -e "  ${RED}●${RESET} ${BOLD}$name${RESET}  ${DIM}stopped${RESET}"
  fi
}

# ── Status ────────────────────────────────────────────────────────────────────

show_status() {
  echo ""
  echo -e "${CYAN}${BOLD}  ChessLoop — service status${RESET}"
  echo    "  ──────────────────────────────────────"
  status_line "Backend  (FastAPI :$BACKEND_PORT) " "$BACKEND_PORT"
  status_line "Frontend (Vite    :$FRONTEND_PORT)" "$FRONTEND_PORT"
  echo ""
}

# ── Stop ──────────────────────────────────────────────────────────────────────

stop_svc() {
  local name="$1" port="$2"
  local pid; pid=$(pid_on_port "$port")
  if [[ -z "$pid" ]]; then
    echo -e "  $name is not running"
    return
  fi
  echo -e "  ${YELLOW}Stopping${RESET} $name (pid $pid)…"
  kill -TERM "$pid" 2>/dev/null || true
  local deadline=$(( SECONDS + 6 ))
  while kill -0 "$pid" 2>/dev/null && [[ $SECONDS -lt $deadline ]]; do sleep 0.3; done
  kill -9 "$pid" 2>/dev/null || true
  echo -e "  ${RED}●${RESET} $name stopped"
}

do_stop() {
  echo ""
  echo -e "${CYAN}${BOLD}  Stopping services…${RESET}"
  stop_svc "Backend"  "$BACKEND_PORT"
  stop_svc "Frontend" "$FRONTEND_PORT"
}

# ── Start ─────────────────────────────────────────────────────────────────────

start_backend() {
  if svc_running "$BACKEND_PORT"; then
    echo -e "  Backend already running on :$BACKEND_PORT"
    return
  fi
  echo -e "  ${YELLOW}Starting${RESET} backend…"
  (
    cd "$BACKEND_DIR"
    source .venv/bin/activate
    CHESSLOOP_DB_PATH="$BACKEND_DIR/chessloop.db" \
    CHESSLOOP_JWT_SECRET="***REMOVED-COMPROMISED-JWT-SECRET***" \
    CHESSLOOP_CORS_ORIGINS="http://localhost:$FRONTEND_PORT" \
    exec uvicorn main:app --host 0.0.0.0 --port "$BACKEND_PORT" \
      >> "$BACKEND_LOG" 2>&1
  ) &
  local deadline=$(( SECONDS + 10 ))
  while ! svc_running "$BACKEND_PORT" && [[ $SECONDS -lt $deadline ]]; do sleep 0.3; done
  svc_running "$BACKEND_PORT" \
    && echo -e "  ${GREEN}●${RESET} Backend up  (log: $BACKEND_LOG)" \
    || echo -e "  ${RED}Backend failed to start — check $BACKEND_LOG${RESET}"
}

start_frontend() {
  if svc_running "$FRONTEND_PORT"; then
    echo -e "  Frontend already running on :$FRONTEND_PORT"
    return
  fi
  echo -e "  ${YELLOW}Starting${RESET} frontend…"
  (
    cd "$FRONTEND_DIR"
    exec npm run dev -- --port "$FRONTEND_PORT" --host 0.0.0.0 >> "$FRONTEND_LOG" 2>&1
  ) &
  local deadline=$(( SECONDS + 20 ))
  while ! svc_running "$FRONTEND_PORT" && [[ $SECONDS -lt $deadline ]]; do sleep 0.5; done
  svc_running "$FRONTEND_PORT" \
    && echo -e "  ${GREEN}●${RESET} Frontend up (log: $FRONTEND_LOG)" \
    || echo -e "  ${RED}Frontend failed to start — check $FRONTEND_LOG${RESET}"
}

do_start() {
  echo ""
  echo -e "${CYAN}${BOLD}  Starting services…${RESET}"
  start_backend
  start_frontend
  echo ""
  echo -e "  ${GREEN}${BOLD}Ready!${RESET}  → http://localhost:$FRONTEND_PORT"
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
  echo -e "    ${BOLD}5)${RESET}  View logs  (both, live — Ctrl-C to return)"
  echo -e "    ${BOLD}6)${RESET}  View backend log"
  echo -e "    ${BOLD}7)${RESET}  View frontend log"
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
        echo -e "  ${DIM}Tailing both logs — press Ctrl-C to return to menu${RESET}"
        trap 'echo ""' INT
        tail -f "$BACKEND_LOG" "$FRONTEND_LOG" 2>/dev/null || echo "  (no logs yet — start the services first)"
        trap - INT
        ;;
      6)
        echo -e "  ${DIM}Backend log — Ctrl-C to return${RESET}"
        trap 'echo ""' INT
        tail -f "$BACKEND_LOG" 2>/dev/null || echo "  (no backend log yet)"
        trap - INT
        ;;
      7)
        echo -e "  ${DIM}Frontend log — Ctrl-C to return${RESET}"
        trap 'echo ""' INT
        tail -f "$FRONTEND_LOG" 2>/dev/null || echo "  (no frontend log yet)"
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
