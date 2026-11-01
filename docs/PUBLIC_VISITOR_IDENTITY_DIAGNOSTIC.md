# Public visitor identity: diagnostic-only candidate

Status: local only; no commit, push, deployment, public audience change, Render operation, provider request or mission creation.
Baseline: Sites source ba2f6b8c965f05191714e36eb96d5a627494bd0a (saved version 4).

## Scope

Changed files:
- deploy/sites/worker.mjs
- deploy/sites/worker.test.mjs
- deploy/sites/identity_probe.py (new operator-only Python helper; not bundled into browser assets)
- docs/PUBLIC_VISITOR_IDENTITY_DIAGNOSTIC.md

The existing bounded diagnostic endpoints independently parse ID and email. They log only event name, diagnosticVersion=2, approved case, transport, presence/validity booleans and two HMAC fingerprints. Each fingerprint uses JSON serialization of [consensus-identity-diagnostic, 2, window-deadline, sites-id|sites-email, validated-value]. The existing gateway key is used only server-side. Fingerprints cannot be compared across windows or against backend visitor claims.

Responses expose only the existing fixed no-store status/detail; they never expose fingerprints. Diagnostic responses are 503 if either validated input exists, otherwise 401. This is not a grant of gameplay access. Expired/missing windows return 404. No diagnostic request is forwarded to Render.

ID parsing rejects whitespace, controls, comma-joined values and excessive length. Diagnostic email parsing conservatively accepts one bounded ASCII addr-spec, rejects whitespace/comma-joined duplicates, empty/malformed local/domain labels and overlong components. Only domain case is normalized. Do not collapse local-part case, plus tags, dots or aliases. Some valid unusual emails are intentionally unsupported and fail closed. Full names do not identify users.

IMPORTANT: gameplay /api/access and X-Consensus-Visitor still use the unchanged ID source and visitor:<id> HMAC. No email authorization fallback or auto-selection was implemented. The candidate must stay admission-blocked during any future hosted diagnosis. Existing quotas, backend authentication, seat authorization and persistence are untouched.

## Evidence and limitations

Public documentation https://learn.chatgpt.com/docs/sites/data-and-connections#add-sign-in-with-chatgpt documents email and optional name, not ID. Installed Sites reference identity-and-secrets.md and starter chatgpt-auth.ts additionally describe/use a site-scoped ID. This discrepancy does not establish which layer supplied the repeated public ID. Prior canary evidence showed both accounts had one shared ID-derived fingerprint; it did not compare authenticated email values. No raw identities were retained.

Local checks: 15 relay tests passed; fixture-only dispatch matrix includes 24 authenticated and 12 anonymous HTTP/WS cases. A shared ID with distinct synthetic emails reproduces the ID collision while producing distinct email fingerprints. Duplicate/case-variant combined email values are rejected when delivered to Worker. Window and source namespace separation, raw-value non-disclosure, admission blocking and unchanged ID authorization are tested.

Negative control: a directly invoked Worker accepts an arbitrary well-formed email as diagnostic input. This proves that HMAC is pseudonymization, NOT proof of authenticity. A sanitizing fixture is explicitly NOT evidence that actual Sites dispatch sanitizes anything.

Operator helper: 24 offline simulated requests passed. Raw duplicate and case-variant email headers are sent alongside ID variants for both normal HTTP and actual WebSocket-upgrade request headers. Only fixed diagnostic endpoints are used. Cookie input uses getpass and remains in process memory; neither cookie nor response bodies/headers are printed or saved. A local machine may independently record terminal/session input; use trusted local terminals and never paste cookies into chat or shell arguments. Account labels are operator annotations, not authentication. No network is used in offline tests.

Current operator logs intentionally contain short-window HMAC pseudonyms; these are linkable within the window and are not anonymous data. Do not export raw log events. Compare in memory and retain only case counts/booleans. Sites/provider log retention is independent of application backup retention.

## Required hosted evidence (NOT YET VERIFIED; requires separate authorization)

No production test can establish the new fields without deploying the diagnostic candidate. No new public window is proposed as already authorized by this task.

After separately authorized scoped source push/private diagnostic deployment, preserve owner-private audience, closed gameplay admission, current secrets and Render. Confirm the candidate's diagnosticVersion=2 locally/private before any public window. Prepare both account helpers fully first.

If separately authorized to open a bounded public diagnostic window:
1. Verify active deadline, public policy and correct candidate deployment; register automatic private restoration before asking operator to send requests. Keep gameplay blocked regardless of fingerprints.
2. Obtain same-window base and five forged-header variants for each of two confirmed Sites accounts over HTTP and WebSocket upgrades, plus the anonymous matrix. Use identity_probe.py; do not reuse the old helper lacking email duplicate variants.
3. Compare only events with diagnosticVersion=2 and timestamps inside that exact window. Each account must have 12 distinct case labels. Require emailValid=true, one stable emailFingerprint per account across every accepted variant, and different email fingerprints between A and B. Inspect ID/email independently. A baseline 503 alone is NOT a pass. Explicit edge rejection of forged variants can be accepted only with evidence it occurred at dispatch and correct baselines reached Worker.
4. Anonymous cases must not yield an email or ID fingerprint even under forgery (or must be verifiably rejected at dispatch). Missing events, redirects, unexpected 404s, same account fingerprints, altered fingerprints, or unexplained errors fail the gate.
5. Restore private immediately after evidence collection or on failure/timeout. No gameplay unlock or budget activation during diagnosis.

These upgrade probes exercise dispatch's HTTP upgrade entry, not a completed gameplay socket. Preserve existing seat handshake and Origin checks and verify real authenticated socket behavior separately before claiming end-to-end acceptance.

## Conditional smallest correction (NOT IMPLEMENTED)

Only after actual sanitization and separation evidence: use the validated platform email for /api/access and gameplay identity, fail closed on missing/ambiguous email, and derive X-Consensus-Visitor with a separately versioned domain such as JSON([consensus-visitor, email-v1, email]). Never fall back to the known-colliding ID. Do not expose/store raw email or use display name. Keep gateway key, fixed upstream header allowlist, Origin/rate limits and seat secrets unchanged. No Render deployment, DB schema change, provider request or credential rotation is required for this relay correction.

Quota compatibility must be reviewed explicitly: switching HMAC inputs changes creator/rate-limit keys. Do NOT claim old per-visitor buckets automatically carry over. Persisted historical creator keys must remain unchanged; there is no reliable way to split one historical shared ID key into two accounts. Existing global mission/storage caps remain authoritative. Test stable new email-derived quota keys across HTTP/WS/reconnect/restart and spoofing, document one-time attribution discontinuity, and obtain acceptance rather than silently migrating records. Email address changes also create a new pseudonym. Existing game seats remain governed by their independent credentials; account switching and seat privacy need regression testing before release.

After separate approval for the proven correction: local tests/build, scoped source push, owner-private Sites deployment, authenticated access checks, then separately authorized public release and budget unlock. Preserve Render and main database throughout. The current task authorizes none of these deployments/access/budget changes.
