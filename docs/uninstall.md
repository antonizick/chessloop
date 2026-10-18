# Uninstalling ChessLoop

```bash
chessloop uninstall
```

(or `bash /opt/chessloop/deploy.sh uninstall`). It shows **exactly** what it will remove, with sizes, before it asks you to confirm. There are three levels:

| Level | Removed | Kept |
|---|---|---|
| **1. Stop ChessLoop** | Its containers. | Your data, settings, files and Docker images. `chessloop start` brings it back. |
| **2. Also the images** | Containers and ChessLoop's Docker images. | Your data, settings, files. `chessloop start` rebuilds the images. |
| **3. Everything** | Containers, images, the data volume (all accounts, libraries and progress), `/opt/chessloop` with the settings file, the `chessloop` command; on Windows, the keep-alive settings (it asks). | Your backups in `~/chessloop-backups`, your logs, and Docker itself. |

Level 3 offers a **final backup** first (with the settings file) and asks you to type `DELETE`. It cannot be undone. A volume named `chessloop-data` that has files in it is never deleted: it is not ChessLoop's own data, and the installer tells you where to look.

Docker stays installed because other programs may use it. The installer prints the command to remove it if nothing else does.

Unattended: `chessloop uninstall --yes --level 1` (level 3 also needs `CHESSLOOP_ALLOW_DATA_DELETE=1`).

To remove Ubuntu from Windows as well, that is a separate step in Windows (`wsl --unregister`). It deletes everything inside that Ubuntu, so only do it if you have nothing else in it.
