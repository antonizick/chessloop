# Install ChessLoop on Ubuntu or Debian

This guide takes you from a computer with Ubuntu or Debian to a working ChessLoop. You do not need to know Linux. Every step says what to type and what you should see.

**On Windows 11?** Use the [Windows guide](windows-wsl2.md) instead.

## Before you start

You need:

- **Ubuntu 24.04 or 26.04, or Debian 12 or 13**, 64-bit Intel or AMD. Other systems are not tested. The installer says so and asks before it continues.
- About **2 GB of memory** and **5 GB of free disk space** (3 GB is the minimum).
- An **internet connection**.
- A user account that can use `sudo`. This is the account you set up when you installed Linux, if you are the only user. `sudo` means "run this as the administrator". It asks for your own password.

The installer checks all of this first and changes nothing until you say `Continue`.

## Step 1. Open a terminal

A *terminal* is a window where you type commands.

- **Ubuntu or Debian with a desktop:** press `Ctrl` + `Alt` + `T`. Or open the menu and search for "Terminal".
- **A server or a computer in another room:** connect with SSH. On another Linux or Mac computer, or in Windows PowerShell, type `ssh YOUR-USERNAME@THE-COMPUTERS-ADDRESS`, then your password.

You should see a line that ends with `$`. That is where you type.

## Step 2. Run the installer

Copy this line, paste it into the terminal and press `Enter`. To paste in most terminals, press `Ctrl` + `Shift` + `V`.

```bash
curl -fsSL https://raw.githubusercontent.com/antonizick/chessloop/main/deploy.sh | bash
```

You should see a box that says **ChessLoop Installer**, then a menu:

```text
  What would you like to do?

    1)  Install    — Set up ChessLoop on this computer
    2)  Update     — Get the latest version (backs up your data first)
    3)  Back up    — Save all ChessLoop data to a file
    4)  Restore    — Put back the data from a backup file
    5)  Uninstall  — Remove ChessLoop (choose how much)
    6)  Exit

  Choice [1-6]:
```

Type `1` and press `Enter`. (The other choices are for later.) Next comes a short check of your computer:

```text
  Checking this computer
  ✓  System: Ubuntu 24.04.5 LTS
  ✓  Processor: x86_64
  →  Docker: not installed yet (the installer adds Docker Engine from Docker's official repository).
  ✓  Memory: 3.8 GB
  ✓  Free disk space: 23 GB
  ✓  Internet: can reach registry-1.docker.io download.docker.com
```

A yellow warning here means the installer found a problem. [Troubleshooting](../troubleshooting.md) lists every warning and what to do.

### The careful way: read the script first

The line above downloads a script from GitHub and runs it. Some people prefer to read a script before running it. That is a good habit. Do this instead:

```bash
curl -fsSLO https://raw.githubusercontent.com/antonizick/chessloop/main/deploy.sh
less deploy.sh
```

`less` shows the script one screen at a time. Press `Space` for the next screen and `q` to quit. When you are happy with it, run it:

```bash
bash deploy.sh
```

To install a fixed version instead of the newest one, pick a version name from the [releases page](https://github.com/antonizick/chessloop/releases) (it looks like `v1.2.3`) and put it in front of the last command:

```bash
CHESSLOOP_REF=VERSION-NAME bash deploy.sh
```

If there is no release yet, skip this and use the newest version.

## The installer's questions

You answer a few plain questions. The choice in `[brackets]` is the default: press `Enter` to take it. Typing is hidden only for passwords.

### 1. Where will you open ChessLoop?

```text
  Where will you open ChessLoop?
    1) Only on this computer
    2) Also on other devices in my home network (phone, tablet, laptop)
    3) From anywhere on the internet, with my own domain name (HTTPS)
  Access [1-3] [2]:
```

| Choice | Pick it when | Example |
|---|---|---|
| **1** Only on this computer | You use ChessLoop in the browser on the same computer. | A laptop you also sit at. |
| **2** Also on other devices in my home network | You want to open it from other devices on your Wi-Fi. | A mini-PC in a cupboard that you use from your laptop and phone. |
| **3** From anywhere on the internet | Advanced. Not covered by these guides. | You know how to set up a domain name and HTTPS yourself. |

If you are not sure, choose **1**. You can change it later in [Configuration](../configuration.md#bind_addr).

Choice 2 uses plain `http://`, which is not encrypted. Use it only on a network you trust. If your computer has a public internet address, the installer warns you before it offers choice 2.

Choice 3 keeps ChessLoop private on the computer and prints a reminder. It does not set up HTTPS. See [Not covered](../../README.md#not-covered-hosting-chessloop-on-the-internet).

### 2. Port

```text
  Port [8090]:
```

A *port* is the number at the end of the address, like `http://localhost:8090`. Press `Enter`. If 8090 is already taken, the installer suggests a free one.

### 3. Your admin email and password

```text
  Admin email: you@example.com
  Admin password:
```

This is the account you sign in with. You are the *admin*: the one who can manage other accounts. There is no default password.

- The email does not need to be real, and ChessLoop does not send anything to it unless you turn on email below.
- The password must have **at least 12 characters**. A few unrelated words work well, for example `purple-ladder-coffee-moon`. Nothing shows while you type, and you type it twice.
- Or press `Enter` to let the installer make a strong password. It shows it once at the end, in a box. Save it right away, for example in a password manager.

### 4. Email (optional)

```text
    1) No, skip email for now (recommended if you're not sure)
    2) Yes, I have SMTP details
```

Choose **1** unless you already know your mail provider's *SMTP* details. Without email, people who register can sign in at once, and you reset forgotten passwords in the Admin panel. You can add email later: see [Configuration](../configuration.md#email).

### 5. Starter opening libraries

```text
  Load the starter opening libraries? (recommended) [Y/n]:
```

Press `Enter`. This adds 16 ready-made opening libraries (Ruy López, Sicilian and more), each with 7 to 9 named lines (127 lines in all), so ChessLoop is not empty. They come with ChessLoop: you need no Lichess account and no internet for this step.

### 6. Ready to install

The installer lists exactly what it is going to do, then asks:

```text
  Continue? [Y/n]:
```

Press `Enter` to go on, or `n` to stop. Nothing has changed on your computer before this point.

Then it asks for your **sudo password**, which is your own password:

```text
  Type your own password for sam when asked.
  Nothing appears while you type; that's normal. Press Enter when done.
```

On Ubuntu 26.04 the prompt looks like `[sudo: authenticate] Password:`. It is the same thing. If you mistype it, the installer asks again.

There are no more questions after this, except when a test email fails.

## Step 3. Wait

The installer installs Docker (a program that runs ChessLoop in sealed boxes called *containers*, so nothing else on your computer changes), downloads ChessLoop into `/opt/chessloop`, builds it and starts it. It shows one progress line at a time:

```text
  ✓  Installing Docker Engine (about 1 minute) (33 s)
  ✓  Building ChessLoop (44 s)
  ✓  Starting ChessLoop and waiting until it is healthy (12 s)
  ✓  Admin account created: you@example.com (username 'admin').
  ✓  Checked: you@example.com can sign in.
```

This takes about 5 minutes (2 minutes on a fast connection, up to 10 on a slow one). You can leave it running. If it fails, it says which step failed and shows the last lines of its log. Run the installer again and it carries on where it stopped.

## Step 4. Open ChessLoop

At the end you see:

```text
  ╔══════════════════════════════════════════════════════════╗
  ║   ✓  ChessLoop is installed and running                  ║
  ╚══════════════════════════════════════════════════════════╝

  Open ChessLoop
    On this computer:  http://localhost:8090

  Sign in with you@example.com
     and the password you chose. You can change it in Settings → Account.
```

If you let the installer make your password, a box shows it. **It is shown only once.** Save it now.

Open the address in your web browser and sign in. You should see the ChessLoop sign-in page, and after signing in, the dashboard. Next: [Using ChessLoop](../using-chessloop.md).

If you chose "also on other devices", the installer also prints an address like `http://192.168.1.20:8090`. Type that into the browser on your phone or laptop. Both devices must be on the same network.

## After the install

- **Docker commands:** until you log out and in again, commands that start with `docker` need `sudo` in front. You will rarely need them: the `chessloop` command does the work.
- **Daily commands:** `chessloop status`, `chessloop backup`, `chessloop update`. See [Daily commands](../../README.md#daily-commands).
- **Back up now.** Run `chessloop backup`, then copy the file out of `~/chessloop-backups` to another computer or a USB stick. [Backup and restore](../backup-restore.md) explains why this matters.
- **The install log** is `~/chessloop-install-<date>.log`. It never contains passwords. Attach it if you ask for help.
- **Starts with the computer:** Docker starts at boot and brings ChessLoop back by itself.

## If something goes wrong

Read [Troubleshooting](../troubleshooting.md). It lists every message the installer can show and what to do. To ask for help, open an [Install problem](https://github.com/antonizick/chessloop/issues/new?template=install_problem.yml) issue and attach the log file.

## Unattended install

For scripts and testing, every answer can come from a setting instead of a question:

```bash
CHESSLOOP_ADMIN_EMAIL=you@example.com bash deploy.sh --yes
```

`bash deploy.sh --help` lists every setting. Without `CHESSLOOP_ADMIN_PASSWORD`, the installer makes a password and prints it once.
