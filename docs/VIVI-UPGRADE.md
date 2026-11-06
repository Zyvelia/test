# Vivi upgrade: dashboard, startup, voice, moderation, tickets and notifications

Update code while preserving your private `.env` and `data/`. Run `setup.bat` on
Windows or `bash setup.sh` on Linux to install the updated Discord voice library.
The Python package is now **vivi**, so developer commands use `python -m vivi.bot`.
Existing database files and old ticket/role buttons remain supported. The visible
bot name/avatar in Discord must be changed in Developer Portal → Bot; local code
cannot reserve a Discord name or rename your Discord application automatically.

New feature flags (`music`, `voice_rooms`, `notifications`, `ticket_tools`,
`raid_protection`, `mention_protection`, `warning_thresholds`) start **off**.
AI remains off unless you already enabled it. Inspect `/admin features`.

## Full local dashboard

Follow [DASHBOARD.md](DASHBOARD.md) for Discord OAuth login. The dashboard now edits:

- Welcome/log channels, support role and ticket category.
- Welcome text/color, goodbye settings, newcomer/rules roles, filters, timezones,
  birthday/daily channels, AI-approved channels/quotas, and other validated settings.
- FAQs with add/remove controls.
- Ticket category labels with category selectors; open ticket owner/claim/priority status.
- Twitch, YouTube and GitHub notification subscriptions with metadata tests.
- Feature switches and configuration backup/restore with explicit confirmation.
- Read-only bot permission checks and explicit optional provider smoke tests.

Fields validate channel types, server membership, safe assignable roles, ranges,
private staff logs and allowed values. Every change rechecks Discord administrator
permissions and CSRF. Secrets are still edited only in the host's private .env;
the dashboard never reveals or changes tokens. Staff use Discord commands to claim,
move or reprioritize a ticket. Creating live role/ticket/rules panels stays explicit
through the existing Discord commands; the dashboard does not silently post them.

Configuration backup version 2 includes subscription definitions, with a fresh
baseline on restore. Version 1 backups are still accepted. Tokens, profiles, cases,
transcripts, timer state and in-progress games/audio are not configuration backups.
For a complete local backup, stop Vivi and preserve the whole data/ directory.

## Optional Windows automatic startup

After normal setup, double-click **install-startup.bat**. It creates a limited,
current-user Task Scheduler task and starts Vivi in the background when you sign
in after a reboot. It does not need or save your Windows password. It does not
start before login. Keep the installation folder in the same location.

Use **remove-startup.bat** to stop/remove that task. You can inspect/start/stop it
in Windows Task Scheduler (`ViviBot-` followed by your Windows SID). Do not also
run start.bat while the scheduled copy is active; a process lock prevents duplicate
bot instances from this folder. Background logs are in data/logs/bot.log. Errors
such as a missing/rejected token stop instead of causing endless restarts.

See [LINUX.md](LINUX.md) for the equivalent systemd user-service installer, optional
boot-without-login lingering, and Linux launch/verification scripts.

## Uploaded music and voice rooms

The pinned discord.py voice extra includes PyNaCl and DAVE support. Also install
FFmpeg on the host. On Windows, one option is `winget install --id Gyan.FFmpeg --exact`,
then reopen the terminal; or set FFMPEG_PATH in .env to your ffmpeg.exe. On Linux,
install ffmpeg and libopus using your distro's signed packages (see LINUX.md).

Enable `music`, join a normal voice channel, then:

- `/music play file`: upload MP3, WAV, OGG/Opus, FLAC or M4A under 10 MiB.
- `/music queue`, `/music pause`, `/music resume`, `/music skip`.
- `/music stop`: clear the queue; `/music leave`: clear/disconnect.
- `/music volume percent`: 0–100, default playback volume 50%.

At most ten tracks wait in the queue, plus the current track. Other voice channels
cannot control that queue. Any member in the same voice channel can use playback
controls. Vivi leaves when the last human leaves; disabling music stops it on the
next maintenance pass. Queues do not survive restarts. Files are deleted after use,
with deferred cleanup for OS file locks. Only uploaded attachments are supported;
YouTube/Spotify searching or streaming and voice recording are not included.
FFmpeg receives a local filename and a fixed audio format, not a supplied URL.

For temporary rooms, enable `voice_rooms` and set:

- `voice_lobby`: ID of the join-to-create voice channel.
- `voice_category`: destination Discord category ID.
- `voice_user_limit`: 0–99 (zero is unlimited).

Vivi needs View Channel, Connect, Speak for music; Manage Channels and Move Members
for join-to-create. It preserves destination category restrictions, allows the
owner into their own room, and mediates owner controls without granting them
Manage Channels. `/room rename`, `/room limit`, and `/room lock locked:true/false`
control a room you own. Unlock restores the original @everyone Connect setting;
explicit role/member allows can bypass a room lock. Empty rooms are cleaned up
within a maintenance cycle after a short creation grace period, including after
restart. Maximum 25 temporary rooms per server.

## Advanced moderation options

Enable only the protections you want, then use the dashboard or /admin setting:

| Feature | Settings | Behavior |
|---|---|---|
| `mention_protection` | `mention_limit` (default 5) | Delete messages exceeding the number of unique mentioned users/roles, or mentioning @everyone/@here. |
| `raid_protection` | `raid_limit` (8), `raid_window` (30 seconds) | Detect a burst of joins, record an alert and pause automatic newcomer roles for five minutes. |
| Raid action | `raid_action`: alert or lockdown; `raid_channel`; `raid_lock_minutes` (5) | Optional timed @everyone Send Messages deny in one configured text channel; preserves the previous setting. |
| `warning_thresholds` | `warning_count` (3), `warning_window_days` (30), `warning_timeout_minutes` (10) | Apply a timeout at each multiple of the configured recent manual-warning count. |

Raid protection does not automatically ban newcomers or prevent joining. A channel
lockdown does not defeat explicit role/member allows or administrators. Disabling
raid protection resumes normal newcomer roles; an already-created timed lockdown
still restores its permission when due. Staff with Manage Messages are exempt
from message filtering. Warning thresholds act on /warn records, not on every
AutoMod deletion, and respect Discord hierarchy/permissions. A failed automatic
timeout is logged for staff. Target owners, administrators, bots and other protected
members are still subject to Discord's moderation restrictions.

## Ticket upgrades

Enable `ticket_tools`. Add labeled Discord categories in the dashboard, or set
`ticket_categories` to JSON such as `{"Support":123456789012345678,"Reports":234567890123456789}`.
Opening a ticket offers a category selector; the support role is still the one
configured by /setup. Existing tickets default to General/normal/unclaimed.

Inside a ticket:

- `/ticket claim` claims it; another staff member cannot steal the claim.
- `/ticket release` releases your own claim; Manage Channels can override.
- `/ticket priority value`: low, normal, high or urgent.
- `/ticket category label`: move to a configured category **without syncing** its
  permissions, so the ticket's private overwrites are preserved.
- `/ticket status`: show metadata to the ticket owner or staff.

Claims/priorities/categories persist through restart and appear in transcripts.
Closing retains the existing transcript confirmation, then attempts to DM the owner
one 1–5-star satisfaction request, valid seven days. Only that owner can submit a
single rating; staff see it in private logs. Closed DMs may prevent delivery.
Ratings are identifiable feedback, not anonymous. Profile deletion removes their
stored rating records. Ticket tools do not restrict a claimed ticket's visibility
from other support staff.

## Twitch, YouTube and GitHub updates

Enable `notifications`. Configure subscriptions in the dashboard or:

`/notify add provider source channel`

Providers and source formats:

- `twitch`: public Twitch channel login. Set TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET
  in .env; create a Twitch developer application and use its app credentials.
- `youtube`: public YouTube channel ID beginning `UC` (not a handle or full URL).
  Uses the public uploads RSS feed; no YouTube API key is needed.
- `github_releases`: `owner/repository`, watches non-draft release metadata.
- `github_commits`: `owner/repository`, watches the latest commit metadata.

Use `/notify list` and `/notify remove ident`. The first successful poll establishes
a baseline so old events are not flooded into the channel. Later polls run about
five minutes apart; up to five recent events are considered. Twitch posts when a
new stream session appears. API failures use a ten-minute backoff. Notifications
run separately from moderation timers, so slow APIs do not delay lockdown expiry.
There is no webhook listener, inbound port forwarding, media scraping, or browser
login automation. Providers may impose quotas; the bot must remain online.

Public GitHub requests work without a token but have lower limits. For a private
repo or a higher authenticated limit, use a minimally scoped NOTIFY_GITHUB_TOKEN
and explicitly bind its allowed server/repository pairs in the host's .env:

```dotenv
NOTIFY_GITHUB_TOKEN=your_token_locally
NOTIFY_GITHUB_ACCESS={"123456789012345678":["owner/repository"]}
```

The token is not attached for other server/repository pairs. This prevents an
administrator of an unrelated server from using the host's token to read private
repositories. It is never displayed by the dashboard or included in backups.
Subscriptions have a per-server limit of 20. Metadata tests do not post to Discord;
actual notifications post only to the configured destination with mentions disabled.
Delivery is best effort; a crash immediately after a successful post can cause a
repeat. YouTube feed timing and GitHub/Twitch quotas are controlled by those services.

## Live verification

Run **verify.bat** on Windows or `bash verify.sh` on Linux. It checks a configured
bot login and server/channel permissions using read-only Discord metadata, with
results written to data/verification.json. `/admin verify` checks the current
server from the running bot. No test messages are posted.

By default provider calls are unrun. Explicitly use `verify.bat --providers` or
`bash verify.sh --providers`, or check the dashboard's provider-test checkbox,
to send tiny AI/translation requests (which may cost money). Tests never print
credentials. A missing setting is reported as not configured, not a pass.
The dashboard can test notification provider metadata without posting it.

Complete a real browser OAuth sign-in to verify your Discord app redirect/client
secret. A successful logged-in dashboard check reports that actual session as
verified. The CLI does not claim to verify an interactive OAuth flow. Voice needs
a real Discord voice-channel test from your account: automated tests validate
local decoding and controls, not live encrypted audio delivery.
