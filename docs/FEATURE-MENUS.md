# Community, ticket, profile and administration menus

Vivi uses these private menu entry points:

| Command | Menu actions |
| --- | --- |
| `/community` | Rules panels, role menus/previews, private reports and appeals, polls, giveaways, suggestions, birthdays, spotlight consent and social tools |
| `/ticket` | Open a ticket, view status, request closure, staff claiming/release, priority/category, labels, timeline and staff availability |
| `/profile` | View/preview cards, appearance, visibility, stickers, showcases, loadouts, banner upload/review/deletion and staff moderation |
| `/admin` | Administrator-only setup, role/ticket panels, verification, backup/restore, history, rollback, health, branding, notification subscriptions/filters, channel XP, custom alias creation/removal and update checks; Features and Detailed settings buttons |
| `/settings` | Shortcut opening feature switches and detailed settings first; the same administrative tools remain available |

The old `/community ...`, `/ticket ...`, `/profile ...` and `/admin ...` slash groups are replaced. Role-button and ticket-panel creation, the `/notify ...` group, alias creation/removal and per-channel XP configuration are also inside `/admin`, reducing the current registered leaf command count from 160 to 138. Existing handlers remain behind the menus. Other direct command groups remain available.
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

## Fast administrative and moderation commands

`/setup` stays available for initial server setup, and is also in the admin menu.
`/embed` stays available for writing and posting saved messages. `/globalban` stays
available to the configured operator account only; its menu discovery and runtime
checks are unchanged.

`/warn`, `/warnings`, `/timeout`, `/untimeout`, `/kick`, `/ban` and `/purge` remain
direct shortcuts. The `/mod` commands, including tempban, unban, lockdown, unlock,
slowmode and history, also remain available without opening `/admin`.

Open `/admin`, choose an action and press **Open action** for maintenance or panel
creation. Choose **Features** or **Detailed settings** for the corresponding settings.
The original handler permissions are retained; the admin menu is private, belongs
to its opening account/server and expires after 15 minutes. Changing permissions
while a form is open prevents it from being submitted. Old favorites referencing
`admin ...`, `notify ...`, `economy channel_xp`, `role_button` or `ticket_panel` resolve to `/admin`.

Existing Discord installations receive the changed command registry on the next
normal bot startup/sync. Discord may take time to refresh its command picker.
