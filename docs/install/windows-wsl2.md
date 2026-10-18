# Install ChessLoop on Windows 11

This guide takes you from a Windows 11 PC with nothing extra installed to a working ChessLoop. You do not need to know Linux.

**How it works.** ChessLoop runs on Linux. Windows 11 can run a small Linux inside it called *WSL 2* (Windows Subsystem for Linux). You install WSL with *Ubuntu* (a popular Linux), run the ChessLoop installer inside Ubuntu, and open ChessLoop in your normal Windows browser.

## Before you start

You need:

- **Windows 11, version 22H2 or newer.** To check: press the `Windows` key, type `winver` and press `Enter`. The window says "Version 22H2" or a later one such as 23H2, 24H2 or 25H2. Windows 10 is not covered.
- **Administrator rights** on the PC for the first step.
- A 64-bit Intel or AMD PC with *virtualization* switched on. It is on by default on almost every PC. If step 2 says virtualization is off, [Troubleshooting](../troubleshooting.md#windows-virtualization-is-turned-off) shows how to turn it on.
- About **2 GB of free memory** and **8 GB of free disk space**. (Ubuntu takes about 1.5 GB and ChessLoop about 3 GB; the rest is room to spare.)
- An **internet connection**.
- **Ubuntu 24.04 or 26.04.** Both work. The plain `wsl --install` command gives you the newest one, and that is fine.

The whole job takes about 15 minutes the first time, plus two restarts of Windows.

## Step 1. Open PowerShell as administrator

*PowerShell* is a window where you type commands.

1. Press the `Windows` key and type `PowerShell`.
2. Right-click **Windows PowerShell** and choose **Run as administrator**.
3. Windows asks "Do you want to allow this app to make changes?" Choose **Yes**.

The window's title starts with "Administrator:".

## Step 2. Install WSL

Type this and press `Enter`:

```powershell
wsl --install
```

You should see progress lines such as "Installing: Virtual Machine Platform" and "Installing: Windows Subsystem for Linux". It takes a couple of minutes.

**On a PC that never had WSL, this first run only installs WSL itself.** It does not install Ubuntu yet. When it finishes, it asks you to restart.

1. **Restart Windows.**
2. After the restart, open PowerShell as administrator again (Step 1) and run the **same command a second time**:

   ```powershell
   wsl --install
   ```

   This time it downloads Ubuntu and opens an Ubuntu window.

If you already use Docker Desktop, or an earlier try already switched the Windows features on, one run is enough: it installs WSL and Ubuntu together.

Want Ubuntu 24.04 instead of the newest? Use `wsl --install -d Ubuntu-24.04`. Both work equally well with ChessLoop.

## Step 3. Create your Ubuntu user

The Ubuntu window asks you to create a user:

```text
Create a default Unix user account:
New password:
Retype new password:
```

- The user name suggestion is your Windows name. Press `Enter` to take it, or type a short lowercase name.
- Choose a password and type it twice. **Nothing shows while you type a password.** No dots, no stars. That is normal. Keep typing and press `Enter`.
- This is your Ubuntu password. You need it later when the installer asks for `sudo`. It does not have to match your Windows password.

Ubuntu may also ask: **Would you like to opt-in to platform metrics collection (Y/n)?** That is Ubuntu's own question about sending usage statistics. ChessLoop does not need it. Type `n` and press `Enter` to share nothing; either answer works.

You should end up at a line like `sam@PC-NAME:~$`. That is where you type commands. Leave this window open. If your line shows a path like `sam@PC-NAME:/mnt/c/Users/sam$` instead, you are in your Windows folder: type `cd ~` and press `Enter`.

## Step 4. Run the ChessLoop installer

In the Ubuntu window, copy this line, paste it (right-click in the window, or `Ctrl` + `Shift` + `V`) and press `Enter`:

```bash
curl -fsSL https://raw.githubusercontent.com/antonizick/chessloop/main/deploy.sh | bash
```

Prefer to read the script first? See [the careful way](linux.md#the-careful-way-read-the-script-first).

The installer asks the same questions as on Linux. [Every question is explained here](linux.md#the-installers-questions). On Windows these differ:

- **Where will you open ChessLoop?** Choice **1** is "Only on this Windows PC". Choose it unless you want a phone or tablet to connect: see [Use ChessLoop from your phone](#optional-use-chessloop-from-your-phone).
- **Keep ChessLoop running on Windows.** Answer `Y`. [See below](#step-6-keep-chessloop-running) for what this does.
- It asks for your **sudo password**. That is the Ubuntu password from Step 3, and nothing shows while you type it.

When it ends with **ChessLoop is installed and running**, the install is done.

## Step 5. Open ChessLoop in Windows

Open **Edge**, Chrome or Firefox **in Windows** (not inside Ubuntu) and go to:

```text
http://localhost:8090
```

Use `localhost`, not the long address that starts with `172.`. That one does not work from Windows.

You should see the ChessLoop sign-in page. Sign in with the email and password you gave the installer. Next: [Using ChessLoop](../using-chessloop.md).

## Step 6. Keep ChessLoop running

Windows stops Ubuntu, and ChessLoop with it, about 15 seconds after you close the last Ubuntu window. It also does not start Ubuntu again when Windows restarts. Then your browser shows "localhost refused to connect".

When you answer `Y` to **Keep ChessLoop running on Windows**, the installer changes two settings for your Windows user. You do not need administrator rights for them:

1. It adds `instanceIdleTimeout=-1` to `%UserProfile%\.wslconfig`. This tells WSL not to stop Ubuntu when its window is closed.
2. It puts a small file `ChessLoop.cmd` in your Startup folder. Windows runs it when you sign in, and it starts Ubuntu.

The settings apply after Windows restarts, or after you run this in PowerShell:

```powershell
wsl --shutdown
```

Then open Ubuntu once, or restart Windows. After that you can close the Ubuntu window, and ChessLoop stays up.

**After a restart, be patient.** Sign in to Windows, then give it a few minutes: in the lab ChessLoop answered about 1½ minutes after sign-in, and it can take up to 5 minutes. Until then the browser shows "localhost refused to connect". You do not need to open anything.

### Doing it by hand

If you said no, or want to check, make the same two changes yourself. In a normal PowerShell window (not administrator):

```powershell
Add-Content "$env:USERPROFILE\.wslconfig" "[general]`r`ninstanceIdleTimeout=-1"
Set-Content "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\ChessLoop.cmd" "wsl.exe -d Ubuntu --exec /bin/true"
wsl --shutdown
```

If you installed `Ubuntu-24.04`, write `-d Ubuntu-24.04` instead of `-d Ubuntu`. `wsl -l -v` lists the exact name. If `.wslconfig` already has a `[general]` section, add the `instanceIdleTimeout=-1` line under it instead of adding a second section.

### Undo it

Delete the line `instanceIdleTimeout=-1` from `%UserProfile%\.wslconfig` and delete `ChessLoop.cmd` from the Startup folder (press `Windows` + `R`, type `shell:startup`, press `Enter`). Uninstalling ChessLoop at level 3 offers to do this for you.

## Optional: use ChessLoop from your phone

By default only the PC itself can open ChessLoop. To open it from a phone or tablet on the same Wi-Fi:

> **Warning.** This lets every device on that network open ChessLoop's sign-in page. Do it only on a network you trust, such as your home.

1. When the installer asks **Where will you open ChessLoop?**, choose **2** (also on other devices). If you installed already, run `chessloop uninstall` to level 1 and install again, or follow [Configuration](../configuration.md#bind_addr).
2. Say **yes** when the installer offers *mirrored networking*. It adds this to `%UserProfile%\.wslconfig`:

   ```text
   [wsl2]
   networkingMode=mirrored
   ```

3. In PowerShell, restart WSL:

   ```powershell
   wsl --shutdown
   ```

4. Open PowerShell **as administrator** and allow the port through the firewall. Replace `8090` if you chose another port:

   ```powershell
   New-NetFirewallHyperVRule -Name ChessLoop -DisplayName ChessLoop -Direction Inbound -VMCreatorId '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' -Protocol TCP -LocalPorts 8090
   ```

5. In Ubuntu, find the PC's address:

   ```bash
   hostname -I
   ```

   Use the first address, for example `192.168.1.20`. On your phone, open `http://192.168.1.20:8090`.

If the phone cannot connect, see [Troubleshooting](../troubleshooting.md#my-phone-cannot-open-chessloop-windows). Do not follow guides that tell you to use `netsh interface portproxy` with `listenaddress=0.0.0.0` and `connectaddress=127.0.0.1`. That recipe stops `localhost` from working on the PC.

## If you use Docker Desktop

You do not need Docker Desktop: the installer puts Docker inside Ubuntu. If you already have Docker Desktop, the installer uses it. Two things to know:

- **Licence.** Docker's page ([docs.docker.com/subscription/desktop-license](https://docs.docker.com/subscription/desktop-license/)) says Docker Desktop is free for small businesses (fewer than 250 employees and less than $10 million a year in revenue), personal use, education and non-commercial open source projects. Larger companies and government bodies need a paid plan. Read the page yourself if you are not sure. ChessLoop does not need Docker Desktop.
- **Switch on WSL integration before you install ChessLoop.** In Docker Desktop open **Settings → Resources → WSL integration**, switch on your Ubuntu, and choose **Apply & restart**. If you skip this, the installer stops with a message that says exactly this.

Also in Docker Desktop's settings, switch on **Start Docker Desktop when you sign in to your computer**. ChessLoop then comes back after a Windows restart. With Docker Desktop you do not need the keep-alive setting from Step 6.

Docker Desktop's own message "WSL not installed" means: do Steps 1 to 3 above, then try again.

If Windows asked about its firewall when Docker Desktop first ran and you closed the box, Windows may have blocked other devices. [Troubleshooting](../troubleshooting.md#my-phone-cannot-open-chessloop-windows) explains how to fix that.

## Everyday use on Windows

- **Type `chessloop` commands in an Ubuntu window.** Open the Start menu and choose **Ubuntu**. See [Daily commands](../../README.md#daily-commands).
- **Open ChessLoop** at `http://localhost:8090` in your Windows browser.
- **Back up** with `chessloop backup`. The file lands in the Ubuntu home folder. To see it in Windows, type `explorer.exe ~/chessloop-backups` in Ubuntu.
- **"localhost refused to connect"** means Ubuntu is not running. Open the Ubuntu window and wait a few seconds (after a Windows restart, wait up to 5 minutes first). If it keeps happening, check [Step 6](#step-6-keep-chessloop-running).
