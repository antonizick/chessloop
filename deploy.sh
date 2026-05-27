#!/bin/bash
set -e

# ChessLoop — One-command deploy script for Linux (Ubuntu/Debian)
# Usage: curl -fsSL https://raw.githubusercontent.com/antonizick/chessloop/main/deploy.sh | bash

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║  ChessLoop — Installation & Update                            ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo

# ─── Configuration ───────────────────────────────────────────────────

GITHUB_URL="https://github.com/antonizick/chessloop"
INSTALL_DIR="${CHESSLOOP_DIR:-/opt/chessloop}"
CHESSLOOP_SUBDIR="$INSTALL_DIR/chessloop"
SYSTEMD_SERVICE="/etc/systemd/system/chessloop.service"

# ─── Step 1: Check / Install Prerequisites ────────────────────────

echo "→ Checking prerequisites…"

if ! command -v git &> /dev/null; then
    echo "  Installing git…"
    sudo apt-get update && sudo apt-get install -y git
fi

if ! command -v docker &> /dev/null; then
    echo "  Installing Docker…"
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    sudo bash /tmp/get-docker.sh
    rm /tmp/get-docker.sh
    sudo usermod -aG docker "$USER"
    echo "  ⚠️  User added to docker group; you may need to run 'newgrp docker' or log out/in"
fi

if ! docker compose version &> /dev/null; then
    echo "  Installing Docker Compose plugin…"
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

echo "  ✓ Prerequisites OK"
echo

# ─── Step 2: Clone or Update Repo ──────────────────────────────────

if [ -d "$INSTALL_DIR" ]; then
    echo "→ Updating ChessLoop from git…"
    cd "$INSTALL_DIR"
    git pull
else
    echo "→ Cloning ChessLoop repository…"
    git clone "$GITHUB_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

echo "  ✓ Repository ready at $INSTALL_DIR"
echo

# ─── Step 3: Configure .env ────────────────────────────────────────

ENV_FILE="$CHESSLOOP_SUBDIR/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "→ Creating .env configuration…"

    # Generate JWT_SECRET
    JWT_SECRET=$(openssl rand -base64 32)

    # Prompt for PUBLIC_PORT
    read -p "  Public port (default 8090): " PUBLIC_PORT
    PUBLIC_PORT="${PUBLIC_PORT:-8090}"

    # Prompt for DOMAIN
    read -p "  Domain name (optional, leave blank for localhost): " DOMAIN

    # Write .env
    {
        echo "# ChessLoop configuration"
        echo "PUBLIC_PORT=$PUBLIC_PORT"
        echo "JWT_SECRET=$JWT_SECRET"
        if [ -n "$DOMAIN" ]; then
            echo "DOMAIN=$DOMAIN"
        fi
    } > "$ENV_FILE"

    echo "  ✓ Configuration written to $ENV_FILE"
else
    echo "→ Using existing .env configuration"
fi

echo

# ─── Step 4: Build and Start Services ──────────────────────────────

echo "→ Building and starting ChessLoop…"
cd "$CHESSLOOP_SUBDIR"

docker compose -f docker-compose.prod.yml up -d --build

echo "  ✓ Services started"
echo

# ─── Step 5: Wait for Health Check ────────────────────────────────

echo "→ Waiting for ChessLoop to be healthy (max 60s)…"

PUBLIC_PORT=$(grep "PUBLIC_PORT" "$ENV_FILE" | cut -d= -f2)
PUBLIC_PORT="${PUBLIC_PORT:-8090}"

for i in {1..30}; do
    if curl -s "http://localhost:$PUBLIC_PORT/api/health" > /dev/null 2>&1; then
        echo "  ✓ ChessLoop is running and healthy"
        break
    fi
    echo "  Waiting… ($i/30)"
    sleep 2
done

if ! curl -s "http://localhost:$PUBLIC_PORT/api/health" > /dev/null 2>&1; then
    echo "  ⚠️  Health check failed. Check logs:"
    echo "     docker compose -f $CHESSLOOP_SUBDIR/docker-compose.prod.yml logs -f"
    exit 1
fi

echo

# ─── Step 6: Set up Systemd Autostart ──────────────────────────────

echo "→ Setting up autostart with systemd…"

SYSTEMD_CONTENT="[Unit]
Description=ChessLoop Chess Training System
After=docker.service
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=$CHESSLOOP_SUBDIR
ExecStart=$(command -v docker) compose -f docker-compose.prod.yml up
ExecStop=$(command -v docker) compose -f docker-compose.prod.yml down
Restart=always
RestartSec=10
User=$USER

[Install]
WantedBy=multi-user.target
"

echo "$SYSTEMD_CONTENT" | sudo tee "$SYSTEMD_SERVICE" > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable chessloop

echo "  ✓ Systemd service enabled (autostart on boot)"
echo

# ─── Step 7: Print Summary ────────────────────────────────────────

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║  ✓ ChessLoop deployment complete!                            ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo

SERVER_IP=$(hostname -I | awk '{print $1}')

echo "📍 Access ChessLoop:"
echo "   http://localhost:$PUBLIC_PORT"
echo "   http://$SERVER_IP:$PUBLIC_PORT"
echo

echo "🔐 First login:"
echo "   1. Navigate to http://$SERVER_IP:$PUBLIC_PORT"
echo "   2. Click 'Register' and create your account"
echo "   3. Promote to admin: run this command on the server:"
echo "      docker compose -f $CHESSLOOP_SUBDIR/docker-compose.prod.yml exec backend python -c"
echo "        \"from database import get_session; from models.user import User;"
echo "         s = next(get_session()); u = s.query(User).filter_by(username='YOUR_USERNAME').first();"
echo "         u.role='admin'; s.add(u); s.commit() if u else None\""
echo

echo "🛠️  Useful commands:"
echo "   Start:   systemctl start chessloop"
echo "   Stop:    systemctl stop chessloop"
echo "   Status:  systemctl status chessloop"
echo "   Logs:    docker compose -f $CHESSLOOP_SUBDIR/docker-compose.prod.yml logs -f"
echo "   Update:  cd $INSTALL_DIR && bash deploy.sh"
echo

echo "💾 Backups:"
echo "   Admin panel → Admin → Database backups"
echo "   Create, download, and restore backups from the admin UI"
echo

echo "✅ Done! ChessLoop is running with autostart enabled."
echo "   Reboot to verify autostart works."
echo
