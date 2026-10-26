# Milestone 3 verification

Milestone 3 extends the existing mission store, React UI, first-frame seat authentication, and per-player WebSocket projections. It stops at `decision_locked`: no metric updates, consequences, additional crises, or progression are implemented. Existing Milestone 1/2 tests and authored JSON are unchanged.

## Architecture and state

- `domain.py`: adds typed chat records, voting rounds, resolution reasons/results, strict chat/vote intents, and `decision_locked`. Mission holds one current deadline, up to two rounds, private vote maps, bounded chat, per-seat chat rate timestamps, and the locked decision.
- `missions.py`: centralizes discussion deadlines, due transitions, chat, voting, eligibility, resolution, and allowlisted projection. All production mutations remain under the existing app state lock.
- `voting.py`: independent pure plurality calculation; highest submitted count wins, without a majority threshold.
- `main.py`: retains existing HTTP create/join/start/discussion routes; extends authenticated WebSocket actions and manages one lifespan scheduler. No new public timer/phase-control endpoints exist.
- `connections.py`: snapshots membership and per-viewer payloads under the state lock, releases it before network I/O, and orders publications with a separate delivery lock. Failed sends remove only the failed socket and republish presence, preserving multi-tab behavior. Fresh snapshots are captured after delivery serialization, so delayed publishers cannot send an older snapshot after a newer one.
- React: retains the compact header, role badges, public/private briefing, and baseline metrics. Adds phase clocks, read-only/live chat states, private radio-card voting with explicit submit, consensus aggregate results, and locked-decision explanations. No added dependencies.

## Timers and races

The store accepts a clock function (production uses Unix seconds from `time.time`). Discussion records `now + 60`; initial/final voting each records `now + 30`; a tied first vote records `now + 20` for consensus. Deadlines are not reset on socket lifecycle events. The browser anchors each received `server_now` to `performance.now()` and only animates remaining time. Client wall-clock skew cannot advance a phase. Network transit can make the displayed remainder slightly optimistic; zero displays “Waiting for server update.”

One app-lifespan task checks deadlines every 100ms. Each tick checks the current authoritative phase/deadline under the state lock. Vote/chat intents and reconnect authentication also check expiry. A late vote at or after its deadline is rejected even if the scheduler has not yet run. At the exact boundary, timeout takes precedence; there is no fabricated last vote.

Ticks carry no captured phase transition commands. Repeated ticks before the new deadline do nothing, and a callback for an old deadline cannot force a newer phase forward. A delayed wake opens the next phase with its full duration rather than skipping a voting window nobody saw. Last-vote resolution and timeout are serialized by the same lock; whichever runs later rechecks current state. Decision lock clears the deadline and prevents further transitions. Lifespan shutdown cancels and awaits the scheduler.

Socket delivery has bounded two-second send/close waits outside the state lock. Publication is serialized and a slow client may delay delivery and scheduler publication; state mutations are not blocked by those network waits. This remains a single-worker, in-memory MVP and is not designed for distributed deployment.

## Protocol and validation

Existing first frame: `{"type":"authenticate","credential":"<seat credential>"}`.

New authenticated intents:

- `{"type":"chat","text":"<1–500 trimmed characters>"}`
- `{"type":"vote","round_id":"<current server round ID>","choice_id":"<authored choice ID>"}`

Schemas forbid extra fields and coercion. Client-supplied sender IDs, callsigns, mission IDs, winners, credentials in actions, or role assignments are not accepted. The socket's authenticated seat credential and mission route determine identity and scope. Frames must be text JSON of at most 4096 characters; malformed/unknown/binary/oversized frames close with policy error. Recognized invalid fields and game-rule rejections return an error frame without losing the seat. State frames remain `{"type":"state","mission":...}`; action errors use `{"type":"error","detail":"..."}` without stack traces.

## Chat

Chat opens only in discussion and consensus, with read-only history during briefing/voting/decision lock. IDs and timestamps are server-generated and callsigns come from the authenticated seat. One accepted message per second per seat (shared across its tabs); only the most recent 100 messages remain. Messages are ordered by locked insertion and reconnect receives retained history. React renders text normally, with no HTML injection API. Private intelligence is never automatically copied into chat; players may deliberately share their own information.

## Eligibility and disconnect policy

Each voting round freezes the started participating seats (seats with assigned roles), including temporarily disconnected participants. Each seat has one vote regardless of holding one or two domains. Joining after start remains blocked. Refresh/reconnect restores the same identity, roles, current phase/deadline, history, own vote, and result.

The existing implementation reserves seats indefinitely; five-minute removal/role redistribution is still unimplemented. Milestone 3 deliberately adds no seat expiry. Instead, every voting round has a 30-second deadline and resolves early only when every eligible seat has voted. Missing/disconnected players remain eligible to vote on reconnect until that deadline. At expiry, missing votes become explicit abstentions/nonresponses, never AI votes. Discussion and consensus deadlines also continue through disconnects. The explicit milestone timeout policy takes precedence over pausing for missing participants.

## Public/private boundaries

The internal Mission and VotingRound models are never serialized wholesale.

Public fields include phase, deadline, server time, crisis title/briefing/reference choices/recommendation ID, metrics, player identity/presence/role labels, retained chat, submitted/eligible vote counts, closed-round aggregate totals/abstentions, and the final decision.

The viewer-specific projection includes only that seat's role intelligence and `voting.your_vote`. It never includes another seat's vote or the internal seat-to-choice maps. An open round publishes no per-choice totals. Closed-round audit projections publish aggregate totals only, without individual selections. Role ownership is public, but intelligence texts remain private. Credentials, consequence text, and metric deltas remain excluded. Server audit retains both rounds' vote maps internally; round-two votes start empty.

## Resolution rules

- Unique plurality in initial vote: `initial_plurality`.
- Positive tied highest count in initial vote: consensus for 20 seconds, then a fresh final voting round for 30 seconds. Closed first-round totals and tied choices are shown after that round closes.
- Unique plurality in final vote: `final_plurality`.
- Positive tied highest count in final vote: `ai_tie_break`, selecting the existing authored recommendation, even if the recommendation was not one of the tied choices.
- Zero valid votes in either round: `no_vote_ai_fallback`, selecting the authored recommendation. This is distinct from a tie-break, with all nonresponses counted as abstentions.

Decision stores the chosen ID, reason, deciding round ID, totals, abstentions, and whether it follows the recommendation. Both fallback reasons are explicitly explained in the UI. There is never a third voting round. Metrics remain unchanged and Crisis 01 remains loaded.

## Verification commands and results

Run from repository root:

- `.venv/bin/python -m pytest backend/tests -q`: **74 passed**, including all 44 pre-existing tests. One existing Starlette/httpx TestClient deprecation warning; no failures.
- `npm --prefix frontend run typecheck`: **passed**.
- `npm --prefix frontend run build`: **passed**, including TypeScript; Vite built 34 modules.
- `.venv/bin/python -m pip check`: **No broken requirements found**.
- `git diff --check`: **passed**.
- `.venv/bin/python backend/tests/smoke_milestone3.py`: **passed**, using temporary real Uvicorn, HTTP, two real WebSocket clients, and production 60s/20s deadlines without clock overrides. Verified mission creation/join, shared briefing and private intelligence separation, discussion chat, automatic voting, hidden own-vote projection, initial tie, consensus chat, fresh final votes, AI tie-break (A selected with B=1/C=1), unchanged metrics, and actual reconnect after decision lock. Temporary server terminates in cleanup.

Tests use controlled clocks for all 60/20/30-second rules, exact-deadline precedence, duplicate/stale ticks, missing/no votes, fresh final votes, all supported initial tie distributions, 2–1–1 plurality, final plurality, AI tie-break, unauthorized/invalid/duplicate/stale votes, one vote per multi-role seat, private projections, chat phases/limits/retention/rate/identity, reconnect across phases, live transport error handling, state-lock availability during network waits, and scheduler shutdown. Deterministic transport tests exercise the production tick path with injected time, without long sleeps.

The final diff was reviewed against the starting milestone implementation. Earlier implementation/refinement work and existing tests were preserved. No commit, tag, or push was performed.

## Known limitations and manual review

No browser rendering or physical-device testing was performed. Playwright/Puppeteer and a frontend test suite are not configured in this checkout. Review desktop/tablet/mobile layouts, radio-card interaction, multi-tab feedback, and chat scrolling/accessibility in real browsers. Chat renders a bounded scrollable history; there is no unread-message indicator or automatic scroll-to-latest behavior.

Existing mission memory is lost on restart; there is no host transfer, mission expiry, seat removal, or distributed coordination. The wall-clock source assumes a reasonably maintained server clock; large system clock adjustments can affect real elapsed durations. Timer and race rules are tested with injected time. No Milestone 4 feature or new infrastructure/dependency is included.

Milestone 3 is ready for code review on automated and real-transport verification, with visual browser/mobile acceptance still outstanding.

## Critical gameplay fix — consensus and final-vote discoverability

### Reported failure and root-cause investigation

A real three-player test reported A/B/C → initial 1–1–1 tie → consensus with no usable chat/final-vote controls → zero final votes, three abstentions, and no-vote AI fallback. That outcome is not a successful interactive-gameplay check.

Tracing the current implementation found a concrete frontend ordering/discoverability defect: the active chat and response controls were children of CrisisBriefing, below Operations Room, metrics, public briefing, and private intelligence. The chat composer was additionally below retained history. Phase updates neither moved focus nor brought the new controls into view. The final round used a small generic phase label and “Submit private vote,” without a prominent final-round heading. A player could therefore remain far from the time-limited interaction even while receiving valid server updates.

The backend trace found no skipped-round mechanism in this path. An initial positive tie opens consensus at `now + 20`; expiry opens a new round ID with empty votes, the same three eligible seats, and a fresh `now + 30` deadline. Only a subsequent expiry (or all fresh votes) resolves that round. Both WebSocket chat handling and React chat enablement already permit `consensus_window`; previous `your_vote` state does not govern chat. First-round submission state is replaced on opening the final round.

New three-seat controlled-clock/protocol checks and a real production-clock run confirm those transitions. They do not reconstruct the original browser session: no original server trace, browser event log, or screenshot was available. Thus the confirmed defect is buried interactions and lack of transition guidance; the precise reason a particular original browser could not send chat cannot be established retrospectively. There is no basis to claim that the original final countdown was skipped. In the live regression, every seat received a final deadline with approximately 30 seconds remaining, and the rendered React snapshot displayed 00:30.

### Corrective changes

- App renders a single ActiveGameplay region immediately below the compact mission header, ahead of the roster, metrics, and crisis intelligence.
- Discussion shows its deadline and live chat there. Consensus shows its deadline, tied options, first-round totals, the notice “Discuss your choices. Final voting begins when this countdown ends.” and live chat there.
- The chat composer precedes bounded history, so existing messages cannot push it out of the active panel.
- Initial/final voting shows the timer and all three response cards in that region. Final voting has the prominent “Final Vote — 30 seconds” heading, “Submit Final Vote” button, and explicit submitted confirmation. The submit area is sticky within the voting panel, and controls retain mobile-friendly sizing.
- The response component is keyed by the authoritative round ID, ensuring a fresh local selection on revote; submission state still comes only from the current round's viewer-private `your_vote`.
- On phase/round change, an effect focuses the active region and scrolls it into view. Chat arrivals, vote progress, and presence-only snapshots do not retrigger the effect. The section receives focus without automatically opening a mobile keyboard.
- Decision lock shows the actual collective result before secondary information. Reference choices and read-only historical chat remain accessible below, with no duplicate active controls. Operations Room descriptions now match the phase.
- No backend application, deadline, eligibility, privacy, socket contract, or resolution rule was changed by this fix. No Milestone 4 feature or dependency was added. Earlier uncommitted Milestone 3 work is preserved.

### Regression tests and verification

New `backend/tests/test_consensus_regression.py` covers three-player A/B/C, exactly 20 seconds of consensus, writable shared chat, fresh per-seat final votes, a full 30-second opportunity, separate round records, 2–1 final plurality, a final 1–1–1 AI tie-break, and a zero-vote fallback only after expiry. It also verifies that even a very late consensus tick opens a fresh 30-second final window rather than skipping it. HTTP/WebSocket coverage verifies consensus chat broadcasts, phase delivery to all three seats, actual disconnect/reconnect during consensus and final voting, restored own vote/deadline, and B/B/A → B with zero abstentions.

New `frontend/tests/gameplay.test.tsx` renders the actual App and gameplay components with deterministic per-viewer server snapshots. It checks active DOM order, enabled consensus composers for all three previous-vote holders, fresh unselected final radio controls, final heading/submit button placement, confirmation/disabled state after submission, disconnected-state gating, read-only voting chat, no duplicated panels, and result placement. The runner uses Node's built-in test runner, React server rendering, and already installed esbuild, with no new dependency. Only the transport/session hooks are replaced with fixture sources for these rendering tests; production code is unchanged. These are rendered-markup tests, not mounted browser interaction or viewport tests.

Commands and results:

- `npm --prefix frontend test`: **6 passed**. The first test run was 5/6 because a new assertion assumed React's HTML attribute order; the assertion was corrected to inspect the input tag independent of attribute ordering. Final runs pass.
- `.venv/bin/python -m pytest backend/tests -q`: **79 passed**, including the 74 pre-existing cases. The existing Starlette/httpx TestClient deprecation warning remains.
- `npm --prefix frontend run typecheck`: **passed**.
- `npm --prefix frontend run build`: **passed**, 34 modules.
- `.venv/bin/python -m pip check`: **No broken requirements found**.
- `git diff --check`: **passed**.
- `.venv/bin/python backend/tests/smoke_milestone3.py`: **passed**. Smoke now uses three actual WebSocket clients and unchanged production timers: 60-second discussion → A/B/C → 20-second consensus with chat → fresh final-round broadcasts to all three seats with a full 30-second deadline → B/B/A → B by `final_plurality`, zero abstentions, unchanged metrics, and reconnect recovery. No zero-vote fallback was counted as a smoke-test success.

The targeted changes were reviewed for scope. No commit, tag, or push was performed.

### Remaining browser/mobile checks

No Playwright, Puppeteer, jsdom, or browser interaction harness is installed in this checkout. No browser/physical-device verification was performed. Rendered markup and protocol checks do not prove actual scroll geometry, focus behavior, touch interaction, or radio/button clicks. Re-run the original three-browser A/B/C → consensus chat → B/B/A sequence at desktop and mobile widths, including starting a transition while scrolled down in private intelligence, typing/sending consensus chat, and checking the visible final countdown. Confirm focus moves once per phase and does not interrupt chat typing as messages arrive.

Implementation and automated/protocol verification are complete; real-browser acceptance of the corrected interactive layout remains outstanding. The original report is preserved above rather than retroactively described as a successful browser test.
