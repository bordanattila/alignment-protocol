# Milestone 9.4 — LLM reliability, performance and gameplay evaluation

## Pre-implementation architecture audit (2026-10-29)

Baseline: `e0941e1` (Milestone 9.3); clean working tree. Read repository instructions, product architecture, generation provider/service/coordinators, strict crisis/endgame contracts, narrative context, mission mutations, aggregate persistence, operator inspector, existing deterministic fixtures, privacy/reconnect tests and previous acceptance reports before code changes.

- Crisis and endgame generation already have bounded asynchronous provider calls, monotonic total duration, HTTP status and sanitized categorical outcomes. They commit outcomes to existing private mission diagnostics. Generated snapshots/results and finalized diagnostics have persistence immutability guards.
- There are no retained initiation timestamps, provider/validation breakdowns or token counts. The adapter discards `usage` when extracting an assistant message. Total generation duration is not HTTP/network latency or commit-to-browser availability.
- Existing categories distinguish disabled/configuration, timeout, provider failures, JSON/schema/reference rejections and lifecycle recovery. Repetition currently shares `invalid_schema`; classify it more precisely without changing the actual acceptance rules.
- Five-field legacy crisis records and separate endgame diagnostic records survive restart. They represent the latest outcome per crisis, not a historical retry journal. Existing operator access is a local read-only SQLite CLI; no gameplay endpoint exposes diagnostics.
- Exact history pairs are validated against the recent three decisions plus two significant older decisions. Empty references are legal; they establish neither utilization nor meaningful semantic continuity. Endgame sections require bounded references to completed decisions.
- Production state mutations, voting, consequences and timers remain server-owned. Provider inference occurs outside the state lock. Validation is bounded synchronous work; it is not literally zero blocking time and must be measured rather than described as asynchronous.
- Existing tests provide fake scenario/story providers, mock HTTP transports, controlled game clocks and real three-WebSocket-client/restart smoke harnesses. Reuse those boundaries. Evaluation fixtures must be isolated synthetic missions and not open a live database.
- The previous real-provider sample is four requests, three accepts, one `invalid_schema` fallback, no generated historical references. Usage was not retained and cannot be backfilled. It is a small acceptance sample, not a model benchmark or an endgame result.

Implementation plan: extend existing diagnostic records with optional typed measurements, capture only safe usage and monotonic stage durations, preserve old records, and add an offline evaluator/cost tool and explicit human rubric. No prompt, provider configuration, gameplay rule, numeric consequence, UI or schema-acceptance relaxation. No paid requests. Optional real-provider evaluation will be documented for later approval, not executed.

## Implemented architecture and compatibility

`GenerationMeasurement` is an optional nested field on the **existing** crisis and endgame diagnostics. Provider adapters, services, live admission and the existing read-only inspector share this one representation. There is no new diagnostic table, alternative mission state, new API endpoint or client payload.

The measurement records operation, sanitized configured model, whether a provider call was attempted, available stage durations, provider-reported numeric token usage, whether history was available, accepted reference count and a fixed objective rejection detail. It does not retain request/response text, private intelligence, history text, credentials, names or chat. Exception details never enter records. Model labels have bounded syntax and exclude the configured key if accidentally used as a model label.

Provider usage is reduced to input/output/total token counts. Booleans, negative values, oversized/noninteger counts, inconsistent sums and counts larger than a supplied total are discarded as unreliable usage, without changing scenario acceptance. Partial usage keeps missing values null; counts are not inferred by subtraction or text length. Unrelated metadata is ignored. Refusals and invalid completed responses preserve reported usage when available, because a rejected output can be billable. HTTP errors and timeouts commonly have unknown usage. These fields follow the [official Chat Completions usage definition](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create); no current prices or token estimates were fetched or hardcoded.

The old five-field crisis records and old endgame diagnostics serialize unchanged when measurement is absent. They remain valid under existing finalized-record guards. New records add `measurement`; the existing inspector automatically returns it. SQLite schema 2 and aggregate format 1 are unchanged. Tests restore both legacy crisis records and a finalized legacy endgame story without rewriting their diagnostic representation or accepted content. Existing tests also retain result-hash, snapshot, reconnect and private-projection coverage.

Objective repeated-title/content, duplicate-choice-text and identical-effects checks now attach fixed subcategories while retaining their existing `invalid_schema` category and identical acceptance/rejection conditions. No prompt, consequence, effect bound or valid proposal behavior was changed. An AST comparison against the baseline verified the crisis instructions and continuity prompt function unchanged. Content, endgame contract/prompt, provider configuration and frontend diffs are empty.

### Measured timing boundaries

All production duration measurements use `time.perf_counter`; game clocks/deadlines remain untouched.

| Field | Boundary and limitation |
| --- | --- |
| Existing `duration_seconds` | Service start through outcome completion, including attempted provider, contract validation and deterministic fallback selection if applicable; now stored to six decimal places |
| `provider_seconds` | Awaited adapter call, including its request construction, client/network work and response-envelope processing; **not network-only latency, TTFT or token throughput** |
| `validation_seconds` | Strict crisis/endgame contract validation call, including rejected contracts; excludes subsequent persistence and separate credential-output safeguard |
| `fallback_seconds` | Crisis authored selector and snapshot validation; null when not run. Endgame uses its already available deterministic summary, so no invented selection duration is reported |
| `availability_seconds` | Null: commit/publication occur after this immutable outcome is prepared; no inaccurate commit-to-browser interval is claimed |

Timeout reports include the measured attempted call and total fallback outcome duration. Disabled/configuration-before-request cases have no provider timing. Cancellation/restart/internal-state records without a completed trace remain unknown rather than becoming zero-cost or successful attempts. Durations are rounded only for serialization; ordering and intervals are monotonic.

## Evaluation methodology

The offline CLI has **no real-provider mode**. It neither loads `.env` nor constructs a network provider. Deterministic fake providers and scripted monotonic clocks pass through the actual production `GenerationService`, `generate_conclusion`, provider-response abstraction, contracts and diagnostic models. Fixture histories are created by playing the production mission/voting/consequence engine in memory with three synthetic players and a controlled game clock. It does not open a live database.

Six fixture histories cover: no prior decisions; several resolved decisions; major infrastructure damage; declining Public Trust; interconnected grid/water/care situations; and varied executed choices/metric outcomes. Separate fixtures complete an authored-reference ten-crisis victory and early defeat to construct authoritative endgame inputs. Authored content, history and consequence logic are reused, not reimplemented.

Twenty-nine cases include valid standalone outputs for each history, five valid historical links, malformed JSON, invalid effects/schema, provider failure, timeout, fabricated references, repeated title, exact repeated content, duplicate choice text, identical effects, missing usage, disabled generation, and seven victory/defeat endgame outcomes. Each case makes zero or one fake call; no automatic retries.

Outputs contain only case identifiers and typed diagnostics, grouped reliability/latency/usage/model summaries, optional projected costs and an unreviewed status. Prompts, responses, generated prose and synthetic private reports are not copied into evaluation records. The CLI can explicitly summarize an operator-selected mission through the existing read-only inspector. It refuses output paths that would overwrite that database or known SQLite/ownership sidecars, including existing hard links. Missing/invalid arguments yield a fixed error, not raw input/exception data.

### Counters, denominators and coverage

- `provider_attempts`: supplied outcomes whose trace records an attempted adapter call. Disabled generation and known configuration-before-request failures are excluded; legacy/unfinished traces are unknown. It measures calls attempted by the application, not proof of remote inference/billing.
- `accepted_count`: generated content admitted by the contract. `rejected_count` is JSON/schema/reference rejection among known attempts, distinct from provider errors and timeouts.
- Schema rejection includes existing objective repetition failures; separate repetition subcounts identify that subset. Historical rejection counts explicit unsupported references, not unverifiable prose.
- `accepted_rate`, `rejection_rate`, `attempted_fallback_rate` and attempted reason-specific rates divide by **known provider attempts**. All-outcome fallback rates and reason-specific rates divide by **all supplied outcome records**, including disabled fallback.
- Endgame and crisis summaries have the same definitions and remain separate. Missing usage/model/timing fields have explicit unknown counts. Configured model labels identify operator selection, not a verified provider-resolved model revision.
- The reporter calculates metrics for the supplied dataset. Controlled offline cases contain one complete outcome per attempted call, so their counters are exact. Production storage still retains final-per-crisis diagnostics: it is **not a complete audit of all manual retries, stale tasks or hard-killed requests**. An all-time request/billing count cannot be reconstructed from those records, and the report explicitly labels this coverage limit.

### Validity versus utilization

The contract tests whether explicit references correspond to actually supplied executed decisions. Validity may pass with an empty reference list. The reporter separately counts accepted outputs with supported references and accepted outputs without references.

Explicit reference utilization divides accepted outputs with at least one reference by **accepted outputs with history and measured reference count**. Fresh openings are excluded. This is a structural proxy, not evidence of meaningful incorporation. Semantic consistency, causal relevance, engagement and meaningful continuity remain `manual_review_required`. A valid citation can still accompany weak prose; a standalone event can be strategically good. No second model judges quality.

### Latency reporting

Each stage reports sample count, minimum, median/p50, nearest-rank p95 and maximum. Empty samples return null, not zero. Overall and per-operation distributions are available; timeout and fallback totals have separate groups. Legacy total duration is never relabeled as provider latency. Fixture timeouts are injected immediately while advancing scripted time: the simulated 60-second values do not measure hardware or real provider performance.

## Gameplay quality rubric and reusable sheet

Generate a reviewer sheet with `--review-template /tmp/consensus-review.json`. It defines **all five anchors for each criterion**, and produces one case row with null scores, blank notes and `not_reviewed` status. It never fills semantic ratings automatically. Review accepted content in the game's UI against its public recorded decisions; write high-level observations without copying role-private text, chat, identities or credentials.

| Criterion | 1 | 3 | 5 |
| --- | --- | --- | --- |
| Scenario clarity | Incomprehensible | Understandable with minor gaps | Immediately clear, concise, contextualized |
| Plausibility | Incompatible with setting/history | Mostly plausible | Convincing civic constraints grounded in events |
| Distinctiveness | Essentially repeats a crisis | Some novelty, familiar structure | Fresh pressure that develops the mission |
| Strategic tradeoffs | Obvious or identical choices | Real but uneven gains/costs | Three compelling, competing strategies |
| Metric relevance | Contradicts current conditions | Some relevant pressures | Coherent use of actual metric trajectory |
| Consequence coherence | Contradictory outcomes | Mostly coherent | Precise causal costs/benefits consistent with facts |
| Role relevance/privacy | Roles irrelevant or leakage | Some useful differences | Distinct perspectives materially affect strategy without leakage |
| Historical continuity | Invents/contradicts decisions | Valid standalone/weak linkage | Strong actual continuity without forced sequels |
| Narrative engagement | Confusing/uninteresting | Adequate civic stakes | Memorable stakes and sustained cooperative deliberation |

Levels 2 and 4 are explicitly defined in the generated sheet, not left to reviewer invention. Notes should explain scores and quote only safe public evidence when needed. The exact-repeat tests are objective rejection checks, not a calibrated semantic similarity score or a new blacklist.

## Cost estimator

Supply a JSON map of **configured model label → `input_per_million`, `output_per_million`**, using nonnegative finite decimal prices in one operator-selected currency. Prices are required for a cost projection; there is no default model price, currency conversion or speculative current pricing. Decimal arithmetic avoids binary floating-point monetary rounding.

Known request cost = `(reported input tokens × input rate + reported output tokens × output rate) / 1,000,000`. Both counts and the matching model price must be known. Rejected responses/refusals with usage are included. Unknown usage/pricing is counted separately; fallback never implies a free call. Known-token sums are explicitly partial sums with known/unknown request counts.

The utility reports known-usage subtotal, complete observed-batch estimate only when all costs/attempts are known, mean known-sample cost per crisis/endgame, conditional ten-crisis-plus-one-endgame mission projection, and repeated-mission projection. Future projections explicitly assume the known-usage samples represent future calls and one attempt per slot. Cached discounts, service tiers, different retry rates and missing samples can change bills; this is not an invoice or spending ceiling. Missing historical usage cannot be backfilled from prose length, duration or fallback status.

### Commands and hypothetical example

```sh
.venv/bin/python -m app.generation.evaluation \
  --output /tmp/ce94-baseline.json --review-template /tmp/ce94-review.json

# Optional: explicit read-only operator inspection. Never required for offline evaluation.
.venv/bin/python -m app.generation.evaluation \
  --database /absolute/private/mission.sqlite3 --mission-index 1 \
  --output /tmp/mission-evaluation.json

# Optional pricing map supplied by the operator:
.venv/bin/python -m app.generation.evaluation \
  --pricing /path/to/pricing.json --missions 3 --output /tmp/cost-evaluation.json
```

A tested **hypothetical**, synthetic-only map used `fixture-model-v1` prices of 1 input and 2 output currency units per million. With synthetic 1,000 input/600 output tokens on 22 cases, known subtotal is 0.0484; five attempted calls have unknown cost, so the complete batch estimate is null. Conditional means are 0.0022 per crisis and per endgame; projected ten-crisis mission 0.0242, three missions 0.0726. **These are arithmetic fixtures, not real prices, tokens or expenditures.**

## Baseline evidence

### Reproducible offline accounting baseline

| Metric | Result |
| --- | --- |
| Outcome records / known attempted calls / disabled outcomes | 29 / 27 / 2 |
| Accepted outputs | 14 (12 crisis, 2 endgame) |
| Fallbacks | 15: disabled 2, invalid continuity 2, invalid JSON 1, invalid schema 6, timeout 2, unavailable 2 |
| Accepted / attempted | 14/27 = 51.85% |
| Attempted fallbacks / attempted | 13/27 = 48.15% |
| Contract rejections / attempted | 9/27 = 33.33% |
| Objective repetition subset | 4, all still classified `invalid_schema` |
| Crisis reference utilization with history | 5/11 = 45.45% |
| Combined reference utilization with history | 7/13 = 53.85% |
| Recorded synthetic usage | 22 known cases, 5 unknown attempted cases; 22,000 input / 13,200 output / 35,200 total known tokens |
| Meaningful continuity / strategic quality | Unreviewed; no automatic score |

These are deliberate adversarial fixture proportions, **not a measured model success rate**. They establish correct counters, failure categorization and denominator handling.

| Scripted stage, seconds | n | min | p50 | p95 | max |
| --- | ---: | ---: | ---: | ---: | ---: |
| Total generation | 29 | 0.001 | 0.205 | 60.003 | 60.005 |
| Adapter call | 27 | 0.201 | 0.201 | 60.001 | 60.001 |
| Contract validation | 23 | 0.001 | 0.001 | 0.001 | 0.001 |
| Crisis fallback selection | 10 | 0.001 | 0.001 | 0.001 | 0.001 |
| Content availability after commit/delivery | 0 | unknown | unknown | unknown | unknown |

Scripted durations make regression comparisons reproducible. They do not establish a real latency SLA or prove that production validation always takes 1 ms.

### Existing real-provider evidence, not rerun

The earlier authorized four-call `gpt-6-luna` run accepted three crises and rejected one schema response into authored fallback: 75% accepted, 25% fallback in **four** samples. Total generation durations were 16.545, 26.630, 19.412 and 21.781 s; min 16.545, p50 20.5965, nearest-rank p95/max 26.630 s. All HTTP statuses were 200. These historical totals cannot be split into adapter/validation times. No tokens or endgame result were recorded.

Of the accepted outputs, the two with history supplied no references: explicit utilization 0/2. That does not prove the model cannot use history; the small run simply failed to demonstrate meaningful continuity. The old schema rejection cannot be retrospectively assigned one of the new objective subcategories. See [the retained acceptance report](MILESTONE_9_3_REAL_PROVIDER_ACCEPTANCE.md). **No real-provider run was executed in Milestone 9.4.**

## Prepared real-provider protocol — NOT executed or approved

The previous four-call authorization is exhausted and does not authorize this protocol. Proposed maximum is **six calls**, no retries:

| Call | Operation | Synthetic authoritative input |
| --- | --- | --- |
| 1 | Crisis | Fresh opening, empty history |
| 2 | Crisis | Several completed decisions and major infrastructure damage |
| 3 | Crisis | Declining Public Trust with recorded gains/costs |
| 4 | Crisis | Interconnected prior events and varied executed choices |
| 5 | Endgame | Isolated ten-crisis victory fixture, completed locally without paid crisis calls |
| 6 | Endgame | Isolated early-defeat fixture |

Before execution, present the exact configured model/timeout, current operator-supplied input/output prices, explicit assumed input/output token budgets for crisis and endgame, expected expenditure and a separately approved maximum spend. With assumed counts `Ic, Oc, Ie, Oe` and prices `Pin, Pout`, expected expenditure is `(4×(Ic×Pin + Oc×Pout) + 2×(Ie×Pin + Oe×Pout)) / 1,000,000`. **Required prices/count assumptions are not supplied, so expected real expenditure is currently unknown and this is not ready to execute.** A conditional estimate is not a guaranteed billing cap.

Use only isolated fixtures; preserve normal request construction, validation and fallback. Count every attempted call against the cap even if it times out or has unknown billing. Stop on budget exhaustion or unexpected authorization/configuration failure; do not retry or start a paid ten-crisis campaign. Report actual usage/cost coverage separately from projected assumptions. Retain sanitized records and human scores, not raw provider payloads or private context.

Explicit acceptance criteria for that later small run:

- Zero unsupported references admitted, zero privacy leaks or authoritative state changes from prose.
- Both endgames validate and remain consistent with victory/defeat; at least three of four crises validate. Report each failure independently, without salvaging the result through an extra request.
- At least one of the three history-bearing crisis cases has a human-confirmed meaningful reference to an actual executed decision/consequence. Empty references alone do not meet this criterion.
- Review every accepted output using the rubric: scores at least 3 for clarity, plausibility, distinctiveness, tradeoffs, metric relevance, consequence coherence, role relevance and engagement; at least one history case scores at least 4 for continuity. Report reviewer notes rather than model-generated ratings.
- Capture known adapter/validation/total stages and usage, label missing values, and show min/p50/p95/max with small sample counts. Respect the approved timeout; confirm the existing UI/mission remains responsive while awaiting content. A six-sample p95 is not a production SLA.
- Display one accepted real endgame in the review and verify all statistics and cited facts against authority, including reconnect. If either endgame falls back, record that gap instead of claiming acceptance.

## Verification results

All development/verification providers are fake or `httpx.MockTransport`; no real API credentials are required.

| Command | Result |
| --- | --- |
| `timeout 90 .venv/bin/python -m pytest backend/tests -q -x -o faulthandler_timeout=40` | **578 passed**, one pre-existing Starlette/httpx TestClient deprecation warning, 19.89 s |
| `timeout 120 .venv/bin/python -m pytest backend/tests/test_llm_evaluation.py -q -x -o faulthandler_timeout=40` | **36 passed**, same warning, 1.40 s (also included in full run) |
| Capture-enabled frontend test command below | **108 passed**, zero failures/skips, 315.32 ms |
| `npm --prefix frontend run build` | Includes `tsc --noEmit`; TypeScript and Vite passed, 43 modules, 498 ms Vite build |
| `.venv/bin/python -m pip check` | No broken requirements |
| `npm --prefix frontend ls --depth=0` | Valid frontend dependency tree |
| `git diff --check` | Passed |
| AST comparison of baseline/current `INSTRUCTIONS` and `continuity_instructions` | Unchanged |
| Diff of authored content, endgame contract/prompt, provider configuration and frontend | Empty |

Frontend invocation:

```sh
MISSION_RESTART_FILE=/tmp/ce-m7-restart.json \
MISSION_REVIEW_FILE=/tmp/ce-m6-live.json \
CHAT_ACCEPTANCE_FILE=/tmp/ce-chat-5-1.json \
EXPANSION_REVIEW_FILE=/tmp/ce-m8-live.json npm --prefix frontend test
```

The 36 targeted cases verify counters and reason/rate denominators, reference validity versus utilization, percentile definitions, unknown/partial/unreliable usage, real adapter usage extraction through mock HTTP responses, billable rejected outputs, disabled/configuration handling, timing stages, pricing arithmetic/model matching/missing cost, deterministic reproduction with credential access/network provider disabled, all six fixture contexts, rubric anchors, privacy, legacy crisis/endgame diagnostics, independent voting/timer/metric/reconnect progress during held endgame inference, CLI artifacts and refusal to overwrite a database. Existing full-suite tests cover stale/cached outcomes, exactly-once state, voting, private projections and reconnect/restart behavior.

Two intermediate full-suite runs hit the existing intermittent in-process WebSocket `TestClient.receive_json` stalls, once in the campaign reconnect test and once in the identity/review test. Each run was bounded by `timeout`; no unrelated transport change was made. An intermediate 575-test run and the final 578-test run passed. This test-harness flakiness remains a known limitation; the actual local network smoke checks below also passed.

```sh
timeout 90 .venv/bin/python backend/tests/smoke_adaptive_narrative.py
timeout 90 node --experimental-websocket frontend/tests/smokeReconnection.mjs
```

Both passed. The first ran three separate ten-crisis games with three real WebSocket clients and fake inference: accepted story, restart while pending, and provider failure fallback. It preserved mixed crisis sources, stable history/metrics, private intelligence boundaries and one request per normal slot. The second used production controllers through Vite to verify individual interruption, backend restart, saved identities/roles/history/chat, continued voting/timers and the existing presence/progression UX. These are real local network checks with synthetic inference, not human browser/mobile acceptance or paid model tests.

The offline CLI and hypothetical cost command above also passed, producing `/tmp/ce94-baseline.json`, `/tmp/ce94-review.json` and `/tmp/ce94-cost-example.json`. These temporary files are reproducible outputs; the baseline tables retain their findings if temporary files are cleaned up. No live mission database was inspected or mutated during this milestone.

## Exact file inventory

Added:

- `backend/app/generation/measurement.py`: bounded numeric usage, shared private measurement model and monotonic stage recorder.
- `backend/app/generation/evaluation_report.py`: counters/denominators, latency distributions, token coverage and explicit-price Decimal projections.
- `backend/app/generation/evaluation_fixtures.py`: production-engine synthetic histories and deterministic providers/clocks.
- `backend/app/generation/evaluation.py`: offline-only CLI, existing read-only operator inspection and reusable human review sheet.
- `backend/tests/test_llm_evaluation.py`: 36 targeted test cases.
- `docs/MILESTONE_9_4_LLM_EVALUATION.md`: this report, including pre-edit audit and future acceptance protocol.

Modified:

- `README.md`: offline/operator evaluation commands and scope.
- `backend/app/domain.py`: crisis diagnostics inherit the optional measurement field.
- `backend/app/narrative_models.py`: endgame diagnostics share that field.
- `backend/app/generation/provider.py`: whitelist reported usage, preserve it for rejected envelopes/refusals, mark pre-request configuration/disabled errors.
- `backend/app/generation/contract.py`: safe error metadata and exact-repetition subcategories, with unchanged acceptance rules.
- `backend/app/generation/service.py`: shared measurement boundaries, accepted reference counts and injectable monotonic clock.
- `backend/app/generation/live.py`: persist service measurements with existing crisis admission.
- `backend/app/generation/conclusion_live.py`: shared endgame timing/usage/reference measurements in existing endgame diagnostic.
- `backend/tests/test_durable_generation_diagnostics.py`: expect the new optional field on newly measured records; existing round-trip/privacy assertions retained.

No dependencies, SQL schema, result hashes, authored content, model settings, prompts, frontend or gameplay rules changed. All work remains local; no commit, tag or push.

## Outstanding review and recommendation for Milestone 9.5

Human gameplay scores remain unfilled. Real-provider usage/cost and meaningful historical continuity still need the separately approved protocol; so do real endgame/browser quality and production-scale latency measurements. Production final-outcome diagnostics cannot audit every historical retry or recover usage from interrupted calls. Browser-delivery availability is deliberately unknown. Validation remains bounded synchronous CPU work; held-provider tests demonstrate independent voting/timers/reconnect/completion, not zero event-loop blocking under arbitrary load.

Milestone 9.5 should first run the small priced, approved protocol and review schema subcategories and semantic ratings. Optimize the demonstrated failure modes and measured latency/cost afterward, in separate reviewable changes. Do not tune prompts to the synthetic baseline's adversarial pass percentage or relax validation to raise acceptance.
