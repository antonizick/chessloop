# ChessLoop

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![CI](https://github.com/antonizick/chessloop/actions/workflows/ci.yml/badge.svg)](https://github.com/antonizick/chessloop/actions/workflows/ci.yml)

Self-hosted, move-based spaced-repetition chess opening trainer.

Teach it your repertoire by playing moves. It drills you back, corrects mistakes, and schedules review so the positions that break you get more practice.

**Features:** opening library builder · spaced-repetition drill engine · public library discovery with read-only viewer · TOTP MFA · dark/light theme · admin panel with backup/restore · Lichess Explorer integration

## Screenshots

![ChessLoop Tracking dashboard](screenshots/ChessLoop%20Tracking%20dashboard.png)

![ChessLoop Openings database](screenshots/ChessLoop%20Openings%20database.png)

![ChessLoop Learning and training arenas](screenshots/ChessLoop%20Learning%20and%20training%20arenas.png)

![Chessloop Game tracking and self analysis](screenshots/Chessloop%20Game%20tracking%20and%20self%20analysis.png)

![Chessloop Statistics tracking](screenshots/Chessloop%20Statistics%20tracking.png)

---

## Deploy to a new machine

One command on Ubuntu 24.04 or 26.04, Debian 12 or 13, or Ubuntu inside WSL 2 on Windows 11 (all 64-bit Intel/AMD). Other systems are not tested; the installer says so and asks before it continues.

```bash
curl -fsSL https://raw.githubusercontent.com/antonizick/chessloop/main/deploy.sh | bash
```

Prefer to read the script before running it? Download it, look at it, then run it:

```bash
curl -fsSLO https://raw.githubusercontent.com/antonizick/chessloop/main/deploy.sh
less deploy.sh
bash deploy.sh
```

You need: about 2 GB of memory, 5 GB of free disk space, an internet connection, and a user who can use `sudo`. The install takes about 3 to 10 minutes, mostly downloading and building. The installer checks all of this first, tells you what it is going to do, and changes nothing until you say "Continue".

### What the installer asks

1. **Where will you open ChessLoop?** Only on this computer; also on other devices in your home network; or from the internet with your own domain name (HTTPS). On a computer with a public internet address it warns before offering the plain-HTTP home-network choice.
2. **Port.** The number at the end of the address (default 8090). If it is taken, the installer suggests a free one.
3. **Your admin email and password.** Choose a password of at least 12 characters, or press Enter and the installer creates a strong one and shows it once. There is no default login.
4. **Email (optional).** Skip it, or enter SMTP details; the installer sends a test message. Without email, people who register can sign in at once.
5. **Starter opening libraries** (recommended).
6. **On Windows with WSL:** whether to keep Ubuntu running when its window is closed and start it with Windows.

Then it installs Docker Engine from Docker's official repository if needed, downloads ChessLoop into `/opt/chessloop`, writes the settings file `chessloop/.env` (readable only by you), builds and starts ChessLoop, creates your admin account and checks that it can sign in. It writes a log of the run to `~/chessloop-install-<date>.log` (passwords are never in it). If something fails, it says which step, shows the last lines of the log, and tells you how to report it. Run the installer again and it continues where it stopped.

### Unattended install

For scripts and testing, every answer can come from an environment variable:

```bash
CHESSLOOP_ADMIN_EMAIL=you@example.com bash deploy.sh --yes
```

`bash deploy.sh --help` lists the settings (`CHESSLOOP_ACCESS`, `CHESSLOOP_PORT`, `CHESSLOOP_DOMAIN`, `CHESSLOOP_ADMIN_PASSWORD`, `CHESSLOOP_SEED`, `CHESSLOOP_SMTP_*`, `CHESSLOOP_INSTALL_DIR`, `CHESSLOOP_REPO`, `CHESSLOOP_REF`, …). Without `CHESSLOOP_ADMIN_PASSWORD` the installer generates a password and prints it once.

### Windows 11 (WSL 2)

Open ChessLoop in your **Windows** browser at `http://localhost:8090`. Windows stops Ubuntu (and ChessLoop) shortly after you close its last window and does not restart it with Windows; the installer offers to change two settings for your Windows user (`%UserProfile%\.wslconfig` and a `ChessLoop.cmd` file in the Startup folder) so ChessLoop keeps running. They apply after `wsl --shutdown` or a Windows restart. To reach ChessLoop from a phone, WSL needs mirrored networking and a Windows firewall rule; the installer prints the exact steps. If Docker Desktop is installed, switch on its WSL integration for your Ubuntu first (Settings > Resources > WSL integration).

---

## After install

### Access

```
http://localhost:PORT          (this computer; on Windows, in your Windows browser)
http://YOUR-COMPUTERS-IP:PORT  (other devices, if you chose the home-network option)
```

### First login

Sign in with the admin email and password you gave the installer. The admin account is ready at once: it does not need email verification. Change the password later in **Settings → Account → Change password**.

To create another admin, or reset a forgotten admin password, run:

```bash
cd /opt/chessloop/chessloop
sudo docker compose -f docker-compose.prod.yml exec backend \
  python seeds/create_admin.py --email you@example.com --reset-password
```

**Email is optional.** Without email (SMTP) settings, people who register can log in straight away (`EMAIL_VERIFICATION=auto`, the default, turns verification on only when SMTP is set up). An admin can verify accounts and set passwords in **Admin → Users**.

The admin account has full access to the Admin panel (⚙ icon in the sidebar), where you can manage users, create/download backups, and import openings from the Lichess database.

### Service management

Docker starts at boot and brings ChessLoop back by itself. The installer adds a `chessloop` command (a link to `/opt/chessloop/deploy.sh`) for everything else:

```bash
chessloop status      # running? address, version, latest backup
chessloop stop        # stop (Docker starts it again when the computer restarts)
chessloop start
chessloop restart
chessloop logs        # the last messages; chessloop logs -f keeps following
chessloop help        # all commands
```

If `chessloop` isn't found (an install made before this command existed), use `bash /opt/chessloop/deploy.sh status` and so on; the next Update adds the command. Older installs also had a `chessloop` systemd service that never worked (it restarted every 10 seconds with an error); Update removes it.

---

## Update (pull new code, keep your data)

```bash
chessloop update          # or: bash /opt/chessloop/deploy.sh update
```

What happens:
1. It shows the installed version and fetches the new one (the branch the install follows, normally `main`), with the new lines from `CHANGELOG.md`.
2. It saves a backup of all data in `~/chessloop-backups/` first. If that fails, nothing is changed (`--no-backup` overrides this).
3. Files of ChessLoop that you changed by hand are put aside with `git stash` (your settings in `chessloop/.env` are never touched).
4. It builds and starts the new version and waits until it is healthy.
5. If the new version doesn't build or doesn't start, it goes back to the previous version and, if needed, to the data from the backup, and says what went wrong.
6. It tidies up after older versions: the broken `chessloop` systemd service, the extra empty `chessloop-data` Docker volume, and the old `admin@example.com` account with the password `admin` (it offers to remove or lock it).

Your data (user accounts, libraries, SRS progress) lives in the `chessloop_chessloop-data` Docker volume; Update never removes it. Unattended: `chessloop update --yes`.

---

## Uninstall

```bash
chessloop uninstall       # or: bash /opt/chessloop/deploy.sh uninstall
```

It lists exactly what will be removed, with sizes, before asking. Three levels:

| Level | What is removed | What stays |
|---|---|---|
| **1: Stop ChessLoop** | Its containers | Data, settings, files, Docker images. `chessloop start` brings it back. |
| **2: Also the images** | Containers and ChessLoop's Docker images | Data, settings, files. `chessloop start` rebuilds the images. |
| **3: Everything** | Containers, images, the data volume (all accounts and libraries), `/opt/chessloop` with the settings, the `chessloop` command, and on Windows the settings that keep Ubuntu running (you are asked) | Your backups in `~/chessloop-backups`, Docker itself |

Level 3 offers a final backup first (with the settings file) and asks you to type `DELETE`. Every level also removes the old `chessloop` systemd service if an older version installed one. Docker stays installed: the script prints the command to remove it.

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
#   JWT_SECRET=<paste the output of: openssl rand -base64 32>
#   (.env does not run commands; ChessLoop refuses to start with the example value)
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
| `DOMAIN` | no | — | Your public domain; email links use `https://DOMAIN` |
| `FRONTEND_URL` | no | `https://DOMAIN` or `http://localhost:PUBLIC_PORT` | Address used in email links (set it for a home-network install) |
| `CORS_ORIGINS` | no | — | Extra origins allowed to call the API from a browser. Not needed: the UI and API share one origin |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_TLS` | no | no email | Outgoing mail; see `chessloop/.env.example` |
| `EMAIL_VERIFICATION` | no | `auto` | `auto` (on only with SMTP), `on`, `off` |
| `EMAIL_MX_CHECK` | no | `false` | Check the email domain's mail servers at registration |
| `ACCESS_TTL_MIN` | no | `15` | JWT access token lifetime in minutes |
| `REFRESH_TTL_DAYS` | no | `30` | JWT refresh token lifetime in days |

---

## Backups

A backup holds password hashes and two-factor secrets: keep it private. Backups are written so that only your user can read them (mode 600).

### From the command line

```bash
chessloop backup                          # → ~/chessloop-backups/chessloop-<date>-<time>.tar.gz (+ .sha256)
chessloop backup --with-settings          # also the settings file .env (it holds your secret key)
chessloop restore                         # choose one of your backups
chessloop restore ~/chessloop-backups/chessloop-20261017-153000.tar.gz
```

The backup is a consistent copy made while ChessLoop runs (SQLite's backup API), plus the Admin-panel backups and a checksum. **Restore** checks the file (checksum, database integrity), saves a safety backup of the current data, puts the backup in place, starts ChessLoop and confirms that every table has the same number of rows as the backup. It also accepts a `full_….db` file downloaded from Admin → Backups.

**Moving to a new computer:** install ChessLoop there, copy the backup file over, and run `chessloop restore FILE`. Everyone signs in again (each install has its own secret key), with the accounts and passwords from the backup.

Copy backups to another computer or a USB stick: a backup on the same disk is lost with the disk.

### From the Admin panel

Admin → Backups tab. Create named backups on demand, download them to your computer, and restore from any backup without downtime. They are stored inside the data volume (`/data/backups`, mode 600), so they are lost with the volume: download the ones you want to keep.

Three backup types:

| Type | Contents |
|---|---|
| `full` | Entire database: users, libraries, lines, SRS progress |
| `content` | Libraries and lines only (portable to another instance) |
| `progress` | SRS cards and review log only |

---

## Seed starter libraries

Populate the instance with 16 curated opening libraries and publish them to Public Discovery:

```bash
# Against a running Docker install:
docker compose -f /opt/chessloop/chessloop/docker-compose.prod.yml \
  exec -T backend python seeds/seed_libraries.py

# Against the dev server:
cd chessloop/backend && python seeds/seed_libraries.py
```

It writes straight into the database (no email or login needed) and is safe to run again. New accounts registered afterwards get a copy of "Ruy López — Closed".

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
├── deploy.sh                  ← installer and the `chessloop` command: install, update, backup, restore, uninstall, status
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
        ├── Dockerfile         ← nginx image with the config built in
        └── default.conf       ← /api/* → backend, /* → frontend SPA, security headers
```

---

## Troubleshooting

### All API calls fail / 504 Gateway Timeout after Docker restart (WSL2)

**Symptom:** The app shows a connectivity error, `chessloop status` shows all containers running, but every API call returns 504.

**Cause:** Docker's bridge network can lose its iptables FORWARD rule when the Docker daemon restarts (seen on WSL2 after sleep or hibernate). Containers stay listed as "Up" but can't reach each other.

**Fix:** Recreate the containers and their network. The database lives in the `chessloop_chessloop-data` Docker volume and is unaffected.

```bash
cd /opt/chessloop/chessloop
sudo docker compose -f docker-compose.prod.yml down
chessloop start
```

---

## Ports reference

| Mode | Service | Default | Override |
|---|---|---|---|
| Docker (prod) | Web UI (nginx) | `8090` | `PUBLIC_PORT` in `.env` |
| Docker (prod) | Backend, frontend | internal | — |
| Dev | FastAPI | `8100` | `--port` flag |
| Dev | Vite | `8090` | `server.port` in `vite.config.ts` |

---

## License

ChessLoop is free software, licensed under the [GNU Affero General Public License v3.0 or later](LICENSE) (AGPL-3.0-or-later). If you run a modified version as a network service, the AGPL requires you to offer its users the source code. See [NOTICE](NOTICE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
