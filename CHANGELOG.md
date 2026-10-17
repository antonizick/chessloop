# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and this project intends to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html) from its first release.

History before this changelog: see `git log`.

## [Unreleased]

### Added
- `LICENSE` (GNU AGPL-3.0-or-later), `NOTICE` and `THIRD_PARTY_NOTICES.md`.
- `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1) and this changelog.
- GitHub issue templates (install problem, bug report, feature request), a pull request template and Dependabot configuration.
- `.editorconfig` and `.gitattributes` (LF line endings, so scripts work when cloned on Windows for WSL).
- GitHub Actions CI (`.github/workflows/ci.yml`) on pushes to `main` and pull requests: backend tests, frontend type check and build, ShellCheck (advisory for now), Compose file validation, Docker image builds and a gitleaks secret scan. Actions and scanner images are pinned by SHA or digest.
- `scripts/ci-local.sh` runs the same checks locally in Docker, and `.gitleaks.toml` configures the secret scan.
- CI status badge in the README.
- `VITE_ALLOWED_HOSTS` environment variable for the Vite dev server's allowed hostnames.
- **Change password** in Settings → Account (`POST /api/auth/change-password`). It checks the current password, applies the password rule, signs out every other session and is rate limited.
- `CHESSLOOP_EMAIL_VERIFICATION` (`auto` default, `on`, `off`): with `auto`, new accounts must verify their email only when SMTP is configured, so an install without email no longer locks every new user out.
- Public `GET /api/auth/config` (registration open, verification required, SMTP configured, password minimum length; no secrets). The sign-in page uses it: when the server cannot send email, an unverified user is told to ask their admin instead of being offered a resend that cannot arrive.
- Admin → Users shows whether each account is verified, with a **Verify** button; admins can verify accounts and set passwords on a server without email. Admin → System settings shows whether SMTP is configured and whether the verification setting comes from the server or from an admin, with a "Use the server setting" link.
- `seeds/create_admin.py --email … [--username …] [--password-stdin] [--reset-password]`, also reading `CHESSLOOP_ADMIN_EMAIL`/`CHESSLOOP_ADMIN_PASSWORD`, and asking for the password (hidden) when run in a terminal. Exit codes 0/2/3.
- Every `.env` setting now reaches the backend in the production stack: `FRONTEND_URL`, `DOMAIN`, all `SMTP_*`, `EMAIL_VERIFICATION`, `EMAIL_MX_CHECK` and `LICHESS_API_TOKEN` (passed through; not used yet). Email works without editing `docker-compose.prod.yml`.
- `chessloop/.env.example` documents every setting in plain English, marking which are required.
- Security headers from nginx: Content-Security-Policy, `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options`, `Referrer-Policy` and `Permissions-Policy` (see SECURITY.md).
- Health checks for the frontend container, and the reverse proxy waits for healthy backend and frontend containers before it starts.
- `chessloop/frontend/.dockerignore`, and an `nginx` image build in CI.
- The backend container refuses to start with a missing, short, example or shell-command `JWT_SECRET`, and says how to fix it.
- The backend's own log messages (for example "SMTP not configured — skipping email") now also go to the container output, so they show in `docker compose logs`; startup logs whether email is configured.

### Changed
- **No default admin account.** `seeds/create_admin.py` no longer creates `admin@example.com` / `admin`; it creates the admin you specify, already verified. The installer summary prints the command instead of default credentials.
- One password rule everywhere a password is set: at least 12 characters and not built on a common word (see SECURITY.md). It used to be 8 characters for registration and reset, and none for admin-created accounts.
- Changing or resetting a password (including an admin setting one) now invalidates all existing sign-in tokens for that account (token version stored in the JWT).
- `EMAIL_MX_CHECK` now defaults to `false`: the live DNS lookup rejected every address on offline or LAN-only servers.
- `seeds/seed_libraries.py` writes the 16 starter libraries straight into the database and publishes them, instead of registering a `seed@chessloop.local` account over HTTP (which was rejected, so seeding always failed). It needs no email, no login and no options, and new accounts again receive "Ruy López — Closed". The old `--url/--email/--username/--password` options and the default seed password are gone.
- `seeds/seed_lichess.py` and `seeds/pull_opening_variations.py` no longer default to a `seedbot@chessloop.app` / `SeedBot1234!` account: `--email` is required and the password comes from `CHESSLOOP_SEED_PASSWORD` or a hidden prompt.
- Accounts created by an admin in Admin → Users are verified.
- Admin → System settings no longer saves the verification choice just by opening the page; the server's `EMAIL_VERIFICATION` applies until an admin changes the toggle. Turning verification on without SMTP is refused with an explanation.
- The registration page now says what to do next (sign in, check your email, or ask the admin) instead of always "Check your email".
- Vite dev server no longer has a hard-coded personal hostname; it accepts `localhost,127.0.0.1` unless `VITE_ALLOWED_HOSTS` is set.
- `planning.md` moved to `docs/history/planning.md`.
- The data volume's name is pinned to `chessloop_chessloop-data`, the name Compose has always given it, so existing installs keep their data and the name no longer depends on the folder. Scripts and docs that said `chessloop-data` pointed at an empty volume.
- The port is bound to `127.0.0.1` by default (it was `0.0.0.0` when `.env` had no `BIND_ADDR`), as the docs always said.
- No CORS headers by default (the UI and API share one origin); nginx no longer adds `Access-Control-Allow-Origin: *`, and the installer no longer writes `CORS_ORIGINS=*` when no domain is given.
- Email links default to `https://DOMAIN` (or `http://localhost:PUBLIC_PORT`), and the sender to the `SMTP_USER` address, instead of `no-reply@chessloop.local`, which real mail servers reject.
- nginx's config is built into its own image (`chessloop/nginx/Dockerfile`) instead of bind-mounted, so the proxy also starts when Docker brings containers back at boot before the file is available (Docker Desktop on Windows).
- Health checks work: the backend uses Python instead of `curl` (not in the image), nginx checks `127.0.0.1` instead of `localhost` (IPv6 in Alpine).
- Base images: Node 24 LTS (`npm ci`) for the frontend build, `nginx:1.30-alpine`, `python:3.12.15-slim-trixie`. The backend image no longer installs `build-essential` (784 MB → 353 MB).
- The frontend's `index.html` is served with `Cache-Control: no-cache` and hashed assets as immutable, so browsers load a new version right after an update.
- `docker-compose.yml` is labelled development-only, requires `JWT_SECRET`, binds to `127.0.0.1` and uses the same nginx image.
- `.gitignore` now also ignores `*.db*`, `*.tsbuildinfo`, `passdata/`, `backups/`, `runs/` and `*.tar.gz`.

### Removed
- The "testing" nginx headers: wildcard CORS, `X-Frame-Options: ALLOWALL` and a CSP that allowed everything.
- The `/chess/` subpath routes in nginx: the frontend always calls `/api` and loads its files from `/`, so ChessLoop never worked under a subpath.
- The public `/docs` and `/openapi.json` routes in the Docker stack.
- The obsolete `version:` key in both compose files (Compose printed a warning on every command).
- Developer-only and personal files: root `CLAUDE.md`, the committed `chessloop.db`, `passdata/`, `scripts/` (one-off maintenance scripts with personal paths and a compiled `__pycache__`), and `chessloop/frontend/tsconfig.tsbuildinfo`.
