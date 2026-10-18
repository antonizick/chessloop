# Configuration

ChessLoop's settings live in one file, the *settings file*: `/opt/chessloop/chessloop/.env`. The installer wrote it for you. This page explains every setting in plain English.

## How to change a setting

1. Open the file in a simple editor. In a terminal:

   ```bash
   nano /opt/chessloop/chessloop/.env
   ```

   Move with the arrow keys. Save with `Ctrl` + `O`, then `Enter`. Quit with `Ctrl` + `X`.
2. A line that starts with `#` is a comment and is ignored. To use a setting, remove the `#` and the space it leaves, and write your value after the `=`.
3. Apply the change. `chessloop restart` is **not** enough, because it does not read the file again. Run:

   ```bash
   cd /opt/chessloop/chessloop
   sudo docker compose -f docker-compose.prod.yml up -d
   ```

4. Run `chessloop status` to check that ChessLoop is up.

**Keep `.env` private.** It holds your secret key and, if you set up email, your email password. Only your user can read it (mode 600). Never post it in an issue. `chessloop update` never changes it.

## All settings

### Required

#### `JWT_SECRET`
The secret key that protects everyone's sign-in. The installer made a strong one. ChessLoop refuses to start with the example value or with anything shorter than 32 characters. If you change it, everybody has to sign in again. To make a new one, run `openssl rand -base64 32` and paste the result after the `=`. Don't type the command into the file: the file does not run commands.

### Where ChessLoop listens

#### `PUBLIC_PORT`
The port in the address, as in `http://localhost:8090`. Default `8090`.

#### `BIND_ADDR`
Who can connect.

- `127.0.0.1` (default): only this computer.
- `0.0.0.0`: also other devices on your network. Use it only on a network you trust: the connection is not encrypted.

This is what the installer's "Where will you open ChessLoop?" question sets (choice 1 gives `127.0.0.1`, choice 2 gives `0.0.0.0`). On Windows, other devices also need the [WSL steps](install/windows-wsl2.md#optional-use-chessloop-from-your-phone).

#### `DOMAIN`
A domain name, if you put ChessLoop behind your own HTTPS server. Used for links in emails. Leave it empty. [Hosting on the internet is not covered.](../README.md#not-covered-hosting-chessloop-on-the-internet)

#### `FRONTEND_URL`
The web address people use to open ChessLoop, used for links in emails. Default: `http://localhost:PUBLIC_PORT`. For a home network, set it to the address your other devices use, for example `http://192.168.1.20:8090`.

#### `CORS_ORIGINS`
Other web sites allowed to call ChessLoop from a browser. Leave it empty: ChessLoop's own pages don't need it. A `*` is ignored.

### Email

Without email, ChessLoop sends nothing: new accounts can sign in at once, and the admin verifies accounts and sets passwords in **Admin panel → Users**. To turn email on you need your mail provider's *SMTP* details (their help pages list them). The installer can ask for them and send a test message; or set them here.

| Setting | Meaning |
|---|---|
| `SMTP_HOST` | Your mail provider's server, for example `smtp.gmail.com`. Empty means no email. |
| `SMTP_PORT` | Usually `587`. Use what your provider says. |
| `SMTP_USER`, `SMTP_PASSWORD` | Your login. For Gmail use your address and an *app password*, not your normal password. |
| `SMTP_FROM` | The sender shown on emails, for example `ChessLoop <chess@example.com>`. Many providers only accept their own address. |
| `SMTP_USE_TLS` | `true` (default) encrypts the connection with STARTTLS. Use `false` only if your provider says so. |

#### `EMAIL_VERIFICATION`
`auto` (default): new accounts must click an emailed link only if `SMTP_HOST` is set. `on`: always require it (needs email). `off`: never. An admin's choice in **Admin panel → System settings** overrides this.

#### `EMAIL_MX_CHECK`
`false` (default). `true` checks at registration that the email's domain can receive mail. It needs internet DNS.

### Advanced

| Setting | Meaning |
|---|---|
| `ACCESS_TTL_MIN` | Minutes a sign-in lasts before it is quietly renewed. Default `15`. |
| `REFRESH_TTL_DAYS` | Days before someone must sign in again. Default `30`. |
| `LICHESS_API_TOKEN` | Reserved. This version does not use it: the starter libraries and "Import from Lichess" on a library work without it. It is a secret like a password if you ever set it. |

## Settings only the installer uses

The installer takes `CHESSLOOP_*` variables for unattended installs (`bash deploy.sh --help` lists them). They are not part of `.env`.
