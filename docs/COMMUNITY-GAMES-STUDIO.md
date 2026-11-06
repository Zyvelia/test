# Vivi: community, games and dashboard studio

These additions work with the same Windows, Linux and Docker launchers. **Rerun
`setup.bat` or `bash setup.sh` after updating** to install the pinned chess rules
library. Rebuild your image if you use Docker. Restart Vivi to register commands;
a development server set with `DEV_GUILD_ID` receives them immediately. Global
Discord command changes may take time to appear.

## Enable the optional features

Use the dashboard switches or `/admin feature name:… enabled:true` for:

| Switch | Enables |
| --- | --- |
| `staff_reviews` | New conduct forms and internal blocklist appeals |
| `ticket_tools` | Existing ticket tools and ticket labels |
| `lfg` | Looking-for-group boards |
| `timezone_directory` | Public, explicitly opt-in local-time directory |
| `reminders` | Creation and delivery of personal reminders |
| `games` | Games, including the eight new games below |
| `notifications` | Scheduled Steam and other provider notifications |
| `welcome_cards` | Sends the configured card to new members |

All these optional features default to off. Existing moderation permissions still
apply. Favorites and private timezone preferences do not require an economy/XP
profile to be public. Saved review history remains privately accessible when new
review submissions are switched off.

Use `/admin option name:reviewer_role value:ROLE_ID` for a dedicated independent
reviewer role. Administrators can also review, except when they are the author or
subject of that submission. Configure `review_channel` with a private text channel
that denies **@everyone → View Channel**. That channel receives only opaque review
references, never complaint contents or identities. Review details are returned
privately to an eligible reviewer. Host administrators with access to the database
and backups still control the underlying files.

Configure `lfg_channel` with the group-board text channel. `lfg_hours` controls
expiry (1–72 hours, default 24). The dashboard provides channel/role selectors.

## Moderation and review tools

| Command | What it does |
| --- | --- |
| `/cases warning_remove warning_id reason` | Removes the active warning and creates an audit case containing its original moderator, original reason, remover and removal reason. Both database changes commit together. Role hierarchy applies to current members. Existing cases remain. |
| `/cases evidence_add case_id attachment note` | Stores a private local copy of a case attachment, with uploader, size and SHA-256 integrity hash. Allows ten files per case, 8 MiB each; PNG/JPEG/WebP/TXT/PDF/JSON only. |
| `/cases evidence_list case_id` | Privately lists a case’s attachment IDs for staff with Moderate Members permission. |
| `/cases evidence_get evidence_id` | Returns a file privately after checking server, permission and integrity. Evidence has no public dashboard download URL. |
| `/cases conduct member` | Opens a private form for an incident description, when/where and optional evidence links about a staff member. Each author may have three open submissions of each type. |
| `/cases reviews` | Lists submissions the current independent reviewer can access. |
| `/cases review review_id status reason` | Reads a submission or records an under-review/accepted/declined decision and reviewer reason. Final decisions cannot be overwritten through this command. |
| `/cases my_reviews` | Lets authors privately track their own submission statuses and responses. |
| `/cases blocklist member action reason` | Maintains an internal staff reference list with an audit history. Requires Ban Members and role hierarchy. It does **not** automatically ban, unban or block access. |
| `/cases blocklist_appeal` | Lets a listed member submit their own appeal. Acceptance removes the internal listing and records the reviewer decision; Discord ban status is unchanged. |

Members banned from Discord cannot use in-server appeal commands. Keep an external
appeal contact for them. Conduct reports and evidence are retained for staff review
rather than automatically deleted by a personal-data request. Back up the entire
`data/` directory or use encrypted full-data backups to retain evidence files;
configuration-only backups do not contain case evidence or member records.

## Support and social tools

| Command | What it does |
| --- | --- |
| `/support tags labels` | Sets up to eight comma-separated labels on the current ticket. Omit labels to clear them. |
| `/support timeline ticket_id` | Downloads a private administrative activity timeline as the ticket owner or support staff; omit the ID inside an open ticket. Includes opening, claims, releases, priorities, categories, labels and closure. Stores the latest 200 events and survives ticket closure. Old tickets begin recording events after this update. |
| `/support availability status` | Lets current support staff share available/busy/away status, or hide themselves. This is a self-reported status, not presence detection. |
| `/support staff` | Shows the statuses of current support staff who chose to share them. |
| `/social lfg game availability slots description` | Publishes a board with persistent Join, Leave and Close buttons. Hosts choose 2–10 total slots; Vivi prevents overfilling. One active board per host, fifty per server. |
| `/social lfg_find game` | Searches active boards by game name and returns links. Matchmaking is a searchable board, not automatic skill-based pairing. |
| `/social timezone zone public` | Saves an IANA timezone such as `Europe/London`. `public` defaults to false. Set it false to leave the directory, even if the directory feature has since been disabled. |
| `/social timezones search` | Shows current local times for matching current members who opted in. Never collects exact locations. |
| `/social remind when text` | Schedules a private DM reminder with `10m`, `2h`, `3d` or an ISO date/time. A time without an offset uses your selected timezone, then the server timezone. Ambiguous/nonexistent daylight-saving times require an explicit offset. |
| `/social reminders` | Privately lists your pending/failed reminders. Maximum ten per member per server. |
| `/social reminder_cancel reminder_id` | Cancels your own reminder. |
| `/social favorite command remove` | Adds/removes an existing slash command name, for example `social reminders`, from your private list (maximum twenty). |
| `/social favorites` | Shows your favorite command names. Normal command permissions still apply. |

Reminders persist through restarts and are checked every fifteen seconds while
Vivi is online. They allow one minute to one year ahead. Enable server DMs; delivery
retries up to three times and then shows as failed. No public-channel fallback is
used. Disabling reminders pauses delivery; overdue reminders resume after re-enabling.
Vivi must still share the originating server with the member. A crash between DM
send and database acknowledgement can cause a duplicate delivery.

A personal-data deletion request removes reminders, favorites, dashboard preferences,
shared timezone preferences, availability and active database LFG participation.
Previously published boards/messages, transcripts, moderation records and backups
still need the staff retention review requested by the existing privacy workflow.

## Eight new games

Enable `games`, then use:

| Command | Rules and controls |
| --- | --- |
| `/games connect_four opponent` | Two players drop pieces into seven columns; first to connect four wins. Column buttons or `/games move notation:4`. |
| `/games checkers opponent` | American 8×8 checkers: mandatory captures, forward captures for men, kings move/capture both directions, full multi-jump required. Use `b6-d4-f2`. Promotion ends the turn. |
| `/games chess opponent` | Legal chess moves, checks, mate, castling, en passant, promotion and automatic draw outcomes. Use SAN (`Nf3`, `O-O`) or UCI (`e2e4`, `e7e8q`). `draw` claims a currently valid threefold/50-move draw. |
| `/games hangman` | Guess a letter or full word; six wrong guesses end the game. |
| `/games anagram rounds` | Hosts a 2–10 player lobby. Join, then the host starts 2–10 rounds of thirty seconds each. Submit guesses privately; correct answers score remaining seconds. Each member scores once per round. Answers come from Vivi’s curated word bank. |
| `/games sudoku difficulty` | Generates a unique-solution puzzle with easy/medium/hard clue density and a live filled-cell count. Use `A1=5` or `A1=0` to clear an editable cell. Clues are immutable; row/column/box conflicts are rejected. Difficulty is based on clues, not a human solving-technique rating. |
| `/games memory` | A 4×4 pair-matching board with clickable cards. Mismatches remain visible for two seconds; matched cards stay revealed. |
| `/games battleship opponent` | Quick 6×6 variant: automatically places ships of lengths 3, 2, 2. Fire with `A1`–`F6`. The public message shows only the latest shot and turn; your fleet and shot grid are private. |

Multiplayer opponents must accept the challenge within two minutes. Use the
**Enter move** button or `/games move`, `/games board` for a private board, and
`/games resign` to end your game. New games allow one active session per member per
server and fifty sessions per server. They time out after thirty minutes of
inactivity. Sessions and Sudoku progress live in memory and end when Vivi restarts;
reminders, LFG boards and member preferences are persistent. The new games award
no currency. Existing trivia/word/tic-tac-toe commands remain available separately.

Chess uses the pinned upstream `chess` package (GPL-3.0-or-later); its copyright and
license are included with the installed dependency. See its
[upstream project](https://github.com/niklasf/python-chess) for distribution terms.

## Dashboard studio

Enable the existing local dashboard and sign in with Discord as a current server
administrator. The new **Dashboard studio** section contains:

- **Personal panel order:** drag section summaries or use their Move up/down
  buttons, then select **Save my panel order**. Order belongs to the signed-in
  administrator in this server; other administrators keep their own layouts.
- **Welcome-card editor:** add/reorder supported avatar/header/server/message/brand/
  custom-text elements. Drag them in the canvas or edit labeled X/Y/size/color
  controls with a keyboard. Uses the joining member’s avatar; arbitrary image URLs
  and HTML are not supported. **Preview PNG** renders the same layout as real
  welcomes. **Save welcome layout** applies it; **Restore default layout** resets it.
- **Announcement builder:** add/reorder title, text, named field and divider blocks
  with drag/drop or Up/Down buttons. The title belongs first; fields render in
  block order as named text inside one embed. Drafts are private to the signed-in
  administrator. Preview does not post. Choose a channel, tick the explicit
  publication confirmation and select **Publish announcement** to send it.
  Mentions never ping. Current admin status and bot channel permissions are checked.
- **Accessibility checks:** static audit of the generated settings/editor HTML for
  heading order, labels, duplicate IDs, image alt attributes, main landmark and
  live status region. Findings identify places to investigate; this does not
  certify WCAG compliance or replace keyboard/real screen-reader testing. Editor
  fields created in the browser use wrapping labels and keyboard reorder controls.
- **Release information:** checks published releases without downloading or
  installing updates. Also available through `/admin updates`.

JavaScript is served locally with a restrictive Content Security Policy. Every
write uses the existing CSRF protection and a fresh Discord administrator check.
Detailed settings, drafts and editor data are server-scoped. Layout and announcement
inputs are bounded and validated again on the server.

## Steam news and releases

Use `/notify add provider:steam source:730 channel:#game-news` with a numeric
Steam application ID (730 is an example). The existing subscription list, removal,
dashboard metadata test, five-minute polling/backoff and deduplication apply.
The first successful poll establishes a baseline; it does not flood old news.
Steam news does not require an API key and this integration does not expose Steam
category/tag metadata for filters.

The release checker defaults to `Zyvelia/test`. The host can set
`UPDATE_REPOSITORY=owner/repository` and, for a private repository or API limits,
a dedicated `UPDATE_GITHUB_TOKEN`. Discord users cannot choose arbitrary API URLs
or change that token. Results cache for thirty minutes. No published release (or an
inaccessible private release) is reported clearly. Only `vMAJOR.MINOR.PATCH` stable
tags are compared automatically; other tags request manual comparison. A Git push
alone does not create a GitHub release.

## Verification

The automated tests use local/mocked Discord interactions and provider responses;
they do not log the bot in or publish messages to a real server. Python tests cover
permissions, server isolation, atomic warning auditing, evidence integrity, reminder
retry behavior, game moves and dashboard validation. The development-only DOM tests
exercise the production editor HTML and JavaScript:

```sh
python -m unittest discover -s tests -v
npm ci --prefix tests/ui
npm --prefix tests/ui test
```

The DOM test uses `python` by default; set `VIVI_PYTHON` to your virtual-environment
Python when needed. Node/jsdom is required only for development tests, not running
Vivi. CI runs Python tests on Windows/Linux and editor DOM tests on Linux. Test
OAuth login, game challenges, role permissions, DMs and provider reachability with
your own configuration before enabling these in a live community.
