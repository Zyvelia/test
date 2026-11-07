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
Artwork stays in `assets/vivi/avatars`; public site code is in `vivi/web` and
`vivi/website.py`. Server-specific dashboard themes remain separate from public
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
