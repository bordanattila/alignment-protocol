# Sites deployment assessment

Assessed October 30, 2026. No gameplay or application source was changed, no Site
was created or deployed, and no paid inference was requested.

Subsequent preparation: the user selected Railway with a persistent volume.
See [Railway + Sites deployment](RAILWAY_SITES_DEPLOYMENT.md) for the prepared
configuration, local verification, and account/approval steps. The statements
below describe the initial assessment before that adaptation.

## Decision

The existing application cannot be deployed unchanged as a complete Sites app.
The documented Sites server runtime is Cloudflare Workers (128 MB per isolate,
HTTP-based external connections). Its supported application paths are static
assets, Vinext, and Worker ESM; its structured persistent storage is D1. The
installed Sites instructions do not document hosting an arbitrary Uvicorn/ASGI
process or a persistent local SQLite database.

The smallest adaptation is Sites-hosted React assets connected to the existing
FastAPI backend on a persistent Linux host. This preserves the authoritative
engine, SQLite history, authored campaign selector, privacy projections, and
WebSocket protocol. A backend host has not been identified or provisioned.
No `.openai/hosting.json` or deployment configuration exists in the checkout;
Sites returned no existing Sites in the selected account.

## Existing architecture and compatibility

| Component | Current implementation | Sites impact |
| --- | --- | --- |
| UI | React 19, TypeScript, Vite, responsive CSS | Production assets build successfully; preserve existing components and styling. |
| HTTP transport | FastAPI in `backend/app/main.py` | Requires an external ASGI host or a server migration. |
| Live state | One `MissionStore`, asyncio state lock, ordered socket broadcasts | Cannot assume one Worker isolate owns all clients or survives between requests. |
| Timers | Server deadlines checked by a continuous 100 ms scheduler | Keep existing process; Worker-only hosting needs durable coordination and wakeups. |
| Storage | SQLite WAL, full synchronous commits, Linux `fcntl` ownership lock | Requires private persistent disk and one owning process; D1 is not a drop-in filesystem mount. |
| Joining | Invite token plus separate seat credential | Preserve first-frame WebSocket authentication and per-mission saved credentials. |
| Privacy | Server allowlisted projection, role-specific intelligence and own vote | Keep filtering on the backend; never bundle crisis JSON into frontend assets. |
| Campaign | Ten seeded authored crises from a 30-crisis catalog, conditional follow-ups | Preserve current selector and content; no shortened campaign. |
| Review | Durable results, metric timeline, deterministic summary and optional generated interpretation | Retain SQLite aggregate and result invariants; disable inference. |

Relevant files: `backend/app/main.py`, `missions.py`, `connections.py`,
`persistence.py`, `domain.py`, `campaign.py`, `voting.py`, `consequences.py`,
`generation/config.py`, `frontend/src/missionEntry.ts`, `useLobby.ts`,
`missionConnection.ts`, `App.tsx`, `Gameplay.tsx`, and `MissionReview.tsx`.
Repository inventory also includes content, tests, existing verification reports,
and untracked gameplay-evaluation work, which was left intact.

## Recommended deployment adaptation

1. Retain FastAPI on one Linux process with a persistent private volume,
   TLS, and long-lived WebSocket support. Use a stable absolute
   `CONSENSUS_DB_PATH`, keep SQLite/WAL/lock files outside served assets, and
   start Uvicorn with `--workers 1 --ws-max-size 4096`.
2. Set `CONSENSUS_LLM_ENABLED=false` explicitly in the backend service
   environment. Supply no provider credentials. Confirm `/api/capabilities`
   returns `generated_missions: false` and generated mission creation is
   rejected server-side. Sites environment settings alone cannot disable an
   independently hosted backend.
3. Host only the existing Vite production output on an owner-private Site.
   The current frontend sends HTTP and WebSocket requests to its own origin;
   a static upload alone would therefore be broken.
4. Prefer a narrow same-origin Worker relay for the existing `/api` HTTP routes
   and WebSocket upgrade, after verifying that the Sites deployment and access
   layer support that upgrade end to end. The upstream must be a fixed trusted
   HTTPS backend, never a visitor-selected URL. Preserve session headers,
   authentication frames, close behavior, query handling, and uncached private
   responses. Keep the backend protected independently so knowing its origin
   does not bypass the intended private-preview access boundary.
5. If that relay is unavailable, add one configured backend origin shared by
   every HTTP call and the WebSocket URL. This requires explicit HTTP CORS and
   WebSocket Origin validation plus independent backend access control. A
   private frontend does not make a publicly reachable backend private.
6. Preserve the Sites audience as owner-private for review. An owner-only Site
   cannot serve external playtest participants until access is separately
   approved and granted. Do not make it public to work around testing access.

The relay is an implementation candidate, not a verified deployed capability.
No proxy or cross-origin changes have been made before a target host is known.
Existing saved browser credentials are origin-scoped; changing the frontend
origin does not automatically transfer sessions from localhost.

## Worker-only alternative

The documented Sites-native migration is to a Worker-compatible server and D1
storage while retaining the React design and authored data. This is a major
server migration: transport handlers, typed validation, state serialization,
atomic result persistence, timer execution, and reconnect behavior need porting
and regression verification. D1 alone does not provide mission socket ownership
or a continuously running timer process. Durable Objects with alarms would be a
candidate coordination mechanism only if Sites explicitly supports provisioning
those bindings; that support is not established by the installed documentation.
Do not present ordinary Worker globals as authoritative multiplayer storage.

No Worker-only rewrite should start without a separately agreed architecture.
Keeping the existing backend avoids this migration and is the recommended path.

## Preserve current behavior

The code is more specific than the original MVP specification: it has 60-second
discussion, 30-second hidden votes, a 20-second Consensus discussion followed by
a fresh 30-second vote, plurality outcomes, and AI fallback after a second tie.
The current final crisis is The Last Coordination; weakest-metric finale
selection is not implemented. Seats remain reserved rather than expiring after
five minutes with role redistribution. These are existing limits, not changes
required for deployment. This work does not alter those rules.

## Verification completed locally

Executed with `CONSENSUS_LLM_ENABLED=false` for Python checks:

- `.venv/bin/python -m pytest backend/tests -q`: **663 passed**, one dependency
  deprecation warning.
- `npm test` in `frontend`: **105 passed, 4 skipped, 0 failed**.
- `npm run build` in `frontend`: strict TypeScript checking and Vite production
  build passed.
- `.venv/bin/python backend/tests/smoke_milestone8.py`: passed with three real
  local WebSocket clients and temporary SQLite storage. Completed ten distinct
  authored crises, initial tied vote, Consensus Window and final voting,
  role-private intelligence checks, synchronized metrics/history, conditional
  follow-up content, idempotent acknowledgements, and process kill/restart
  recovery with the same identities and roles. This fixture uses a controlled
  clock; it does not change production timing constants.

These results do not establish remote, hosted, or physical-device acceptance.
No Sites preview URL exists yet.

## Required hosted acceptance before external playtest

Use authorized test visitors on separate browsers/devices. Confirm create/join
and capacity for 2–4 players, role assignment and network-payload privacy,
public recommendation, chat and presence, hidden votes, 2-1-1 plurality,
initial tie and second-tie AI fallback, refresh without a duplicate seat,
disconnect/reconnect, ten-crisis completion and endgame review. Verify TLS/WSS
through the actual Sites access layer, persistent-volume restart recovery,
saved history after deployment restart, and capability rejection of generated
missions. Include a phone layout check and normal production timer timing.

Do not claim deployment complete until those checks run against the actual
architecture. Public access and paid API requests require separate approval.

## Hosting references inspected

Installed Sites skill and its storage, identity/secrets, Worker ESM starter,
Vinext hosting manifest, and build helper were inspected. Primary local runtime
documentation:

- `/mnt/c/Users/borda/.codex/plugins/cache/openai-curated-remote/sites/1.1.2/skills/sites/SKILL.md`
- `/mnt/c/Users/borda/.codex/plugins/cache/openai-curated-remote/sites/1.1.2/skills/sites/references/storage.md`
- `/mnt/c/Users/borda/.codex/plugins/cache/openai-curated-remote/sites/1.1.2/skills/sites/references/identity-and-secrets.md`

Next required input: an existing HTTPS/WSS backend host with persistent disk and
its deployment access method, or a selected hosting target. No host cost or new
external infrastructure has been authorized or incurred by this assessment.
