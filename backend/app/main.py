import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, Header, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketState

from .connections import LobbyConnections, close_socket
from .domain import JoinRequest
from .missions import MissionError, MissionStore


def create_app() -> FastAPI:
    app = FastAPI(title="Consensus Engine", version="0.1.0")
    store = MissionStore()
    app.state.missions = store
    # A player may have multiple tabs. Only their last socket closing marks them offline.
    connections = LobbyConnections(store)
    lock = asyncio.Lock()

    @app.exception_handler(MissionError)
    async def mission_error(_request: Request, exc: MissionError):
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "milestone": "lobby-foundation"}

    @app.post("/api/missions", status_code=201)
    async def create(body: JoinRequest):
        async with lock:
            mission, player = store.create(body.callsign)
            return {"token": mission.token, "credential": player.credential}

    @app.post("/api/missions/{token}/join")
    async def join(token: str, body: JoinRequest, x_mission_session: str | None = Header(default=None)):
        async with lock:
            mission, player = store.join(token, body.callsign, x_mission_session)
            await connections.broadcast(token)
            return {"token": mission.token, "credential": player.credential}

    @app.websocket("/api/missions/{token}/ws")
    async def lobby(socket: WebSocket, token: str):
        await socket.accept()
        player = None
        try:
            # Credentials go in a first frame, not a URL that access logs retain.
            frame = await asyncio.wait_for(socket.receive(), timeout=10)
            if frame["type"] == "websocket.disconnect":
                return
            text = frame.get("text")
            if text is None or len(text) > 4096:
                await close_socket(socket, reason="Expected a small text authentication message")
                return
            message = json.loads(text)
            if (not isinstance(message, dict) or set(message) != {"type", "credential"}
                    or message["type"] != "authenticate"
                    or not isinstance(message["credential"], str)
                    or len(message["credential"]) > 128):
                await close_socket(socket, reason="Invalid session message")
                return
            async with lock:
                player = store.authorize(token, message["credential"])
                connections.add(token, player.id, socket)
                await connections.broadcast(token)
            if socket.application_state == WebSocketState.DISCONNECTED:
                return
            while True:
                # This milestone accepts authentication only; game intents come later.
                frame = await socket.receive()
                if frame["type"] == "websocket.disconnect":
                    break
                await close_socket(socket, reason="No lobby actions are available yet")
                break
        except MissionError:
            await close_socket(socket, reason="Mission session unavailable")
        except (ValueError, RecursionError, asyncio.TimeoutError):
            await close_socket(socket, reason="Invalid session message")
        except WebSocketDisconnect:
            pass
        finally:
            if player:
                async with lock:
                    connections.remove(token, player.id, socket)
                    await connections.broadcast(token)

    build = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if build.is_dir():
        # Mission invite URLs use ?mission=token, so static serving needs no SPA fallback.
        app.mount("/", StaticFiles(directory=build, html=True), name="frontend")
    return app


app = create_app()
