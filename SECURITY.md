# Security Policy

## Supported versions
ChessLoop has not made a tagged release yet. Until it does, only the latest commit on `main` receives security fixes.

## Reporting a vulnerability
Please report security problems **privately**. Do not open a public issue.

1. Go to <https://github.com/antonizick/chessloop/security/advisories/new> (the "Security" tab, then "Report a vulnerability").
2. Describe what you found, how to reproduce it, and what an attacker could do.

You will get a reply through the same GitHub thread. ChessLoop is maintained by one person in their spare time, so please allow some days for a first answer.

**In scope:** the backend API, authentication (password, JWT, TOTP), the installer and `chessloop` command (`deploy.sh`), the Docker/nginx configuration, and backup/restore.
**Out of scope:** attacks that need an already-compromised server or admin account, missing hardening on a server you exposed to the internet without HTTPS, and vulnerabilities in third-party software that ChessLoop merely depends on (report those upstream).

## Security model
- ChessLoop is **self-hosted**. By default it is meant to be reached on `localhost` or your home/office network. If you expose it to the internet, put HTTPS in front of it.
- Sign-in uses passwords hashed with bcrypt and short-lived JWT tokens signed with `JWT_SECRET`. Keep `JWT_SECRET` private; anyone who has it can forge sign-ins.
- **No default credentials.** There is no built-in admin; you create it with `seeds/create_admin.py`, which takes the password from stdin, an environment variable or a hidden prompt, never from the command line.
- **Password rule:** at least 12 characters (at most 128), and not built on a common word such as "password", "admin" or "chessloop" (with digits, symbols or letter swaps like `0` for `o` around it). The same rule applies to registration, change password, password reset, accounts an admin creates or resets, and `create_admin.py`. Existing passwords keep working until they are changed.
- **Changing or resetting a password signs you out everywhere.** Each account has a token version that is stored in every sign-in token; a password change, a reset through the emailed link, or an admin setting a new password increments it, so all earlier access and refresh tokens stop working at once. The device that made the change receives new tokens.
- **Sign-in** is rate limited: 10 wrong passwords per email address and 30 per IP address in 15 minutes, then HTTP 429 until the window passes. A correct sign-in clears the account's count.
- Wrong current passwords on **Settings → Change password** are rate limited: 5 failures per account and per IP address in 15 minutes. **Two-factor codes** are limited too: 5 wrong codes per account in 15 minutes, at sign-in and when turning two-factor off. The counters are held in memory and reset when the backend restarts. The address is the browser's, which nginx passes on in `X-Real-IP`.
- **Email verification** is on only when the server can send email (`EMAIL_VERIFICATION=auto`, the default; `on`/`off` force it). An admin cannot switch it on without SMTP, because nobody could then verify. Accounts an admin creates are verified.
- Optional two-factor authentication uses TOTP (authenticator apps).
- **Backups contain password hashes and MFA secrets.** Store them like passwords and do not share them or attach them to issues. `chessloop backup` writes them with mode 600 into `~/chessloop-backups` (folder mode 700), with a SHA-256 checksum file; the settings file (`.env`, with `JWT_SECRET`) is included only when you ask for it (`--with-settings`). Admin-panel backups are kept inside the data volume, folder mode 700, files mode 600. Restore checks the checksum and the database's integrity before it changes anything, and saves a safety backup of the current data first.
- Never post your `.env` file, `JWT_SECRET`, or database in a public place.
- **`JWT_SECRET` is checked at startup.** The backend container refuses to start when the secret is empty, shorter than 32 characters, the `.env.example` placeholder or another published example, or a shell command such as `$(openssl rand -base64 32)` (a `.env` file does not run commands).

- **Containers:** the backend runs as an unprivileged user (uid 10001) with no Linux capabilities. A short-lived `data-owner` service hands data files created by older versions (which ran as root) to that user before the backend starts. All containers run with `no-new-privileges`.
- **Installer downloads:** Docker's apt signing key must have the fingerprint `9DC8 5822 9FC7 DD38 854A E2D8 8D81 803C 0EBF CD88`, or the installer stops before trusting it; apt then checks every Docker package against it.
- **Browser error reports** (`POST /api/logs/client`, no sign-in needed) are capped: each field is kept on one line and shortened, 30 reports per address per minute, request body 32 KB, and the `frontend.log` file rotates at 1 MB.
- **Who may change a library:** its owner or an admin. (Before 2026-10, any account named `nick` could too.)
- **Scanners in CI:** Trivy fails the build on a fixable HIGH or CRITICAL vulnerability in any image, pip-audit on any known vulnerability in the backend's Python packages; `npm audit` is reported. See [docs/THREAT-MODEL.md](docs/THREAT-MODEL.md) for the full threat model and the risks that are accepted on purpose.

## Network model and headers
- Only the nginx container publishes a port: `PUBLIC_PORT` (default 8090) on `BIND_ADDR`, which defaults to `127.0.0.1` (this computer only). Set `BIND_ADDR=0.0.0.0` to let other devices on your network connect. The backend and frontend containers are reachable only inside the Docker network.
- The web UI and the API share one origin, so no CORS is needed and none is sent by default. `CORS_ORIGINS` adds explicit origins for another front end; `*` is ignored.
- nginx sends `Content-Security-Policy` (scripts and API calls only from ChessLoop itself; inline styles and `https:`/`data:` images allowed for admin-written banners, the board and the MFA QR code; no framing by other sites), `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin` and a `Permissions-Policy` that turns off camera, microphone, location, payment and USB. It does not send `Strict-Transport-Security`: HTTPS is terminated by your reverse proxy, which should add it.
- Behind a TLS proxy, nginx passes the proxy's `X-Forwarded-Proto` on to the backend.
- The interactive API docs (`/docs`, `/openapi.json`) are not published by the Docker stack.
- Uploads are limited to 10 MB, except restoring a backup file (200 MB) and browser error reports (32 KB).
