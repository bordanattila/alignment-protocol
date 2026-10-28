# Milestone 9.2 — Live context-aware crisis generation

Implemented locally on 2026-10-28, based on committed Milestone 9.1 (`9cf1adc`). The checkout was clean before work. No commit, tag, or push was created. Authored missions remain the default; generated missions require explicit creation-time selection and server enablement.

## Reconnaissance and decisions

Read `AGENTS.md`, the product specification, all five requested generation modules and configuration example, Milestone 9.1 documentation, mission/domain/campaign/consequence/persistence/connection code, HTTP/WebSocket routes, creation UI, and existing regression and smoke fixtures. Findings and the proposed integration point were reported before editing.

- `MissionStore.start` selected the first crisis. `continue_mission` acknowledged the immutable result and selected the next crisis. These are the only admission boundaries changed.
- The production factory uses the 30-entry authored campaign and Milestone 8 `select_crisis`; legacy test/embedding loaders may use fixed sequences. Selection depends on seed, slot, and executed results. Five authored prerequisites remain unchanged.
- All mutations run under the app's existing `asyncio.Lock`. `@persisted` commits an entire intent before success/publication and rolls it back on storage failure. `LobbyConnections` snapshots under that lock, then delivers outside it under its delivery lock.
- SQLite stores complete mission aggregates, a checksum, and a separate immutable result-hash index. On recovery, the current crisis is reconstructed from the saved sequence; no inference is needed to reconstruct content. Existing voting, metrics, history, and score logic operate on the canonical `Crisis` model.
- The foundation already supplies bounded async HTTP, typed sanitized failures, strict proposal validation, canonical identity, immutable acceptance, and an explicit deep-captured authored fallback selector. These were reused.

The historical repository instruction against live LLM calls is superseded for explicitly selected generated missions by this milestone's request. Authored mode retains its prior selection and gameplay rules. No framework, balancing algorithm, deployment service, or dependency was added.

## Configuration and mission modes

`CreateMissionRequest` extends the existing callsign request with `mode: authored | generated`, default `authored`. Existing clients sending only callsign remain compatible. Mode has no update endpoint and is immutable in persisted missions, including the lobby. Join requests cannot change it.

`GET /api/capabilities` returns only:

```json
{"generated_missions": false}
```

The value is true when generation is explicitly enabled and the endpoint/model/required credential are configured, or an explicitly injected test provider is supplied. Availability means configuration readiness, not proof that a remote provider is reachable. Generated creation while unavailable returns HTTP **409**, code `generation_unavailable`, with a concise safe message. Unknown/incorrect mode values return **422**. Credentials and provider configuration never appear in capability responses.

Settings use the existing Milestone 9.1 environment names, read at application creation/backend startup:

| Variable | Default | Purpose |
| --- | --- | --- |
| `CONSENSUS_LLM_ENABLED` | `false` | Allow optional inference / offer configured generated missions |
| `CONSENSUS_LLM_ENDPOINT` | unset | Complete operator-selected chat-completions endpoint |
| `CONSENSUS_LLM_MODEL` | unset | Operator-selected model |
| `CONSENSUS_LLM_API_KEY` | unset | Backend-only bearer credential |
| `CONSENSUS_LLM_REQUIRE_API_KEY` | `true` | Set false explicitly for unauthenticated local servers |
| `CONSENSUS_LLM_TIMEOUT_SECONDS` | `15` | Total deadline; finite, greater than zero, at most 120 seconds |
| `CONSENSUS_LLM_RESPONSE_FORMAT` | `json_schema` | Explicit `json_schema` or `json_object`; same backend validation |

No `.env` loading was added. `backend/generation.env.example` documents settings without real provider values. Invalid settings log only `configuration` and disable new generated creation. Existing generated missions can recover and progress with authored fallback if inference is disabled or credentials disappear after a server restart. Missing/invalid configuration never disables ordinary authored play.

## Live state machine and concurrency

Generated mission transitions:

```text
lobby --host start, all 2–4 seats connected--> preparing
preparing --validated durable admission--> briefing
briefing --> discussion --> existing voting / Consensus Window --> decision_locked
decision_locked --host acknowledgement, all seats connected--> preparing
decision_locked --tenth result acknowledged--> completed
resolved metric at zero --> failed (existing immediate defeat)
```

Starting assigns roles through the unchanged algorithm, snapshots initial metrics and the authored fallback catalog/seed, and persists a preparation attempt. Generated `sequence` contains only accepted crises; it starts empty and grows to ten. No ten-crisis inference batch is requested. The reported mission length is always ten, including early-loss summaries.

`GenerationAttempt` records a random internal ID, target slot, and pending/error status. `LiveGeneration` captures the request and existing authored selector while holding the state lock, then runs the foundation service in an independent asynchronous task. External inference never holds the mission lock or delays unrelated mission actions/timers.

Safeguards:

- One runtime task per persisted `(mission, attempt)`; the scheduler and repeated HTTP requests cannot duplicate it.
- Existing acknowledgement IDs remain the idempotency key. Repeated `/continue` returns `advanced=false`, including during preparation and after completion.
- Admission checks generated mode, preparation phase, exact attempt ID/status, target versus committed result count, and accepted sequence length. Late, replaced, terminal, or already admitted results cannot overwrite state.
- Presence-only publication revisions do not invalidate an otherwise current attempt. During preparation, completed history and metrics cannot change through gameplay intents, so the attempt/target check is the relevant freshness guard.
- A successful candidate survives transient admission storage failure in memory. A later scheduler attempt reuses it rather than calling inference again. Accepted state is published only after commit succeeds.
- Once admitted, the task finishes its ordered publication. Scheduler cleanup cannot cancel that publication merely because the phase is now briefing. A dedicated slow-publication regression covers this race.
- Shutdown cancels/awaits tasks before closing SQLite. Obsolete inference tasks are cancelled; admission guards still reject late responses.
- A disconnected player may return to a preparation snapshot without generating another request. Admission may finish while a seat is absent, but discussion cannot begin until every reserved seat reconnects. Result acknowledgement remains presence-gated. There is no automatic opening of discussion/voting on admission.
- The current crisis counter advances only after successful admission. During preparation, the previous accepted slot/result remains internal; public crisis/private-intelligence fields are empty, and the UI shows a preparation heading.

The implementation preserves the repository's supported **single-process, single-worker** authority. Persistent deployments retain the existing POSIX ownership lock, which prevents two app processes owning one database. An in-memory app instance is independently authoritative. No cross-worker or distributed inference-coordination claim is made.

## Failure and restart policy

The service handles timeouts, disabled/missing configuration, authentication/network/provider failures, unsupported/truncated responses, refusal/tool calls, malformed JSON, bad schema/effects/options, invalid continuity, and unexpected provider exceptions through the existing sanitized categories.

The fallback dependency is exactly `authored_selector(saved_campaign, target_index, completed_results)`, calling unchanged Milestone 8 `select_crisis`. It respects stage, used authored IDs, seed, and executed prerequisites. Generated IDs do not qualify an authored prerequisite unless the actual prerequisite crisis/choice was executed. Existing catalog capacity supplies valid independent fallback choices at every slot. No alternate selector or manufactured crisis is introduced.

Internal admission source is `generated` or `authored_fallback`. Source, provider failure details, prompts, and context are not projected to players. Once fallback is admitted, no second request is launched for that slot.

On restart:

- Already accepted crises are restored verbatim from the persisted sequence/admission; the LLM is never called to reconstruct them.
- A persisted **pending** preparation is resolved synchronously through its saved authored selector before serving requests. This avoids duplicate inference/charges across reloads or process crashes, including a crash before the provider actually received the request.
- A persisted **error** preparation stays visibly recoverable, awaiting host retry. No invalid fallback is fabricated.
- Timed accepted rounds retain the existing reconnect-wait and original-deadline recovery rules. All saved identities, roles, history, and partial votes restore through the original credentials.

If no valid fallback/candidate can be admitted, the mission stays in `preparing`, with safe public `generation_status=unavailable`; the slot is not advanced. The UI offers **Retry preparation** to the host when every seat is connected. `POST /api/missions/{token}/retry-preparation` is host-authorized, requires that error state, and creates a fresh bounded attempt. This is an explicit recovery action, not automatic retry/regeneration of an accepted crisis. A still-invalid catalog/state needs operator repair; repeatedly retrying cannot fix bad authoritative content. Storage failures retain the pending attempt/candidate and use the existing retry-on-storage-recovery behavior.

## Identity, immutability and persistence

The Milestone 9.1 strict validator still owns acceptance: canonical A/B/C identifiers, complete four-role intelligence, recommendation, complete strict integer metric proposals in [-24, 18], bounded meaningful text, strategic structural checks, exact permitted continuity references, and forbidden extra state fields. Provider identity is discarded. Canonical `generated-<SHA-256>` identity remains content-derived. Exact normalized content already used in a mission fails and falls back.

`CrisisAdmission` adds a frozen internal record containing source, canonical accepted crisis JSON, and SHA-256 of those bytes. The complete canonical `Crisis` is also appended to the existing sequence, which remains the engine's source for voting/consequences. No effects are modified by integration. The admission hash is separate from the foundation's fingerprint (which also includes continuity references) and from the existing resolved-result hash. Continuity references are validated at generation time; their canonical content-derived effect on identity is retained, but a separate reference ledger is not added.

Before saving generated state, validation checks sequence/admission agreement, content hashes, uniqueness, target slot/ledger/phase consistency, and completion length. Saved admissions are append-only: changing both a snapshot and its checksum still cannot replace an existing admission. Mode cannot change. Original resolution records and their hashes retain their existing append-only checks; the `CrisisResult` schema is unchanged, including the legacy `authored_deltas` field name for accepted generated effects.

SQLite **schema 2 / aggregate format 1** remain unchanged. `mode`, `generation`, and `admissions` are additive aggregate fields, using the established campaign-extension pattern. Old payloads lacking these fields load with authored/none/empty defaults. The existing exact-field, checksum, migration, catalog, roles, history, deadline and metric checks remain in place; generated content gets appropriate partial-sequence/admission checks rather than being required to exist in the authored catalog. Authored fallback entries still require valid catalog stages/prerequisites. A legacy fixture with all new fields removed restores with identical result hashes.

Newly saved aggregates require this application version. Do not downgrade the database to an older reader that rejects these added fields. Use the existing SQLite backup procedure before deployment; no user database was deleted or overwritten for testing.

## Context and privacy

The existing allowlist context builder now reads the pending target slot when present. Initial request: crisis 1, metrics 70, no decisions/used IDs. Later requests: committed current metrics, last three executed public decisions and selected consequences (600-character cap), and used scenario IDs. All context containers remain frozen copies.

Private chat, callsigns, identities/connection IDs, credentials, invite token/campaign seed, role assignments, role reports, uncommitted votes, tallies, timers, result IDs, and future content remain excluded. Provider instructions explicitly ask for varied civic themes tied to metric strengths/weaknesses and completed consequences, forbid invented/contradictory history, and identify crisis 10 as final. These instructions do not authorize state changes. The model cannot change mission length, add metrics, execute tools, or define voting rules.

Public projection adds only selected `mode` and safe `generation_status` (`preparing`, `unavailable`, or null), plus the preparation phase. During preparation, no candidate/private content is sent. After admission, the original public crisis allowlist and viewer-role private projection are reused. Unexecuted metric consequences remain private server content. Context/prompts/provider configuration, attempt IDs, admissions, raw failures and source diagnostics never appear in snapshots. Executed history remains public as before.

## Frontend scope

The existing entry form gains a labeled, touch-friendly full-width select. **Authored Mission** is the default. **AI-Generated Mission** is disabled unless the safe capability lookup explicitly returns true. Failed capability lookup fails closed; invited players do not see a mode selector or send a mode override.

Preparation uses the existing operations layout, an accessible polite status announcement, and a guarded retry button for recoverable errors. Current voting/chat/presence/review interfaces and responsive breakpoints are unchanged. The production reconnect controller already accepts authoritative phase snapshots; new tests cover preparation → reconnect → ready without sending progression intents.

## Verification

All commands run from `/home/attila_unix/projects/consensus-engine`. Tests use temporary databases and fake providers; no normal suite requires model credentials. Backend tests add **23** cases and frontend tests add **5** cases.

| Command/check | Result |
| --- | --- |
| `timeout 100 .venv/bin/python -m pytest backend/tests -q -x -o faulthandler_timeout=35` (initial compatibility pass) | 432 existing tests passed, 1 existing warning, 11.58 s |
| `timeout 90 .venv/bin/python -m pytest backend/tests/test_live_generation.py -q -o faulthandler_timeout=25` | 23 passed, 1 existing warning, 1.25 s |
| `timeout 120 .venv/bin/python -m pytest backend/tests -q -o faulthandler_timeout=40` (full successful run) | **455 passed**, 1 existing warning, 12.44 s |
| `timeout 90 .venv/bin/python -m pytest backend/tests/test_live_generation.py backend/tests/test_generation_contract.py backend/tests/test_generation_provider.py backend/tests/test_generation_integration.py -q -o faulthandler_timeout=30` (after final task cleanup) | **193 passed**, 1 existing warning, 2.38 s |
| `npm --prefix frontend test` | 98 passed, 4 capture-dependent skipped, 0 failed |
| `MISSION_RESTART_FILE=/tmp/ce-m7-restart.json MISSION_REVIEW_FILE=/tmp/ce-m6-live.json CHAT_ACCEPTANCE_FILE=/tmp/ce-chat-5-1.json EXPANSION_REVIEW_FILE=/tmp/ce-m8-live.json npm --prefix frontend test` | **102 passed**, 0 skipped/failed |
| `npm --prefix frontend run typecheck` | Passed |
| `CONSENSUS_LLM_API_KEY=GENERATION-9-2-BUILD-CANARY npm --prefix frontend run build` | Final TypeScript and Vite build passed; 43 modules; JS 264.96 kB, CSS 12.61 kB |
| `.venv/bin/python -m pip check` | No broken requirements found |
| `npm --prefix frontend ls --depth=0` | All declared dependencies resolved; no changes needed |
| `.venv/bin/python -m pip wheel --no-deps ./backend -w /tmp/ce-9-2-wheel` | Wheel built successfully |
| `timeout 90 .venv/bin/python backend/tests/smoke_live_generation.py` | **Passed** real three-client ten-crisis generated mission, two fallbacks, voting reconnect, pending process-kill/restart, one inference attempt per slot, consistent state/history and ten resolution records |
| `timeout 90 .venv/bin/python backend/tests/smoke_milestone8.py` | **Passed** authored ten-crisis game, two follow-ups, privacy, exactly-once continuation, restart; score 70.75 in this seeded run |
| `timeout 90 node --experimental-websocket frontend/tests/smokeReconnection.mjs` | **Passed** original production controller/Vite interruption, restart, presence, original deadlines, privacy and exactly-once resolution |
| `git diff --check` | Passed |

Additional explicit Python checks scanned `frontend/dist` for **11** secret/configuration/internal-diagnostic canaries and all **120** authored role reports (raw and JSON-escaped): absent. Wheel inspection confirmed eight generation modules and 32 authored content JSON files. Unpacked-wheel execution imported packaged `app.generation.live`, accepted a fake CLI proposal, served the safe default capability response, and created an ordinary mission through HTTP. The disposable `backend/build` from packaging was removed.

The generated network smoke uses an injected deterministic fixture provider, actual Uvicorn/SQLite/HTTP/WebSocket processes, a controlled file clock, and three clients. Crisis 3 intentionally fails schema validation; crisis 4 stalls and is recovered via authored fallback after a process kill. The test journals only synthetic allowlist requests and verifies ten calls numbered 1–10, empty initial history, no private chat, ten unique saved crises, exactly two fallback admissions, and ten immutable resolution records. It does not exercise a model.

One intermediate full-suite attempt stalled in the existing `test_campaign.py` TestClient reconnect helper (`restore` → `states`), as intermittently observed before this milestone; its 120-second bound terminated it with exit 124. A subsequent complete run passed all 455 tests. The retained diagnostic log is `/tmp/ce-9-2-backend.log`; the successful run is `/tmp/ce-9-2-backend-final.log`. Initial local test development also caught a fixture unpacking error, a typed-delta fixture error, and the missing exhaustive UI phase label; all were corrected before successful results above. No production workaround for the existing TestClient timing issue was introduced. The remaining warning is the pre-existing Starlette TestClient HTTPX deprecation.

Other local logs: `/tmp/ce-9-2-live-tests.log`, `ce-9-2-generation-final.log`, `ce-9-2-ui.log`, `ce-9-2-ui-acceptance.log`, `ce-9-2-typecheck.log`, `ce-9-2-build.log`, `ce-9-2-smoke-live.log`, `ce-9-2-smoke-authored.log`, `ce-9-2-reconnection.log`, and `ce-9-2-wheel.log` (all under `/tmp`). Captured frontend evidence includes the freshly rerun authored smoke and prior restart/review/chat captures.

The optional provider readiness check inspected only enabled/completeness booleans, withholding all setting values. It reported **false**. No real model request was made. Mock/fixture success is not a real-provider compatibility claim; latency, provider schema support, cost, creative quality, and actual contextual continuity still need opt-in model acceptance.

## Starting and manual multiplayer acceptance

Keep provider credentials in the backend process environment. Export your chosen full endpoint and model; export a key securely when required, or use explicit unauthenticated loopback configuration. Set `CONSENSUS_LLM_ENABLED=true`, then restart the backend so settings are re-read. Existing local databases remain enabled.

```sh
# From the repository root, with your backend environment already configured:
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
npm --prefix frontend run dev
```

For deployment retain one worker and a stable private database path, for example the existing documented `CONSENSUS_DB_PATH` setup. A reload during preparation intentionally chooses saved authored fallback. Authored missions continue without any LLM variables.

Manual browser/device checklist (not claimed completed):

- With generation disabled, create an authored mission and verify the generated option is unavailable; old create clients still work.
- With a configured provider enabled, create an AI-generated mission and join from three independent browser identities/devices.
- Start with all seats connected. Observe the inline preparing announcement, then identical public crisis/choices with only each player's assigned intelligence.
- Discuss/vote, verify consequences/history agree, and continue. Confirm later scenarios reflect completed decisions and current metrics without referring to private chat.
- Disconnect during preparation, reconnect using the same saved session, and verify there is one admitted crisis. Try discussion while a seat is absent; it must remain blocked.
- Refresh/reconnect during voting; confirm same crisis, role reports, option IDs, deadline and saved vote. Exercise an initial and final tie.
- Restart during preparation and during an accepted vote. The former should become authored fallback; the latter should preserve the accepted content and existing recovery semantics.
- Force a short timeout/unavailable provider in a development environment. Verify authored fallback proceeds and no provider error/configuration is shown.
- Complete ten crises and review all history, metrics and score. Also exercise an early defeat. Verify preparing/error status and select controls at phone width with keyboard/screen reader status announcements.

## Limits and readiness

All feasible automated and real-network fake-provider acceptance passed. Actual browser/mobile/screen-reader use and real-model narrative quality remain manual checks. Structural validation and exact continuity-reference validation cannot prove that free prose is factually consistent with history or strategically interesting. Semantic repetition can survive content-bound ID checks; no new balancing/quality algorithm was introduced.

The context intentionally includes only three recent executed decisions, 600 characters per selected consequence and used IDs, not a complete world model. Generation runs only at admission boundaries, without prefetch/streaming UI. A user can explicitly retry a failed preparation, but automatic provider retries and distributed worker ownership are outside scope. Persistence outages still require storage recovery. There is no new mission-abandonment endpoint; existing terminal states and shutdown invalidate outstanding admissions.

Milestone 9.2 is ready for local review/commit with real-provider and interactive device acceptance explicitly unverified. No authored scenario, vote rule, timing duration, metric application/clamping rule, role assignment, legacy result record, chat subsystem, or review design was changed.

## Exact file inventory

Modified:

- `README.md` — current live-mode setup, recovery policy and smoke commands.
- `backend/app/domain.py` — creation mode, preparing phase, attempt/admission models and aggregate fields.
- `backend/app/generation/context.py` — authoritative pending target number.
- `backend/app/generation/provider.py` — explicit context/variety/final-crisis narrative instructions.
- `backend/app/generation/service.py` — update outdated standalone-only docstring; acceptance/fallback logic unchanged.
- `backend/app/main.py` — settings/readiness, safe capability endpoint, mode creation, task lifecycle and guarded retry route.
- `backend/app/missions.py` — centralized preparation/admission/recovery, fixed generated mission length, mode validation and safe projection.
- `backend/app/persistence.py` — additive legacy defaults, generated sequence/admission checks and append-only guards.
- `backend/generation.env.example` — startup/live-mode documentation.
- `frontend/src/App.tsx` — capabilities, selected mode, preparing/retry UI.
- `frontend/src/Gameplay.tsx` — preparing phase label.
- `frontend/src/MissionEntryForm.tsx` — accessible mode select and availability copy.
- `frontend/src/missionEntry.ts` — safe capability lookup and creation-only mode intent.
- `frontend/src/styles.css` — responsive touch-friendly select.
- `frontend/src/types.ts` — optional compatible mode/status fields and preparation phase.
- `frontend/tests/gameplay.test.tsx` — creation/defaults/availability/intents/preparation/retry tests.
- `frontend/tests/missionConnection.test.ts` — reconnect during preparation through ready state.

Added:

- `backend/app/generation/live.py` — asynchronous single-owner inference/admission coordinator.
- `backend/tests/test_live_generation.py` — 23 deterministic lifecycle, privacy, race, fallback, recovery and compatibility cases.
- `backend/tests/smoke_live_generation.py` — real three-client/process-restart fake-provider campaign acceptance.
- `docs/MILESTONE_9_2_LIVE_GENERATION.md` — this report.
