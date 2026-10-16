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
- Optional two-factor authentication uses TOTP (authenticator apps).
- **Backups contain password hashes and MFA secrets.** Store them like passwords and do not share them or attach them to issues.
- Never post your `.env` file, `JWT_SECRET`, or database in a public place.
