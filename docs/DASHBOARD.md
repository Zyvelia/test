# Optional Windows dashboard

The dashboard is optional. Slash commands work without it or an OAuth secret.
It runs only on your PC's loopback address and lets current server administrators
view and change feature switches. Detailed channel/role settings remain available
through `/admin setting` inside Discord.

1. Open your application at https://discord.com/developers/applications.
2. Under OAuth2, add the redirect URI exactly:
   `http://127.0.0.1:8765/callback`
3. Copy the application's **Client ID** (Application ID) and **Client Secret** into
   your local `.env`. The client secret is different from the bot token. Do not
   put either secret in chat, GitHub, screenshots, or a public configuration file.
4. Set these values locally:

   ```dotenv
   DASHBOARD_ENABLED=true
   DISCORD_CLIENT_ID=your_application_id
   DISCORD_CLIENT_SECRET=your_client_secret
   DASHBOARD_REDIRECT_URI=http://127.0.0.1:8765/callback
   ```

5. Restart with `start.bat`. On that same PC, type `http://127.0.0.1:8765` in your
   browser. Choose **Sign in with Discord** and approve the `identify` and `guilds`
   scopes. This does not ask for your Discord password inside the bot's own page.
6. Choose a server you own or administer where this bot is installed, and enable
   or disable features. AI still needs a configured provider and approved channels.
7. Use **Sign out** when done. Sessions expire within one hour and are lost when
   the bot restarts. Set DASHBOARD_ENABLED=false and restart to disable the listener.

The listener refuses external interfaces. Do not forward its port or try to publish
it through a tunnel. Public hosting would need a separate HTTPS deployment design.
For a different port, change both the registered Discord redirect and .env to the
same loopback URL, including `/callback`. If using `localhost` instead of
`127.0.0.1`, use it consistently in the browser and registered redirect.

OAuth state is single-use and bound to a browser cookie. Sessions use HttpOnly,
SameSite cookies; feature-change forms require a CSRF token. Every action fetches
fresh Discord server permissions, so a revoked administrator cannot keep using an
old session. Feature changes and server selections are scoped to a permitted
server. Cookies are not marked Secure because this is HTTP on loopback; only the
local browser should connect. OAuth tokens and session state stay in process memory,
not configuration backups. Bot tokens and provider keys are never displayed.

If the page will not open, inspect the terminal: verify that the feature is enabled,
OAuth credentials are present, and the port is unused. If Discord rejects login,
check that the registered redirect exactly matches the configured value. If no
servers appear, make sure you have Administrator permission (or own the server)
and the bot is installed there. Browser security paths are covered by automated
local tests; live OAuth login still needs your Discord application credentials.
