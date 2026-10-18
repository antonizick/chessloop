# Development

For people who want to change ChessLoop's code. To use ChessLoop, see the [README](../README.md).

## Layout

```text
deploy.sh               installer and the `chessloop` command
chessloop/
  .env.example          every setting, explained
  docker-compose.yml        development stack
  docker-compose.prod.yml   production stack (health checks, bind address)
  backend/              FastAPI app (routers/, services/, models/, seeds/, tests/)
  frontend/             React + Vite + TypeScript (src/api, components, pages)
  nginx/                nginx image: /api/* to the backend, everything else to the frontend
docs/                   user guides (this folder)
scripts/                ci-local.sh, smoke.sh, test-deploy-helpers.sh
```

Tech: Python 3.12, FastAPI, SQLModel, SQLite (WAL); python-jose, passlib (bcrypt), pyotp; React 18, Vite, TypeScript, Chessground, chess.js, TailwindCSS, Zustand, TanStack Query; Docker Compose and nginx.

## Run it for development

### Backend

```bash
cd chessloop/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
CHESSLOOP_JWT_SECRET=dev-secret-that-is-long-enough-0123456789 uvicorn main:app --reload --port 8100
```

API docs at `http://localhost:8100/docs` (development only; the Docker stack does not publish them).

### Frontend

```bash
cd chessloop/frontend
npm install
npm run dev
```

Open `http://localhost:8090`. Vite sends `/api/*` to `http://localhost:8100`.

### Ports

| Mode | Service | Default | Change with |
|---|---|---|---|
| Production | Web page (nginx) | 8090 | `PUBLIC_PORT` in `.env` |
| Development | FastAPI | 8100 | `--port` |
| Development | Vite | 8090 | `server.port` in `vite.config.ts` |

## Create an admin and load starter libraries

```bash
cd chessloop/backend
python seeds/create_admin.py --email you@example.com      # asks for a password
python seeds/seed_libraries.py                            # 16 starter libraries
```

`create_admin.py` also accepts `--password-stdin`, `--username` and `--reset-password`. The password is never taken from the command line.

## Tests and checks

```bash
cd chessloop/backend && pytest -q
cd chessloop/frontend && npm ci && npm run lint && npm run build
scripts/ci-local.sh          # all of CI in Docker: backend frontend shell helpers compose images secrets
```

Pass step names to run only some, for example `scripts/ci-local.sh backend frontend`.

## The SRS algorithm

A modified SM-2. Right: the interval grows by the ease factor (2.5 by default; Easy adds 0.15, Hard takes 0.15 off). Wrong: the interval drops to `max(1, interval × 0.25)`, the position returns in 10 minutes and its miss count goes up. Four misses make a leech. Session selection: overdue first, then leeches in a leech drill, then new items (20% weight), with a bias to weak items (ease below 1.8 counts double).

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md). Releases and history: [CHANGELOG.md](../CHANGELOG.md).
