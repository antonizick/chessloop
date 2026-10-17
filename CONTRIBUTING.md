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

Or run everything CI runs in one go. It needs only Docker, because each step runs in a container (so your local Python and Node versions don't matter):
```bash
scripts/ci-local.sh            # all steps
scripts/ci-local.sh backend    # or pick steps: backend frontend shell compose images secrets
```

### Continuous integration
Every push to `main` and every pull request runs `.github/workflows/ci.yml`:

| Job | What it checks |
|---|---|
| Backend tests | `pytest` on Python 3.12 |
| Frontend lint and build | `npm run lint` and `npm run build` on Node 24 LTS |
| ShellCheck (advisory) | `deploy.sh`, `manage.sh`, `scripts/*.sh`. Known warnings don't fail the run yet |
| Compose files validate | `docker compose config` for the production and development files |
| Docker image build | Builds the backend and frontend images (nothing is pushed) |
| Secret scan | gitleaks over the full git history, configured in `.gitleaks.toml` |

Workflow actions are pinned to a full commit SHA with the version in a comment; Dependabot proposes updates. CI uses no secrets or tokens.

## Pull requests
- Branch from `main`; keep each PR focused on one change.
- Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `chore:`).
- We recommend signing off your commits (`git commit -s`, the [DCO](https://developercertificate.org/)).
- **Docs are part of done.** Update the README or `docs/` when behaviour changes, and add a line under `[Unreleased]` in [CHANGELOG.md](CHANGELOG.md).
- Never commit secrets, `.env` files, databases or backups.
- Changes to the installer, Docker Compose or nginx should be tried on a clean virtual machine first.

## Reporting problems
Use the issue templates. For security problems, follow [SECURITY.md](SECURITY.md) instead.
