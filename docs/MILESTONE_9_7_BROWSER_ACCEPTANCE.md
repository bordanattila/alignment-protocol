# Milestone 9.7 — Browser gameplay acceptance and preparation UX

## Pre-change architecture and tooling audit

Recorded before application modifications. React/Vite renders authoritative WebSocket projections through `MissionConnection` and `useLobby`. Local storage retains a credential per invite token; independent browser contexts therefore provide independent player identities. Mission creation/joining use the existing HTTP forms, and WebSockets authenticate in the first frame. Backend role assignment, hidden voting, host acknowledgement, deadlines, metrics, admission and recovery remain authoritative. Briefing/private panels, voting/Consensus Window/result UI and final narrative/history/chart components are already covered by Node-rendered component tests; those are not browser acceptance.

The Milestone 9.6 lifecycle starts inference after host acknowledgement, outside the state lock, with no pre-generation. Preparation retains the prior public result and hides future crisis/private intelligence. Existing smoke servers inject fake providers and use isolated SQLite/controlled clocks; these patterns can be reused without changing production settings or timers.

Environment: Ubuntu 24.04 under WSL, Node 20.19.5. No Playwright dependency is present in this repository, but an existing external Playwright 1.64.1 runtime and cached Chromium are installed. The first Chromium launch failed with `libnspr4.so` missing; `ldd` identified only NSS/NSPR libraries missing. `apt-get download libnspr4 libnss3` and `dpkg-deb -x` supplied these into `/tmp/ce97-browser-libs/runtime`, without installing system packages or changing app dependencies. A second real-browser probe succeeded: **Chromium 156.0.8078.4**, three independent contexts, screenshots, console observation, ARIA snapshots and viewport changes supported. Headless browser acceptance is feasible. No real screen reader, physical phone, or human speech inspection is claimed. Axe is not installed; native browser accessibility/DOM inspection will be used rather than adding an app dependency.

Runtime used for this audit:

```bash
export CONSENSUS_PLAYWRIGHT_MODULE=/tmp/claude-1000/-home-attila-unix-projects-new-protfolio/21ff37d3-b193-4d44-a6e1-db24618c60df/scratchpad/pw/node_modules/playwright/index.mjs
export CONSENSUS_CHROMIUM=/home/attila_unix/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome
export LD_LIBRARY_PATH=/tmp/ce97-browser-libs/runtime/usr/lib/x86_64-linux-gnu
```

The reusable runner will also support a normally installed `playwright` runtime and an explicit browser path. Chromium is headless with a temporary profile; this environment's Playwright launch disables the browser sandbox. Use only isolated local synthetic data here. Screenshot export masks private panels, invite/session URLs, chat and submitted vote content; raw browser diagnostics/database stay in a protected temporary directory. Existing acceptance/evidence archives are hashed separately and will not be overwritten.

Browser startup plan: build the existing frontend and serve that build through an isolated FastAPI fixture process bound to loopback on a dedicated port, with an injected fake provider, temporary SQLite database and a test-only clock-control interface. No production route, clock constant, provider config or data is modified. A real 26-second fake delay will exercise preparation; controlled deadline jumps accelerate other rounds while retaining the existing configured 60/20/30-second windows. Backend restart means stopping and starting that fixture process against the same isolated database; browser refresh is tested separately.

## Three-player acceptance results

**Real headless Chromium acceptance completed.** The final realistic-delay run is `docs/evidence/milestone_9_7/verified/`. It completed with zero findings, zero browser console errors and zero uncaught page errors. A separate five-second fake regression additionally verifies native Tab navigation; it is not used for the 26-second UX timing results.

Players A, B and C were created through the actual callsign/Create Mission/Join Mission forms in independent Chromium contexts. Distinct credentials and identities were retained only in browser memory/local storage. Tests observed actual WebSocket frames and DOM output; no shared React state object, jsdom or HTML-only renderer was used to simulate players. The observation hook records received state without changing what the app receives. The final runner uses desktop contexts for A/B and touch-emulated 390 × 844 mobile for C, including real browser touch events on C's voting controls.

| Acceptance area | Actual browser outcome |
| --- | --- |
| Create/join/lobby | Three distinct identities, three connected seats, host-only Start control |
| Roles/privacy | Four domains covered with role counts 2/1/1; each frame and DOM contains only the viewer's authorized intelligence; common public content agrees |
| Initial briefing | Rendered title/recommendation/private cards; B reload restores the same identity, roles and public history |
| Clear plurality | B/B/A resolves B immediately; one recorded result and no Consensus Window |
| Three-way initial tie | A/B/C opens the existing 20-second Consensus Window with usable chat |
| Final vote | New round 2 opens for the configured 30 seconds; rendered countdown agrees with the received authoritative deadline within one second |
| Final tie | A/B/C in the final round executes the AI recommendation, with `ai_tie_break` and one additional history entry; no third vote |
| Unauthorized intent | A browser-sent vote containing a spoofed player field is rejected; submitted count remains unchanged |
| Hidden votes | Non-submitting peers retain null own-vote fields; no shared vote map is exposed; screenshots exclude selections/submissions |
| Nonresponse | C goes offline during voting; two B votes plus deadline expiry record one abstention and one result |
| Presence/progression | Missing C is shown disconnected; host's Next crisis remains disabled until reconnection |
| Late intent | C's restored browser submits an old round ID; it is rejected without changing the recorded result |
| Preparation | Prior public outcome, executed choice and metric table remain visible; old vote/Next controls disappear; future crisis/private data remain withheld |
| Failure/timeout | Fake provider unavailable at crisis 3 and timeout-category failure at crisis 4 both admit valid authored fallback; UI reaches a normal readable briefing |

Existing configured discussion/Consensus Window/voting durations remain **60/20/30 seconds**. The fixture advances its clock to deadlines to keep the suite practical; the server still decides every transition. A wall-clock offset lets the clock continue advancing between jumps and across restarts, so refresh does not fabricate a fresh full countdown. The browser tests compare rendered countdowns against received state using that browser's own monotonic clock. No production deadline constants were changed.

The fake valid proposals and effects are controlled fixtures. Authored fallback remains the existing deterministic **mission-seeded** selector: invite tokens differ between new missions, so fallback IDs and final scores can differ between runs. Tests derive expected final metrics/scores from authoritative recorded results and compare them with the rendered UI. They do not assert that different mission seeds produce identical content. No seed, scenario selection, balance or metric rule was changed to force a preferred result.

## Preparation UX and actual browser timing

The host's document remains loaded while other players refresh/reconnect. All following intervals use **one host-browser `performance.now()` clock**, starting at the actual Next crisis click. Receipt is the real WebSocket message event. DOM rendering is observed on an animation frame after the relevant heading/result is present; this is not a measurement of physical display presentation or screen-reader speech.

Final realistic-delay run:

| Browser event | Since host continuation |
| --- | ---: |
| Preparing snapshot received | 15.4 ms |
| Preparing heading rendered | 30.0 ms |
| Recorded outcome visible in viewport | 30.0 ms |
| Next briefing snapshot received | 26,029.6 ms |
| Next briefing observed rendered | **26,045.7 ms** |
| Receipt to observed briefing DOM frame | 16.1 ms |

The previous result stayed available throughout the 26-second pending interval. B refreshed during that interval. C's tab closed before admission and reopened after it; connected A/B received the admitted briefing and C restored the same seat/current crisis. Exactly one fake attempt per crisis slot was retained, including after refresh and restart.

The matching existing server lifecycle sample records:

| Server interval | Seconds |
| --- | ---: |
| Scheduling queue | 0.005415 |
| Generation/service duration | 26.002554 |
| Outcome-ready through admission/commit | 0.006140 |
| Scheduling through admission/commit | 26.014135 |
| Server publication completion | 0.005248 |

These are separate durations with different boundaries. No backend monotonic timestamp was subtracted from a browser timestamp. The server's player-visible/rendering fields correctly remain unknown; the browser probe supplies its own correlated observation. The browser interval also includes intent delivery and client processing/render scheduling. The fixture's intentional 26-second delay is **not a new measurement of `gpt-6-luna` latency**, a performance optimization, or evidence that the exploratory 15-second provider target has been achieved.

Provider failure and timeout were simulated by the injected provider raising the existing categories. The timeout case does not claim a new real 60-second HTTP timeout measurement. Existing backend timeout/cancellation regressions and generation/restart smokes ran separately.

### Instrumentation corrections retained transparently

The first `before/` run incorrectly selected the mission-start preparing event when computing continuation-to-preparation timing, yielding negative early timing fields. Those fields are invalid and are not used here. Filtering events to timestamps at or after the host continuation corrected the correlation; `before-confirmed/` and subsequent realistic runs were repeated with valid correlation. No application behavior was changed to correct this measurement error.

A separate experimental fast keyboard run used only a 50 ms fake delay, too short to perform its pending-preparation refresh sequence. It stopped in that fixture step and is retained as incomplete in `keyboard-regression/`. The distinct quick regression now uses five seconds, omits screenshots, and completed successfully in `keyboard-verified/`. This did not change any production timeout or the canonical 26-second acceptance fixture.

## Refresh, reconnect and actual process restart

| Browser action | Verified preservation |
| --- | --- |
| B reloads briefing | Same identity/roles/current crisis/history |
| B reloads Consensus Window | Same phase/deadline and restored chat |
| B reloads preparation | Same seat, pending state and prior result; no duplicate inference |
| C closes/reopens after admission | Same saved identity and current admitted briefing |
| C disconnects during voting | Accurate presence, one nonresponse at expiry, reconnect restores authoritative result |
| Host disconnects/reconnects | Same host identity and result; controls resume only after connection restoration |
| B opens another tab with saved identity | Existing seat reused; three total players retained |
| Backend stops/restarts during discussion 5 | New real process, same isolated SQLite database, same identities, roles, public history, chat, crisis, phase and original discussion deadline |
| Backend stops/restarts after victory | Same terminal history/outcome and no extra crisis generation |
| B reloads defeat | Same failed mission and recorded collapse |

Restart assertions require fresh revisions beyond pre-stop state, not merely cached DOM. Browser refresh and backend process restart are distinct tests. Offline emulation plus closing the native WebSocket provides a controlled disconnect; this is not a claim about arbitrary packet loss or physical Wi-Fi loss. Existing killed-process pending-generation/restart smokes provide additional real-network coverage separately from browser interaction.

## Rendered victory and defeat reviews

The final realistic run completed ten crises through real buttons, three-player voting and host acknowledgements. The browser rendered:

- Victory: Infrastructure **60**, Public Trust **100**, Economy **59**, Safety **76**; Consensus Score **73.75**.
- A fresh collapse fixture selected bounded negative Infrastructure effects through three actual rounds. Infrastructure clamped to **0**, with final metrics **0/79/73/73** and defeat score **56.25**.

All three rendered reviews were checked against the authoritative score and metric values; history summaries were checked in chronological crisis order. Screenshots show narrative sections, their explicit “AI-generated interpretation” attribution, separate recorded statistics, resolution labels, metric charts, progression tables and expandable decision history. These narratives came from a fake provider, not an LLM quality evaluation. Enter opens a native history disclosure; ArrowRight scrolls the focused mobile metric table. Terminal refresh/restart preserved review content. The final journal has ten main crisis attempts plus one endgame, then three collapse crisis attempts plus one endgame; no crisis inference occurs after either terminal state.

## Responsive layout and accessibility

Rendered briefing, voting, preparation, victory and defeat were evaluated at:

- Desktop **1440 × 900**.
- Tablet **768 × 1024**.
- Mobile **390 × 844**.
- Narrow mobile **320 × 640**.

Final measured document width matched the viewport at all 20 phase/viewport combinations. No critical panel or button extended outside the viewport. Visible radio centers passed native browser hit testing at all four widths; the narrow radio was also selected. Tables intentionally scroll inside labeled focusable regions while the document remains within the viewport. Representative screenshots were visually inspected, including narrow voting, preparation and the review. Long metric words may wrap at 320 px; this remains a dense small-screen presentation, not proof of comfort on a physical phone.

Native Chromium accessibility-tree checks at lobby, preparation, consensus and victory found **zero unnamed controls**. Polite status regions are present for connection/presence/preparation. Rendered countdowns expose readable text, and phase focus provides a predictable navigation start. Space selects a radio; Tab reaches host discussion and radio controls; Enter activates unread jump and disclosure controls; ArrowRight scrolls review tables. The unread control preserves the reader's scroll position until activated and then returns focus to the chat history. Presence updates during preparation do not steal focus.

Sampled opaque computed text foreground/background pairs had minimum contrast approximately **7.20:1** (victory minimum **7.72:1**) with no failures against size-adjusted 4.5/3 thresholds in those samples. This custom check is not a comprehensive WCAG/axe audit: it does not certify gradient compositing, placeholders, every focus/hover state or assistive-technology behavior. Axe was not installed and no new project dependency was added for it. The app provides one dark theme, so a separate light-theme acceptance result is not claimed. Reduced-motion preference was enabled; phase scrolling uses `auto`, and no new animation was added.

No physical-device interaction or actual screen-reader speech was performed. Automated tree inspection and keyboard events do not establish those manual experiences.

## Reproduced defects and exact fixes

### 1. Focus lost during preparation

Reproduce: resolve a crisis, focus/click the host's Next crisis, then observe active element during the 26-second preparation. Before: `BODY`, no named target. Root cause: `ActiveGameplay` excluded `preparing` from its existing focus effect, and the newly retained public result panel had no focus ref/tab target.

Fix: `frontend/src/Gameplay.tsx` includes preparation with a recorded result in the existing phase-focus effect, attaching its ref and `tabIndex=-1` to the panel. After: `SECTION`, named “Recorded outcome during preparation.” Refresh/presence updates in the same phase do not move focus. Regression: browser exact-target assertion and presence-update focus retention.

### 2. Focus lost when admitted briefing replaced preparation

Reproduce: leave focus in the pending panel and wait for admission. Before: `BODY`, at the previous scroll position. Root cause: removing preparation removed its focus target; briefing had no phase focus handoff.

Fix: `frontend/src/App.tsx` focuses and scrolls the existing mission title on phase/crisis transition into briefing. The title is programmatically focusable without adding a normal Tab stop. After: the current `.mission-header h1` is focused. Native Tab then reaches the host's Begin discussion control. Regression: exact heading-target and native Tab checks; effect dependencies exclude mere presence/revision updates.

### 3. Sticky submit bar covered a mobile radio

Reproduce: enter initial voting at 320 × 640 with active controls in view. Before: the sticky bottom submit bar covers one visible radio center; `elementFromPoint` returns the overlay instead of its label. The screenshot captures the obstruction.

Fix: `frontend/src/styles.css` keeps the existing submit area in ordinary form flow after the choices. No control, label, choice, validation or vote behavior changed. After: zero blocked radio centers at all four widths, with the narrow radio selectable and mobile C voting via touch emulation. Regression: browser hit tests and real selection/touch events. The button is reached below the choices rather than overlaying them.

Before/after evidence:

- [Before: blocked narrow vote](evidence/milestone_9_7/before-confirmed/voting-narrow-viewport.png) · [After: unobstructed vote](evidence/milestone_9_7/verified/voting-narrow-viewport.png).
- Focus before: `before-confirmed/findings.json`; focus after: `verified/checks.json` (`preparation_focus`, `next_briefing_focus`).
- [Recorded result during preparation](evidence/milestone_9_7/verified/preparation-mobile.png).

These are the only application changes. No model, prompt, generation schema, pre-generation, retry, voting duration/tie rule, civilization consequence, role boundary, backend gameplay, transport or persistence implementation changed.

## Screenshots, privacy and evidence locations

Public-safe final checkpoints are in `docs/evidence/milestone_9_7/verified/`:

- `three-player-lobby.png`, `initial-briefing.png`.
- `individual-voting.png`, `consensus-discussion.png`, `final-voting.png`.
- `decision-result.png`, `crisis-preparation.png`, `connection-loss.png`.
- `endgame-review.png`, `early-defeat.png`.
- `briefing-*`, `voting-*`, `preparation-*`, `victory-*`, `defeat-*` for all four viewport classes.

Every screenshot masks all role-private panels, invite inputs, chat histories/composers, and any draft/submitted vote selection/status. Browser address bars are not captured. No storage state, trace archive, raw accessibility tree, prompts, raw provider responses, credential/session identifiers or chat contents are exported. Private databases and failure diagnostics stay in mode-0700 `/tmp/ce97-private-*` directories (failure text mode 0600). Earlier temporary captured network fixtures were backed up privately before existing smokes regenerated their fixed temporary output paths.

Per-run `checks.json`, result status, sanitized server diagnostics and lifecycle durations are retained. The source observer uses real frames solely in memory for synchronization/privacy assertions. Public diagnostics contain no player/mission identifier. `preserved-artifacts.json` verifies all **118 historical Milestone 9.5/9.6 acceptance/preparation/evidence files** remain byte-identical.

Five realistic-delay browser runs completed: `before/` (one finding), `before-confirmed/` (three findings), and `after/`, `final/`, `verified/` (zero findings each). The separate fast incomplete/corrected runs are labeled separately; they are not counted as realistic timing evidence. Intermediate screenshots are retained, bringing this evidence directory to approximately 60 MiB before final metadata. Review the exact screenshot inventory when selecting documentation for a commit.

## Verification and reproducible commands

| Check | Result |
| --- | --- |
| Complete backend | **634 passed**, one existing Starlette/httpx TestClient deprecation warning, 19.78 s |
| Frontend with fresh captured fixtures | **109 passed, 0 skipped**, 278.31 ms |
| Default frontend invocation | 105 passed, four optional snapshot checks skipped; all four exercised in final run |
| TypeScript / production build | Passed |
| Python dependencies | `pip check`: no broken requirements |
| Frontend dependencies | `npm ls --depth=0`: passed |
| Git whitespace | Passed |
| Real browser | Five completed realistic-delay runs; final three zero findings; corrected fast keyboard regression zero findings |
| Existing local-network/recovery smokes | All eight listed below passed |
| Paid / real-provider API calls | **0** |

The backend suite is passing in this milestone; the historical Milestone 9.5 timeouts and Milestone 9.6 correction evidence remain preserved, not rewritten. No existing assertion or test was disabled to achieve these results.

Build and real-browser acceptance, from repository root with the runtime environment above:

```bash
cd frontend
npm run build
cd ..
node frontend/tests/browserAcceptance.mjs docs/evidence/milestone_9_7/new-run --require-clean
# Optional separate five-second fake regression (not realistic-delay evidence):
node frontend/tests/browserAcceptance.mjs docs/evidence/milestone_9_7/new-fast-run --require-clean --fast-fake-regression
```

Output directories must not already exist. The runner starts/stops its own isolated fixture process and creates independent browser contexts. It rejects external browser HTTP origins. It automatically uses an injected fake provider for every crisis/endgame and never reads `backend/.env`. `--require-clean` rejects usability findings in addition to core gameplay failures. Do not point it at production missions.

Manual fixture startup for browser review, using a **new** temporary folder and a test-only control key:

```bash
fixture_dir=$(mktemp -d /tmp/ce97-private-manual-XXXXXX)
CE_BROWSER_TEST_KEY=manual-local-fixture .venv/bin/python backend/tests/browser_acceptance_server.py "$fixture_dir" 18779
```

Open `http://127.0.0.1:18779` in separate profiles/private contexts. Create an AI-Generated Mission and join via its invite; the fixture injects fake inference. The test-only control API advances deadlines when called with the test key. It is never part of the production app and must remain loopback-only. Normal backend development remains FastAPI/Uvicorn with React/Vite or the built frontend; no development configuration changed.

Other checks executed:

```bash
timeout 90 .venv/bin/python -m pytest backend/tests -q -o faulthandler_timeout=15
.venv/bin/python -m pip check

# Sequential smokes; some share a test port:
.venv/bin/python backend/tests/smoke_milestone7.py
.venv/bin/python backend/tests/smoke_live_generation.py
.venv/bin/python backend/tests/smoke_adaptive_narrative.py
.venv/bin/python backend/tests/smoke_milestone5.py
node --experimental-websocket frontend/tests/smokeReconnection.mjs
.venv/bin/python backend/tests/smoke_milestone6.py
.venv/bin/python backend/tests/smoke_milestone8.py
.venv/bin/python backend/tests/test_chat_acceptance.py

cd frontend
npm test
MISSION_REVIEW_FILE=/tmp/ce-m6-live.json EXPANSION_REVIEW_FILE=/tmp/ce-m8-live.json CHAT_ACCEPTANCE_FILE=/tmp/ce-chat-5-1.json MISSION_RESTART_FILE=/tmp/ce-m7-restart.json npm test
npm run typecheck
npm run build
npm ls --depth=0
cd ..
git diff --check
```

Smokes use 60-second bounds (65 for review/expansion/chat); command outcomes are saved in `network-smokes.json`. Probe/dependency/build/test logs are preserved without gameplay payloads. A setup build invoked once from the repository root failed because there is no root package.json; it was rerun successfully in `frontend/`. The initial missing-library launch, timing-correlation mistake and incomplete 50 ms fast fixture are separately documented; none is counted as successful acceptance.

## Manual acceptance still required

Use the isolated fixture server for a human review session:

1. Have three people join in separate real browsers/devices, read their own intelligence, and verify only their own cards are received.
2. Play clear plurality and tied rounds, read the result, then wait through the 26-second preparation while navigating by keyboard and listening to actual screen-reader announcements.
3. Exercise real phone touch/zoom, narrow tables, long crisis content, chat reading/unread behavior, connection-loss warnings and terminal history/chart/table navigation.
4. Refresh during briefing/preparation, interrupt a real network connection, and restart the isolated backend while preserving its database.
5. Check with the intended screen readers, mobile Safari/WebKit and other target browsers. Check high contrast/forced colors and text scaling if required for deployment.

These human, physical-device, cross-browser and screen-reader speech checks were **not performed**. The previously observed tooling blocker was resolved, so real headless-browser gameplay acceptance is complete; this does not certify those manual experiences or all WCAG criteria. Narrative strategic quality and real-model latency are outside this fake-provider acceptance.

## Exact file inventory and next recommendation

Modified application files:

- `frontend/src/App.tsx` — once-per-briefing focus handoff to the current mission title.
- `frontend/src/Gameplay.tsx` — focusable retained-result panel and preparation phase handoff.
- `frontend/src/styles.css` — non-overlaying vote submit area.

Added tools/documentation:

- `backend/tests/browser_acceptance_server.py` — isolated loopback fake provider/SQLite fixture, continuously advancing controlled clock and keyed test controls.
- `frontend/tests/browserAcceptance.mjs` — repeatable real Chromium multiplayer/UX/privacy/timing/keyboard/responsive/accessibility checks.
- `docs/MILESTONE_9_7_BROWSER_ACCEPTANCE.md` — this report, including the pre-change audit.
- `docs/evidence/milestone_9_7/` — public-safe screenshots, checks, diagnostics, logs, preservation and verification records. `inventory.json` enumerates every file; `SHA256SUMS.json` seals the packet and changed sources.

No production backend, dependency manifest/lockfile, model/prompt/provider configuration, game content or gameplay rule changed. No existing uncommitted work was discarded and all historical evidence hashes match. No commits, tags or pushes were made.

Recommend a short human three-person phone/keyboard/screen-reader acceptance session next, using these same fixtures. No buffered pre-generation or further LLM optimization should be inferred from these results. Any future real-provider evaluation requires separate authorization.
