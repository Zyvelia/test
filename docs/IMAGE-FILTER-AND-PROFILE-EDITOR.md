# Known scam images, live profile editing and settings search

## Known scam-image deletion

Administrators can upload reference images through **`/settings` → Setup & backups
→ Scam Image Add**. Choose Open action, upload the image, supply a short label,
then review and confirm. Alternatively choose Scam Images under Features and use
**Manage scam-image references**. The bot returns a reference ID and the image's
SHA-256 code. Use Scam Image List and Scam Image Remove to manage references.

Enable **Scam Images** under `/settings` → Features. It is independent of the
text AutoMod switch and disabled by default. Supported member attachments matching
saved references are deleted before XP or other message rewards are processed.
Manage Messages staff and bot messages follow the existing moderation exemptions.
The bot needs access to the channel, message-content intent and Manage Messages.
Missing deletion permissions are reported as failures rather than successful deletions.

The default `scam_image_distance=0` uses exact file SHA-256 or normalized pixel
hashes. Pixel matching can detect an unchanged image saved with different metadata
or lossless encoding. Image hashes are identifiers, not executable image code.

Values **1–4** opt into perceptual similarity matching for some resized/recompressed
copies, with a matching aspect ratio and adequate contrast. This is experimental:
related-looking images can collide, and modified scam images can evade it. Keep
exact matching unless you have checked your references. Remove a reference or
disable the feature to stop its use. This feature recognizes supplied examples;
it does not identify every scam, read QR codes, OCR text or inspect linked websites.

Limits: 100 references per server; static PNG/JPEG/WebP up to 4 MiB and eight million
pixels. Animated images, external URLs, embeds and unsupported/oversized attachments
are not inspected. Up to ten attachments per message are considered. Posted
attachments and attachment edits delivered through Discord's cached edit events
are checked; old message history is not retrospectively scanned.

Only hashes, dimensions, labels, staff IDs and timestamps are stored for references;
original reference files and candidate image bytes are not retained by Vivi. Discord
handles its own uploaded attachments under its policies. References are server-scoped
and persist across restarts. They are included in full-data backups, not the
configuration-only export. Matching deletions create rate-limited moderation cases
containing reference IDs and message/channel IDs, without reposting the image.

## Live profile editor

Open `/profile`, then choose **Live profile editor**. It displays a private generated
card alongside controls for backgrounds (including your approved uploads), gradient
presets/custom colors, fonts, layouts, stickers and status text. Each accepted change
redraws the preview. The existing field-visibility settings remain respected.

Changes remain a draft until **Save changes**. **Revert draft** reloads the latest
saved appearance; closing or timing out discards unsaved edits. Another menu changing
your saved style causes stale saves to be rejected. Status filters, approved-banner
checks, six-sticker limits and other original style rules still apply. The Profiles
feature must be enabled. Precise sticker placement, loadouts and banner submission
remain available as separate actions within `/profile`.

## Global dashboard settings search

After selecting a server, use the visible **Search all settings** field. Search for
`welcome`, `raid`, `birthday`, `scam`, a setting name or an action. Results cover all
rendered server modules, including closed panels and fields hidden by a module filter.
Select a result to open the relevant panel and focus its control. Search never saves
or submits settings. Nothing from other servers is fetched.

Keyboard: Arrow Down focuses results, Enter opens the first result, and Escape clears
the inline search. Ctrl/Cmd+K continues to open the command palette with the same
improved index. Results include matching counts and keyboard-accessible buttons.
