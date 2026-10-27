# Milestone 7.3 — Player presence and disconnection UX

## Architecture findings and cause

This was a visibility/context gap, not a missing server presence mechanism. `LobbyConnections` already owns a mission-scoped mapping of player IDs to sets of authenticated WebSockets. `MissionStore.project` already includes each participating seat's stable public ID, callsign, `connected` flag and existing public roles. Disconnect/connect broadcasts carry complete per-viewer snapshots, with persisted monotonic revisions; private intelligence remains filtered by authorized roles.

The old UI displayed local connection status and a full roster in Operations room, below the active gameplay/chat/result panels. Finished reviews had only a small connection badge. The Next crisis control used the correct authoritative gate but explained missing players only as “Waiting for every player.” A disconnected player's cached countdown could say “Waiting for server update” without a prominent nearby explanation.

No backend production changes, additional presence store, counters in the wire schema, polling, reconnect loops, networking dependencies or persistence changes were required.

## Presence state and socket replacement

Presence uses `mission.players` directly. Connected count is the number of server-provided `connected=true` seats; assigned-seat count is the full participating roster, including disconnected seats. No client presence claim is sent.

Existing backend behavior is retained and covered by tests:

- HTTP-created/joined seats remain disconnected until WebSocket authentication succeeds.
- Connect/disconnect broadcasts update authorized members of that mission.
- Multiple sockets for the same seat form a set. Removing an old socket cannot mark the seat offline while a replacement or another tab remains connected. Repeated stale cleanup does not remove the replacement.
- A failed send removes its failed socket and republishes corrected presence; existing tests continue covering this path.
- New connection snapshots include current presence, identity and role-private state.
- Presence connectivity is transient: serialized players are disconnected, and initialization resets recovered seats to disconnected until authenticated connections return. A saved completed mission follows the same rule.
- The new presence UI renders only callsign, You label and Connected/Disconnected text. It never renders credentials, role intelligence or vote contents. Existing public roles remain in the original lobby roster; the new compact display adds no role disclosures.
- Revision ordering and cross-mission isolation are unchanged.

## UI changes

`MissionPresence.tsx` supplies three small components:

1. **ConnectionNotice** uses the existing Milestone 7.2 hook state. It sits before gameplay in lobby, briefing, discussion, voting, Consensus Window, outcome, restart waiting and terminal review. On loss it says “Connection lost — reconnecting automatically.” Continued failure changes that to “Connection unavailable — continuing to retry automatically.” It explains stale mission state, disabled chat/voting, automatic recovery and that refresh should not normally be required. Initial connection and unrecoverable sessions have distinct accurate wording. Only the existing accepted-snapshot transition clears the warning and reports Connected/Reconnected.
2. **PlayerPresence** shows a compact roster and connected/assigned count above gameplay, including post-game review. Status text complements restrained green/amber styling. If the local connection is down, the count is explicitly **Last known** and a note says presence reflects the last server update; the client does not pretend cached teammate flags are current or alter server truth.
3. **ContinueStatus** names every missing public callsign, displays connected count, and explains why progression is blocked. Local disconnection, a pending HTTP request, and waiting for the host have their own messages. The host button is linked to that explanation with `aria-describedby`.

Notifications and presence use polite atomic status regions. The warning has sticky positioning so it remains visible while scrolling; long text/callsigns wrap, the roster grid shrinks, and narrow screens use one column. The original full roster remains in the lobby; active missions use the compact presence display. No popup, focus change or modal is introduced. Automated CSS/markup checks do not establish real browser layout or screen-reader speech behavior.

## Next crisis behavior

The existing button remains disabled when the local authoritative connection is unavailable, a continue request is pending, or any assigned seat is disconnected. Only the host receives that control. Missing names and count update from each new snapshot, for example:

> Waiting for Network 2 to reconnect before continuing. Players connected: 2 of 3.

With all seats restored, the explanation reports readiness and the control enables according to the existing conditions. The same behavior applies to Finish mission after the last crisis. The backend continues to reject advancement with HTTP 409 while any assigned player is disconnected. Nothing skips seats, changes quorum, removes players, changes timers or forces advancement.

## Tests and commands

From `/home/attila_unix/projects/consensus-engine`:

```sh
.venv/bin/python -m pytest backend/tests/test_presence.py -q
timeout 90s .venv/bin/python -m pytest backend/tests -q -o faulthandler_timeout=30
npm --prefix frontend test
MISSION_RESTART_FILE=/tmp/ce-m7-restart.json MISSION_REVIEW_FILE=/tmp/ce-m6-live.json CHAT_ACCEPTANCE_FILE=/tmp/ce-chat-5-1.json npm --prefix frontend test
node --experimental-websocket frontend/tests/smokeReconnection.mjs
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend ls --depth=0
.venv/bin/python -m pip check
git diff --check
```

Results:

- New backend presence tests: **6 passed**, covering joined/offline seats, connect/disconnect/reconnect broadcasts, old-socket race cleanup, cross-mission isolation, credentials/privacy, active and completed restart presence, nonresponse and unchanged Next crisis authorization.
- Complete backend suite: **226 passed in 7.79s**. One existing Starlette/httpx deprecation warning. The diagnostic timeout was not reached; no partitioning or skips were needed.
- Full frontend default suite: **90 passed, 3 optional capture tests skipped**, zero failures (93 tests).
- Frontend with existing captured restart/review/chat evidence: **93 passed**, zero skips/failures.
- Added ten UI tests; updated the prior two status assertions to check the new prominent accessible notification instead of the replaced status badge. Existing reconnect-controller tests and voting/chat tests remain enabled.
- TypeScript type-check: **PASS**.
- Production build: **PASS**, 43 modules; JS 262.22 kB, CSS 12.22 kB.
- Frontend installed dependency integrity (`npm ls --depth=0`): **PASS**, no dependency/version changes.
- `pip check`: **No broken requirements found**.
- Whitespace/diff checks: **PASS**.

Frontend coverage includes all live phases plus terminal review; an expired cached countdown accompanied by a loss warning; automatic reconnect status changes; count/text labels and no extra secret fields; stale-presence labeling; removal of stale warnings/labels; individual/multiple missing-player explanations; host/local-loss/pending-request reasons; mobile wrapping/single-column CSS; accessible status regions; disabled voting/chat and resumed valid controls.

Logs: `/tmp/ce-7-3-presence.log`, `/tmp/ce-7-3-backend.log`, `/tmp/ce-7-3-ui.log`, `/tmp/ce-7-3-ui-acceptance.log`, `/tmp/ce-7-3-network.log`.

## Live multiplayer verification

The extended existing `smokeReconnection.mjs` uses real uvicorn and Vite processes, three continuously held production reconnect controllers, native Node WebSockets and a temporary SQLite database on isolated ports 18772/18773. Existing individual-interruption and backend-restart checks remain intact. The new presence scenario renders production React presence/notification/outcome components in Node from actual received snapshots.

Observed sequence:

1. Three players reach active crisis voting.
2. C's WebSocket closes and its connection factory temporarily rejects retries; A/B receive C disconnected, count 2 of 3. C's local reconnect state renders the loss notice.
3. A/B submit B. Advancing the controlled server clock to the original deadline resolves the round with totals A=0, B=2, C=0 and **one nonresponse**. No voting or deadline code changes are used.
4. Production outcome markup has a disabled Next crisis button and names C in the waiting explanation. A real attempted continue returns HTTP 409.
5. C's transport is unblocked and automatically authenticates with the original credential. It retains identity/roles, receives the resolved phase, and all clients report connected presence. Rendered presence becomes 3 of 3 and the warning clears.
6. The production host control enables. A manually attempted vote for the expired round is rejected and cannot change totals.
7. The host advances successfully into Crisis 4 briefing.

**PASS.** The same smoke also passes its existing three-client restart sequence after Crisis 1: automatic reconnect without remount/refresh, restored identities/roles/intelligence/crisis/metrics/chat/history/deadline, increasing revisions and exactly-once consequences. Backend tests separately verify recovered seats start disconnected and become connected individually, including completed missions.

These are real-network checks plus server-rendered component markup, **not browser UI acceptance**. The fake-socket/controller tests and deterministic server/socket-registry tests are reported separately above.

## Manual browser acceptance and limitations

The user reported successful manual browser testing of Milestone 7.2 (live teammates continue, nonresponses, automatic reconnect and preserved identities/roles). This milestone does not claim that as verification of its new UI.

Browser automation initialization was attempted again through the supported computer-use runtime, but failed before accessing a browser with `sandboxCwd is not a local file URI: file:///home/attila_unix/projects/consensus-engine`. No browser navigation, screenshots or screen-reader checks were performed.

Remaining manual acceptance:

1. Open three profiles/devices, create/join a mission and start voting. Disconnect C, leaving its page open.
2. On C, confirm the visible sticky automatic-reconnect warning, stale-state explanation and disabled chat/vote controls. Scroll and check a narrow phone viewport; an expired countdown must not be the only connection indication.
3. On A/B, confirm C's public callsign says Disconnected and the count is 2 of 3. Submit two matching votes and let the original deadline expire. Confirm one nonresponse, no altered quorum/timing, and the disabled Next crisis control naming C.
4. Restore C without refreshing. Confirm Reconnected, same identity/roles, updated result/phase, no replayed votes/chat, presence 3 of 3, and host progression enabled. Continue the mission.
5. Repeat with two missing players; verify both names and the count. Confirm a non-host never receives a progression control.
6. Restart the backend against the same database with pages open. Recovered presence must reflect only reauthenticated seats, and the established mandatory-phase recovery policy must hold. Repeat in a completed/failed review.
7. Check replacement/overlapping tabs, long callsigns, 320–400px layout, zoom and screen-reader status announcements. Check initial connection and invalid/unrecoverable credentials do not promise an active retry loop.

The existing socket transport still determines when an established silent network loss becomes detectable. No new heartbeat or five-minute seat removal/redistribution was added. Presence reflects authenticated live sockets, not user activity or whether a page is in the foreground. Background tabs can throttle retries. Browser/device layout and assistive-technology acceptance remain pending.

## Exact Milestone 7.3 changed-file inventory

- `frontend/src/MissionPresence.tsx` — new notification, compact presence and progression explanation components.
- `frontend/src/App.tsx` — integrate them in all phases/review; keep full roster in lobby and remove buried duplicate connection badges.
- `frontend/src/ConsequenceOutcome.tsx` — explanatory status linked to the existing disabled progression control.
- `frontend/src/styles.css` — scoped warning/presence styles, sticky warning, responsive wrapping.
- `frontend/tests/gameplay.test.tsx` — ten presence/UX tests and updated status-region assertions.
- `frontend/tests/smokeReconnection.mjs` — retain prior checks and add real C-offline/nonresponse/gate/reconnect scenario with production markup.
- `backend/tests/test_presence.py` — six tests of existing authoritative behavior, privacy and gating.
- `docs/MILESTONE_7_3_PLAYER_PRESENCE.md` — this report.

All pre-existing uncommitted work was preserved. No backend production code, transport protocol, SQLite schema/semantics, role assignment, scoring, history, voting or deadline rules changed. No commit, tag or push was created. Implementation and automated/network verification are complete; new UI browser acceptance remains pending.
