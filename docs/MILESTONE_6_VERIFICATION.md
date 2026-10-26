# Milestone 6 verification

## Reconnaissance findings (recorded before implementation)

The existing FastAPI MissionStore owns in-memory missions, automatic roles, clocks, votes and metrics. CrisisResult is an exactly-once ledger keyed by deciding round ID; before/after metrics, authored/applied deltas and chosen outcome are already copied at resolution. Only the current result is projected. Public crisis context, all available choice descriptions and prior initial/final tallies are not retained in the result; live rounds reset at the next briefing. There is no timeline or terminal mission summary contract. Completion requires the existing host acknowledgment; collapse happens immediately after consequences. Victory score is already the arithmetic mean; failed missions currently leave the live consensus_score field unset.

The React App renders terminal states through its current-decision UI and archived chat. useLobby replaces mission state from WebSocket snapshots. Delivery is already ordered by a server delivery lock, but there is no explicit client stale-snapshot guard. Private intelligence is projected per seat and must remain excluded from shared history. Chat uses the Milestone 5.1 isolated scroll controller. Existing tests use deterministic clocks, TestClient WebSockets, live Uvicorn smokes and React server-rendered markup. The working tree was clean before this milestone.

Planned extension: enrich the existing ledger rather than maintain a parallel history; capture starting metrics once at mission start; derive timeline and terminal statistics from copied result records; project public history through the existing authorized snapshots; add a lightweight monotonically increasing publication revision for stale-event protection; present a terminal review with native expandable entries, SVG metric trends and an accessible data table. Keep the live game state machine and memory-only lifecycle.

## Final history contract and backend behavior

The existing `Mission.results` ledger is the sole source of finalized history. `CrisisResult` now also stores:

- Public crisis briefing and an ordered tuple of `PublicChoice` records (ID, title, description).
- Authored AI recommendation ID.
- An ordered tuple of `RecordedRound` records: round ID, initial/final number, public totals, abstentions and eligible-seat count.
- Explicit `consensus_window_occurred`, `final_vote_occurred` and `status` (`resolved` or `collapsed`).

Existing fields retain sequence number, stable crisis ID, title, chosen label/description, outcome, deciding method/totals, and before/authored/applied/after metrics. No individual votes, voter IDs, credentials, role intelligence, future crises or unexecuted consequence narratives are added to the history contract.

The recorder still runs only through the existing `_apply_consequences` handoff under the state lock. It validates/copies the complete result before appending and checks the deciding round ID before applying anything again. The collapse-causing result is appended with its zero metric before the failed phase is published. A tied initial vote is not a finalized crisis and does not append a partial record; its closed tally is copied together with the final tally when a decision resolves. No-vote fallback retains zero tallies and actual abstentions, rather than fabricating a tie or final vote. The plurality, 60/20/30-second timers, acknowledgment and role rules are unchanged.

Result/public-choice/round models forbid field reassignment through frozen Pydantic models. Tuples preserve ordered record collections. Nested metrics, decision totals and round totals are copied away from live objects; projection serialization produces independent copies. These protect historical records from later gameplay mutations; nested Pydantic metrics/dictionaries are not claimed to be recursively immutable against arbitrary internal Python code. Tests mutate live metrics, decisions, tallies, authored context and returned dictionaries without changing recorded history.

`Mission.initial_metrics` captures the actual starting values once at start. The projected `metrics_timeline` derives Start plus every result's after-snapshot, including an early collapse. There is no independently mutated timeline or client reconstruction of applied deltas.

Authorized state snapshots now include three sibling fields:

| Field | Availability / source |
|---|---|
| `history` | Chronological serialized public result ledger, empty before resolution |
| `metrics_timeline` | Empty before start; initial snapshot plus each recorded after-snapshot |
| `summary` | Null until `completed` or `failed`; derived terminal outcome/counts/metrics/score/statistics |

The summary references the sibling history/timeline through the common mission envelope rather than copying the whole ledger a second time into itself. It contains victory/defeat, resolved crisis count (including the crisis causing defeat), configured total, final metrics, Consensus Score, consensus-window count, final-vote crisis count and a breakdown of initial plurality, final plurality, final AI tie-break and no-vote fallback. Counts come only from recorded results.

The existing average formula is extracted into `consensus_score(metrics)` and used for both victory and review summaries. The prior live `consensus_score` field remains null for a defeated mission; its terminal summary includes the numerical final average. The UI explicitly labels that state defeat. Victory still waits for host acknowledgment of the tenth result; no premature completion or eleventh crisis was introduced.

## Synchronization and access boundaries

The existing authenticated WebSocket snapshots carry the same shared history, timeline and summary to every seat; current private intelligence and own-vote filtering remain unchanged. There is no history-write endpoint. Extra history fields on vote/continue intents are rejected by existing input validation. Mission-member projection authorization and credential boundaries remain in force.

Each publication increments an integer `revision` under the existing state lock, with the existing delivery lock continuing to prevent old server broadcasts overtaking newer snapshots. The client `SnapshotOrder` accepts only increasing revisions and replaces the whole authoritative snapshot; it never appends/merges history. Duplicate or older snapshots therefore cannot regress finalized results. useLobby also ignores callbacks from obsolete sockets. Revision tracking survives socket retries within a session and resets with a new session effect. Legacy snapshots lacking revisions are accepted only before any revisioned snapshot has been accepted.

Reconnection receives the whole finalized ledger through the normal snapshot. Mission history has exactly the same **memory-only lifetime** as the mission. A backend restart loses it. No database, persistent archive, account, analytics service or new dependency was added.

## Frontend review

`MissionReview.tsx` provides a dedicated terminal screen whenever the authoritative terminal summary is present:

- Clear Civilization Survived / Civilization Collapsed outcome, completed/configured count, server score and final values for all four canonical metrics.
- A four-series SVG chart with labels, consistent colors and distinct solid/dashed patterns. Start and every resolved crisis are marked; per-point titles and an exact-value table give non-color access to every value.
- Native closed-by-default `details`/`summary` entries in server chronological order. Compact summaries show crisis, chosen action, resolution method and actual deltas. Expanded content shows original public context, all three choices, AI marker, separate initial/final tallies, abstentions, consensus/final-round flags, outcome/status and before/change/after values.
- Cooperative team totals from the server summary, without player rankings or invented individual voting attribution.

The terminal branch omits chat/composer, voting, progression controls and private intelligence panels. Existing brand navigation and a return-to-mission-creation link remain; no replay workflow is added. Review focus/scroll runs once on entering that screen, while existing active-phase focus and smart-chat code remain unchanged. Legacy fixtures/snapshots without the new summary retain the prior outcome screen; missing optional historical context within a review displays unavailable/not-recorded text rather than invented values.

CSS is scoped to the review. Wide charts and tables have labeled, keyboard-focusable inner horizontal scroll regions. A 560px chart minimum keeps labels readable instead of shrinking them to tiny phone-size text; the containing page stays bounded. Final-metric/statistic grids collapse to one column below 400px. Native details have touch-friendly summary targets and no client mutation or network action. Physical keyboard, screen-reader, chart scrolling and native details interaction still require browser acceptance.

## Tests and exact commands/results

Commands below run from the repository root. No established test assertions were removed or weakened.

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest backend/tests/test_history.py -q` | **15 passed**, one existing Starlette/httpx TestClient deprecation warning |
| `.venv/bin/python -m pytest backend/tests -q` | **182 passed**, same one existing warning |
| `npm --prefix frontend test` | **46 passed, 2 optional captured-snapshot acceptance cases skipped** |
| `.venv/bin/python backend/tests/smoke_milestone6.py > /tmp/ce-m6-smoke.log` | **PASS**, real Uvicorn/HTTP/three WebSocket clients; 20x injected clock |
| `.venv/bin/python backend/tests/test_chat_acceptance.py` | **PASS**, refreshed chat acceptance snapshots for regression replay |
| `MISSION_REVIEW_FILE=/tmp/ce-m6-live.json CHAT_ACCEPTANCE_FILE=/tmp/ce-chat-5-1.json npm --prefix frontend test` | **48 passed**, no skips, including both captured-snapshot acceptance cases |
| `npm --prefix frontend run typecheck` | Passed |
| `npm --prefix frontend run build` | Passed; 41 modules; JS 255.92 kB, CSS 9.46 kB |
| `.venv/bin/python -m pip check` | No broken requirements found |
| `git diff --check` | Passed |

Backend additions cover actual starting snapshots, all four resolution methods, 2–1–1 plurality, 1–1–1 initial tie without premature recording, separate final tally and abstentions, exactly-once callbacks/acknowledgment, actual clamping, protection from later mutation, mission isolation, membership, rejected client history injection, shared publication revisions, full ten-crisis victory, early collapse, chronology, privacy and terminal reconnect equality. Existing 167 tests remain, including 2/3/4-player production campaigns and chat tests.

Frontend additions cover victory/defeat, authoritative score, absence of terminal gameplay controls, all four timeline series and exact data table, native expandable markup, before/after and voting labels, authoritative team counts, chronological escaped content, unavailable optional fields, restored review equality, mobile CSS boundaries, duplicate/out-of-order revision rejection and rendering the actual live terminal snapshots. Existing 34 ordinary tests and optional chat replay remain.

The test environment uses real React server rendering plus pure ordering/controller tests and explicit CSS contract checks. Native details are verified as real `details`/`summary` markup, closed by default; no simulated toggle is presented as a real browser interaction. No DOM layout engine, screenshots, touch or physical-device testing was used.

## Live multiplayer evidence

The new smoke reuses the existing three-client campaign driver, with an optional observation callback that leaves its earlier assertions intact. It starts a real temporary Uvicorn server with production content and the established 20x injected clock, without changing any production duration constants.

**A — Full victory:** path `BBBCCBCAAC` completes ten crises. History contains ten unique, ordered finalized records; timeline contains Start plus ten snapshots. Final metrics are **Infrastructure 63 / Public Trust 55 / Economy 53 / Safety 52**, score **55.75**. Shared history/timeline/summary are identical across all clients. Summary breakdown: **8 initial plurality, 1 final plurality, 1 final AI tie-break, 0 no-vote fallback; 2 Consensus Windows and 2 crises with final voting**.

**B — Early defeat:** separate path `BAAA…` collapses Economy at Crisis 4. The failed crisis is included as the fourth history entry with status collapsed and Economy 0; timeline contains Start plus four snapshots. Summary score **54.5** does not change its defeat outcome. Host advancement is rejected. No victory or later crisis is published.

**C — Consensus:** Crisis 2 uses A/B/C initial tie and B/B/A final plurality. Crisis 4 uses A/B/C twice and executes its authored AI C recommendation. Both initial and final tallies survive into terminal history.

**D — Reconnect:** the driver closes/reopens a guest socket at Crisis 6 discussion, Crisis 8 after its vote, and Crisis 9 result. It also opens a fresh authenticated socket after terminal closure. The history, summary and timeline are identical to the finalized records; later reconnects do not reapply consequences. Victory and defeated states both restore correctly.

Evidence is reproducible with the smoke command; its terminal public payloads are written to `/tmp/ce-m6-live.json` and rendered by the optional frontend acceptance test. The chat acceptance regression also passes through discussion, rejected send, voting and next-crisis origin labels. These are actual backend network/transport checks and rendered UI checks, **not manual browser multiplayer acceptance**.

## Known limitations and deferred acceptance

No new real-browser, mobile-device or screen-reader acceptance was performed. Verify the terminal review at roughly 360/390px widths and on desktop: native details keyboard/touch toggling, chart/table inner scrolling, value readability, focus on entering terminal state, brand/return navigation, and restored terminal review on refresh. Recheck active voting visibility and smart chat on an ordinary run. Existing rendered/CSS checks do not prove physical layout or focus behavior.

History/revisions live only in the server process. There is no cross-restart persistence, downloadable archive, public sharing or player analytics. Unresolved crises have no finalized history entry, and current hidden vote contents remain private. No historical role-intelligence reveal or individual voter attribution was introduced. Broader deferred MVP work (disconnect timeout/role redistribution, randomized pool/weakest-metric finale, QR/replay, durable storage and deployment hardening) remains outside scope. No rules, content files or production timers changed.

## Exact changed files

Created:

- `backend/tests/test_history.py`
- `backend/tests/smoke_milestone6.py`
- `frontend/src/MissionReview.tsx`
- `frontend/src/snapshotOrder.ts`
- `frontend/tests/missionReview.test.tsx`
- `docs/MILESTONE_6_VERIFICATION.md`

Modified:

- `backend/app/domain.py` — extend existing ledger, initial snapshot and publication revision.
- `backend/app/missions.py` — copy finalized public history; derive timeline/summary.
- `backend/app/consequences.py` — share the unchanged average score formula.
- `backend/app/connections.py` — increment ordered publication revision under the state lock.
- `backend/tests/smoke_milestone5.py` — optional observer for reuse, preserving all existing smoke assertions.
- `frontend/src/types.ts` — history/summary/timeline/revision contracts with legacy fixture compatibility.
- `frontend/src/useLobby.ts` — reject duplicate/stale snapshots and obsolete-socket callbacks.
- `frontend/src/App.tsx` — route terminal summaries to read-only review.
- `frontend/src/styles.css` — scoped terminal review presentation.
- `frontend/tests/gameplay.test.tsx` — include new tests in the existing runner.

No commits, tags or pushes were created. Milestone 6 implementation and automated verification are complete; manual browser/mobile acceptance remains pending.
