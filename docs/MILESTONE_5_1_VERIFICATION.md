# Milestone 5.1 verification

## Reconnaissance and root cause

Read repository AGENTS.md and inspected Gameplay.tsx, App.tsx, useLobby.ts, types, bounded chat CSS, the existing rendered frontend runner/tests, and the controlled-clock multiplayer fixtures. The checkout was clean at the start of this milestone.

Auto-scroll was absent. ChatPanel rendered an ordered list keyed by authoritative message ID inside `.chat-history`, which had a maximum height and `overflow-y: auto`. There were no chat scroll refs, listeners, effects, unread state, or successful-send scroll handling. WebSocket snapshots replace the mission state through useLobby; new keyed list items therefore appeared below the visible area without any code moving the history viewport.

The separate ActiveGameplay effect intentionally focuses and reveals the active interaction on phase/round changes. It does not depend on chat messages and was left unchanged. Active discussion and Consensus Window chat mount inside that region; voting/result chat mounts separately as an archive. Mission-wide history, its 100-message server bound, and crisis-origin labels already existed.

## Implementation

- `frontend/src/chatScroll.ts`: view-only controller using the known history element's `scrollTop`, `scrollHeight` and `clientHeight`. No second message store, optimistic rendering, transport changes or dependency additions.
- `frontend/src/useChatScroll.ts`: refs and layout effects initialize the viewport after DOM updates and update it for new authoritative lists. A passive listener is attached only to the history element. ResizeObserver watches the history viewport and inner list for wrapping, content-height and viewport changes. Both observations and the listener are cleaned up on unmount/identity change.
- `frontend/src/Gameplay.tsx`: connects the hook to a bounded, keyboard-focusable history region with an inner ordered list; adds a counted, accessible jump button directly below it. Composer, Send button, message IDs and crisis labels remain intact.
- `frontend/src/styles.css`: chat-only styles preserve existing mobile height limits, contain touch scroll chaining, reset inner-list spacing, and reserve a separate unread row. The button does not overlay messages or the composer; it inherits the existing 48px minimum touch target and focus styling.

Following means `scrollHeight - clientHeight - scrollTop <= 40` pixels. This tolerates fractional geometry. Incoming messages follow only if this flag was true before the DOM update, or if a newly received message belongs to the current player. While reading earlier, the controller leaves scrollTop alone and increments unread. Manual return within tolerance clears unread and resumes following. Jump to latest directly assigns the history's bottom position, clears unread, and resumes following.

Stable message IDs detect arrivals across duplicate snapshots and unchanged-length 100-message rollover. A bounded 200-ID cache covers recent/replayed snapshots; a latest authoritative timestamp watermark excludes older backfill after an ID leaves that cache. Equal timestamps are still distinguished by ID. Unread is capped at the retained history length, so it does not advertise an ever-growing count of unavailable messages. These are view metadata only; message bodies are not copied or changed.

`sendIntent` returning true confirms only local socket dispatch. It does not trigger scrolling or clear unread. Only a new own message in the authoritative list confirms delivery and jumps to latest. Rejected sends (including the server's unchanged-state broadcast before its error frame) have no effect on scroll/unread. Existing composer dispatch/text-clearing behavior is unchanged. An own message from another tab of the same seat also counts as confirmed own activity.

Initial mount with existing history starts at the latest message without marking historical messages unread. Empty initial history works too. A fresh mount after refresh, restoration, or phase relocation initializes latest; reconnect while the same component stays mounted retains the reading position and treats only new IDs as arrivals. A new identity creates fresh view bookkeeping. Crisis changes alone do not reset the controller or historical server messages. Remounts during phase changes initialize only the inner history, without changing phase progression.

Resize observations keep the bottom visible while following, including long wrapping messages and smaller viewports. They leave a reader of earlier messages alone. Browsers without ResizeObserver still follow new authoritative messages but cannot react to later independent geometry changes.

## Focus, accessibility and layout isolation

Chat arrival/update/resize paths use no focus, window scrolling or scrollIntoView APIs. Only the history's scrollTop changes. The existing phase-level effect remains the owner of revealing discussion, initial voting, Consensus Window and final voting controls.

Unread uses a native button, explicit count/text, a meaningful accessible label, polite atomic announcements and standard keyboard activation. When an activated button disappears, focus moves to the history with `preventScroll: true` only if that button had focus. Incoming messages never move focus from typing or voting controls. The history region itself is focusable for keyboard scrolling. The unread row reserves height rather than causing layout growth on each unread toggle, and sits outside the scrolling history.

The original mobile `min(180px, 25dvh)` active-history bound, composer-before-history order, full-width Send button, label/message wrapping and phase-first voting controls remain. Added overscroll containment keeps touch scrolling from chaining into the page. This is code/geometry evidence, not physical keyboard or touchscreen acceptance.

## Automated verification

Commands run from repository root:

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest backend/tests -q` | **167 passed**, one existing Starlette/httpx TestClient deprecation warning |
| `npm --prefix frontend test` | **34 passed, 1 optional acceptance test skipped** without captured snapshots |
| `.venv/bin/python backend/tests/test_chat_acceptance.py` | **PASS**; three-client controlled-clock transport acceptance; snapshots written to `/tmp/ce-chat-5-1.json` |
| `CHAT_ACCEPTANCE_FILE=/tmp/ce-chat-5-1.json npm --prefix frontend test` | **35 passed**, including cross-layer snapshot replay |
| `npm --prefix frontend run typecheck` | Passed |
| `npm --prefix frontend run build` | Passed; 39 modules; production JS 247.02 kB, CSS 7.84 kB |
| `.venv/bin/python -m pip check` | No broken requirements found |
| `git diff --check` | Passed |

All previous 166 backend tests and 20 frontend tests remain. New frontend tests cover initial history, bottom tolerance, batches/rapid arrivals, preserved scroll position, unread accumulation, jump/manual return, confirmed own sends, unchanged/rejected sends, duplicate snapshots, reconnect backfill, equal timestamps, bounded rollover, crisis labels/transitions, remount, resize, observer/listener cleanup, rendered button accessibility, click-handler focus behavior, and isolation from outer scroll/focus APIs.

The Node runner has no native DOM layout engine. Scroll tests deliberately use explicit mutable `scrollTop`, `scrollHeight` and `clientHeight` geometry and execute the production controller. ResizeObserver/listener lifecycle is tested with an explicit adapter. Button markup uses real React server rendering and its production click handler is exercised with a focus stub. These are not mounted-browser layout, native touch, React DOM effect scheduling or screenshot tests. Existing rendered tests continue to verify active controls precede roster/intelligence, final voting renders fresh controls, and actual campaign content/mission-wide labels remain present.

The first new smoke attempt incorrectly expected an error frame before the existing unchanged-state broadcast on rejected chat. Inspection confirmed the established broadcast-then-error contract; the new harness was corrected and both smoke and full suites passed. Production transport was not changed. An initial default-sandbox read also failed because bubblewrap is unavailable; commands were retried through the permitted escalation flow.

## Multiplayer acceptance evidence

The new backend integration opens three independent TestClient WebSocket sessions with production content and a controlled clock. Eagle1 sends seven accepted messages; all three clients receive identical ordered chat IDs/content with Crisis 1 labels. A too-fast send is rejected; all clients receive unchanged chat and only the sender receives the error. A controlled discussion deadline opens voting; B/B/A resolves the crisis and the host advances to Crisis 2. Seven older messages remain, and Eagle3 adds an eighth message labeled Crisis 2. No production timer values were altered.

Captured real backend projections are then consumed by three independent production scroll controllers with deliberately mocked viewport geometry. A and C follow incoming messages; B looks back after three messages. Four later messages leave B's scrollTop unchanged and show four unread; C remains at latest with zero unread. Jump clears B's count; Crisis 2 history and its new message continue following. This is cross-layer simulated acceptance, not three physical browsers or a real-network browser smoke.

## Remaining browser/mobile acceptance and limitations

No new manual browser/device testing or browser automation was performed. Before closing physical acceptance, check at approximately 360px and 390px widths and on a laptop:

1. Receive enough messages to fill history; confirm following moves only the inner region.
2. Read earlier messages, receive more, inspect counted button, activate it by keyboard and touch, and manually return to latest.
3. Type while peers send; verify caret/focus stays in the composer. Test a rejected send while scrolled up and a confirmed own send.
4. Use long sender labels/multiline content, open/close the physical keyboard and rotate/resize; verify bounded history, wrapping, natural touch scrolling, visible Send and unread controls, and no page jump.
5. Refresh/reconnect with history, enter the next crisis, and exercise discussion → voting → Consensus Window → final voting. Verify phase-level controls still become visible and keep focus.

The server retains only the latest 100 messages. Content that has actually been evicted cannot remain readable; no archive or history-fetch system was added. The timestamp watermark assumes the existing server's chronological chat timestamps; substantial backward system-clock changes are outside this scroll-view contract. No backend chat delivery, voting, timers, crisis sequencing, consequences, scoring, persistence or identity behavior was modified.

## Exact files changed

Created:

- `frontend/src/chatScroll.ts`
- `frontend/src/useChatScroll.ts`
- `frontend/tests/chatScroll.test.tsx`
- `backend/tests/test_chat_acceptance.py`
- `docs/MILESTONE_5_1_VERIFICATION.md`

Modified:

- `frontend/src/Gameplay.tsx`
- `frontend/src/styles.css`
- `frontend/tests/gameplay.test.tsx` (imports the new tests into the existing runner)

No commits, tags or pushes were created. Implementation and automated checks are complete; physical browser/mobile acceptance remains explicitly pending.
