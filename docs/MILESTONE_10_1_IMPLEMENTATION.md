# Milestone 10.1 — Local competition sign-in experience

Completed locally 2026-10-31. **Not committed, pushed, deployed or published.**
Production remains on Milestone 10.0; no production game request, mission update,
viewer invitation, secret rotation or paid resource/provider call was made.
The existing Sites audience was not changed.
Read-only Sites metadata reconfirmed version 2, owner-only access and zero external viewers.

## Implemented behavior

### Access and entry

- `GET /api/access` is served by the relay itself and returns exactly
  `{"signedIn":true}` or `{"signedIn":false}`, with `Cache-Control: no-store`.
  It does not contact Render or return account IDs, email, visitor HMACs,
  credentials, mission information or authentication URLs. Wrong methods,
  upgrade requests and foreign Origins are rejected.
- Public game information remains visible without sign-in. Anonymous game API
  requests, including create/join/WebSocket upgrade, still receive 401 before
  upstream forwarding. No anonymous guest ID or custom authentication stack exists.
- The frontend checks access before mounting gameplay or opening a saved-seat
  WebSocket. It presents checking, unavailable, signed-out and signed-in states.
  It never renders remembered private game state while sign-in is absent.
- Sign-in uses a normal `target="_top"` anchor to the platform-owned
  `/signin-with-chatgpt?return_to=...`. Sign-out similarly uses the platform route.
  There is no fetch-driven OAuth exchange or application callback implementation.
- Return paths retain only a validated application-root mission invite. External
  URLs, protocol-relative paths, backslashes/control characters, auth routes,
  duplicate/malformed invites, arbitrary queries and fragments are discarded.
  Seat credentials are never put in a URL. Invalid invites show an error rather
  than silently becoming new-mission requests.
- A host-created invite is preserved through later sign-in expiry and cancellation,
  not just when the page was initially opened from an invitation.

### Reauthentication and game seats

- HTTP 401 from entry/actions causes a separate access check. A valid ChatGPT
  session with an invalid seat retains the existing game-session error behavior.
- Repeated WebSocket handshake failures, or a policy close, check site access.
  Confirmed signed-out access stops socket retries and offers sign-in without
  deleting the saved seat. Successful reauthentication restores that credential,
  identity and roles. No new seat is allocated automatically.
- A policy-close 1008 while site access remains valid is treated as an invalid
  game seat, not an invitation to loop through sign-in. Unknown network/access
  errors preserve credentials and the bounded existing reconnect strategy.
- Access checks time out after eight seconds. They do not follow redirects with
  fetch. A platform-level 401/403 or manual/opaque redirect also prompts normal
  top-level sign-in, covering private dispatch rejecting a request before the
  relay can return JSON. Non-auth service failures remain unavailable/retry states.
- Focus, pageshow and returning to a visible document recheck access. Obsolete
  async probes cannot resurrect a stopped connection or schedule duplicate sockets.

### Explicit sign-out and forgetting

- “Sign out and forget saved seats” asks for confirmation before removing this
  browser's `consensus.session.*` credentials and using platform sign-out.
- A separate “Forget this browser's saved seats” action has the same irreversible
  warning. It does not delete server records, unrelated browser storage or any
  other player's seat. Confirmed forgetting stops the local game connection.
- Other same-origin game tabs observe seat removal through the storage event,
  close their transport and remove their private gameplay UI.
- Cancellation preserves credentials and the current mission. Failure to remove
  storage prevents sign-out navigation and warns the user to clear site storage
  before sharing the profile. Local tests exercise this failure path.

**Bearer-seat limitation:** site identity remains an eligibility/rate-limit
identity, not a new account binding for seats. A person holding a valid copied
credential can reuse it after passing site access. An account switch performed
outside the app, with both accounts signed in, cannot be distinguished by a
boolean-only access response. App-controlled sign-out/forgetting handles the
normal shared-browser flow; it is not a global revocation or account-isolation
guarantee. The UI instructs players to use individual profiles/devices and forget
old seats before using another account. Strong account binding or cross-device
recovery would require a separate approved design, not a silent change here.

## Instructions and disclosures

The entry no longer says “No account required.” It explains ChatGPT sign-in,
2–4 individual profiles/devices, callsigns, host-created invites, private roles,
chat, the real 60-second discussion and 20-second tie window, hidden plurality
voting, AI tie-breaking, ten authored crises and shared results.

The existing dark civic-console layout and all gameplay components are retained.
The new information and disclosure panels use the same typography, colors,
spacing, keyboard focus treatment and 48 px controls. Public information is
available before sign-in; data/privacy details are also present in lobby,
gameplay and endgame review.

The disclosure covers team chat and persisted game records, hidden-vote timing,
browser seat secrets, no automatic cross-device recovery, pseudonymous abuse
identification, raw identity not forwarded to Render, and hosting-provider
processing. It distinguishes local forgetting from server-wide erasure.

It accurately describes 24-hour lobby, seven-day unfinished and 30-day completed/
failed inactivity retention, connected-seat exemption, activity extending periods,
periodic cleanup and backups as separate copies. It promises neither exact-time
deletion nor erasure of backups. Permanently disconnected players cannot currently
be removed/replaced; stranded teams may need a fresh mission. No automatic
five-minute recovery/removal is advertised.

### Configuration still required before publication

`frontend/.env.example` documents two **public build-time** values:

| Value | Purpose |
| --- | --- |
| `VITE_OWNER_CONTACT_URL` | Owner-approved HTTPS or simple mailto contact reference |
| `VITE_BACKUP_RETENTION_NOTICE` | Owner-approved finite backup retention and removal explanation |

Defaults remain blank. Missing/invalid contact or missing policy produces a
visible preview/publication-dependency message. No contact details, backup period
or self-service server deletion feature were invented. Unsafe contact schemes,
embedded URL credentials and mailto query/control injection are rejected.
These fields are public text, not secret storage; do not put credentials in them.

## Trust boundary and limits of local verification

The HMAC visitor claim, backend gateway secret, exact Origin handling, forwarding
allowlist, limits and separate per-player authorization are preserved. The relay
does not accept an arbitrary browser visitor ID, email, proxy address or cookie
as an alternative identity source. It reads only the Sites dispatch-owned ID
header and never forwards the raw identity or incoming visitor/proxy claims.

**Sites dispatch must strip/overwrite caller-supplied identity headers.** A direct
call to the Worker function can supply a header of the same name; this code cannot
cryptographically distinguish that from dispatch injection. It must not be hosted
behind an arbitrary proxy that forwards internet headers unchanged. Public header
sanitization, including duplicate/case-variant headers and WSS upgrades, remains
a mandatory real-platform release gate. HMAC-signing an unverified caller ID
would not make that ID trustworthy.

Relay spoofing tests use an explicit fixture dispatch that removes incoming
identity headers before injecting a known test identity. They verify forwarding
and failure behavior under that contract. They **do not prove that actual Sites
public dispatch implements that contract**. No bypass token or guest identity
fallback is used.

Browser acceptance uses a separate, loopback-only fake dispatch in
`backend/tests/browser_acceptance_server.py`. Its fake cookie and confirm/cancel
routes exist only in that test adapter. The production Python application has
no such routes or authentication changes; Docker copies `backend/app`, not this
test module. `CE_BROWSER_ACCESS_TEST=true` selects authored-only access scenarios;
the older full-game fixture uses explicit fake inference for regression coverage.
Neither uses operator provider settings or makes real inference requests.

Official platform contract references remain in
[the readiness assessment](MILESTONE_10_1_PUBLIC_ACCESS_READINESS.md):
[Sites sign-in](https://learn.chatgpt.com/docs/sites/data-and-connections#add-sign-in-with-chatgpt)
and [sharing](https://learn.chatgpt.com/docs/sites/publishing-and-sharing), plus
the installed Sites identity reference and sign-in helper. No live sign-in or
public audience operation was used to validate this implementation.

## Verification

| Check | Local result |
| --- | --- |
| Backend regressions | **704 passed**; no production backend source changed |
| Frontend tests | **117 passed, zero skipped**, including retained synthetic cross-layer fixtures |
| Relay tests | **11 passed** |
| TypeScript | Passed |
| Vite production build | Passed |
| Worker artifact build, `--local` | Passed; no Site identity created or publication performed |
| Python dependency check | Passed |
| Access browser acceptance | Passed; desktop, 390 px mobile and 320 px narrow layouts |
| Existing full-game browser acceptance | Completed, **zero findings**, realistic fake-provider-delay mode |
| Real provider / production requests | **Zero** |

The four optional cross-layer frontend cases use the retained local synthetic
chat, process-restart, victory/defeat and expanded-review captures. They are not
production data and were not copied into evidence. The standalone frontend run
also passes (113 passed; those four cases skip when fixture inputs are absent).

Access browser coverage includes:

- Anonymous information, hidden entry forms, denied create/join and fixture
  spoofing; keyboard Tab order, visible focus and Enter navigation.
- Invite-preserving sign-in and cancellation; unsafe return-data removal.
- Two real local browser contexts, including mobile/touch emulation, joining an
  isolated authored mission and receiving the same authoritative public state.
- Expired HTTP create/action requests, unchanged phase and preserved seat key.
- Expired WebSocket sign-in, stopped retry loop, removed private UI, cancellation,
  successful reauthentication and the same role/seat without duplicates.
- Invalid game credentials distinguished from missing site sign-in, then valid
  same-seat recovery after refresh.
- Canceled and confirmed sign-out, blocked-storage failure, shared tabs, clean
  fake-account switching, explicit forgetting and unrelated storage preservation.
- Invalid invite rejection and keyboard disclosure interaction.

Masked screenshots were visually inspected. Chromium mobile emulation is not
physical iOS/Android acceptance. The existing full-game browser run separately
checks three-client synchronization/privacy, full victory/defeat flows, restart,
timers and review; its backend and clock are isolated fixtures.

Evidence: `docs/evidence/milestone_10_1/implementation/verification.json`,
`access_browser.json`, `game_browser.json`, and the masked screenshots in that
directory. Private panels, chat and invite values are masked. No seat credentials,
raw identities, database copies or browser profiles were saved there.

### Reproduce locally

From the repository root:

```sh
.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend test
npm run test:relay
npm --prefix frontend run typecheck
npm --prefix frontend run build
node deploy/sites/build.mjs --local
.venv/bin/python -m pip check
```

For browser tests, use the existing compatible Playwright/Chromium runtime as
documented in Milestone 9.7. Set `CONSENSUS_PLAYWRIGHT_MODULE`,
`CONSENSUS_CHROMIUM` and the required runtime library path for this host, then:

```sh
node frontend/tests/accessBrowserAcceptance.mjs /tmp/NEW-unique-access-output
node frontend/tests/browserAcceptance.mjs /tmp/NEW-unique-game-output --require-clean
```

Output directories must not already exist. The harnesses start/stop their own
loopback fixtures and use new temporary SQLite files. Access acceptance blocks
all non-loopback browser requests and deletes its temporary database afterward.
Do not point either harness at Sites, Render, production databases or a provider.
Ordinary bare FastAPI development does not implement the relay-local status or
Sites sign-in; use these explicit fixtures for auth-aware local testing rather
than adding a production auth-bypass flag.

## Exact future rollout and external-account plan

Each stage below needs its stated **new authorization**. None was performed.

1. **Review/configuration:** approve the local diff, contact reference and finite
   backup policy. Decide whether current bearer-seat/shared-browser and stranded-
   seat limits are acceptable. Confirm ChatGPT sign-in is acceptable to competition
   judges; do not assume outside visitors require a paid subscription.
2. **Scoped source authorization:** authorize only the Milestone 10.1 frontend,
   relay, supporting tests/docs and corresponding Sites source commit. Preserve
   unrelated untracked work and private operator evidence. No merge/force push.
3. **Owner-private Sites deployment:** separately approve updating the existing
   project `appgprj_6ae4eb0c13cc8191ad3f7fe36e793414`. Reconfirm owner-only access,
   preserve its environment/gateway key, capture version 2/environment revision 1
   as the rollback reference, build the exact reviewed source and use the private
   deployment operation. Do not deploy Render: its existing Milestone 10.0 backend
   supports this relay/frontend change unchanged.
4. **Private hosted acceptance:** get explicit permission for a bounded synthetic
   mission and its normal API writes. Verify status shape/cache, owner HTTP/WSS,
   anonymous denial, sign-in cancellation/expiry, same-seat reauthentication,
   sign-out/forgetting and original-record preservation. Use supported operator
   access for read-only integrity checks; no direct writes, cleanup or restart.
   Validate test callsigns before allocation and stop at the exact creation budget.
5. **External viewer approval:** obtain named accounts/emails and explicit viewer
   invitation/audience permission, plus a separate game-data/usage budget. This
   changes owner-only to named-viewer private access; do not treat it as already
   authorized. Never grant editor roles. Test owner plus two/three real outside
   accounts, two/three/four-seat games, role/vote isolation, same-account identity
   stability and different-account quota isolation. Output comparison booleans,
   not raw user IDs/HMACs. Confirm actual iOS Safari/Android Chrome invite/login,
   keyboard, backgrounding, network changes and same-profile recovery.
6. **Public-dispatch gate:** private viewers cannot establish anonymous public
   header behavior. Obtain an explicit platform guarantee or separately approve
   a controlled public-mode validation strategy. That is publication. The current
   implementation adds no admission kill switch: an admission-disabled public
   canary would itself need a reviewed guard before use. Test anonymous forged
   identity/email/visitor/proxy headers, duplicate/case variants, logged-in spoofing,
   callback redirects and WSS identity injection. Missing stable IDs fail closed;
   never substitute email or a guest cookie to make a test pass.
7. **Load/publication approval:** only after identity/physical-device acceptance,
   approve the assessment's exact load duration, creation/socket/byte budget and
   sufficient included traffic allowance. No test ran against production here.
   A final public-audience approval is separate from source/private deployment.

On a private Sites regression, use the previously saved private version as the
application rollback, preserving audience, environment and all Render data. Stop
instead of rewriting backend auth, rotating secrets, adding resources or issuing
a deliberate restart. Restoring an audience policy does not necessarily revoke
already-established sockets; real platform revocation behavior and any emergency
connection-drain authority must be agreed before public rollout.

## Scope inventory

- Relay: `deploy/sites/worker.mjs`, `worker.test.mjs`.
- Frontend: new `access.ts`, `useAccess.ts`, `AccessExperience.tsx`,
  `PublicInformation.tsx`, `vite-env.d.ts`, public `.env.example`; updated App,
  session, entry, connection, lobby hook and styles.
- Tests: new `access.test.tsx` and `accessBrowserAcceptance.mjs`; updated frontend
  runner/connection regressions and the **test-only** browser backend adapter.
- Documentation/evidence: this report and its implementation evidence folder.

No `backend/app` file, FastAPI game endpoint, voting/timer rule, balance, schema,
SQLite record, Dockerfile, Render Blueprint or production configuration changed.
All local fixture servers stopped. The implementation is ready for source review,
with publication risks and external-account acceptance explicitly still open.
