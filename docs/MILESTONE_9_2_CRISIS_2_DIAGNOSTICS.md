# Milestone 9.2 — Crisis 2 fallback diagnostics

Implemented locally on 2026-10-28. No paid requests, commits, tags or pushes.

## Verified findings

The affected mission in `backend/data/consensus-engine.sqlite3` persists `mode: generated` and admission sources `generated → authored_fallback → generated`. It has reached Crisis 3. Crisis 2 was therefore an admitted authored fallback, not a frontend mode/display substitution.

Both the running Uvicorn reload supervisor and worker were configured with generation enabled, model `gpt-6-luna`, timeout `60.0` seconds and `json_schema` output. Configuration was inspected using a whitelist; credentials and complete environment values were not printed. No provider request was made to check access.

The saved aggregate contains no historical generation diagnostic records. No usable Crisis 2 generation log was recoverable from the available terminal output. Existing admissions persist the accepted source and immutable scenario, but not the rejection reason. **The exact historical cause cannot be reconstructed.** There is no evidence here to select timeout, provider error, malformed response, continuity rejection or a lifecycle interruption. A current configuration check also cannot prove which configuration a historical request used.

The lifecycle captures authoritative context and the deterministic fallback selector under the state lock, performs inference outside the lock, and admits under the lock only if the attempt still owns the pending target. Repeated launch/progression calls share one task per attempt. A transient admission-write failure reuses the cached outcome. An explicit host retry creates a new attempt; restart recovery admits fallback without repeating inference. These behaviors remain intact and are covered by regression tests and the ten-crisis network smoke.

## Persisted diagnostics

Each new completed preparation records exactly these fields in the existing private mission JSON aggregate:

| Field | Meaning |
| --- | --- |
| `crisis_number` | Authoritative target, 1–10 |
| `source` | `generated`, `authored_fallback`, or null when no scenario was admitted |
| `category` | `success`, a bounded existing provider/validation failure category, or an explicit lifecycle category |
| `duration_seconds` | Finite nonnegative elapsed generation duration, rounded to milliseconds |
| `http_status` | Provider response status when known; otherwise null |

Existing categories distinguish authentication, quota/rate limiting, model access, unsupported format/provider schema/response, invalid JSON, scenario schema, continuity, refusal, timeout, unavailable provider, disabled/configuration and unexpected provider errors. Lifecycle categories are `internal_state`, `canceled` and `restart_recovery`.

`success` requires a generated admission. The fallback retains its original failure category and known provider HTTP status. Cancellation records a null source while leaving preparation pending. On restart, recovery replaces that pending record with `authored_fallback` / `restart_recovery`, status null and duration zero: no new inference occurred. Capture failures use `internal_state` with zero duration; no provider was called.

The record commits atomically with scenario admission or the existing recoverable error state. Finalized records cannot change or disappear. A pending error/cancellation record can be replaced by an explicit retry or recovery outcome for the same crisis number. Stale attempts cannot overwrite the current attempt or an admitted scenario. There are at most ten records; this is a per-crisis outcome summary, not an audit of every retry.

Prompts, provider response bodies, credentials, player details and private context are never added to these records. A typed model forbids extra fields and arbitrary category/status data. Gameplay projection remains an explicit allowlist and never includes diagnostics. No HTTP endpoint was added.

## Developer access

From the repository root, with local access to the private database:

```sh
.venv/bin/python -m app.generation.inspect_diagnostics \
  --database backend/data/consensus-engine.sqlite3 --mission-index 1
```

Use the actual configured database path. Index 1 means the most recently **created** mission, 2 the preceding one. The command uses SQLite `mode=ro`, works while the backend owns the database, and prints only the five-field records. Missing database/index or malformed metadata produces a fixed sanitized error without exception details. It makes no network requests. The existing affected mission returns `[]`; there is no historical backfill.

The database is still private application state: possession of its filesystem permissions grants access. The CLI is an operator mechanism, not a player-facing API.

## Compatibility and architecture

`Mission.generation_diagnostics` is an additive field with a default empty list. The aggregate compatibility loader explicitly allows that missing legacy field. SQLite schema version 2 and aggregate format 1 remain unchanged. No SQL migration, new table, history rewrite or external service is needed.

The existing failure enum moved unchanged to dependency-free `generation/errors.py`, allowing the domain diagnostic model to share the same bounded categories without a domain/contract circular import. `generation.contract` continues to re-export it for existing callers. Strict proposal/continuity validation and immutable scenario admission are unchanged.

The persistence layer validates diagnostic ordering, uniqueness and agreement with admissions/current preparation. It preserves finalized records alongside the existing immutable admission and result guards. Voting, timers, consequences and client code are unchanged.

## Duplicate recommendation correction

`cooling-access.json` contained the recommendation sentence in its authored briefing. The frontend correctly displays a separate recommendation from the scenario's recommended choice. The duplication originated in content.

The identical pattern existed in 19 other expansion briefings. All 20 had only the appended `AI recommendation: … This prioritizes … under the current constraints.` suffix removed. A parsed comparison against the repository baseline confirmed every other field unchanged: situations, options, IDs, dependency metadata, intelligence, numeric effects and result text.

Previously accepted/saved scenarios use their own full snapshots. They retain their original briefing, including any old duplicate, so content and finalized result hashes are never rewritten. New campaign snapshots receive the corrected source text. A dedicated regression test restores an old cooling briefing and verifies its result hash remains intact.

## Files changed by this task

- `backend/app/domain.py`: typed bounded private diagnostic list.
- `backend/app/generation/errors.py`, `contract.py`: unchanged shared failure enum relocated/re-exported.
- `backend/app/generation/live.py`: record normal, error and cancellation outcomes with existing attempt guards.
- `backend/app/missions.py`: centralized recording, admission/error integration, restart recovery and cancellation intents.
- `backend/app/persistence.py`: legacy default, metadata invariants and finalized-record immutability.
- `backend/app/generation/inspect_diagnostics.py`: local read-only inspection CLI.
- `backend/app/content/expansion/*.json`: the 20 briefing-only suffix removals.
- `backend/tests/test_durable_generation_diagnostics.py`: 18 cases including parametrized outcomes, provider status sanitization, durable restart, cancellation/recovery, inference deduplication, stale outcomes, privacy, legacy aggregates, immutable metadata, CLI execution and content compatibility.
- `backend/tests/test_live_generation.py`: an existing mode-corruption fixture also clears the newly added generated metadata, preserving the intended immutable-mode assertion.
- `backend/tests/smoke_live_generation.py`: checks ten durable diagnostic outcomes, schema-fallback/restart categories and absence from real client frames.
- `README.md` and this report: developer instructions and verified limitations.

Pre-existing uncommitted provider/service diagnostics, continuity improvements, tests and earlier reports were preserved. They are included in the verification suite but are not new fixes for this historical incident.

## Verification commands and results

No verification command below contacts a real inference provider. HTTP/provider fixtures use mock transports or injected fake providers; network smoke tests run temporary local backend processes.

```sh
timeout 120 .venv/bin/python -m pytest backend/tests -q -x -o faulthandler_timeout=40
```

517 passed, one existing Starlette/httpx TestClient deprecation warning, 14.02 seconds. The focused diagnostics file was subsequently rerun after adding a subprocess CLI assertion: 18 passed in 1.03 seconds. An initial targeted run exposed a legacy corruption-test fixture that needed to clear the new generated field; that fixture was corrected and the affected tests passed.

```sh
timeout 90 .venv/bin/python backend/tests/smoke_live_generation.py
timeout 90 .venv/bin/python backend/tests/smoke_milestone8.py
timeout 90 node --experimental-websocket frontend/tests/smokeReconnection.mjs
```

Passed: generated ten-crisis run with three WebSocket clients, exactly one request per slot, validation fallback, killed-process fallback and voting reconnect; authored ten-crisis run with saved-history/privacy checks; automatic reconnect through Vite after individual interruption and backend restart. The generated smoke was rerun after adding explicit durable-record/category assertions.

```sh
npm --prefix frontend test
MISSION_RESTART_FILE=/tmp/ce-m7-restart.json \
MISSION_REVIEW_FILE=/tmp/ce-m6-live.json \
CHAT_ACCEPTANCE_FILE=/tmp/ce-chat-5-1.json \
EXPANSION_REVIEW_FILE=/tmp/ce-m8-live.json npm --prefix frontend test
npm --prefix frontend run build
.venv/bin/python -m pip check
npm --prefix frontend ls --depth=0
git diff --check
```

Default frontend run: 98 passed, four capture-dependent tests skipped. Capture-enabled run: 102 passed, zero skips/failures. Build includes `tsc --noEmit`; TypeScript and Vite production build passed. Python dependency check found no broken requirements; frontend dependency tree passed. Whitespace check passed. Read-only inspection against the affected database returned `[]`, consistent with its legacy metadata. Parsed authored-content comparison confirmed exactly 20 briefing edits and no other content-field differences.

## Remaining limitations

The historical Crisis 2 cause remains unknown; this work makes future committed outcomes diagnosable. No real-provider success or failure was tested in this investigation. A hard kill before diagnostic commit can only be attributed to restart recovery afterward. If the database cannot write, no durable outcome can be promised until storage recovers; the existing in-process cached outcome avoids repeating inference. Explicit retries retain the latest outcome for that crisis rather than all attempts. Existing saved briefings intentionally retain old text.
