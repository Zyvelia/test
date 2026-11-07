# Vivi website

Vivi includes a responsive website with the selected short-haired avatar (option 3),
invite buttons, feature pages, a searchable directory of the bot's actual commands,
and a Discord-authenticated dashboard connected to the existing server settings.
The three FAQ slash commands have been removed. Existing FAQ configuration remains
in backups and the dashboard; legacy FAQ aliases no longer register slash commands.

## Run on your PC without a domain

1. Run the normal setup for [Windows](../README.md) or [Linux](LINUX.md).
2. In your local `.env`, set `DASHBOARD_ENABLED=true`.
3. Start Vivi with `start.bat` or `bash start.sh`.
4. Open **http://127.0.0.1:8765** on that computer. The dashboard is at
   **http://127.0.0.1:8765/dashboard**.

Public pages and the invite button work without an OAuth client secret. The website
runs inside the bot process and stops when that process stops. This local address
is accessible on your computer; it is not a publicly hosted website or shareable
internet address. GitHub stores the code, not the running Python backend.

## Enable Discord dashboard login

At https://discord.com/developers/applications select Vivi, open OAuth2, and register
this exact redirect: `http://127.0.0.1:8765/callback`.
Set these locally and restart:

```dotenv
DASHBOARD_ENABLED=true
DISCORD_CLIENT_ID=1568121020047429775
DISCORD_CLIENT_SECRET=your_oauth_client_secret
DASHBOARD_REDIRECT_URI=http://127.0.0.1:8765/callback
WEBSITE_AVATAR=neon-bob
```

The OAuth client secret differs from the bot token. Keep both in your local `.env`.
Choose **Sign in with Discord** and authorize `identify` and `guilds`. Select a
server you own or administer; install Vivi first if it is not there. Changes use
the same database and settings as the Discord commands. AI still needs its own
provider, feature switch and allowed channels.

Login uses single-use cookie-bound state. Sessions expire in one hour and disappear
on restart. Every private page and action rechecks current Discord Administrator
or owner permissions. Writes require CSRF tokens and check supplied browser origins.
OAuth tokens remain in process memory. Credentials never appear in the website.
Live OAuth authorization requires your application's credentials and a correctly
registered redirect; automated tests use temporary synthetic accounts only.

## Optional future public hosting

A domain is not needed for local use. For a shareable site, run the Python bot and
website continuously on your PC or a Linux host behind an HTTPS reverse proxy.
Configure your real domain and its certificate before switching the redirect:

```dotenv
DASHBOARD_REDIRECT_URI=https://vivi.example.com/callback
DASHBOARD_LISTEN_PORT=8765
DASHBOARD_BIND_HOST=127.0.0.1
```

Register that exact HTTPS callback in Discord too. The proxy must preserve the
public Host header and forward to `127.0.0.1:8765`; for example, a Caddy site:

```caddyfile
vivi.example.com {
    reverse_proxy 127.0.0.1:8765
}
```

Replace the example domain with one you control and configure its DNS. HTTPS mode
marks authentication cookies Secure. The app accepts only the configured public
hostname and origin, without trusting arbitrary forwarded headers. Native binds
remain on loopback; container mode can bind internally to `0.0.0.0` while Compose
publishes only on host loopback. See [Docker](DOCKER.md). Do not expose the HTTP
backend port directly. A static-only host cannot run this dashboard backend.

## Customize and preview

`WEBSITE_AVATAR` accepts `neon-bob`, `neon-headset`, `silver-crown` or `velvet-moth`.
Artwork stays in `assets/vivi/avatars`; public site code is in `vivi/site/web` and
`vivi/site/website.py`. Server-specific dashboard themes remain separate from public
site branding. Bot status reflects its actual connection; no fabricated usage
statistics are displayed.

For development without a Discord connection, run
`python scripts/preview_website.py`. Add `--dashboard-preview` only for synthetic
local server data. This uses a temporary database and never loads `.env`.
Browser checks run with `npm ci --prefix tests/ui`,
`npx --prefix tests/ui playwright install chromium`, then
`npm --prefix tests/ui run test:website` after installing Python requirements.

If the page does not open, check the enabled flag, startup logs and port availability.
If login returns a setup message, configure OAuth credentials. If Discord rejects
login, match the redirect exactly, including the hostname, port and `/callback`.

## Account and settings synchronization

After login, the website header shows your Discord display name and avatar (or an
initial when no avatar is set). Open that menu for Your servers or Sign out. The
sign-in link is hidden on public and dashboard pages while your session is valid.
The footer's “Vivi bot online/offline” describes the bot connection, not your login.

On a server dashboard, use feature switches to enable modules and **Customize** to
open related controls. Welcome text and colors, moderation limits, AI channels,
voice settings, XP overrides, notifications and other supported settings save to
the same server database used by Discord commands. Provider credentials remain
host configuration. Save each setting to apply it; unsaved typing is not sent.
Open dashboards check the saved configuration every 30 seconds and when you return
to the tab. A changed configuration reloads automatically when no form has edits.
When you have unsaved edits, a notice offers to reload rather than discarding them.

The website now includes a dedicated [feature manager](WEB-MODULES.md) at `/modules`.
Select a server, browse module cards and enable/disable features directly. Configure
links open the relevant detailed settings; switches share Discord's saved state.

## Customize modules and event messages

Every active module’s **Configure** button opens a page for that module. Supported server-wide settings use the same validation and database as Discord settings commands. Modules with specialized editors link to those editors; member preferences and individual activities remain in their Discord menus. Global-ban participation retains its separate server-owner consent requirement. Provider credentials remain host configuration.

For **Welcome** or **Goodbye**, choose a destination channel, enable the message, and select text or an embed. Welcome setup works without configuring tickets. Write text with `{member}`, `{username}`, `{server}` and `{member_count}`, or choose a saved template from **Embed writer**. Text welcomes may mention the joining member; embeds and goodbye messages disable mentions. Welcome cards can be included in text welcomes; their layout editor is linked on the page.

**Preview without saving** shows a sample without writing settings or sending to Discord. Use browser Back to preserve the draft. **Save message settings** validates the complete form before saving it together; new join/departure events use it immediately. Enabled messages require a valid channel and the corresponding bot permissions. Disabled drafts can be saved without a destination.

Selecting an embed copies its content into the event settings. This copy is included in configuration backups and remains usable if the library template is deleted. After editing a library template, select it again in the welcome/goodbye composer and save to apply the new version. Previously posted messages remain unchanged. Placeholder expansion is bounded to Discord embed limits.

Changes made through Discord appear on reloading the page. Open customization pages also check for changes automatically and reload only when no unsaved edits exist; otherwise they offer to reload. The welcome channel is shared with existing server setup commands and does not require a bot restart.

## Grouped dashboard sections

The module manager groups related controls into 11 expandable sections: Welcome & joining; Moderation & safety; Tickets & support; Levels & profiles; Games & events; Community activities; Teams & gaming groups; Music & voice; Notifications; AI & translation; Server tools. Each feature still has its own switch, so grouping never enables or disables features implicitly.

Search and category/status filters reveal matching nested controls. Configuration pages share related-setting tabs and the same grouped navigation. Welcome-card, XP, ticket, subscription, alias and scheduled-backup editors appear inside the relevant module. Their save actions return to that module. General setup/history/appearance tools remain under **Server tools**; the old prominent Detailed settings link is removed, and advanced bulk switches start collapsed.

A busy Discord API does not log you out. The website preserves your profile during HTTP 429, transient service failures and connection problems. Only a genuine expired local session or Discord HTTP 401 asks you to reconnect. Permission denials use a permission message rather than telling a still-signed-in member that the login expired. All cache/session data remains in memory and disappears on bot restart.

## Staff workspace

The new [staff dashboard](STAFF-DASHBOARD.md) adds current staff-role checks, cases, reports/appeals and ticket lists. Use **Staff workspace** in the sidebar. Feature configuration remains administrator-only. The server home card shows real member count, online status and enabled modules; message editors update their sample preview live.
