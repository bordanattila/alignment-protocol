import asyncio
import json
import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager, suppress
from collections.abc import Callable

from fastapi import FastAPI, Header, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.websockets import WebSocketState

from .connections import LobbyConnections, close_socket
from .domain import JoinRequest, ChatIntent, VoteIntent, ContinueRequest, Crisis
from .missions import MissionError, MissionStore
from .persistence import SQLiteMissions, PersistenceError
from .campaign import load_campaign_catalog


def create_app(clock: Callable[[], float] | None = None,
               crisis_loader: Callable[[], list[Crisis]] | None = None,
               database_path: str | Path | None = None) -> FastAPI:
    options = {}
    if clock is not None:
        options["clock"] = clock
    if crisis_loader is not None:
        options["crisis_loader"] = crisis_loader
    else:
        options["campaign_loader"] = load_campaign_catalog
    if database_path is not None:
        options["persistence"] = SQLiteMissions(database_path)
    store = MissionStore(**options)
    lock = asyncio.Lock()
    # Keep membership semantics, but isolate socket delivery from state mutation.
    connections = LobbyConnections(store, lock)

    async def tick():
        changed = set()
        async with lock:
            for token in store.mission_tokens():
                try:
                    if store.advance_due(token): changed.add(token)
                except PersistenceError:
                    logging.getLogger(__name__).error("Mission storage unavailable; timer will retry.")
        for token in changed | set(connections.pending):
            try:
                await connections.broadcast(token, retry_only=token not in changed)
            except PersistenceError:
                logging.getLogger(__name__).error("Mission publication waiting for storage recovery.")

    async def scheduler():
        while True:
            await asyncio.sleep(0.1)
            try:
                await tick()
            except PersistenceError:
                logging.getLogger(__name__).error("Mission storage unavailable; scheduler will retry.")

    @asynccontextmanager
    async def lifespan(_app):
        store.initialize()
        task = asyncio.create_task(scheduler())
        _app.state.scheduler_task = task
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            store.close()

    app = FastAPI(title="Consensus Engine", version="0.1.0", lifespan=lifespan)
    app.state.missions = store
    # Test hooks exercise the production scheduler path with a controlled clock.
    app.state.tick = tick
    app.state.lock = lock

    @app.exception_handler(PersistenceError)
    async def storage_error(_request: Request, _exc: PersistenceError):
        return JSONResponse({"detail": "Mission storage is temporarily unavailable. Retry after reconnecting.",
                             "code": "storage_unavailable"}, status_code=503)

    @app.exception_handler(MissionError)
    async def mission_error(_request: Request, exc: MissionError):
        return JSONResponse({"detail": exc.message, "code": exc.code}, status_code=exc.status)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "milestone": "consequences-progression"}

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
        return {"token": mission.token, "credential": x_mission_session or player.credential}

    @app.post("/api/missions/{token}/start")
    async def start(token: str, x_mission_session: str = Header()):
        async with lock:
            store.start(token, x_mission_session)
        await connections.broadcast(token)
        return {"status": "started"}

    @app.post("/api/missions/{token}/discussion")
    async def discussion(token: str, x_mission_session: str = Header()):
        async with lock:
            store.begin_discussion(token, x_mission_session)
        await connections.broadcast(token)
        return {"status": "discussion"}

    @app.post("/api/missions/{token}/continue")
    async def continue_mission(token: str, body: ContinueRequest, x_mission_session: str = Header()):
        async with lock:
            advanced = store.continue_mission(token, x_mission_session, body.result_id)
        await connections.broadcast(token)
        return {"advanced": advanced}

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
            credential = message["credential"]
            async with lock:
                player = store.authorize(token, credential)
                store.advance_due(token)
                connections.add(token, player.id, socket)
            await connections.broadcast(token)
            if socket.application_state == WebSocketState.DISCONNECTED:
                return
            while True:
                frame = await socket.receive()
                if frame["type"] == "websocket.disconnect":
                    break
                text = frame.get("text")
                if text is None or len(text) > 4096:
                    await close_socket(socket, reason="Expected a small text action message")
                    break
                message = json.loads(text)
                if not isinstance(message, dict) or message.get("type") not in ("chat", "vote"):
                    await close_socket(socket, reason="Unsupported mission action")
                    break
                try:
                    intent = (ChatIntent if message["type"] == "chat" else VoteIntent).model_validate(message)
                except ValidationError:
                    await connections.error(socket, "Invalid action fields or message length.")
                    continue
                error = None
                async with lock:
                    try:
                        if isinstance(intent, ChatIntent):
                            store.send_chat(token, credential, intent.text)
                        else:
                            store.vote(token, credential, intent.round_id, intent.choice_id)
                    except MissionError as exc:
                        error = exc.message
                # A late rejected intent may itself have advanced an expired phase.
                await connections.broadcast(token)
                if error:
                    await connections.error(socket, error)
        except PersistenceError:
            await close_socket(socket, code=1011, reason="Mission storage unavailable; reconnect to retry")
        except MissionError:
            await close_socket(socket, reason="Mission session unavailable")
        except (ValueError, RecursionError, asyncio.TimeoutError):
            await close_socket(socket, reason="Invalid session message")
        except WebSocketDisconnect:
            pass
        finally:
            if player:
                try:
                    async with lock:
                        connections.remove(token, player.id, socket)
                    await connections.broadcast(token)
                except PersistenceError:
                    await close_socket(socket, code=1011, reason="Mission storage unavailable; reconnect to retry")

    build = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if build.is_dir():
        # Mission invite URLs use ?mission=token, so static serving needs no SPA fallback.
        app.mount("/", StaticFiles(directory=build, html=True), name="frontend")
    return app


app = create_app(database_path=os.environ.get("CONSENSUS_DB_PATH", "data/consensus-engine.sqlite3"))
