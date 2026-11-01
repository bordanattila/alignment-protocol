# Competition release — stable version 3 baseline

This release is based on GitHub `1b929e1fbd1fbd3f7696329b058bb37c7bd2c43e`, Sites source `ff975efce7af6dbaf9d2f98e6abf0829ed74be92` and Render `98cdb0bf99d7eaba2258121d9b4213ea25eea874`. No player removal, redistribution or host succession is included. No mission schema, voting, scoring, role assignment or timer is changed.

## Admission and identity gate

`CONSENSUS_ADMISSION_MODE` defaults to `closed`; only the exact value `public` permits existing authenticated game traffic. `canary` also blocks every game API/upgrade before Render. Static information and no-store boolean `/api/access` remain available. Existing gateway HMAC, Origin, input/rate limits and seat credentials remain mandatory.

In `canary` mode, `CONSENSUS_SECURITY_CANARY_UNTIL` is an epoch-millisecond deadline no more than 15 minutes away. Expired, missing or malformed windows expose no probe. The `/api/release-probe` and `/api/release-probe/ws` routes never forward to Render. They respond 401 for missing identity, 503 for an identity-bearing request, and log only a case label, transport, sign-in boolean and window-scoped HMAC fingerprint. Fingerprints are operator-only logs, not browser responses or backend visitor claims. Raw IDs, email, cookies, seat credentials and keys are never logged.

The probe observes identity supplied by actual dispatch, including upgrades; it does not itself prove that input headers were sanitized. Compare baseline/forged/duplicate/mixed-case/proxy probes for anonymous clients and two distinct signed-in accounts. Authenticated fingerprints must remain stable per account/transport and differ between accounts. Missing identity cannot become signed-in through supplied headers. Restore owner-private policy immediately on failure, ambiguity or the 15-minute deadline. Admissions stay closed until the entire gate passes. Audience restriction must not be assumed to revoke existing sockets.

Current blocker: the owner has no independent tester or second ChatGPT account available. Do not start a public canary, grant public gameplay, or report independent acceptance on the basis of owner-only or local mocks. The owner reports the Handshake submission form is editable with Submit enabled; this does not confirm extended prize eligibility.

## Paid inference allowance

The existing provider and validation/fallback are reused. The deployed factory can now read explicitly enabled settings but requires `BoundedReleaseProvider` and a pre-existing valid ledger on the existing persistent volume. A disabled flag retains authored-only operation. Only `gpt-6-luna`, the exact OpenAI Chat Completions endpoint, strict schema, a required key and a timeout no greater than 60 seconds are allowed.

The bounded adapter sets `service_tier=default`, `store=false` and `max_completion_tokens=8192` (including reasoning). Complete serialized request size is at most 32,768 UTF-8 bytes; a conservative 4,096-token framing allowance gives the local input envelope of 36,864 tokens. At approved standard rates of $0.10/M input and $0.50/M output this envelope is $0.0077824, below the reserved $0.01. Actual returned usage must be complete and within those bounds and the reservation; otherwise further paid inference is halted. No tools, alternative models, endpoints, processing tiers or automatic provider retries are added. Truncated/invalid generated content uses existing validation and fallback rather than relaxed contracts.

The separate `/data/consensus-llm-budget.sqlite3` operator ledger uses SQLite FULL synchronous transactions and an exclusive one-time initialization. It does not modify the mission database format. Each attempt reserves 10,000 microdollars before HTTP dispatch. Concurrent requests serialize at the shared provider and transactions enforce 100 total attempts / 1,000,000 reserved microdollars, across crisis and ending operations and across restarts. Reservations are never refunded, including failed/unknown-billed attempts. Missing/corrupt/failed persistence closes inference; it never initializes or replenishes from application startup. Paid failures halt subsequent attempts; gameplay continues using existing fallback.

Initially `phase=acceptance` permits one attempt only. Public inference cannot open until the synthetic acceptance script has verified one generated snapshot, isolated restart/integrity and role projections. That script is explicitly gated by `--authorized-one-request`; repeat execution refuses without dispatch. The subsequent operator `open-public` action requires the verified flag and a non-halted ledger. It is not authorized before the security gate passes. No dashboard alert is represented as a hard spending limit.

The one acceptance request is synthetic and uses a temporary SQLite mission only; it writes no live mission. It logs sanitized usage, source/failure, integrity and snapshot digest. A provider failure/fallback consumes that attempt and is not successful AI acceptance; no replacement request is authorized. Existing pending generated missions must be absent or separately approved before activation; preflight found zero.

Operator commands, only at the corresponding authorized stage:

```sh
python -m app.generation.release_budget initialize
python -m app.generation.release_budget status
python -m app.generation.release_acceptance --authorized-one-request
# Only after AI acceptance AND the actual public security gate pass:
python -m app.generation.release_budget open-public
```

The key is entered only in the existing Render service's server-side Environment settings using **Save only**. Other required values: enabled=true, model=gpt-6-luna, endpoint=https://api.openai.com/v1/chat/completions, response_format=json_schema, timeout=60, require_api_key=true, with the existing CONSENSUS_LLM_ prefixes. No key is copied to Sites, Git, archives or browser responses. Existing `render.yaml` retains its disabled safety baseline; a future Blueprint synchronization can turn inference back off and must be reviewed. This release uses explicitly saved service settings and a manual exact-commit deployment, not Blueprint provisioning or automatic deployment.

## Data and instructions

The owner approved `mailto:attila.bordan@snhu.edu` and a maximum 30-day encrypted operator-copy retention period. Public-only Vite settings are in `frontend/.env.production`; no credentials are included. Provider-managed copies/logs have separate disclosed retention. Operator expiry/purge tracking is required; this release does not claim to have installed a scheduled backup-deletion service.

Instructions retain mandatory ChatGPT sign-in, invitation-link joining, separate browser profiles, irrecoverable-seat warnings and the lack of permanent-dropout recovery. AI-generated mode is conditional on server availability; authored mode and fallback remain usable. Public scenario/history processing by OpenAI is disclosed. Neither no-login nor room-code competition compliance is claimed. No guest authentication is added.

## Verification and rollout

Local verification includes the existing backend/frontend/relay suites, real adapter mock transport with count-before-send, concurrent durable exhaustion, failure/usage controls, one-call synthetic acceptance and isolated restore, local sign-in/mobile-emulation browser acceptance, and a patched SQLite 3.51.3 container with gateway/authoritative authored HTTP/WSS checks. Local fixtures are not public identity or independent-account evidence.

Production preflight: SQLite integrity/foreign-key/application validation passed; five missions, 21 results, zero connected players, zero generated missions, generation disabled. A fresh online backup passed checksum and an identical-row isolated restore and was verified off-disk on the owner's encrypted storage. No restoration occurred. Preserve original finalized-result digest and compare after deployment. Preserve one instance/worker, 0.5 CPU/512 MB, existing 1 GB disk, gateway credentials, manual deployment and the $0 extra-build limit.

Deploy the closed-admission Sites update owner-private first, then manually deploy the exact reviewed backend source after saved-only settings and ledger preparation. Run the single authorized synthetic AI acceptance. Do not open the allowance to public inference or the Sites audience without the required account/tester gate.

If the security and AI gates eventually pass, the approved external smoke budget is one labeled two-player **authored** mission: independent sign-in, invite join, chat, votes, same-seat reconnect and phone access when available. No paid calls or replacement mission are authorized for that smoke. Stop at the minimum release; no polish, load expansion or recovery work.

On a critical update failure, stop and preserve production data. Keep or restore the private Sites baseline and closed admission. Any backend rollback must use the stable application with disabled generation settings; its old factory refuses enabled flags. No database restore or extra unapproved restart is part of rollback. The allowance file remains intact, never reset. A fallback is safe degradation, not proof that live AI acceptance passed.

## Exact source changes

- `backend/app/generation/provider.py`: default no-op pre-dispatch hook.
- `backend/app/generation/release_budget.py`: bounded provider and durable allowance.
- `backend/app/generation/release_acceptance.py`: one-request synthetic acceptance.
- `backend/app/railway.py`: explicit bounded enablement, existing protections retained.
- `backend/tests/test_release_budget.py`: focused allowance/adapter/restore tests.
- `deploy/sites/worker.mjs`: closed admission and bounded diagnostic canary.
- `deploy/sites/worker.test.mjs`: admission and canary fixtures.
- `frontend/src/PublicInformation.tsx`: accurate mode and provider disclosures.
- `frontend/.env.production`: approved public contact and finite backup notice.
- `docs/COMPETITION_RELEASE.md`: this release protocol.

No Dockerfile, dependency, infrastructure, gameplay or main database-format change is included. Existing SQLite 3.51.3 remains in the container.
