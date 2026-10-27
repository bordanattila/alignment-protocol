# Milestone 7.1 — Mission creation 503 regression

## Demonstrated cause

Milestone 7 changed the resolution index from a `record` JSON column to a `record_hash` digest column without advancing SQLite `user_version=1` or migrating existing databases. This was a missing migration in the implementation.

The running development server used `/usr/bin/python3`, uvicorn `--reload`, working directory `backend`, no `CONSENSUS_DB_PATH`, and therefore `backend/data/consensus-engine.sqlite3`. Read-only inspection found version 1, the legacy `record` column, zero missions, permissions 0600, and `PRAGMA quick_check = ok`.

An empty missions table let startup recovery succeed without querying resolution rows. The first POST traversed the mission endpoint, `MissionStore.create`, the persistence wrapper, and `SQLiteMissions.save`. Its first SQL operation requested `record_hash`, raising `sqlite3.OperationalError: no such column: record_hash`.

The endpoint's only HTTP 503 path is the registered `PersistenceError` handler. SQLite save errors are deliberately wrapped in that safe exception; finalized-history integrity failures also use it. The response was:

```json
{"detail":"Mission storage is temporarily unavailable. Retry after reconnecting.","code":"storage_unavailable"}
```

Malformed requests remain 422; unauthorized session credentials remain 401. Ownership-lock, initialization, migration and recovery failures stop startup rather than serving a broken store. No evidence implicated permissions, SQLite contention, session identity, or the reload ownership lock.

## Safe reproduction

The existing database was opened read-only and copied using SQLite's backup API into a private temporary directory. The source was not deleted, replaced or used for diagnostic mission creation. Running the existing development entry point with `--reload` against that copy reproduced startup success followed by HTTP 503 and the missing-column operation. Evidence: `/tmp/ce-7-1-before-server.log` and `/tmp/ce_7_1_reproduce.py` (temporary local artifacts).

Normal reload of the user's already-running server subsequently applied the fixed migration. Read-only inspection confirmed schema version 2, `record_hash`, zero missions and healthy integrity. Diagnostics did not insert missions into the user's database.

## Fix

Database schema version 2 accepts both known version-1 index layouts. Legacy JSON resolution records are converted to canonical SHA-256 digests inside one explicit transaction. Existing aggregate payloads, identities, crisis numbers, histories and hashes must validate before the old table is removed and the version advances. The existing digest layout is validated and promoted without rewriting mission payloads. Any migration failure rolls back schema, version and data.

Column layouts are checked even for empty databases, so incompatible layouts fail at startup. Recovery additionally compares indexed crisis numbers with the aggregate ledger. JSON aggregate format version remains 1. Persistence, FULL synchronization, WAL, ownership locks, uniqueness constraints, immutable results, role projections, timers and voting behavior remain enabled and unchanged.

Files changed for 7.1 (other working-tree changes predate this task):

- `backend/app/persistence.py`: migration, schema validation, ledger/index validation.
- `backend/tests/test_persistence.py`: current schema version expectation.
- `backend/tests/test_persistence_migration.py`: eight regression cases.
- `backend/tests/smoke_milestone7_1.py`: real reload-mode migration, HTTP creation and reconnect smoke; optional source is copied read-only.
- `README.md`: automatic migration documentation.
- `docs/MILESTONE_7_1_VERIFICATION.md`: this report.

## Verification commands and results

Commands below run from the repository root unless noted.

- `.venv/bin/python -m pytest backend/tests/test_persistence.py backend/tests/test_persistence_migration.py -q`: 38 passed; one existing Starlette/httpx deprecation warning.
- `.venv/bin/python backend/tests/smoke_milestone7_1.py "$(cat /tmp/ce-7-1-repro-path)"`: PASS against a backup of the actual failing schema; three HTTP creations returned 201; a file-triggered reload restored the identical player identity and reconnect credential. Log: `/tmp/ce-7-1-after-server.log`. The command also works without an argument using a generated legacy fixture.
- `.venv/bin/python backend/tests/smoke_milestone7.py > /tmp/ce-7-1-recovery-smoke.log`: PASS across five real server generations. Preserved partial votes, expired Consensus Window recovery, roles/private intelligence, chat, independent missions, full ten-crisis victory/history (score 55.75), and early defeat/history (score 54.5).
- `npm --prefix frontend test > /tmp/ce-7-1-ui-default.log`: 62 passed, three optional captured-snapshot tests skipped, zero failures.
- `MISSION_RESTART_FILE=/tmp/ce-m7-restart.json MISSION_REVIEW_FILE=/tmp/ce-m6-live.json CHAT_ACCEPTANCE_FILE=/tmp/ce-chat-5-1.json npm --prefix frontend test > /tmp/ce-7-1-ui-acceptance.log`: all 65 passed, zero skipped.
- `npm --prefix frontend run typecheck`: passed.
- `npm --prefix frontend run build`: passed (includes type-check).
- `.venv/bin/python -m pip check`: no broken requirements found.
- `git diff --check`: passed.

The migration tests cover HTTP creation, multiple persisted missions, restart/reconnect, both legacy layouts with a complete campaign, preserved history/roles/privacy, exactly-once results, uniqueness constraints, malformed history rollback and incompatible empty schemas. Existing persistence tests cover operational storage failures returning 503 without accepting a mission.

An initial full backend run stalled after 39 passing tests and was interrupted; it is not counted as a passing suite. It was rerun with `-o faulthandler_timeout=45` to capture any recurrence. The diagnostic rerun stalled after 92 passing tests while `test_history.py:173` awaited a WebSocket frame following socket closure. All 220 backend tests then passed in two partitions:

- `.venv/bin/python -m pytest backend/tests -q --ignore=backend/tests/test_history.py -o faulthandler_timeout=45`: 205 passed in 7.08s.
- `.venv/bin/python -m pytest backend/tests/test_history.py -q -o faulthandler_timeout=45`: 15 passed in 0.69s.

Each partition reports the existing Starlette/httpx deprecation warning. The intermittent transport-test stall remains a limitation; no unrelated broadcast or gameplay changes were made to mask it.

Two verification harness issues were corrected: a test callsign exceeded the existing 24-character limit (correctly returned 422); and the first reload probe changed its file before WatchFiles was ready. The smoke now retries the file trigger while waiting for a new startup. Neither required changing application behavior.

## Restart and manual acceptance

Stop the existing port-8000 development server with Ctrl+C before starting another owner. Keep the same database path:

```sh
cd /home/attila_unix/projects/consensus-engine/backend
CONSENSUS_DB_PATH=/home/attila_unix/projects/consensus-engine/backend/data/consensus-engine.sqlite3 ../.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 and create a mission. Or check HTTP creation (this intentionally creates a real mission):

```sh
curl -i -H 'Content-Type: application/json' -d '{"callsign":"Host"}' http://127.0.0.1:8000/api/missions
```

Expect 201; keep the returned reconnect credential private. Join from another browser profile, start play, refresh, stop/restart the backend using the same command, and reconnect both saved seats. Verify unchanged roles, private intelligence and current crisis; review finished history after a run. Do not delete the database or lock file to work around startup errors.

## Limits

Physical browser/device acceptance remains manual. A monolithic backend run intermittently stalls in existing WebSocket transport tests; all tests passed when partitioned as documented above. The existing single-process POSIX ownership model and reconnect policy remain unchanged. Unknown/corrupt databases fail closed and require offline repair or a consistent backup. Temporary verification artifacts are not durable backups. No commit, tag or push was created.
