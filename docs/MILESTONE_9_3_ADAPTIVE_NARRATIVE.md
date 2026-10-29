# Milestone 9.3 — Adaptive narrative continuity and endgame storytelling

Implemented locally on 2026-10-28 against `9c84052` (`fix: harden Milestone 9.2 live generation and diagnostics`). The required 9.2 prerequisite was committed and the working tree was clean before this work. No commits, tags, pushes or paid inference requests were made.

## Reconnaissance

Read `AGENTS.md`, the product specification and the actual 9.1/9.2 implementation before editing. A concise reconnaissance summary was provided in the chat before implementation.

- FastAPI owns mission mutations through `MissionStore`, under the existing state lock. The `persisted` intent wrapper commits the complete aggregate before success/publication and rolls it back on failure.
- The live scenario coordinator captures a request under the lock, infers outside it and admits a frozen snapshot under an attempt-ID guard. Accepted snapshots, admission hashes and five-field diagnostics persist inside the mission aggregate.
- Completed votes produce immutable `CrisisResult` records with public situation, executed choice, selected consequence, before/after metrics and actual clamped deltas. SQLite additionally protects finalized result hashes. Provider context intentionally omits vote maps, identities, credentials, chat, connection state and role-private intelligence.
- Before this milestone, crisis requests supplied only the last three public decisions and current metrics. Explicit continuity references were checked against executed choice/number pairs, and standalone crises remained valid.
- The 30-crisis library has five prerequisite relationships: concentrated grid outage → substation reckoning; delivered water → bottled-water waste; temporary wards → care workforce; priority corridor → freight debt; service isolation → identity recovery. These relationships and all source scenario files remain unchanged.
- Terminal summaries are reconstructed from saved public results, including a deterministic ending, notable decisions, score, four metric series, team vote summary and chronological decision review. No generated epilogue existed.
- The review already provides a narrative panel, stable component identity, native expandable history and responsive charts. This milestone reuses that panel rather than redesigning gameplay.
- SQLite schema version 2 stores format-1 JSON mission aggregates with additive compatibility defaults. No new table or SQL migration is necessary.

The later explicit user scope authorizes live narrative generation beyond the original authored-only v0.1 guideline. The LLM remains a content proposer/interpreter; authority over gameplay is unchanged.

## Derived narrative memory

The existing `GenerationContext` now includes an optional `narrative_memory`, built on demand. There is no persisted memory summary, separate history store or summarization request.

| Input | Authoritative source and bound |
| --- | --- |
| Recent decisions | Existing last-three window, with actual applied deltas added |
| Significant earlier decisions | Up to two outside that window, ranked by total absolute applied movement, ties by crisis order |
| Established events | Last three executed crises' saved public briefings, at most 300 characters each |
| Open pressures | Up to four current metric deficits relative to the actual initial snapshot, with current value, net change and up to three contributing recorded crisis numbers |
| Recurring costs | Metrics reduced by at least two executed decisions; conservative recurring tradeoff themes, not invented social events |
| Strengths / weaknesses | Every metric tied for the current maximum / minimum |
| Used titles | At most ten saved titles, to discourage repeating an accepted crisis |

Each decision includes its stable public scenario ID, crisis number, executed choice ID/title, selected consequence (at most 600 characters) and actual clamped metric deltas. Voting-round/result IDs are deliberately excluded from provider input. Scenario IDs plus mission-local crisis numbers distinguish events without exposing transport identity.

Open pressures describe recorded numeric deficits. They do not assert an unrecorded strike, shortage, unrest or future disaster. Recurring costs describe repeated measured tradeoffs, avoiding speculative theme inference. Established situations and executed outcomes remain separate fields.

Repeated crisis inputs contain at most five full decisions, three situation excerpts and four metric pressure records per category. Test fixtures assert a crisis request context remains below 16 KB. Endgame input includes all completed decisions (at most ten) and remains below 24 KB in the fixture. Text/model field bounds enforce finite input sizes; those byte thresholds are fixture checks, not a universal token estimate.

## Adaptive generation and quality safeguards

The existing version-1 crisis proposal and numeric bounds (`-24..18`) remain intact. Prompts distinguish established events, recorded costs and independent new challenges; they instruct the model to use relevant earlier events without forcing every crisis to be a sequel. They explicitly prohibit invented past choices, unsupported vote/metric claims, unresolved-to-resolved leaps and recommendation sentences in the public briefing.

Explicit continuity references now match exact executed pairs from the recent window **or** the two retained significant earlier decisions. Request-specific JSON Schema offers those same pairs; at most three may be cited. An empty opening history still requires `[]`, and independent later crises may also use `[]`. A metric-pressure contributor number alone does not authorize a missing historical choice.

Two objective checks were added to new scenario admission: an exact normalized title cannot repeat an executed crisis title, and the three choices cannot have identical numeric effect vectors. Existing distinct text, gains/costs, dominated-option, structural, integer-bound and continuity checks remain. No fuzzy similarity threshold, semantic keyword blacklist, balance change or automatic repair/retry loop was introduced. Old accepted content is not revalidated against these new proposal checks or rewritten.

Prompt instructions improve quality but cannot prove semantic truth in arbitrary prose. Exact references remain strictly validated; unsupported explicit references still cause deterministic authored fallback. No claim of real-model quality improvement is made from fake-provider tests.

## Endgame contract and factual boundary

`endgame-1.0` is separate from the crisis proposal contract. Required sections are `journey`, `cost` and `standing`. Each contains 40–900 characters of text and one to three distinct references to actual completed crisis numbers. Extra fields, wrong versions, missing sections, unsupported references, invalid lengths, duplicate JSON keys, nonfinite JSON and oversized input are rejected. Control characters are rejected. The configured API key appearing in accepted output is rejected before persistence.

Provider input supplies finalized victory/defeat, resolved crisis count, actual initial/final metrics, unchanged Consensus Score, all completed public decisions, their recorded consequences/applied deltas and derived memory. It excludes private reports, chat, identities, connection metadata and vote identities/tallies.

The schema cannot output authoritative statistics, scores, vote counts or mission outcome fields. The provider returns only interpretation and reference numbers. The backend resolves references to saved scenario IDs, crisis/choice titles and recorded consequences for the displayed source details. Outcome, score, charts, metric values and decision history always come from server-owned records.

The existing chat-completions adapter is reused, including endpoint/model/credentials, output size limits, timeouts, refusal handling and sanitized HTTP error classification. It chooses `endgame_narrative_v1` for endgame requests and the existing crisis schema for scenario requests. Both `json_schema` and configured `json_object` paths are tested with mock transports. Object properties are required and extra properties forbidden, following [OpenAI structured-output requirements](https://developers.openai.com/api/docs/guides/structured-outputs). No SDK, orchestration framework or new infrastructure was introduced.

## Lifecycle and durable snapshots

On a new generated mission's authoritative victory or collapse, the same committed intent creates one pending `ConclusionState`. Authored missions do not create it. Mission completion and final voting never await inference.

`LiveConclusions` uses the existing scheduler, state lock, connection broadcaster, settings and provider interface. It captures terminal public input under the lock, makes one bounded asynchronous request outside the lock and commits admission/fallback under the lock. Duplicate completion/launch events share the same pending attempt. A transient database admission failure retains the completed outcome in memory, so retrying storage does not repeat inference.

Admission requires the current mission to remain terminal, the pending attempt ID to match, and a hash of the complete authoritative outcome/results/initial/final metrics to equal the captured basis. Stale requests cannot replace a newer/finalized conclusion. This hash is new story admission metadata; existing crisis/result hash algorithms are unchanged.

An accepted narrative is a frozen typed snapshot with immutable reference tuples inside the mission aggregate. The aggregate checksum protects its stored representation, and the save guard forbids changing or removing a finalized conclusion, including its diagnostic. Source details are derived from immutable results. There is no accepted-story regeneration on refresh/reconnect.

Provider failure, timeout, invalid structure/reference or disabled generation finalizes deterministic fallback. The existing ending is available throughout pending generation. Clean shutdown records cancellation/fallback when storage permits. Restart while still pending records `restart_recovery` and fallback without another inference. Already accepted stories restore unchanged.

The only durable extension is optional `conclusion`, defaulting to null for legacy aggregates. Old authored and generated missions retain their saved content, accepted admissions, diagnostics, roles, results and hashes. Previously completed missions without a conclusion are not retroactively sent to a provider. A mission still in play when upgraded may receive a conclusion on its later terminal transition. Do not downgrade a database containing this new field to an application that predates it.

## Frontend

The existing post-game narrative panel displays the deterministic ending while pending and after fallback. Pending state has an accessible status message, without disabling charts/history or claiming the mission is unfinished. On acceptance, the same panel shows three concise sections and an explicit **AI-generated interpretation** label. Native expandable “Recorded basis” details contain authoritative source excerpts.

Statistics retain their existing separate panel, four charts, Consensus Score and history components. Terminal victory/defeat headings and values never come from generated prose. React escapes all story text. The review component is not remounted or keyed by story state; its focus/scroll effect remains mount-only, so arrival does not intentionally refocus or scroll. Narrative text wraps on narrow displays, uses readable line height/width, and source toggles have a 44-pixel minimum target.

## Operator-only diagnostics

Existing five-field crisis records and the default inspection output are unchanged. Endgame diagnostics separately record `operation: endgame`, source (`generated` / `deterministic_fallback`), bounded category, duration and known provider HTTP status. Lifecycle categories include cancellation, restart recovery and internal-state failure. Restart recovery has zero duration because no new inference occurred. Logs contain only fixed categories/metadata; no raw prompt, response, credential or private context is persisted or logged by this feature.

```sh
.venv/bin/python -m app.generation.inspect_diagnostics \
  --database backend/data/consensus-engine.sqlite3 --mission-index 1 --operation crisis
.venv/bin/python -m app.generation.inspect_diagnostics \
  --database backend/data/consensus-engine.sqlite3 --mission-index 1 --operation endgame
```

Use the actual database path. Index 1 is latest-created, 2 the preceding mission. The tool opens SQLite read-only and exposes no HTTP route. Public snapshots include only story status and accepted text/server-resolved sources, never diagnostics, attempt IDs or basis hashes.

## Verification

All inference fixtures are offline. Mock HTTP transports and deterministic fake providers were used; no paid requests, real-model evaluation or real-provider success are claimed.

| Command | Result |
| --- | --- |
| `timeout 120 .venv/bin/python -m pytest backend/tests -q -x -o faulthandler_timeout=40` | 542 passed in 18.48 s; one pre-existing Starlette/httpx TestClient deprecation warning |
| Capture-enabled `npm --prefix frontend test` (variables below) | 108 passed, zero skips/failures, 277.66 ms |
| `npm --prefix frontend run build` | Includes `tsc --noEmit`; TypeScript and Vite passed, 43 modules, 490 ms Vite build |
| `.venv/bin/python -m pip check` | No broken requirements |
| `npm --prefix frontend ls --depth=0` | Valid dependency tree |
| `git diff --check` | Passed |
| `git diff --name-only -- backend/app/content` | Empty; all 30 authored crises and five relationships unchanged |

Frontend capture-enabled invocation:

```sh
MISSION_RESTART_FILE=/tmp/ce-m7-restart.json \
MISSION_REVIEW_FILE=/tmp/ce-m6-live.json \
CHAT_ACCEPTANCE_FILE=/tmp/ce-chat-5-1.json \
EXPANSION_REVIEW_FILE=/tmp/ce-m8-live.json npm --prefix frontend test
```

Twenty-five new backend cases cover initial/progressive/bounded memory, recorded deltas and significant earlier decisions, valid/invalid references, exact repetition/effect guards, ten-crisis victory, early defeat, separate strict schema, both adapter formats, failure/timeout/disabled behavior, pending reconnect/recovery, cancellation, stale admission, duplicate launch/completion, persistence retry without reinference, immutable story modification/removal, legacy terminal aggregates, private projection and preserved result hashes. Six frontend cases cover pending/generated/fallback markup, authoritative victory/defeat, retained history/charts, serialized reconnect state, escaping and separation from statistics. Existing tests continue to cover mobile layout, voting, 2/3/4-player rules, presence, recovery and privacy.

An initial regression pass identified three assertions enumerating the old context fields; they were updated to include the new allowed memory field while retaining private-data canaries. The first saved-story reload test exposed Python-list versus strict immutable-tuple parsing; reference arrays now normalize only JSON/Python lists to immutable tuples while retaining strict bounded integer validation. All checks above include those fixes.

### Multiplayer network smoke

```sh
timeout 90 .venv/bin/python backend/tests/smoke_adaptive_narrative.py
timeout 90 .venv/bin/python backend/tests/smoke_milestone8.py
timeout 90 node --experimental-websocket frontend/tests/smokeReconnection.mjs
```

All passed. The new smoke performs three separate ten-crisis generated-mode games with three real WebSocket clients each, using production engine/persistence and fake inference. Every run includes validation fallback, interrupted-crisis fallback and real voting reconnect. Endgame cases prove:

1. A held request leaves completion, deterministic ending, final metrics and history immediately available; reconnect during that request preserves them.
2. Releasing a valid story updates all three clients to the same accepted story; restart retains it without another request.
3. Killing the server while held records restart fallback on recovery with no second request.
4. Provider HTTP/error failure records fallback, keeps the existing ending and agrees across clients.
5. Final metrics, outcome, score, timeline and ten results remain identical before/after each narrative transition; no private chat enters endgame input.

The authored smoke completes ten crises with two follow-ups and preserves privacy, restart content and exactly-once acknowledgements (this run's score 64.0). The controller/Vite smoke passes individual loss, backend restart and presence UX checks. These are network and server-rendered UI checks, not a human mobile browser acceptance session.

## Manual acceptance checklist

- [ ] Start the backend with the intended provider settings and stable database path; confirm the frontend can select generated mode. A live generated mission can incur up to one additional request for its conclusion.
- [ ] On three browsers/devices, compare Crisis 2/3's narrative against actual executed decisions. Independent events should still occur naturally. Use operator diagnostics to distinguish fallback.
- [ ] Complete a generated mission and confirm victory/score/charts/history appear before story completion. Also exercise early defeat and confirm its outcome remains unambiguous.
- [ ] Read all story sections against their recorded source details. Evaluate factual consistency, causal restraint, variety, strategic choices and whether significant earlier events are recognized. Record disagreements as narrative-quality findings; do not treat prose as authority.
- [ ] While a story is pending, refresh/reconnect another client. Once accepted, compare text on all clients and after backend restart; it must remain identical.
- [ ] With a local fake/unavailable provider, confirm deterministic fallback and its operator diagnostic. Restart a held fake request and confirm no repeated inference.
- [ ] On phone and laptop, verify paragraph width, source toggles, focus/reading position, chart accessibility and scroll behavior when the story arrives.
- [ ] Open an old completed authored/generated mission and confirm unchanged results, existing ending and no retroactive request.

## Known limitations

- Arbitrary prose cannot be proven semantically true by structural validation. References and authoritative fields are constrained; interpretation is labeled and sources/statistics are rendered deterministically. Real-model narrative quality and mobile reading-position behavior still require the manual evaluation above.
- Recurring themes intentionally use measured metric costs, not speculative semantic event extraction. Only two significant older decisions are retained in repeated crisis input; endgame input includes all completed decisions.
- Exact title and identical-effect checks prevent objective repetition, not paraphrased duplicates. Prompt guidance handles subjective similarity without a brittle rejection heuristic.
- Storage outages can prevent diagnostic/story commits until storage recovers. The deterministic ending is still available, and cached outcomes avoid repeated inference in the running process. A hard kill before commit leads to restart fallback rather than a provider retry.
- There is no player-facing story retry/regeneration control, no historical backfill and no new model configuration. This avoids silently repeating paid requests or changing accepted narratives.

## Exact file inventory

Added:

- `backend/app/narrative_models.py`
- `backend/app/generation/endgame.py`
- `backend/app/generation/conclusion_live.py`
- `backend/tests/test_adaptive_narrative.py`
- `backend/tests/smoke_adaptive_narrative.py`
- `docs/MILESTONE_9_3_ADAPTIVE_NARRATIVE.md`

Modified:

- `README.md`
- `backend/app/domain.py`
- `backend/app/generation/context.py`
- `backend/app/generation/contract.py`
- `backend/app/generation/provider.py`
- `backend/app/generation/inspect_diagnostics.py`
- `backend/app/main.py`
- `backend/app/missions.py`
- `backend/app/persistence.py`
- `backend/tests/smoke_live_generation.py`
- `backend/tests/test_generation_contract.py`
- `backend/tests/test_generation_provider.py`
- `backend/tests/test_live_generation.py`
- `frontend/src/types.ts`
- `frontend/src/MissionReview.tsx`
- `frontend/src/styles.css`
- `frontend/tests/missionReview.test.tsx`

Ready for local review with the automated acceptance checks passing. Real-provider quality and human browser/mobile acceptance remain explicitly unverified.
