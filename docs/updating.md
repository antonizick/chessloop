# Updating ChessLoop

An update gets the newest version of ChessLoop and keeps your data.

```bash
chessloop update
```

If the `chessloop` command is not found (an install made before it existed), use `bash /opt/chessloop/deploy.sh update`. That update adds the command.

## What happens

1. It shows the installed version, fetches the new one (an install made from a release follows the newest release; an older install made from the development version follows its branch, normally `main`) and prints what is new from `CHANGELOG.md`. If there is nothing new, it says "ChessLoop is up to date" and asks **Rebuild it anyway?** Press `Enter` to say no. (*Rebuild* means build the same version again. You only need that if something is broken.) Add `--force` to rebuild without being asked.
2. **It saves a backup first** in `~/chessloop-backups`. If that fails, nothing is changed. (`--no-backup` skips this; don't, unless you know why.)
3. Files of ChessLoop that you edited by hand are put aside with `git stash`. Your settings file `.env` is never touched.
4. It builds and starts the new version and waits until it is healthy.
5. **If the new version does not build or start, it goes back by itself** to the previous version and, if needed, to the data in the backup. You see:

   ```text
   ✗  The update didn't work: the new version didn't build.
   ✓  ChessLoop is running the previous version again, de3c5c5 (2026-10-17), with your data.
      Full log: /home/sam/chessloop-update-20261018-000127.log
   ```

   Try again later, and attach the log to an [Install problem](https://github.com/antonizick/chessloop/issues/new?template=install_problem.yml) issue.
6. It tidies up after very old versions: the old `chessloop` systemd service that never worked, the empty extra `chessloop-data` Docker volume, and, only if you are updating a very old install, the old `admin@example.com` account with the password `admin`. Newer installs never had it. It asks whether to remove or lock that account, and creates an admin if there is none. On Windows it offers the [keep-alive setting](install/windows-wsl2.md#step-6-keep-chessloop-running).

If the extra `chessloop-data` volume has files in it, the update leaves it alone and tells you how to look inside. Your real data is in `chessloop_chessloop-data`.

## No questions

```bash
chessloop update --yes
```

## Going back

If you want an older version, restore a backup made before the update: see [Backup and restore](backup-restore.md). Or ask for help in an issue.
