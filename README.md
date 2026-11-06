# Aurora Discord Bot

A Discord server bot you can run on your **Windows PC** for free. Includes welcome
messages, self-service role buttons, staff moderation, and private support tickets.
This replaces the Minecraft project; previous versions remain in Git history.

## What it does

- Welcomes new members in your chosen channel.
- Lets members add/remove safe roles using persistent buttons.
- Records warnings and offers timeout, untimeout, kick, ban, and message cleanup.
- Creates one private support ticket per member. The member, support role, bot,
  and server administrators can see it.
- Confirms ticket closure, saves a text transcript, and deletes the ticket channel.
- Remembers server settings, warnings, roles, and tickets after restarting.

There is no AI API, paid subscription, or port forwarding required. Keep your PC
awake, online, and the bot terminal open. Closing it, shutting down, or sleeping
stops the bot. Run only **one copy** for a given bot token/database.

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
   Name it whatever you like, such as Aurora.
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

1. Double-click **start.bat**. Wait for `Connected as ...` in the terminal.
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
Warnings are stored and logged; they are not automatically sent to the member.

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
- `data/aurora.sqlite3`: settings, warnings, role registrations, and open tickets.
- `data/transcripts/`: saved text transcripts; excluded from Git.

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
python -m aurora.bot
```

Automated tests exercise database persistence, ticket concurrency/privacy, cleanup
on failures, permission policy, and persistent component registration without
connecting to Discord. GitHub Actions runs the suite on Linux and Windows.
Actual Discord login, live channel permissions, welcome events, and the Windows
batch launchers still need testing on your server/PC. No bot token is included.
