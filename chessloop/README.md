# ChessLoop

Self-hosted, move-based spaced-repetition chess opening trainer.

> **Status:** Phase 5 complete — fully production-ready for self-hosting.

---

## 🚀 Quick Deploy

Deploy to a fresh Ubuntu/Debian server in one command:

```bash
curl -fsSL https://raw.githubusercontent.com/antonizick/chessloop/main/deploy.sh | bash
```

The script automatically:
- Installs Docker and Docker Compose
- Clones the repository
- Generates a JWT secret
- Prompts for configuration (port, domain)
- Starts all services
- Sets up autostart on boot via systemd

After deploy, access ChessLoop at `http://your-server-ip:8090`, register an account, and promote yourself to admin. Full instructions are printed at the end of the deploy script.

**For updates:** Re-run the same deploy command. It will pull the latest code and rebuild services.

**For backups:** Use the Admin panel → Database backups to create, download, and restore backups without downtime.

---

## What it does

ChessLoop lets you teach it your opening repertoire by playing moves on a board, then drills you back with intelligent spaced-repetition scheduling. The core loop:

1. **Teach** — play moves on the Teaching Board; each move is saved to a Line in a Library
2. **Practice** — the SRS engine (SM-2 variant) picks your weakest positions and quizzes you
3. **Feedback** — wrong answers show a red flash + correct-move arrow; you must physically replay the right move before continuing
4. **Track** — the Stats page shows accuracy heatmaps by move number and mastery % per opening

---

## Feature status

| Phase | What | Status |
|---|---|---|
| 1 | Auth (JWT + TOTP MFA), Library/Line CRUD, Chessground board, dark/gold UI | ✅ Complete |
| 2 | Teaching board (live move recording, move list, per-move notes, move navigation, PGN export) | ✅ Complete |
| 3 | SRS practice loop, SM-2 scheduler, leech detection, session summary, sounds | ✅ Complete |
| 4 | Stats (heatmap, mastery, leeches), public library discovery, dashboard live data | ✅ Complete |
| 5 | Board themes, piece sets, sounds settings, admin panel, seed libraries, Docker prod | ✅ Complete |

---

## Teaching Board Controls

The Teaching Board provides intuitive controls for recording and navigating through opening moves:

| Control | Action |
|---|---|
| Drag pieces | Record moves onto the board (creates Line with move sequence) |
| ⟪ | Jump to first move |
| ‹ | Go to previous move (or last move if at live position) |
| › | Go to next move (disabled when at live position) |
| ⟫ | Jump to last move |
| ↓ PGN | Download line as standard PGN file (with `[Event]` header) |
| ⧭ | Duplicate line (creates a copy with all moves) |
| Delete (🗑) | Remove a move and all subsequent moves |

Move-by-move navigation lets you review and edit your lines without re-playing them. PGN export makes openings portable to other chess tools. Line duplication lets you quickly create variations of existing lines.

### Move Notes

Add annotations to any move to document strategy, warnings, or variations:

- **Click on a move** in the move list to select it
- **Click "Add note"** (or "Edit" if a note exists) to open the editor
- **Type your annotation** — use Ctrl+Enter to save or Escape to cancel
- **Notes persist** — switching lines and returning shows all saved notes immediately
- **Visible everywhere** — notes appear in Teaching Board, Unrated Learning, and Practice modes

Perfect for documenting why you play a move, warning about traps, or linking to analysis.

---

## Unrated Learning Mode

The **Unrated Learning** mode provides a distraction-free, read-only way to browse and study opening libraries:

| Feature | Available | Why |
|---|---|---|
| View opening lines | ✅ | Study your repertoire |
| Navigate moves | ✅ | Arrow keys, navigation buttons |
| Read move notes | ✅ | See annotations added in Teaching mode |
| Export PGN | ✅ | Use lines in other tools |
| Flip board | ✅ | View from Black's perspective |
| Edit/delete lines | ❌ | Read-only mode |
| Edit/delete notes | ❌ | Notes are read-only here |
| Add moves | ❌ | No piece dragging allowed |
| Make changes | ❌ | Board is always locked |

**Access Unrated Learning from two places:**
1. **Library grid cards** — Click "Unrated Learning" button (left of "✎ Teach")
2. **Library detail page** — Click "Unrated Learning" button (left of "Teaching board")

Perfect for reviewing openings before practice sessions or sharing repertoires in a controlled way. All move notes you added in Teaching mode are displayed above the board as read-only, so you can see your annotations and analysis without making accidental changes.

### Line Management

In the **Lines** panel on the right side of the Teaching Board:
- **Click a line** to select and view it on the board
- **Double-click** to rename a line
- **Hover to reveal controls:**
  - **⧭** — Duplicate the line (creates "{name} copy" with all moves)
  - **🗑** — Delete the line (with confirmation step)

---

## Tech stack

### Backend
- **Python 3.12** + **FastAPI** — async REST, auto OpenAPI docs
- **SQLModel** — Pydantic + SQLAlchemy in one; type-safe models
- **SQLite** (WAL mode) — zero config, file = backup
- **python-jose** + **passlib** — JWT sessions + bcrypt hashing
- **pyotp** — TOTP MFA (Google Authenticator compatible)
- **chess** (python-chess) — server-side move validation and UCI/FEN computation

### Frontend
- **React 18** + **Vite** + **TypeScript**
- **Chessground 9** — drag/drop/touch chess board
- **chess.js** — client-side move validation, FEN/PGN
- **TailwindCSS** — utility-first dark/gold theme
- **Zustand** — lightweight state (auth store)
- **TanStack Query** — data fetching, caching, background refresh

### Infrastructure
- **Docker Compose** — 3 services: frontend, backend, nginx
- **Nginx** — reverse proxy: `/api/*` → FastAPI, `/*` → React SPA

---

## Quick start (development)

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
CHESSLOOP_JWT_SECRET=dev-secret uvicorn main:app --reload --port 8100
```

OpenAPI docs: http://localhost:8100/docs

### Frontend

```bash
cd frontend
npm install
npm run dev   # http://localhost:8090
```

The Vite dev server proxies `/api/*` → `http://localhost:8100`.

### Network Access

The frontend dev server is automatically accessible via:
- **Localhost:** `http://localhost:8090`
- **Local network:** `http://<machine-ip>:8090` (requires `host: true` in vite.config.ts)
- **Tailscale VPN:** `https://<machine-tailscale-ip>:8443` (HMR auto-configures `wss://` for HTTPS)

HMR (Hot Module Reload) automatically detects the connection protocol and adapts:
- HTTP connections → use `ws://` for HMR WebSocket
- HTTPS connections → use `wss://` (secure WebSocket) for HMR

This allows seamless development access across different networks without manual configuration.

---

## Production self-hosting (Docker)

### 1. Configure

```bash
cp .env.example .env
```

Edit `.env` and set:

| Variable | Required | Default | Description |
|---|---|---|---|
| `JWT_SECRET` | **yes** | — | Long random string. Generate: `openssl rand -hex 32` |
| `PUBLIC_PORT` | no | `8090` | Host port for the web UI |
| `DOMAIN` | for CORS | `localhost` | Your public domain (e.g. `chess.mysite.com`) |

### 2. Build and start

```bash
# Development (binds to 0.0.0.0 so you can reach it from other machines)
docker compose up --build

# Production (binds to 127.0.0.1 — put a reverse proxy in front)
docker compose -f docker-compose.prod.yml up -d --build
```

App: `http://localhost:${PUBLIC_PORT}`

### 3. SSL (recommended for production)

**Option A — Caddy (simplest):** Install Caddy on the host and add to your Caddyfile:

```
chess.yourdomain.com {
    reverse_proxy localhost:8090
}
```

Caddy auto-provisions and renews the Let's Encrypt cert.

**Option B — Cloudflare Tunnel:** Create a tunnel to `localhost:8090`. SSL handled by Cloudflare.

**Option C — Nginx on host:**

```nginx
server {
    listen 443 ssl;
    server_name chess.yourdomain.com;
    ssl_certificate     /etc/letsencrypt/live/chess.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/chess.yourdomain.com/privkey.pem;
    location / {
        proxy_pass http://127.0.0.1:8090;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

See `docker-compose.prod.yml` for full SSL-inside-Docker notes.

### 4. Create your first admin account

Register normally in the UI. Then promote yourself to admin via Python:

```bash
cd backend
source .venv/bin/activate

python3 << 'EOF'
import sys
from sqlmodel import Session, create_engine, select
from models.user import User

engine = create_engine("sqlite:///chessloop.db", echo=False)
with Session(engine) as session:
    user = session.exec(select(User).where(User.username == "yourname")).first()
    if user:
        user.role = "admin"
        session.add(user)
        session.commit()
        print(f"✅ {user.username} promoted to admin")
    else:
        print("❌ User not found")
EOF
```

Once promoted, the **Admin panel** (⚙ icon in the sidebar) grants:
- Backup creation, download, and deletion
- User promotion / demotion
- Opening import from Lichess (with automatic GitHub line population)

### Importing Openings from Lichess

In the Admin panel, you can import openings from the Lichess database:

1. **Search** for an opening by name or ECO code (the system provides 50+ curated openings)
2. **Select** an opening and review its information (difficulty, description, ECO code)
3. **Import** the opening — the system creates a Library with:
   - A **Main line** with the opening's starting moves
   - **All matching opening lines** from the Lichess GitHub chess-openings repository (automatically loaded)
   - Optional additional variations from Lichess Explorer games (if requested)

**Automatic GitHub line loading:**
When you import an opening, the system immediately fetches all opening lines from the [Lichess chess-openings repository](https://github.com/lichess-org/chess-openings) that match the opening's ECO code. This populates your library with a comprehensive set of variations without any extra steps.

You can optionally:
- **Publish** the opening immediately to Public Discovery
- **Import variations** from recent master games (Lichess Explorer data)

---

## Seed starter libraries

ChessLoop ships with a seed script that populates 16 curated opening libraries and publishes them to the Public Discovery page. Useful on a fresh install.

```bash
cd backend
source .venv/bin/activate

# Against the dev server (default):
python seeds/seed_libraries.py

# Against Docker:
python seeds/seed_libraries.py --url http://localhost:8090
```

The script creates a `seedbot` account, adds the 16 openings, and publishes them. Any existing library with the same name is skipped.

To seed with your own account:
```bash
python seeds/seed_libraries.py --email you@example.com --username you --password YourPassword
```

---

## Appearance

Go to **Settings** to customise:

| Setting | Options |
|---|---|
| Board theme | Brown (default) · Blue · Green · Ice · Purple |
| Piece set | CBurnett (default) · Alpha · Mono · Shadow |
| Sounds | On / Off |

Changes take effect immediately (live preview in Settings before saving).

---

## API overview

| Prefix | Purpose |
|---|---|
| `/api/auth/` | Register, login, MFA setup/confirm, refresh token, preferences |
| `/api/libraries/` | CRUD, active toggle, publish, fork |
| `/api/lines/` | CRUD, append/delete moves (SAN-only or SAN+UCI+FEN), per-move notes |
| `/api/practice/` | Session start/next/answer/end, due-count badge |
| `/api/stats/` | Accuracy heatmap, mastery per library, leeches, recent sessions |
| `/api/public/` | Browse/search public libraries, star, comment |
| `/api/admin/` | Backup CRUD + user management (admin role required) |

Full interactive docs: `http://localhost:8100/docs` (dev) or `http://YOUR_HOST/api/docs` (Docker).

---

## Ports

| Mode | Service | Default | Override |
|---|---|---|---|
| Docker | Public web UI (nginx) | **8090** | `PUBLIC_PORT` in `.env` |
| Docker | Backend, frontend | internal only | — |
| Dev | FastAPI (uvicorn) | **8100** | `--port` flag |
| Dev | Vite dev server | **8090** | `server.port` in `vite.config.ts` |

---

## SRS algorithm

Modified SM-2 with leech detection:

- **Correct:** interval grows by ease factor (default 2.5×); Easy adds +0.15 ease, Hard subtracts -0.15
- **Wrong:** interval reset to `max(1, interval × 0.25)`, position requeued in 10 min, leech count incremented
- **Leech threshold:** 4 cumulative wrong answers → position flagged as leech, surfaced in dedicated Leech Drill mode
- **Session selection:** overdue items first → leeches always included in leech_drill → new items (20% weight) → weakness bias (ease < 1.8 gets 2× weight)

---

## Data model (key tables)

```
User           — auth, preferences (theme, piece_set, board_theme, sounds_on)
Library        — opening repertoire container (white/black/both, public/private)
Line           — move sequence within a library (JSON array of {san, uci, fen_after, note?})
PracticePosition — one SRS card per (user, line, move_index)
ReviewLog      — every answer recorded with timing
PracticeSession — session metadata + aggregate stats
PublicSignal   — stars and comments on public libraries
Backup         — admin backup records (file_path, type, size)
```

---

## Running tests

```bash
cd backend
source .venv/bin/activate
pytest tests/ -v
```

Tests cover: SRS engine correctness, practice session selection logic, practice API end-to-end.

---

## Backups

Use the **Admin panel → Backups** tab to create named backups on-demand and download them. Three backup types:

| Type | What's included |
|---|---|
| `full` | Entire SQLite file (users + content + SRS progress) |
| `content` | Libraries and lines only (portable to another instance) |
| `progress` | SRS cards + review log only |

Up to 10 backups are retained; the oldest is pruned automatically when the limit is exceeded.

### Backup location

By default, backups are stored in `./backups/` (relative to the backend directory). You can override this:

```bash
# Development:
CHESSLOOP_BACKUP_DIR=/path/to/backups uvicorn main:app --port 8100

# Docker (in .env):
CHESSLOOP_BACKUP_DIR=/data/backups
```

For volume-level snapshots in Docker:

```bash
docker run --rm \
  -v chessloop-data:/src \
  -v $(pwd):/out \
  alpine tar czf /out/chessloop-backup-$(date +%F).tar.gz -C /src .
```

---

## Project structure

```
chessloop/
├── backend/
│   ├── main.py              # FastAPI app factory + router registration
│   ├── database.py          # SQLite + SQLModel engine
│   ├── config.py            # Settings (JWT secret, CORS origins, etc.)
│   ├── models/              # SQLModel table classes
│   ├── schemas/             # Pydantic request/response schemas
│   ├── routers/             # auth, libraries, lines, practice, stats, public, admin
│   ├── services/            # srs_engine, position_key, practice_session, backup_service
│   ├── auth/                # JWT, MFA, password helpers
│   └── seeds/               # seed_libraries.py — 16 starter openings
├── frontend/
│   └── src/
│       ├── api/             # Typed fetch wrappers
│       ├── components/      # board/, layout/, practice/, teaching/
│       ├── pages/           # Dashboard, Libraries, TeachingBoard, PracticeBoard,
│       │                    # Stats, Public, Settings, Admin
│       ├── stores/          # Zustand auth store
│       └── types/           # Shared TypeScript interfaces
├── nginx/
│   └── default.conf         # Reverse proxy config
├── docker-compose.yml       # Development compose
└── docker-compose.prod.yml  # Production compose (127.0.0.1 binding, health checks)
```
