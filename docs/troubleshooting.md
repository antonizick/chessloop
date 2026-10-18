# Troubleshooting

Find your symptom, read the cause, follow the fix. If nothing here helps, open an [Install problem](https://github.com/antonizick/chessloop/issues/new?template=install_problem.yml) issue and attach the log file the installer names (`~/chessloop-install-<date>.log`, or `chessloop-update-…`). Logs never contain passwords.

Start with this command. It tells you whether ChessLoop is running, its address and its version:

```bash
chessloop status
```

## During the install

### "This computer can't reach: download.docker.com" (or another address)
**Cause:** no internet, or a company proxy or firewall blocks the address.
**Fix:** check that the computer is online (`ping -c 3 github.com`). Behind a proxy or firewall, allow the addresses the installer lists. Run the installer again: it continues where it stopped.

### "Port 8090 is already used by another program; 8091 is free."
**Cause:** something else on the computer already uses that port.
**Fix:** press `Enter` to take the free port the installer suggests. Your address then ends in `:8091`.

### A yellow question: "Continue anyway, at your own risk?"
**Cause:** your system or processor is not one of the tested ones (Ubuntu 24.04 and 26.04, Debian 12 and 13, 64-bit Intel or AMD).
**Fix:** it may still work, but it is not tested. Say `n` to stop, or `y` to go on at your own risk.

### Warnings about low memory or disk space
**Cause:** the computer has less than about 2 GB of memory or 3 GB of free disk.
**Fix:** free some disk space or add memory. The installer asks before it continues.

### The password for `sudo` is "wrong" or you see "Sorry, try again."
**Cause:** you mistyped. Nothing shows while you type a password, which makes this easy to do.
**Fix:** type it again slowly and press `Enter`. It is your own login password for this computer (on Windows, the Ubuntu password you chose).

### "The test email couldn't be sent"
**Cause:** the SMTP details are wrong, or the mail server refused the connection.
**Fix:** choose **1** to retype the details, or **2** to turn email off for now. ChessLoop works without email. See [Configuration](configuration.md#email).

### "An earlier install in /opt/chessloop didn't finish."
**Cause:** the previous run stopped (a lost connection, a closed window).
**Fix:** nothing. Let it continue: it keeps your settings and data and does the missing steps.

### The build seems stuck
**Cause:** the first build downloads a lot. A slow connection takes up to 10 minutes.
**Fix:** wait. The progress line still shows the step. If nothing changes for 15 minutes, press `Ctrl` + `C` and run the installer again.

### The installer failed with an error
**Fix:** it names the failed step and shows the last lines of its log. Run it again first. If it fails again, open an [Install problem](https://github.com/antonizick/chessloop/issues/new?template=install_problem.yml) issue with the log.

## After the install

### I cannot sign in
- Check the email: it is the admin email you gave the installer.
- Forgot the password? Reset it:

  ```bash
  cd /opt/chessloop/chessloop
  sudo docker compose -f docker-compose.prod.yml exec backend python seeds/create_admin.py --email you@example.com --reset-password
  ```

  It asks for a new password (12 characters or more).
- For someone else: in **Admin panel → Users** the admin can set a new password.

### "Email not verified"
**Cause:** someone forced email verification, but ChessLoop cannot send email.
**Fix:** in **Admin panel → Users**, click **Verify** next to the person. Or set up email: [Configuration](configuration.md#email).

### "docker: permission denied"
**Cause:** your user is not in Docker's group until you log out and in again.
**Fix:** put `sudo` in front (`sudo docker …`), or log out and in. The `chessloop` command does this for you.

### `chessloop: command not found`
**Cause:** an install made before the command existed.
**Fix:** `bash /opt/chessloop/deploy.sh status`. The next `bash /opt/chessloop/deploy.sh update` adds the command.

### The page does not load after the computer restarted
**Fix:** wait a minute. Docker starts first, then ChessLoop. Then run `chessloop status`. If it says stopped, run `chessloop start`. (`chessloop stop` lasts until the next restart; to keep it off, uninstall at level 1.)

### Every page shows an error, or "504 Gateway Timeout"
**Cause:** Docker's network between ChessLoop's parts can break when Docker restarts (seen on WSL after sleep). The containers show as running but cannot talk to each other.
**Fix:** your data is safe. Recreate the containers:

```bash
cd /opt/chessloop/chessloop
sudo docker compose -f docker-compose.prod.yml down
chessloop start
```

### My other device cannot open ChessLoop
- Did you choose "Also on other devices" when you installed? Check `BIND_ADDR` in [Configuration](configuration.md#bind_addr).
- Use the address the installer printed (`http://192.168.x.x:8090`), not `localhost`. `localhost` always means "this device".
- Both devices must be on the same network. A guest Wi-Fi often blocks this.
- The computer's firewall may block the port. On Ubuntu with `ufw`: `sudo ufw allow 8090/tcp`.

### The update failed
The update goes back by itself and tells you. See [Updating](updating.md). Attach the log to an issue.

### A restore fails
Restore checks the file first and stops before changing anything if the file is damaged, does not match its `.sha256` checksum, or is not a ChessLoop backup. Copy the file again from where you keep it. Keep the `.tar.gz` and `.sha256` files together. If it fails after the switch, the message names the safety backup (`…-before-restore.tar.gz`) that has your previous data.

### I can't find my backups
They are in `~/chessloop-backups` of the user who ran the command. On Windows that is inside Ubuntu: `explorer.exe ~/chessloop-backups` opens it in Windows.

## Windows (WSL 2)

### "localhost refused to connect"
**Cause:** Ubuntu is not running. Windows stops it about 15 seconds after the last Ubuntu window closes, and does not start it again after a restart.
**Fix:** open **Ubuntu** from the Start menu and wait a few seconds. To stop it happening, use the [keep-alive setting](install/windows-wsl2.md#step-6-keep-chessloop-running).

### `wsl --install` finished but there is no Ubuntu
**Cause:** on a PC that never had WSL, the first run installs only WSL.
**Fix:** restart Windows, open PowerShell as administrator, and run `wsl --install` again.

### Windows: virtualization is turned off
**Cause:** `wsl --install` or Ubuntu says virtualization (VT-x, AMD-V, SVM) is off.
**Fix:** restart the PC into its firmware setup (BIOS or UEFI; the key shown at start-up is often `F2`, `F10` or `Del`), find the virtualization option (the name depends on the maker) and turn it on. Your PC's maker has instructions for your model.

### The installer says Docker Desktop is running but Ubuntu can't use it
**Fix:** in Docker Desktop open **Settings → Resources → WSL integration**, switch on your Ubuntu, choose **Apply & restart**, then run the installer again. Or uninstall Docker Desktop: the installer then sets up Docker inside Ubuntu.

### My phone cannot open ChessLoop (Windows)
1. You must have chosen "also on other devices" and said yes to mirrored networking. Then run `wsl --shutdown`.
2. The firewall step needs an **administrator** PowerShell. See [the steps](install/windows-wsl2.md#optional-use-chessloop-from-your-phone).
3. Use the address from `hostname -I` in Ubuntu, with `:8090`, not `localhost`.
4. With Docker Desktop: if you closed Windows' firewall question the first time, Windows may have created "Docker Desktop Backend" **Block** rules. Open **Windows Defender Firewall with Advanced Security → Inbound Rules**, delete those Block rules, and allow the port.
5. Do not use `netsh interface portproxy` with `listenaddress=0.0.0.0`: it stops `localhost` from working.

### A Ubuntu window hangs for minutes
Restart Windows. This was seen once on Ubuntu 26.04 and not reproduced.
