# Vivi dashboard on Windows and Linux

The dashboard is integrated with Vivi's website. See [the website setup guide](WEBSITE.md)
for local startup, Discord OAuth login, artwork choices and optional HTTPS hosting.

Open `http://127.0.0.1:8765/dashboard` after enabling `DASHBOARD_ENABLED=true` and
starting Vivi. Public pages do not need OAuth credentials; private settings require
Discord login and current server owner or Administrator permissions.

Existing feature switches, detailed settings, previews, configuration history,
backup controls, aliases, welcome-card and announcement editors remain connected
to the bot database. See [PRODUCTIVITY.md](PRODUCTIVITY.md) and
[the detailed settings guide](VIVI-UPGRADE.md#full-local-dashboard).
