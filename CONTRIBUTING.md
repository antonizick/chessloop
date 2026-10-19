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
shellcheck deploy.sh scripts/*.sh
scripts/test-deploy-helpers.sh
```

Or run everything CI runs in one go. It needs only Docker, because each step runs in a container (so your local Python and Node versions don't matter):
```bash
scripts/ci-local.sh            # all steps
scripts/ci-local.sh backend    # or pick steps: backend frontend shell helpers compose dockerfiles images scan audit docs secrets
```

### Continuous integration
Every push to `main` and every pull request runs `.github/workflows/ci.yml`:

| Job | What it checks |
|---|---|
| Backend tests | `pytest` on Python 3.12 |
| Frontend lint and build | `npm run lint` and `npm run build` on Node 24 LTS |
| ShellCheck | `deploy.sh`, `scripts/*.sh` |
| Compose files validate | `docker compose config` for the production and development files |
| Dockerfile lint (hadolint) | the backend, frontend and nginx Dockerfiles |
| Image build and scan (backend, frontend, nginx) | builds each image (nothing is pushed) and scans it with Trivy; fails on a HIGH or CRITICAL vulnerability that has a fix |
| Dependency audit | `pip-audit` on the backend requirements (fails on any known vulnerability); `npm audit --omit=dev` for the frontend (reported, doesn't fail) |
| Install smoke | runs `deploy.sh --yes` from the PR's commit on a fresh runner, the API smoke test, backup → change → restore, and Update |
| Docs links | links, anchors, images and banned words in the user docs |
| Secret scan (gitleaks) | the full git history, configured in `.gitleaks.toml` |

**Required checks.** `main` is protected: a pull request can be merged only when every job above has passed (the three image jobs count separately), and nobody can force-push to `main` or delete it. Repository admins can still bypass this in an emergency. Please don't: people install straight from `main`.

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
