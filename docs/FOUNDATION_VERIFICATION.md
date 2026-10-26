# Foundation verification report

This report covers the mission/lobby hardening pass only. No gameplay was added. No commits or pushes were made.

## Results

- Declared backend dependencies installed into `.venv`; declared frontend dependencies installed into `frontend/node_modules`, generating `frontend/package-lock.json`. No new dependency declarations were added.
- Backend: **35 tests passed**, with one upstream Starlette warning that its httpx-based TestClient is deprecated in favor of httpx2. The existing declared httpx test dependency was retained.
- Frontend: strict TypeScript check passed; Vite production build passed (31 modules).
- FastAPI import, Uvicorn startup, health endpoint, built HTML/JS serving, real-network two-client WebSocket synchronization, credential privacy, disconnect, and same-seat reconnect passed.
- Vite development startup and HTML passed. The live smoke test did not separately exercise Vite's API proxy.
- Both smoke-test servers shut down without tracebacks.
- `pip check`: no broken requirements. `git diff --check`: passed (tracked changes only; Git does not inspect untracked scaffold files with this command).
- No lint command was run: no linter is configured. Frontend verification uses strict TypeScript and the production build without adding a test framework.

## Exact files changed in this pass

Modified relative to the starting working tree (several scaffold files were already untracked):

- `.gitignore` — ignore TypeScript build metadata.
- `README.md` — exact setup, development, verification, and single-service commands plus scope and limitations.
- `backend/app/main.py` — validate authentication frames, reject unsupported frames, handle disconnects, and use connection cleanup boundary.
- `backend/app/missions.py` — reject explicitly empty credentials and safely compare Unicode input.
- `frontend/package.json` — explicit typecheck script; build invokes typecheck.
- `frontend/src/styles.css` — remove empty import.
- `frontend/src/useLobby.ts` — encode mission token in WebSocket path.

Created:

- `backend/app/connections.py` — socket membership, bounded send/close handling, failed-send removal and corrected presence broadcasts.
- `backend/tests/test_foundation.py` — 35 parameterized test cases.
- `frontend/package-lock.json` — resolved declared frontend dependencies.
- `docs/FOUNDATION_VERIFICATION.md` — this report, including all shell commands from this pass.

Generated/ignored installation and runtime outputs include `.venv/`, Python egg metadata and bytecode/cache directories, `frontend/node_modules/`, and `frontend/dist/`. They are not source changes.

Existing `AGENTS.md` changes and the untracked product specification were preserved. Domain models, Vite configuration, and the overall FastAPI-authoritative architecture were retained.

## Remaining limits and readiness

The foundation is ready for the next incremental development milestone, not a finished/public-release v0.1 game. Physical browser/phone usability and browser localStorage behavior have not been exercised with browser automation or real devices. Reconnect identity is verified at the server/transport boundary. Lobby seats remain reserved indefinitely; missions have no expiry/abuse limits or persistence, require one worker, and disappear on restart. Slow clients can delay lobby operations while bounded send/close attempts finish. Deployment-specific WebSocket origin policy remains future hosting work. Role assignment, game start, crises, chat, voting, gameplay timers/consequences, QR joining, and match disconnect grace periods remain deliberately unimplemented.

## Complete shell command log

Commands below are exact shell invocations, including inspections. Working directory defaults to `/home/attila_unix/projects/consensus-engine`. Repository edits used the patch tool rather than shell commands. The first inspection was attempted in the sandbox and failed because bubblewrap was unavailable; its identical approved escalation succeeded. Subsequent commands ran with approved escalation because the sandbox could not launch.

### 1. Repository root

```sh
git status --short && cat AGENTS.md && rg --files backend frontend && cat backend/pyproject.toml backend/app/main.py backend/app/missions.py backend/app/domain.py frontend/package.json frontend/tsconfig.json frontend/vite.config.ts frontend/src/useLobby.ts frontend/src/session.ts frontend/src/App.tsx README.md
```

Result: Sandbox launch failed (missing bubblewrap); retried with approved escalation and succeeded.

### 2. Working directory: `/home/attila_unix/projects/consensus-engine`

```sh
cat .gitignore frontend/src/types.ts frontend/src/main.tsx frontend/src/styles.css frontend/index.html backend/app/__init__.py && git diff -- AGENTS.md
```

Result: Exit 0.

### 3. Working directory: `/home/attila_unix/projects/consensus-engine/frontend`

```sh
npm install
```

Result: Started session 57763; its completion is recorded below.

### 4. Working directory: `/home/attila_unix/projects/consensus-engine`

```sh
python3 -m venv .venv && .venv/bin/python -m pip install -e './backend[dev]'
```

Result: Started session 66039; its completion is recorded below.

Process output collection for session 66039: exit 0. This was a tool poll, not a shell command.

Process output collection for session 57763: exit 0. This was a tool poll, not a shell command.

### 5. Working directory: `/home/attila_unix/projects/consensus-engine/frontend`

```sh
npm run typecheck && npm run build
```

Result: Exit 0. TypeScript and production build passed.

### 6. Working directory: `/home/attila_unix/projects/consensus-engine`

```sh
.venv/bin/python -m pytest backend/tests -q
```

Result: Exit 0. 35 passed; 1 upstream deprecation warning.

### 7. Repository root

```sh
.venv/bin/python - <<'PY'
import json
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
from websockets.sync.client import connect
from app.main import app

root = Path.cwd()
assert app.title == "Consensus Engine"
print("FastAPI import: PASS")

def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]

def wait_ready(process, url):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Server exited before readiness")
        try:
            response = httpx.get(url, timeout=0.3)
            if response.status_code == 200:
                return response
        except httpx.TransportError:
            pass
        time.sleep(0.05)
    raise RuntimeError("Server readiness deadline exceeded")

processes = []
with tempfile.TemporaryFile(mode="w+") as logs:
    try:
        port = free_port()
        server = subprocess.Popen(
            [str(root / ".venv/bin/python"), "-m", "uvicorn", "app.main:app",
             "--host", "127.0.0.1", "--port", str(port), "--workers", "1",
             "--ws-max-size", "4096"], stdout=logs, stderr=subprocess.STDOUT)
        processes.append(server)
        base = f"http://127.0.0.1:{port}"
        assert wait_ready(server, base + "/api/health").json()["status"] == "ok"
        page = httpx.get(base + "/")
        assert page.status_code == 200 and 'id="root"' in page.text
        import re
        asset = re.search(r'src="([^"]+\.js)"', page.text).group(1)
        assert httpx.get(base + asset).status_code == 200
        print("Uvicorn startup, health, built HTML and JS: PASS")

        host = httpx.post(base + "/api/missions", json={"callsign": "Host"}).json()
        token = host["token"]
        url = f"ws://127.0.0.1:{port}/api/missions/{token}/ws"
        def auth(ws, credential):
            ws.send(json.dumps({"type": "authenticate", "credential": credential}))
            return json.loads(ws.recv(timeout=3))["mission"]
        with connect(url) as first:
            host_state = auth(first, host["credential"])
            guest = httpx.post(base + f"/api/missions/{token}/join", json={"callsign": "Guest"}).json()
            assert len(json.loads(first.recv(timeout=3))["mission"]["players"]) == 2
            with connect(url) as second:
                guest_state = auth(second, guest["credential"])
                snapshot = json.loads(first.recv(timeout=3))["mission"]
                assert snapshot["players"] == guest_state["players"]
                assert host["credential"] not in json.dumps(snapshot)
                assert guest["credential"] not in json.dumps(snapshot)
            assert not json.loads(first.recv(timeout=3))["mission"]["players"][1]["connected"]
            with connect(url) as refreshed:
                restored = auth(refreshed, guest["credential"])
                assert restored["you"] == guest_state["you"]
                assert len(restored["players"]) == 2
                assert json.loads(first.recv(timeout=3))["mission"]["players"][1]["connected"]
        print("Real-network lobby sync, privacy, disconnect and reconnect: PASS")

        vite_port = free_port()
        vite = subprocess.Popen(
            ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(vite_port), "--strictPort"],
            cwd=root / "frontend", stdout=logs, stderr=subprocess.STDOUT,
            start_new_session=True)
        processes.append(vite)
        response = wait_ready(vite, f"http://127.0.0.1:{vite_port}/")
        assert 'src="/src/main.tsx"' in response.text
        print("Vite development server startup and HTML: PASS")
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                if process is processes[-1] and len(processes) == 2:
                    import os, signal
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
                process.wait(timeout=5)
        logs.seek(0)
        output = logs.read()
        assert "Traceback" not in output, output
        print("Server shutdown without traceback: PASS")
PY
```

Result: Exit 0. All six live smoke checks passed.

### 8. Repository root

```sh
git diff --check && .venv/bin/python -m pip check && git status --short && cat backend/app/main.py backend/app/connections.py && rg --files backend/tests frontend -g '!node_modules' -g '!dist' -g '!package-lock.json'
```

Result: Exit 0. Dependency consistency and tracked whitespace checks passed.

The live smoke command also launches the exact Uvicorn and npm/Vite subprocess arguments shown in its Python code, then terminates them in its cleanup block. No additional test/build/lint commands were run.

