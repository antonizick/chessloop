# ChessLoop

Self-hosted, move-based spaced-repetition chess opening trainer.

> **Status:** Phase 4 complete — Stats, Public Discovery, and a fully live Dashboard.  
> Phase 5 next: piece-set themes, seed libraries, admin backup UI, Docker prod config.

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
| 2 | Teaching board (live move recording, move list, per-move notes) | ✅ Complete |
| 3 | SRS practice loop, SM-2 scheduler, leech detection, session summary, sounds | ✅ Complete |
| 4 | Stats (heatmap, mastery, leeches), public library discovery, dashboard live data | ✅ Complete |
| 5 | Piece-set themes, seed libraries, admin backup UI, Docker prod config, README | 🔜 Next |

---

## Tech stack

### Backend
- **Python 3.12** + **FastAPI** — async REST, auto OpenAPI docs
- **SQLModel** — Pydantic + SQLAlchemy in one; type-safe models
- **SQLite** (WAL mode) — zero config, file = backup
- **python-jose** + **passlib** — JWT sessions + bcrypt hashing
- **pyotp** — TOTP MFA (Google Authenticator compatible)

### Frontend
- **React 18** + **Vite** + **TypeScript**
- **Chessground 9** — drag/drop/touch chess board
- **chess.js** — move validation, FEN/PGN
- **TailwindCSS** — utility-first dark/gold theme
- **Zustand** — lightweight state (auth store)
- **TanStack Query** — data fetching, caching, background refresh

### Infrastructure
- **Docker Compose** — 3 services: frontend, backend, nginx
- **Nginx** — reverse proxy: `/api/*` → FastAPI, `/*` → React SPA

---

## API overview

| Prefix | Purpose |
|---|---|
| `/api/auth/` | Register, login, MFA setup/confirm, refresh token, logout |
| `/api/libraries/` | CRUD, active toggle, publish, fork |
| `/api/lines/` | CRUD, append/delete moves, per-move notes |
| `/api/practice/` | Session start/next/answer/end, due-count badge |
| `/api/stats/` | Accuracy heatmap, mastery per library, leeches, recent sessions |
| `/api/public/` | Browse/search public libraries, star, comment |

Full interactive docs: `http://localhost:8100/docs` (dev) or `http://localhost:${PUBLIC_PORT}/api/docs` (Docker).

---

## Ports

ChessLoop is parameterised so it never collides with anything else on the host.

| Mode | Service | Default | Override |
|---|---|---|---|
| Docker | Public web UI (nginx) | **8090** | `PUBLIC_PORT` in `.env` |
| Docker | Backend, frontend containers | internal only | — |
| Dev | FastAPI (uvicorn) | **8100** | `--port` flag |
| Dev | Vite dev server | **8090** | `server.port` in `vite.config.ts` |

If 8090 is busy, set a different `PUBLIC_PORT` in `.env` before `docker compose up`.

---

## Dev quickstart

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

### Full stack (Docker)

```bash
cp .env.example .env   # set CHESSLOOP_JWT_SECRET; optionally change PUBLIC_PORT
docker compose up --build
```

App: `http://localhost:${PUBLIC_PORT:-8090}`

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
User           — auth, preferences
Library        — opening repertoire container (white/black/both, public/private)
Line           — move sequence within a library (JSON array of {san, uci, fen_after, note?})
PracticePosition — one SRS card per (user, line, move_index)
ReviewLog      — every answer recorded with timing
PracticeSession — session metadata + aggregate stats
PublicSignal   — stars and comments on public libraries
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
│   ├── routers/             # auth, libraries, lines, practice, stats, public
│   ├── services/            # srs_engine, position_key, practice_session
│   └── auth/                # JWT, MFA, password helpers
├── frontend/
│   └── src/
│       ├── api/             # Typed fetch wrappers (auth, libraries, lines, practice, stats, public)
│       ├── components/      # board/, layout/, practice/, teaching/
│       ├── pages/           # Dashboard, Libraries, TeachingBoard, PracticeBoard, Stats, Public, …
│       ├── stores/          # Zustand auth store
│       └── types/           # Shared TypeScript interfaces
├── nginx/
│   └── default.conf         # Reverse proxy config
└── docker-compose.yml
```

---

## Running tests

```bash
cd backend
source .venv/bin/activate
pytest tests/ -v
```

Tests cover: SRS engine correctness, practice session selection logic, practice API end-to-end.
