# Vivi: AFK, previews, history, backups, tray, health, languages and aliases

Update your code and rerun setup.bat (Windows) or bash setup.sh (Linux). Preserve
.env and data/. Existing databases and buttons remain compatible. All new runtime
features are optional; `afk`, `scheduled_backups` and `custom_aliases` start off.
Preview/history/health dashboard tools require the existing administrator login.

## AFK status

Enable `afk` with /admin feature or the dashboard. Members use
`/tools afk reason:Taking a break`. A blank reason clears their status. Their next
normal, non-filtered chat message also clears it and welcomes them back. Message
edits do not clear it. Mentions of an absent member show their reason without
pinging them or anyone named in the reason. Notices are limited to once per
minute per member/channel, with at most five statuses shown in one reply.

Statuses are per server, persist through restart, and are removed by the existing
personal-data deletion flow. Disabling AFK stops notices; enabling it later does
not automatically erase saved statuses. AFK reasons are visible to server members
who mention you, so do not put private information there.

## Dashboard previews

Open Dashboard previews after signing in. Edit preview text and choose a welcome
accent color. Preview welcome card opens a PNG using the same renderer as actual
welcome cards and your cached Discord avatar when available. Preview announcement
shows escaped text in a browser; it does not emulate every Discord Markdown or
embed detail. Both are previews only: they do not publish messages, change saved
settings, or create a configuration revision. Save actual welcome settings through
the separate settings editor when satisfied.

## Configuration history and rollback

The last **100 configuration changes per server** are recorded with UTC time,
action, before/after configuration and actor. Slash commands identify the Discord
member; dashboard changes identify the OAuth user; background/host changes are
labeled system. Secrets, profiles, AFK reasons, votes, transcripts and runtime
polling updates are not configuration snapshots.

- `/admin history` lists revisions privately.
- `/admin rollback revision:ID confirm:true` restores the After configuration from
  that revision after validating current server resources.
- The dashboard shows revisions, before/after JSON, and an explicit confirmation
  form for rollback. Other servers' revisions are not accessible.

Rollback is recorded as a new revision; it does not rewrite the audit trail.
Channel/role references that are missing or unsafe must be corrected before
restoring. Discord messages, channels, moderation actions and personal records
are not rolled back. Role-button callbacks and native aliases are refreshed.
Configuration snapshots may include server-written FAQ text; treat history as
private staff data and consider it when reviewing privacy requests.

## Scheduled private configuration backups

Enable `scheduled_backups` and set `backup_hours` (1–168; default 24) and
`backup_keep` (1–30; default 7). The first overdue run backs up once, then repeats
at the selected interval while Vivi is online. Missed intervals produce one
catch-up backup, not a flood. `/admin backup_now` or the dashboard can create one
immediately without enabling the schedule.

Files are written atomically under `data/backups/SERVER_ID/` with private file
permissions on Linux and inherited folder ACLs on Windows. Retention removes only
Vivi-generated matching backup files in that server's folder. Dashboard downloads
require fresh administrator permissions and are scoped to that server.

These are **configuration backups**: settings, FAQs, flags, safe alias definitions,
role-button registrations and notification definitions. They exclude credentials,
profiles, moderation cases, ticket transcripts and live jobs. For a complete data
backup, stop Vivi and privately copy data/ plus .env separately. Secrets are never
uploaded by this scheduler. Existing /admin restore and dashboard restore accept
these files. A backup failure appears in the health dashboard and retries later.

## Windows tray controls

Run setup.bat to install the Windows-only pystray dependency, then double-click
**tray.bat**. Right-click the purple V icon to:

- Start Vivi without a terminal window.
- Stop the Vivi process tree started by that tray.
- Open the local dashboard or log folder.
- Exit the tray and stop its own Vivi process.

The tray respects Vivi's duplicate-process lock. A copy already running through
Task Scheduler or a terminal is shown as running elsewhere; the tray deliberately
does not terminate a process it did not launch. Stop that copy with Task Scheduler,
its terminal, or the appropriate host launcher before starting a tray-managed copy.
Tray launch/action failures are logged to data/logs/tray.log; bot output remains
in data/logs/bot.log. The tray is a Windows native UI, not a Docker controller.
Linux users can use systemd and the same web health/dashboard controls.

## Health dashboard and container health

`/admin health` and the authenticated web health page show observed gateway
connection, uptime, latency, timer/notification task state, ticket/record counts,
audio queue size, database size, last successful backup, notification backoffs and
recent error classes. They do not reveal keys, message contents, or another
server's personal data. Refresh the page to update it; it is not a monitoring push
service. A process existing by itself is not shown as a live Discord connection.

The scheduler writes a private heartbeat. Docker health checks require a connected
heartbeat less than 120 seconds old. This may take up to that window to detect a
crash; it does not independently call Discord or restart an unhealthy container.
See [DOCKER.md](DOCKER.md) for container deployment.

## Localization

Set server `language` to `en`, `es`, or `fr` in the dashboard or /admin setting.
Members can use `/tools language` for a personal reply-language override or choose
Server default. Core status, role/ticket/music responses, default welcome/goodbye
messages, the new AFK messages, dashboard buttons/summaries/settings labels, and
supported command names/descriptions have local English/Spanish/French catalogs.

Discord's own client language controls localized command names. The server/member
setting controls supported bot replies; the dashboard follows the server language.
Custom alias names remain as chosen. User-written text, server/channel names, AI
output, saved custom welcome text, and FAQ content are not rewritten. Catalog
coverage is intentionally explicit: strings without a translation fall back to
English. Some older command prose and documentation remain English. No external
translation API or AI is used for these built-in interface languages.

## Custom command aliases

Enable `custom_aliases`. An administrator can create shortcuts from /alias add or
the dashboard. Example:

`/alias add name:rules target:commands argument:rules`

This creates a server-only **/rules** command with the fixed FAQ search. It is also
available through `/alias run name:rules`. `/alias list` lists definitions and
`/alias remove` removes one. Alias definitions persist and are included in backups,
history and rollback; native command registration is refreshed on changes/startup.
Discord registration failures leave /alias run available and are shown in health.

Targets are deliberately informational: ping, help, commands, your own profile,
music queue, or ticket status. The target's permissions/checks and feature switches
still apply. No arbitrary code, shell commands, moderation actions, recursion or
built-in command overrides are accepted. Fixed arguments are supported only for
FAQ/command searches. Maximum 25 aliases per server; names are new lowercase
1–20-character identifiers. Alias use never grants ticket access or reveals a
private profile through a public message-prefix command: these remain slash
interactions with their normal private responses.
