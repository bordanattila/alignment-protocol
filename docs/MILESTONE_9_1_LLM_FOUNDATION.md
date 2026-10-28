# Milestone 9.1 — LLM scenario generation foundation

Implemented locally on 2026-10-27. No commit, tag, or push. Live gameplay continues to use the Milestone 8 authored selector. No frontend code, route, database schema, result hashing, timers, or voting rules changed.

## Reconnaissance

The checkout was clean at `f83c2e0` (`Milestone 8 Gameplay Experience & Scenario Expansion`). Before editing, inspected `AGENTS.md`, the product specification, backend dependencies, routes, mission manager, persistence, domain models, authored campaign selection, content, expansion tests, README, and Milestone 8 report. A concise findings/integration summary was provided before editing.

- `domain.Crisis`, `Choice`, and `MetricDeltas` are the canonical content models. A crisis already includes a recommendation and four role reports. `Scenario` adds authored stage/category/prerequisite metadata; it is not a second crisis engine.
- The catalog contains 30 authored crises and five decision-dependent follow-ups. `campaign.select_crisis` uses seed, slot, catalog, and executed results for deterministic ten-crisis selection and follow-up briefing context.
- Existing consequences span **-24 through +18**. All authored options have gains and costs; no option is Pareto-dominated. Generated proposals retain these observed constraints. The existing AI recommendation remains authored data used by the existing tie/no-vote rules.
- Mission aggregates snapshot content, campaign metadata, metrics, and immutable resolved decisions. SQLite schema 2 / aggregate format 1 and existing result hashes need no change.
- No existing inference client or configuration framework exists. Server configuration uses environment variables, including `CONSENSUS_DB_PATH`. Generation follows that pattern in a standalone settings object.
- HTTPX was already an installed development dependency. It is now a runtime dependency because the optional adapter uses it. No SDK, orchestration framework, agent, vector store, or new service was added.

## Architecture

The new `app.generation` package is deliberately independent of `main`, transport handlers, and mission mutation. Nothing imports it into live progression. Even setting `CONSENSUS_LLM_ENABLED=true` does not alter live missions; an integration test explicitly checks this.

`GenerationRequest` contains contract version and a frozen, server-built context. The async `ScenarioProvider` protocol returns a `ProviderResponse` containing structured JSON text, or raises a typed `GenerationError`. Providers and HTTP clients can be injected. `GenerationService` applies the deadline, validation, normalization, identity assignment, immutable acceptance, sanitized failure handling, and explicit fallback. Only accepted snapshots leave this boundary as actionable content.

`ChatCompletionsProvider` posts to the exact configured endpoint with `model`, two messages, `stream=false`, and a structured `response_format`. It uses HTTPX asynchronously, disables redirects, and its owned client ignores environment proxy settings. It never requests tools or follows tool calls. The default format is strict `json_schema`; an operator may explicitly select `json_object` for a compatible endpoint. Both pass the same backend validator. There is no automatic format downgrade, retry, or regeneration.

The wire format was checked against the [official structured outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs). This is protocol research, not proof that any particular commercial or local model supports this schema. No actual model was exercised.

## Server-only configuration

Reference file: `backend/generation.env.example`. No automatic `.env` loader was introduced. Export selected values into the backend/developer process; never put provider credentials in `VITE_` variables.

| Variable | Default | Meaning |
| --- | --- | --- |
| `CONSENSUS_LLM_ENABLED` | `false` | Explicitly enable inference for the standalone service/harness |
| `CONSENSUS_LLM_ENDPOINT` | unset | Full operator-selected chat-completions URL; no suffix is appended |
| `CONSENSUS_LLM_MODEL` | unset | Operator-selected model identifier |
| `CONSENSUS_LLM_API_KEY` | unset | Optional bearer credential, stored as `SecretStr`, excluded from representations |
| `CONSENSUS_LLM_REQUIRE_API_KEY` | `true` | Missing required credentials fail before network I/O; explicitly set false for unauthenticated local servers |
| `CONSENSUS_LLM_TIMEOUT_SECONDS` | `15` | Finite total operation deadline, greater than 0 and at most 120 seconds |
| `CONSENSUS_LLM_RESPONSE_FORMAT` | `json_schema` | `json_schema` or `json_object` |

Boolean values accept `true`/`false`, case-insensitively. Enabled HTTP generation requires an endpoint, model, and key when required. Empty optional values remain unset. Invalid configuration has a constant safe error message. Endpoint/model/key are excluded from settings representations. Keys never enter prompts. Remote URLs require HTTPS; plain HTTP is permitted only for localhost/loopback. URL credentials, queries, fragments, invalid ports, excessive lengths, and control characters are rejected. No provider URL, model, or credential default is built into runtime code.

## Contract and validation boundary

Version **`1.0`** proposal envelope:

```text
schema_version
crisis: canonical Crisis fields with stronger untrusted-input constraints
  id (optional untrusted label; ignored for authoritative identity)
  title, briefing, ai_recommendation_choice_id
  private_intelligence: infrastructure, community, economy, safety
  choices[3]: id, title, description, consequence, metric_deltas
    metric_deltas: infrastructure, public_trust, economy, safety
continuity_references: [{crisis_number, choice_id}] (optional; defaults empty)
```

`ProposedCrisis`, `ProposedChoice`, and `ProposedEffects` extend the existing canonical models. They do not introduce a parallel scenario engine. Accepted data is revalidated and exported as the existing `Crisis` type. Future selection metadata is not model-authored state.

| Text | Minimum characters | Maximum characters |
| --- | ---: | ---: |
| Crisis/choice title | 3 | 120 |
| Public briefing | 80 | 2,000 |
| Choice description | 20 | 1,000 |
| Narrative consequence | 30 | 1,200 |
| Each role report | 40 | 1,200 |

Validation trims narrative text, rejects non-narrative control characters, requires all four roles and all four effects, and checks the existing three-choice/recommendation invariants. Option IDs and recommendation are trimmed/uppercased to **A/B/C**; choices are sorted into canonical order. Duplicate/missing/unknown IDs, duplicate titles/descriptions, and identical role reports are rejected. Each option must contain gains and costs, with no Pareto-dominated option. Effects are strict integers in **[-24, 18]**; booleans, floats, strings, missing metrics, and larger effects fail.

Every proposal/object level forbids extra fields, including nested player, vote, timer, metric-state, role-assignment, connection, completion, and score fields. There is no Markdown/prose extraction, fence stripping, missing-field invention, or repair call. JSON duplicate keys and nonfinite numbers fail. Content is bounded to 64 KiB UTF-8; the outer provider response is bounded to 128 KiB. Unicode/recursion/shape errors become safe failure categories. Accepted content echoing the configured API key is rejected, including JSON-escaped echoes.

`--schema` emits the same Pydantic-derived contract in strict structured-output form: explicit four-role object, all properties required, and `additionalProperties=false`. Strict wire requests use `id="unassigned"` and an empty continuity array when absent. Backend acceptance also permits omitting those optional fields; it never trusts a provider label.

Continuity references can cite only exact `(crisis_number, choice_id)` pairs in the supplied authoritative history. Unknown, wrong-choice, and duplicate references fail as `invalid_continuity`; no history or prerequisite is fabricated. Empty references are valid. Free-text truthfulness is outside schema validation.

## Minimal generation context

`build_context(mission)` explicitly copies these fields:

- Current crisis number and four current metrics.
- Last three executed public decisions: crisis number/ID/title, executed choice ID/title, selected narrative consequence capped at 600 characters.
- Used scenario IDs from executed history plus the current selected crisis, capped by the ten-crisis campaign size.

It excludes callsigns, player/seat/connection IDs, invite token/campaign seed, credentials, roles, chat, private intelligence, raw votes/tallies, result IDs, timestamps/deadlines, the remaining catalog, and full mission serialization. Metrics/history/ID containers are frozen copies. Tests seed sensitive canaries into a real mission and check exclusion without mutating the mission. Context is internal backend data, not an API accepting arbitrary client context.

The crisis number describes the supplied mission's current slot; this helper does not advance it. Future integration must capture/build context for the intended selection boundary under the existing state lock, then release the lock before remote I/O.

## Identity and immutable acceptance

The backend discards provider identity and assigns `generated-` plus a full SHA-256 digest of normalized version, creative content, effects, and sorted validated continuity references. The same normalized content gets the same ID despite provider labels or option order. Content changes change identity. IDs already in the supplied used-ID set are rejected. This detects exact normalized duplicates, not semantically similar themes.

`AcceptedScenario` is a frozen snapshot holding canonical JSON and frozen continuity references. Each `to_crisis()` call produces a fresh canonical model; mutating an export cannot alter the accepted snapshot or its fingerprint. All three proposed consequences are captured together before any future round admission. No re-generation after votes is supported. This fingerprint is separate from the existing immutable result-ledger hash, which is unchanged.

Milestone 9.1 does not persist generated snapshots. Future admission must durably pin the accepted snapshot to the mission before briefing/votes and retain it across reconnect/restart. The standalone service cannot itself provide transactional admission or freshness checks against live state.

## Failure handling and authored fallback

Failure categories are `disabled`, `configuration`, `timeout`, `unavailable`, `authentication`, `rate_limited`, `unsupported_response`, `invalid_json`, `invalid_schema`, `invalid_continuity`, `refusal`, and `unexpected`.

HTTP 401/403 map to authentication, 408/504 to timeout, 429 to rate limiting, other 5xx to unavailable, and other non-200 statuses (including redirects) to unsupported response. Network errors are unavailable. Refusals, truncated/non-stop completions, tool/function calls, multiple completions, non-string content, malformed envelopes, and oversized responses fail closed. A total asynchronous deadline bounds slow streaming as well as connection/read operations. Caller cancellation propagates without invoking fallback.

The service logs only fixed categories, never exception text, traceback, provider body, URL/model/key, prompt, context, or private content. No player-facing error endpoint was added. Unexpected provider errors are sanitized before fallback.

`authored_selector(campaign, index, results)` deep-captures explicit authoritative catalog/seed/history and calls the unchanged Milestone 8 `select_crisis`. It validates catalog and target slot/history length. Follow-up qualification, briefing context, deterministic replay, and existing fallback rules are retained. The service requires an explicit fallback dependency; without one it returns `fallback_failure=missing_selector`, and invalid selector state returns `invalid_state`, with no actionable snapshot. It never invents a mission or replaces a live crisis. With valid state, disabled/unavailable/invalid generation returns the selected authored snapshot.

## Developer harness

Run from the repository root with the existing development environment:

```sh
.venv/bin/python -m app.generation.cli --mode disabled
.venv/bin/python -m app.generation.cli --mode fake
.venv/bin/python -m app.generation.cli --mode failure
.venv/bin/python -m app.generation.cli --schema
```

The default is `disabled`, even if the environment enabled inference. `fake` feeds a known authored payload through proposal validation and assigns a generated identity; it demonstrates plumbing, not creative generation. `failure` simulates unavailability and returns the deterministic authored Grid Under Pressure fallback. JSON output includes source, sanitized failure, accepted scenario/three effects, and fingerprint. Context is synthetic metrics 70 / crisis 1 / empty history; fallback uses an explicit synthetic seeded campaign. Nothing reads or writes the active mission database.

For optional real-provider testing, securely export operator-selected endpoint/model/credentials (or explicitly disable auth for a local server), set `CONSENSUS_LLM_ENABLED=true`, then run:

```sh
.venv/bin/python -m app.generation.cli --mode live
```

This command was **not run against a real model**. Model/provider support, latency, cost, refusal behavior, and narrative quality require separate opt-in acceptance. Do not paste keys into reports or shell history. Generated developer output includes its synthetic role reports and is intended only for local inspection.

## Verification commands and exact results

All commands below ran from the repository root unless otherwise noted. Logs/captures under `/tmp` are local disposable evidence, not committed fixtures. No active user database was opened by generation checks.

| Command | Result |
| --- | --- |
| `.venv/bin/python -m pytest backend/tests/test_generation_contract.py -q` (initial contract pass) | 99 passed |
| `.venv/bin/python -m pytest backend/tests/test_generation_contract.py backend/tests/test_generation_provider.py -q` (adapter pass) | 163 passed |
| `.venv/bin/python -m pytest backend/tests/test_generation_contract.py backend/tests/test_generation_provider.py backend/tests/test_generation_integration.py -q -o faulthandler_timeout=30` | **170 passed**, 1 existing Starlette warning, 1.25 s |
| `timeout 120 .venv/bin/python -m pytest backend/tests -q -o faulthandler_timeout=40` | **432 passed**, 1 existing Starlette warning, 11.46 s |
| `npm --prefix frontend test` | 93 passed, 4 capture-dependent skipped, 0 failed |
| `MISSION_RESTART_FILE=/tmp/ce-m7-restart.json MISSION_REVIEW_FILE=/tmp/ce-m6-live.json CHAT_ACCEPTANCE_FILE=/tmp/ce-chat-5-1.json EXPANSION_REVIEW_FILE=/tmp/ce-m8-live.json npm --prefix frontend test` | **97 passed**, 0 skipped/failed |
| `npm --prefix frontend run typecheck` | Passed |
| `CONSENSUS_LLM_API_KEY=GENERATION-BUILD-CANARY-ONLY npm --prefix frontend run build` | Passed TypeScript and Vite; 43 modules, JS 263.15 kB, CSS 12.41 kB |
| `.venv/bin/python -m pip check` | No broken requirements found |
| `npm --prefix frontend ls --depth=0` | Passed; all declared packages resolved |
| `.venv/bin/python -m pip wheel --no-deps ./backend -w /tmp/ce-9-1-wheel` | Built `consensus_engine-0.1.0-py3-none-any.whl` |
| `timeout 90 .venv/bin/python backend/tests/smoke_milestone8.py` | Passed ten real network crises, branch follow-up, final voting, shared history/metrics, private projection, exactly-once continuation, and backend restart; final score 68.0 |
| `timeout 90 node --experimental-websocket frontend/tests/smokeReconnection.mjs` | Passed individual interruption, backend restart recovery, production connection controllers through Vite, presence, deadlines, privacy, and exactly-once resolution |
| CLI disabled/fake/failure/schema commands above | Authored/disabled; generated/success; authored/unavailable; valid strict schema |
| `git diff --check` | Passed |

Additional explicit Python checks scanned `frontend/dist` for the synthetic build key, `CONSENSUS_LLM_`, generation fallback diagnostics, context canaries, and all **120** authored role reports (raw and JSON-escaped): absent. Wheel inspection confirmed seven generation modules, 32 content JSON files, and HTTPX as a runtime dependency. Unpacked-wheel execution imported only the packaged generation code and successfully accepted a fake proposal. The disposable `backend/build` created by wheel building was removed; existing egg metadata was retained.

Logs: `/tmp/ce-9-1-generation.log`, `ce-9-1-backend.log`, `ce-9-1-ui.log`, `ce-9-1-ui-acceptance.log`, `ce-9-1-build.log`, `ce-9-1-wheel.log`, `ce-9-1-smoke8.log`, and `ce-9-1-reconnection.log`. CLI outputs: `/tmp/ce-9-1-{disabled,fake,fallback,schema}.json`.

The 170 new tests cover configuration, optional local auth, strict formats, HTTP/error handling, event-loop-safe total timeout/cancellation, response bounds/refusal/tools, duplicate/nonfinite JSON, all text/effect boundaries, extra state fields at four nesting levels, canonical identity, continuity, context exclusions, snapshot alias protection, fallback/follow-up determinism, harness modes, and live application isolation. Existing regressions cover role privacy, plurality/ties/no-votes, timers, metrics/win/loss, history/result hashes, legacy migration/recovery, presence/reconnection, seeded selection, and summaries.

Verification levels are distinct:

1. Fake providers and HTTPX mock transports: validation and injected protocol/error coverage.
2. Actual loopback HTTP fixture server: exercised owned async HTTP client, request/response format, and unauthenticated local transport. It is not an LLM server.
3. Existing real multiplayer network smoke tests: gameplay/restart non-regression, without inference.
4. Actual local/commercial model: **not exercised; no real-provider compatibility claim**.

The only backend-suite warning is the installed Starlette TestClient deprecation concerning HTTPX; it predates this milestone. No dependency replacement was needed. The previously observed intermittent TestClient WebSocket hang did not occur in this full run. Network smokes use injected clocks and production controllers, not interactive phone/browser acceptance.

## Future Milestone 9.2 and limits

The safest integration point is the existing centralized next-crisis selection/admission boundary after the prior decision is immutable and all required continuation conditions are met, before publishing the next briefing. Capture context and authored selector under the mission lock, release it for inference, then re-acquire and verify revision/target slot/session status before accepting a result. Stale requests must be cancelled/discarded. Keep the validated authored result ready, persist the accepted complete crisis snapshot before publication, and use that same snapshot for all views, votes, resolution, and recovery. Never await remote inference while holding the game-state lock or regenerate after votes.

This milestone supplies those building blocks, without adding a live waiting phase, state revision guard, SQL snapshot storage for generated crises, retries, streaming UI, cache, or dynamic follow-up prerequisites. Provider-specific strict-schema support still needs real-model testing; explicit JSON-object mode retains backend validation. Shape/bounds/tradeoff checks cannot prove narrative truth, balanced strategy, privacy semantics inside model-created prose, or meaningful continuity. Recent context is intentionally limited to three decisions. No model may execute tools or modify authoritative state. Content-bound IDs do not detect semantic repeats. Effect limits and contract versions should evolve deliberately with balancing evidence.

## Exact changed-file inventory

Modified:

- `README.md` — standalone entry point and documentation link.
- `backend/pyproject.toml` — promote existing HTTPX dependency from dev to runtime.

Added:

- `backend/app/generation/__init__.py` — isolated package.
- `backend/app/generation/config.py` — secure environment settings.
- `backend/app/generation/contract.py` — versioned canonical-derived contract, strict parsing/validation, identity and accepted snapshot.
- `backend/app/generation/context.py` — authoritative allowlist projection.
- `backend/app/generation/provider.py` — async protocol and HTTP adapter.
- `backend/app/generation/service.py` — acceptance/failure boundary and explicit existing-selector fallback.
- `backend/app/generation/cli.py` — synthetic developer harness.
- `backend/generation.env.example` — server-only configuration reference without credentials.
- `backend/tests/test_generation_contract.py` — contract/privacy/identity/immutability tests.
- `backend/tests/test_generation_provider.py` — settings/HTTP/errors/deadline/local transport tests.
- `backend/tests/test_generation_integration.py` — harness, authored follow-up and unchanged live mission tests.
- `docs/MILESTONE_9_1_LLM_FOUNDATION.md` — this report.

Milestone 9.1 foundation is ready for local review and commit. Real-model acceptance remains explicitly unverified and live scenario integration is deferred to Milestone 9.2 as requested.
