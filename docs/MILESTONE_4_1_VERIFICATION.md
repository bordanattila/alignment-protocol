# Milestone 4.1 — multiplayer identity and mobile acceptance hardening

## Investigation and reproduced findings

Read AGENTS.md, README, Milestone 3/4 verification history, mission/domain/transport/session code, completion/chat rendering and CSS, plus existing backend and rendered tests. The starting tree already contained uncommitted Milestone 4 work; it is preserved. Root-cause findings were reported before implementation.

### Callsigns

The existing HTTP join route already serializes membership checks/allocation with the app state lock and rejects casefold-equal names. Before this patch, a direct HTTP reproduction returned:

| Attempt | Before patch |
| --- | --- |
| First `Eagel2` join | 200 |
| Second exact ASCII `Eagel2` | 409 |
| `Eagel2` followed by U+200B ZERO WIDTH SPACE | 200, creating a distinct but visually similar seat |
| Decomposed `E` + combining acute + `agle`, with composed `Éagle` already present | 200 |
| Direct store ` Eagle2 ` with `Eagle2` already present | Created a second seat |

Thus the exact ASCII duplicate is not reproducible through the current locked HTTP path. Confirmed gaps were missing Unicode normalization, accepted invisible formatting characters, and normalization enforced only by the HTTP schema rather than the store. Existing casefold comparison also did not account for interior whitespace that HTML renders alike. There was no machine-readable duplicate code. The original browser session's raw requests/server version are unavailable, so this report does not claim to establish which gap caused that particular screenshot.

### Completion score

The score was already correctly calculated by the backend and restored in snapshots. It was rendered by ConsequenceOutcome after the full outcome/impact table, while Operations Room used “shown above.” That is a presentation/discoverability issue, not a scoring defect. No scoring or completion rule changed.

### Mobile chat

History was already bounded: 320px generally and 220px in active gameplay, with overflow-y:auto. The composer and existing 48px Send button were already above history. The Milestone 3 phase-change focus/scroll effect already brings active voting ahead of historical chat and is keyed to phase/round, not message arrivals. There was no unbounded-history growth bug to fix. The small-screen history cap was still large relative to a phone viewport; sender text also benefited from the same anywhere-wrap behavior as message bodies.

## Backend identity policy

backend/app/callsigns.py is the shared normalization/comparison boundary used by the HTTP Callsign validator and direct MissionStore calls:

- Display input uses Unicode NFKC compatibility normalization and strips leading/trailing whitespace.
- Normalized length remains 1–24 Unicode code points. Display capitalization is preserved.
- New names with Unicode category C characters (including control/format characters such as zero-width spaces and bidi controls) are rejected. Visible international letters, accents and symbols remain supported.
- The comparison key applies NFKC/casefold normalization and collapses interior whitespace. Display names are not lowercased or automatically suffixed/renamed.
- Existing legacy seats are compared safely even if they predate the format-character restriction; comparison ignores their control/format characters without rewriting their stored display name. Valid credentials still restore the original seat.

Join validates/compares before creating a Player or credential and appending a seat. Duplicate normalization and capacity decisions remain inside the existing transport lock. Concurrent same-name or equivalent-name HTTP joins produce exactly one success. Duplicate errors take precedence over capacity errors for an existing name in a full lobby.

Duplicate response:

```json
{"detail":"That callsign is already taken in this mission. Choose another.","code":"callsign_taken"}
```

Status is 409. MissionError now has a stable code field; other existing mission errors retain their status/detail with a generic mission_error code unless a specific code is provided. Invalid HTTP callsign fields remain normal 422 validation errors. Direct-store invalid names use invalid_callsign.

Room membership and true identity continue to use random player IDs and seat credentials. Callsigns are labels, never authentication. New players cannot claim a reserved disconnected seat by typing its name. Same names in separate rooms are allowed. In the store, credential restoration precedes new-name validation and never allocates a player or changes the old callsign/roles. Existing browser refresh uses the unchanged saved credential/WebSocket authentication path. The existing reservation policy remains unchanged: this repository has no implemented five-minute removal/redistribution timer, and none was added.

Unicode confusable letters from different scripts are not transliterated or treated as identical. This is normalization/case/whitespace identity matching, not a full international homoglyph detection system.

## Frontend join behavior

MissionEntryRequest retains the existing HTTP flow, maps callsign_taken to the exact friendly message, and uses a synchronous pending gate. A second submit while awaiting the API sends no second request, even before React repaints the disabled button. The gate releases on success/error so a rejected name can be edited and retried.

MissionEntryForm is the existing callsign form extracted for focused rendering tests. It retains the entered controlled value, leaves it editable, displays the error immediately beside the field, and associates it with aria-describedby/aria-invalid plus role=alert. Busy state is exposed with aria-busy and the existing disabled Connecting button. App catches the error, preserves the callsign and page, and only saves a session/navigates after a successful response. No silent rename or unrelated redirect occurs on rejection.

Frontend tests separately verify the API rejection → editable form rendering → successful alternative request path and the pending-request gate. They are not mounted browser form/click tests.

## Completion presentation

FinalConsensusScore now renders exactly once immediately beneath MISSION COMPLETE, before the executed choice, narrative, and impact table. Its label is “Final Consensus Score” with a prominent responsive numeric value and `/ 100`. It reads mission.consensus_score directly and retains the existing maximum-two-decimal formatting. No React average or new backend score calculation exists.

Operations Room wording is now “The mission is complete. Review your final score and civilization outcome.” It no longer makes a positional claim. The full result and final metric values remain available. Rendered restoration checks and live three-client reconnect verify the score remains in the authoritative completed state.

## Mobile changes and preserved phase behavior

- Active history at widths <=700px is capped at min(180px, 25dvh), with a 180px fallback. The existing single overflow-y:auto history region remains; no extra scrolling wrapper, scroll trap, fixed composer or nested panel scroller is introduced.
- The composer/Send button stay above history. Their order and 48px touch target were already correct and are preserved.
- Anywhere wrapping now covers history list items/sender labels as well as the existing long message bodies.
- Existing phase-first ordering and phase/round-only focus/scroll logic are unchanged. Message arrivals do not trigger focus jumps; initial/final voting remains before roster, reference information and archived chat.

Actual mobile viewport geometry, virtual-keyboard behavior and scrolling require browser acceptance; CSS review and rendered markup do not prove them.

## Exact files changed by this patch

1. backend/app/callsigns.py — shared normalization, visible-name validation and comparison key.
2. backend/app/domain.py — Callsign validator uses the shared policy, retaining schema length metadata.
3. backend/app/missions.py — canonical duplicate check, direct-store validation and machine-readable MissionError codes.
4. backend/app/main.py — expose MissionError.code in existing HTTP error responses.
5. backend/tests/test_identity_hardening.py — 24 new normalized-name/concurrency/reconnect/score cases.
6. backend/tests/smoke_milestone4_1.py — automated live acceptance for three clients.
7. frontend/src/missionEntry.ts — friendly API mapping and pending request gate.
8. frontend/src/MissionEntryForm.tsx — accessible editable error/pending form presentation.
9. frontend/src/App.tsx — use the form/request boundary; retain input on errors; neutral completion wording.
10. frontend/src/ConsequenceOutcome.tsx — remove the buried score; export the focused authoritative score presentation.
11. frontend/src/Gameplay.tsx — place that score directly under the completed heading.
12. frontend/src/styles.css — compact mobile history cap, sender wrapping and score prominence.
13. frontend/tests/gameplay.test.tsx — seven new frontend checks, preserving all eleven previous checks.
14. docs/MILESTONE_4_1_VERIFICATION.md — this report.

Earlier Milestone 4 files/changes visible in git status are not all new Milestone 4.1 edits. They were not reset or removed. No timing, voting, tie detection, consequence application/ledger, host acknowledgement, crisis progression, collapse or score formula was changed by this patch. No dependency, infrastructure or deployment change was introduced.

## Automated verification

Run from the repository root:

| Command | Final result |
| --- | --- |
| .venv/bin/python -m pytest backend/tests -q | 126 passed; one existing Starlette/httpx TestClient deprecation warning |
| npm --prefix frontend test | 18 passed: 16 rendered-component checks and 2 async request/gating checks |
| npm --prefix frontend run typecheck | Passed |
| npm --prefix frontend run build | Passed; strict TypeScript, Vite 37 modules |
| .venv/bin/python -m pip check | No broken requirements found |
| git diff --check | Passed |
| .venv/bin/python backend/tests/smoke_milestone4_1.py | Passed; actual HTTP/WebSocket clients, described below |

All 102 pre-patch backend cases and 11 pre-patch frontend cases remain and pass. No failing test was weakened/skipped. No separate linter/formatter is configured.

New backend coverage includes exact/case/trim/Unicode/casefold/HTML-whitespace duplicates, hidden formatting rejection, no seat allocation, distinct names, cross-room names, three simultaneous-join variants, direct-store normalization, legacy-seat comparison, disconnected-name impersonation rejection, original credential identity, full-lobby stable duplicate codes, and three-client completion/reconnect. New frontend coverage includes exact inline error semantics/value preservation, editable retry, disabled pending form, synchronous duplicate request gating, prominent restored server score, whole/fractional/zero/max formatting, and composer/voting DOM order with 100 long messages.

## Automated/simulated multiplayer acceptance evidence

The live smoke starts a temporary real Uvicorn server with production authored Crisis 01 and a test-only 10x injected clock. Production 60/20/30 constants remain unchanged. It uses actual HTTP requests and three WebSocket clients, not mocked transport or a browser.

Passed Test A at protocol level:

- Eagle1 creates; Eagle2 joins.
- A new Eagle2 attempt receives 409/callsign_taken.
- Eagle3 joins the still-available seat.
- All clients see exactly Eagle1/Eagle2/Eagle3 in a three-seat roster.

Passed Test B at protocol level:

- Start assigns roles; Eagle2's socket actually closes and remaining clients see it disconnected.
- HTTP restoration with its valid credential ignores an attempted alternate display name.
- A new socket using that credential restores the same ID, roles, callsign, phase, crisis and authorized intelligence; roster remains three seats.

Discussion/voting and Test D at protocol level:

- All three send discussion messages; all receive shared history.
- The scheduler opens hidden voting. A/A/B selects authored A and applies the unchanged Milestone 4 effects.
- Host acknowledgement completes the one-crisis configured mission.
- All clients receive score 69 and final metrics 78/62/72/64.
- After all original sockets close, Eagle2 reconnects to completed state with the same identity/roles/result and score 69.
- The temporary server is terminated in cleanup.

Test C is only partially verified automatically: rendered components with 100 long messages keep the composer/Send before the single history region and move active voting before historical chat. Viewport bounds/wrapping were reviewed in CSS. No real mobile viewport scrolling, touch send, focus or keyboard interaction was performed.

## Manual browser status, remaining limitations and deferred work

No manual three-browser or physical-device test was performed. There is no configured Playwright/Puppeteer/browser-interaction harness in this checkout. Rendered-component and real-transport results are explicitly separate from manual/browser acceptance.

Outstanding: repeat duplicate/edit/retry in real browsers; check score visibility and formatting at desktop and 375px mobile widths; scroll a long history with the virtual keyboard open; verify Send remains comfortable to reach; and verify transitions from discussion through final voting/outcome bring controls into view without stealing focus on ordinary message arrivals.

The original raw ASCII duplicate incident cannot be fully reconstructed without its request/state data. The concrete normalization/invisible-character gaps are reproduced and closed, while standard exact duplicates are regression-covered. This does not add cross-script homoglyph protection or retroactively rename an old seat.

Existing single-worker/in-memory limits, only one production authored crisis, reserved disconnected seats without five-minute expiry/redistribution, and other previously deferred content/features remain unchanged. No unrelated work was advanced. No commit, tag or push was performed.

Implementation and automated verification are ready for review; manual browser/mobile acceptance remains outstanding.
