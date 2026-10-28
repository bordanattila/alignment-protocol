# Milestone 9.2 — Live LLM generation investigation

Investigated on 2026-10-28 from clean commit `98ba2da` (Milestone 9.2). Changes remain local; no commit, tag, or push. No user mission content, accepted snapshots, model configuration, credentials, or API billing settings were edited.

## Findings and root cause

The current mission is correctly persisted as **`generated`**. Its first three accepted scenarios are all recorded as **`authored_fallback`**:

| Crisis | Saved scenario ID | Saved source |
| --- | --- | --- |
| 1 | `grid-under-pressure` | `authored_fallback` |
| 2 | `transit-at-dawn` | `authored_fallback` |
| 3 | `evacuation-routes` | `authored_fallback` |

The active record was inspected read-only in `backend/data/consensus-engine.sqlite3`. Only mode, phase, crisis number, result count, public scenario IDs and sources were printed. No invite token, player identity, credential, chat, vote, private intelligence, or complete aggregate was printed. The mission was at Crisis 3 briefing with two executed results. Existing saved mode and content were not changed by the investigation.

The frontend creation helper serializes the selected mode; the backend request validates and persists it. No update route changes mode, and recovery retains it. Inspection of the running reload supervisor and worker confirmed generation enabled with the same model/format as the env file. `/api/capabilities` returned HTTP 200 / `generated_missions=true`. This is not an authored-mode submission or a reconnect resetting mode.

Two **external provider blockers** were verified, alongside insufficient diagnostic specificity:

1. The running backend and `backend/.env` select **`gpt-3.5-turbo`**, endpoint `https://api.openai.com/v1/chat/completions`, response format **`json_schema`**, and a 15-second deadline. A single synthetic request through the actual HTTP adapter received **HTTP 404**, error code **`model_not_found`**, type **`invalid_request_error`**, after approximately **0.986 seconds**. It used authored fallback. The observed error is model unavailable/inaccessible for that request, not an authentication or timeout error. The model-list endpoint did list this model, so listing alone is not proof that a completion can be requested successfully.
2. A controlled synthetic generated-mission smoke explicitly selected **`gpt-4o-mini`** for that run only. Its first generation request received **HTTP 429**, classified from the bounded error body as **`quota_exceeded`**, after **0.839 seconds** (0.851 seconds through live admission). It admitted authored fallback and stopped immediately. No second crisis request was sent and no paid retry loop was run.

The read-only model availability request returned HTTP 200 with the same credential; both configured model and smoke candidate were listed. This does not establish usable generation quota. There were exactly **two generation POST requests** in the investigation: one reproducing the configured failure and one supported-model smoke that stopped on quota rejection. No successful model completion was obtained. Provider billing/charge accounting was not inspected and no claim about charges is made.

There is also a documented format mismatch independent of the observed 404: OpenAI's [structured output guide](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat) lists strict `json_schema` support starting with GPT-4o Mini / compatible newer models; [GPT-3.5 Turbo](https://developers.openai.com/api/docs/models/gpt-3.5-turbo) does not support strict structured outputs. The actual configured request was rejected for `model_not_found`, so an unsupported-format HTTP response was **not** observed in that reproduction. Do not conflate the two findings.

OpenAI's [error-code guidance](https://developers.openai.com/api/docs/guides/error-codes) distinguishes quota/billing rejection from temporary rate limiting and says quota-related failures require credits/limits/account action before retrying. Changing model alone does not resolve the verified quota rejection.

## Evidence limits for the original requests

The old admission record stores source and accepted content, but not provider failure category or request timing. The available chat terminal contained no matching historical generation-category records. Consequently, the precise historical HTTP result for each of the already accepted Crisis 1/2/3 attempts cannot be reconstructed from persisted state.

Their fallback sources and generated mode are proven. The live code invocation path and current configured failure are proven. It would be inaccurate to assert that each historical crisis definitely received the same HTTP 404: interrupted preparation can also recover directly through authored fallback, and old records do not distinguish that cause. New diagnostics close this gap for future attempts without changing old snapshots or result hashes.

## Lifecycle trace

1. Creation: frontend `MissionEntryRequest.submit` sends `{callsign, mode}` for creation; joining does not send a mode override. `CreateMissionRequest` accepts only authored/generated, defaulting to authored. The store persists the selected mode.
2. Crisis 1: host start assigns the existing roles, snapshots the authored fallback catalog/seed and initial metrics, creates a persisted target-slot-0 attempt, and enters `preparing`. `main.start` calls `LiveGeneration.launch_pending` under the existing lock.
3. Capture: the coordinator copies `GenerationRequest` and `authored_selector` under the lock. Initial context is crisis 1 / metrics 70 / empty completed history. Inference runs outside the lock.
4. Request: the adapter sends the configured model, system instructions/schema, allowlisted context, `stream=false`, and strict `response_format.json_schema`. The key appears only in the Authorization header. No user token, identity, private chat/intelligence or uncommitted vote goes into the context.
5. Provider errors: non-200 responses are mapped to fixed categories. The observed 404 and 429 failures occur **before generated JSON parsing or crisis validation**; there is no generated crisis payload to repair in these cases.
6. Valid completion: successful envelopes pass strict JSON parsing, canonical proposal validation, metric/text/continuity/privacy constraints and server identity assignment. The integration does not weaken or bypass this contract.
7. Fallback/admission: failure invokes the existing deep-captured Milestone 8 authored selector. Source is stored as `authored_fallback`; accepted content and its hash are durably stored before briefing/publication. Accepted snapshots never regenerate because configuration changes later.
8. Crisis 2: the original voting/consequence path commits the executed result and metrics. Host acknowledgement creates target-slot-1 preparation. The new request uses updated authoritative metrics, the executed choice/consequence, and used IDs. Reconnect and duplicate acknowledgements do not add generation calls. Restarting a pending preparation intentionally admits saved authored fallback without a model replay.

The exact two-crisis controlled harness is exercised with a fake provider in the normal suite, including accepted generated identities, updated metrics/history/choice context, and restoration of the accepted second snapshot from temporary SQLite. Real Crisis 2 remains unverified because the real-provider smoke stopped at the quota-rejected first request.

## Changes made

No gameplay, frontend, contract acceptance rule, prompt, metric limit, timer, vote rule, result model, SQL schema or immutable content was changed. The verified implementation defect was diagnostic loss: HTTP 404/model errors became generic `unsupported_response`, and all HTTP 429 responses became temporary `rate_limited` regardless of quota/body.

The adapter now reads at most **16 KiB** of an error body within its existing total deadline. It inspects fixed known code/type/parameter values and unsupported-format wording in memory, then discards the body. It does not store or log raw messages or payloads. New sanitized categories:

| Category | Distinction |
| --- | --- |
| `model_unavailable` | Known model-not-found / unsupported-model rejection |
| `quota_exceeded` | Known credit, billing, organization/project usage or spend rejection |
| `unsupported_format` | Known response-format parameter rejected as unsupported |
| `invalid_provider_schema` | Provider rejects the submitted JSON schema |

Existing `authentication`, `rate_limited`, `timeout`, `unavailable`, `unsupported_response`, `invalid_json`, `invalid_schema`, `invalid_continuity`, `refusal` and other foundation categories remain. Unrecognized, malformed or oversized provider errors reduce to the existing status-based category. HTTP status metadata is range/type-checked; untrusted metadata cannot inject arbitrary text into logs. HTTP 200 with invalid generated content remains `invalid_schema`, with status 200 preserved.

`GenerationOutcome` adds duration and sanitized HTTP status metadata; neither is exposed in mission projections or appended to immutable admission/result records. The service emits:

```text
generation_result mode=generated crisis=1 source=authored_fallback success=False failure=quota_exceeded http_status=429 duration_seconds=0.839
```

Generation success uses INFO, failure WARNING. The live coordinator emits a separate `crisis_admitted` INFO record through Uvicorn's existing server logger **after successful commit**, so success is visible with the normal Uvicorn command. A storage retry does not log a false admission or repeat generation. Both events carry mode, crisis number, source, generation success/failure, fixed failure category, HTTP status and duration. No mission identifier, attempt ID, model/prompt, secret, player data or provider message is logged.

Startup fallback admission has `failure=restart_recovery`, `http_status=None`, duration 0.000, distinguishing intentional recovery without inference from a provider failure. Context/identity/vote privacy and immutable snapshots remain unchanged.

## Required operator action

Update the **model setting** to one supported by your API project and strict structured outputs. The smoke candidate `gpt-4o-mini` is listed for this credential and documented as supporting strict output, but no successful completion with this exact contract has yet been obtained because quota was rejected. Keep strict format enabled:

```dotenv
CONSENSUS_LLM_ENABLED=true
CONSENSUS_LLM_ENDPOINT=https://api.openai.com/v1/chat/completions
CONSENSUS_LLM_MODEL=gpt-4o-mini
CONSENSUS_LLM_RESPONSE_FORMAT=json_schema
CONSENSUS_LLM_REQUIRE_API_KEY=true
```

Keep the existing key private. Check API credit balance/billing and applicable project/organization usage/spend limits for the project owning that key; restore API quota/access before another real test. The precise account-side restriction cannot be established from the allowed response category alone; dashboard/billing settings were not read or changed. This is not resolved by restarting repeatedly. No change to the existing 15-second production timeout was justified by these sub-second rejection responses.

`backend/.env` was intentionally left unchanged. After updating it and fixing API quota, restart from your usual backend working directory to preserve the same relative database location:

```sh
# From the repository root; the inspected user database is backend/data/...
CONSENSUS_DB_PATH=/home/attila_unix/projects/consensus-engine/backend/data/consensus-engine.sqlite3 \
  .venv/bin/python -m uvicorn app.main:app --env-file backend/.env \
  --reload --host 127.0.0.1 --port 8000
```

The explicit database path retains the existing inspected user database when starting from the repository root. Do not start a second owner while the current backend is running. Accepted fallback crises remain unchanged; a future acknowledged crisis or new generated mission will attempt inference with the restarted settings.

## Controlled smoke utility

Added `backend/tests/smoke_provider_progression.py`. It requires explicit `--live`, makes **at most two** generation requests with no automatic retries, uses only synthetic identities/context and an isolated temporary SQLite database, and stops after the first fallback. It prints only safe source/timing/context-agreement/identity booleans and counts. It never uses an active mission. Temporary content is deleted afterward.

After fixing API quota, this command can verify the production coordinator, strict validation, generated Crisis 1, authoritative result/metric handoff, generated Crisis 2 with updated context, and snapshot restart recovery:

```sh
.venv/bin/python backend/tests/smoke_provider_progression.py \
  --live --env-file backend/.env --model gpt-4o-mini --timeout-seconds 60
```

Model/deadline overrides apply only to this smoke, not the env file or existing missions. The 60-second test cap is not a measured generation-latency recommendation. The real invocation in this investigation returned fallback/exit 1 at Crisis 1 due to quota and **did not invoke Crisis 2**. Normal automated tests inject a fake provider into this same harness and perform no external calls.

## Verification results

| Command / check | Result |
| --- | --- |
| Safe read-only SQLite mode/source inspection | Generated mode retained; first three admissions authored fallback |
| Running worker/supervisor configuration inspection | Enabled, configured `gpt-3.5-turbo`, strict schema, key present; no key value printed |
| `GET /api/capabilities` | HTTP 200, generated missions available |
| One configured-model synthetic POST | HTTP 404 / `model_not_found`; fallback in 0.986 s |
| Read-only `GET /v1/models` | HTTP 200; configured model and smoke candidate listed; no full model list printed |
| Opt-in two-crisis real-provider command above | First request HTTP 429 / `quota_exceeded`; fallback in 0.839 s; stopped at one request / exit 1; no real Crisis 2 |
| `timeout 90 .venv/bin/python -m pytest backend/tests/test_generation_diagnostics.py backend/tests/test_generation_provider.py backend/tests/test_live_generation.py -q -x -o faulthandler_timeout=30` | **114 passed**, one existing warning, 2.33 s |
| `timeout 120 .venv/bin/python -m pytest backend/tests -q -o faulthandler_timeout=40` | **482 passed**, one existing warning, 13.03 s |
| `npm --prefix frontend test` | 98 passed, 4 capture-dependent skipped, 0 failed |
| `MISSION_RESTART_FILE=/tmp/ce-m7-restart.json MISSION_REVIEW_FILE=/tmp/ce-m6-live.json CHAT_ACCEPTANCE_FILE=/tmp/ce-chat-5-1.json EXPANSION_REVIEW_FILE=/tmp/ce-m8-live.json npm --prefix frontend test` | 102 passed, 0 skipped/failed |
| `npm --prefix frontend run build` | Type-check and Vite passed; 43 modules; JS 264.96 kB / CSS 12.61 kB |
| `.venv/bin/python -m pip check` | No broken requirements found |
| `timeout 90 .venv/bin/python backend/tests/smoke_live_generation.py` | Passed fake-provider ten-crisis real-network mission: two fallbacks, voting reconnect, pending process-kill recovery, one inference attempt per slot |
| `git diff --check` | Passed |

The 27 added deterministic tests cover model/quota/format/provider-schema classification; malformed/oversized/untrusted errors; complete safe metadata and accurate HTTP status; no secret/private prose in logs; commit-before-admission logging and no duplicate diagnostics on storage retry; and the exact two-crisis smoke harness using a fake provider. Existing tests continue to verify unchanged strict acceptance, context filtering, plurality/tie/no-vote behavior, timer and metric rules, all role distributions, ten-crisis progression, reconnect/restart and legacy result hashes.

One initial new test assumed the helper fixture's crisis number was 1; that fixture represents crisis 2. The assertion was corrected before the successful runs above. The remaining test warning is the existing Starlette TestClient HTTPX deprecation. No full-suite hang occurred in this run.

Evidence files under `/tmp`: `ce-live-investigation-real.log` (sanitized failure only), `ce-live-investigation-diagnostics.log`, `ce-live-investigation-backend.log`, `ce-live-investigation-ui.log`, `ce-live-investigation-ui-acceptance.log`, `ce-live-investigation-build.log`, and `ce-live-investigation-smoke.log`. No complete provider payload, API key, private player content or raw aggregate was saved to these logs/report.

## Changed files

Modified:

- `backend/app/generation/contract.py` — fixed failure categories and safe HTTP status on generation errors.
- `backend/app/generation/provider.py` — bounded error interpretation and response status metadata.
- `backend/app/generation/service.py` — sanitized duration/status/source diagnostics.
- `backend/app/generation/live.py` — committed admission diagnostics, visible with default Uvicorn logging.
- `backend/app/missions.py` — explicit startup recovery-fallback diagnostic.
- `README.md` — link to this investigation/troubleshooting procedure.

Added:

- `backend/tests/test_generation_diagnostics.py` — 27 focused diagnostics/harness regressions.
- `backend/tests/smoke_provider_progression.py` — explicitly opt-in, bounded real-provider progression smoke.
- `docs/MILESTONE_9_2_LIVE_GENERATION_INVESTIGATION.md` — this report.

## Remaining limitations

Successful real-generated Crisis 1 and context-aware real-generated Crisis 2 remain **unverified**, blocked by external API quota. Fake-provider two-crisis and ten-crisis integration verifies the live mechanics but does not prove actual provider/schema/content quality. Historical individual fallback error codes cannot be recovered because the old code did not persist/log sufficient metadata. New diagnostics do not retroactively change that evidence or rewrite accepted content. Account/model/quota configuration needs operator action; no validation or fallback guarantee was weakened to hide the failure.
