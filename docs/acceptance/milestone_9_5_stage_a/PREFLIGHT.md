# Milestone 9.5 — Real-provider acceptance: preflight and authorization checkpoint

Date: 2026-10-29. **Status: Stage A preflight/planning prepared; paid baseline, human acceptance and Stage B optimization are pending. Milestone 9.5 is not complete.**

## Preflight findings

Baseline: `8f6d6da`, committed Milestone 9.4. `git status --short` was empty before this work. No existing local changes were overwritten. This stage changes only this report, not prompts, provider configuration, validation, gameplay, authored content or the frontend.

Inspected the repository instructions, Milestone 9.4 protocol/report, generation adapter/services, typed measurement/reporting/cost utilities, deterministic fixtures, human rubric, private diagnostics and existing lifecycle tests.

| Setting | Verified value |
| --- | --- |
| Configuration source for the proposed isolated run | `backend/.env`, explicitly loaded; no assumption that an existing worker has reloaded it |
| Provider | OpenAI-compatible adapter configured for OpenAI |
| Model | `gpt-6-luna` |
| Generation enabled | Yes |
| Timeout | 60.0 seconds per provider operation |
| Output format | `json_schema`; unchanged strict backend validation |
| Endpoint / credential presence | Both configured; credential required |
| Credential validity / billing / model access | Not tested; no verification request sent |
| Processing tier | Operator's planning assumption: Standard, short context; not explicitly requested or verified by the existing adapter |
| Pricing configuration before operator reply | No approved price file or pricing variables found |

No secrets, full environment or credentials were printed or stored. No provider, health, capability or mission call was made against the running backend; no live mission database was opened. Configuration presence is not proof of provider access.

The adapter, contracts, diagnostics and isolated fixture inputs are ready for the planned cases. A later authorized execution must bind them to a fresh six-call counted run, with no automatic retries. The old two-crisis real-provider smoke is insufficient for this six-case batch and has not been run. There is no deviation from the Milestone 9.4 case allocation; the additional 15-second crisis-p95 target comes from Milestone 9.5 and remains exploratory.

## Application pathways to exercise after separate approval

- Crisis: existing `ChatCompletionsProvider` request construction → `GenerationService.generate` → `accept_proposal`, authoritative reference/repetition checks and deterministic authored fallback. Isolated admission/projection checks use existing `MissionStore`/live generation patterns, never a live mission.
- Endgame: locally completed synthetic victory/defeat histories → `build_endgame_request` → `generate_conclusion` → strict `accept_endgame`, deterministic existing ending on failure, and immutable terminal snapshot/review checks through the existing store and review presentation.
- Reporting: existing `GenerationMeasurement`, crisis/endgame diagnostics, `EvaluationRecord` and reporting utilities. Record attempted calls before dispatch; preserve usage on rejected outputs when present; unknown usage stays unknown. Provider duration means the full adapter call, not pure network latency, TTFT or UI availability.
- Human review: existing anchored nine-criterion reviewer sheet; ratings and meaningful-continuity classification remain pending, never supplied automatically.

Synthetic fixtures use production voting, consequences, metric clamping and history construction. Both terminal fixtures are completed locally without paid crisis calls. Provider context excludes identities, private chat, connection data, credentials, hidden votes and role-private intelligence. Accepted private intelligence would be available only through assigned-player projections during authorized review.

## Operator-approved planning inputs and exact estimate

The operator supplied these values in chat and explicitly approved them **for planning only**, not paid execution. They are treated as operator-supplied rates, not independently verified current pricing.

| Input | Planning value |
| --- | ---: |
| Model | `gpt-6-luna` |
| Currency | USD |
| Assumed tier | Standard, short context |
| Input price / million tokens | $0.10 |
| Output price / million tokens | $0.50 |
| Assumed input / output per crisis | 5,000 / 2,000 tokens |
| Assumed input / output per endgame | 8,000 / 3,000 tokens |
| Maximum proposed requests | 6: four crises, two endgames |
| Estimated crisis cost each / subtotal | $0.0015 / $0.0060 |
| Estimated endgame cost each / subtotal | $0.0023 / $0.0046 |
| Batch assumed input / output | 36,000 / 14,000 tokens |
| **Expected batch expenditure** | **$0.0106** |
| **Proposed maximum expenditure** | **$1.00 — not yet authorized** |
| Automatic retries | Prohibited |

Validated the supplied rates with the existing Milestone 9.4 `Pricing` model and used the same Decimal token-cost formula as its estimator:

```text
Crisis:  (5,000 × $0.10 + 2,000 × $0.50) / 1,000,000 = $0.0015
Endgame: (8,000 × $0.10 + 3,000 × $0.50) / 1,000,000 = $0.0023
Batch:   4 × $0.0015 + 2 × $0.0023 = $0.0106
```

These are assumptions, not measured token usage or charges. No fictional acceptance records were created to calculate the estimate. A rejected output or timeout can still be billable. The unchanged adapter does not set an output-token billing cap or explicitly select/verify the assumed tier. A 60-second timeout is not a spending cap; an unknown outcome does not prove no charge. The projected expenditure and six-call limit do not guarantee provider-side enforcement of $1.00.

## Authorization gate — execution stopped

The operator's latest reply states that the rates/budget assumptions are planning approval only and explicitly forbids real-provider requests until separate authorization. Previous four-request authorization is exhausted and does not carry forward.

**Paid requests made in Milestone 9.5: zero. Actual expenditure incurred by this work: zero.** There is no real-provider acceptance result and no new measured provider latency or token usage.

Separate explicit approval is still required for **up to six requests, four crises plus two endgames, with the proposed $1.00 spending limit and no retries**, after reviewing the estimate and enforcement limitations. No test request has been made to verify credentials. Stage B must not begin on simulated results or substitute for the missing paid baseline.

## Six-case plan and current per-request status

| # | Case | Fixture | Public history entries in request | Serialized request bytes, excluding adapter system/schema | Status |
| --- | --- | --- | ---: | ---: | --- |
| 1 | Fresh crisis | `fresh` | 0 | 463 | Not attempted; authorization pending |
| 2 | Infrastructure damage | `infrastructure-damage` | 3 recent, plus retained earlier memory | 3,644 | Not attempted; authorization pending |
| 3 | Declining Public Trust | `declining-trust` | 3 recent, plus retained earlier memory | 3,792 | Not attempted; authorization pending |
| 4 | Interconnected prior events | `interconnected` | 3 | 2,999 | Not attempted; authorization pending |
| 5 | Victory endgame | `victory` | 10 | 7,526 | Not attempted; authorization pending |
| 6 | Early-defeat endgame | `defeat` | 4 | 4,140 | Not attempted; authorization pending |

These byte counts validate fixture construction only. They are not token estimates or full HTTP request sizes. Requests use current production serialization; no prompt was altered to encourage a particular result.

On any later authorized run, charge each attempted dispatch immediately against the six-request limit, including timeout/unknown responses. Stop on unexpected authentication, credential, configuration or spending-limit failure. Never compensate for rejection with another batch or start a paid ten-crisis run. Keep immutable baseline snapshots and sanitized diagnostics; do not retroactively reclassify fallbacks as successes.

## Acceptance and human review status

Real reliability, fallback reasons, crisis/endgame success, stage latency, usage coverage and cost: **not measured in this stage**. Statistical rates and percentiles are unavailable, not zero or simulated passes. Milestone 9.4's synthetic baseline is retained only as offline tooling evidence.

After an authorized baseline, evaluate the requested targets: at least 3/4 accepted crises, 2/2 accepted endgames, zero unsupported references admitted, zero privacy leaks, zero authoritative mutations from prose, and exploratory crisis p95 ≤15 s. Use nearest-rank p95 and report sample size; six cases cannot establish a production SLA.

Compare only like-for-like fields with the historical four-request sample: its acceptance was 3/4, schema fallback 1/4, and total durations 16.545, 26.630, 19.412 and 21.781 seconds. It did not retain provider/validation stage timing, usage or endgame results. Do not invent those missing measurements or count prior outputs as the Stage A baseline.

A blank six-case anchored human sheet was generated at `/tmp/ce95-human-review.json`. All nine ratings and notes remain unreviewed. The later reviewer must compare accepted public content to actual decisions and inspect strategic options without copying private intelligence into notes. Record continuity as absent, superficial, meaningful or contradictory; require at least one human-confirmed meaningful connection among the three history-bearing crisis cases. A supported reference alone is not a semantic pass.

Both real endgames, their displayed facts and actual review rendering remain pending. Existing fake-provider/reconnect/frontend tests below verify mechanisms, not real-provider prose or human browser acceptance. The prior performance/continuity findings justify evaluation, not an untested prompt rewrite.

## Defects, changes and before/after comparison

No new production defect was demonstrated in preflight. No model substitution, prompt change, consequence adjustment, retry loop, semantic filter, validation relaxation or optimization was implemented. Stage B root-cause analysis and any evidence-driven changes remain pending the authorized Stage A baseline and human review.

The existing intermittent in-process WebSocket TestClient receive stall reappeared during offline verification. It is a known test-harness limitation, not evidence about the provider. No unrelated transport cleanup was made. Successful offline checks do not establish real-provider improvement.

## Offline verification

No regression command called a real provider.

| Check | Result |
| --- | --- |
| Full backend suite | **578 passed**, 20.08 seconds; one existing Starlette/httpx TestClient deprecation warning |
| Captured frontend suite | **108 passed**, zero failures/skips, 326.93 ms |
| TypeScript / production build | Passed; build includes `tsc --noEmit`, 43 modules, 507 ms Vite build |
| Python dependency check | No broken requirements |
| Frontend dependency tree | Passed |
| Whitespace/diff check | Passed; only this documentation file added |
| Offline evaluator | Passed: 29 synthetic outcomes, 27 fake attempted calls, 14 accepts, 15 fallbacks; these are adversarial fixture counts, not model results |
| Three-client generation/endgame smoke | Passed: accepted-story, pending-restart fallback, provider-failure fallback, mixed crisis sources, private projections and exactly-once behavior |
| Reconnect/presence smoke | Passed: individual interruption, backend restart, retained identities/roles/history/chat/deadlines, continued voting and progression safeguards |

The first whole-backend attempt encountered the known intermittent in-process WebSocket `TestClient.receive_json` stall in `test_three_player_transport_consensus_chat_final_plurality_and_reconnect` and was bounded by the 90-second timeout. The clean rerun passed all 578 tests. No transport behavior or test was changed. Network smokes use real local WebSockets with fake inference; no human browser acceptance is claimed.

Commands:

```sh
timeout 90 .venv/bin/python -m pytest backend/tests -q -x -o faulthandler_timeout=40
MISSION_RESTART_FILE=/tmp/ce-m7-restart.json \
MISSION_REVIEW_FILE=/tmp/ce-m6-live.json \
CHAT_ACCEPTANCE_FILE=/tmp/ce-chat-5-1.json \
EXPANSION_REVIEW_FILE=/tmp/ce-m8-live.json npm --prefix frontend test
npm --prefix frontend run build
.venv/bin/python -m pip check
npm --prefix frontend ls --depth=0
git diff --check
.venv/bin/python -m app.generation.evaluation --output /tmp/ce95-offline-evaluation.json
timeout 90 .venv/bin/python backend/tests/smoke_adaptive_narrative.py
timeout 90 node --experimental-websocket frontend/tests/smokeReconnection.mjs
```

The existing fixture builder constructed all six planned inputs offline. Exact Decimal arithmetic verified the operator's $0.0106 estimate. No paid execution script or live-mode flag was run, and no live mission database was inspected or modified.

## Remaining concerns and next action

1. Separate execution authorization is absent. Stop at this checkpoint.
2. Credential/account/model access is configured but unverified; no credential-check call is permitted before approval.
3. Standard/short-context prices and token amounts are planning assumptions. The unchanged adapter does not verify tier or enforce a hard $1.00 billing cap.
4. A later six-case execution needs a counted isolated runner binding the inspected fixtures to existing production services. No production behavior should change before that baseline.
5. Actual schema rejection reasons, meaningful continuity, strategy quality, real endgame correctness, reported usage and measured cost remain unknown until the run; human ratings remain pending afterward.
6. Historical diagnostics are final-per-crisis summaries, not a full retry/billing audit. A future bounded run must record each attempted case independently.

Recommended next step: obtain the separate six-request/$1.00 approval after the operator reviews this report, then execute the unchanged baseline and collect human review. Only then consider narrowly demonstrated Stage B corrections. Do not declare the milestone complete while either gate or human review remains outstanding.

## Exact file inventory

Repository additions: `docs/MILESTONE_9_5_LLM_ACCEPTANCE.md` only. No application, prompt, configuration, test, schema, dependency or frontend files changed. Temporary preparation artifacts: `/tmp/ce95-human-review.json`, `/tmp/ce95-offline-evaluation.json`, and `/tmp/ce95-preflight-*.log` verification logs. No raw prompts, provider responses or credentials were stored in these artifacts.

No commits, tags or pushes.
