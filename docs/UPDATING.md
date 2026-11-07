# Update Vivi from GitHub

The host updater installs the latest `main` commit from **Zyvelia/test**. It supports both downloaded ZIP copies and Git checkouts on Windows and Linux. It runs on the computer hosting Vivi; Discord members cannot trigger code installation through the dashboard.

## First installation of the updater

If your existing copy does not contain `update.bat` / `update.sh`, stop Vivi first and open a terminal **inside your existing Vivi folder**. This one-time bootstrap downloads the updater automatically; it does not require replacing folders manually.

Windows PowerShell:

```powershell
Invoke-WebRequest "https://raw.githubusercontent.com/Zyvelia/test/main/scripts/bootstrap_update.py" -OutFile "$env:TEMP/vivi-bootstrap-update.py"
& ".\.venv\Scripts\python.exe" "$env:TEMP/vivi-bootstrap-update.py"
```

Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/Zyvelia/test/main/scripts/bootstrap_update.py -o /tmp/vivi-bootstrap-update.py
.venv/bin/python /tmp/vivi-bootstrap-update.py
```

The bootstrap loads its updater modules in a temporary folder, uses the existing virtual environment and applies the same preservation and backup rules as normal updates. It also requires access to `raw.githubusercontent.com`. A normal GitHub download or `git pull` can still be used instead.

Stop all old Vivi processes before this first update. Older launchers and directly running `python -m vivi.bot` do not hold the new host lock.

## One-click updates

1. Stop Vivi. Close the tray bot or stop its Windows startup task / Linux systemd service too.
2. On Windows, double-click **update.bat**. On Linux, run **`bash update.sh`**.
3. Wait for **Update complete**, then run **start.bat** or **`bash start.sh`** as usual.

No Git installation is needed for ZIP copies. Git checkouts require Git, the `main` branch, the official origin URL and no local changes. They use `fetch` and a fast-forward merge; diverged history and edited source files are rejected rather than reset or discarded. Commit or stash local edits before updating.

For a check without installing source files or dependencies:

```powershell
update.bat --check
```

```bash
bash update.sh --check
```

The first ZIP check may report that its installed revision is unknown. Running the updater compares actual files and records the installed commit.

## Update from the Windows tray

Right-click Vivi’s tray icon and choose **Update Vivi from GitHub**. If this tray started the bot, it stops that process tree, runs the same updater in the background and starts Vivi again only after a successful update. If Vivi was stopped, it stays stopped after updating. A bot launched elsewhere must be stopped in its own launcher/service first; the tray does not terminate unrelated processes.

The tray shows **updating…** while work is in progress and disables conflicting start, stop, update and exit actions. Completion/failure notifications and a status row show the result. Choose **Open update log** to read `data/logs/update.log`; **Open logs** opens the containing folder. A failed update leaves the bot stopped for troubleshooting rather than restarting uncertain code. A successful restart skips a duplicate automatic-update check for that launch.

To get this menu option in an older tray, exit the tray, run `update.bat` once, then reopen `tray.bat`. Changes to the tray UI itself load when the tray is reopened; the restarted bot always loads the updated bot code. If Windows reports package files in use during dependency installation, close the tray and use `update.bat` to finish the update.

The controller’s process/update flows are covered by automated tests; the native tray UI and notification behavior require a Windows host.

## Automatic updates when starting

Add this line to your local `.env`:

```dotenv
AUTO_UPDATE=true
```

Every normal launcher start, including tray, Windows startup and Linux systemd startup, checks GitHub and installs updates before starting the bot. It does not interrupt a running bot or periodically update it during operation. Set `AUTO_UPDATE=false` to return to manual updates.

If the check or installation fails, startup stops with an error rather than launching uncertain code. Resolve the error or disable automatic updates and try again. Downloaded source is pinned to an immutable commit before installation. This tracks the repository’s current main branch, not just numbered GitHub releases; the dashboard’s existing release checker is a separate read-only tool.

## What is preserved

The updater does not replace `.env`, `.venv`, `data`, Git metadata, installed Node modules, encryption keys or database files. Existing token/configuration values are not sent to GitHub. New default configuration options do not overwrite your `.env`; add options you want to enable yourself.

ZIP updates replace upstream source files, saving overwritten originals under **`data/update-backups/<backup-id>/`**. Other custom files remain. Files removed upstream are deleted only when recorded by a previous updater run and unchanged locally. Locally edited source that still exists upstream will be backed up and replaced; move custom code to a separate branch/Git checkout if you want updates to stop on local edits.

New Python dependencies are installed into the Python environment running the updater when requirements change. Launch using the supplied scripts so this is Vivi’s `.venv`. Pip installations cannot be rolled back automatically and may partly change packages on failure; rerun setup to repair them before starting. OS packages such as FFmpeg are not installed by the updater.

## Backups and interrupted updates

Archive installs keep a recovery journal while replacing source files. If an update fails or is interrupted, the next updater run restores the previous source before trying again. Do not manually start a bot after an interrupted update until recovery finishes. Keep `data/update-pending.json` and the referenced backup intact.

To explicitly restore source from an archive-update backup, stop Vivi and use its folder name:

```powershell
update.bat --rollback BACKUP_ID
```

```bash
bash update.sh --rollback BACKUP_ID
```

This restores files replaced by that update and removes files it added. It can replace later source edits, so choose the backup carefully. It does **not** restore the database, `.env` or Python packages. Run setup for compatible dependencies after rollback. If the updater itself was absent before that backup, rollback may remove it too. Git updates retain their previous commit in Git history and print its ID; archive rollback is not used for Git installs.

Keep a separate encrypted full-data backup before significant updates. An updater’s source backup is not a database migration backup. Old source backups are retained until you remove them; remove them only when no pending recovery references them.

## Windows encoding error (CP932 or another legacy code page)

A message such as `'cp932' codec can't decode byte ...` means an older updater
read GitHub’s UTF-8 JSON using Windows’ local encoding. It is not a missing
Discord or GitHub token. The public updater does not require either token.

Stop Vivi, open PowerShell in its folder, and run this once to update the older
updater with UTF-8 mode enabled:

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
.\update.bat
```

Current updater versions explicitly read metadata as UTF-8, decode Git output
with UTF-8 and enable UTF-8 for launcher/tray update processes. No system-wide
Windows locale change is needed. Restart the tray after updating to load its fix.

## Troubleshooting

- **Vivi or another updater is running:** stop the launcher, tray bot or startup service first. The launcher and updater share a cross-platform host lock.
- **GitHub cannot be reached / rate limited:** retry later. The public updater requires HTTPS access to `api.github.com`, `codeload.github.com`, and `github.com` for Git checkouts. No token is required. The installer keeps TLS verification enabled.
- **Dependency installation failed:** run setup again; check Python version and package network access. Then retry the update.
- **Docker:** rebuild the image and recreate the container using your normal Docker deployment. Do not enable in-place automatic updating in an ephemeral container.

The archive and transaction tests use synthetic fixtures. Linux download checks can be run in development; Windows batch launching and Windows file locking still need verification on a Windows host.
