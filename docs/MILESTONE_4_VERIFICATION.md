# Milestone 4 — consequences and configured progression

## Reconnaissance and boundary

Read AGENTS.md, README, product specification, foundation/Milestone 2/Milestone 3 verification history, existing domain/store/content/transport/UI, and relevant rule/transport/rendered tests. The repository already had four bounded Metrics initialized to 70, authored Choice.consequence and Choice.metric_deltas, one validated Crisis 01 JSON, stable seat credentials, role-filtered snapshots, and one locked in-memory store. All four decision reasons converge in MissionStore._resolve. That is the sole Milestone 3 → Milestone 4 handoff; voting/chat/timer rules are retained.

Only Grid Under Pressure is currently authored. Production sequencing is deterministic as requested for this milestone, rather than implementing the broader MVP's randomized pool/weakest-metric finale. Existing role ownership/order had no per-crisis variation mechanism; ownership and presentation order are preserved, with no role reassignment.

## Architecture and authoritative data flow

1. Existing voting resolves to a Decision: initial plurality, final plurality, AI tie-break, or explicitly labeled no-vote fallback.
2. Under the same state lock, _resolve immediately invokes _apply_consequences. No client request calculates or applies effects.
3. The selected authored choice provides the public narrative and all four deltas. Values are clamped to 0–100, then checked for zero. A typed CrisisResult records the immutable event ID, crisis identity/number/title, executed title/description, decision context/aggregate totals, narrative, before/after values, authored deltas, and actual applied deltas.
4. Surviving results reuse decision_locked as the distinct durable consequence/result phase. This completes the existing stopping phase rather than adding another near-identical phase. There is no deadline on result review. All clients receive the same public result and metrics; observers never apply it locally.
5. The host acknowledges the exact result via POST /api/missions/{token}/continue with the existing X-Mission-Session credential and strict JSON {"result_id":"<server result ID>"}. The server moves to the next briefing, or completes the mission after review of the final configured result. All occupied seats must be connected to advance, matching existing start/discussion safeguards.

Completion deliberately occurs after host acknowledgement of the final result. “Finish mission” replaces “Next crisis” on that result. There is no hidden automatic advance and no fleeting result screen. Collapse, in contrast, is immediate and does not wait for acknowledgement.

The existing transport lock covers all mutations. Socket sends still happen after releasing that lock. No new infrastructure, dependencies, deployment changes, accounts, or public debug/fixture controls were introduced.

## Civilization state and exactly-once protection

Metrics begin at 70 when the Mission is created and remain mission-wide state. Advancing never reinitializes them. CrisisResult.before/after are independent copies so later metrics cannot rewrite earlier results. Internal results retain public decision/impact history; only the current crisis's result is projected.

The deciding voting-round ID is the stable consequence event key. _apply_consequences first checks the result ledger for that key and returns the stored result on a repeat. It validates/builds a complete new result before publishing metric mutations. _resolve also ignores callbacks outside voting, so stale callbacks cannot revive a failed/completed mission or re-resolve a finished round. Ordinary reads, broadcasts, socket reconnects, and refreshes only project state.

Continuation separately deduplicates acknowledged result IDs under the same lock. Repeating a previously acknowledged result returns {"advanced":false}, including when a later crisis is waiting on its own result. Unknown/mismatched IDs and invalid phases are rejected. Non-hosts cannot advance, even with a valid result ID. Concurrent duplicate requests advance exactly one index. Stale vote IDs cannot match a new crisis's newly generated voting-round ID.

“Persistent” means across crises and refresh/reconnect in the running process. There is no durability across server restarts; this retains the approved in-memory architecture.

## Sequence and reset policy

backend/app/content/sequence.json currently contains ["grid-under-pressure"]. The existing package-data wildcard includes this manifest. The content loader checks a nonempty, nonrepeating list of safe IDs, validates all referenced crises, and checks file/declared ID agreement before mission mutation. Each mission snapshots its configured sequence independently.

To add another production crisis, author a validated JSON and append its ID to the manifest; no progression code changes are required. Production does not contain a fabricated Crisis 02. Test fixtures supply additional crises exclusively through create_app/MissionStore's Python-side loader injection, not an HTTP option.

On Next crisis, the server increments the index once, loads the next sequence entry, enters briefing, clears current voting rounds/decision/deadline, and publishes no stale result as the new crisis's result. It preserves seat identity, roles, metrics, and mission chat history/rate limits. Begin discussion then creates a fresh 60-second deadline; voting round numbers restart at one, with new IDs and empty votes. New intelligence is projected only for that seat's existing roles. Frontend crisis numbers/counts come from the server, replacing fixed “Crisis 01” labels.

## Collapse and completion

After clamping, any zero value immediately sets failed and records every collapsed metric. The final result and final values remain available on reconnect. Failed missions cannot continue, discuss, vote, or post chat. The top result panel displays GAME OVER — CIVILIZATION COLLAPSED, named collapsed metrics, the causing choice/outcome, and final values.

When the host finishes the last surviving configured result, the server sets completed and stores Consensus Score = sum(final metrics) / 4. The index remains on the final existing crisis. Completed missions cannot advance into a nonexistent crisis or reopen discussion/voting. The terminal result and score remain authoritative on reconnect. Tests cover configured lengths 1, 2, and 10. The current production sequence is a one-crisis demonstration, not the completed ten-crisis v0.1 game.

## UI and privacy

The phase-first layout from the critical Milestone 3 fix is preserved. Result/collapse/completion remains above roster/metrics/intelligence. The result shows the executed response, authored narrative, vote resolution and aggregate counts, all four before → after values, signed applied changes, and current state. If clamping changes a delta, the UI labels the authored delta separately. Names, arrows and numeric signs convey impact without relying on color. The score is formatted from the server value; React never calculates consequences, failure, victory, or the next crisis.

The internal Mission/sequence/results collection is never serialized wholesale. The public CrisisResult DTO contains no role intelligence, credentials, future crisis data, or seat-to-choice vote maps. Only the executed choice's consequence/deltas are published. The existing viewer-private intelligence and own-vote filtering remains unchanged. No individual hidden votes are added to results. Voluntarily shared mission chat remains public history across crises.

## Exact files changed for Milestone 4

- README.md — current scope, consequence/progression policy, test command and production-content limits.
- backend/app/content/sequence.json — production authored sequence manifest.
- backend/app/crises.py — validated packaged sequence loading.
- backend/app/domain.py — CrisisResult, ContinueRequest, sequence/index/result ledger and terminal state fields.
- backend/app/missions.py — exactly-once handoff, clamped effects, result snapshots, collapse, guarded continuation/completion, projection fields.
- backend/app/main.py — strict host continuation route and Python-side fixture-loader injection.
- backend/tests/test_milestone3.py — replace the now-obsolete “metrics remain 70 after resolution” assertion with exact authored result values; preserve voting/phase assertions.
- backend/tests/smoke_milestone3.py — assert authored B effects/result instead of unchanged post-decision metrics.
- backend/tests/test_milestone4.py — deterministic rules, concurrency, privacy, progression, reconnect and synchronization coverage.
- backend/tests/smoke_milestone4.py — live HTTP/WebSocket fixture acceptance.
- frontend/src/types.ts — authoritative crisis/result/terminal DTOs.
- frontend/src/ConsequenceOutcome.tsx — narrative, impact table, collapse names, score, host acknowledgement controls.
- frontend/src/Gameplay.tsx — result/terminal phase rendering and stored executed-choice data.
- frontend/src/App.tsx — result acknowledgement intent, dynamic crisis identity, phase descriptions and current metric labels.
- frontend/src/CrisisBriefing.tsx — authoritative crisis number.
- frontend/src/styles.css — restrained result-table/score styling and narrow-screen table spacing.
- frontend/tests/gameplay.test.tsx — expanded result/terminal fixtures and five rendered consequence/progression checks.
- docs/MILESTONE_4_VERIFICATION.md — this report.

Authored Grid Under Pressure JSON, existing session/WebSocket hook, connections implementation, pure plurality calculator, product spec/AGENTS, and historical reports are not modified by this milestone. No unrelated working-tree changes were removed. No commit, tag, or push performed.

## Automated verification

Commands run from repository root:

| Command | Result |
| --- | --- |
| .venv/bin/python -m pytest backend/tests -q | 102 passed; one existing Starlette/httpx TestClient deprecation warning |
| npm --prefix frontend test | 11 passed (six prior rendered checks plus five new checks) |
| npm --prefix frontend run typecheck | Passed |
| npm --prefix frontend run build | Passed; strict TypeScript and Vite, 35 modules |
| .venv/bin/python -m pip check | No broken requirements found |
| git diff --check | Passed |
| .venv/bin/python -m pip wheel --no-deps --wheel-dir /tmp/consensus-m4-wheel ./backend | Passed; inspected wheel archive and confirmed manifest plus Crisis 01, no fixture sequence |
| .venv/bin/python backend/tests/smoke_milestone4.py | Passed; live automated acceptance described below |

All 79 earlier backend cases remain, with one post-resolution expectation updated to match the new authored consequences. The new 23 cases cover every decision reason, exactly-once reprocessing, each metric's upper/lower clamp, immediate collapse, multiple zero metrics, sequence independence, stale vote rejection, immutable result snapshots, preserved roles/private filtering, configured lengths, host/phase/presence/extra-field guards, simultaneous duplicate HTTP acknowledgements, and synchronized result/progression/collapse/completion with refresh/reconnect.

Rendered React checks verify result placement, narrative and signed deltas, before/after values, clamping labels, host-only Next crisis/Finish mission controls, dynamic Crisis 02 presentation, server-provided score, and disabled/absent active controls after terminal states. These are rendered-markup checks, not a browser click or geometry test. No standalone linter/formatter is configured; existing TypeScript/build/whitespace checks were used.

## Automated live multiplayer acceptance evidence

smoke_milestone4.py starts a temporary real Uvicorn process, creates three real WebSocket clients, and uses the built HTML/API. It injects a test-only two-crisis fixture and a 10x clock so the 60/20/30 constants remain untouched while waits shorten. No fixture route is shipped. The server is terminated in cleanup.

Passed sequence one:

1. Fresh three-seat mission: every metric 70.
2. Crisis 01 B/B/A: initial plurality B, zero abstentions.
3. All clients receive one identical result and metrics 75 / 67 / 63 / 72.
4. Two refresh observers restore identical metrics/result with no reapplied effects.
5. Host continues to fixture crisis two; duplicate acknowledgement cannot skip ahead.
6. All clients retain those metrics, seats and authorized intelligence; prior vote/decision/result fields are cleared.
7. Fresh discussion and A/B/C initial tie → consensus chat → fresh B/B/A final vote.
8. Final plurality B produces 76 / 65 / 66 / 68; Finish mission stores score 68.75.
9. Actual terminal reconnect restores completed state and the exact final result.

Passed sequence two:

1. A/B/C initial tie → consensus chat → A/B/C final tie → AI tie-break A.
2. One result applies A effects: 78 / 62 / 72 / 64; repeat refreshes do not change it.
3. Next fixture crisis C/C/A resolves C, with fixture safety delta -100.
4. All clients receive failed, collapsed safety, and final metrics 79 / 60 / 75 / 0.
5. Continue is rejected; actual terminal reconnect restores the same collapse/result.

The existing production-clock Milestone 3 smoke is also rerun against the new handoff, exercising the full real 60-second discussion and 20-second consensus with three clients; its final verification outcome is recorded in the completion addendum below.

## Manual browser acceptance and deferred work

No manual browser, browser automation, or physical-mobile testing was performed. The environment has no configured Playwright/Puppeteer harness. Real sockets prove protocol behavior; rendered tests prove markup branches, not actual focus/scroll geometry, clicks, touch targets, or assistive-technology behavior. Manual review should repeat the three-browser cycle, compare all result tables/metrics, refresh in result/terminal phases, and exercise Next crisis with a controlled fixture build.

Only one production crisis is authored. The engine is ready to consume a larger configured pool, but production Crisis 02 and the remaining content are not fabricated here. Broader randomized/weakest-metric sequencing, role presentation variation, five-minute removal/redistribution, host transfer, QR invitations, replay controls, and any next-milestone content remain deferred. In-memory state is lost on restart and requires one worker. Authored metric values remain subject to future play-balancing. No analytics, LLM integration, database, or deployment change is included.

## Completion addendum

The final check set passed again: 102 backend tests, 11 rendered frontend tests, strict TypeScript, production build (35 modules), pip check, and git diff --check.

`.venv/bin/python backend/tests/smoke_milestone3.py` also passed with the actual production 60-second discussion and 20-second consensus: three-seat A/B/C initial tie → shared consensus chat → a fresh final round broadcast with 30 seconds available → B/B/A → B by final plurality → exactly one authored B consequence/result → same-seat reconnect. Expected post-result metrics are now 75 / 67 / 63 / 72, replacing only the obsolete pre-Milestone-4 smoke expectation of unchanged 70s.

Both automated live smoke servers shut down via their cleanup paths. No browser/mobile acceptance is claimed. Implementation and automated/protocol verification are complete and ready for review; full ten-crisis content and the deferred features above are not represented as finished.
