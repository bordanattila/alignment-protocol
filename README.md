# Consensus Engine

*Intelligence proposes. Humanity decides.*

Milestone 8: a React/TypeScript cooperative game with a FastAPI-authoritative 2–4-player mission, timed discussion/chat, hidden plurality voting, authored consequences, and configured crisis progression. Create a mission, share its invite URL, and join with a callsign. Separate browser profiles receive separate seats; refreshes and additional tabs reuse the saved seat credential.

## Development

Requires Python 3.12+ and Node 20.19+. Run from the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e './backend[dev]'
.venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --ws-max-size 4096
```

In another terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. Vite proxies HTTP and WebSockets to FastAPI. To try another device on the same network, open the computer's LAN address on port 5173 and create/copy the invite there. A localhost invite only works on the host computer. If clipboard access is unavailable, copy the displayed invite field manually.

## Verification

From the repository root:

```sh
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python -m pip check
cd frontend
npm test
npm run typecheck
npm run build
```

The backend suite covers membership, validation, capacity, credential privacy, WebSocket synchronization, refresh/reconnect identity, malformed messages, multiple tabs, and failed-send cleanup. TypeScript uses strict checking; rendered React tests use the existing esbuild toolchain and Node test runner. No separate linter is configured.

## Serve the built app

```sh
cd frontend
npm ci
npm run build
cd ..
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --ws-max-size 4096
```

FastAPI serves `frontend/dist` if it exists at startup. Open http://localhost:8000. Use one worker: SQLite is durable authority and one process owns its runtime cache/sockets. Missions survive restart when the same database is retained. Invite URLs use `/?mission=<token>`.

## Architecture and current limits

- `backend/app/domain.py`: typed internal state and crisis schema foundations.
- `backend/app/missions.py`: membership, seat authorization, and explicit public projections.
- `backend/app/connections.py`: socket membership, presence, and bounded send/close cleanup.
- `backend/app/main.py`: HTTP/WebSocket transport and static frontend serving. A lock serializes membership operations and snapshots.
- `frontend/src/`: React UI, per-mission credentials in localStorage, and WebSocket retry.

The invite token permits joining; a separate credential authorizes a seat. Credentials travel in the first WebSocket frame rather than the URL and are excluded from public snapshots. Disconnected lobby seats remain reserved indefinitely. There is no host transfer, mission expiry or public deployment abuse limiting yet. Socket sends run outside the state lock, with bounded waits; slow clients can still delay publications.

The host starts once 2–4 occupied seats are connected. The backend assigns all four roles once, loads the packaged scripted sequence, and enters `briefing`. Begin discussion starts 60 seconds of chat, followed by 30-second hidden voting. A tied highest submitted count opens a 20-second chat/Consensus Window and fresh 30-second final vote. Plurality, final AI tie-break, and explicitly labeled no-vote fallback are server-owned. Private intelligence and own-vote state are projected per seat.

Every decision applies its authored consequence exactly once. The durable `decision_locked` result shows its narrative, before/after metrics, applied changes, and resolution method. The host selects Next crisis after review; the result ID makes retries safe. All occupied seats must reconnect before advancing. Seats/roles/metrics persist; new crises start with fresh briefing and vote state. Zero metrics immediately cause collapse. After the final configured result, Finish mission enters completion and computes the server-side average Consensus Score.

`backend/app/content/expansion/catalog.json` configures the 30-crisis library and escalation stages. Standard missions select ten crises, beginning with the unchanged **Grid Under Pressure** and ending with **The Last Coordination**. The original `sequence.json` remains the fixed legacy/reference campaign. Schema and catalog validation reject malformed, missing, duplicate, or unreachable records. Only the selected public result's consequence/deltas are exposed; future content and other roles' intelligence remain server-side. Chat remains mission-wide, bounded to 100 messages, with each message labeled by its originating crisis.

Production state persists in SQLite; live sockets and presence are reconstructed on restart. Five-minute seat removal/role redistribution, weakest-metric finales, QR joining, and replay controls remain future work. Physical browser/device and mobile acceptance remain manual. The seeded ten-crisis campaign selects from 30 authored crises; this is not the complete v0.1 feature set.

Milestone 4 checks and automated live fixture acceptance:

```sh
.venv/bin/python backend/tests/smoke_milestone4.py
```

This test starts a temporary fixture server with a two-crisis sequence and 10x injected clock. It does not change the production sequence or duration constants.

See [Milestone 4 verification](docs/MILESTONE_4_VERIFICATION.md) for current behavior, exact commands/results, architecture decisions, and manual-review limits.

See [Milestone 2 verification](docs/MILESTONE_2_VERIFICATION.md) for implementation decisions, commands, results, and remaining checks.

## Ten-crisis campaign verification

```sh
.venv/bin/python -m app.campaign_analysis
.venv/bin/python backend/tests/smoke_milestone5.py
.venv/bin/python backend/tests/smoke_milestone3.py
```

The offline analysis enumerates all 59,049 decision paths using production clamping and collapse rules. The Milestone 5 smoke uses three real WebSocket clients, production content and a 20x injected clock; the Milestone 3 smoke retains actual 60/20/30-second timing. Neither changes production duration constants.

See [Milestone 5 verification](docs/MILESTONE_5_VERIFICATION.md) for content design, balance findings, exact validation results, playthrough evidence, changed files, and browser/mobile acceptance limits.

## Durable storage and restart recovery

The production entry point `app.main:app` stores missions in `data/consensus-engine.sqlite3` relative to the working directory. Use a stable absolute path to retain the same database across restarts:

```sh
CONSENSUS_DB_PATH=/absolute/private/path/consensus-engine.sqlite3 .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --ws-max-size 4096
```

The directory is created if needed; SQLite/WAL files contain private game content and credential hashes and must remain private. One process per database is enforced by a POSIX ownership lock (Linux/WSL). Never delete the database to fix a recovery error; incompatible/corrupt records stop startup without discarding missions. Restore a consistent backup or repair offline. No automatic mission deletion is configured.

Active sessions recover into an explicit waiting state until all reserved seats reconnect. Original unexpired deadlines remain unchanged. Already-open expired voting resolves only its saved submissions; downtime counts toward its deadline. Expired discussion/Consensus Window transitions open the next mandatory voting phase only after all seats reconnect, with a fresh 30-second opportunity. A newly required Consensus Window waits for all seats before its 20 seconds begins. No old timer is reset. Finished reviews, metrics, roles and chat restore through the existing credentials.

Every accepted intent and publication revision commits before success/broadcast. Use SQLite's backup API for live backups, or stop the server cleanly before copying its database. Do not copy only the main database while WAL writes are active. See the [Milestone 7 report](docs/MILESTONE_7_VERIFICATION.md) for backup examples, schema/versioning, security, operational limits and exact test evidence.

Database schema version 2 automatically migrates both known version-1 resolution-index layouts, validating saved history before committing. Invalid layouts fail at startup. See the [Milestone 7.1 regression report](docs/MILESTONE_7_1_VERIFICATION.md) for the mission-creation fix and reload verification.

```sh
.venv/bin/python -m pytest backend/tests/test_persistence.py -q
.venv/bin/python backend/tests/smoke_milestone7.py
```

`create_app(database_path=...)` is the persistent application factory. Its omitted-path form and standalone MissionStore retain isolated in-memory behavior for existing tests/embedding; production should use `app.main:app` or supply an explicit database path. No database is opened merely by importing the module.


## Seeded campaigns and authored follow-ups

New missions created through the default application factory use the 30-crisis catalog. Every standard run has exactly ten crises: Grid Under Pressure, two more early crises, three middle crises, three late crises, then The Last Coordination. Decisions can qualify five authored follow-ups; otherwise independent fallback crises keep the run valid. Existing saved missions keep their original campaign. The fixed ten-entry loader remains an explicit legacy/reference fixture for regression tests and exhaustive analysis.

A new optional campaign aggregate stores the immutable seed (the mission invite token), full authored catalog snapshot and dependency metadata. Executed decisions remain the existing immutable result ledger. No SQL migration or result-hash rewrite is needed; old aggregates without campaign metadata load as legacy missions. Do not downgrade an active expanded database to an older application that cannot read this metadata.

Offline debugging and sampled balance checks:

```sh
.venv/bin/python -m app.expansion_analysis --seed debug-example
.venv/bin/python -m app.expansion_analysis --seed debug-example --choices BBBCCBCAAC
.venv/bin/python -m app.expansion_analysis --sample 100
.venv/bin/python backend/tests/smoke_milestone8.py
node --experimental-websocket frontend/tests/smokeReconnection.mjs
```

These tools simulate production rules offline; they do not change live missions. A seed plus the same choices reproduces scenario selection, consequences and final metrics. See [Milestone 8 gameplay expansion](docs/MILESTONE_8_GAMEPLAY_EXPANSION.md) for inventory, prerequisites, compatibility, exact validation results and manual acceptance.

## Standalone scenario generation foundation

Milestone 9.1 adds a disabled-by-default proposal pipeline and standalone developer harness. Milestone 9.2 connects it to explicitly selected generated missions; authored missions retain their existing selector and remain the default.

```sh
.venv/bin/python -m app.generation.cli --mode disabled
.venv/bin/python -m app.generation.cli --mode fake
.venv/bin/python -m app.generation.cli --mode failure
.venv/bin/python -m app.generation.cli --schema
.venv/bin/python -m pytest backend/tests/test_generation_contract.py backend/tests/test_generation_provider.py backend/tests/test_generation_integration.py -q
```

These commands need no credentials. Optional remote inference requires explicit `--mode live`, `CONSENSUS_LLM_ENABLED=true`, and operator-supplied endpoint/model settings. Keep credentials in the backend environment; [generation.env.example](backend/generation.env.example) lists settings without loading them automatically. See [Milestone 9.1 foundation](docs/MILESTONE_9_1_LLM_FOUNDATION.md) for the contract, privacy boundary, fallback behavior, exact verification results, and provider compatibility limits.

## Optional live generated missions

Export `CONSENSUS_LLM_ENABLED=true` and your operator-selected full endpoint, model, and required credential into the backend environment before starting `app.main:app`. Local unauthenticated loopback servers may use `CONSENSUS_LLM_REQUIRE_API_KEY=false`. No provider values belong in the frontend environment.

The creation form defaults to **Authored Mission**. **AI-Generated Mission** becomes available when `/api/capabilities` reports backend readiness. Generated missions prepare one validated crisis at a time from committed public decisions and current metrics. Provider failures use the existing deterministic authored selector. Accepted content is persisted before briefing; reconnects never regenerate it. Restarting an interrupted preparation admits authored fallback instead of repeating inference. Play still requires every reserved seat to reconnect before starting discussion or advancing a result.

```sh
.venv/bin/python -m pytest backend/tests/test_live_generation.py -q
.venv/bin/python backend/tests/smoke_live_generation.py
```

The smoke uses a fake provider, three real WebSocket clients, a temporary database, and a killed/restarted backend. It needs no model or credential. See [Milestone 9.2 live generation](docs/MILESTONE_9_2_LIVE_GENERATION.md) for concurrency, persistence, recovery policy, configuration, verification and manual acceptance.

If generated missions keep serving authored content, inspect the backend `generation_result` / `crisis_admitted` records for source, sanitized failure, HTTP status and duration. Capability availability checks configuration completeness; it does not verify API billing or model access. See the [live generation investigation](docs/MILESTONE_9_2_LIVE_GENERATION_INVESTIGATION.md) for the verified model/quota failures and an explicitly opt-in, two-request provider smoke. Fix API access/quota before retrying; accepted crises are never regenerated.

New preparation outcomes also persist five sanitized fields in the existing private mission aggregate: crisis number, source, category, duration and provider HTTP status. They are excluded from gameplay snapshots. A local read-only developer command inspects them without acquiring the backend ownership lock or contacting a provider:

```sh
.venv/bin/python -m app.generation.inspect_diagnostics --database backend/data/consensus-engine.sqlite3 --mission-index 1
```

Use your actual database path; `1` selects the most recently created mission, `2` the previous mission. Old missions without records return `[]`; historical causes are not inferred. No SQL migration is needed. See [Crisis 2 fallback diagnostics](docs/MILESTONE_9_2_CRISIS_2_DIAGNOSTICS.md) for the investigation, category semantics, compatibility and offline verification.

## Adaptive narrative and generated mission endings

Generated crises also receive bounded narrative memory derived from executed public decisions: recent outcomes and actual metric changes, up to two significant earlier decisions, established public situations and recorded metric pressures. Explicit references remain strictly validated; independent crises are still allowed. This does not add a second mission history or change consequences.

New generated missions reaching victory or defeat can receive a three-section AI interpretation of the full mission. Completion is immediate. The existing deterministic ending remains visible while the one bounded asynchronous request runs and whenever generation fails. Accepted stories persist once; refresh/reconnect never regenerates them. Restart during a pending request selects deterministic fallback. Previously completed missions and authored missions keep their existing ending behavior.

The review labels generated prose as interpretation and renders statistics and expandable recorded sources from authoritative records. It does not treat free-form prose as verified game facts. The existing provider settings and adapter serve both operations; no extra service or credential is required. A generated mission may make one additional provider request after its outcome is finalized when generation is enabled.

Endgame diagnostics use the same local inspection mechanism:

```sh
.venv/bin/python -m app.generation.inspect_diagnostics --database backend/data/consensus-engine.sqlite3 --operation endgame
.venv/bin/python -m pytest backend/tests/test_adaptive_narrative.py -q
.venv/bin/python backend/tests/smoke_adaptive_narrative.py
```

The smoke uses fake inference, temporary SQLite databases and three real WebSocket clients. It exercises a ten-crisis mixed-source campaign, pending-story reconnect, accepted-story restart, interrupted-story restart fallback and provider failure. See [Milestone 9.3](docs/MILESTONE_9_3_ADAPTIVE_NARRATIVE.md) for contracts, compatibility, exact results, limitations and manual acceptance.

## Offline LLM evaluation

The evaluation command makes no network requests, reads no API credentials, and has no live-provider mode:

```sh
.venv/bin/python -m app.generation.evaluation --output /tmp/consensus-evaluation.json --review-template /tmp/consensus-review.json
```

Add `--continuity-cases` for ten Stage B contrasts, including supported links, independent events and valid citations attached to superficial/contradictory prose. Structural acceptance remains separate from human semantic review. The default 29-case baseline is unchanged. See [Stage B continuity and audits](docs/MILESTONE_9_5_STAGE_B_CONTINUITY.md) for the prompt correction, review guide, latency evidence and recommendation visibility findings.

It exercises six synthetic histories and production crisis/endgame validation with success, malformed output, unsupported references, exact repetition, failures, timeouts and disabled cases. Results clearly label scripted timings and token counts as synthetic. Human scores remain blank; supported references are measured separately from meaningful narrative continuity.

New private diagnostics optionally include typed stage timings, reported token usage, configured model and reference counts. Legacy diagnostics remain readable; unknown measurements are never backfilled. To summarize an explicitly selected existing mission read-only:

```sh
.venv/bin/python -m app.generation.evaluation --database /absolute/private/mission.sqlite3 --mission-index 1 --output /tmp/mission-evaluation.json
```

Cost estimates require an operator-supplied pricing JSON mapping model names to `input_per_million` and `output_per_million`. Add `--pricing /path/to/pricing.json --missions 3`. No prices are assumed, and missing usage stays unknown even when authored fallback was used. Production records summarize final outcomes per crisis, not every historical retry. See [Milestone 9.4](docs/MILESTONE_9_4_LLM_EVALUATION.md) for rate denominators, the rubric, baseline evidence, cost assumptions and the unexecuted six-request real-provider protocol.
