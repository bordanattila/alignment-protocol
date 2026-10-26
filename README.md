# Consensus Engine

*Intelligence proposes. Humanity decides.*

Milestone 4: a React/TypeScript cooperative game with a FastAPI-authoritative 2–4-player mission, timed discussion/chat, hidden plurality voting, authored consequences, and configured crisis progression. Create a mission, share its invite URL, and join with a callsign. Separate browser profiles receive separate seats; refreshes and additional tabs reuse the saved seat credential.

## Development

Requires Python 3.12+ and Node 20.19+. Run from the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e './backend[dev]'
.venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --ws-max-size 4096
```

In another terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. Vite proxies HTTP and WebSockets to FastAPI. To try another device on the same network, open the computer's LAN address on port 5173 and create/copy the invite there. A localhost invite only works on the host computer. If clipboard access is unavailable, copy the displayed invite field manually.

## Verification

From the repository root:

```sh
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python -m pip check
cd frontend
npm test
npm run typecheck
npm run build
```

The backend suite covers membership, validation, capacity, credential privacy, WebSocket synchronization, refresh/reconnect identity, malformed messages, multiple tabs, and failed-send cleanup. TypeScript uses strict checking; rendered React tests use the existing esbuild toolchain and Node test runner. No separate linter is configured.

## Serve the built app

```sh
cd frontend
npm ci
npm run build
cd ..
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --ws-max-size 4096
```

FastAPI serves `frontend/dist` if it exists at startup. Open http://localhost:8000. Use one worker: missions and sockets are in memory and are lost on restart. Invite URLs use `/?mission=<token>`.

## Architecture and current limits

- `backend/app/domain.py`: typed internal state and crisis schema foundations.
- `backend/app/missions.py`: membership, seat authorization, and explicit public projections.
- `backend/app/connections.py`: socket membership, presence, and bounded send/close cleanup.
- `backend/app/main.py`: HTTP/WebSocket transport and static frontend serving. A lock serializes membership operations and snapshots.
- `frontend/src/`: React UI, per-mission credentials in localStorage, and WebSocket retry.

The invite token permits joining; a separate credential authorizes a seat. Credentials travel in the first WebSocket frame rather than the URL and are excluded from public snapshots. Disconnected lobby seats remain reserved indefinitely. There is no host transfer, mission expiry, persistence, or public deployment abuse limiting yet. Socket sends run outside the state lock, with bounded waits; slow clients can still delay publications.

The host starts once 2–4 occupied seats are connected. The backend assigns all four roles once, loads the packaged scripted sequence, and enters `briefing`. Begin discussion starts 60 seconds of chat, followed by 30-second hidden voting. A tied highest submitted count opens a 20-second chat/Consensus Window and fresh 30-second final vote. Plurality, final AI tie-break, and explicitly labeled no-vote fallback are server-owned. Private intelligence and own-vote state are projected per seat.

Every decision applies its authored consequence exactly once. The durable `decision_locked` result shows its narrative, before/after metrics, applied changes, and resolution method. The host selects Next crisis after review; the result ID makes retries safe. All occupied seats must reconnect before advancing. Seats/roles/metrics persist; new crises start with fresh briefing and vote state. Zero metrics immediately cause collapse. After the final configured result, Finish mission enters completion and computes the server-side average Consensus Score.

`backend/app/content/sequence.json` currently configures only **Grid Under Pressure**. There is no production Crisis 02 yet; adding validated crisis files and IDs to the manifest extends progression without engine changes. Tests cover two- and ten-crisis fixture sequences. Only the selected public result's consequence/deltas are exposed; future content and other roles' intelligence remain server-side.

State persists only within the running process. Five-minute seat removal/role redistribution, additional authored crises, variable pool ordering/weakest-metric finales, QR joining, and replay controls remain future work. Physical browser/device and mobile acceptance remain manual. This is not the complete ten-crisis v0.1 game.

Milestone 4 checks and automated live fixture acceptance:

```sh
.venv/bin/python backend/tests/smoke_milestone4.py
```

This test starts a temporary fixture server with a two-crisis sequence and 10x injected clock. It does not change the production sequence or duration constants.

See [Milestone 4 verification](docs/MILESTONE_4_VERIFICATION.md) for current behavior, exact commands/results, architecture decisions, and manual-review limits.

See [Milestone 2 verification](docs/MILESTONE_2_VERIFICATION.md) for implementation decisions, commands, results, and remaining checks.
