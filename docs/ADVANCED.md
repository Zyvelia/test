# Channel XP, dashboard branding, filters, instant hooks and encrypted backups

Update the source and rerun setup.bat or bash setup.sh. The encryption dependency
is installed on Windows/Linux and in Docker. Existing configuration backups remain
accepted; new exports retain notification filters and the new server settings.

## Per-channel XP

Enable the existing xp feature, then use the dashboard’s Per-channel XP editor or:

`/economy channel_xp channel:#chat enabled:true amount:20 cooldown:120`

Amounts are 0–100; cooldowns are 30–3,600 seconds. Unchecking enabled excludes a
channel completely, including its message-based coin awards. Zero XP also grants
no message coins. Text and forum-channel rules can be managed in the dashboard;
threads inherit their parent rule. Removing an override restores 10 XP / 60 seconds.

The short-message/duplicate-content checks remain. Per-channel cooldowns and a
shared minimum interval prevent hopping channels to bypass the configured delay.
Configuration is per server and included in history/rollback/backups. These settings
do not alter existing XP balances or award XP for edited/AutoMod-removed messages.

## Themes and branding

Choose midnight, velvet, ocean or light, plus a validated accent, display name and
tagline. Use the dashboard editor or /admin branding. Names/taglines are escaped;
arbitrary CSS, JavaScript, HTML and remote asset URLs are not accepted.

Branding affects the authenticated server dashboard and welcome/profile footers.
The public login page keeps Vivi’s identity. It does not reserve or rename the
Discord application username or change its avatar: those stay under your control
in Developer Portal. User-provided welcome text is still customizable separately.

## Notification filters

Use the dashboard’s Notification filters or:

`/notify filters ident:SUBSCRIPTION_ID branch:main tags: categories:`

- GitHub commits: one exact branch for polling/push delivery; tag patterns instead
  require signed push webhooks. Use either a branch or tag patterns, not both.
- GitHub releases: tag patterns, such as `v2.*`, and categories `release` or `prerelease`.
- Twitch: category names/patterns, such as `Just Chatting` or `Science*`, checked for
  new stream notifications.
- Custom incoming hooks: supplied tag/category metadata can be filtered.
- YouTube RSS does not provide category metadata; unsupported category filters are
  rejected rather than claiming to work. Public upload notifications still work.

Lists are comma-separated; patterns support shell-style wildcards, not arbitrary
regular expressions. Changing filters resets the polling baseline, avoiding a flood
of older events. Filters are applied again before queued webhook delivery.

## Instant signed GitHub and custom webhooks

This is an **optional receiver separate from the administrator dashboard**. It
supports GitHub push/release notifications and custom signed JSON. Twitch/YouTube
still use polling in this release; Twitch EventSub/YouTube WebSub are not claimed.

1. Enable notifications and instant_webhooks for your server.
2. Add a normal github_commits/github_releases subscription, or a webhook subscription
   with a short source label for a custom integration.
3. In the private host .env, set WEBHOOK_ENABLED=true and WEBHOOK_SECRET to a long
   random master secret (at least 32 bytes). Do not share the master with providers.
4. Keep the native listener on loopback port 8766. Configure your own reachable HTTPS
   reverse proxy/domain to forward only `/hooks/` to this receiver. Set
   WEBHOOK_PUBLIC_URL to that origin, with no /hooks suffix. The bot does not register
   a domain, configure your router, request a certificate, or expose the dashboard.
5. Restart Vivi. /notify webhook_info ident shows the callback URL, not its secret.
6. On the host, export a **per-watch** secret into a private file outside the checkout:

   ```sh
   # Linux, or use .venv\Scripts\python.exe on Windows
   .venv/bin/python -m vivi.webhooks SUBSCRIPTION_ID --output /private/path/watch-secret.txt
   ```

7. Enter that file’s content as the GitHub repository webhook secret. Set content
   type application/json and select Push and/or Release events as appropriate.
   Each subscription has a distinct derived secret; a key for one cannot sign another.
   Keep exported files private. Never paste secrets into Discord or chat.

For custom integrations, POST JSON with id, title and an HTTPS url, plus optional
tag/category. Compute `X-Vivi-Signature: sha256=HEX_HMAC_SHA256` over the exact request
bytes using the exported per-watch secret as the HMAC key. GitHub uses its standard
X-Hub-Signature-256 header. The receiver rejects unsigned, oversized or mismatched
source payloads. Changing whitespace after signing changes the signature.

Accepted events are stored durably and normally delivered within about a second
once the bot is ready. Repeated payloads are suppressed, including across restart,
with bounded 30-day receipts. Queue capacity is 100; failures retry with backoff up
to eight attempts. Health shows pending/dead jobs. `/notify clear_webhooks ident`
discards that watch’s queued/dead jobs and keeps duplicate suppression receipts.
Disabling the feature discards queued work when the worker processes it. Provider
retries and crashes can still cause best-effort delivery behavior; exactly-once
network delivery is not promised. Polling remains a fallback for GitHub watches.

Docker publishes receiver port 8766 only to host loopback. Its internal container
bind uses the same explicit container guard as the dashboard. Forward only the
receiver through your HTTPS reverse proxy; do not publish administrator routes.
Use normal reverse-proxy body/rate limits. Provider setup and delivery from your
public domain need live testing with your own configuration.

## Encrypted full-data backups (host owner only)

These include a consistent SQLite snapshot, profiles, moderation data, configuration
history, transcripts, ratings and other persistent data files. They exclude .env,
the encryption key, existing backups, audio caches, lock/journal files and heartbeat.
The selected Vivi database is snapshotted with SQLite’s backup API and integrity
checked; independent files are checked for changes while read. For an exact stopped
filesystem snapshot, stop Vivi before creating the backup.

Full-data backups can span multiple servers, so ordinary server administrators
cannot download or restore them through Discord or the dashboard. Existing scheduled
per-server configuration JSON backups remain unchanged. The host can schedule the
full-backup CLI separately using Task Scheduler or cron if desired.

Generate a key **outside the checkout** (the default is a private user configuration
folder), and store a separate recovery copy. Key material is never printed:

```sh
# Windows:
backup.bat key
# Linux:
bash backup.sh key
```

Set BACKUP_KEY_FILE in .env to that file’s path, or pass `--key PATH`. Then:

```sh
# Windows
backup.bat create
backup.bat restore --file C:\private\full.vbackup --target C:\private\restored-vivi

# Linux
bash backup.sh create
bash backup.sh restore --file /private/full.vbackup --target /private/restored-vivi
```

Default output is data/encrypted-backups/full-....vbackup. The format uses streaming
AES-256-GCM with a random nonce and authenticated header. Wrong keys or modified
archives fail authentication before extraction. A manifest checks file digests and
sizes, paths are constrained, symlinks/duplicates/unsafe Windows names are rejected,
and restored SQLite integrity is checked. The default restore cap is 10 GiB and
100,000 files. Files use private Linux modes/inherited Windows folder ACLs.

Restore requires a new or empty directory **outside the checkout**. It never writes
over the running data directory. Stop the bot, inspect the restored data, back up
current data and deliberately move it into place afterward. Keep .env and keys
separately: losing the encryption key makes the archive unrecoverable, and .env is
not restored automatically. Plaintext temporary files live in private OS temp
folders and are cleaned up after completion/failure; allow sufficient free disk.
