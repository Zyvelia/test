# Community, ticket, profile and settings menus

Vivi now uses four private entry points:

| Command | Menu actions |
| --- | --- |
| `/community` | Rules panels, role menus/previews, private reports and appeals, polls, giveaways, suggestions, birthdays, spotlight consent and social tools |
| `/ticket` | Open a ticket, view status, request closure, staff claiming/release, priority/category, labels, timeline and staff availability |
| `/profile` | View/preview cards, appearance, visibility, stickers, showcases, loadouts, banner upload/review/deletion and staff moderation |
| `/settings` | Administrator-only feature switches, detailed settings, server setup, verification and configuration backup/restore |

The old `/community ...`, `/ticket ...` and `/profile ...` slash groups are replaced,
reducing the registered leaf command count from 187 to 158. Their existing handlers
remain behind the menus. Other direct command groups remain available.
In the older feature guides, **`/profile` → Customize** means open the menu and
choose Customize; words in parentheses describe the form fields.

## Using an action

1. Run the menu command in the server/channel where the action should take place.
2. Choose an action from the dropdown; use Previous/Next for longer lists.
3. Choose **Open action**. Native member, role and channel pickers, choice dropdowns,
   text fields and file-upload controls collect the original inputs.
4. Longer forms have multiple steps. Choose **Continue form** after each step.
5. Review your inputs and choose **Confirm action**, or Cancel. No action runs while
   filling the form. Commands that publish messages are marked as public actions.

Menu messages and results are private; explicitly published polls, suggestions,
role panels and similar actions still appear in their destination channels.
The original permission checks, feature switches, cooldowns, data scoping,
moderation checks and input limits still apply. Permissions are checked again at
execution. Menus belong to their requesting member and server, and expire after
15 minutes of inactivity. Reopen the relevant command to get fresh controls.

## Tickets

Open `/ticket` anywhere in the server to create a ticket. For status, claiming,
labels, priority, category and closing, open the menu **inside that ticket channel**.
Staff controls require the configured support role or the original channel-management
permissions. Ticket closure retains its separate transcript-and-delete confirmation.
Existing persistent ticket panel buttons still work.

## Profiles

The menu keeps all existing appearance and visibility settings. Banner Submit uses
a native upload field and preserves file limits, image validation and staff review.
Banner Review still prevents members from approving their own submissions.
Profile privacy stays unchanged when applying saved cosmetic loadouts.

## Server settings

Only current Administrators can open and use `/settings`. Feature changes use
explicit **Enable / Disable** buttons. Detailed settings use validated text or
native channel/role selectors; choose **Edit value** and submit to save.
An empty optional channel/role picker clears that setting. AI-channel lists over
25 entries use comma-separated IDs to preserve the existing larger-list support.

Settings use the same database, validation and configuration history as Discord
commands and the dashboard. Open editors reject stale saves after a setting changes
elsewhere. Server setup, backup, restore and other administrative actions are under
**Setup & backups**. Restores also require the original `confirm` field to be true.
If the website is enabled, a dashboard link appears; loopback links work on the
computer hosting Vivi.

## Migration

Update and restart Vivi to synchronize the new command layout with Discord. Existing
records, profiles, ticket channels and configuration are retained. Registered
shortcuts targeting Ticket Status still resolve its internal handler. Old favorites
for retired subcommands display the matching menu entry point in `/help` and
`/social favorites`.

Menu forms use the native modal controls supported by the pinned discord.py 2.7.1.
Automated checks validate components, uploads, multi-step review, confirmations,
permission revocation, settings sync and backward-compatible aliases. A configured
running bot is needed for live Discord UI verification.
