# Milestone 10.1 — Competition public access readiness

Assessment and implementation plan, 2026-10-31. **No publication authorization.**

The production game remains on Milestone 10.0: Render commit
`98cdb0bf99d7eaba2258121d9b4213ea25eea874`, Sites source
`0a63ae9a9ee668c36fc1fc0a6c422678393dca24`, Sites version 2/environment revision 1.
Read-only Sites metadata confirms owner-only access and zero external viewers;
public access and external invitations are supported capabilities, not enabled
permissions. An auth client ID is present; that is not proof of public sign-in
or external-account compatibility. Render still has one 0.5 CPU/512 MB instance,
one existing 1 GB disk and automatic deployments disabled.

This work changed documentation/evidence only. It made no deployment, commit,
push, audience change, invitation, production game request, database write,
provider call, secret change or resource creation. Tests below used local mocks.

## 1. Recommendation

Use **an anonymously readable information page, with Sites-managed Sign in with
ChatGPT required before creating, joining or reconnecting to a mission**. Keep
callsigns and separate per-seat credentials; do not add a game password/account
system. Retain the existing relay HMAC visitor claim, gateway secret, Origin
checks and all backend action/seat authorization.

This is the smallest supported access adaptation. It changes relay/frontend
entry and reauthentication UX, not the authoritative FastAPI engine, database,
gameplay rules or infrastructure. Do not publish by changing the audience alone.

The public audience and application sign-in are separate controls. Official
OpenAI documentation supports public content with optional Sites-managed sign-in;
we would make that sign-in mandatory for game APIs. Named external viewers are
also available as a nonpublic trial, with separate approval. Sources:
[Sites sign-in](https://learn.chatgpt.com/docs/sites/data-and-connections#add-sign-in-with-chatgpt),
[sharing and external viewers](https://learn.chatgpt.com/docs/sites/publishing-and-sharing).

If the competition requires play without any ChatGPT sign-in, this recommended
model does **not** meet that requirement. Resolve that requirement before launch;
do not silently advertise anonymous guest play or weaken the gateway to provide it.

## 2. What public visitors encounter today

| Visitor | Current relay behavior if the audience became public |
| --- | --- |
| Anonymous landing-page visitor | Static frontend is served, but entry currently says “No account required” |
| Anonymous capabilities/create/join request | HTTP 401 before contacting Render |
| Anonymous WebSocket upgrade | HTTP 401; no mission connection |
| Authenticated visitor with a platform-injected ID | Relay derives a pseudonymous visitor claim and forwards the protected request |
| Visitor supplying only `X-Consensus-Visitor` | Rejected when platform identity is absent; the supplied claim is never forwarded |
| Authenticated visitor without a valid seat credential | Cannot resume another seat or perform its actions |

The installed Sites identity reference explicitly says public requests may lack
both authenticated identity headers. Signed-in user IDs are stable within a
Site and differ between Sites. The platform owns identity injection and sign-in.
See the installed `identity-and-secrets.md`, starter README and
`templates/vinext-starter/app/chatgpt-auth.ts` referenced in the evidence file.

Current code paths:

- `deploy/sites/worker.mjs:27`: missing `oai-authenticated-user-id` returns 401.
- `deploy/sites/worker.mjs:49`: a small forwarding allowlist excludes visitor
  cookies, raw account identity and caller-supplied visitor/proxy headers.
- `deploy/sites/worker.mjs:60`: HMAC-SHA256 over `visitor:` plus the platform ID
  produces the stable backend visitor claim using the server-only gateway key.
- `backend/app/railway.py`: the backend requires the gateway secret and a valid
  trusted visitor claim before serving game requests. Origin alone is insufficient.
- `frontend/src/session.ts`: a separate bearer seat credential lives in this
  browser's localStorage; the backend stores its hash. Sign-in is not seat recovery.

Seven local relay fixtures confirmed anonymous landing access, anonymous API/WSS
denial, rejection of a forged backend visitor claim alone, and authenticated-fixture
HTTP/WSS forwarding with the same derived visitor identity. These fixtures make
zero production requests. They do not prove how public dispatch handles headers.

### Essential trust boundary still requiring validation

The relay must receive identity **from Sites dispatch**, never from an internet
caller. Its HMAC authenticates the relay's claim to Render; it cannot turn an
unverified input header into a verified person. Local tests inject platform header
fixtures and therefore cannot validate public header sanitization.

Before admitting public gameplay, establish that public dispatch removes or
overwrites caller-supplied `oai-authenticated-user-id`/email headers, including on
WebSocket upgrades. Test anonymous spoofing and authenticated A attempting to
claim B. Missing identity must fail closed, and spoofing must not change quotas.
Existing owner-private rejection tests do not prove this public behavior because
dispatch rejects anonymous callers before the Worker runs.

The starter documents platform-owned injection, but the material inspected does
not explicitly specify every public-mode header-spoofing case. Treat successful
hosted validation or a sufficiently explicit platform guarantee as a release
gate, not as an established exploit or a reason to weaken checks. If trustworthy
identity cannot be established, public gameplay is a no-go.

## 3. Guest access versus ChatGPT sign-in

| Model | Assessment |
| --- | --- |
| Keep current security and just enable public audience | Anonymous users cannot play; confusing entry UX; not ready |
| Public information, ChatGPT sign-in to play | Recommended supported path; no backend rewrite or extra paid service |
| Platform-supported anonymous identity | Not documented in the inspected Sites contract; cannot assume it exists |
| Custom signed anonymous session cookie | Technically conceivable, but a separate identity/abuse design, not an available feature or approved implementation |
| Browser UUID, callsign, unsigned cookie, query/header ID or unverified IP | Caller-controlled or unstable/shared; unacceptable replacement for trusted identity |
| One shared `anonymous` visitor bucket | Collateral rate limits and no useful visitor isolation; not recommended |

A server-issued, cryptographically verified guest cookie could preserve the
gateway and separate seat checks, but it would not establish one person per
identity. Clearing cookies or requesting fresh identities can reset guest quotas.
It would require supported cookie/upgrade behavior, issuance limits, expiry,
cross-origin protection, key-management review and credible abuse controls.
Mobile/in-app cookie restrictions also require testing. A signed cookie alone
does not preserve the strength of today's account-based abuse buckets.

The Sites workflow directs us to preserve its hosted authentication integration
rather than scaffold a separate OAuth/session stack. Do not introduce a custom
guest stack by default. Anonymous play needs a separately approved design after
platform support and competition requirements are established. No guest route,
cookie, signing key, provider or paid bot-protection service is added here.

Never expose the gateway key to the browser, hash an arbitrary caller ID as if
it were verified, fall back to email/IP identity, or distribute a Sites service
bypass token. Service access supplies no visitor identity and does not replace
seat authorization.

## 4. Minimum implementation, after approval

### Relay and frontend access state

1. Add a narrowly scoped, no-store relay-local access-status response with only
   the state the UI needs, such as `signedIn`. No raw account ID, email, visitor
   HMAC, secret, membership directory or mission data. It must not forward an
   anonymous call to Render. The exact response is an application proposal,
   not an existing Sites API.
2. Gate entry and saved-seat WebSocket startup on that state. Signed-out users
   see an ordinary **Sign in with ChatGPT** anchor; signed-in users see callsign
   entry. Keep unauthenticated game APIs/WSS rejected server-side.
3. Use the platform-owned `/signin-with-chatgpt` route with top-level navigation
   (`target="_top"`), not fetch or client routing. The installed helper uses
   `return_to`. Preserve only a validated same-origin relative application path,
   including the invite query. Reject external/protocol-relative destinations
   and reserved auth paths. Never put seat credentials in URLs.
4. Keep `/signin-with-chatgpt`, `/signout-with-chatgpt` and `/callback` owned by
   dispatch. Do not implement an OAuth exchange or import Next.js server helpers
   into the React client. Preserve React/Vite and Worker ESM.
5. Distinguish expired Sites sign-in from invalid game credentials. Currently,
   entry shows a private-playtest 401 message, capabilities silently become
   unavailable, and failed WSS handshakes can retry indefinitely. Recheck access
   after relevant HTTP errors/repeated handshake failures, pause attempts while
   signed out, offer sign-in and resume the saved seat after successful access.
   Do not turn every policy-close 1008 into login: an invalid seat remains invalid.
6. Change the misleading entry copy to: “Sign in with ChatGPT to play. No separate
   game account or password. Choose a callsign for your team.” Use general
   sign-in-required errors instead of “private playtest” copy where appropriate.
7. Keep all protected responses/HTML with auth state no-store. Optionally evaluate
   immutable caching only for fingerprinted public JS/CSS; current static assets
   are also no-store, increasing repeat-load traffic. This is not needed for auth.

Expected files: `deploy/sites/worker.mjs` and tests; `frontend/src/App.tsx`,
`missionEntry.ts`, `missionConnection.ts`, `useLobby.ts`, relevant components,
styles, tests and public instructions. New small access/disclosure components are
preferable to a large App refactor. **No backend or database change is needed for
the recommended access model.** Any later demonstrated backend need returns for
review rather than silently entering this scope.

### Account changes and bearer-seat limits

ChatGPT identity presently gates eligibility and rate buckets, not seat ownership.
The same account in another browser does not automatically recover a game seat.
Another account in the same browser profile may inherit locally stored seat
credentials. Multiple tabs in one profile normally reuse the same seat.
Likewise, a copied valid bearer credential can restore that seat for someone who
passes the Site's entry gate; changing the ChatGPT account does not invalidate it.

Use one browser profile/device per player in instructions. Add an explicit
shared-device/sign-out treatment: close the app socket and offer forgetting local
seat credentials with a warning that they cannot be recovered merely by signing
in again. Test account switching and canceled sign-in. A normal sign-out should
not silently leave an apparently private seat for the next user. Avoid claiming
that external platform sign-out revokes existing WSS sessions or clears storage.

If strict account-bound seats or cross-device recovery is required, that needs a
separate approved authorization/persistence design. Do not silently bind existing
seats to new identities, revoke credentials or change gameplay membership here.

## 5. External accounts, instructions and mobile

External-account compatibility is **plausible, not yet verified**: the engine
accepts independent seats and the quota identity is Site-scoped, but Milestone
10.0 tested three simulated backend players plus the owner's browser relay path.
It did not establish real outside-account sign-in, public header sanitization or
cross-account privacy on the actual Sites edge.

After separate audience/invitation and game-data-write approvals, use the owner
and two or three named external **viewers**, never editors. Test a personal/free
account and an outside-workspace account where available. Do not infer a paid
visitor subscription requirement from the Site author's plan. Confirm invite
acceptance, mobile top-level login and return to the original mission URL.
Private invited-viewer tests still cannot prove signed-out public-mode behavior.

Public instructions should explain:

- 2–4 players, one callsign/seat per browser profile/device; the host shares the
  invite and starts once everyone is connected.
- Ten authored crises, role-private intelligence, public AI recommendations,
  hidden plurality voting and the tie/revote/AI tie-break sequence.
- Signing in does not reveal a teammate's intelligence or recover a lost seat.
  Keep the same browser/storage and invite to reconnect; avoid sharing a browser
  profile, screenshots of private intelligence or a live mission invite publicly.
- Callsign length is 1–24 characters. Clipboard fallback exists; QR joining is
  not implemented. Add local QR rendering only if selected as a separate small
  UX item; do not send invite tokens to an external QR-generation service.
- Authored content is being used; no live LLM generation or provider access is
  required. The host's recommendation is game content, not a promise of an optimal
  decision.

### Dropout limitation requiring an owner decision

Current `Player` stores connection state but has no disconnect-expiry timestamp.
`set_connected()` preserves the seat, and `continue_mission()` requires every
reserved seat to be connected. Automatic five-minute removal/role redistribution
is not implemented in this deployed version. Reconnect success does not prove
that feature. A permanently departed player can strand the team at a mandatory
progression point; a fresh mission may be necessary.

Do not publish a five-minute automatic-recovery promise. Decide whether to accept
and disclose this limitation for the competition or authorize a separate gameplay
milestone. This assessment does not implement seat removal or change voting.

### Mobile assessment

Existing evidence supports responsive foundations: 48 px controls, stacking at
small widths, wrapping presence, labeled forms, reduced-motion/contrast checks
and local browser checks at 320/390/768/1440 px. It does not establish the new
public sign-in flow or physical-device behavior. No new visual/mobile run was
performed in this assessment.

Require actual iOS Safari and Android Chrome trials: portrait/landscape, 200%
zoom, keyboard/IME input, clipboard fallback, long callsigns/invites, voting
controls under the keyboard, review-table scrolling and returning from sign-in.
Test backgrounding/screen lock and Wi-Fi/mobile transitions. Confirm the same
seat returns and stale controls remain disabled; do not reset server deadlines.
Test external-browser versus in-app-browser storage isolation explicitly.

## 6. Player-facing data and retention disclosures

Add a short entry disclosure and a persistent “Data and privacy” link in lobby,
gameplay and review. Explain callsigns, team chat, decisions/votes, metrics and
mission history are persisted; chat is for the mission team and votes remain
hidden until resolution. Warn against entering sensitive information. Describe
invite-based admission separately from private-role authorization.

Explain that Sites handles sign-in. The relay uses a Site-scoped account ID to
derive a pseudonymous abuse-control identifier; it does not forward raw identity,
email, names or cookies to Render. Do not call this anonymous or promise that
OpenAI/Render process no request metadata. The game should not prefill or reveal
account email/name as the player's callsign.

Proposed player wording, subject to owner review:

> This browser remembers your mission seat. Keep using the
> same browser; clearing its storage or changing devices may lose that seat.
> Callsigns, chat and mission results are saved on the game server. When everyone
> is offline, inactive lobbies expire after 24 hours, unfinished missions after
> 7 days, and finished missions after 30 days. Returning can extend these periods.
> Missions do not expire while someone remains connected.

The exact implementation measures from the later of accepted activity and
finalization, skips connected missions, and cleans up periodically in batches.
Do not promise deletion exactly at a wall-clock instant or permanent archival
of endgame review. Completed retention also covers failed missions.

Browser seat keys can outlive server records. “Forget this browser's seat” is
local credential removal, not server-wide mission erasure. There is no current
self-service server deletion endpoint; do not invent one or an operator contact.

**Before publication, the owner must approve a finite backup-retention policy and
an actual contact/removal process.** Encrypted off-disk snapshots are separate
copies and are not purged by application TTLs. The previously proposed rollback
window is not a completed ongoing backup/deletion policy. Public copy must not
promise erasure from all copies at the mission TTL. No retention period, backup,
production record or deletion mechanism is changed in this assessment.

## 7. Tests and limited-load readiness

### Security/functional matrix

| Area | Required evidence before public gameplay |
| --- | --- |
| Anonymous access | Instructions readable; game writes/upgrades denied; sign-in CTA usable |
| Identity spoofing | Anonymous forged identity/email/visitor/IP rejected on real dispatch; authenticated spoof cannot change actor |
| Login callback | Invite survives; open redirects/auth loops rejected; cancellation/expiry handled |
| Cross-account | A/B/C have separate quotas and seat keys; roles/votes filtered; no email/raw ID leakage |
| Stable actor | Same account across allowed profiles gives stable visitor identity; different accounts differ, including behind one shared IP |
| Seat authority | Missing/wrong credentials rejected; valid copied bearer keys have the documented same-seat behavior; supplied role IDs never grant roles; login alone never restores another seat |
| Shared browser | Sign-out/account switch/local-storage loss behavior explicitly tested and disclosed |
| Game | 2/3/4-player rules, 4-player 2–1–1 plurality, ties, chat, reconnect, full ten-crisis mission/review |
| Transport | Real signed-in browser HTTP/WSS, auth-expired handshake, no credential query strings |
| Mobile | Real iOS/Android tests described above |
| Retention | Disclosure matches deployed policy; natural expiry observed later; local injected-clock tests cover boundaries |

Prefer boolean operator comparisons of test missions' creator identifiers for
identity isolation; never add a public diagnostic returning raw IDs or HMACs.
Use only synthetic missions and approved viewers in hosted trials, preserving
existing records. Validate all fixture callsigns and request schemas before
allocating a seat. Enforce a hard test-creation budget; a failed lobby allocation
must not silently produce another mission on retry. Retain test artifacts under
normal policy rather than adding a cleanup/delete backdoor.

### Limited load proposal, not authorization

Milestone 10.0's three-client sampled memory/CPU was comfortably within the
approved instance. That is not a public capacity guarantee. Full-state broadcasts,
chat fan-out, accumulated history and reconnect bursts need a bounded test.

1. **Local first:** existing 0.5 CPU/512 MB container configuration, synthetic
   temporary SQLite and fixture gateway identities. Stage 1/3/5 concurrent missions
   with 4/12/20 sockets, controlled chat/votes and bounded reconnect bursts. A
   single visitor's 16-socket cap still applies; distinct synthetic identities are
   allowed only in the isolated local gateway fixture, never as production spoofing.
2. **Hosted later, separately approved:** one real external-account mission first;
   then at most three concurrent synthetic missions/12 sockets for ten minutes.
   Specify exact total mission creations and real account distribution in that
   approval. Keep authored mode, current rates and one authoritative instance.
3. Confirm available Render bandwidth and Sites hosting/traffic allowance first.
   Use included capacity only; the $0 extra-build limit is not a traffic-spend cap.
   Proposed generator ceiling: 25 MiB application payload received, with sufficient
   additional platform-overhead headroom. This limits the generator, not all site
   traffic or the invoice. Do not run hosted load when overage exposure is unknown.
4. Suggested success target: no unauthorized data, duplicate seats, lost accepted
   actions, inconsistent results or integrity errors; action-to-authoritative-state
   p95 below two seconds, measured on the generator's own monotonic clock.
   Expected 401/403/409/413/429/policy closes are evaluated against the scenario,
   not mistaken for server failure.
5. Proposed client-side stop thresholds: memory over 350 MiB; CPU above 0.4 core
   sustained for 60 seconds; free disk below 128 MiB; unexpected 5xx, integrity or
   privacy failure; or exceeded time/byte/creation budget. Stop test clients and
   report; do not restart, resize, delete data or change quotas automatically.

No production load, database copy, new load service, telemetry store or paid
resource is needed for this assessment. Any later hosted test writes game state
and consumes metered resources, so it needs an explicit test/data/usage approval.

## 8. Publication sequence and withdrawal

1. Owner selects the sign-in model, confirms competition rules, decides the
   stranded-seat limitation, and approves disclosures/contact/backup policy.
2. Authorize local relay/frontend implementation and tests. Review the exact
   changes; separately authorize commit/push and an owner-private deployment.
   Preserve the current backend commit, disk, keys and manual deployment settings.
3. After separate permission for named **viewer** invitations, run the nonpublic
   external-account/mobile trial. That audience would be private to invitees,
   rather than owner-only; make no such change under the present instruction.
4. Public anonymous-dispatch behavior cannot be proven while the audience remains
   owner-private. Obtain a platform guarantee or request explicit approval for a
   short public canary with game admission disabled at the relay. Validate sign-in,
   header scrubbing, safe callbacks and WSS without exposing mission data. A
   public canary is itself publication and must never be treated as a free probe.
5. Obtain the exact limited-load approval and run only the selected budgeted
   scenarios. Keep LLM calls disabled. A failed gate stops publication rather than
   causing an unapproved backend rewrite or resource upgrade.
6. Present evidence and obtain the final “Anyone on the internet”/game-admission
   approval. Verify signed-out instructions and signed-in gameplay, maintain
   existing gateway protections and observe rejections, disk, memory and traffic.

Before any audience change, record its original policy and approved rollback.
Returning to owner-only blocks new visitor entry, but **must not be assumed to
revoke already-open WebSockets**: game authentication occurs at connection setup.
Test/confirm platform revocation behavior. Any required emergency connection
drain/process replacement must be explicitly covered by the later rollout
authorization; no extra restart, secret rotation or database restoration is
authorized now. Never expose Render directly to compensate for a Sites issue.

## 9. Readiness decision

**Ready to review a small ChatGPT-sign-in implementation; not ready for public
competition publication.** The remaining gates are public identity trust and login
return behavior, real outside-account/mobile acceptance, truthful access/retention
copy with a backup policy, an explicit dropout-limitation decision, and bounded
load evidence. Current production remains preserved and owner-private.

Local assessment evidence: `docs/evidence/milestone_10_1/assessment.json` and
`relay_access_assessment.json`. No implementation or publication was performed.
