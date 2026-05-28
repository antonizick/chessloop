# ChessLoop

Self-hosted, move-based spaced-repetition chess opening trainer.

Teach it your repertoire by playing moves. It drills you back, corrects mistakes, and schedules review so the positions that break you get more practice.

---

## Deploy to a new machine

One command on any Ubuntu, Debian, RHEL, or Arch Linux machine:

```bash
curl -fsSL https://raw.githubusercontent.com/antonizick/chessloop/main/deploy.sh | bash
```

Or if you already have the repo:

```bash
bash deploy.sh
```

The script opens an interactive menu:

```
  ╔═══════════════════════════════════════════════════════╗
  ║              ♞  ChessLoop  Deployer  v2              ║
  ╚═══════════════════════════════════════════════════════╝

  1) Install    — Fresh install on this machine
  2) Update     — Pull latest from GitHub (keeps your data)
  3) Uninstall  — Remove ChessLoop (selective or full wipe)
  4) Exit
```

---

## Install walkthrough

The install flow guides you through every decision:

### 1. Install directory

Default: `/opt/chessloop`. You can pick any path you have access to.

### 2. Dependencies

The script detects your Linux distribution and auto-installs whatever is missing: `git`, `curl`, `openssl`, Docker, and Docker Compose. You will be prompted for your sudo password if needed.

### 3. Port

The script scans all ports currently in use and suggests the first free port at or above the default (8090). You can accept the suggestion or type any port from 1–65535.

```
  Scanning listening ports…
    In use: 22 80 443 3306 8080
  ✓ Port 8090 is free.

  Public web port [default: 8090]: _
```

### 4. Network access (bind address)

This is the most consequential choice. The script explains both options in full before asking:

---

**Option 1 — Localhost only** *(recommended for internet-facing servers)*

ChessLoop listens on `127.0.0.1` only. It cannot be reached directly from any other machine. You add a reverse proxy (Caddy, Nginx, Cloudflare Tunnel, Tailscale Funnel) in front, which handles HTTPS and forwards requests to `localhost:8090`.

- Passwords are never sent in plain text (SSL from the proxy)
- The app is not directly exposed to port scanners or the internet
- Required if you plan to use a domain name with a real SSL cert
- One extra step: install your proxy of choice

*Best for: VPS/cloud servers, anyone with a domain name*

---

**Option 2 — All interfaces** *(simplest for home/LAN use)*

ChessLoop listens on `0.0.0.0`. Any device on your network — or the internet if your firewall allows it — can reach ChessLoop directly at `http://YOUR-IP:8090`.

- No extra software needed, works immediately after install
- HTTP only — passwords travel in plain text over the network
- Not recommended if this server is reachable from the internet

*Best for: Raspberry Pi, home server, LAN-only access*

---

### 5. Domain name (optional)

If you have a domain (e.g. `chess.example.com`), enter it here. The script will configure CORS to accept requests from that origin. Leave blank for IP-only access.

### 6. Build and start

Docker builds the backend and frontend containers. This takes 3–10 minutes on a fresh machine. After the build, all three services start automatically (backend, frontend, nginx reverse proxy).

### 7. Health check

The script polls `http://localhost:PORT/api/health` every 2 seconds for up to 90 seconds. You see progress in the terminal.

### 8. Autostart (optional)

Prompts to install a systemd service so ChessLoop restarts automatically on reboot. Recommended for any server that needs to stay up.

---

## After install

### Access

```
http://localhost:PORT
http://YOUR-SERVER-IP:PORT
```

### First login

The deploy script creates a default admin account automatically:

| Field | Value |
|---|---|
| Username | `admin` |
| Password | `admin` |

> **⚠ Change the default password immediately** — go to **Settings → Account** before sharing the URL with anyone.

The admin account has full access to the Admin panel (⚙ icon in the sidebar), where you can manage users, create/download backups, and import openings from the Lichess database.

### Service management

```bash
systemctl start   chessloop
systemctl stop    chessloop
systemctl restart chessloop
systemctl status  chessloop

# Logs:
docker compose -f /opt/chessloop/chessloop/docker-compose.prod.yml logs -f
```

---

## Update (pull new code, keep your data)

Run the deploy script again and choose **Update**:

```bash
bash /opt/chessloop/deploy.sh
# → choose 2) Update
```

What happens:
1. The script creates a timestamped snapshot of your Docker volume before touching anything
2. `git pull` downloads the latest commits from the main branch
3. If you're already up to date you can still force a rebuild
4. `docker compose up -d --build --remove-orphans` rebuilds the containers
5. Your database (user accounts, libraries, SRS progress) lives in the `chessloop-data` Docker volume and is **never removed** by the update process
6. Health check confirms the new version is running

---

## Uninstall

Run the deploy script and choose **Uninstall**. Three levels:

| Level | What is removed |
|---|---|
| **1 — Containers only** | Stops and removes running containers. Images and all data stay on disk. |
| **2 — Containers + images** | Removes containers and the Docker images. The database volume and files remain. |
| **3 — Full wipe** | Removes everything: containers, images, database, files, systemd service. Requires typing `DELETE` then `YES`. |

Levels 1 and 2 are reversible — you can reinstall and your data will still be there. Level 3 is permanent.

---

## Adding HTTPS (after localhost-only install)

### Caddy (easiest — auto-renews certs)

```bash
# Install Caddy
curl -fsSL https://caddyserver.com/get | bash

# /etc/caddy/Caddyfile
chess.yourdomain.com {
    reverse_proxy localhost:8090
}

systemctl enable --now caddy
```

### Cloudflare Tunnel (no open ports needed)

1. Install `cloudflared` on the server
2. `cloudflared tunnel create chessloop`
3. Configure the tunnel to forward `chess.yourdomain.com` → `http://localhost:8090`
4. Cloudflare handles SSL automatically

### Nginx on the host

```nginx
server {
    listen 443 ssl;
    server_name chess.yourdomain.com;
    ssl_certificate     /etc/letsencrypt/live/chess.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/chess.yourdomain.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://127.0.0.1:8090;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 80;
    server_name chess.yourdomain.com;
    return 301 https://$host$request_uri;
}
```

### Tailscale Funnel (access from anywhere on your Tailnet)

```bash
tailscale funnel 8090
```

---

## Manual Docker setup (without the deploy script)

```bash
git clone https://github.com/antonizick/chessloop /opt/chessloop
cd /opt/chessloop/chessloop

# Configure
cp .env.example .env
# Edit .env:
#   PUBLIC_PORT=8090
#   BIND_ADDR=127.0.0.1        # or 0.0.0.0 for direct access
#   JWT_SECRET=$(openssl rand -base64 32)
#   DOMAIN=chess.example.com   # optional

# Build and start
docker compose -f docker-compose.prod.yml up -d --build

# Check status
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f
```

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `JWT_SECRET` | **yes** | — | Long random string. Generate: `openssl rand -base64 32` |
| `PUBLIC_PORT` | no | `8090` | Host port the web UI listens on |
| `BIND_ADDR` | no | `127.0.0.1` | `127.0.0.1` (localhost only) or `0.0.0.0` (all interfaces) |
| `DOMAIN` | no | `localhost` | Your public domain — used to scope CORS origins |
| `CORS_ORIGINS` | no | auto | Explicit CORS allow-list (overrides the DOMAIN-derived value) |
| `ACCESS_TTL_MIN` | no | `15` | JWT access token lifetime in minutes |
| `REFRESH_TTL_DAYS` | no | `30` | JWT refresh token lifetime in days |

---

## Backups

### From the Admin panel

Admin → Backups tab. Create named backups on demand, download them to your computer, and restore from any backup without downtime.

Three backup types:

| Type | Contents |
|---|---|
| `full` | Entire database: users, libraries, lines, SRS progress |
| `content` | Libraries and lines only (portable to another instance) |
| `progress` | SRS cards and review log only |

### Docker volume snapshot

```bash
docker run --rm \
  -v chessloop-data:/src \
  -v $(pwd):/out \
  alpine tar czf /out/chessloop-$(date +%F).tar.gz -C /src .
```

### Restore from snapshot

```bash
# Stop services first
docker compose -f /opt/chessloop/chessloop/docker-compose.prod.yml down

# Restore the volume
docker run --rm \
  -v chessloop-data:/dst \
  -v $(pwd):/src \
  alpine tar xzf /src/chessloop-YYYY-MM-DD.tar.gz -C /dst

# Restart
docker compose -f /opt/chessloop/chessloop/docker-compose.prod.yml up -d
```

---

## Seed starter libraries

Populate the instance with 16 curated opening libraries and publish them to Public Discovery:

```bash
# Against a running Docker install:
docker compose -f /opt/chessloop/chessloop/docker-compose.prod.yml \
  exec backend python seeds/seed_libraries.py --url http://localhost:8000

# Against the dev server:
cd chessloop/backend && python seeds/seed_libraries.py
```

---

## Development setup

### Backend

```bash
cd chessloop/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
CHESSLOOP_JWT_SECRET=dev-secret uvicorn main:app --reload --port 8100
# OpenAPI docs: http://localhost:8100/docs
```

### Frontend

```bash
cd chessloop/frontend
npm install
npm run dev   # http://localhost:8090
# Vite proxies /api/* → http://localhost:8100
```

---

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, SQLModel, SQLite (WAL) |
| Auth | python-jose (JWT), passlib (bcrypt), pyotp (TOTP MFA) |
| Frontend | React 18, Vite, TypeScript, Chessground, chess.js, TailwindCSS |
| State | Zustand (auth), TanStack Query (server data) |
| Infrastructure | Docker Compose, Nginx (reverse proxy inside container) |

---

## Project layout

```
ChessLoop/
├── deploy.sh                  ← interactive deploy/update/uninstall script
└── chessloop/
    ├── .env.example
    ├── docker-compose.yml     ← development
    ├── docker-compose.prod.yml← production (health checks, bind address)
    ├── backend/
    │   ├── main.py            ← FastAPI app factory
    │   ├── models/            ← SQLModel table classes
    │   ├── routers/           ← auth, libraries, lines, practice, stats, public, admin
    │   ├── services/          ← SRS engine, backup, practice session
    │   └── seeds/             ← seed_libraries.py (16 starter openings)
    ├── frontend/
    │   └── src/
    │       ├── api/           ← typed fetch wrappers
    │       ├── components/    ← board, layout, practice, teaching
    │       └── pages/         ← Dashboard, Libraries, Practice, Stats, Settings, Admin
    └── nginx/
        └── default.conf       ← /api/* → backend, /* → frontend SPA
```

---

## Ports reference

| Mode | Service | Default | Override |
|---|---|---|---|
| Docker (prod) | Web UI (nginx) | `8090` | `PUBLIC_PORT` in `.env` |
| Docker (prod) | Backend, frontend | internal | — |
| Dev | FastAPI | `8100` | `--port` flag |
| Dev | Vite | `8090` | `server.port` in `vite.config.ts` |
