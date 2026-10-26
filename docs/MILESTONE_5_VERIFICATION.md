# Milestone 5 verification — 2026-10-26

## Scope and reconnaissance

Read AGENTS.md, README, the v0.1 product specification, prior Milestone 3/4/4.1 reports, authored schema/content, mission transitions, result/score UI, private projections, and tests before changes. The existing engine already supported configured sequences, stable roles, per-viewer intelligence, 60-second discussion, 30-second hidden voting, 20-second Consensus Window, fresh final voting, exactly-once results, host acknowledgment, clamped metrics, collapse/completion and reconnect. Production content contained only Crisis 01. Missing work was nine authored records, a ten-entry manifest, campaign balance analysis, and validation across repeated multiplayer rounds.

The engine was retained. The only consequence refactor extracts the existing literal clamp and zero-detection rules into pure functions shared with offline analysis. The server still owns every transition, assignment, vote, metric and score; no new runtime service or dependency was added. The fixed sequence requested here intentionally defers the broader MVP randomized pool/weakest-metric finale.

## Authored campaign

| # | Crisis / central conflict | AI choice and rationale |
|---|---|---|
| 01 | **Grid Under Pressure** — Heat: grid capacity versus public welfare | A: Follow the AI Recommendation — Grid stability |
| 02 | **Waterline Alert** — Water: contamination protection versus continuity | B: Isolate and Deliver — Contain exposure while retaining supply |
| 03 | **Care at Capacity** — Care: immediate capacity versus conserved resources | A: Open Temporary Care Wards — Expand immediate clinical capacity |
| 04 | **The Essential Corridor** — Supplies: essential deliveries versus market access | C: Build a Priority Corridor — Protect essential freight |
| 05 | **Signal and Rumour** — Information: speed and control versus legitimacy | A: Reserve a Single Alert Channel — Fast verified alert delivery |
| 06 | **Services Under Intrusion** — Cyberattack: recovery versus live service continuity | C: Isolate in Stages — Contain intrusion while retaining service |
| 07 | **Storm at the Barrier** — Storm: evacuation safety versus lifeline protection | B: Defend Lifeline Substations — Protect lifeline substations |
| 08 | **Credit Under Strain** — Finance: credit protection versus public confidence | C: Secure Critical-Service Credit — Keep essential-service credit moving |
| 09 | **A Fair Share** — Allocation: legitimacy versus enforcement | C: Delegate Accountable Quotas — Accountable local distribution |
| 10 | **The Last Coordination** — Final cascade: central repair versus distributed resilience | B: Protect Lifeline Islands — Preserve independent lifeline service |

Recommendations: **A: 3, B: 3, C: 4**. Recommendations express plausible local priorities, rather than a guaranteed best campaign policy. The narratives connect successive city stresses without assuming a particular previous choice. Accumulated metrics supply state context; no procedural branching was added.

Each new record includes three distinct strategies and outcome narratives, all four deterministic integer deltas, and four different private reports. Infrastructure reports capacity/dependency constraints; Community reports access, vulnerable populations and legitimacy; Economy reports liquidity, supply and opportunity costs; Safety reports exposure, evacuation and secondary hazards. Facts introduce conflicting constraints and uncertainty rather than a secret correct answer. Every choice has gains and costs; outcomes explain those tradeoffs.

Crisis 01 is byte-for-byte unchanged, guarded by SHA-256 `1a83bdb443c9a0b893b48271c3523cf6c9f47e7e92a0f2037d7acdf1801c29ac`. No content migration was required.

## Schema, privacy and progression

The existing Pydantic schema now rejects blank authored text, unknown fields, noninteger deltas and malformed IDs; requires exactly A/B/C, a valid recommendation, complete metric fields, and all roles. The existing loader rejects duplicate manifest entries, missing/unreachable JSON, malformed JSON and filename/declared-ID mismatch. Production tests pin the ordered ten-entry catalog; the generic engine retains support for smaller explicit test fixtures.

The same per-seat backend projection includes only current public content and intelligence for assigned roles. Full sequence content, other role reports, previous result ledgers and future outcomes are never serialized to clients. Tests scan every projection against all unauthorized reports across all ten records. The built production JS/CSS is separately scanned against all 40 private reports. UI test-only JSON imports do not enter the production bundle.

Roles remain unchanged throughout. New briefings clear discussion/voting/decision state while retaining metrics, identity and the bounded mission-wide chat. Chat now records its server-owned originating crisis number and the UI labels historical messages, avoiding confusion with current discussion. Existing 100-message and two-round bounds remain. No socket subscription/effect logic was changed. Host-only acknowledgment and result-ID idempotency remain unchanged. Zero immediately fails; tenth result acknowledgment alone completes with average final metrics; there is no eleventh crisis.

## Balance methodology and results

Run from repository root: `.venv/bin/python -m app.campaign_analysis`. Enumerates all **59,049** full A/B/C strings, applying the same production clamp after each executed decision and stopping immediately at zero. Early-collapse suffixes count separately in the full-string enumeration. Raw full-horizon totals are hypothetical arithmetic only; executed totals stop at collapse. Eight representative paths are cross-checked against actual MissionStore resolution.

- Survival: **29,267 (49.56%)**; collapse: **29,782**. No per-crisis Pareto-dominant choice.
- Collapses by crisis: 4: 729; 5: 2,187; 6: 5,346; 7: 5,211; 8: 5,265; 9: 4,644; 10: 6,400.
- Zero metrics across collapsed strings (may overlap): Economy 18,263; Public Trust 4,472; Infrastructure 3,246; Safety 4,132. Every metric can end a mission.

| Policy | Path | Outcome / final metrics (Infrastructure, Trust, Economy, Safety) | Score |
|---|---|---|---|
| always_A | `AAAAAAAAAA` | Collapse at 7: [46, 10, 0, 100] | — |
| always_B | `BBBBBBBBBB` | Survived: [49, 71, 31, 44] | 48.75 |
| always_C | `CCCCCCCCCC` | Collapse at 10: [43, 100, 39, 0] | — |
| authored_AI | `ABACACBCCB` | Survived: [80, 72, 8, 60] | 55.0 |
| alternating_ABC | `ABCABCABCA` | Collapse at 7: [52, 76, 0, 88] | — |
| alternating_CBA | `CBACBACBAC` | Collapse at 10: [0, 92, 23, 68] | — |

| Policy | Full-horizon raw totals (Infrastructure, Trust, Economy, Safety) |
|---|---|
| always_A | [-6, -106, -62, 36] |
| always_B | [-21, 1, -39, -26] |
| always_C | [-27, 48, -31, -70] |
| authored_AI | [14, 2, -62, -10] |
| alternating_ABC | [-22, 22, -116, 8] |
| alternating_CBA | [-80, 38, -47, -2] |

Highest-score surviving path: `BBCCCBCCAB`, metrics [87, 75, 5, 80], score **61.75**. Strongest minimum-metric path: `BBBCCBCAAC`, metrics [63, 55, 53, 52], score **55.75**. The lowest surviving score is 28.0.

Economy is the principal bottleneck (about 61% of collapsed strings), reflecting repeated emergency spending. Its restoration competes with trust, infrastructure and safety. Always-B survives but scores below mixed strategies; always-A and always-C collapse. Following AI survives with only 8 Economy. The best-average path leaves Economy at 5, while the robust path retains every metric above 50: final average and resilience are different objectives. Early costly commitments constrain later choices. This is a plausible initial balance, not proof of human difficulty or enjoyment: exhaustive equally weighted paths are not player probabilities, and perfect-information path optimization is not normal play. Human balancing remains useful, especially for economic pressure.

## Multiplayer verification

Deterministic integration tests run the entire production campaign with **2, 3 and 4 players**, preserving 2+2, 2+1+1 and 1+1+1+1 role allocation. Every crisis checks shared public state, private filtering, deadline freshness, unique round IDs, no stale decisions, accumulated metrics, exactly one ledger entry, host acknowledgments, retry acknowledgment safety and terminal score. They exercise initial ties, final plurality and unresolved final AI tie; four-player rounds include 2–1–1 plurality. Duplicate resolution/consequence callbacks cannot reapply effects. Existing authorization/identity tests remain.

Later restoration covers Crisis 4 consensus, Crisis 8 voting, Crisis 9 result and completion in controlled-clock integration. The live test additionally closes the guest socket and reconnects using its original credential at Crisis 6 discussion, Crisis 8 voting **after its vote**, and Crisis 9 result. It checks ID, callsign (unchanged despite attempted rename), roles, deadline, intelligence, metrics and result/own-vote state. Completion and failed-state restoration also pass. No five-minute timeout behavior was added.

### Live three-client campaign (accelerated)

Command: `.venv/bin/python backend/tests/smoke_milestone5.py`. Real Uvicorn, HTTP and three WebSocket clients, production ten-crisis loader, injected 20x wall clock. Production timing constants are unchanged. Each broadcast is checked for synchronized public state and authorized intelligence. Crisis 2 uses A/B/C tie then B/B/A revote. Crisis 4 remains A/B/C on the final vote, executing authored AI C. Chat messages identify their originating crisis. Duplicate host acknowledgment cannot skip a crisis.

Metric vectors below are Infrastructure / Public Trust / Economy / Safety.

| # | Crisis | Choice | Resolution | Authored deltas | Resulting metrics | Next phase |
|---|---|---|---|---|---|---|
| 1 | Grid Under Pressure | B | initial_plurality | [5, -3, -7, 2] | [75, 67, 63, 72] | briefing |
| 2 | Waterline Alert | B | final_plurality | [-8, 6, -8, 10] | [67, 73, 55, 82] | briefing |
| 3 | Care at Capacity | B | initial_plurality | [4, -10, 6, -12] | [71, 63, 61, 70] | briefing |
| 4 | The Essential Corridor | C | ai_tie_break | [10, 6, -12, -8] | [81, 69, 49, 62] | briefing |
| 5 | Signal and Rumour | C | initial_plurality | [-6, 6, -6, 2] | [75, 75, 43, 64] | briefing |
| 6 | Services Under Intrusion | B | initial_plurality | [16, -8, -18, 4] | [91, 67, 25, 68] | briefing |
| 7 | Storm at the Barrier | C | initial_plurality | [-10, 10, -8, 4] | [81, 77, 17, 72] | briefing |
| 8 | Credit Under Strain | A | initial_plurality | [-6, -14, 18, -10] | [75, 63, 35, 62] | briefing |
| 9 | A Fair Share | A | initial_plurality | [6, -20, 6, 4] | [81, 43, 41, 66] | briefing |
| 10 | The Last Coordination | C | initial_plurality | [-18, 12, 12, -14] | [63, 55, 53, 52] | completed |

Live run: **PASS**, ten distinct crises once each, final metrics **63/55/53/52**, Consensus Score **55.75**, preserved after reconnect. Separate production-content collapse run `BAAA…` reaches Economy 0 at Crisis 4; advance is rejected (409), completion is absent, and reconnect restores the failed result. Automated production-store tests independently cover legitimate collapse at crises **4, 6 and 10**, duplicate callbacks and blocked advancement.

### Real-time smoke

`.venv/bin/python backend/tests/smoke_milestone3.py`: **PASS**. No clock override: actual 60-second discussion and 20-second Consensus Window; fresh final voting with 30-second deadline, B/B/A final plurality, original B consequences and reconnect. This complements the accelerated full campaign rather than claiming a ten-round real-time session.

## Commands and results

All commands run from the repository root unless a prefix specifies otherwise.

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest backend/tests -q` | 166 passed; one pre-existing Starlette/httpx TestClient deprecation warning |
| `npm --prefix frontend test` | 20 passed |
| `npm --prefix frontend run typecheck` | Passed |
| `npm --prefix frontend run build` | Passed; 37 modules |
| `.venv/bin/python -m pip check` | No broken requirements found |
| `.venv/bin/python -m app.campaign_analysis` | Passed; all 59,049 paths analyzed |
| `.venv/bin/python backend/tests/smoke_milestone5.py` | Live full campaign and separate collapse passed (20x injected clock) |
| `.venv/bin/python backend/tests/smoke_milestone3.py` | Production-duration smoke passed |
| `.venv/bin/python backend/tests/smoke_milestone4_1.py` | Original Crisis 01 fixture passed: duplicate callsign rejection, identity reconnect and completion score 69 (10x injected clock) |
| `git diff --check` | Passed |
| `.venv/bin/python -m pip wheel --no-deps --wheel-dir /tmp/ce-m5-wheel ./backend` | Passed; wheel contains manifest and exactly ten authored crisis files |
| `.venv/bin/python /tmp/ce_m5_artifacts.py` | Passed; all 40 private reports absent from built frontend assets; packaged manifest/content match sources |

Content/schema validation is part of the backend suite. All prior 126 backend tests remain; the prior one-crisis identity/score test and 4.1 smoke now explicitly load an original-Crisis-01 fixture so their original exact score of 69 stays meaningful. The production-content test now expects ten records. No behavioral assertions were removed. No standalone linter is configured. Frontend tests increased from 18 to 20: actual ten-crisis titles/briefings/options, two-role intelligence, active controls and actual outcomes render; mission-wide chat labeling is checked. Existing completion/collapse/metrics and responsive CSS checks remain.

The optional wheel attempt using `--no-build-isolation` initially failed because setuptools is not installed in the runtime venv; retry with normal isolated build dependencies succeeded (see command table). Generated wheel staging files were removed; wheel output stayed in `/tmp`. No runtime dependency changes were needed.

## Browser/mobile acceptance and limits

No new manual browser or physical-device acceptance was performed in this task. The user reports prior Milestone 1–4.1 manual acceptance; this report does not recertify it. Rendered React tests are server-rendered markup and source/CSS checks, not viewport screenshots, touch interaction or browser focus testing. Existing phase-first controls, responsive layout, readable narratives and bounded chat remain; actual phone viewport accessibility across long content still needs manual acceptance.

State remains in process memory and requires one worker. Restart loses missions. Five-minute disconnect timeout/role redistribution, host transfer, expiry, replay controls, QR joining, randomized pools/weakest-metric finale, persistent storage and public deployment hardening remain deferred. No dynamic LLM, account or new infrastructure work was introduced. Campaign human balance and physical mobile acceptance remain the principal follow-ups.

## Exact changed files

Created:
- `backend/app/campaign_analysis.py`
- `backend/app/consequences.py`
- `backend/app/content/waterline-alert.json`
- `backend/app/content/care-at-capacity.json`
- `backend/app/content/essential-corridor.json`
- `backend/app/content/signal-and-rumour.json`
- `backend/app/content/services-under-intrusion.json`
- `backend/app/content/storm-at-the-barrier.json`
- `backend/app/content/credit-under-strain.json`
- `backend/app/content/a-fair-share.json`
- `backend/app/content/the-last-coordination.json`
- `backend/tests/test_campaign.py`
- `backend/tests/smoke_milestone5.py`
- `docs/MILESTONE_5_VERIFICATION.md`

Modified:
- `README.md`
- `backend/app/content/sequence.json`
- `backend/app/crises.py`
- `backend/app/domain.py`
- `backend/app/missions.py`
- `backend/tests/smoke_milestone4_1.py`
- `backend/tests/test_identity_hardening.py`
- `backend/tests/test_milestone4.py`
- `frontend/src/Gameplay.tsx`
- `frontend/src/types.ts`
- `frontend/tests/gameplay.test.tsx`

No commits, tags or pushes were created. Milestone 5 implementation and automated validation are ready for review/commit, with manual browser/mobile acceptance explicitly outstanding.
