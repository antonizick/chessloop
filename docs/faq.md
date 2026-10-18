# FAQ

**Is ChessLoop free?**
Yes. It is free software under the GNU Affero General Public License v3.0 or later. See [LICENSE](../LICENSE).

**Does it need the internet?**
Only to install and update. Your openings and practice work offline.

**Where is my data?**
In a Docker volume called `chessloop_chessloop-data`, on your computer. Nothing is sent anywhere. Back it up with `chessloop backup` ([Backup and restore](backup-restore.md)).

**Do I need a Lichess account?**
No. The starter libraries (16 openings with 127 lines) and everything else work without one.

**Do I need email?**
No. Without email, new users sign in at once and an admin sets passwords in Admin panel → Users. Email only adds verification links and "Forgot password". See [Configuration](configuration.md#email).

**Can my family use it?**
Yes. Each person registers their own account, with their own progress. Share the address ([Using ChessLoop](using-chessloop.md#4-invite-family-and-friends)).

**Can I use it from my phone?**
Yes, if you chose "Also on other devices in my home network" when installing. Open the address the installer printed. On Windows there are [extra steps](install/windows-wsl2.md#optional-use-chessloop-from-your-phone).

**Can I use it from my phone when I am away from home (on mobile data)?**
No. A home-network install can be reached only from devices on your home network. These guides do not cover reaching it from outside. See the next question.

**Can I put it on the internet?**
These guides do not cover it, and ChessLoop is built for personal, private use. See [Not covered](../README.md#not-covered-hosting-chessloop-on-the-internet).

**Does it start by itself?**
Yes. Docker starts when the computer starts and brings ChessLoop back. On Windows, use the [keep-alive setting](install/windows-wsl2.md#step-6-keep-chessloop-running).

**How do I change the port or turn on email?**
[Configuration](configuration.md).

**How do I get the newest version?**
`chessloop update` ([Updating](updating.md)).

**How do I remove it?**
`chessloop uninstall` ([Uninstalling](uninstall.md)).

**Which systems work?**
Ubuntu 24.04 and 26.04, Debian 12 and 13, and Windows 11 with Ubuntu 24.04 or 26.04 in WSL 2. All 64-bit Intel or AMD. Other systems are not tested.

**Does it work on a Raspberry Pi or Apple Silicon Mac?**
Not tested. The installer warns about other processors.

**I found a bug.**
Open a [bug report](https://github.com/antonizick/chessloop/issues/new?template=bug_report.yml).
