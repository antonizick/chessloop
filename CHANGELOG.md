# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and this project intends to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html) from its first release.

History before this changelog: see `git log`.

## [Unreleased]

### Added
- **Fresh-eyes fixes (Phase 11):** the guides now say what testers who followed only the docs had to guess: the installer's first menu, the "settings file" and "Rebuild it anyway?" questions, the account count that includes `seedbot`, "Can't scan? Enter manually" for two-factor sign-in, how to make a first library and line, what **Learned** means, that mobile data away from home does not work, Ubuntu's first-run "platform metrics" question on Windows, the `/mnt/c` prompt, and that ChessLoop needs up to 5 minutes to come back after a Windows restart.
- **Starter libraries now hold real content:** each of the 16 starter openings has 7 to 9 named lines (127 in all), for example Chigorin, Breyer and Zaitsev under Ruy López — Closed. The lines are bundled in `services/starter_data.json`, so installing needs no network and no Lichess token. `scripts/build-starter-lines.py` (development only) builds the file; `tests/test_starter_content.py` replays every line.
- `seeds/seed_libraries.py` now tops up libraries that already exist (adds missing lines, keeps your copies and edits), and `chessloop update` runs it (also when you are already on the newest version, for installs that were updated by an older script), printing "Added N lines to the starter libraries.".
- User guides for people with no coding background: `docs/install/linux.md`, `docs/install/windows-wsl2.md` (from a PC with nothing installed to a working ChessLoop), `docs/using-chessloop.md`, `docs/backup-restore.md`, `docs/updating.md`, `docs/uninstall.md`, `docs/configuration.md` (every `.env` setting), `docs/troubleshooting.md`, `docs/faq.md`, `docs/glossary.md` and `docs/development.md`, with screenshots in `docs/images/`.
- `scripts/check-doc-links.py` (offline check of links, anchors, images and banned words in the docs; CI job "Docs links", also `scripts/ci-local.sh docs`), `scripts/extract-doc-commands.sh` and `scripts/readability.py`.
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

- **Installer rewrite (`deploy.sh` Install):** checks the computer first (system, processor, memory, disk, internet, Docker, WSL) and changes nothing until you confirm; asks plain questions (where you will open ChessLoop, port, admin email and password, optional email, starter libraries); installs Docker Engine and the compose plugin from Docker's official apt repository with visible progress; writes `chessloop/.env` from `.env.example` with mode 600; builds and waits until all three services are healthy; creates the admin you chose and checks that it can sign in; loads the starter libraries; sends a test email when SMTP is configured. A log of every run goes to `~/chessloop-install-<date>.log` (no passwords in it). On failure it names the step, shows the last log lines and links the "Install problem" issue form; running Install again continues an unfinished install.
- Unattended mode: `bash deploy.sh --yes` (also `curl … | bash -s -- --yes`) with `CHESSLOOP_*` variables for every answer, plus `CHESSLOOP_REPO` and `CHESSLOOP_REF` to install a fork, branch or tag; `bash deploy.sh --help`. Risky steps need an explicit setting in this mode (`CHESSLOOP_ALLOW_UNTESTED`, `CHESSLOOP_ALLOW_LOW_RESOURCES`, `CHESSLOOP_ALLOW_PUBLIC_LAN`, `CHESSLOOP_ALLOW_PACKAGE_REMOVAL`).
- Ubuntu 26.04 LTS is supported next to Ubuntu 24.04 and Debian 12 and 13; other systems get a clear "not tested" question.
- Windows 11 + WSL 2: the installer detects WSL, shows `http://localhost:PORT` for the Windows browser (never the WSL-internal address), checks that systemd is on, and with the user's OK writes `instanceIdleTimeout=-1` into `%UserProfile%\.wslconfig` and a `ChessLoop.cmd` Startup file so ChessLoop keeps running when Ubuntu's window is closed and after a Windows restart; for phone access it turns on WSL mirrored networking (on request) and prints the Windows firewall command. Docker Desktop's WSL integration is used when it is on; when Docker Desktop can't be used, the installer checks whether it is running and says either to start it or to switch on its WSL integration for your Ubuntu (it never installs Docker Engine next to it). An existing `.wslconfig` is merged (a backup is kept); one saved as UTF-16 is left alone, with Notepad steps instead.
- `scripts/test-deploy-helpers.sh` (unit tests for the installer's helper functions), `scripts/smoke.sh` (API smoke test) and an advisory CI job "Install smoke" that runs `deploy.sh --yes` from the pull request's commit and then the smoke test.

- **`chessloop` command:** the installer links `/usr/local/bin/chessloop` to `/opt/chessloop/deploy.sh`, so `chessloop status | start | stop | restart | logs | backup | restore | update | uninstall | help` work from any folder (an older install gets the link at its next Update). `deploy.sh` takes the same commands (`bash deploy.sh status`).
- **Backup from the command line:** `chessloop backup [FILE] [--with-settings]` saves a consistent copy of the database (SQLite's backup API, while ChessLoop runs), the Admin-panel backups and a manifest with row counts into `~/chessloop-backups/chessloop-<date>-<time>.tar.gz` (mode 600, folder 700) with a `.sha256` checksum file. The settings file `.env` is included only on request, because it holds secrets.
- **Restore from the command line:** `chessloop restore [FILE]` (or a numbered list of your backups) checks the checksum, the database's integrity and that it is a full backup, saves a safety backup of the current data, puts the backup in place with ChessLoop stopped, starts it and confirms that every table has the same number of rows as the backup. It also restores a `full_….db` file downloaded from Admin → Backups, and works on a fresh install on another computer (everyone signs in again there).
- `seeds/legacy_admin.py` reports, deletes or locks the `admin@example.com` account with the password `admin` that installs made before 2026-10 still have (Update uses it).
- The CI "Install smoke" job also backs up, changes the data, restores and checks the row counts, and runs Update.

### Changed
- Admin → Openings → **Seed** now loads the same 16 starter libraries and lines as the installer (it used a separate list of 15 openings with different names).
- The README is rewritten for first-time users (what you need, a five-step quick start, guides, daily commands). The old HTTPS recipes (Caddy, Cloudflare Tunnel, host nginx, Tailscale Funnel) are removed: hosting ChessLoop on the internet is not covered (one of them, `caddyserver.com/get`, never worked). `chessloop/README.md` now points to the main README and `docs/development.md`.
- The installer's "from anywhere on the internet" choice now links to the README's "Not covered" section instead of an HTTPS guide.
- **Update rewritten:** shows the installed and the new version and the new `CHANGELOG.md` lines; follows the branch the install is on (or `CHESSLOOP_REF`) instead of always `main`; saves a real backup first and stops if that fails (`--no-backup` overrides); puts files you changed by hand aside with `git stash` instead of failing; builds, starts and waits until healthy; if the new version doesn't build or doesn't start, goes back to the previous version (and, if it had started, to the data from the pre-update backup) and says why. When there is nothing new it still starts a stopped ChessLoop. Works with `--yes` and `--force`. It also tidies up after older versions: removes the broken `chessloop` systemd service, turns on Docker's start at boot if it is off, offers to remove the extra empty `chessloop-data` volume (one with files in it is never touched, only explained), deletes the empty `backup-pre-update-*.tar.gz` files older updates left, offers to remove or lock the old default admin, offers to create an admin when there is none, and says when email verification is still on without email.
- **Uninstall rewritten:** lists exactly what each level removes and keeps, with sizes, before asking. Level 1 removes the containers; level 2 also ChessLoop's images (including old builds left by updates); level 3 also the data volume, `/opt/chessloop`, the `chessloop` command and, on Windows, the keep-running settings (asked separately; only the values the installer wrote). Level 3 offers a final backup (with the settings file) and asks you to type `DELETE`. `--yes --level N` works (level 3 also needs `CHESSLOOP_ALLOW_DATA_DELETE=1`). Docker stays installed and the command to remove it is shown, as are the general images older versions downloaded (`nginx:1.27-alpine`, `alpine`), which are kept because other programs may use them.
- Admin-panel backups are made with SQLite's backup API (a consistent copy while ChessLoop writes) and are private: the backup folder is mode 700 and every backup file mode 600, also uploads and files made by older versions.
- The installer no longer creates a systemd unit; Docker's own start at boot (`restart: always`) brings ChessLoop back. (The unit made by older installers is dealt with in Update, a later change.)
- The installer shows the right address for the access you chose: no LAN address for a "this computer only" install.
- Docker from the Ubuntu or Debian package (`docker.io`) without the compose plugin is repaired with the matching package instead of a standalone binary.
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
- No CORS headers by default (the UI and API share one origin); nginx no longer adds `Access-Control-Allow-Origin: *`, and the installer no longer writes `CORS_ORIGINS=*` when no domain is given. The backend ignores `CORS_ORIGINS=*` (with a startup warning), so installs that already have it in `.env` stop sending wildcard CORS with credentials after an update.
- Email links default to `https://DOMAIN` (or `http://localhost:PUBLIC_PORT`), and the sender to the `SMTP_USER` address, instead of `no-reply@chessloop.local`, which real mail servers reject.
- nginx's config is built into its own image (`chessloop/nginx/Dockerfile`) instead of bind-mounted, so the proxy also starts when Docker brings containers back at boot before the file is available (Docker Desktop on Windows).
- Health checks work: the backend uses Python instead of `curl` (not in the image), nginx checks `127.0.0.1` instead of `localhost` (IPv6 in Alpine).
- Base images: Node 24 LTS (`npm ci`) for the frontend build, `nginx:1.30-alpine`, `python:3.12.15-slim-trixie`. The backend image no longer installs `build-essential` (784 MB → 353 MB).
- The frontend's `index.html` is served with `Cache-Control: no-cache` and hashed assets as immutable, so browsers load a new version right after an update.
- `docker-compose.yml` is labelled development-only, requires `JWT_SECRET`, binds to `127.0.0.1` and uses the same nginx image.
- `.gitignore` now also ignores `*.db*`, `*.tsbuildinfo`, `passdata/`, `backups/`, `runs/` and `*.tar.gz`.

### Fixed
- **Signing in as a different person no longer shows the previous person's libraries and stats.** The browser kept its cached answers after Logout, so the next account on the same tab saw the last account's data for up to 30 seconds (until a reload). The cache is now cleared when someone signs out or a different user signs in. Found by Phase 11 fresh-eyes testers.
- A first practice session no longer fails with a misleading message: when **Learned/Active lines only** is on and no line is marked Learned, the message now says so and what to do. The message also scrolls into view on a short window.
- `chessloop update` explains its "Rebuild it anyway?" question.
- Opening a public library on Discover showed no lines (the server answered 500 because each line lacked its `is_learned` field). The lines now load.
- `chessloop install|update|backup|restore|uninstall` run without a terminal and without `--yes` (cron, a script, `ssh host chessloop backup`) now stop with only the two "use --yes" lines, instead of adding "Something went wrong" and an issue link.
- Update's "Backup saved" archive was empty (86 bytes) and created an extra, empty `chessloop-data` volume, because it looked for the wrong volume name; level-3 uninstall said "Could not remove volume" and left the database. Every path now uses the real volume `chessloop_chessloop-data` (compared by exact name).
- Restoring a backup in Admin → Backups emptied the Backups list: entries whose files still exist are now kept.
- The `chessloop` systemd service older installers wrote restarted every 10 seconds with an error; Update and Uninstall remove it (Docker brings ChessLoop back at boot without it). Uninstall now says that every level removes it.

### Removed
- `manage.sh`: it ran a second, incompatible set of containers with a different data folder, so following it on a normal install made all accounts seem to disappear, and it published port 8090 to the network. Its commands are now `chessloop status | start | stop | restart | logs | backup | restore | update`.
- The "testing" nginx headers: wildcard CORS, `X-Frame-Options: ALLOWALL` and a CSP that allowed everything.
- The `/chess/` subpath routes in nginx: the frontend always calls `/api` and loads its files from `/`, so ChessLoop never worked under a subpath.
- The public `/docs` and `/openapi.json` routes in the Docker stack.
- The obsolete `version:` key in both compose files (Compose printed a warning on every command).
- Developer-only and personal files: root `CLAUDE.md`, the committed `chessloop.db`, `passdata/`, `scripts/` (one-off maintenance scripts with personal paths and a compiled `__pycache__`), and `chessloop/frontend/tsconfig.tsbuildinfo`.

### Upgrading from an earlier install
- Run Update with the new script once: `curl -fsSL https://raw.githubusercontent.com/antonizick/chessloop/main/deploy.sh | bash -s -- update` (or `bash /opt/chessloop/deploy.sh` and choose Update; if that older script runs, run Update a second time so the new one tidies up). Your data stays in the `chessloop_chessloop-data` volume.
- If the install was made before 2026-10, Update offers to remove the old `admin@example.com` account (password `admin`) and to create your own admin account.
- If email isn't set up but an admin once opened Admin → System settings, new accounts may still be asked to confirm their email; Update says so. Fix it in Admin → System settings with "Use the server setting".
- `manage.sh` is gone; use the `chessloop` command. Archives made with the old README's `docker run … tar` command of `chessloop-data` were empty (they named the wrong volume); make a new backup with `chessloop backup`.
