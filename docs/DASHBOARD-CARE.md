# Dashboard change log, tests, drafts and privacy

Update Vivi, restart it, sign in to the dashboard, and select your server. The sidebar contains **Change log**, **Setup tests**, and **Privacy & retention**. These pages require current Discord administrator/owner access. Membership is checked with Discord, including for changes and restore actions. Moderation and support pages continue to use their separate staff permissions.

## Change log

Search the latest configuration revisions by setting, staff ID, action, or value. Select **Compare values** to see previous/new values, staff identity (name when cached, otherwise Discord ID), and UTC time. Dashboard and Discord settings use the same recorded history. Full revisions link to the existing confirmed configuration-restore workflow.

History contains configuration values, including message text; avoid putting secrets in settings or templates. History does not record every game action, message, or saved-library edit. At most 100 configuration revisions are retained per server, optionally fewer under an age limit. Older revisions cannot be reconstructed.

## Test buttons

- **Welcome → Send sample welcome:** uses the current editor draft and your Discord profile. Confirm the destination before sending. Settings and automatic Welcome availability do not change. The existing Send to Discord action remains available. No live test is sent automatically on page load.
- **Check notification destinations:** checks each configured subscription's current text channel and Vivi's View Channel, Send Messages and Embed Links permissions. It does not post notifications or call external providers. Existing subscription provider tests remain separate.
- **Test role permissions:** checks Manage Roles, configured automatic/rules/selectable roles, protected staff/default roles, managed roles, privileged permissions and Vivi's role hierarchy. It does not assign or remove roles. Actual role assignment still rechecks permissions and feature policy.

The related notification and role configuration pages include their test buttons too. Missing channels, roles and permissions produce actionable results rather than an expired-login message.

## Recover unfinished drafts

Welcome, goodbye and embed editors save unfinished changes in this browser's local storage, scoped to your Discord account, server and editor/template. Returning offers **Restore draft** or **Discard draft**, without changing saved configuration. Embed fields, their order and inline choices recover too. A successful Save clears that editor's recovered draft. Previewing and sending do not save configuration or clear drafts.

Drafts expire after seven days and expired entries are removed when an editor opens. Drafts are local to the browser profile, not synced between devices, encrypted backups, or a guarantee against storage clearing. OAuth tokens and CSRF values are excluded. Avoid shared browser profiles for private content. Discard removes the stored draft while leaving the current editor text available; further editing starts a new draft. If storage is unavailable, the editor explains that recovery is unavailable.

## Privacy and retention

Members use **`/tools delete_data`** and its confirmation to delete supported personal data and create a staff review request for retained records. The existing flow removes profile/birthday/AI memory, attributable votes and supported personal records/uploads, and preserves moderation records pending review. It does not reverse bans or remove all published messages, transcripts, exports or backups.

**Privacy & retention** contains the private deletion-review queue. Reviewers record a status and explanation of what was removed or retained and why. Completing a review records staff identity/time; it does not claim to automatically erase remaining records. Contact the requester privately as appropriate. Retained backup copies need separate review and must not unnecessarily reintroduce deleted information on restore.

Optional retention controls apply only to:

| Setting | Removed after the limit |
| --- | --- |
| Configuration change log | Old configuration revisions, still subject to the existing 100-revision cap |
| Completed/declined privacy requests | Requests whose resolution timestamp is older than the limit; pending/in-review requests remain |
| Closed-ticket activity events | Old timeline events for channels with no active ticket; active tickets remain |

Use **0** to disable age-based cleanup, or **7–3,650 days**. Confirm applying limits to existing and future records. Cleanup runs about every ten minutes while the bot is online. These controls do not delete cases, moderation evidence, ticket transcripts, Discord messages, exports or backup files. All cleanup is server-scoped.

The public [privacy policy](../vivi/site/policies.py) explains browser drafts, staff access, these retention limits and existing deletion limitations. Contact: **Vivi-Roseveil@proton.me**, operator **ZyVelia**. Keep tokens and private requests out of public channels.

## Validation

Python tests cover history comparisons and escaping, server isolation, fresh membership/CSRF checks, read-only diagnostics, retention validation/cleanup, and privacy review transitions. Browser checks cover closed-tab recovery, embed fields, discard/save behavior, expiry, account separation, mobile pages and ordinary-member denial. Tests use synthetic Discord fixtures; no real messages are sent.

```bash
.venv/bin/python -m unittest discover -s tests
VIVI_PYTHON="$PWD/.venv/bin/python" VIVI_BROWSER_PATH=/usr/bin/chromium node tests/ui/care.test.cjs
```
