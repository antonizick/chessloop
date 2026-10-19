# ChessLoop

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![CI](https://github.com/antonizick/chessloop/actions/workflows/ci.yml/badge.svg)](https://github.com/antonizick/chessloop/actions/workflows/ci.yml)

ChessLoop is a chess opening trainer that you run on your own computer. You teach it your openings by playing the moves on a board, then it quizzes you and brings back the positions you get wrong more often. Your accounts, openings and progress stay on your computer.

![ChessLoop dashboard](screenshots/ChessLoop%20Tracking%20dashboard.png)

![ChessLoop practice](screenshots/ChessLoop%20Learning%20and%20training%20arenas.png)

## What you need

| | |
|---|---|
| **A computer to run it on** | Ubuntu 24.04 or 26.04, Debian 12 or 13, or Windows 11 with Ubuntu 24.04 or 26.04 inside WSL 2. All 64-bit Intel or AMD. |
| **Memory and disk** | About 2 GB of memory and 5 GB of free disk space (3 GB is the minimum). |
| **Internet** | For the install only. ChessLoop itself works without it. |
| **Admin rights** | A user who can use `sudo` (on Windows: an administrator for the first step). |
| **Time** | About 5 minutes for the install (2 minutes on a fast connection). On Windows, add about 15 minutes the first time to set up WSL. |

New to this? Every guide below is written for someone who has never used a terminal. The words in *italics* the first time they appear are explained in the [glossary](docs/glossary.md).

## Quick start on Ubuntu or Debian

1. **Open a terminal.** On Ubuntu press `Ctrl` + `Alt` + `T`. On a server, connect with SSH.
2. **Paste this line** and press `Enter`:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/antonizick/chessloop/main/deploy.sh | bash
   ```

   Want to read the script first? Use the [careful way](docs/install/linux.md#the-careful-way-read-the-script-first).
3. **Answer the questions.** The installer checks your computer, then asks where you will open ChessLoop, your admin email and a password. Press `Enter` to accept the choice in `[brackets]`. It changes nothing until you say `Continue`. [Every question explained](docs/install/linux.md#the-installers-questions).
4. **Wait.** It downloads and builds ChessLoop. You see a progress line and no more questions. It ends with a box that says **ChessLoop is installed and running**.
5. **Open it.** Go to <http://localhost:8090> in your web browser and sign in with the email and password from step 3. If you chose to use ChessLoop from other devices, type the address the installer printed at the end instead (it looks like `http://192.168.1.20:8090`).

You are done. Next: [your first steps in ChessLoop](docs/using-chessloop.md).

**On Windows 11?** Follow the [Windows guide](docs/install/windows-wsl2.md). It starts from a PC with nothing installed.

## Guides

| I want to… | Read |
|---|---|
| Install on Ubuntu or Debian | [Install on Linux](docs/install/linux.md) |
| Install on Windows 11 | [Install on Windows 11 (WSL 2)](docs/install/windows-wsl2.md) |
| Learn to use ChessLoop | [Using ChessLoop](docs/using-chessloop.md) |
| Save my data, or move to another computer | [Backup and restore](docs/backup-restore.md) |
| Get the newest version | [Updating](docs/updating.md) |
| Stop, start or check ChessLoop | [Daily commands](#daily-commands) |
| Remove ChessLoop | [Uninstalling](docs/uninstall.md) |
| Change a setting (port, email, …) | [Configuration](docs/configuration.md) |
| Fix a problem | [Troubleshooting](docs/troubleshooting.md) |
| Look up a word | [Glossary](docs/glossary.md) |
| Quick answers | [FAQ](docs/faq.md) |
| Change the code | [Development](docs/development.md) |

## Daily commands

The installer adds one command, `chessloop`. Type it in a terminal (on Windows: in your Ubuntu window).

| Command | What it does |
|---|---|
| `chessloop status` | Is it running? Shows the address, the version and your latest backup. |
| `chessloop backup` | Saves all your data to a file in `~/chessloop-backups`. |
| `chessloop update` | Gets the newest version. It backs up first and goes back if anything fails. |
| `chessloop stop` / `chessloop start` / `chessloop restart` | Stop, start or restart it. |
| `chessloop logs` | Shows the last messages. `chessloop logs -f` keeps following. |
| `chessloop help` | Lists every command, including `restore` and `uninstall`. |

ChessLoop starts by itself when the computer starts. `chessloop stop` lasts until the next restart.

## Not covered: hosting ChessLoop on the internet

This project is for **personal, private installs**: your computer, your home network, your family and friends. Putting ChessLoop on the public internet needs a domain name, HTTPS, updates and monitoring. These guides do not cover that, and ChessLoop has not been security-tested for it. The installer's third choice ("from anywhere on the internet") only keeps ChessLoop private on the computer and tells you that you have to add the HTTPS part yourself.

## Get help

- Look in [Troubleshooting](docs/troubleshooting.md) first.
- If the installer failed, open an [Install problem](https://github.com/antonizick/chessloop/issues/new?template=install_problem.yml) issue and attach the log file it names (`~/chessloop-install-<date>.log`). The log never contains passwords.
- Found a bug in ChessLoop itself? Open a [Bug report](https://github.com/antonizick/chessloop/issues/new?template=bug_report.yml).
- Security problem? Read [SECURITY.md](SECURITY.md) and report it privately.

## Licence

ChessLoop is free software under the [GNU Affero General Public License v3.0 or later](LICENSE) (AGPL-3.0-or-later). In short: you may use, change and share it. If you run a changed version as a service for other people, you must give them your source code. The source is here, in this repository. See [NOTICE](NOTICE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
