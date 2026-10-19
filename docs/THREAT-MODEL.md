# ChessLoop threat model

This page explains what in a ChessLoop install is worth protecting, who could reach it, and what protects it. It is for people who review or change ChessLoop's code. If you only use ChessLoop, read [SECURITY.md](../SECURITY.md) instead.

Last reviewed: 2026-10-18, on `main` after the hardening changes listed in the [CHANGELOG](../CHANGELOG.md).

## Scope

ChessLoop is for **personal, private installs**. The installer offers three places to open ChessLoop. This model covers the first two, plus Windows:

| Access mode | What it means | Who can connect |
|---|---|---|
| **Only on this computer** (default) | nginx listens on `127.0.0.1:PUBLIC_PORT` | Programs on this computer, including its browser |
| **Other devices on my home network** | nginx listens on `0.0.0.0:PUBLIC_PORT`, plain HTTP | Anyone on the same network (family, guests, other devices) |
| **Windows 11 + WSL 2** | as above, inside Ubuntu on WSL; `localhost` forwarding to Windows; optional mirrored networking for phones | The Windows user; with mirrored networking and the firewall rule, the home network |

**Out of scope:** hosting ChessLoop on the internet. The third installer choice ("the internet with my own domain") only binds to `127.0.0.1` and points to the README's "Not covered" section. There is no TLS setup, no internet-facing rate limiting, no WAF and no hardening checklist for public hosting. If you put ChessLoop on the internet, you take on those risks yourself, and you need at least HTTPS in front of it.

## What is worth protecting

| Asset | Where it lives | Why it matters |
|---|---|---|
| Accounts and password hashes (bcrypt) | `chessloop.db` in the Docker volume `chessloop_chessloop-data` | Offline guessing; reused passwords |
| TOTP (two-factor) secrets | same database, in plain form (they must be readable to check codes) | Whoever has them can make valid codes |
| `JWT_SECRET` | `/opt/chessloop/chessloop/.env` (mode 600) and the backend's environment | Whoever has it can sign in as any user |
| Backups | `~/chessloop-backups/*.tar.gz` (600, folder 700); Admin-panel backups in the volume (`backups/`, 700/600) | They hold everything above (and `.env` only with `--with-settings`) |
| SMTP password (optional) | `.env` | The mail account it belongs to |
| The host itself | — | The installer uses `sudo`; a user in the `docker` group is effectively root |
| Users' training data | the database | Privacy, and the effort put into it |

## Entry points

| Entry point | Who can reach it | Notes |
|---|---|---|
| The installer, run as `curl … \| bash` | Whoever controls what is downloaded: GitHub, the network path, Docker's servers | Runs as the user; `sudo` only for system steps (below) |
| `chessloop` command (`/usr/local/bin/chessloop` → `/opt/chessloop/deploy.sh`) | Local users who can run it; it needs `docker` group or `sudo` for anything real | Backup, restore, update, uninstall |
| The web UI and API through nginx | See "Who can connect" per access mode | One origin; no CORS by default |
| Unauthenticated API routes | same | `/api/auth/register`, `/login`, `/login/mfa`, `/refresh`, `/verify-email`, `/resend-verification`, `/forgot-password`, `/reset-password*`, `/api/auth/config`, `/api/health`, `/api/public/*`, `POST /api/logs/client` |
| Admin API (`/api/admin/*`) | Signed-in admins only | Users, backups (upload, restore, download), openings, banner and popup HTML, logs |
| Docker socket | root and `docker` group members on the host | Full control of the host |
| Backups | Whoever can read the backup folder or a copied file | Restoring a backup replaces every account |
| SMTP (outgoing only) | The mail server and the network path to it | Verification and reset links; `SMTP_USE_TLS=true` by default |
| Lichess Explorer (outgoing, admin search only) | Lichess and the network path | Sent only if the admin sets `LICHESS_API_TOKEN` (a no-permission token, as a Bearer header, never logged); failures are shown, not silent |

## Trust boundaries

1. **Browser ↔ nginx.** Plain HTTP. In "this computer only" mode the traffic never leaves the machine. In home-network mode, anyone on the network can watch or change the traffic, including sign-in passwords and tokens. That is accepted for a trusted home network (below). If the computer has a public IP address, the installer warns before you choose home-network mode (S3).
2. **nginx ↔ backend and frontend.** A private Docker network. The backend port 8000 is not published. nginx overwrites `X-Real-IP` with the real peer address, so the backend can trust it for rate limits.
3. **Backend ↔ data volume.** The backend runs as uid 10001 with no Linux capabilities and `no-new-privileges`. A one-shot `data-owner` service (root, `CHOWN` and `DAC_READ_SEARCH` only, no network) hands an older root-owned volume to that user before the backend starts.
4. **Installer ↔ the internet.** It downloads Docker's signing key and packages, clones the repository over HTTPS, and pulls base images from Docker Hub. Docker's key must have the known fingerprint `9DC8 5822 9FC7 DD38 854A E2D8 8D81 803C 0EBF CD88`, or the installer stops before apt trusts it. After that, apt checks every Docker package's signature against the key.
5. **Installer ↔ root.** `sudo` is used for: apt, `/etc/apt/keyrings` and Docker's `.sources` file, `usermod -aG docker`, `systemctl enable docker`, creating `/opt/chessloop`, the `/usr/local/bin/chessloop` link, and Docker commands until the new group applies. Each use says why. A background `sudo -n -v` keeps the sudo timestamp fresh and ends with the script.
6. **WSL ↔ Windows.** With your OK, the installer writes to your Windows `.wslconfig` (`instanceIdleTimeout=-1`, and `networkingMode=mirrored` on request) and a `Startup\ChessLoop.cmd` that runs `wsl.exe` at sign-in. It needs no admin rights. It keeps a timestamped copy of `.wslconfig` first, and Uninstall removes only the values it wrote.

## Threats and controls

| # | Threat | Control | Status |
|---|---|---|---|
| T1 | Default or guessable admin login | No built-in admin. `create_admin.py` reads the password from stdin or a hidden prompt (never argv). A generated password is shown once. The 12-character rule with a denylist applies everywhere. Update deletes or locks the old `admin@example.com`/`admin` account. | Done (S1) |
| T2 | Forged sign-ins with a public or weak `JWT_SECRET` | 32 random bytes from `openssl rand`. The backend refuses empty, short, example and `$(…)` secrets. `.env` is mode 600. | Done (S2) |
| T3 | Secrets in logs or on screen | The admin password is never in the install log (checked on every lab install); `JWT_SECRET` is never printed; app logs carry no tokens. The browser error log (`POST /api/logs/client`, no sign-in) keeps each field on one line with a length cap, takes 30 entries per address per minute, and rotates at 1 MB (2 old files); nginx limits its body to 32 KB. | Done |
| T4 | Exposure on a network by accident | Default `BIND_ADDR=127.0.0.1`; home-network mode is an explicit choice with a public-IP warning; on WSL the internal address is never printed. | Done (S3) |
| T5 | Clickjacking, script injection, cross-site calls | CSP (`script-src 'self'`), `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`; no wildcard CORS (`*` ignored); admin HTML sanitised with DOMPurify; `/docs` and `/openapi.json` not published. | Done (S4) |
| T6 | Stolen backup | Backups are mode 600 in a 700 folder; `.env` only on request; the docs say they hold password hashes and TOTP secrets. | Done (S5) |
| T7 | Tampered download (installer, Docker packages, images) | Verify-before-run steps in the install guides; Docker key fingerprint pinned; apt signatures; HTTPS for the clone; base images pinned to a supported line and scanned in CI. `curl \| bash` from `main` is still the documented quick path. | Done, with the rest accepted (S6) |
| T8 | Compromised container or app bug escalating | Backend non-root, no capabilities, `no-new-privileges`; nginx and frontend use the official nginx images (master process root, workers unprivileged) with `no-new-privileges`. | Done (S7); nginx-as-root accepted |
| T9 | Online password guessing | bcrypt, the 12-character rule. Sign-in: 10 wrong passwords per email address and 30 per address in 15 minutes (a correct sign-in clears the account count). Change-password: 5 wrong attempts per account and per address in 15 minutes. Two-factor codes: 5 wrong codes per account in 15 minutes, at sign-in and when turning it off. | Done |
| T10 | Session theft lasting forever | Access tokens 15 min, refresh 30 days; a password change or reset bumps the account's token version, so every older token stops working. | Done |
| T11 | Privilege by username | A user named `nick` used to be able to read and publish anyone's libraries. Removed: only the owner or an admin. | Done |
| T12 | Path tricks in uploads and restores | Admin upload names are reduced to `[A-Za-z0-9._-]`; `chessloop restore` extracts only `manifest.json`, `chessloop.db` and `backups/<name>` (no `/` or `..`); it checks the checksum and integrity, and makes a safety backup first. `rm -rf` of the install folder is refused for system or home folders. | Done |
| T13 | Vulnerable dependencies | CI: Trivy fails on a fixable HIGH or CRITICAL in any image; pip-audit fails on any known Python vulnerability; `npm audit` reported; Dependabot on. | Done |
| T14 | Secrets committed to the repository | gitleaks over the full history in CI; `.gitignore` covers `.env`, databases and backups. | Done |
| T15 | Unreviewed change reaching `curl \| bash` users | Branch protection on `main` with the CI checks required, no force-push (admins can bypass). | See CONTRIBUTING |

## Accepted risks

These are known and deliberately not fixed, because they don't matter for a private install, or because fixing them costs more than it saves.

- **Plain HTTP on the home network.** Anyone on that network can read sign-in traffic. A trusted home network is the premise of that mode. Use "only this computer" if the network isn't trusted.
- **`/auth/verify-email` signs the user in.** The link is single-use (an already-verified account is refused), expires after 24 hours, and goes only to the account's inbox.
- **A password reset by email can switch off two-factor.** The user chooses that on the reset page. It means access to the inbox is enough to take the account. This keeps people who lost their phone from being locked out on a server without recovery codes.
- **TOTP secrets are stored readable.** They must be, to check codes. Backups are protected instead (T6).
- **The `docker` group is root-equivalent.** The installer adds the user to it, as Docker's own instructions do, so that `chessloop` commands work without `sudo`.
- **nginx master processes run as root** inside their containers (the official images; workers drop privileges). Switching to unprivileged images would change ports and the image source.
- **React Router advisories** (two moderate, need v7): they concern user-controlled link targets and server rendering, and ChessLoop has neither. `npm audit` stays advisory in CI until the upgrade.
- **Debian packages with no fix yet** in the backend base image are not counted by the image scan (`--ignore-unfixed`). They are fixed when Debian ships a fix and the image is rebuilt.
- **Rate limits are in memory.** They reset when the backend restarts. ChessLoop runs one worker, so one counter is enough.
- **`curl | bash` from `main`.** It is the quick path, and the guides show how to download, read and run instead. Installing a release tag instead of `main` is being considered for the first release.

## Source code (AGPL-3.0 section 13)

ChessLoop is licensed under the GNU AGPL-3.0-or-later. The source code of every version is available at <https://github.com/antonizick/chessloop>. If you run a modified version as a service for other people, you must offer them its source. See [NOTICE](../NOTICE).
