# ChessLoop

Self-hosted, move-based spaced-repetition chess opening trainer.

## Phase 1 (current)

- FastAPI backend with SQLModel + SQLite (WAL)
- JWT auth (access + refresh) with optional TOTP MFA
- Library / Line CRUD
- React + Vite + TypeScript frontend
- Chessground renders on Teaching and Practice pages (static)
- Dark / gold Tailwind theme
- Docker Compose: backend + frontend + nginx

## Ports

ChessLoop is parameterized so it never collides with anything else on the host.

| Mode | Service | Default | Override |
|---|---|---|---|
| Docker | Public web UI (nginx) | **8090** | `PUBLIC_PORT` in `.env` |
| Docker | Backend, frontend containers | (internal network only — no host binding) | — |
| Dev | FastAPI | **8100** | `--port` flag on `uvicorn` |
| Dev | Vite | **8090** | `server.port` in `vite.config.ts` |

If 8090 is busy on your machine, set a different `PUBLIC_PORT` in `.env` before `docker compose up`.

## Dev quickstart

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
CHESSLOOP_JWT_SECRET=dev-secret uvicorn main:app --reload --port 8100
```

OpenAPI: http://localhost:8100/docs

### Frontend

```bash
cd frontend
npm install
npm run dev   # http://localhost:8090
```

The Vite dev server proxies `/api/*` to `http://localhost:8100`.

### Full stack (Docker)

```bash
cp .env.example .env   # set JWT_SECRET, optionally change PUBLIC_PORT
docker compose up --build
```

App: `http://localhost:${PUBLIC_PORT:-8090}`
