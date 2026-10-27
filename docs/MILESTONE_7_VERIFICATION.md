# Milestone 7 verification

## Architecture findings and design (before implementation)

Inspected AGENTS.md, current domain/store/transport, startup scheduler, voting/consequence ledger, private projections, chat, revisions, frontend reconnect/countdown behavior, package dependencies and existing test fixtures. Missions are wholly memory-only; browser localStorage credentials survive but cannot restore a lost server mission. Runtime sockets/tasks/locks and connected flags are transient. Final history, authored content, pending votes, deadlines and publication revisions must become durable. The existing exactly-once result ledger and explicit state machine will be reused.

Design: Python stdlib SQLite, versioned validated JSON mission aggregates plus a unique append-only resolution index. SQLite is durable authority; one process owns a write-through runtime cache. Mutations commit before acknowledgment/publication, rollback cache on failure, and never deserialize pickle. Persist immutable per-mission authored sequence, identity hashes, votes/deadlines, chat and ledger; derive summaries/timelines. Reset runtime presence on recovery. Retain original deadlines; expired votes resolve saved submissions. Mandatory phases not yet played wait explicitly for every reserved player before receiving a fresh normal-duration opportunity. No timer or voting-rule redesign. Production database path configurable, tests isolated by default. Existing Milestone 6.1 uncommitted UI files/report will be preserved.

## Persistence implementation and authority

`backend/app/persistence.py` uses only Python's stdlib sqlite3, hashlib and POSIX fcntl. Production `app.main:app` defaults to `data/consensus-engine.sqlite3`; `CONSENSUS_DB_PATH` overrides it. Opening/validation/recovery happen in FastAPI lifespan, not at import. Shutdown cancels scheduling and closes SQLite/ownership resources.

SQLite is the durable authority. MissionStore is a single-owner, write-through runtime cache, not an independently writable second authority. Existing application mutations remain under the state lock. A small outer-intent wrapper snapshots the affected cache entry, executes the existing rule code, then commits changed durable data. Nested expiry/resolution/consequence calls share the outer operation. Storage failures restore the cache snapshot and do not acknowledge the mutation. A rejected late action may still commit a valid expired-phase transition before returning its established rejection; this preserves the prior engine behavior.

Runtime presence is deliberately excluded from persistence comparison: disconnects cannot roll back into ghost connected seats when storage is unavailable. Actual recovery/resume phase changes still require a commit. Publications persist their revision before sending any snapshot. Failed publications are queued for scheduler retry; an in-flight send is not a failed publication. Failure of one mission's timer/publication does not lose another committed mission's publication. A process crash discards only runtime handles/queues; reconnect republishes the durable state.

Operations are synchronous, bounded local SQLite transactions under the existing lock. Network sends still occur outside that state lock. This favors correctness and the small MVP over introducing another asynchronous database service.

## Schema, migrations and stored data

Database schema **v1**, tracked with `PRAGMA user_version`:

| Table | Contents / constraints |
|---|---|
| `missions` | Opaque mission token primary key; `format_version=1`; canonical JSON payload; SHA-256 payload checksum |
| `resolutions` | Mission foreign key, stable deciding-round result ID, crisis number, immutable canonical record hash; primary key `(mission_token,result_id)`; unique `(mission_token,crisis_number)` |

Initialization of an empty database is transactional. Unknown schema versions or nonempty unversioned databases fail closed. Mission JSON has its own format version and exact top-level field contract; future schema/model changes require an explicit versioned migration. There is no pickle/deserialization of executable objects. No existing persisted database required migration: earlier milestones were memory-only.

Each aggregate stores stable mission/player IDs, credential verification hashes, roles, phase/index, the full immutable-per-mission authored sequence, metrics/initial metrics, UTC deadlines, pending votes/eligibility/tallies, decision/result ledger, acknowledged result IDs, bounded chat and rate-limit timestamps, publication revision and any recovery metadata. The current crisis is reconstructed from the saved sequence/index rather than duplicated in storage or reloaded from potentially changed package content. Recovery works even if the content-loader callback is unavailable. Summary/timeline/chart data are derived exactly as before and are not stored separately. The resolution index stores hashes, not duplicate historical narratives.

WAL journaling, `synchronous=FULL`, foreign keys and transaction boundaries protect accepted operations. Mission JSON, vote changes, metric consequences, ledger entry and resolution index insert commit together. The existing stable deciding-round key and duplicate-vote/acknowledgment checks remain. The index prevents two different results for the same crisis; existing result hashes must match on subsequent writes, and finalized entries cannot be removed. Retry after a committed-but-unacknowledged vote/result cannot apply consequences again.

The payload checksum detects accidental damage; it is not encryption or an authenticity guarantee against an administrator editing the database. Load checks schema/version/checksum, typed content, exact record fields, membership/role/metric/history consistency, voting/recovery deadlines and resolution-index equality. Any invalid record stops startup with a safe error. Valid records are retained in the database; there is no automatic deletion, replacement or partial silent recovery.

## Credentials and privacy

New seat credentials retain their existing high-entropy random format. SQLite stores only their SHA-256 verification digest; raw reconnect secrets are stripped before serialization. A fast digest is appropriate for random capability tokens, not human passwords. Raw credentials exist only in the original response/client and active request/socket context. Restored players have no raw credential stored in their internal Player object; reconnect responses echo only the credential just successfully supplied by that caller. WebSocket actions authorize using the authenticated request secret rather than trying to recover one from storage.

The database file is created/restricted to owner read/write (`0600`); newly created directories request `0700`. Backups contain private authored intelligence and chat and also need private storage. No encryption-at-rest service is introduced. Never serve the database directory as static content. No reconnect secrets or mission payloads are logged in operational errors. Tests scan the database, WAL and other runtime files for the generated raw secrets.

Existing per-seat projections remain the privacy boundary: only authorized current role intelligence and the caller's own pending vote are projected. Public history contains aggregate tallies, not individual votes. Invite membership and credentials remain isolated per mission. No account, password, role-claim, history-edit or mission-discovery endpoint was added.

## Recovery and timer policy

Production timers remain wall-clock Unix/UTC deadlines (`time.time()`); browser `performance.now()` is still only a local rendering aid. No monotonic process timestamp is persisted as a deadline.

At startup every live socket is gone and all player connected flags become false. Briefing, result, victory and defeat phases retain their state. Timed phases become explicit `reconnect_wait`, preserving `recovery_phase` and the original deadline. Startup reconciles an already-expired voting round; the scheduler also reconciles a waiting vote that expires while players are reconnecting. No guessed future phase is simulated through multiple offline opportunities.

| Recovered condition | Behavior |
|---|---|
| Unexpired discussion, initial vote, Consensus Window or final vote | Wait for reserved seats; if still unexpired when all return, resume the **original** deadline and saved submissions |
| Expired discussion | Do not restart its 60 seconds; open the mandatory initial vote only when all seats return, with a fresh 30-second voting opportunity |
| Expired Consensus Window | Do not restart its 20 seconds; open mandatory final voting only when all seats return, with a fresh 30-second opportunity |
| Already-open expired initial/final voting | Resolve its saved submissions under existing plurality/abstention/fallback rules; never reopen/reset that old vote |
| Expired initial vote yields a top tie | Preserve its closed tally and hold a **new, not-yet-played** Consensus Window; its normal 20 seconds starts after all reserved seats return, followed by fresh final voting |
| Result/completed/failed | Restore without reapplying consequences; derived review/history/score remain identical |

Downtime counts against deadlines of phases already opened. Missing submissions in an expired vote remain abstentions; no new voting rule is invented. Fresh durations above belong only to a newly required phase that has not yet been offered. Repeated restarts while waiting do not renew an original deadline or start an unplayed phase offline. A participant who sends a stale/expired vote gets the existing rejection after any necessary authoritative expiry processing.

The existing all-seats-connected start/advance requirement remains. A missing reserved player can hold recovery indefinitely because five-minute timeout/removal/role redistribution remains deferred. This milestone does not fabricate a replacement participant or silently drop a seat.

## Frontend integration

The existing localStorage identity, exponential WebSocket retry and stale-revision guard are preserved. Durable publication revisions and a startup increment ensure post-restart snapshots are newer than the last published snapshot. Each accepted snapshot replaces authoritative state rather than appending history/messages. Obsolete socket callbacks remain ignored.

Minimal additions recognize `reconnect_wait`, explain waiting for all players, show restored chat read-only, and leave actions disabled until the server resumes the appropriate phase. No countdown is shown for a held phase; original active deadlines resume from server timestamps, with the existing zero clamp. Recovered terminal summaries route directly to the Milestone 6 review. A connection interruption explains automatic restoration, and an accepted fresh snapshot clears that temporary error. An invalid session message asks the player to check their invite/contact the host rather than assuming a restart destroyed the mission.

Milestone 5.1 chat view bookkeeping remains unchanged: restored messages have the same stable IDs and mission-wide crisis labels, so snapshot replay does not insert duplicates. New mounts initialize at latest; same-component restoration counts only genuine new messages under its existing rules. Milestone 6.1 chart/table/badge/mobile changes were preserved without alteration in this task.

## Automated tests and exact results

Run from the repository root:

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest backend/tests/test_persistence.py -q` | **30 passed**; one existing Starlette/httpx TestClient deprecation warning |
| `.venv/bin/python -m pytest backend/tests -q` | **212 passed**; same existing warning |
| `npm --prefix frontend test` | **62 passed, 3 optional snapshot cases skipped** (65 total) |
| `MISSION_RESTART_FILE=/tmp/ce-m7-restart.json MISSION_REVIEW_FILE=/tmp/ce-m6-live.json CHAT_ACCEPTANCE_FILE=/tmp/ce-chat-5-1.json npm --prefix frontend test` | **65 passed**, no skips |
| `npm --prefix frontend run typecheck` | Passed |
| `npm --prefix frontend run build` | Passed; 41 modules; JS 257.72 kB, CSS 10.98 kB |
| `.venv/bin/python -m pip check` | No broken requirements found |
| `.venv/bin/python backend/tests/smoke_milestone7.py > /tmp/ce-m7-smoke.log` | **PASS**; genuine process kills/restarts, SQLite, real HTTP and WebSockets |
| `git diff --check` | Passed |

The 30 persistence cases cover new/multiple missions, original identities and callsign uniqueness, invalid/cross-mission credentials, role-private projections, stable authored content without reloading a pool, metrics, chat/rate limits and message IDs, raw-secret absence, pending votes, initial/final tallies, duplicate actions, expired/unexpired timers in four timed phases, repeated recovery, delayed final-vote opportunity, result/acknowledgment idempotency, actual ten-crisis victory and early defeat, canonical review equality, fresh application instances, unique SQLite constraints, commit failure rollback, HTTP 503, transient presence, failed-publication retry, schema/corrupt-record handling and exclusive ownership.

All previous 182 backend tests remain. Existing frontend assertions remain, with the render utility using each snapshot's actual `server_now` for recovery countdown checks. Five new ordinary frontend cases cover held recovery, restored own vote, stable chat/deadline, zero-clamped expired timer and disconnected controls. One optional case renders the actual killed-process recovery snapshots, including final voting and both terminal outcomes. The preceding two optional acceptance cases still run against their captured chat/review fixtures. No tests are presented as mounted-browser or physical-device verification.

During development the unchanged four-player campaign regression caught a retry-queue race: an in-flight publication had incorrectly been considered retryable, generating an extra snapshot. The queue now contains only failed publications, claimed under the delivery lock, and the complete suite passes. A new frontend test initially assumed radio attribute order; it was corrected to inspect the saved choice's checked state independent of serialization order. No game assertions were weakened.

## Genuine live restart evidence

`smoke_milestone7.py` runs **five separate Uvicorn processes**, using a shared temporary SQLite database and a test-only UTC clock file. It kills processes abruptly (`SIGKILL`), waits for exit, launches a new interpreter/application, and reconnects real WebSocket clients. No server memory, cache, module globals, sockets or tasks survive these restarts. The clock file is an injected test clock, not a production endpoint; production durations remain 60/20/30 seconds. This is real process/network/storage verification with controlled time, not a same-instance reconnect simulation or production-duration browser playtest.

- **A — Active restart:** three players complete Crisis 1, enter Crisis 2 discussion and exchange chat. After restart, IDs, roles, crisis, metrics, public history, private intelligence and chat match. The unexpired discussion deadline is unchanged; revision increases.
- **B — Voting interruption:** one valid vote is saved; restart restores the same round, own vote and deadline. A duplicate submission is rejected. The remaining A/C submissions produce the original top tie without recounting the stored B.
- **C — Consensus interruption:** process stops in the Consensus Window; test time advances beyond its saved deadline. Recovery waits for players and opens a fresh **mandatory final vote** with a full 30-second opportunity, preserving the initial A/B/C tally. Final B plurality resolves once.
- **D — Terminal restart:** the primary mission completes all ten crises with final metrics **63/55/53/52**, score **55.75**. A separate production-content mission collapses at Crisis 4 with score **54.5** and defeat status. Another real process restart restores byte-equivalent canonical history, derived timeline/summary, metrics and chat for both; no consequence is repeated.
- **E — Isolation:** an independent two-player mission runs beside the primary mission across restarts. Its roles, channel messages, history and state remain distinct. Original valid credentials work only in their own mission.

The smoke emits safe PASS lines and writes authorized test snapshots to `/tmp/ce-m7-restart.json` for frontend acceptance. It does not log reconnect secrets. Its temporary database and runtime files are removed only when that test finishes; production missions are never automatically deleted.

## Operations: location, restart and backups

Default command (from a stable working directory):

```sh
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --ws-max-size 4096
```

Recommended explicit private path:

```sh
CONSENSUS_DB_PATH=/absolute/private/path/consensus-engine.sqlite3 .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --ws-max-size 4096
```

Restart with the same path; preserve browser localStorage credentials. A different working directory with the relative default, or a different configured path, creates/opens a different database and cannot restore the original mission. `create_app(database_path=...)` enables persistence for embedded/factory use. Omitting that factory argument and standalone MissionStore retain isolated ephemeral behavior for existing tests/embedding; production should use `app.main:app` or explicitly supply a path. Import alone does not create a database.

Only **one application process per database** is supported and enforced with a POSIX advisory ownership lock. Use one worker and local Linux/WSL storage. Live socket membership remains process-local; multi-worker/distributed coordination is not added. Do not edit the database through another writer while the server runs. The ownership lock is released automatically after process death; do not delete a live owner's lock file to bypass it. Its empty file may remain after shutdown.

For a live consistent backup, use SQLite's backup API rather than copying only the main file while WAL writes are active. Example (replace paths; parent backup directory must exist and be private):

```sh
.venv/bin/python - <<'PY'
import os
import sqlite3
os.umask(0o077)
with sqlite3.connect('file:/absolute/private/path/consensus-engine.sqlite3?mode=ro', uri=True) as source:
    with sqlite3.connect('/absolute/private/backups/consensus-engine.sqlite3') as target:
        source.backup(target)
PY
```

Alternatively stop the server cleanly, wait for exit/SQLite close, then copy the database. Keep the source's WAL/SHM files intact during active operation and recovery. To restore a backup, stop the process, preserve the damaged/current database and its sidecars for diagnosis, restore a consistent backup into the configured location without stale sidecars, restrict permissions, and start again. Do not delete valid mission rows to bypass corruption. A point-in-time backup necessarily lacks later actions; browser refresh may be needed after deliberately restoring an older revision. Normal restart uses current durable revisions and does not require clearing the saved seat.

Unknown schema/format, checksum/index inconsistency, invalid records, unsupported ownership or unavailable storage stop recovery with safe diagnostics. Runtime write failures return HTTP 503 or close WebSockets with a recoverable 1011, preserve the last durable state, and retry queued publication/timer work after storage returns. An error after a commit but before acknowledgment can be ambiguous to the caller; result/vote retry protections prevent duplicate consequences. An explicit resend of chat remains a new chat intent under the existing rules.

## Limitations and manual acceptance

No actual browser/device or physical mobile acceptance was performed. New Node tests render real React markup and restored payloads; they do not execute a browser's automatic retry loop, focus, ResizeObserver, keyboard or touch behavior. Before closing manual acceptance, play on three real browsers/devices, interrupt/restart the configured backend in discussion, partial initial/final voting, and consensus, and inspect restored chat/unread/focus, private roles and countdowns. Repeat a terminal refresh and check the mobile review at the Milestone 6.1 widths.

SQLite is local durable storage, not replicated storage or encryption. Backups and filesystem durability remain operational responsibilities. The owner lock requires POSIX/Linux/WSL; native Windows-server locking and network filesystem/multi-host deployment are not implemented. Startup currently loads all retained missions and fails closed if any record is invalid, retaining all data for repair. There is no automatic mission expiry/deletion, public archive, account recovery or ability to reconstruct a raw seat credential after browser storage is lost. Runtime synchronous writes and per-mission JSON snapshots are intentionally sized for the small MVP.

Five-minute disconnect timeout/removal/role redistribution remains deferred, so recovery can wait indefinitely for a reserved seat. Variable crisis pools/weakest-metric finales, QR/replay, production hosting, accounts, cloud databases, analytics/leaderboards and LLM scenarios remain outside scope. This milestone preserves the fixed ten-crisis campaign, metrics, vote rules, history/review and mobile polish.

## Changed-file inventory

Created for Milestone 7:

- `backend/app/persistence.py`
- `backend/tests/test_persistence.py`
- `backend/tests/smoke_milestone7.py`
- `docs/MILESTONE_7_VERIFICATION.md`

Modified for Milestone 7:

- `.gitignore` — ignore runtime database/WAL/ownership files.
- `README.md` — durable entry point, restart policy, backup/configuration overview.
- `backend/app/domain.py` — credential digest and durable recovery metadata.
- `backend/app/missions.py` — transactional write-through cache, reconstruction and recovery policy.
- `backend/app/main.py` — lifespan/configuration, safe storage errors and timer/publication retry.
- `backend/app/connections.py` — durable revisions and failed-publication retry tracking.
- `frontend/src/types.ts` — recovery snapshot/phase type.
- `frontend/src/Gameplay.tsx` — recovery phase label.
- `frontend/src/App.tsx` — recovery explanation and restored read-only chat.
- `frontend/src/useLobby.ts` — recoverable interruption message and clearing on restored state.
- `frontend/tests/gameplay.test.tsx` — restored UI/countdown tests and optional real-restart snapshot acceptance.

Pre-existing uncommitted Milestone 6.1 changes were preserved: `frontend/src/MissionReview.tsx`, `frontend/src/styles.css`, `frontend/tests/missionReview.test.tsx`, and `docs/MILESTONE_6_1_UI_POLISH.md`. They are not new Milestone 7 implementation changes.

No commits, tags or pushes were created. Milestone 7 implementation, automated checks and genuine backend restart scenarios are complete; real-browser/device acceptance remains explicitly pending.
