# Milestone 2 verification

Implemented host-only authenticated HTTP start/discussion intents under the existing transport lock, deterministic balanced backend role assignment, validated and packaged Crisis 01 JSON matching the reference briefing/intelligence/choices, and explicit allowlisted public plus viewer-private snapshots. New React briefing component renders public content, assigned domains, private cards, and read-only choices with responsive command-center styling.

## Decisions

- Keep the in-memory single-worker store, existing sockets, credentials, multi-tab handling, and reconnect protocol.
- Require all occupied lobby seats connected and 2–4 seats before start. Reserved offline seats are not silently excluded or stripped of roles. This deliberately adds a start precondition; no seat-removal/host-transfer behavior is added.
- Assign roles round-robin in join order exactly once. Role ownership is public; intelligence is private. No client-supplied role or player identity controls assignment.
- Start enters visible `briefing`; host acknowledgement enters untimed `discussion`. Disconnected participants block this forward transition. No automatic timer or further progression exists.
- Public crisis projection excludes private intelligence and consequence/delta data. Viewer intelligence is a separate allowlisted field. The three authored consequence/delta sets are provisional content for future balancing and never execute here.
- JSON is included as setuptools package data, loaded relative to the module and validated before mission mutation.

## Commands and results

Inspection: `pwd`, `rg --files` (excluding lock/build/dependency output), `cat` of AGENTS.md, full product spec, backend/frontend source, tests, dependency manifests and README; `ls -a`; `git status --short`. Initial tree was clean. The sandbox launcher failed because bubblewrap is absent; subsequent shell commands used approved escalation.

- `.venv/bin/python -m pytest backend/tests -q`: initial collection failed because the existing editable installation referenced the old alignement-protocol directory.
- `.venv/bin/python -m pip install --no-deps --no-build-isolation -e ./backend`: failed because setuptools was not installed in the environment.
- `.venv/bin/python -m pip install -e './backend[dev]'`: passed, repairing the editable install using declared isolated build dependencies.
- `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q`: 44 passed.
- `.venv/bin/python -m pytest backend/tests -q` after install repair: 44 passed. One existing Starlette/httpx TestClient deprecation warning.
- `.venv/bin/python -m pip check`: passed, no broken requirements (initial and final runs).
- In frontend: `npm run typecheck`: passed.
- In frontend: `npm run build`: passed, including strict TypeScript and Vite production build (32 modules).
- `.venv/bin/python` inline live smoke script: passed. Spawned temporary Uvicorn on 127.0.0.1:18765; fetched health, built HTML and asset URLs; created/joined a mission; authenticated two actual WebSocket clients; verified shared briefing, disjoint intelligence, host start, discussion, and reconnect identity/roles/crisis. Server terminated after check.
- `git diff --check`: initially found an extra blank line at EOF in domain.py; corrected and rerun clean.

Tests cover balanced unique role coverage for 2/3/4 players, start authority/phase/count/presence guards, content schema, common briefing/recommendation, full-payload privacy, public-field privacy, late-join rejection, discussion guards, repeated start rejection, actual transport snapshots, and reconnect for 2/3/4 players. Existing foundation tests remain unchanged.

## Remaining checks and limits

Physical browser/device and visual mobile acceptance remain manual; no claim of browser-rendered verification. No frontend test framework is configured. Existing single-process memory limits, reserved seats, and lack of host transfer persist. The TestClient dependency deprecation is non-blocking and unchanged. All excluded milestone features remain unimplemented.

Milestone 2 is ready to commit on automated and live transport checks, with manual browser/mobile review still recommended. No commit or push performed.

## UI refinement addendum

Refinement-only files: `frontend/src/App.tsx`, `frontend/src/CrisisBriefing.tsx`, `frontend/src/styles.css`, new `frontend/src/RoleBadge.tsx`, and this addendum. The earlier Milestone 2 changes were already present and remain intact.

- Server-reported `briefing` or `discussion` selects the compact mission header; landing/lobby retain the hero. Existing branding stays above Crisis 01, the phase label, and the server-supplied crisis title. Crisis numbering remains 01 because this milestone has only one crisis and the current contract has no round index.
- Tighter gameplay spacing, desktop player columns, tablet stacking, wrapping badges/headings/text, and narrow-screen single-column metrics preserve reading order and existing 48px controls. No new dependencies.
- A shared text-labeled role badge uses blue/purple/amber/teal accents in the roster and private cards. Roles are read from existing server assignments; no frontend assignment or inference is added. Private cards render only the existing viewer-private payload.
- Response title presentation shortens “Follow the AI Recommendation” to “Follow AI Recommendation” and shows a neutral outlined “AI Recommended” badge based on the authoritative recommendation ID. Choice IDs, authored JSON titles/descriptions, and recommendation data are unchanged; no selection/voting controls exist.
- Backend source, WebSocket handling, session recovery, phase transitions, metrics, start guards, and privacy projections were not modified during refinement. Reviewed the UI diff for unrelated changes.

Verification commands:

- `npm --prefix frontend run typecheck`: passed.
- `npm --prefix frontend run build`: passed (33 modules), including TypeScript checking.
- `git diff --check`: passed.
- `rg --files frontend -g '*test*' -g '*spec*' -g '!node_modules' -g '!dist'`: no frontend tests found; package.json has no test script.
- Node `require.resolve` checks for `playwright`, `@playwright/test`, and `puppeteer`: unavailable in this checkout.

No manual or automated browser rendering was performed. Desktop 1440px, tablet 768px, mobile 375px, one/two-role rendering, and phase-transition visual acceptance remain browser checks; responsive CSS and rendering branches were reviewed in source only. No commit, tag, or push performed.
