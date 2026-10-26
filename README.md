# Consensus Engine

*Intelligence proposes. Humanity decides.*

Milestone 2: a React/TypeScript mission screen and a FastAPI-authoritative, live 2–4-seat lobby with host-controlled mission start and Crisis 01 information delivery. Create a mission, share its invite URL, and join with a callsign. Separate browser profiles receive separate seats; refreshes and additional tabs reuse the saved seat credential.

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
npm run typecheck
npm run build
```

The backend suite covers membership, validation, capacity, credential privacy, WebSocket synchronization, refresh/reconnect identity, malformed messages, multiple tabs, and failed-send cleanup. TypeScript uses strict checking; no separate lint tool or frontend test framework is configured.

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

The invite token permits joining; a separate credential authorizes a seat. Credentials travel in the first WebSocket frame rather than the URL and are excluded from public snapshots. Disconnected lobby seats remain reserved indefinitely. There is no host transfer, mission expiry, persistence, or public deployment abuse limiting yet. One slow socket can delay lobby operations while its bounded send/close attempts finish.

The host starts once 2–4 occupied seats are connected. The backend assigns all four roles in join order, loads validated authored JSON, and enters `briefing`. The host selects Begin discussion to enter untimed `discussion`; disconnected players must reconnect before this transition. Private intelligence is projected separately for each seat, while briefing, choices, and role ownership are public. Refresh retains the same assignment and crisis. Authored consequences are server-only data and are not executed.

This milestone does not implement chat, voting, gameplay timers, consequences, crisis sequencing, QR joining, or five-minute match disconnect handling. Physical browser/device and mobile usability checks remain manual. It is a foundation for the next milestone, not the complete v0.1 game.

See [Milestone 2 verification](docs/MILESTONE_2_VERIFICATION.md) for implementation decisions, commands, results, and remaining checks.
