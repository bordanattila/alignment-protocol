# Milestone 9.5 Stage B — authorized real-provider revalidation

The existing counted harness executed **once**, making exactly four sequential crisis requests using `gpt-6-luna`, the original Stage A fixture order, the revised Stage B continuity prompt, and otherwise unchanged production generation/validation pathways. **All four returned HTTP 200 and were accepted as generated scenarios. No fallback occurred.** There were no retries, replacement requests, additional test calls, or endgame requests. The authorization is exhausted; no further requests were made.

[Paired public review](acceptance/milestone_9_5_stage_b_revalidation/review.html) · [Unscored human review sheet](acceptance/milestone_9_5_stage_b_revalidation/human-review.json) · [Machine-readable paired comparison](acceptance/milestone_9_5_stage_b_revalidation/comparison.json)

## Individual real results

Latency below is measured total generation time; provider adapter and validation durations are retained separately in diagnostics. References identify actual authoritative `(crisis number, selected choice)` pairs. Input/output counts are provider-reported usage. Costs use the supplied USD rates: $0.10 per million input and $0.50 per million output tokens.

| Original fixture | Accepted / source | Explicit references | Total latency | Input / output tokens | Calculated USD cost | Fallback reason |
| --- | --- | --- | ---: | ---: | ---: | --- |
| Fresh | Yes / generated | None (empty history) | 32.142340 s | 2,086 / 2,050 | $0.0012336 | None |
| Infrastructure damage | Yes / generated | Crisis 3 choice A; Crisis 4 choice B | 28.300592 s | 3,311 / 2,390 | $0.0015261 | None |
| Declining Public Trust | Yes / generated | Crisis 4 choice B | 23.566773 s | 3,351 / 1,904 | $0.0012871 | None |
| Interconnected events | Yes / generated | Crisis 2 choice B; Crisis 3 choice A | 20.568565 s | 3,051 / 1,625 | $0.0011176 | None |

Accepted public titles, in order:

1. An Unverified Water Alert
2. The Double-Billed City
3. A Bridge Begins to Hum
4. The Freight Viaduct Fracture

Provider adapter durations were 32.141843, 28.300156, 23.566390, and 20.568149 seconds. Validation durations were 0.000392, 0.000390, 0.000345, and 0.000372 seconds. These timings do not measure browser delivery or player-perceived availability.

Totals: **11,799 input + 7,969 output = 19,768 tokens**. Calculated expenditure: **$0.0051644**, below the $0.0060 planning estimate and $1.00 administrative ceiling. Usage was available for all four requests; unknown-billing reserve is zero. Calculation: `(11,799 × 0.10 + 7,969 × 0.50) / 1,000,000`. This is an estimate using operator-supplied rates, not a provider invoice or guarantee of provider-side billing limits.

## Paired comparison with Stage A

Only the four original Stage A crisis attempts are included; its two endgames are excluded. The harness verified each fixture's authoritative public history and starting metrics against the original archive before dispatch.

| Measure | Stage A | Stage B revalidation |
| --- | ---: | ---: |
| Schema/strict backend admission | 4/4 accepted | 4/4 accepted |
| Authored fallback | 0/4 | 0/4 |
| History-bearing outputs with supported explicit references | 0/3 | 3/3 |
| Opening-crisis references | 0 | 0 |
| Total-generation latency p50 | 24.938657 s | 25.933683 s |
| Total-generation latency p95 / maximum | 29.722707 s | 32.142340 s |
| Reported input tokens | 11,679 | 11,799 |
| Reported output tokens | 7,255 | 7,969 |
| Calculated cost | $0.0047954 | $0.0051644 |
| Human-reviewed meaningful continuity | Pending | Pending |

| Fixture | Stage A → Stage B total latency | Stage A → Stage B input/output tokens | Stage A → Stage B calculated USD cost |
| --- | --- | --- | --- |
| Fresh | 29.722707 → 32.142340 s | 2,086/1,976 → 2,086/2,050 | $0.0011966 → $0.0012336 |
| Infrastructure damage | 27.820954 → 28.300592 s | 3,271/2,011 → 3,311/2,390 | $0.0013326 → $0.0015261 |
| Declining Public Trust | 22.056361 → 23.566773 s | 3,311/1,697 → 3,351/1,904 | $0.0011796 → $0.0012871 |
| Interconnected events | 20.737480 → 20.568565 s | 3,011/1,571 → 3,051/1,625 | $0.0010866 → $0.0011176 |

Structural reference utilization increased in this sample. Median latency and calculated cost increased; no performance improvement is established. Four samples, stochastic outputs, and uncontrolled provider conditions cannot establish causal performance effects or stable percentiles. The p95 calculation is nearest-rank, which equals the maximum for four samples.

No semantic ratings were assigned. Supported identifiers establish valid references, not meaningful causal continuity. Reviewers should compare the paired public briefings/options against the supplied actual prior decisions, recorded outcomes, and applied metric changes, then classify continuity as absent, superficial, meaningful, or contradictory with supporting text. Opening continuity may be not applicable. The human review sheet remains entirely unscored; Stage A semantic ratings also remain pending. Public-only evidence cannot establish private-role relevance.

## Integrity, privacy, and remaining limitations

All four cases passed unchanged history/metrics, unchanged finalized resolution hashes, common public projection, and per-player authorized private-intelligence filtering checks. Restart restored accepted crisis snapshots and assigned roles for all four isolated missions with **zero additional provider requests**. Source hashes remained unchanged, and both the 66-file preservation manifest and preparation packet checksums were verified. The original Stage A baseline and Stage B development/preparation artifacts were preserved in place.

The public archive contains sanitized diagnostics and synthetic public content/history only. It excludes the isolated SQLite database, credentials, prompts, raw provider responses, player/session identifiers, and private role intelligence. The paired HTML is an escaped, script-free offline review artifact; application UI code is unchanged. Its review checks record four paired cases and no assigned human ratings.

The **full backend suite timed out twice during preparation** in existing WebSocket TestClient receives: foundation reconnect, then campaign reconnect. It is **not reported passing**. Preparation's focused 54-test regression run, including eight protocol tests, passed; dependency and whitespace checks passed. Those offline results are separate from this four-request real-provider batch. No full-suite or frontend rerun was performed after this artifact-only execution. No generation, validation, provider configuration, voting, gameplay, or UI source files were changed.

## Execution and evidence

Executed exactly once from the repository root:

```bash
.venv/bin/python backend/tests/revalidate_stage_b.py \
  --authorized-live-four --output /tmp/ce95b-revalidation-live \
  > /tmp/ce95b-revalidation-live.log 2>&1
```

Exit status: 0. The directory remains private and contains the isolated synthetic SQLite database and durable journal. **Do not rerun this command.**

Offline archival/rendering used `/tmp/ce95b_archive_results.py`, with no provider imports or requests. Durable public artifacts are under `docs/acceptance/milestone_9_5_stage_b_revalidation/`: attempt journal, evaluation, diagnostics, comparison, public outputs, blank human-review sheet, privacy/history checks, restart checks, source-integrity checks, sanitized execution log, authorization record, review HTML/checks, and checksums. Final archive checks and `git diff --check` passed.

No further optimization, provider request, commit, tag, or push was performed. Awaiting human review.
