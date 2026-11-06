# Vivi Discord Bot

A Discord server bot you can run on **Windows or Linux** for free. Includes welcome
messages, self-service role buttons, staff moderation, and private support tickets.
This replaces the Minecraft project; previous versions remain in Git history.

## What it does

- Custom welcome cards, goodbye messages, safe newcomer roles, and rules acceptance.
- FAQ search, role dropdowns for games/platforms/notifications, and permission previews.
- Spam/word/link filtering, numbered moderation cases, temporary bans, lockdowns,
  slowmode, private reports, appeals, and opt-in moderation explanations.
- Support tickets, polls (including anonymous voting), eligible-entry giveaways,
  public reroll history, and a suggestion voting board.
- Opt-in birthdays/spotlights, daily questions, trivia, word games and tic-tac-toe.
- XP with anti-spam limits, private-profile/leaderboard opt-out, achievements,
  virtual currency and cosmetic profile titles/colors.
- Timezones, unit conversions, optional translation, and data deletion requests.
- Per-server switches, configuration backups/restores, and a local Discord-login dashboard.
- Optional AI with channel restrictions, daily quotas, and opt-in expiring memory.
- Crash recovery, optional Windows/Linux automatic startup, and private local error logs.
- Uploaded-audio queues, temporary voice rooms, advanced moderation options, ticket
  claiming/categories/priorities/ratings, and Twitch/YouTube/GitHub notifications.

**AI is off by default.** All new optional features start off; enable only the ones
you want with `/admin feature`. Existing welcome, roles, tickets and moderation
remain enabled. `/admin features` lists all switches; `/tools commands search:...`
searches the command menu. Settings and saved data are isolated by server.

Read the [complete feature guide](docs/FEATURES.md) for each command and setting,
or the [optional dashboard setup](docs/DASHBOARD.md) for browser controls.

No paid subscription or port forwarding is needed for the core bot. Optional hosted
translation/AI providers may charge; local models need a separate model server.
Keep your PC awake, online, and the terminal open. Run only **one copy** for a given
bot token/database. The launcher restarts crashes but cannot run while your PC sleeps.

## Linux support and latest upgrades

For Linux, see [Linux setup and systemd startup](docs/LINUX.md): `bash setup.sh`,
then `bash start.sh`. All core bot, dashboard, voice and notification features use
the same Python code on both operating systems.

The [Vivi upgrade guide](docs/VIVI-UPGRADE.md) covers the full dashboard, Windows
Task Scheduler/Linux systemd startup, uploaded-audio music, temporary voice rooms,
raid/mention/warning protections, staff ticket tools, ratings and external alerts.
New capabilities remain optional and off by default. Run `verify.bat` or
`bash verify.sh` for a report distinguishing live passes, missing configuration and
checks that still need your browser or a real Discord voice connection.

## 1. Download and prepare (Windows)

1. On this repository, select **Code → Download ZIP**.
2. Right-click the downloaded ZIP → **Extract All**. Open the extracted folder.
3. Install **Python 3.11 or newer** from https://www.python.org/downloads/windows/.
   Include the Python launcher (`py`) during installation. Python 3.12 is tested.
4. Double-click **setup.bat**. It creates an isolated Python environment, installs
   dependencies, and opens your private `.env` configuration in Notepad.

Always extract the ZIP first; do not launch the scripts from inside the ZIP.
You can rerun setup.bat to refresh dependencies; it preserves an existing .env.

## 2. Create your Discord bot

1. Open https://discord.com/developers/applications and choose **New Application**.
   Name it whatever you like, such as Vivi.
2. Open **Bot**. Use **Reset Token** to generate its token if needed. Paste the
   token only into the local `.env` file after `DISCORD_TOKEN=`. Save the file.
   **Never send the token in chat, upload .env, or show it in a screenshot.**
3. On that same Bot page, enable **Server Members Intent** and
   **Message Content Intent**. Member events power welcome messages; message
   content is used for ticket transcripts, not for prefix commands.
4. In **OAuth2 → URL Generator**, select scopes **bot** and **applications.commands**.
5. Select bot permissions: **View Channels**, **Send Messages**, **Read Message
   History**, **Embed Links**, **Attach Files**, **Manage Roles**, **Manage Channels**,
   **Manage Messages**, **Moderate Members**, **Kick Members**, and **Ban Members**.
   For optional voice tools, also grant **Connect**, **Speak**, and **Move Members**.
   Administrator permission is not required.
6. Open the generated invite URL, choose your server, and authorize it. You need
   permission to manage that server.
7. In Discord **Server Settings → Roles**, move the bot's role above roles it will
   assign and members it will moderate. Keep human administrator roles above it.

`.env` example (use your real token locally):

```dotenv
DISCORD_TOKEN=paste_your_token_here
DEV_GUILD_ID=
```

Optional: enable Developer Mode in Discord, right-click your server → Copy Server
ID, and place it after `DEV_GUILD_ID=`. This registers commands immediately for
that test server. Leave it blank for global commands, which can take time to show.
If you change between test-server and global registration, Discord may temporarily
show duplicate or stale commands; keep one mode for normal use.

## 3. Start and configure

1. Double-click **start.bat**. The crash supervisor starts the bot; wait for `Connected as ...` in the terminal.
2. In your server, create a **Support Staff** role, a **Support Tickets** category,
   a welcome text channel, and a private staff-log text channel.
3. In the log channel permissions, deny **View Channel** for `@everyone`; allow
   only your trusted staff and the bot. Check other role overrides too. Transcripts
   may contain personal messages, so keep this channel private.
4. Give the bot View Channel and Manage Channels in the ticket category; also let
   it send messages, read history, embed links, and attach files in its channels.
5. As a server administrator, run:
   `/setup welcome:#welcome ticket_category:Support Tickets staff:@Support Staff logs:#staff-log`
   Choose the actual channels and role from Discord's menus.
6. Run `/ticket_panel channel:#support` to post the support button.
7. Create an ordinary member role below the bot's role, then run
   `/role_button channel:#choose-roles role:@Gaming label:Gaming`.
8. Test `/ping`, click a role button, open a ticket, and close it. Also test joining
   with another account to check the welcome message.

Role buttons refuse managed roles, @everyone, the configured support role, and
roles with moderation/management permissions. Rechecking at click time prevents a
previously safe role from granting those permissions after an admin changes it.
Do not use a self-service role to grant access to sensitive private channels.

## Commands

| Command | Required member permission | Purpose |
|---|---|---|
| `/ping`, `/help` | None | Status and help |
| `/setup` | Administrator | Save this server's channels/support role |
| `/role_button` | Administrator | Post an opt-in role button |
| `/ticket_panel` | Administrator | Post a private-ticket button |
| `/warn member reason` | Moderate Members | Record a warning |
| `/warnings member` | Moderate Members | Show the latest ten warnings privately |
| `/timeout member minutes reason` | Moderate Members | Timeout for 1 minute to 28 days |
| `/untimeout member` | Moderate Members | Remove a timeout |
| `/kick member reason` | Kick Members | Remove a member |
| `/ban member reason` | Ban Members | Ban without erasing message history |
| `/purge count` | Manage Messages | Delete up to 100 recent messages |

Moderation also checks the human moderator's and bot's role hierarchy. The server
owner, bot itself, moderator themselves, and equal/higher roles are protected.
Discord still enforces its own permissions, including timeout restrictions.
Warnings are stored and logged. To send best-effort private explanations, set
`/admin setting name:dm_explanations value:true`. Every moderation action also
gets a searchable staff case number.

Only a ticket's creator, configured support staff, or someone with Manage Channels
can close it. Closing requires a second confirmation. It saves the **most recent
1,000 messages** in chronological order to `data/transcripts/CHANNEL_ID.txt` and
attempts to upload a copy to staff logs before deleting the channel. If local
transcript creation fails, the channel stays open. A failed log upload still
leaves the local file. Attachments are saved as URLs, not downloaded files;
Discord attachment links can expire. Embeds, edits, deleted messages, and threads
are not archived. This is a basic support transcript, not a complete server backup.

## Local files and backups

- `.env`: private bot token; excluded from Git.
- `.venv/`: isolated installed dependencies; excluded from Git.
- `data/vivi.sqlite3`: settings, warnings, role registrations, and open tickets.
  Existing `data/aurora.sqlite3` installations are reused automatically; do not keep
  both databases in the same data directory.
- `data/transcripts/`: saved text transcripts; excluded from Git.
- `data/logs/`: bounded local crash/error logs; excluded from Git.
- The database also stores optional profiles, votes, timers, appeals and AI memory
  for features you explicitly enable. See the feature guide for deletion and retention.

Stop the bot before backing up `data/`. Keep the backup and .env private. Delete
old transcripts manually according to your server's retention needs. This bot
stores member IDs, moderation reasons, and ticket message text; tell members how
support transcripts are retained. The database is not encrypted on disk.

## Troubleshooting

- **Token rejected:** reset it in Developer Portal → Bot and update .env.
- **Privileged intents error:** enable both intents listed above, then restart.
- **Commands missing:** check invite scopes, restart Discord, or use DEV_GUILD_ID.
- **Missing permissions / role updates fail:** check channel overrides and ensure
  the bot role is above the target role. Discord administrators still need a bot
  with sufficient role hierarchy.
- **Ticket category or staff missing:** rerun /setup with existing resources.
- **Bot goes offline:** leave the terminal open and disable PC sleep while hosting.
- **Transcript upload failed:** check Attach Files and private log channel access;
  find the local transcript under data/transcripts.

## Development and validation

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m vivi.bot
```

Automated tests exercise database migrations and persistence, ticket privacy,
moderation policy, timer recovery, voting, economy, opt-in AI controls and local
dashboard HTTP/OAuth permission paths without connecting to Discord or AI providers. GitHub Actions runs the suite on Linux and Windows.
Actual Discord bot/OAuth login, live channel permissions, external providers,
voice delivery and Windows startup still need testing on your own server/PC.
Linux setup, local audio decoding and dashboard HTTP behavior are tested here;
actual service activation depends on your host’s systemd user session. No bot token is included.
