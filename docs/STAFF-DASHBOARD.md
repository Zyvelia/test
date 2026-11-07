# Vivi staff dashboard

Open **Staff workspace** in the dashboard sidebar, or the link below the server home card. The server selector lists servers where Vivi can verify your staff access. Each staff page checks current membership and roles with Discord before reading records. Logged-out visitors must sign in; ordinary members receive no staff records.

## Access

| Page | Who can access it |
| --- | --- |
| Staff home | Server owner/Administrator, Moderate Members, Manage Channels, or the configured support staff role |
| Cases; reports and appeals | Server owner/Administrator or Moderate Members |
| Tickets | Server owner/Administrator, Manage Channels, or the configured support staff role |
| Feature configuration and shared embed library | Server owner/Administrator, using the existing dashboard authorization |

The staff selector uses your OAuth server list for discovery, then verifies roles through Vivi. Discovering a server does not grant administrator access. Staff pages are read-only and do not bypass the existing Discord checks for moderation, appeal decisions or ticket actions. Configuration and record queries are scoped to the selected server.

## Server home card

The module overview and staff home show the available Discord member count, Vivi’s actual ready/online status and the number of enabled modules. Module switches retain saved settings when switched off. Global-ban participation still requires fresh owner consent after opting out. The enabled count updates when you toggle modules on the module overview.

## Cases

Search by member’s numeric Discord ID, exact action, and words in the reason. Filters can be combined. Open a case to see its full reason, member ID, staff ID and recorded UTC time. Results are paginated and do not include other servers’ cases.

## Reports and appeals

The queue defaults to pending reports and appeals, with type and status filters and pagination. Expand a request to read its author, target/member or case, message, and any recorded staff response. Use `/mod review` in Discord to record a decision; accepting a request does not automatically ban, unban or remove a timeout. Privacy requests and independent staff-conduct reviews retain their separate existing workflows.

## Tickets

The ticket list shows channel/member IDs, Open/Closing/Closed/Channel missing status, priority, claimant and age, with status filtering and pagination. Age comes from the ticket event timeline, or Discord’s channel creation time for older open tickets. It shows **Not recorded** when no reliable time exists. Closed records appear while retained ticket-rating metadata exists; the dashboard does not invent missing historical metadata. Closed-ticket age is its recorded duration.

## Welcome, goodbye and saved embeds

The welcome/goodbye editor now has a live sample preview while typing or choosing an embed, including `{member}`, `{username}`, `{server}` and `{member_count}` placeholders. This preview does not save or send anything. Discord renders final markdown, inline fields and remote images when delivering the message.

Saved embeds use the existing library shared with `/embed`. Event-message settings keep a copy of a selected template; edit the template, select it again and save to apply a new version. Switching a module off does not delete its template or text settings.

The welcome-card designer includes a **Vivi velvet neon** layout with pink accents, an avatar area and editable text. Choose that style or reset to the new default. Existing saved layouts keep their values and default to Plain unless you change them. The browser canvas and generated PNG both include the selected layout style.

## Windows tray artwork

The tray now uses `assets/vivi/tray/vivi.png`. `vivi.ico` in the same folder contains 16, 20, 24, 32, 40, 48, 64, 128 and 256 pixel variants for Windows shortcuts and other local uses. `vivi-64.png` is also included. Reopen the tray after updating to load its new image. If artwork is missing, a built-in monogram keeps the tray usable. The artwork can be regenerated with `python scripts/generate_tray_icon.py`.

Automated tests cover access checks, role changes, server isolation, filtering, pagination and icon assets. Browser tests use synthetic accounts and records; native Windows icon display still needs checking on Windows.
