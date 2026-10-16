# Contributing to ChessLoop

Thanks for helping. ChessLoop is licensed under AGPL-3.0-or-later; by contributing you agree your work is released under the same licence. Please read the [Code of Conduct](CODE_OF_CONDUCT.md).

## Development setup

### Backend (FastAPI + SQLite)
```bash
cd chessloop/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
CHESSLOOP_JWT_SECRET=dev-secret uvicorn main:app --reload --port 8100
# OpenAPI docs: http://localhost:8100/docs
```

### Frontend (React + Vite)
```bash
cd chessloop/frontend
npm ci
npm run dev   # http://localhost:8090, proxies /api/* to http://localhost:8100
```
To open the dev server from another hostname, set `VITE_ALLOWED_HOSTS` (comma-separated), for example `VITE_ALLOWED_HOSTS=localhost,127.0.0.1,myhost.example npm run dev`.

## Tests and checks
Run these before you open a pull request:
```bash
cd chessloop/backend && pytest -q
cd chessloop/frontend && npm run lint && npm run build
shellcheck deploy.sh manage.sh
```

## Pull requests
- Branch from `main`; keep each PR focused on one change.
- Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `chore:`).
- We recommend signing off your commits (`git commit -s`, the [DCO](https://developercertificate.org/)).
- **Docs are part of done.** Update the README or `docs/` when behaviour changes, and add a line under `[Unreleased]` in [CHANGELOG.md](CHANGELOG.md).
- Never commit secrets, `.env` files, databases or backups.
- Changes to the installer, Docker Compose or nginx should be tried on a clean virtual machine first.

## Reporting problems
Use the issue templates. For security problems, follow [SECURITY.md](SECURITY.md) instead.
