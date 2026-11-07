# Vivi: teams, tournaments, profiles and more games

Update the repository files and restart Vivi. Windows, Linux and Docker use the
same implementation. Docker users should rebuild their image. No additional
Python dependencies are required for this batch. The bundled serif/monospace fonts
work without installing system fonts; their license is in
`vivi/assets/fonts/LICENSE-DejaVu.txt`.

## Feature switches

Enable features through the dashboard or `/admin feature name:… enabled:true`:

| Switch | What it enables |
| --- | --- |
| `invite_tracking` | Private, best-effort invite attribution |
| `competitions` | Persistent single/double-elimination competitions |
| `teams` | Team rosters, consent-based invitations and recruitment |
| `library` | Searchable game builds and strategy guides |
| `profiles` | Profile customization, uploads and cosmetic loadouts |
| `games` | The five additional games, alongside existing games |

The five new switches default to off. Existing game settings continue to apply.
The final “Privacy, reliability and optional AI” heading in the selection had no
individual features selected; it does not enable or add the entire earlier list.
AI remains optional and off unless explicitly enabled by an administrator.

## Invite-source estimates

Vivi needs Discord **Manage Server** permission to read invite counters. Enable
`invite_tracking`, then run `/invites refresh` as Manage Server staff to establish
a baseline. Vivi also establishes baselines when connecting to Discord.

`/invites source` privately shows your own estimate. Staff with Manage Server can
supply a `member` to inspect another member’s source. Exactly one observed invite
increasing by exactly one is labeled **estimated**, with its code and inviter ID.
It is never presented as verified proof.

Missing baselines, permission failures, disappearing/one-use invites, simultaneous
joins, newly discovered used invites and ambiguous counters produce **unknown**.
Vanity/discovery joins are not inferred from normal invite counters. Invite create/
delete events and tracking changes invalidate the baseline; configuration restores
also prevent reuse of an older baseline. Tracking is not retroactive. The latest
source estimate for a member replaces their previous estimate when they rejoin.
Invite codes are not posted publicly by this feature.

## Tournament brackets

- `/competition create name format capacity` creates registration for 2–32 players.
  Choose `single` or `double`; the creator is the host.
- `/competition join competition_id` registers the caller. `/competition leave`
  withdraws them while registration is open.
- `/competition start competition_id shuffle` closes registration and seeds players
  by joining order, or shuffles them when explicitly selected.
- `/competition show competition_id` downloads the seeds, rounds, pending pairings
  and recorded outcomes. IDs in the bracket identify Discord members. Hosts/Manage
  Server staff may select `audit:true` to include private reporting actors/reasons.
- `/competition result competition_id match_id winner reason` records a result.
  Only the host or Manage Server staff may report; the winner must be a player in
  that pending match. A reason records score verification or a forfeit.
- `/competition list` finds open competitions. `/competition cancel … reason`
  cancels one while preserving its history.

Single elimination removes a player after one loss. Double elimination pairs
players in seeded undefeated/one-loss groups, gives automatic byes for odd counts,
and eliminates after two losses. The grand final resets if the previously
undefeated finalist receives their first loss. These loss-bucket rounds support
non-power-of-two entrant counts; they do not implement every tournament organizer’s
preferred conventional upper/lower bracket placement. A round advances after all
its matches are reported. Brackets, results and reporting reasons survive restarts.
Vivi tracks results; it does not automatically play or verify external game matches.

Limits: twenty open competitions per server, two hosted open competitions per
member. Reported results cannot be silently overwritten; cancel and recreate a
competition if its bracket needs a structural correction.

## Teams and recruitment

`/teams create name game` makes you the captain. `/teams invite team_id member
position role` publishes a personal invitation for a starter/substitute slot and a
game-role label. **Only that member can accept.** Invitations expire after 24 hours
and become invalid if captaincy changes. Roster membership does not grant Discord
roles or permissions.

Use `/teams roster`, `/teams list game`, `/teams position`, `/teams remove` and
`/teams captain` to manage existing teams. Only the current captain or Manage Server
staff can change another member’s roster position or transfer captaincy. A new
captain must already be on the roster. Members may `/teams leave`; captains must
transfer management or `/teams disband confirm:true` first.

`/teams recruit team_id requirements openings required_role` publishes a recruitment
post with an Apply button. The optional Discord role is checked when applying.
Posts expire after seven days; `/teams recruitment_close` stops applications sooner.
Applications do not automatically add anyone to the team.

Captains use `/teams applications` to privately download applications, then
`/teams application_decide` with a reason. Acceptance records a decision; joining
still requires a separate invitation the applicant accepts. Members can privately
check `/teams my_applications`.

Limits: fifty teams per server, two captaincies per member, twenty roster members,
twenty outstanding invitations per team, three active recruitment posts per team,
and fifty pending applications per team. Supported invitation/application buttons
are restored after a bot restart.

## Build-sharing and strategy collections

`/library publish kind title game content` publishes a `build` or `guide` to the
server library. Builds can describe character skills, equipment and loadouts;
guides can describe strategies and link to supporting resources. Entries are public
to members of their originating server, not other servers.

Use `/library search game query kind` and `/library read entry_id` to find/read them.
Authors may `/library edit` their text; the last five previous text versions are
retained. `/library remove entry_id reason` lets authors delete their own entries
or Manage Messages staff remove inappropriate ones with a recorded moderation case.
Configured blocked-word/link filters apply to publication and edits. Links are
stored as text, not fetched or executed.

Limits: twenty entries per author, five hundred per server, 1,800 content characters
per entry. Library IDs can be used in their author’s profile showcase slots.

## Five additional games

| Command | Rules and controls |
| --- | --- |
| `/games reversi opponent` | Standard 8×8 flipping rules. Use a coordinate such as `D6`; legal cells show `+`. Turns with no legal moves pass automatically. The higher final piece count wins. The opponent must accept first. |
| `/games minesweeper difficulty` | A 6×6 board with 6/8/12 mines for easy/medium/hard. Reveal `A1`; use `flag A1` or `unflag A1`. The first reveal and its adjacent cells are safe. Reveal every non-mine cell to win. |
| `/games word_search` | An eight-word, 10×10 puzzle. Words can run in eight directions. Submit endpoints such as `A10-F5`, in either direction. Found-word progress is shown. |
| `/games crossword` | A curated three-by-three mini crossword with four intersecting clues. Enter `1A=CAT` or another clue/answer pair. Several small packs are included. Correct answers remain filled and are saved. |
| `/games spelling` | Eight clue-based spelling levels of increasing difficulty, from common words to harder spellings. Enter the word; three mistakes on a level end the challenge. This is a text/clue activity, not audio dictation. |

Use the existing Enter move button or `/games move`, `/games board` and
`/games resign`. Minesweeper, word-search, crossword and spelling save progress to
the database after valid moves. Starting that same puzzle again resumes it;
`/games resume kind` explicitly resumes after a restart. `/games puzzle_reset kind`
discards saved progress after you resign from any active game. Completed puzzles
are cleared so the next start begins another challenge.

Reversi sessions remain in memory and end at restart, like the earlier multiplayer
games. Existing session limits and timeouts apply. The new games award no currency.
Old game buttons cannot control a replacement session.

## Profile customization and starter cosmetics

`/profile` → **Catalog** lists the free starter options:

| Type | Included choices |
| --- | --- |
| Backgrounds | `velvet_ruins`, `rose_dusk`, `moon_lake`, `violet_garden`, `cloud_dream`, `midnight_geometry` |
| Gradient presets | `violet_rose`, `moonlight`, `golden`, `mint` |
| Custom gradients | Two hex colors, for example `#bb99ee,#ffb6cc` |
| Fonts | `rounded`, `serif`, `mono` |
| Layouts | `compact`, `detailed`, `gallery` |
| Stickers | `star`, `moon`, `heart`, `flower`, `crown`, `sparkle` |

Use `/profile` → **Customize** (background gradient font layout status) to change only the
fields you supply. `clear_status:true` clears your message. Statuses are limited to
120 characters and checked against configured word/link filters. Manage Messages
staff can `/profile` → **Moderate** (member reason) to clear a status, including copies in
saved loadouts, with a moderation case.

`/profile` → **Preview** privately previews your current appearance or temporary
background/gradient/font/layout changes **without saving**. `/profile` → **View** (member)
and the existing `/economy profile` show the same privacy-aware PNG card.
Existing equipped shop titles are still displayed when allowed by field visibility.

`/profile` → **Sticker** (item x y) adds a sticker at an exact position on the 900×360 card.
Maximum six; `remove_slot` removes one by its 1-based position. Showcase slots are
set with `/profile` → **Showcase** (slot kind value): choose an earned `achievement`, the
ID of your own published library `creation`, or `clear`. Maximum three slots.
Layouts may show fewer text lines when space is limited.

`/profile` → **Visibility** (field public) controls XP, coins, achievements, showcases,
status, avatar, uploaded banner or equipped title individually. `field:all` controls
the whole profile. Hidden XP also removes you from the XP leaderboard. Owners can
still preview their own private cards; hidden fields remain hidden in the preview.
Visibility controls affect future bot views, not copies/images already shared.

`/profile` → **Loadout** (action name) saves, applies, lists or deletes up to five cosmetic
combinations. Loadouts include supported card appearance and the equipped shop
cosmetic, but do not overwrite privacy settings. An applied shop item must still be
owned; a revoked uploaded banner cannot be restored through an old loadout.

### Uploaded banners

1. `/profile` → **Banner Submit** (attachment) accepts static PNG/JPEG/WebP images up to
   4 MiB and eight million pixels. Vivi normalizes them to 900×360 PNG and strips
   metadata. Maximum five submissions per member.
2. `/profile` → **Banners** lists your submissions. Manage Messages staff can use
   `review_queue:true` to list the review queue.
3. Another staff member uses `/profile` → **Banner Review** (banner_id action:preview)
   to inspect the image privately, then `approve` or `reject` with a reason.
   Staff cannot approve their own uploads. Existing approvals can be revoked.
4. After approval, choose `/profile` → **Customize** (background:upload:BANNER_ID).
   Only the owner may use that upload. `/profile` → **Banner Delete** removes your file.

Missing, deleted or revoked backgrounds fall back to a starter background. Uploaded
banner visibility can be disabled separately. Local banner files are included in
full-data backups, not configuration-only backups.

## Dashboard improvements

- **Command palette:** choose Search settings or press Ctrl+K / Command+K. Search
  section names, setting keys and action labels. Selecting a result opens/focuses
  its existing control; it does not execute or submit that action.
- **Unsaved-change warning:** changing a form, editor document or panel order can
  trigger the browser’s native navigation warning. Submitting that form proceeds
  normally; changes in other forms still count as unsaved. Empty file inputs do not
  create false warnings. Browser/mobile lifecycle behavior can limit these warnings.
- **Mobile navigation:** a Jump to section menu, larger touch controls, responsive
  form fields and horizontally scrolling tables support narrow screens. This is
  responsive navigation; it does not expose the existing local-only dashboard to
  another device or change the OAuth/network configuration.

All existing OAuth administrator checks, CSRF checks and script restrictions remain.
The palette indexes controls already rendered for the authenticated administrator.

## Data handling and verification

The existing personal-data deletion flow now removes your invite-source record,
saved puzzles, uploaded banner files, profile settings/loadouts, team applications,
invites addressed to you and your own library entries. It removes your roster
membership and transfers an occupied team to the next member, or removes an empty
team. Competition/audit history, references in other members’ invite records,
previous public messages and backup copies remain subject to the existing staff
retention review.

Automated tests use mocked Discord interactions and local-only HTTP. They cover
ambiguous invite counters, bracket sizes and final resets, roster consent and role
requirements, library ownership, puzzle rules/save-resume, image validation, banner
approval/revocation, field privacy and loadouts. DOM tests cover the palette, mobile
section links, editing, keyboard ordering and dirty-form warnings. Windows/Linux CI
runs the same Python tests. Live invite counters, Discord uploads and your actual
OAuth session still need testing with your own configuration.
