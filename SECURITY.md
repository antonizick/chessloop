# Security Policy

## Supported versions
ChessLoop has not made a tagged release yet. Until it does, only the latest commit on `main` receives security fixes.

## Reporting a vulnerability
Please report security problems **privately**. Do not open a public issue.

1. Go to <https://github.com/antonizick/chessloop/security/advisories/new> (the "Security" tab, then "Report a vulnerability").
2. Describe what you found, how to reproduce it, and what an attacker could do.

You will get a reply through the same GitHub thread. ChessLoop is maintained by one person in their spare time, so please allow some days for a first answer.

**In scope:** the backend API, authentication (password, JWT, TOTP), the installer scripts (`deploy.sh`, `manage.sh`), the Docker/nginx configuration, and backup/restore.
**Out of scope:** attacks that need an already-compromised server or admin account, missing hardening on a server you exposed to the internet without HTTPS, and vulnerabilities in third-party software that ChessLoop merely depends on (report those upstream).

## Security model
- ChessLoop is **self-hosted**. By default it is meant to be reached on `localhost` or your home/office network. If you expose it to the internet, put HTTPS in front of it.
- Sign-in uses passwords hashed with bcrypt and short-lived JWT tokens signed with `JWT_SECRET`. Keep `JWT_SECRET` private; anyone who has it can forge sign-ins.
- **No default credentials.** There is no built-in admin; you create it with `seeds/create_admin.py`, which takes the password from stdin, an environment variable or a hidden prompt, never from the command line.
- **Password rule:** at least 12 characters (at most 128), and not built on a common word such as "password", "admin" or "chessloop" (with digits, symbols or letter swaps like `0` for `o` around it). The same rule applies to registration, change password, password reset, accounts an admin creates or resets, and `create_admin.py`. Existing passwords keep working until they are changed.
- **Changing or resetting a password signs you out everywhere.** Each account has a token version that is stored in every sign-in token; a password change, a reset through the emailed link, or an admin setting a new password increments it, so all earlier access and refresh tokens stop working at once. The device that made the change receives new tokens.
- Wrong current passwords on **Settings → Change password** are rate limited: 5 failures per account and per IP address in 15 minutes, held in memory (the counter resets when the backend restarts).
- **Email verification** is on only when the server can send email (`EMAIL_VERIFICATION=auto`, the default; `on`/`off` force it). An admin cannot switch it on without SMTP, because nobody could then verify. Accounts an admin creates are verified.
- Optional two-factor authentication uses TOTP (authenticator apps).
- **Backups contain password hashes and MFA secrets.** Store them like passwords and do not share them or attach them to issues.
- Never post your `.env` file, `JWT_SECRET`, or database in a public place.
