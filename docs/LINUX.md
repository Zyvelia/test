# Vivi on Linux

The same Python bot, dashboard, SQLite data, moderation/ticket tools, uploaded-audio
player, temporary voice rooms, notification poller and optional AI work on Linux.
Use Python 3.11+ (3.12 recommended). Do not reuse a Windows `.venv` on Linux.

## Install

Download/extract this repository or clone it into a folder owned by your normal
user. Install prerequisites using your distribution's package manager:

```sh
# Debian / Ubuntu
sudo apt update
sudo apt install python3 python3-venv python3-pip ffmpeg libopus0

# Fedora (enable a distribution-appropriate FFmpeg repository if needed)
# sudo dnf install python3 python3-pip ffmpeg opus

# Arch Linux
# sudo pacman -S python python-pip ffmpeg opus
```

FFmpeg and Opus are needed for music, not for normal text commands. The Python
voice dependencies (PyNaCl and DAVE support) are installed by requirements.txt.

From the extracted repository:

```sh
bash setup.sh
# Edit .env privately with your editor, add DISCORD_TOKEN, then follow README setup.
chmod 600 .env
bash start.sh
```

setup.sh creates `.venv`, installs pinned direct dependencies and creates a private
.env only when one does not already exist. It preserves your data and existing
configuration. Install distro prerequisites separately if venv or pip is missing.
Keep the terminal open when running manually. Ctrl+C stops the supervisor and bot.

Use the same Discord Developer Portal setup, privileged intents, bot role hierarchy
and server `/setup` steps described in README.md. The local dashboard is configured
the same way on Linux: its OAuth callback must point to the loopback browser on
**this same machine**. For a headless host, slash commands work directly. You can also keep the dashboard
private and use an authenticated SSH local forward from your own computer:

```sh
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 your-user@your-linux-host
```

Then open the loopback dashboard in the browser on your own computer. Register the
same 127.0.0.1 OAuth callback. This does not expose the dashboard publicly; it uses
your existing SSH access. Public web hosting needs a separate HTTPS design.

## Automatic startup with systemd

On distributions with systemd user services:

```sh
bash install-startup.sh
systemctl --user start vivi-bot
systemctl --user status vivi-bot
journalctl --user -u vivi-bot -f
```

This writes `~/.config/systemd/user/vivi-bot.service` (or under XDG_CONFIG_HOME),
reloads user units and enables it for your user session. It does not store a
password, require root for the service, or put tokens into the unit. Credentials
are read from the repository's .env. The service and the manual launcher use the
same duplicate-process lock. Do not run the manual launcher while the service is
already running. The service runs in the background; error logs are also saved in
`data/logs/`.

By default it starts when your user session starts. To allow the user manager to
start after boot **without logging in**, an administrator may enable lingering:

```sh
sudo loginctl enable-linger "$USER"
```

This is optional and changes host behavior. It is not performed by Vivi's installer.
The machine must still be powered on and connected; suspend/sleep interrupts the bot.
Keep the repository in the same location, or rerun install-startup.sh after moving it.
On WSL, containers or non-systemd distributions, use start.sh and your preferred
host process manager; the installer reports when systemd is unavailable.

Stop, update or remove startup:

```sh
systemctl --user stop vivi-bot
# Update code, preserve .env and data/, then:
bash setup.sh
systemctl --user restart vivi-bot

# To remove automatic startup:
bash remove-startup.sh
```

The remover checks for a Vivi service file before changing it. It stops/disables
only Vivi's user service and leaves data and .env intact. It does not disable
lingering, because other user services may depend on it.

## Verify and migrate

```sh
bash verify.sh
# Optional explicit small AI / translation requests:
bash verify.sh --providers

.venv/bin/python -m unittest discover -s tests -v
```

verify.sh reads Discord metadata and permissions but never posts test messages.
Dashboard login must be completed in your browser to verify the real OAuth flow.
A token or API key being present is not itself reported as a successful live test.
Verification exits 2 when no bot token is configured, 1 on a failed executed check,
and 0 when the executed required checks pass; optional unconfigured/manual checks
remain labeled in the report.

To move between Windows and Linux, stop the old bot, copy **data/** and **.env**
privately, then create a fresh virtual environment on the new OS. Never run both
copies with the same data/token. New installations use data/vivi.sqlite3; existing
data/aurora.sqlite3 is reused automatically. If both files exist, startup stops so
you can back them up and choose the intended database. Timers and persistent panels
survive; active games, voice connections and audio queues do not.
