# Milestone 9.5 Stage B — Continuity correction and focused audits

## Pre-edit investigation (2026-10-30)

Read repository instructions, the Stage B request, production context/provider/schema/reference validation, evaluator, Stage A examples and corresponding executed fixture histories before implementation. The existing uncommitted Stage A report/archive are preserved. Verified every Stage A checksum before edits.

### Concrete findings

- All Stage A crisis requests received correct authoritative history. `context.history` holds the three recent decisions, and `narrative_memory.significant_earlier_decisions` retains up to two larger earlier applied movements. The infrastructure and trust examples had four executed decisions available across those fields; interconnected had three. Missing history or an empty allowed-reference window does not explain the observed empty lists.
- The actual continuity prompt leads with “Narrative continuity is optional. A standalone crisis is always allowed,” offers an empty array immediately, and ends “An empty array remains valid.” The general instructions permit independent challenges and ask for adaptation, but provide no priority for an actual decision to shape later constraints. The schema also explicitly permits empty references. A standalone emergency fully satisfies this combination.
- The endgame contract differs: every section must cite one to three completed crisis numbers, and its instructions explicitly call for the whole recorded journey. Both Stage A endings complied. This difference is consistent with, but does not prove, why endgames used history more often.
- Pair formatting is already explicit and enforced by a request-specific schema and strict `(crisis_number, choice_id)` checking. The window includes usable choices; no evidence justifies expanding it, tightening the schema or adding a mandatory-reference rule.

### Stage A opportunities, not retroactive causal claims

1. **The Civic Compute Cooling Failure:** the briefing introduces a cooling-loop leak and scarce repair resources, without using the fixture's executed history. Waterline decision 2/B recorded pressure damage to older equipment; care decision 3/A recorded utility strain and depleted financial reserves; freight decision 4/B recorded deteriorating uninspected routes. A new compute fault could create a dilemma constrained by those already recorded maintenance/funding costs. It must not claim those choices caused the leak or consumed a particular unrecorded spare part.
2. **The CivicPass Exposure:** the new breach is presented independently. Executed decision 2/C already damaged confidence through delayed response, 3/B caused transfer-related distress/mistrust and 4/B created unequal access/public resentment; current Trust is 26. Those documented experiences could make the new disclosure/access tradeoff harder. They do not establish that an earlier choice caused a cyberattack, that residents already refused resets, or that a named protest occurred.
3. **The Freight Queue:** the new corrupted update and port queue are not caused by any supplied prior decision. Decision 2/B had actual distribution costs and equipment damage; 3/A had actual staffing/equipment expenses and utility strain. Those existing costs could constrain a new manual-dispatch response while the software incident remains independent. Do not invent an earlier port attack or turn a selected but unexecuted freight option into history.

**Actionable hypothesis:** the prompt makes optional standalone validity especially salient while leaving useful causal/constraint continuity under-specified. A concise, history-aware preference is justified; model-internal cause remains unknown. Keep standalone events valid and distinguish a new event's cause from the earlier constraints/mitigations shaping the response.

### Selected scope before editing

Change only crisis continuity instructions to prefer an actual earlier decision/consequence influencing the dilemma when suitable, explain use of exact existing reference pairs, and preserve independent events without fabricated causality. Keep opening behavior, JSON schema, reference window, numeric limits, validation, fallback, endgame prompt, provider settings and gameplay unchanged. Add labelled offline cases and a human guide; no semantic judge, no human scores and no paid calls. No latency tuning or recommendation-visibility change is justified by the current evidence alone.

## Implemented correction — the crisis prompt changed

Only `continuity_instructions` in the provider changed production behavior. The opening prompt is byte-for-byte identical to the Stage A implementation. The general crisis instructions, context builder, contract/schema, reference validation, repetition rules, endgame prompt/schema, configuration and engine remain unchanged.

For history-bearing requests the prior instructions opened with:

> Narrative continuity is optional. A standalone crisis is always allowed;

and ended by repeating that an empty array remained valid. The replacement adds this concrete preference:

> Prefer a crisis whose constraints or choices are materially shaped by one or two supplied decisions and their recorded consequences. State that connection in the public briefing and cite the exact (crisis_number, choice_id) pairs in continuity_references.

It then distinguishes substantive constraints from merely naming history, and separates a new emergency's cause from existing response constraints. Recorded costs, damage, lost trust or successful mitigation should affect the dilemma. A deficit is not proof of an event; unchosen options and missing older history cannot be claimed. Variety and `[]` remain explicitly allowed when no supported connection fits.

Exact allowed pairs are still supplied. There is no nonempty-array requirement, new output field, larger history window, automatic causal classifier or change to schema acceptance. Three distinct choices, existing effect bounds and strict fallbacks remain intact. This follows the general guidance to make task expectations explicit, rather than assuming the model infers the desired priority ([official prompt guidance](https://developers.openai.com/api/docs/guides/prompt-engineering)). No model-specific reasoning parameter was introduced.

Expected benefit: a clearer preference for decision-shaped later constraints. Risk: the model may still choose standalone events or may cite history superficially. Increased instructions might affect latency or distract from other requirements; no real result is claimed until a separately authorized test. Strict validation still cannot fully verify free-form causal truth.

## Ten offline contrasts and review guide

The existing evaluator gains `--continuity-cases`; its default 29 cases are unchanged. The flag adds ten deterministic fixture-provider outputs to the real `GenerationService`/contract/fallback path. It uses the existing synthetic histories, numeric usage and scripted clocks; it does not call a provider or read credentials.

| Case | Objective reference behavior | Human review question |
| --- | --- | --- |
| Fresh opening | Empty list accepted | Is the opening self-contained without invented prior actions? |
| One supported reference | Actual care decision 3/A accepted | Does utility strain materially constrain the new response? |
| Multiple supported references | Water 2/B and care 3/A accepted | Are the two recorded costs used coherently? |
| Relevant text, no reference | Empty list accepted despite historical wording | Is an actual connection present, and is the missing explicit citation a review finding? |
| Invented reference | Unsupported 10/C rejected into deterministic fallback | No semantic credit for nonexistent history |
| Contradictory prose with valid citation | Structurally accepted | Does the text reverse the actual recorded outcome? |
| Superficial mention with valid citation | Structurally accepted | Would the dilemma be unchanged if that mention were removed? |
| Develop an earlier consequence | Actual 3/A accepted | Do documented spending/utility costs shape the new allocation? |
| Interacting decisions | Actual 2/B and 3/A accepted | Do real equipment/distribution and care costs interact without invented origins? |
| Independent new emergency | Empty list accepted | Does the new event avoid attributing its cause to an earlier choice? |

These are authored contrasts illustrating limitations, **not model-generated successes or automatic human classifications**. The contradictory and superficial cases deliberately pass the structural contract. Their diagnostics and reporter still say semantic consistency and meaningful utilization require human review. The evaluator exports no scenario text/private intelligence into diagnostic records and leaves all nine human scores blank.

The opt-in run produces 39 outcomes / 37 fake attempts / 23 accepts / 16 fallbacks. Within the ten added cases, nine are structurally accepted and one invented reference falls back. Six of the nine accepted new cases have explicit references, including the deliberately bad prose examples. This demonstrates why reference utilization is only a structural proxy, not an improvement score.

Use the existing nine-criterion rubric and these qualitative distinctions; do not assign semantic scores from reference counts:

- **Absent:** No historical connection is established. Example: an independent lightning-damaged traffic relay, with no claim that earlier choices caused it. A good independent challenge is still allowed.
- **Superficial:** The history is mentioned but does not shape constraints or options. Example: “The city remembers opening temporary care wards” followed by a sensor procurement dilemma whose stakes are otherwise unchanged.
- **Meaningful:** A recorded consequence materially changes the present dilemma. Example: actual care decision 3/A strained essential utilities and depleted reserves; those documented costs constrain a new repair-versus-service allocation. Combining water 2/B's equipment damage/distribution costs with care 3/A's reserve depletion can create a grounded competing-resource dilemma. Do not claim the earlier choice caused a newly introduced fault.
- **Contradictory:** The narrative invents, misattributes or reverses history. Example: citing 3/A but claiming the wards left utilities unstrained and replenished reserves, opposite the actual outcome. A valid reference does not make this statement true.

For a real output, read its public context against executed choices and selected outcomes, ask what materially changes because of history, distinguish new fiction from prior facts, then record classification and notes using the existing rubric. Human ratings remain pending, including role-private relevance and browser acceptance. No Stage A human template or score was modified.

## Latency audit — evidence and limits

The immutable Stage A crisis adapter durations were 29.722232, 27.820314, 22.055914 and 20.737118 s; reported completion tokens were 1,976, 2,011, 1,697 and 1,571. Endgame adapter durations were 10.207024 and 11.301509 s, with 776 and 773 completion tokens. Validation ranged 0.000161–0.000581 s. Thus the measured adapter interval dominates this six-case sample; the validation implementation is not supported as the large observed bottleneck.

An offline audit reconstructed the baseline prompt function from the repository baseline and built requests through the current adapter with `httpx.MockTransport`, three samples for each of the six original fixtures. It exported only byte counts, structural counts and timings, not prompts or context. Byte counts are **not token counts**. The context/schema were identical in the before/after comparison.

| Fixture | Instructions before → after (bytes) | Public context bytes | Schema bytes | Full request before → after (bytes) |
| --- | --- | ---: | ---: | --- |
| Fresh | 2,451 → 2,451 | 463 | 3,329 | 10,065 → 10,065 |
| Infrastructure | 2,695 → 2,903 | 3,644 | 4,206 | 15,535 → 15,743 |
| Trust | 2,695 → 2,903 | 3,792 | 4,206 | 15,695 → 15,903 |
| Interconnected | 2,655 → 2,863 | 2,999 | 3,996 | 14,364 → 14,572 |
| Victory endgame | 936 → 936 | 7,526 | 800 | 10,921 → 10,921 |
| Defeat endgame | 936 → 936 | 4,140 | 781 | 7,247 → 7,247 |

“Instructions” exclude the inline JSON schema. For infrastructure/trust the full system message grows from 6,917 to 7,125 bytes, and interconnected from 6,667 to 6,875. The correction adds 208 bytes (about 1.3–1.5% of full request bytes) only for history-bearing crises. Opening/endgame requests are unchanged.

The crisis schema has five definitions and 24–32 property slots across its nodes, including exact allowed-pair branches. Endgame has one definition and six property slots. The endgame context is larger in bytes, yet its instructions/schema and completion token counts are smaller. Longer retained history alone cannot explain the observed crisis/endgame timing difference.

Local pre-mock-dispatch time, including schema generation, JSON serialization and HTTPX request setup, was roughly 0.33–1.73 ms across the final 18-call audit. This is a local mock measurement, not network or real-model latency. It found no request-construction defect warranting an optimization. In `json_schema` mode the schema appears in both the system message and `response_format`; removing the inline copy would alter request instructions and needs a controlled comparison, not an assumed speedup. The inline schema also supports `json_object` mode.

Configured generation parameters are model, non-streaming messages and response format, with the existing 60-second operation bound. No explicit temperature, reasoning effort, service tier, output-token cap, streaming or retry option is added. Existing field-length limits, 64 KiB proposal content validation and 128 KiB provider-response limit are structural/transport protections, not a provider output-token cap or billing cap.

Chat Completions can expose optional `completion_tokens_details.reasoning_tokens`, but the adapter retains only input/output/total counts. Raw Stage A responses were deliberately not retained, so whether those six responses included reasoning detail, and how much time was reasoning versus generation/transport, **cannot be recovered**. Reported completion counts include non-visible output; they cannot safely be equated with visible prose tokens ([official token-counting guidance](https://developers.openai.com/api/docs/guides/token-counting)).

Supported observation: the four longer crisis outputs coincided with longer adapter intervals than the two smaller endings. Unproven explanations include output generation time, reasoning, scheduling, connection setup, network latency and schema/prompt processing. The sample is too small and confounded to assign causation or select a different model.

**No latency parameter or transport optimization was made.** Do not claim the prompt correction makes generation faster. A later approved experiment could keep model, context and schema fixed, compare the revised prompt against the preserved baseline on the same three history fixtures, record full adapter/validation stages and whitelisted reasoning-token details if supplied, and separately test any proposed payload change. That experiment needs its own request/spend approval; no such call occurred here.

## AI recommendation visibility and authority audit

The product pitch explicitly puts AI advice in front of the team so players can combine private intelligence to accept or reject it. The product specification requires one clearly marked recommendation and its use after a second tied vote (`CONSENSUS_ENGINE_V0.1_PRODUCT_SPEC.md`, crisis design and Consensus Window rules). This is intentional public information, unlike role-private intelligence.

| Question | Current behavior and evidence |
| --- | --- |
| Before initial voting? | Yes: `App` renders `CrisisBriefing` whenever an active crisis exists. Its public panel shows the recommended choice description; nonvoting reference choices carry `AI Recommended` |
| To whom? | Every authorized player: `MissionStore.project` includes the same public `ai_recommendation_choice_id` and choices regardless of roles. Only `private_intelligence` is role-filtered |
| Consensus discussion? | Yes: the shared briefing/reference options remain below active consensus chat |
| Final voting? | Yes: `ResponseOptions` marks the same choice in both voting rounds, and the briefing still displays it |
| Post-crisis/review? | Yes: decision-locked view retains the public briefing; `DecisionStatus` says whether advice was followed. Saved results retain the recommended ID; `CrisisHistoryEntry` marks it beside original options |
| Automated decisions? | A unique plurality wins even against advice. An initial top tie opens the Consensus Window. A second tie selects the recommendation; a round with no votes uses the existing no-vote AI fallback |
| Preferred guidance? | It is visibly preferred **AI advice**, not merely a neutral choice description. No radio choice is preselected: `ResponseOptions` starts with empty selection. It is not represented as server-verified optimal, and players may vote otherwise |

No objective privacy or server-authority violation was found. Added tests cover common advice and role-filtered intelligence for 2/3/4 players through discussion, initial voting, consensus, final voting and decision review, and verify a non-AI plurality still wins. Existing tie/no-vote tests remain passing.

Recommendation: retain current shared advice and tie rules for this milestone. Hiding it by role or phase would change the intended deliberation/information model. Anchoring is a legitimate human-testing question; decide any delayed-disclosure or role-specific design separately, with explicit product approval and balanced-information testing. No frontend, recommendation display, selection default or voting behavior changed.

## Verification

All new generation/evaluation calls used deterministic providers or local mock transports. **Zero real-provider requests in Stage B.** The existing Stage A six-request authorization remains exhausted.

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
.venv/bin/python -m app.generation.evaluation --continuity-cases \
  --output /tmp/ce95b-offline-evaluation.json --review-template /tmp/ce95b-review.json
timeout 90 .venv/bin/python backend/tests/smoke_adaptive_narrative.py
timeout 90 node --experimental-websocket frontend/tests/smokeReconnection.mjs
# One-off local payload/size audit, using only mock HTTP transports:
.venv/bin/python /tmp/ce95b_payload_audit.py > /tmp/ce95b-payload-audit.json
```

Results: **607 backend tests passed** in 20.80 s, with the existing Starlette/httpx deprecation warning; **108 frontend tests passed**, zero failures/skips, 304.77 ms. TypeScript and Vite production build passed (43 modules, 519 ms Vite stage). Python dependencies, frontend dependency tree and whitespace check passed. The extended evaluator produced the 39 scripted outcomes described above.

The existing three-client smoke passed all three ten-crisis fake-provider cases: accepted story, pending restart fallback and provider failure fallback. It preserved mixed crisis sources, role privacy, actual voting reconnect, one inference per normal slot, history and metrics. The reconnect/controller/Vite smoke passed individual interruption, backend restart and presence/progression checks. No human browser acceptance is inferred from these network checks.

There are 29 new focused test cases: prompt content in both response formats and empty/history contexts; all ten structural contrasts; no automatic semantic scores; correct/wrong/out-of-window references; standalone compatibility; repeatable fallback; default diagnostic accounting unchanged; credential-free opt-in evaluator reproducibility/privacy; CLI output; common advice/privacy and non-AI plurality for 2/3/4 players. Existing tests cover repetition, private context canaries, endgame acceptance, cached/stale outcomes, immutable hashes and legacy/restart behavior.

An early focused run also passed 142 cases. The final full-suite result includes the opening-prompt preservation and final recommendation audit tests. No unrelated fixes or test-harness changes were needed.

## Preserved baseline and exact file inventory

All original files under `docs/acceptance/milestone_9_5_stage_a/` remain unchanged. The original diagnostics, public review HTML/data, human sheet, cost/token/latency records, request journal, source integrity and checksums are still the real-provider baseline. They are not reinterpreted as results of this new prompt. The Stage A report is updated only to link this Stage B work and qualify its historical status.

Modified:

- `backend/app/generation/provider.py`: history-aware crisis continuity instruction preference; opening request preserved.
- `backend/app/generation/evaluation_fixtures.py`: ten opt-in scripted contrasts using actual fixture outcomes.
- `backend/app/generation/evaluation.py`: `--continuity-cases` and opt-in inclusion, preserving the default 29 records and diagnostic schema.
- `backend/tests/test_generation_continuity.py`: existing request assertions now reflect the explicitly changed instructions.
- `README.md`: discoverability for the opt-in contrasts and audit report.
- `docs/MILESTONE_9_5_LLM_ACCEPTANCE.md`: Stage B update/link; Stage A results unchanged.

Added:

- `backend/tests/test_stage_b_continuity.py`: 29 focused cases.
- `docs/MILESTONE_9_5_STAGE_B_CONTINUITY.md`: this report, including the investigation documented before implementation.

No dependencies, persistence schema, proposal schema, consequence values, endgame instructions, frontend source, provider model/configuration, timers, votes or private-information boundaries changed. No commits, tags or pushes.

## Revalidation and remaining risks

Stage B's implementation and offline/audit criteria are complete. **Real-provider continuity and latency improvement are unverified.** The model may still choose standalone events or attach shallow/contradictory prose to a valid citation. Do not treat the engineered positive examples or passing regressions as improved model quality. Formal human gameplay/role-private/browser ratings remain pending.

Proposed next step, **not executed or authorized**: four calls matching Stage A's fresh/infrastructure/trust/interconnected crisis fixtures, unchanged `gpt-6-luna`, 60-second timeout, strict schema and no retries. At the prior operator planning assumptions of 5,000 input / 2,000 output per crisis and $0.10/$0.50 per million, the conditional estimate is $0.0060. Those prices/assumptions and a proposed $1 administrative ceiling require renewed approval before execution; estimates are not guaranteed caps. Endgame calls are unnecessary for this prompt-only change unless the user separately requests additional controls.

Compare actual reference utilization and human meaningful/superficial/contradictory classifications against Stage A, record per-stage latency and reported usage, and preserve all failures. Keep the same contexts and model to isolate the instruction change; a four-call result remains exploratory. Use the human rubric to test whether past choices materially constrain new choices, rather than selecting a winner by reference count. Do not optimize latency, change advice visibility or substitute a model without additional evidence and separate scope.
