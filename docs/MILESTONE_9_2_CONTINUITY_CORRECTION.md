# Milestone 9.2 — Continuity correction

Implemented locally on 2026-10-28. No commit, tag, or push. The prior investigation's uncommitted diagnostics and smoke utility were preserved. This task changes only continuity guidance/schema descriptions in two existing generation files and adds a focused test file and this report.

## Cause found

The context serializer was correct: the initial authoritative request contains `history: []`, crisis number 1 and initial metrics. No fabricated previous decision was supplied by the server.

The previous request did not communicate that boundary strongly enough:

- The system prompt said to cite only provided decisions, without an explicit opening-crisis/no-history branch or instructions to emit an empty continuity array.
- The generic reference schema allowed crisis numbers 1–10 and choices A/B/C, with up to three entries, regardless of the supplied history. It therefore allowed output that was structurally valid but impossible for the current mission.
- Strict structured output required the `continuity_references` key, while its optional narrative meaning was not explained in the schema. The array already allowed zero elements: the schema did **not** require invented references. The defect was missing request-specific exclusion and clear guidance, not a required nonempty array.

The previous real attempt's `invalid_continuity` result with empty history establishes that it supplied nonempty, unauthorized structured references. The model's internal reason for doing so cannot be established from that category; the concrete request ambiguity and overly broad schema above are directly observable. No speculative model rationale is presented as fact.

## Correction

`provider.continuity_instructions(context)` now explicitly states:

- With empty history: no previous player decisions exist; Crisis 1 is the opening crisis; return `continuity_references: []` exactly; do not invent earlier votes, player actions, crises or decision references in narrative fields.
- Fictional civic background remains allowed, provided it is not attributed to prior player decisions.
- With completed history: optional links may use only supplied executed choices, crisis numbers/identifiers and selected consequences. Unchosen alternatives and missing/older history are not evidence.
- `used_scenario_ids` is an exclusion list rather than proof of earlier choices. Current metrics or crisis numbering do not establish prior player actions.
- A standalone crisis and an empty reference array remain allowed even when history exists.

`proposal_schema(context=None)` still emits the generic contract for tools such as the existing schema CLI. When a request context is supplied:

- Empty history sets `continuity_references.maxItems=0`, with an explicit no-history description.
- Nonempty history creates `items.anyOf` branches for exact supplied `(crisis_number, choice_id)` pairs. Each branch binds the number and choice together, preventing invalid cross-pair combinations.
- The maximum count is the number of distinct supplied decisions (at most three); no minimum greater than zero is introduced.
- The same request-specific schema is sent in strict `json_schema` and embedded in the prompt for both supported response formats.

The [official OpenAI structured-output guide](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat) documents required object properties, nested `anyOf`, enums and array bounds. The transport key remains required for strict output; `[]` means no continuity dependency. Backend acceptance continues to allow omission with its existing empty-list default. No version, field shape or engine model was changed.

## Validation and privacy unchanged

`accept_proposal` still independently rejects unknown, wrong-choice and duplicate references. A provider ignoring the request-specific schema still fails closed and triggers authored fallback. It does not silently delete, repair or accept fabricated references.

All existing strategic, metric, length, private-intelligence and authoritative-field checks remain unchanged. So do identity generation, immutable accepted content, persistence, fallback selection, voting and timer rules. No new state is sent to the provider: the extra instructions use only the same authoritative history already in the bounded context. Prompts, keys and private content are not logged.

This is not a semantic proof of every sentence a model writes. Structured-reference validation is strict; invented implications in free narrative remain a model-quality concern addressed by explicit instructions rather than an added heuristic narrative filter.

## Regression tests

Added 17 cases in `backend/tests/test_generation_continuity.py`:

- Actual HTTP adapter request: empty/nonempty history × strict-schema/JSON-object formats; exact serialized context preserved, prompt and schema agree.
- Empty history permits only an empty continuity array in the request schema.
- Supplied history yields only exact executed number/choice pairs, with no cross-product of unrelated choices.
- Standalone output with empty or omitted references remains accepted with or without history.
- Valid historical references remain accepted.
- Unknown, wrong-choice and duplicate references remain rejected.
- A provider ignoring the empty-history constraint triggers the existing authored fallback.
- Used scenario IDs without executed history never create a narrative dependency.

Commands and results:

| Command | Result |
| --- | --- |
| `timeout 90 .venv/bin/python -m pytest backend/tests/test_generation_continuity.py backend/tests/test_generation_contract.py backend/tests/test_generation_provider.py backend/tests/test_generation_diagnostics.py backend/tests/test_live_generation.py -q -x -o faulthandler_timeout=30` | **230 passed**, one existing Starlette TestClient warning, 2.43 s |
| `timeout 120 .venv/bin/python -m pytest backend/tests -q -o faulthandler_timeout=40` | **499 passed**, same existing warning, 13.26 s |
| `.venv/bin/python -m pip check` | No broken requirements found |
| `git diff --check` | Passed |

No dependency or frontend changes were made. The focused and full suites use fake/local fixture providers only. Local result logs: `/tmp/ce-continuity-tests.log`, `/tmp/ce-continuity-backend.log`.

## Exactly one real-model verification

One real `gpt-4o-mini` request was made with the corrected opening instructions and schema, empty authoritative history, initial metrics 70 and synthetic standalone context. The model/deadline were overridden for this test only (`gpt-4o-mini`, 60 seconds), leaving `backend/.env` and current missions untouched. The existing service and strict authored fallback were used. There were no retries or additional paid model requests for this task.

Observed result:

```text
HTTP status: 200
Duration: 7.950 seconds
Generation source: authored (fallback)
Failure: invalid_schema
Accepted generated crisis: false
```

**A real generated crisis was not successfully accepted in this verification.** The rejection is now reported as the general schema category rather than `invalid_continuity`. That category does not identify the precise violated content/strategic rule. It also does not establish continuity compliance for an otherwise valid real scenario. No raw provider payload was retained or logged to diagnose that separate rejection, and no validation was weakened to obtain a success.

The sanitized log `/tmp/ce-continuity-real.log` includes `continuity_reference_count=0` for the **returned fallback snapshot**, not an independently inspected raw model array. It must not be cited as proof of real-model continuity compliance. The deterministic regression cases establish the corrected prompt/schema boundary and unchanged backend rejection behavior; a successful real accepted opening crisis remains unverified.

## Exact scope

Modified for this task:

- `backend/app/generation/contract.py` — clarify optional reference meaning and derive request-specific reference constraints.
- `backend/app/generation/provider.py` — explicit context-sensitive continuity instructions and use the request-specific schema.

Added:

- `backend/tests/test_generation_continuity.py` — 17 continuity regressions.
- `docs/MILESTONE_9_2_CONTINUITY_CORRECTION.md` — this report.

Prior local investigation changes remain in place. Accepted mission content, API keys, provider configuration, database records and game mechanics were not edited by this correction. Real generation reliability remains subject to the other unchanged schema/strategic rules, and the one permitted real test did not meet full acceptance.

## Subsequent user-requested retest — gpt-6-luna

After the user changed the configured model to `gpt-6-luna` and explicitly requested another test, exactly one additional real opening-crisis request succeeded:

- HTTP 200 in **19.780 seconds**.
- Service source `generated`, no failure category.
- Full existing proposal, strategic and continuity validation passed, with a canonical server-generated identity.
- Context was crisis 1, metrics 70, empty completed history and no used IDs. Acceptance therefore required an empty continuity-reference list.

This confirms that a real opening crisis can be validated and accepted by the generation service with the corrected request and this configured model. It does not establish a real two-crisis playthrough or universal narrative quality. No retry loop, active mission mutation or provider-configuration edit was performed. Sanitized evidence: `/tmp/ce-luna-provider-retest.log`.

The smoke used a **60-second timeout override**, while `backend/.env` still configured **15 seconds**. The observed successful response took longer than that production deadline. Increase `CONSENSUS_LLM_TIMEOUT_SECONDS` (for example to 60, within the existing supported bound) and restart the backend before expecting similarly timed live requests to complete. The successful smoke did not silently change that setting.
