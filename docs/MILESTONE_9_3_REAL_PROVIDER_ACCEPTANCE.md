# Milestone 9.3 — Limited real-provider acceptance

Date: 2026-10-29. The user explicitly authorized four requests for four crises. This is an acceptance run, not another development milestone. No gameplay, prompt, contract or provider code was changed. No commits, tags or pushes were made.

## Scope and isolation

Exactly four real provider requests were attempted, one each for Crises 1–4, with no retries. There was no endgame request, fifth crisis request or full campaign run. The user's final authorization specified four crises, so the proposed separate endgame acceptance remains untested.

The existing `ChatCompletionsProvider`, `LiveGeneration`, strict admission, deterministic fallback, `MissionStore` voting/consequences and SQLite recovery paths were exercised. Configuration was loaded from `backend/.env` without printing credentials or endpoint details: enabled, `gpt-6-luna`, `json_schema`, 60-second timeout. A hard four-call wrapper enforced the budget.

A one-off harness at `/tmp/ce_real_acceptance_4.py` ran against a new private temporary fixture database with three synthetic players. It never opened the user's live mission database and never instantiated the endgame coordinator. After each of the first three crises, synthetic players unanimously chose the option maximizing the actual post-clamp weakest metric, using normal voting and result acknowledgement. Crisis 4 remained at briefing.

Command:

```sh
.venv/bin/python /tmp/ce_real_acceptance_4.py
```

No paid requests were made by regression tests; these four calls were a separate, explicitly authorized real-provider acceptance run.

## Results

| Crisis | Accepted title | HTTP | Persisted source/category | Duration |
| --- | --- | --- | --- | --- |
| 1 | Anomaly in the Water Network | 200 | generated / success | 16.545 s |
| 2 | Heat Dome Strains the Cooling Network | 200 | generated / success | 26.630 s |
| 3 | Care at Capacity | 200 | authored_fallback / invalid_schema | 19.412 s |
| 4 | The Rent Aid Payment Gap | 200 | generated / success | 21.781 s |

Three generated scenarios passed strict validation and became authoritative briefing snapshots. The third response was rejected as `invalid_schema`; the displayed Care at Capacity scenario came from the deterministic authored selector. HTTP 200 indicates provider response success, not scenario validity. The exact field/rule behind that schema rejection was not captured: raw provider responses were not persisted, and the diagnostic deliberately retains only the bounded failure category. No cause beyond that category is claimed and no paid retry was made.

All four requests finished below the configured 60-second bound. Total recorded generation duration was 84.368 seconds.

## Continuity findings

Authoritative context checks passed for each request:

- Crisis 1: zero completed decisions.
- Crisis 2: the actual first decision, its selected consequence and applied deltas; metrics 67 Infrastructure, 72 Public Trust, 65 Economy, 78 Safety.
- Crisis 3: two actual decisions, their selected consequences and deltas; metrics 69, 69, 71, 71 in the same order.
- Crisis 4: three actual decisions, including the authored fallback's executed result; metrics 75, 77, 61, 63.

The executed choices were: district-only water notice (Crisis 1/A), voluntary heat-demand cuts and guidance (Crisis 2/B), and pausing planned care (Crisis 3/C). Submitted decisions, stable scenario IDs, consequences and actual applied deltas matched saved authority exactly. The context window contained 0, 1, 2 and 3 decisions respectively.

**Meaningful generated narrative continuity was not demonstrated by this sample.** All three accepted generated scenarios used `continuity_references: []`. Crisis 2 introduced a heat event independently of the earlier water decision. Crisis 4 introduced a rental-assistance software/payment problem without an explicit causal connection to the earlier executed decisions. These standalone scenarios are permitted by the contract; their acceptance does not establish adaptive sequel quality.

The authored Crisis 3 briefing happens to mention heat illness and a water alert, consistent with this fixture's prior situations. This is authored content and is not evidence that the model produced a coherent sequel. No fabricated explicit reference was accepted, but no accepted generated historical reference was produced either.

## Persistence, projection and diagnostics checks

All assertions passed:

- Request metrics, selected historical choices, scenario identifiers, consequences and applied deltas matched the authoritative records.
- All three synthetic client projections received the same public briefing.
- Each projection contained only its assigned roles' private intelligence, with other-role intelligence absent.
- Internal generation diagnostics were absent from client snapshots.
- Private operator inspection returned the same four five-field records as the committed outcomes.
- Closing and reopening the isolated store preserved accepted Crisis 4, role assignments and all four diagnostics without another request.

This run used the real provider and production generation/store paths with synthetic players and projection checks. It did not exercise a real browser or render a real endgame review. The existing fake-provider three-WebSocket-client and frontend review tests remain the evidence for those paths.

## Evidence and limitations

Temporary local artifacts:

- Harness: `/tmp/ce_real_acceptance_4.py`
- Sanitized run log: `/tmp/ce-real-four-acceptance.log`
- Accepted public scenarios, executed synthetic decisions and checks: `/tmp/ce-real-four-2026-10-29-nkre90xq/public-evidence.json`
- Isolated fixture database: `/tmp/ce-real-four-2026-10-29-nkre90xq/isolated.sqlite3`

The public evidence file contains only accepted public scenario projections, validated reference lists, executed synthetic public decisions and sanitized diagnostics. It excludes prompts, raw provider responses, credentials, player identities and private intelligence. The database contains synthetic game state and should remain private. Temporary artifacts are not guaranteed to survive cleanup; the findings above are retained in this report.

The request budget is exhausted: four requests used, zero endgame requests. Remaining acceptance gaps are a real generated crisis that meaningfully references an executed historical decision, a real validated endgame conclusion and its browser review, and the exact rule behind the one schema rejection. No production fix or extra inference was performed on the basis of this small sample.
