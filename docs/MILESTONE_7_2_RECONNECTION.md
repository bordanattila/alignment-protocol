# Milestone 7.2 — Automatic reconnection and connection resilience

## Root cause and reconnaissance

The existing `useLobby` scheduled retries exclusively in `WebSocket.onclose`. It had no `onerror` handler and no deadline covering connection establishment or authentication. A failed attempt that emitted only `error`, or stayed CONNECTING, permanently stopped the loop while its UI continued saying “Reconnecting.” Refresh worked by mounting a new hook and opening a new socket with the same stored credential.

This was reproduced before editing with the actual hook (a minimal hook host, not a browser), Node 20's native WebSocket, a real uvicorn process, a temporary SQLite database, and a Vite proxy configured identically to development. After backend termination the socket emitted close 1006. The first retry emitted `error` with readyState 0 (CONNECTING), without a close event. After restarting the backend the old hook remained Reconnecting with that socket still CONNECTING. The repaired hook recovered through the same scenario and reported Reconnected, readyState 1. Logs are `/tmp/ce-7-2-baseline-events.log` and `/tmp/ce-7-2-after.log`; the local reproduction driver is `/tmp/ce-7-2-baseline.mjs` (now imports the repaired code).

This establishes the missing error/timeout recovery path with real network traffic. It does not establish which events the user's particular browser emitted: browser acceptance is still required.

Other findings:

- Credentials are stored under `consensus.session.<token>` and sent in the first authentication frame, never the WebSocket URL. Refresh restores this same credential without allocating another seat.
- The backend accepts the socket, validates that frame, authorizes the existing identity, updates presence, and broadcasts a complete role-filtered snapshot. No separate HTTP restore request is necessary for reconnect.
- The existing same-origin ws/wss URL and Vite `/api` proxy are correct and unchanged.
- `SnapshotOrder` rejects duplicate or lower revisions. Revisions are persisted before publication and advanced during recovery; resetting ordering on reconnect would weaken this protection and was not done.
- The React effect previously depended on the session object. It now depends on token and credential primitives so equivalent session objects cannot restart the connection loop.
- There was no application heartbeat. The fix adds a first-snapshot watchdog, not a new heartbeat protocol.
- Ordinary live disconnect retains seats/roles and existing deadlines; established backend restart recovery uses `reconnect_wait` where appropriate. These policies remain unchanged.

## Implementation and retry policy

`MissionConnection` owns one transport and retry loop per mounted mission hook. The hook retains React state and clock sampling; transport logic is separate so it can be tested with controlled sockets/timers without a networking dependency.

Unexpected close, socket error, synchronous constructor/send failure, or failure to receive an accepted authentication snapshot within 15 seconds retires that transport and schedules another attempt. The retry ceiling is `min(1000 * 2^(failures-1), 10000)` milliseconds, with equal jitter uniformly between half the ceiling and the ceiling: initially 0.5–1 second, ultimately 5–10 seconds. Attempts continue without a retry-count limit. Only an accepted fresh snapshot resets the failure count and enables gameplay.

Status announcements use the existing accessible `role="status"` badge:

- Connecting
- Connected
- Connection lost — reconnecting
- Connection unavailable — continuing to retry (after three consecutive failures)
- Reconnected
- Session no longer recoverable (server policy close 1008)

A TCP/WebSocket OPEN event alone never marks the session connected. Reconnected is a connected state and enables valid controls. Snapshot/watchdog/retry timers are canceled on success or stop. Retired socket callbacks are detached and guarded by transport identity, so a late callback cannot overwrite a newer snapshot or schedule a second loop. Effect cleanup, session change and intentional navigation/unmount stop retrying. Invalid/unavailable credentials stop with an actionable status while retaining stored credentials until the user explicitly returns to mission creation.

No gameplay intents are queued or replayed. Chat/vote sends return false while disconnected, and HTTP mission controls are gated by connected state. A reconnect replaces the snapshot wholesale, including authorized intelligence, submitted-vote state, chat, history and review. Backend authority and revision ordering remain intact. The transport cannot guarantee delivery of a frame interrupted during sending; the next snapshot establishes what the server actually accepted.

## Individual disconnection and backend restart evidence

`frontend/tests/smokeReconnection.mjs` runs three production client controllers continuously against real uvicorn and Vite processes with a temporary SQLite database and controlled server clock. It does not remount controllers or refresh between failures. Ports 18772/18773 are isolated from the user's development server, and only temporary data is used.

Individual interruption:

1. Start a three-player mission and discussion.
2. Interrupt A's transport and temporarily block its connection factory.
3. B/C receive A's offline presence and continue chat, the authoritative discussion-to-voting transition and B's vote.
4. Unblock A. Automatic reconnect restores the original identity, roles, private intelligence, new chat, vote progress and unchanged voting deadline.
5. Submit A's vote, interrupt A again, and let C submit. B/C resolve with exactly three votes; A automatically restores the result without replaying its submitted vote.

Restart:

1. Complete Crisis 1, open Crisis 2 discussion, and persist chat.
2. Kill the backend; all three controllers report disconnection and reject offline intents.
3. Keep them alive through startup unavailability, then start a fresh backend process on the same database.
4. All reconnect automatically. Identities, roles, intelligence, crisis, metrics, history, chat and original deadline equal the saved snapshots; accepted revisions strictly increase.
5. Continue voting and resolve Crisis 2 exactly once. Duplicate continue acknowledges do not duplicate history or metrics; no chat or vote is replayed by reconnect.

The existing Milestone 7 smoke separately verifies partial votes, expired Consensus Window recovery, fresh mandatory final-vote opportunity, finished review/history, victory and defeat across five real server process generations. No quorum, timeout, redistribution, resolution, migration or storage rules were changed.

## Automated checks

Run from `/home/attila_unix/projects/consensus-engine`:

```sh
npm --prefix frontend test
MISSION_RESTART_FILE=/tmp/ce-m7-restart.json MISSION_REVIEW_FILE=/tmp/ce-m6-live.json CHAT_ACCEPTANCE_FILE=/tmp/ce-chat-5-1.json npm --prefix frontend test
node --experimental-websocket frontend/tests/smokeReconnection.mjs
.venv/bin/python -m pytest backend/tests/test_persistence.py backend/tests/test_persistence_migration.py backend/tests/test_identity_hardening.py backend/tests/test_consensus_regression.py -q -o faulthandler_timeout=45
.venv/bin/python backend/tests/smoke_milestone7.py
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend ls --depth=0
.venv/bin/python -m pip check
git diff --check
```

Results:

- Frontend default: **80 passed, 3 skipped**, zero failures (83 tests). The skips require optional captured snapshots.
- Frontend with existing review/chat/restart captures: **83 passed, zero skipped**. Includes 16 new transport tests and two new status/control rendering tests.
- Relevant backend tests: **67 passed**, one existing Starlette/httpx deprecation warning.
- Three-controller interruption/restart network smoke: **PASS**.
- Existing five-generation backend recovery smoke: **PASS**, including full victory score 55.75 and early defeat score 54.5.
- TypeScript type-check and production build: **PASS**.
- `npm ls --depth=0`: **PASS**, no new dependencies.
- `pip check`: **No broken requirements found**.
- Whitespace check: **PASS**.

Transport tests use an explicit fake clock/scheduler and controlled WebSocket objects: initial and repeated errors without close, unexpected closure, silent handshake/authentication stall, jitter/backoff, constructor/send errors, success cleanup, leave cleanup, obsolete events, single-loop ownership, stored credentials, monotonic revisions, restored chat/votes and terminal review. Rendering tests verify accessible statuses, disabled controls while offline and resumed interactions on Reconnected. These are not browser tests.

Logs: `/tmp/ce-7-2-ui-default.log`, `/tmp/ce-7-2-ui-acceptance.log`, `/tmp/ce-7-2-backend.log`, `/tmp/ce-7-2-network.log`, `/tmp/ce-7-2-recovery.log`.

## Browser acceptance and remaining limits

Real browser acceptance was not performed. The computer-use skill was inspected and its supported runtime initialization attempted, but `node_repl` failed before browser access with `sandboxCwd is not a local file URI: file:///home/attila_unix/projects/consensus-engine`. No browser controls or refreshes were used. Node real-network tests are not claimed as browser acceptance.

Manual acceptance remains:

1. Run the backend against its existing absolute SQLite path and open three distinct browser profiles/devices. Create/join one mission and note each callsign and roles.
2. Start discussion; interrupt only A's network/socket. Confirm B/C remain connected, see A offline, and receive chat/timer/vote updates. Restore A without refreshing. Confirm Reconnected, same seat/roles, restored chat and saved vote, no duplicate messages/votes, and unchanged server deadline.
3. Complete at least one crisis. Leave all pages open, stop the backend, and wait through multiple automatic retry attempts. Restart on the same database without refreshing any page. Confirm all restore the latest state and can continue; verify a result appears exactly once.
4. Repeat with partial votes and a Consensus Window; confirm established mandatory-phase recovery. Repeat in a completed/failed mission to recover the same post-game review.
5. Leave a page while retries are active and verify it opens no further sockets. Verify invalid credentials show the unrecoverable status rather than a permanent spinner. Check phone layout and screen-reader status announcements.

The watchdog covers connection establishment and the first accepted snapshot. An already authenticated silently half-open connection still depends on the browser/OS transport detecting loss; no application heartbeat was introduced. Background tabs may throttle retry timers. Existing multi-tab seat semantics remain; each mounted hook owns one active transport. Existing five-minute disconnect removal/role redistribution remains future work.

## Exact Milestone 7.2 file inventory

- `frontend/src/missionConnection.ts` — new guarded connection/retry controller.
- `frontend/src/useLobby.ts` — integrate controller, stable identity dependencies, cleanup and authoritative snapshot readiness.
- `frontend/src/App.tsx` — connected/Reconnected control gating and HTTP action guard.
- `frontend/tests/missionConnection.test.ts` — 16 controlled transport/session tests.
- `frontend/tests/gameplay.test.tsx` — two accessible connection-state/control tests.
- `frontend/tests/run.mjs` — bundle/run the new test entry independently of the App snapshot fixture.
- `frontend/tests/smokeReconnection.mjs` — real three-client Vite/backend interruption and restart smoke.
- `docs/MILESTONE_7_2_RECONNECTION.md` — this report.

All other existing working-tree changes predate 7.2 and were retained. No backend, SQLite schema, authored content, gameplay rules or dependency versions changed in this milestone. No commit, tag or push was created. Implementation and automated/network verification are complete; full manual browser/device acceptance remains pending.
