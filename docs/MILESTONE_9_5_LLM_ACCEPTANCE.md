# Milestone 9.5 — Stage A real-provider acceptance

Date: 2026-10-29. **The authorized six-request Stage A batch has executed. Automated acceptance is recorded below; human gameplay review is pending. Stage B had not started at the close of Stage A; see the dated update below. Milestone 9.5 is not fully complete.**

**Stage B update — 2026-10-30:** The historical Stage A status and measurements below are preserved. Stage B has now implemented a focused crisis continuity-instruction correction and opt-in offline contrasts, with latency and AI-recommendation audits. See [the Stage B report](MILESTONE_9_5_STAGE_B_CONTINUITY.md). All files in the Stage A acceptance archive, including diagnostics, review packet/template and integrity hashes, remain unchanged. No new real-provider calls were made; real-model improvement and human acceptance remain unverified.

[Open the public review packet](acceptance/milestone_9_5_stage_a/review.html) · [Human review sheet](acceptance/milestone_9_5_stage_a/human-review.json) · [Machine-readable results](acceptance/milestone_9_5_stage_a/evaluation.json)

## Authorization, configuration and isolation

The user separately and explicitly authorized up to six attempted requests: four crises and two endgames, `gpt-6-luna`, 60 seconds per request, no retries or replacements, and a $1.00 administrative expenditure ceiling. This superseded the earlier planning-only gate. The previous four-request authorization was not reused.

The batch used the unchanged `backend/.env` configuration: OpenAI endpoint, model `gpt-6-luna`, generation enabled, `json_schema`, required credential present and a 60.0-second timeout. API credentials were never printed or copied into reports. Standard/short-context processing is the operator's pricing assumption; the existing adapter does not explicitly set or verify a processing tier. All six actual responses were HTTP 200.

The Git baseline remains `8f6d6da`, committed Milestone 9.4. Before this execution the only local addition was the preflight report from the preceding turn; it was preserved as [PREFLIGHT.md](acceptance/milestone_9_5_stage_a/PREFLIGHT.md). Source hashes taken immediately before dispatch matched afterward for the provider, service, contract, context, endgame path, coordinator, configuration and mission store. No production code, prompts, configuration, validation, gameplay, metrics, authored content or frontend changed.

**Exactly six real requests were dispatched. There were no retries, replacement requests, credential-probe calls or paid campaign runs.** All real requests were sequential and counted durably before dispatch. Separate fake-provider dry runs exercised the harness without using the real-request authorization.

The one-shot harness reused all six existing `evaluation_fixtures.fixture` histories. It captured their stores without changing fixture decisions, metrics or request data. It installed the locally executed authored history as reference snapshots in new generated-mode aggregates, then used normal production services and admission methods for the one real output under test. Prior reference snapshots are not counted as provider attempts. A private, new SQLite database under `/tmp/ce95-stage-a-live-20261029/isolated.sqlite3` held these synthetic aggregates; no live mission database was opened or mutated.

## Cost assumptions, guard and measured usage

Approved planning inputs: USD, input $0.10/million, output $0.50/million; crisis assumption 5,000 input / 2,000 output; endgame assumption 8,000 input / 3,000 output. Expected batch expenditure was $0.0106; administrative ceiling $1.00.

Before each dispatch, the guard checked known calculated expenditure plus reserves for any unknown billing and projected remaining cases. Per-operation projections used the larger of the planning assumption and the largest observed per-operation cost. The largest pre-dispatch projected batch total was $0.0106, below the ceiling. A request-count guard and exclusive run-directory creation prevented accidental continuation/rerunning. No stop condition was triggered.

All six responses supplied reliable token counts. There were no unknown-usage or unknown-cost cases and no unknown-billing reserve was needed. Reported totals: **15,603 input + 8,804 output = 24,407 tokens**.

**Calculated batch cost at the supplied rates: $0.0059623**, comprising $0.0015603 input and $0.0044020 output. Crisis subtotal $0.0047954; endgame subtotal $0.0011669. This is a calculation from actual reported usage and operator prices, not a verified provider invoice or proof of Standard-tier billing. No cached-token discounts, alternate tiers or price substitutions are assumed.

The $1.00 limit was administrative, as authorized; timeout and estimates are not provider-side billing caps. All six permitted requests are now consumed even though monetary headroom remains. Any further paid request requires new authorization.

## Individual outcomes

Request numbers below identify independent fixture cases, not a sequential six-crisis mission. The infrastructure and trust fixtures target Crisis 5, interconnected events target Crisis 4, and the fresh fixture targets Crisis 1.

| # | Fixture / accepted output | Result | Input / output tokens | Calculated USD | Explicit references |
| --- | --- | --- | ---: | ---: | --- |
| 1 | Fresh — **The Water Allocation Error** | Generated, accepted | 2,086 / 1,976 | 0.0011966 | 0 |
| 2 | Infrastructure damage — **The Civic Compute Cooling Failure** | Generated, accepted | 3,271 / 2,011 | 0.0013326 | 0 |
| 3 | Declining trust — **The CivicPass Exposure** | Generated, accepted | 3,311 / 1,697 | 0.0011796 | 0 |
| 4 | Interconnected events — **The Freight Queue** | Generated, accepted | 3,011 / 1,571 | 0.0010866 | 0 |
| 5 | Ten-crisis victory ending | Generated, accepted | 2,363 / 776 | 0.0006243 | 7 unique recorded decisions |
| 6 | Early-defeat ending | Generated, accepted | 1,561 / 773 | 0.0005426 | 4 unique recorded decisions |

All rows: HTTP 200, `source: generated`, `category: success`, no fallback, schema issue, timeout or provider error. Empty crisis references remain valid under the unchanged optional-continuity contract; they are not reclassified as utilization successes.

| # | Adapter seconds | Contract-validation seconds | Total-generation seconds |
| --- | ---: | ---: | ---: |
| 1 | 29.722232 | 0.000372 | 29.722707 |
| 2 | 27.820314 | 0.000581 | 27.820954 |
| 3 | 22.055914 | 0.000407 | 22.056361 |
| 4 | 20.737118 | 0.000325 | 20.737480 |
| 5 | 10.207024 | 0.000161 | 10.207252 |
| 6 | 11.301509 | 0.000293 | 11.301872 |

Measured with production monotonic instrumentation. Adapter duration includes request construction, HTTP/client work and response-envelope parsing. It is not pure network latency, time to first token or browser delivery. Contract timing excludes persistence and the separate credential-output safeguard. UI-delivery/availability duration remains unknown; no zero or synthetic value is substituted.

## Reliability and latency summary

| Measurement | Crises | Endgames | Combined |
| --- | ---: | ---: | ---: |
| Attempts / accepted | 4 / 4 | 2 / 2 | 6 / 6 |
| Acceptance rate | 100% | 100% | 100% |
| Fallbacks / contract rejections / timeouts / provider errors | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| Usage coverage | 4/4 | 2/2 | 6/6 |
| Total seconds minimum | 20.737480 | 10.207252 | 10.207252 |
| Total seconds median/p50 | 24.938657 | 10.754562 | 21.396921 |
| Total seconds nearest-rank p95 | 29.722707 | 11.301872 | 29.722707 |
| Total seconds maximum | 29.722707 | 11.301872 | 29.722707 |
| Adapter seconds minimum | 20.737118 | 10.207024 | 10.207024 |
| Adapter seconds median/p50 | 24.938114 | 10.754266 | 21.396516 |
| Adapter seconds nearest-rank p95/max | 29.722232 | 11.301509 | 29.722232 |

Contract validation ranged 0.000161–0.000581 seconds, combined median 0.000348 and p95/max 0.000581. Thus the measured adapter interval dominates these samples. No finer attribution to network, model reasoning, context size or provider scheduling is established.

Sample sizes are four crises and two endings. A 100% observed acceptance rate or a nearest-rank p95 equal to the maximum in this sample does not establish production reliability or an SLA.

### Preliminary target status

- Crisis acceptance ≥3/4: **met, 4/4**.
- Endgame acceptance 2/2: **met, 2/2**.
- Unsupported explicit historical references admitted: **zero observed**; valid endgame references checked against supplied authoritative history. This is not semantic verification of every sentence.
- Other-role private intelligence in checked projections: **none**. No private intelligence, identity or credential entered the public packet.
- Authoritative history/metric changes caused by generated prose: **none**; records and hashes unchanged.
- Exploratory crisis p95 ≤15 seconds: **not met, 29.722707 seconds**.
- Human-confirmed meaningful crisis continuity: **not demonstrated yet; review pending**. All three history-bearing cases supplied `[]`.

## Continuity and gameplay review

The three history-bearing crisis requests received real executed choices, selected consequences, actual metric deltas and the existing bounded memory. Nonetheless, their accepted reference lists were empty: **explicit crisis utilization is 0/3**, excluding the fresh opening. All four crisis proposals were structurally valid standalone events. This does not establish meaningful narrative continuity, nor does it by itself prove that every implicit thematic connection is absent.

Both endings supplied valid explicit references. Victory cites seven unique completed decisions across its three sections; defeat cites all four completed decisions. Their sections and server-resolved source excerpts are reproduced in the public packet. Supported references are structural evidence, not automatic human quality scores.

The existing [nine-criterion reviewer sheet](acceptance/milestone_9_5_stage_a/human-review.json) contains null scores, blank notes and pending continuity classifications. Please classify crisis continuity as absent, superficial, meaningful or contradictory and compare against the actual prior decisions shown alongside each case. At least one human-confirmed meaningful connection is required among the three history-bearing crisis cases. No score or classification was invented by the assistant.

Review clarity, plausibility, distinctiveness, tradeoffs, metric relevance, consequence coherence, role relevance/privacy, historical continuity and engagement using the existing 1–5 anchors. Endgame criteria that are not applicable should be explained as such by the reviewer. The shared packet intentionally excludes role-private intelligence; role-relevance review still needs separately authorized role-specific inspection. It cannot be completed honestly from public descriptions alone.

## Real endgame admission, review display and restart evidence

Both real accepted narratives were admitted by `MissionStore.finish_conclusion`, persisted as immutable terminal snapshots, then restored without additional provider calls. Generated prose did not alter outcome, score, metrics or history.

| Fixture | Authoritative outcome | Completed crises | Final metrics: Infrastructure / Trust / Economy / Safety | Consensus Score |
| --- | --- | ---: | --- | ---: |
| Victory | Victory | 10 | 55 / 49 / 55 / 64 | 55.75 |
| Early defeat | Defeat; Economy at zero | 4 | 69 / 49 / 0 / 100 | 54.5 |

The **actual accepted real outputs** were rendered with the unchanged `MissionReview` React component and existing CSS. Automated checks verified both outcome labels, AI-interpretation attribution, three generated sections, the original score and all four metric series per review. Public HTML was served over loopback and returned HTTP 200. The Codex browser-tab open was queued; no human browser acceptance is claimed.

- Local preview while the static server runs: `http://127.0.0.1:18775/review.html`.
- Persistent artifact: [review.html](acceptance/milestone_9_5_stage_a/review.html).
- Rendering evidence: [review.html.checks.json](acceptance/milestone_9_5_stage_a/review.html.checks.json).
- Restart evidence: [restart-checks.json](acceptance/milestone_9_5_stage_a/restart-checks.json).

All six accepted crisis/endgame snapshots, roles and terminal summaries survived store restart. Result hashes were checked before/after each generation. Both terminal summaries remain equal across restart. Live reconnect/browser interaction is covered by the unchanged preflight fake-provider network tests; this real batch did not add another live WebSocket playthrough. Narrative semantic accuracy and user reading experience remain human review items.

## Comparison with the older four-request sample

| Measure | Earlier sequential four-crisis sample | Stage A isolated-fixture batch |
| --- | --- | --- |
| Model / timeout | `gpt-6-luna` / 60 s | Same |
| Crisis acceptance | 3/4 | 4/4 |
| Crisis fallback | 1 schema rejection | 0 |
| Crisis total p50 / p95 | 20.5965 / 26.630 s | 24.938657 / 29.722707 s |
| Explicit crisis utilization with history | 0/2 accepted history-bearing outputs | 0/3 |
| Real endgames | Not tested | 2/2 accepted with supported references |
| Usage and separate stage timing | Not retained | Present for all six |

The histories, content and batch design differ, and both samples are small. This is descriptive evidence, **not proof of an optimization, causal improvement or regression**. The prior schema failure cannot be attributed retroactively to a new rejection subcategory. Its missing usage/stage measurements stay unknown. No generation behavior changed between this preflight and Stage A.

## Verification and commands

The one-shot harness was created at `/tmp/ce95_stage_a.py`. Its fake-provider dry run verified counting, spend checks, fixture capture/admission, privacy and restart before paid dispatch. The initial dry run caught only an overly strict test comparison of JSON dictionary order; that comparison was corrected to compare parsed values. Production code and validation were untouched. Dry-run outcomes are not included in real-provider statistics.

Commands used for Stage A:

```sh
# Fake-provider preparation only:
.venv/bin/python /tmp/ce95_stage_a.py

# Executed ONCE under the explicit six-request authorization; budget now exhausted:
.venv/bin/python /tmp/ce95_stage_a.py --authorized-live-six

# Offline rendering of real accepted terminal snapshots:
node /tmp/ce95_render_review.cjs \
  /tmp/ce95-stage-a-live-20261029/public-review.json \
  /tmp/ce95-stage-a-live-20261029/terminal-public-snapshots.json \
  /tmp/ce95-stage-a-live-20261029/review.html

git diff --check
```

Do not rerun the live command. The existing directory prevents replacing this batch, and any additional paid run requires new authorization.

Supplemental artifact checks passed: six durable attempt entries; six accepted records; unchanged production-source hashes; unchanged history, metrics and finalized result hashes; common public projections; per-player private-intelligence filtering; accepted snapshot/role/story preservation after restart; no extra provider request on recovery; existing-component render checks and local HTTP delivery; API-key, player-ID/hash and private-intelligence exclusion from the public archive; preserved baseline artifact checksums.

The preflight verification applies to the identical unchanged production sources: **578 backend tests**, **108 frontend tests**, type-check/build, dependency checks, whitespace checks, three-client fake-provider generation/endgame smoke and Vite/controller reconnect smoke passed. A known intermittent in-process TestClient receive stall required a bounded backend rerun; no transport fix was made. Exact preflight commands/results are retained in [PREFLIGHT.md](acceptance/milestone_9_5_stage_a/PREFLIGHT.md). The full suite was not redundantly repeated after a documentation/test-artifact-only execution; no Stage B regression changes exist to test.

## Baseline preservation and exact inventory

Repository additions/updates are documentation and accepted public review artifacts only:

- Updated `docs/MILESTONE_9_5_LLM_ACCEPTANCE.md` — this Stage A report.
- Added `docs/acceptance/milestone_9_5_stage_a/README.md` — packet instructions and remaining private-role review limitation.
- `PREFLIGHT.md` — preserved original planning checkpoint.
- `evaluation.json` — existing reporter output, actual timings/usage, supplied-rate cost and authorization accounting.
- `diagnostics.json` — the six individual existing typed diagnostic records.
- `attempt-journal.json` — six entries counted before dispatch, projections and calculated request costs.
- `public-review.json` — accepted public crisis/story content plus authoritative prior decisions; no private intelligence.
- `human-review.json` — existing rubric, blank scores/notes, pending classifications.
- `automated-checks.json` — public/private projection and history/hash checks.
- `restart-checks.json` — six restored cases, no new provider calls.
- `source-integrity.json` — unchanged production-source hashes.
- `review.html` and `review.html.checks.json` — real accepted output rendering and checks using the existing review component.
- `SHA256SUMS.json` — integrity hashes for the eleven original baseline files, excluding later explanatory README/main-report edits.

The private fixture database and one-shot harness remain outside the repository under `/tmp`; no raw prompts, raw provider payloads, API keys or private intelligence were added to the public archive. Accepted full game snapshots, including synthetic role intelligence, exist only in the isolated private fixture database as normal game state. The shared static server serves only the public archive, bound to `127.0.0.1`, not that database.

## Status and next action

Stage A's authorized automated baseline is complete. Human quality review and human browser/role-specific acceptance remain pending; **the full milestone is partially complete**.

Descriptive findings to review are the absent explicit crisis references and crisis latency above the exploratory target. No root cause is asserted beyond the measured facts, no prompt/model change is recommended as proven, and no optimization or Stage B work was performed. There are no schema failures in this batch to repair.

**Stop here and await the user's review.** No further provider requests, retries, replacement batch, Stage B optimization, commits, tags or pushes are authorized by this completed batch.
