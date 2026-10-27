# Milestone 8 — Gameplay experience and scenario expansion

## Reconnaissance

The repository was clean at the beginning of this milestone, at commit `9615293` (Milestone 7.3). Before editing, inspected AGENTS.md, milestone reports (especially 7.3), backend models/content/selection/voting/consequences/persistence/projections, frontend gameplay/review/presence, and existing tests. The product specification was also reviewed for compatibility, including its imperfect-AI design requirement. A concise findings/design summary was provided before implementation.

The existing library had ten root-level JSON crises plus `sequence.json`; `load_crisis_sequence` validated a fixed order. FastAPI configured a server-owned MissionStore, with complete authored content stored in its sequence. Plurality, Consensus Window, final voting, clamped metrics, immediate loss, host acknowledgement and exactly-once immutable results were already implemented. Mission-wide chat and presence were operational. SQLite stored checksummed version-1 JSON aggregates and immutable result hashes under SQL schema version 2. Recovery restored saved content rather than reloading today's files. The React result and review already displayed winning choice, outcome, actual metric changes, voting/history and score.

Existing abstractions were reused: Crisis/Choice remain unchanged; existing results are the authoritative prior-decision ledger; the existing sequence holds ten materialized slots; existing result/review components render improved feedback.

## Design and implementation

### Catalog, pacing and deterministic selection

There are now **30 distinct crises**, **90 choices**, and **120 private role reports**. Twenty crises and a metadata catalog live in `backend/app/content/expansion/`. The original ten crisis JSON files and original sequence are unchanged, including the protected Grid Under Pressure bytes. Distribution: infrastructure 5, public trust 5, economy 5, safety 4, environment 6, ethics 5. AI recommendations are A=10, B=10, C=10.

Each scenario still uses exactly A/B/C, one recommendation, four private domains, four integer metric deltas and authored consequence text. Every option has at least one gain and one cost. New middle and late content has larger authored stakes than early content; these are static JSON deltas, not runtime difficulty modifiers. Recommendation positions are varied across A/B/C while the recommendation itself follows each scenario's authored priorities. All thirty are checked for distinct identifiers/titles, complete role information and absence of an option that weakly exceeds another on every metric and strictly exceeds it on at least one.

The default application factory now configures expanded campaigns. Explicit `crisis_loader` injection retains the existing fixed-sequence engine mode, including small test fixtures. The direct MissionStore constructor retains its existing reference-sequence default; production configuration remains the factory's responsibility.

Standard missions always reserve **exactly ten unique slots**:

1. Grid Under Pressure (stage 1).
2. Two additional early-stage crises.
3. Three middle-stage crises.
4. Three late-stage crises.
5. The Last Coordination (stage 4).

The seed is the immutable mission invite token. Selection uses a fresh `random.Random(f'{seed}:{slot}')` with candidates sorted by ID, so wall-clock time, WebSocket timing and other missions cannot affect a selection. Candidate stages are 1,1,1,2,2,2,3,3,3,4. Same seed, same saved catalog and same actual decisions reproduce the run in the supported Python runtime.

At mission start all ten slots receive distinct independent fallbacks. On each existing host acknowledgement, the next slot is selected from eligible follow-ups or independent unused content. If the chosen independent crisis was reserved later in that stage, its slot is swapped; executed slots are never rewritten. Catalog validation requires enough independent fallback content for every stage, so no vote can leave a mission without a valid next crisis. The fixed opening and finale are deliberate; metric-selected finales remain broader MVP work.

### Minimal narrative continuity

A prerequisite contains only one earlier crisis ID, accepted choice IDs and authored public context. Its source must be an independent crisis in a strictly earlier stage. Missing sources, same-stage dependencies, cycles, chains, duplicate conditions, duplicate IDs and fallback shortages are rejected before start mutates roles or phase.

Follow-ups qualify only from an **actual resolved result**, never an individual hidden vote or an unplayed reserved slot. Eligible follow-ups take priority within their stage; ties use the same deterministic seeded selection. A conditional event can occur only once. If its source was not selected or the team chose a different option, independent content is used instead. More eligible follow-ups than remaining slots do not force additional crises.

Five authored links:

| Prior executed decision | Eligible follow-up | Public continuity |
|---|---|---|
| Grid Under Pressure → A | District 7 After Dark | Concentrated outages create household losses and repair-access disputes. |
| Waterline Alert → B | The Delivery Backlog | Emergency water distribution creates container and depot burdens. |
| Care at Capacity → A | Staff Behind the Beds | Temporary beds require experienced staffing without hollowing out clinics. |
| The Essential Corridor → C | The Cost of Priority | Protected lifelines leave ordinary traders facing debt and deferred capacity claims. |
| Services Under Intrusion → A or C | Who Can Restore Access? | Isolation contains intrusion but leaves identity/access restoration obligations. |

On materialization the backend appends the actual source crisis number/title and executed choice title plus authored context to the new public briefing and each choice's eventual outcome. Paragraph breaks make the connection readable. The selected outcome is subsequently frozen in the existing CrisisResult, alongside the exact public briefing, choice, metrics and vote history. Unchosen consequences and all future content remain absent from client projections. There are no hidden metric modifiers or generalized rule expressions; prior choices influence which authored crisis and tradeoffs appear later.

### Persistence and compatibility

One optional `Mission.campaign` aggregate contains the seed and full typed catalog snapshot (including prerequisite metadata). Existing results remain the decision ledger; no parallel event history was added. Selecting/materializing the next slot is part of the existing atomic persisted acknowledgement, before success and broadcast. Failed storage writes retain existing rollback semantics.

**No SQL migration is introduced.** SQL schema remains 2, aggregate format remains 1, and CrisisResult fields/hashes are unchanged. The reader permits exactly one newly optional top-level field: a pre-Milestone-8 aggregate missing `campaign` is treated as `None`. Other unexpected/missing fields still fail closed. Legacy missions keep their original sequence and history; they do not switch to the expanded pool mid-run. New metadata is validated for catalog, stage, length/uniqueness and executed prerequisite invariants on recovery. A test constructs the actual old aggregate shape, confirms reconnect recovery, and checks resolution-table rows/hashes are unchanged.

Recovery uses saved catalog/sequence/context even if current content loaders are unavailable. Credentials, role filtering, presence reset, original deadlines and mandatory-phase restart safeguards retain their established behavior. An older application cannot read a new expanded aggregate: do not downgrade an active expanded database without a consistent compatible backup.

Backend package data now includes the nested JSON directory. A built wheel was extracted and verified to contain 32 JSON assets (30 crises, legacy sequence, expansion catalog) and load all 30 crises without the source checkout.

### Decision feedback and endgame

The existing outcome component now labels immediate consequences. Public briefing and outcome paragraphs retain authored line breaks, including previous-decision references. Winner, vote resolution, actual before/after metrics, applied deltas and clamping remain the existing server data and UI.

The server extends terminal summary projections with:

- `narrative_outcome`: observed victory/zero-metric loss plus the last actually executed action and its recorded consequence.
- `notable_decisions`: up to three actual results with the largest total absolute **applied** metric movement, then shown in chronological order (earlier crisis breaks ties).

The existing post-game review renders those fields in its panel style, while preserving victory/defeat, crises completed, final metrics, exact average Consensus Score, trend, detailed records and presence. Nothing invents events or future consequences on the client. Older captured/embedded summaries without the new optional fields simply omit these additions. Authored text is escaped by React; existing accessibility and responsive behavior remain in place.

## Scenario inventory

Stages denote selection bands, not guaranteed position. All original entries retain their original content. The expanded catalog is the source for stage/category/prerequisite metadata.

| Crisis ID | Title | Category | Stage | Prerequisite |
|---|---|---|---|---|
| `grid-under-pressure` | Grid Under Pressure | infrastructure | 1 | Independent |
| `waterline-alert` | Waterline Alert | environment | 1 | Independent |
| `care-at-capacity` | Care at Capacity | safety | 1 | Independent |
| `essential-corridor` | The Essential Corridor | economy | 2 | Independent |
| `signal-and-rumour` | Signal and Rumour | public_trust | 2 | Independent |
| `services-under-intrusion` | Services Under Intrusion | infrastructure | 2 | Independent |
| `storm-at-the-barrier` | Storm at the Barrier | environment | 3 | Independent |
| `credit-under-strain` | Credit Under Strain | economy | 3 | Independent |
| `a-fair-share` | A Fair Share | ethics | 3 | Independent |
| `the-last-coordination` | The Last Coordination | safety | 4 | Independent |
| `transit-at-dawn` | Transit at Dawn | infrastructure | 1 | Independent |
| `cooling-access` | A Place to Cool Down | public_trust | 1 | Independent |
| `reservoir-bloom` | Bloom at the Intake | environment | 1 | Independent |
| `payroll-gap` | The Payroll Gap | economy | 1 | Independent |
| `evacuation-routes` | One Bridge, Two Queues | safety | 1 | Independent |
| `data-consent` | Consent Under Pressure | ethics | 1 | Independent |
| `substation-reckoning` | District 7 After Dark | public_trust | 2 | grid-under-pressure: A |
| `bottled-water-waste` | The Delivery Backlog | environment | 2 | waterline-alert: B |
| `care-workforce` | Staff Behind the Beds | safety | 2 | care-at-capacity: A |
| `repair-strike` | The Repair Mandate | infrastructure | 2 | Independent |
| `market-cold-chain` | Cold Chain Crossroads | economy | 2 | Independent |
| `schools-as-shelters` | Classrooms or Shelter | ethics | 2 | Independent |
| `air-quality-orders` | The Air We Share | environment | 2 | Independent |
| `housing-inspections` | Cracks in the Register | public_trust | 2 | Independent |
| `freight-debt` | The Cost of Priority | economy | 3 | essential-corridor: C |
| `identity-recovery` | Who Can Restore Access? | ethics | 3 | services-under-intrusion: A/C |
| `floodplain-pumps` | Beyond the Flood Line | environment | 3 | Independent |
| `mutual-aid-contract` | The Mutual Aid Price | infrastructure | 3 | Independent |
| `ration-appeals` | A Right to Appeal | public_trust | 3 | Independent |
| `autonomy-review` | The Emergency Mandate | ethics | 3 | Independent |

## Verification commands and results

Run from `/home/attila_unix/projects/consensus-engine`:

```sh
timeout 120s .venv/bin/python -m pytest backend/tests -q -o faulthandler_timeout=40
npm --prefix frontend test
MISSION_RESTART_FILE=/tmp/ce-m7-restart.json MISSION_REVIEW_FILE=/tmp/ce-m6-live.json CHAT_ACCEPTANCE_FILE=/tmp/ce-chat-5-1.json EXPANSION_REVIEW_FILE=/tmp/ce-m8-live.json npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend ls --depth=0
.venv/bin/python -m pip check
git diff --check
.venv/bin/python -m app.expansion_analysis --sample 100
.venv/bin/python -m app.expansion_analysis --seed reproducible
.venv/bin/python backend/tests/smoke_milestone8.py
node --experimental-websocket frontend/tests/smokeReconnection.mjs
.venv/bin/python backend/tests/smoke_milestone7.py
.venv/bin/python -m pip wheel --no-deps ./backend -w /tmp/ce-m8-wheel
```

Results:

- Full backend: **262 passed in 10.01s**, one existing Starlette/httpx deprecation warning. Includes 36 new expansion cases; no test was removed or skipped. One final-suite attempt stalled in the previously observed TestClient WebSocket receive path (`test_milestone3.py:320`), with a diagnostic traceback and a 120-second process bound (exit 124). The full retry passed; this intermittent transport-test limitation remains documented rather than changing gameplay to mask it.
- Frontend default: **93 passed, 4 optional captured-evidence cases skipped**, zero failures (97 tests).
- Frontend with all four available captures: **97 passed**, zero skips/failures. Four new cases verify immediate narrative feedback, server-only highlights, escaped/optional legacy summary fields and a complete real-process expanded review.
- Type-check and production build: **PASS**. Build includes 43 modules. Frontend installed dependency check: **PASS**. No new runtime/networking dependency.
- `pip check`: **No broken requirements found**. Whitespace/diff check: **PASS**.
- Wheel build and extracted-distribution asset load: **PASS**, 32 JSON assets / 30 validated crises. The first optional `--no-build-isolation` attempt failed because this venv lacks setuptools; the normal isolated build using the already-declared build requirements succeeded. No runtime dependency change was needed. The generated untracked `backend/build` directory was removed; the wheel remains under `/tmp/ce-m8-wheel`.
- Production JS/CSS scan: **PASS**; all 120 full private reports, both raw and JSON-escaped, absent from the bundle.
- Original ten root crisis files remain unchanged; the existing Grid Under Pressure SHA-256 assertion still passes.

The existing full-campaign fixture and historical smoke servers now explicitly inject `load_crisis_sequence` where they assert the original ten IDs, exact paths and scores. Their original assertions remain. Expanded campaigns receive separate 2/3/4-player full-run transport tests, so classic expectations are preserved rather than silently applied to random new content.

New backend coverage includes all thirty schemas and tradeoffs; malformed identifiers/options/deltas/roles; bad catalog references; duplicates, cycles, wrong-stage sources and fallback shortages; 100 unique-seed paced plans; same-seed replay; each of the five follow-ups with every parent choice; unsatisfied fallback; result/metric consistency; clamping/zero loss; ten-crisis victory and summary facts; same-database catalog/seed/branch recovery without content reads; old-payload/hash compatibility; 2/3/4-player full missions with an initial tie, Consensus Window and final vote; role privacy across the entire pool; and common histories/metrics. Existing presence, chat, plurality, missing-player progression and recovery tests remain enabled.

One early expansion test compared an unescaped Unicode intelligence report to default ASCII-escaped JSON and failed its authorized-string check. The assertion was corrected to serialize with `ensure_ascii=False`; it continues checking every authorized and unauthorized report. This was a test serialization issue, not a privacy relaxation.

### Real process/network checks (not browser UI)

`smoke_milestone8.py` starts a real temporary SQLite-backed uvicorn process and three WebSocket clients. It exercises an initial three-way tie and fresh final vote, executes ten unique expanded crises, checks authored prerequisite context, compares every client's history/metrics, scans for unauthorized information, restarts the backend after Crisis 3, preserves identity/roles/content/history, retries acknowledgements without additional application, and completes a scored review. **PASS**. The final recorded run scored **67.75**, selected one follow-up, and wrote public review evidence to `/tmp/ce-m8-live.json` (mode 0600). Different runs are expected to differ.

The unchanged production reconnect controller smoke runs against the new default expanded factory. **PASS** for three continuously held clients reconnecting automatically across backend restart without remount/refresh; individual disconnection; unchanged original deadlines and vote progress; chat restoration; role/privacy/history/metric restoration; C's nonresponse at the deadline; disabled named-player Next crisis gate; reconnect clearing the warning and enabling continuation; stale-vote rejection.

The existing five-generation recovery smoke remains a precise legacy fixture. **PASS** for partial saved votes, expired Consensus Window, fresh mandatory final opportunity, independent mission isolation, canonical ten-crisis victory/history/score 55.75 and early defeat/history/score 54.5. No storage or recovery guarantees were traded for scenario variety.

Logs/captures: `/tmp/ce-m8-backend.log`, `/tmp/ce-m8-backend-final.log`, `/tmp/ce-m8-expansion.log`, `/tmp/ce-m8-ui.log`, `/tmp/ce-m8-ui-acceptance.log`, `/tmp/ce-m8-live.log`, `/tmp/ce-m8-live.json`, `/tmp/ce-m8-reconnect.log`, `/tmp/ce-m8-legacy-recovery.log`, `/tmp/ce-m8-balance.json`, `/tmp/ce-m8-balance-scores.json`, `/tmp/ce-m8-replay.json`, `/tmp/ce-m8-wheel.log`.

### Sampled balance (not an exhaustive or human-playtest claim)

The offline tool executes production transitions/metric rules for seeds `0` through `99`. These policies see the same seeded algorithm but can create different branches because their decisions differ. The balanced policy greedily maximizes the minimum resulting metric and is a test heuristic with access to authored deltas, not a player strategy or an optimal solver.

| Policy | Survived / 100 | Mean survivor score | Survivor score range |
|---|---:|---:|---:|
| Always A | 79 | 56.46 | 45.0–64.5 |
| Always B | 97 | 62.29 | 53.75–70.25 |
| Always C | 99 | 58.83 | 49.75–66.0 |
| Follow authored AI | 95 | 61.37 | 53.25–67.75 |
| Balanced minimum-metric heuristic | 100 | 63.66 | 51.5–71.5 |

No individual scenario has a Pareto-dominant option. AI's final metric average was below the balanced policy on 72 seeds and above on 28. AI-following survived 95 seeds and lost on seeds 11, 16, 24, 50 and 54; the balanced policy survived those same seeds. A deterministic regression locks in both an AI-following success and an AI-following loss. Advice is useful but neither a guaranteed win nor uniformly highest scoring; the AI and constant-letter policies remain strong in this sample. Broader balance and blind human playtesting remain necessary; no claim is made that all combinations are equally difficult or the library is competitively balanced. Survival is intentionally possible; maximizing shared condition remains distinct from merely surviving.

## Known limits and manual acceptance

- Fixed introduction/finale remain; weakest-metric final selection is outside this milestone's required compatibility scope. Eight interior slots vary. There is no player-facing replay/seed-entry control; offline replay uses the seed and exact choices.
- Narrative links are one-level, earlier-stage, explicit choice prerequisites. There are no metric-expression conditions, chained quest graphs, hidden future modifiers, external AI calls or generated scenarios.
- Future content selection is reproducible for the supported Python runtime and saved catalog. Cross-version Python RNG compatibility is not guaranteed. Already materialized content and histories are always restored verbatim; do not use application downgrade as a recovery mechanism.
- The catalog snapshot increases per-mission SQLite payload size; this is deliberately simple single-process MVP storage, with unchanged ownership/durability and no new service. No load/stress or physical-device testing was performed.
- No real browser acceptance was performed. The supported computer-use runtime initialization was attempted but failed before browser access with `sandboxCwd is not a local file URI: file:///home/attila_unix/projects/consensus-engine`. Mocked sockets, TestClient transports, real network processes and server-rendered markup are not browser tests.
- Existing remaining MVP work (five-minute disconnect removal/role redistribution, QR joining and replay controls) remains unchanged. The established auto-reconnect, presence and progression gate are preserved.

Manual checklist:

1. Start the usual backend on the same absolute SQLite path and Vite frontend; create a new mission with 2, 3 and 4 real profiles/devices. Confirm assignments and each player's private intelligence.
2. Play different new missions; confirm ten crises, the fixed introduction/finale, varied interior scenarios, three meaningful options and distinct domain constraints. Verify AI advice against the private reports instead of treating the sampled policy result as a guarantee.
3. Choose A in Grid Under Pressure; when District 7 After Dark qualifies, inspect the public prior-decision reference and different options. Replay an offline seed with a different first choice to verify fallback selection. Exercise other authored links.
4. Inspect result winner, immediate outcome, reference to earlier decisions and actual clamped changes; ensure unchosen/future effects are absent from browser payloads.
5. Exercise plurality, an initial tie and final voting, missed votes, live chat/unread behavior, individual loss/reconnect and named-player Next crisis blocking. Confirm no stale submissions after a phase expires.
6. Keep pages open during backend restart; automatically reconnect without refresh, preserving role-private information, current branch, metrics, chat/history, presence and mandatory-phase policy. Reopen an existing pre-Milestone-8 mission and confirm it keeps its original saved sequence.
7. Finish a ten-crisis victory and an early zero-metric defeat. Compare score to the average, notable decisions to exact recorded entries, narrative outcome to the executed final action, and detailed history across all players.
8. Check phone width, long outcome paragraphs, keyboard access, status announcements and read-only post-game review. Inspect a packaged deployment rather than relying only on editable-install content paths.

## Exact changed-file inventory

The working tree was clean before this task. The following list includes all added/modified source, content, tests and documentation. Temporary captures and build artifacts are excluded. No original crisis JSON or original sequence was modified.

- `README.md`
- `backend/app/campaign.py`
- `backend/app/content/expansion/air-quality-orders.json`
- `backend/app/content/expansion/autonomy-review.json`
- `backend/app/content/expansion/bottled-water-waste.json`
- `backend/app/content/expansion/care-workforce.json`
- `backend/app/content/expansion/catalog.json`
- `backend/app/content/expansion/cooling-access.json`
- `backend/app/content/expansion/data-consent.json`
- `backend/app/content/expansion/evacuation-routes.json`
- `backend/app/content/expansion/floodplain-pumps.json`
- `backend/app/content/expansion/freight-debt.json`
- `backend/app/content/expansion/housing-inspections.json`
- `backend/app/content/expansion/identity-recovery.json`
- `backend/app/content/expansion/market-cold-chain.json`
- `backend/app/content/expansion/mutual-aid-contract.json`
- `backend/app/content/expansion/payroll-gap.json`
- `backend/app/content/expansion/ration-appeals.json`
- `backend/app/content/expansion/repair-strike.json`
- `backend/app/content/expansion/reservoir-bloom.json`
- `backend/app/content/expansion/schools-as-shelters.json`
- `backend/app/content/expansion/substation-reckoning.json`
- `backend/app/content/expansion/transit-at-dawn.json`
- `backend/app/domain.py`
- `backend/app/expansion_analysis.py`
- `backend/app/main.py`
- `backend/app/missions.py`
- `backend/app/persistence.py`
- `backend/pyproject.toml`
- `backend/tests/smoke_milestone5.py`
- `backend/tests/smoke_milestone6.py`
- `backend/tests/smoke_milestone7.py`
- `backend/tests/smoke_milestone8.py`
- `backend/tests/test_campaign.py`
- `backend/tests/test_expansion.py`
- `docs/MILESTONE_8_GAMEPLAY_EXPANSION.md`
- `frontend/src/App.tsx`
- `frontend/src/ConsequenceOutcome.tsx`
- `frontend/src/CrisisBriefing.tsx`
- `frontend/src/MissionReview.tsx`
- `frontend/src/styles.css`
- `frontend/src/types.ts`
- `frontend/tests/gameplay.test.tsx`
- `frontend/tests/missionReview.test.tsx`

**44 files**. No commit, tag or push was created. All changes remain local for review.
