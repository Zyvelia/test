See [Vivi upgrades](VIVI-UPGRADE.md) for the full dashboard, voice, moderation,
ticket tools, notifications and startup additions.

# Feature guide

New optional features start **off**. Existing welcome messages, roles, tickets,
and moderation remain on. Use `/admin features` to inspect your server and
`/admin feature name:polls enabled:true` to enable a feature. Settings are scoped
to each Discord server, not shared between servers.

Feature names: `welcome`, `welcome_cards`, `goodbye`, `autorole`, `rules`, `faq`,
`automod`, `moderation`, `appeals`, `reports`, `roles`, `tickets`, `polls`,
`giveaways`, `suggestions`, `birthdays`, `spotlight`, `games`, `daily_questions`,
`xp`, `economy`, `translation`, `ai`.

Admins use `/admin setting name:... value:...`. Use `true` / `false` for booleans,
numeric channel or role IDs for destinations, and comma-separated values for lists.
Enable Discord Developer Mode to copy IDs. Unknown settings, unsafe newcomer/rules
roles, invalid timezones, and invalid values are rejected.

## Welcome cards, departures, newcomer roles and rules

- `welcome_text`: supports `{member}` and `{server}`; up to 1,800 characters.
- `welcome_color`: hex accent, for example `#87CEEB`.
- Enable `welcome_cards` for generated PNG cards with the joining member's avatar.
  Welcome messages must also be enabled; give the bot Attach Files permission.
- `goodbye_channel`: destination channel ID; `goodbye_text` supports the same tokens.
- `autorole`: a safe newcomer role ID; enable `autorole` to apply it on join.
- `rules_text`: rules to display; `rules_role`: a safe role granted after acceptance.
  Enable `rules`, then `/community` → **Rules** (channel:#rules).

Rules acceptance is a membership-role tool, not a CAPTCHA or anti-bot guarantee.
Configure Discord channel permissions so the acceptance role unlocks your member
channels. Do not give the same role automatically on join.

## FAQ and searchable commands

The FAQ slash commands have been removed. Existing FAQ configuration is retained
in backups and the dashboard for compatibility.

## AutoMod and additional moderation

Enable `automod`, then configure:

- `spam_limit`: 1–100 messages per eight-second window; default 6.
- `blocked_words`: comma-separated whole-word/phrase matches, case-insensitive.
- `blocked_domains`: comma-separated domains; subdomains are included.

AutoMod deletes matching messages and records rate-limited cases. It also inspects
cached message edits. Members with Manage Messages are exempt. Links with embedded
credentials, raw IP hosts, punycode host labels, or denylisted domains are flagged.
This is local filtering, **not** a malware reputation/scanning service. Configure
filters to fit your community; no filtering system catches every disguised link.
Give the bot Manage Messages and Message Content Intent.

Additional commands:

- `/mod tempban member hours reason`: 1–8,760 hours; timer is stored on disk.
- `/mod unban user_id reason`: unban by numeric Discord ID and cancel the timer.
- `/mod lockdown minutes`: 1–1,440 minutes in the current text channel.
- `/mod unlock`: restore the previous bot-managed @everyone Send Messages setting.
- `/mod slowmode seconds`: 0–21,600 seconds; zero turns it off.
- `/mod history member search`: latest 15 matching numbered moderation cases.

A lockdown changes only @everyone's Send Messages overwrite. Explicit role/member
allows and administrators may still speak; threads are not locked. Expiry preserves
other overwrite fields and will not overwrite a manual change away from False.
A later human reban with a different audit reason is not removed by an old timer.
Existing warnings are migrated into numbered legacy cases once on upgrade.

`/kick` and `/ban` now ask the requesting moderator to confirm privately. Only that account can confirm or cancel, and the request expires after two minutes. Permissions, membership and hierarchy are checked again before removal. Cancelling, expiry or a rejected action creates no success case. Once Discord accepts the action, Vivi records its numbered case. Bans do not delete message history.

`dm_explanations:true` enables best-effort DMs explaining the action, reason and
case number. These are informational, not automatic punishments. Closed DMs or
Discord's rules may prevent delivery, particularly after a kick or ban.

## Appeals, private reports and privacy requests

Enable `appeals` for `/community` → **Appeal** (case_id text). A member can appeal only
their own case. Appeals are saved privately and staff are notified in the log
channel. **Banned members cannot use slash commands in the banned server.** Publish
an external appeal contact or use a separate appeals server for those members.

Enable `reports` for `/community` → **Report** (member details). This sends the allegation
to staff instead of making a public accusation. Staff can see the reporter's ID;
this is private, not anonymous. Reports and appeals have a five-minute per-user
cooldown. The bot withholds staff logs if @everyone can view the log channel;
admins should also inspect all other role/member overrides for private access.

Staff use `/mod inbox` to list pending appeals, reports and privacy requests, then
`/mod review ident response accepted`. Reviews record a response and try to DM
the requester. Accepting an appeal does **not** automatically undo a ban or timeout;
staff must apply any moderation change explicitly.

`/tools delete_data` requires a confirmation button. Close any open support ticket
first. It immediately removes the profile, birthday, AI memory, and attributable
open votes, including the keyed vote in an anonymous poll. It creates a staff
request to review moderation records, transcripts, public posts and backups.
An **administrator** can accept a privacy request with `/mod review`, which erases
remaining target moderation cases/warnings and anonymizes that member's moderator
IDs in this server. Staff must separately review exported transcripts, public
messages, request text and backups. Existing Discord roles/bans stay unchanged.
Closed aggregate poll totals remain. This does not promise deletion from Discord
or third-party providers. Privacy request records and audit entries themselves
remain available for staff review.

## Role dropdowns and permission previews

`/community` → **Role Menu** (channel category role_ids) posts a persistent dropdown.
Categories are Games, Platforms or Notifications. Enter 1–25 role IDs separated by
commas. The menu replaces only the choices belonging to that menu; unrelated roles
are preserved. Buttons and dropdowns recheck role safety whenever clicked.

`/community` → **Role Preview** (role) lists server-wide role permission bits. Channel
access may differ because of channel overrides and the member's other roles.
Notification opt-in roles are ordinary safe roles; configure the relevant channels
or announcements to use them. The bot does not automatically subscribe to external
services. Avoid posting overlapping dropdowns containing the same roles.

## Polls, giveaways and suggestions

Enable their feature flags before use. Poll/giveaway creation and staff decisions
require Manage Messages; participants do not need staff permissions.

- `/community` → **Poll** (question choices minutes anonymous): 2–10 choices separated by
  `|`. Every member gets one replaceable vote. A timer closes the poll and publishes
  totals; `/community` → **Poll Close** (ident) closes it early. Open votes persist across
  restarts. Closing removes individual ballots.
- Anonymous polls publish no identities and store a per-poll keyed hash instead of
  a raw member ID. The host still handles the Discord interaction and controls the
  database; this is not cryptographic anonymity from the host.
- `/community` → **Giveaway**: choose a prize, duration, 1–10 winners, minimum account
  age, minimum membership age, required role and minimum XP level. Requirements
  are checked on entry and again when selecting winners. No money changes hands.
- `/community` → **Giveaway Reroll** (ident): excludes previous winners and appends a
  public result. `/community` → **Giveaway History** (ident) shows the saved draw history.
  Giveaways keep entrant IDs for rerolls; privacy deletion removes their entry.
- `/community` → **Suggest** (text): posts a suggestion with support/oppose buttons; one
  replaceable vote per member. `/community` → **Suggestion Decide** (ident accepted reason)
  publishes a staff decision and closes voting. The channel where suggestions are
  posted acts as the suggestions board.

The creation command privately returns the panel ID needed by staff commands.
Keep those IDs or use the ID shown in subsequent results. Timers run every 30 seconds
while online; overdue work is retried after startup. Network failures are logged and
retained for retry. Giveaway result delivery is best effort and may be repeated if
the process crashes immediately after Discord accepts a result message.

## Birthdays, daily questions and member spotlights

- `timezone`: an IANA server timezone such as `America/New_York` or `Europe/London`.
- `daily_hour`: local hour 0–23, default 9.
- `birthday_channel`: birthday announcement destination; enable `birthdays`.
- `/community` → **Birthday** (date:07-23): opt in; no birth year is stored. Run without a
  date to opt out. Announcements use the **server** timezone. February 29 is only
  announced in leap years. No automatic birthday role is added.
- `daily_channel`: question destination; enable `daily_questions`. A rotating local
  question is posted once per calendar day after daily_hour, with restart deduplication.
- Enable `spotlight`; members explicitly opt in using `/community` → **Spotlight Optin**.
  Staff use `/community` → **Spotlight** (channel) to feature a randomly selected consenting
  current member with avatar, level and achievement count. It is a community
  appreciation post, not an assessment of popularity or behavior.

## Games, levels, achievements, and cosmetic currency

Enable `games` for `/games trivia`, `/games word`, `/games guess` and
`/games tictactoe opponent`. Trivia has multiple-choice buttons; word games offer
five guesses within two minutes; tic-tac-toe enforces alternating turns and rejects
spectator moves. Button games time out after three minutes. Active games do not
resume after a bot restart; start a new match. Multiplayer game rewards grant an
achievement, not farmable coins.

Enable `xp` for 10 XP per qualifying message, at most once per member per minute.
Messages under five trimmed characters, repeated previous content, edits and
AutoMod-removed messages do not earn XP. Level = total XP divided by 100.
Enable `economy` for two coins on an XP-awarded message, ten for a correct trivia
or word answer, and 50 from `/economy daily` once per UTC day.

- `/economy profile`: show level, XP, currency, achievements and equipped cosmetic.
- `/economy visibility public:false`: hide the profile from others and opt out of
  `/economy leaderboard`; opt back in with true.
- `/economy shop`, `/economy buy item`, `/economy equip item`: purchase and display
  cosmetic profile titles/colors. Use item `none` to unequip.

Achievements include First words, Level five, Trivia winner, Word solver,
Tic-tac-toe winner, Daily visitor and Collector. Coins have no monetary value,
cannot be bought for money, and do not modify Discord account cosmetics or roles.

## Timezones, units, and optional translation

`/tools timezone date_time:2026-11-20T18:30 source:America/New_York target:Europe/London`
converts a specified date/time. Ambiguous or nonexistent daylight-saving local
times are rejected instead of guessed.

`/tools units` supports m/km/cm/ft/in/mi; kg/g/lb/oz; l/ml/gal_us; and C/F/K.
Only compatible unit categories can be converted.

Translation requires a LibreTranslate-compatible service. Set `TRANSLATE_URL` to
its full `/translate` endpoint in the host's private `.env`, and `TRANSLATE_API_KEY`
if the service requires one. Self-hosted LibreTranslate may not require a key;
hosted providers may charge. Enable `translation`, then use `/tools translate text
target source`. Only the explicitly supplied text is sent to that provider; other
channel messages are not translated or uploaded. Configure a trusted endpoint.
Translation responses and provider quotas need live testing with your service.

## Optional AI — disabled unless explicitly enabled

All normal features work without an AI account or model. To use AI:

1. In `.env`, set `AI_BASE_URL` to an OpenAI-compatible API root ending in `/v1`,
   `AI_MODEL` to the model name, and `AI_API_KEY` only if required. A local Ollama
   example is `AI_BASE_URL=http://127.0.0.1:11434/v1` with a model you have installed.
   Install/run the model separately; it is not bundled with this repository.
2. Restart the bot to load changed environment variables.
3. `/admin setting name:ai_channels value:CHANNEL_ID,OTHER_CHANNEL_ID`
4. `/admin setting name:ai_limit value:20` sets per-member daily attempts (1–100).
5. `/admin feature name:ai enabled:true`.
6. Members can use `/ai ask` in an approved channel. Replies are private.

Turn it off any time with `/admin feature name:ai enabled:false` or the dashboard.
No new provider requests occur while disabled; responses finishing after disabling
are discarded. Memory is off unless a member chooses `/ai memory enabled:true`.
Only their own /ai requests and responses are remembered: at most three turns,
expiring after 24 hours. `/ai clear` erases the stored turns; `/ai memory enabled:false`
erases them and disables memory. The bot does not listen to every message for AI,
read ticket transcripts for AI, or let AI run moderation commands.

Attempts are limited per member per UTC day and output requests are capped at 500
tokens. Provider errors count toward the daily cap; simultaneous requests from one
member are rejected. The configured provider receives prompts and opted-in memory;
its own retention and pricing apply. No provider credentials are included in Git.

## Configuration backups, upgrades, logs and crash recovery

`/admin backup` privately downloads validated configuration JSON: channel/staff
settings, feature switches, FAQs and registered role-button IDs. It excludes tokens,
profiles, cases, tickets, transcripts, live panel definitions and timer records.
`/admin restore file confirm:true` replaces this server's configuration atomically;
backups from another server or with unknown fields are rejected. Repost panels if
needed. Version 2 backups also include notification subscription definitions;
version 1 backups are still accepted. Existing Discord channels, roles and permissions are not recreated.

For a complete local backup, stop the bot and separately preserve the entire
`data/` directory plus `.env` privately. Never upload these to the repository.
To upgrade, stop the bot, replace code while keeping data/ and .env, rerun
setup.bat and restart. Existing data is migrated automatically.

`start.bat` now runs a supervisor. Transient crashes restart with a 5–120 second
backoff; clean shutdowns, missing tokens, rejected tokens and missing privileged
intents stop instead of looping. Ctrl+C stops the supervisor. Error output appears
in the terminal and `data/logs/bot.log` (bounded local log size, previous startup log
retained when rotated). Logs may contain Discord IDs and error details: keep them
private. Optional automatic startup is now available through Windows Task Scheduler
or Linux systemd user services; see [Vivi upgrades](VIVI-UPGRADE.md) and [Linux setup](LINUX.md).
The bot cannot operate while the host is powered off or asleep.


See the [community, games and dashboard studio guide](COMMUNITY-GAMES-STUDIO.md)
for case evidence/reviews, ticket activity, LFG, opt-in timezones, reminders,
favorites, eight additional games, Steam news and visual dashboard editors.

See the [teams, tournaments and profiles guide](TEAMS-PROFILES-TOURNAMENTS.md)
for invite-source estimates, team recruitment, game libraries, five more games,
profile cosmetics/privacy and dashboard navigation improvements.

The [arcade design guide](GAME-DESIGN.md) covers illustrated game cards, themes,
private quick controls, text boards and recommended next improvements.
