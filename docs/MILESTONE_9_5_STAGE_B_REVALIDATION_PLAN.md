# Milestone 9.5 Stage B revalidation — authorization checkpoint

Status: ready for separate execution authorization. **Zero real-provider requests executed during preparation.** No new real-provider acceptance, latency, usage, cost, or human continuity results are claimed.

## Scope and preserved evidence

Use the original Stage A fixtures in this fixed order: fresh, infrastructure damage, declining Public Trust, interconnected events. The harness asserts that their authoritative decision histories and metric values exactly match the archived Stage A public review before dispatch. It uses the existing revised Stage B continuity prompt and production provider, strict validation, fallback selector, scenario admission, persistence, and projection pathways.

No prompt, validation, gameplay, voting, provider configuration, or UI changes were made during this preparation. `revalidation/milestone_9_5_stage_b/preserved-evidence.json` seals 66 pre-existing files, including production Python, frontend sources, all Stage A archive files, and the Stage B development reports/tests. The harness refuses to execute if these hashes change. Original Stage A review files and Stage B development evidence are preserved in place.

New preparation files are `backend/tests/revalidate_stage_b.py`, `backend/tests/test_stage_b_revalidation_protocol.py`, this plan, and the `docs/revalidation/milestone_9_5_stage_b/` packet. The packet contains the protocol, baseline comparison with pending new results, a blank human review, offline checks, and readiness evidence. Existing uncommitted Stage B changes predate this preparation.

## Configuration and cost preflight

Local `backend/.env` was inspected without exposing its values: generation enabled, model `gpt-6-luna`, timeout 60 seconds, response format `json_schema`, endpoint host `api.openai.com`, credentials present. No credential validity, account permissions, quota, or live model availability was tested. The harness loads this same file only in explicitly authorized live mode; fake mode neither loads credentials nor constructs the real adapter.

Operator-supplied USD planning rates are $0.10 per million input tokens and $0.50 per million output tokens. At 5,000 input and 2,000 output tokens:

- Each crisis: `(5,000 × 0.10 + 2,000 × 0.50) / 1,000,000 = $0.0015`.
- Four crises: **$0.0060 expected total**.
- Proposed administrative ceiling: **$1.00**, maximum **four attempts**, no retries or replacement requests.

Prices are operator assumptions, not a verified invoice or current pricing claim. The unchanged provider configuration does not establish a provider-side billing cap, output-token cap, or verified processing tier. A timeout can remain billable. Before each request the harness projects remaining costs using the higher of the planning estimate and largest observed per-request cost. Unknown usage receives a conservative reserve and stops further dispatch. Actual reported usage is multiplied by the supplied rates; this calculated cost is not a provider invoice.

## Counted execution protocol

1. After separate explicit authorization, verify the preservation manifest and unchanged local configuration. No paid smoke call precedes this batch.
2. Use one new private directory (mode 0700) with an isolated SQLite database and JSON evidence files created with mode 0600. Never use the production database. The harness refuses an existing output directory. Do not start a second directory to bypass the attempt limit.
3. Execute the four cases sequentially through the production generation service. Fsync each attempt to the journal **before** provider dispatch. A timeout, provider error, or invalid response consumes that attempt. No endgame calls are permitted. A fifth call is refused.
4. Apply strict validation and deterministic fallback unchanged. Record sanitized category, HTTP status, provider/validation/total generation timing, reported token usage, calculated cost, acceptance/fallback, and validated references. Do not persist raw provider responses, credentials, or prompts.
5. Verify that prior history/metrics and exactly-once resolution hashes remain unchanged. Verify authorized role projections and common public content, then restore from the isolated database without any additional provider calls.
6. Stop on authentication/configuration/quota concerns, unknown billing, or projected/observed spend concerns. Preserve partial results. An interrupted run is not resumed or replaced without new authorization; the journal records attempts even when a response was never received.
7. Keep private diagnostics and the isolated database local. Export only synthetic public review material, sanitized diagnostics, cost/comparison results, and review sheets as appropriate. Seal completed evidence separately without overwriting Stage A or development evidence.

The harness's live flag is an execution switch, **not authorization**. Do not invoke it until the user separately authorizes this four-attempt batch:

```bash
# Repository root; ONLY AFTER separate explicit authorization:
.venv/bin/python backend/tests/revalidate_stage_b.py \
  --authorized-live-four --output /tmp/ce95b-revalidation-live
```

The default command is offline and uses fake providers. Do not rerun a live batch under another output path after any attempt.

## Paired comparison and human review

The comparison uses only Stage A's four crises; its two endgame requests are excluded. Baseline accepted 4/4, fallback 0/4; none of the three history-bearing outputs used explicit references. Total-generation latency p50 was 24.938657 seconds and p95/max 29.722707 seconds. Reported usage totaled 11,679 input and 7,255 output tokens; calculated cost at the supplied rates is $0.0047954.

New real-provider measurements remain null until execution. After execution, pair each accepted result with its original Stage A case and compare schema acceptance, failure/fallback categories, supported reference use, actual latency, usage, and calculated cost. Report small-sample limitations: four requests cannot establish stable latency percentiles or prove a causal performance improvement.

Human reviewers must read the generated public briefing/options against the supplied actual decisions and outcomes. Classify continuity as absent, superficial, meaningful, or contradictory, with concrete quotations/evidence; opening continuity can be not applicable. References alone do not establish meaningful continuity, and empty references remain valid. Compare both baseline and new outputs; existing Stage A human scores are unreviewed, so improvement cannot yet be claimed. Keep unsupported ratings null. Public-only review cannot assess private-role relevance.

## Offline verification

- New protocol readiness tests: **8 passed**. Guards cover exact case list/cost, count-before-dispatch, fifth-call refusal, budget refusal, unauthorized endgames/config drift, timeout consumption without retry, unknown billing stop, credential-free fake execution, preservation, restart, and pending human ratings.
- Protocol plus existing Stage B/continuity regressions: **54 passed**, one existing Starlette/httpx deprecation warning.
- Explicit four-case fake-provider dry runs: **passed** at `/tmp/ce95b-revalidation-ready-v2` and `/tmp/ce95b-revalidation-final`; all four admissions, common public projections, private-role filtering, unchanged prior result hashes/history/metrics, and restart checks passed. Synthetic timing/usage/cost are not real-provider evidence.
- Complete backend suite: two bounded runs stalled in existing WebSocket TestClient receives (foundation reconnect, then campaign reconnect); the first exited 124 at 90 seconds. Do not report the full suite as passing. Dependency check and whitespace check passed. Detailed outcomes are recorded in the packet's `readiness.json`.
- Frontend checks were not rerun for this preparation: no UI/frontend files changed, and the preservation manifest verifies frontend sources unchanged.

Commands used (all offline):

```bash
.venv/bin/python -m pytest backend/tests/test_stage_b_revalidation_protocol.py -q -x
.venv/bin/python -m pytest backend/tests/test_stage_b_revalidation_protocol.py backend/tests/test_stage_b_continuity.py backend/tests/test_generation_continuity.py -q
.venv/bin/python backend/tests/revalidate_stage_b.py --output /tmp/ce95b-revalidation-ready-v2
.venv/bin/python backend/tests/revalidate_stage_b.py --output /tmp/ce95b-revalidation-final
# Bounded full-suite run:
timeout 90 .venv/bin/python -m pytest backend/tests -q -o faulthandler_timeout=40
.venv/bin/python -m pip check
git diff --check
```

Awaiting separate authorization. No commit, tag, or push was performed.
