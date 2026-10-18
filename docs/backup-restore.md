# Back up and restore ChessLoop

A *backup* is a copy of everything ChessLoop knows: accounts, libraries, lines and practice progress. If your disk fails, or you delete ChessLoop by mistake, a backup lets you get it all back. You can also use a backup to move ChessLoop to another computer.

**Make a backup now, and again before anything risky.** `chessloop update` makes one for you first.

## Quick version

```bash
chessloop backup
```

The file lands in `~/chessloop-backups`. **Copy it to another computer or a USB stick.** A backup on the same disk is lost with the disk. On a Linux desktop, open your home folder in the file manager, open `chessloop-backups`, and drag the newest `.tar.gz` file onto the stick.

On Windows, type these in an Ubuntu window (see the [Windows guide](install/windows-wsl2.md#everyday-use-on-windows)).

## What a backup contains

| In the backup | Not in the backup (unless you ask) |
|---|---|
| Every account, with password hashes and two-factor secrets | The settings file `.env` (your secret key, your email password) |
| Libraries, lines, notes | |
| Practice progress and review history | |
| The backups you made in the Admin panel | |
| A checksum so you can tell if the file is damaged | |

**A backup is private.** Anyone who has the file can try to crack the passwords in it. ChessLoop saves backups so that only your user can read them (mode 600). Do not put a backup in a public folder, an email or a shared drive. If you copy it to a USB stick, keep the stick safe.

## Back up from the command line

```bash
chessloop backup
```

ChessLoop keeps running while it makes a consistent copy of its database. You see something like this:

```text
  ✓  Backup saved: /home/sam/chessloop-backups/chessloop-20261018-000125.tar.gz (19.0 KB)
     It holds accounts: 3, libraries: 18, lines: 145.
     Its checksum is in chessloop-20261018-000125.tar.gz.sha256: keep the two files together.
```

The number of accounts is one more than the people you made: it counts `seedbot`, the built-in account that owns the public starter libraries.

Before it starts, ChessLoop asks **Also put the settings file in the backup? [y/N]**. The *settings file* (`.env`) holds your secret key and email password. Press `Enter` to say no. That is right for nearly everyone.

Keep the `.tar.gz` file and its `.sha256` file together. The second one lets ChessLoop check that the first was not damaged.

Options:

| Command | What it does |
|---|---|
| `chessloop backup` | Backs up to `~/chessloop-backups`. |
| `chessloop backup --with-settings` | Also saves the settings file `.env`. It holds your secret key and email password, so treat the backup like a password. You only need this to set up the same settings on another computer. |
| `chessloop backup /path/to/file.tar.gz` | Saves to the file you name. |

## Restore from the command line

```bash
chessloop restore
```

It lists your newest backups. Type the number of one (the newest is 1), or 0 to type the path of another file. Or name the file yourself:

```bash
chessloop restore ~/chessloop-backups/chessloop-20261018-000125.tar.gz
```

Restore:

1. Checks the file against its checksum and checks the database inside it.
2. Shows how many accounts, libraries and lines the backup has, and how many ChessLoop has now. **Those now are replaced.**
3. Asks you to confirm.
4. Saves a safety backup of the current data first (its name ends in `-before-restore`).
5. Puts the backup's data in place, starts ChessLoop and checks that every table has the same number of rows as the backup.

If anything looks wrong, the safety backup is your way back: `chessloop restore` with that file.

It also accepts a `full_….db` file that you downloaded from the Admin panel (see below).

## Move ChessLoop to a new computer

1. **On the old computer:** `chessloop backup`. Copy the `.tar.gz` file and the `.sha256` file to a USB stick.
2. **On the new computer:** [install ChessLoop](install/linux.md) as usual. Use any admin email.
3. Copy the two files to the new computer, for example into your home folder.
4. Run `chessloop restore chessloop-20261018-000125.tar.gz` (with your file's name).
5. Open ChessLoop and sign in **with an account from the backup**. The admin you created during the install is replaced by the backup's accounts.

Everybody has to sign in again on the new computer, because each install has its own secret key. Their passwords are the same as before. Your settings on the new computer (port, email) were not changed. To read the old settings, if you used `--with-settings`:

```bash
tar -xzOf chessloop-20261018-000125.tar.gz settings.env
```

## Back up in the Admin panel

In ChessLoop, open the **Admin panel** (the gear icon in the sidebar, admins only), then the **Backups** tab.

- **Create** a named backup at any time. Choose what it holds:
  - **full**: everything (accounts, libraries, progress).
  - **content**: libraries and lines only. You can load it into another ChessLoop.
  - **progress**: practice cards and review history only.
- **Download** a backup to your computer.
- **Restore** from any backup in the list, without stopping ChessLoop.

ChessLoop keeps the 10 newest backups and deletes older ones. These backups live inside ChessLoop's data, so **they are lost if the data is lost**. Download the ones you want to keep.

## How often?

Back up before an update (the update does it for you), before you uninstall, and then whenever you have added things you would hate to lose. Once a week is a good habit if you use ChessLoop daily.

To back up on a schedule, ask a technical friend to add `chessloop backup` to `cron`. ChessLoop does not do this for you.

## If a restore fails

Read the message. Restore stops before it changes anything if the file is damaged, does not match its checksum, or is not a ChessLoop backup. [Troubleshooting](troubleshooting.md#a-restore-fails) lists the messages.
