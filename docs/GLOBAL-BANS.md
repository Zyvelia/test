# Operator-bound global bans

The configured operator account is **Discord user ID `973054575076581456`**.
Only that numeric account can use `/globalban`; matching names, server-owner roles,
Administrator permission and other staff roles do not grant access. Runtime checks
also protect modal submissions, confirmations, removal, results and retry controls.

`GLOBAL_BAN_OPERATOR_ID` is a host-side setting with that ID as the default. It is
not a token and cannot be changed through Discord or the website. Operators hosting
an independent copy should set their own account ID before inviting servers into
its network. Changing the operator or bot identity invalidates existing server
consent until owners opt in again.

## Server participation

Enforcement is **off by default**. A server owner must explicitly opt in through:

- Website **Manage features → Global Bans**: review the operator ID, accept the owner
  consent checkbox and enable the module.
- `/settings` → Features → Global Bans → Enable: review and confirm the owner opt-in.
- `/admin feature name:global_bans enabled:true`: opens the same owner confirmation.

Opting in may enforce **existing and future** active global entries. Vivi must have
Ban Members. Normal Administrators can disable enforcement in an emergency, but
only the owner can enable it. Disabling clears consent and stops future network
bans/unbans; existing Discord bans remain for local staff to review.

Consent is bound to the server owner, configured operator and bot account. Merely
restoring `feature:global_bans=true` cannot create consent. Configuration restore
clears this feature's consent and requires a new owner opt-in. Full-data recovery
restores the saved records, which are still checked against current identities.

## Adding an entry

1. Use `/globalban` from the configured account.
2. Choose **Add global ban** and enter a Discord user ID, a specific reason and an
   evidence reference such as a case ID or message link. Evidence links are stored,
   not fetched or automatically verified.
3. Review the resolved account, reason, evidence and current network size.
4. Confirm. The entry is saved and per-server jobs are queued for currently opted-in
   servers. Network membership may change before confirmation; later owner opt-ins
   can also enforce the entry.
5. Use **Results** to inspect successful, pending, skipped, preexisting and failed jobs.

Vivi bans the account by ID even if it is not currently a member. Native Discord
bans prevent that account from rejoining until unbanned. New joins are checked before
welcome messages or newcomer roles. Native role hierarchy, protected server owners
and missing bot permissions can prevent enforcement; results report those failures.
This does not identify alternate accounts or guarantee instant enforcement everywhere.
Vivi and the configured operator are protected against adding their own IDs.

No message history is deleted by these bans. Per-server cases identify the global
entry and reason. Evidence references and the complete global list remain private
to the configured operator rather than being published across servers.

## Removing an entry

Choose **Remove entry**, provide a reason, then choose:

- **Remove from blocklist only** — stops network enforcement, leaving existing bans.
- **Also undo verifiable Vivi-issued bans** — queues reviews in still-participating
  servers. Vivi requires a matching local ledger, matching ban-reason marker and
  a matching latest ban audit entry identifying Vivi as issuer before unbanning.

Verified undo also needs View Audit Log. If the relevant entry is outside the last
100 ban audit events, permissions are missing, the ban changed, a different moderator
issued it or the server withdrew consent, Vivi preserves the ban for manual staff
review. Independent bans are never intentionally adopted by this system. Discord
does not provide an atomic conditional-unban API, so concurrent staff actions may
still need manual review.

Members can appeal global entries by emailing **Vivi-Roseveil@proton.me** with their
user ID and relevant context. Local server bans and local appeals remain the
responsibility of that server's staff. Neither a profile deletion nor a global-list
removal automatically reverses independent moderation actions.

## Reliability and records

Jobs and per-server results are stored in SQLite and survive restarts. A bounded
worker checks permissions, consent and active entry state again before acting;
transient Discord failures receive limited backoff retries. **Retry jobs** retries
eligible failed/skipped work without bypassing those checks. Startup reconciliation
checks active entries in currently participating servers. Duplicate jobs and existing
bans do not cause repeated ban requests.

Global entries keep the target ID, reason, evidence reference, operator, timestamps
and a bounded action history. Consent records bind identities; ledgers and jobs record
outcomes and ownership markers. These are moderation records, retained for operator
review, and belong in encrypted full-data backups rather than configuration exports.

Automated tests use synthetic Discord accounts and mocked ban endpoints. Adding
this code and operator ID does not itself create any global entry or issue a ban.
