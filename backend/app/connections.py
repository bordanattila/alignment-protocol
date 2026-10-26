"""Snapshot under the state lock; send outside it, ordered by a delivery lock."""
import asyncio

from fastapi import WebSocket, WebSocketDisconnect

from .missions import MissionStore


async def close_socket(socket: WebSocket, code: int = 1008, reason: str = ""):
    try:
        await asyncio.wait_for(socket.close(code=code, reason=reason), timeout=2)
    except (WebSocketDisconnect, RuntimeError, OSError, asyncio.TimeoutError):
        # A failed transport must not prevent membership cleanup or other sends.
        pass


class LobbyConnections:
    def __init__(self, store: MissionStore, lock: asyncio.Lock | None = None):
        self.store = store
        self.lock = lock or asyncio.Lock()
        self.delivery_lock = asyncio.Lock()
        self.sockets: dict[str, dict[str, set[WebSocket]]] = {}

    def add(self, token: str, player_id: str, socket: WebSocket):
        self.sockets.setdefault(token, {}).setdefault(player_id, set()).add(socket)
        self.store.set_connected(token, player_id, True)

    def remove(self, token: str, player_id: str, socket: WebSocket):
        players = self.sockets.get(token, {})
        connections = players.get(player_id, set())
        connections.discard(socket)
        if not connections:
            players.pop(player_id, None)
            self.store.set_connected(token, player_id, False)
        if not players:
            self.sockets.pop(token, None)

    async def broadcast(self, token: str):
        # Callers release the state lock before publishing. Capture fresh immutable
        # projections only after acquiring the delivery lock, preventing old
        # broadcasts from overtaking newer snapshots. Never await network under
        # the state lock. Failed sends republish corrected presence.
        async with self.delivery_lock:
            while True:
                async with self.lock:
                    self.store.get(token).revision += 1
                    frames = [(player_id, socket, self.store.project(token, player_id))
                              for player_id, sockets in self.sockets.get(token, {}).items()
                              for socket in list(sockets)]
                failed = False
                for player_id, socket, state in frames:
                    try:
                        await asyncio.wait_for(socket.send_json({
                            "type": "state", "mission": state
                        }), timeout=2)
                    except (WebSocketDisconnect, RuntimeError, OSError, asyncio.TimeoutError):
                        async with self.lock:
                            self.remove(token, player_id, socket)
                        await close_socket(socket, code=1011, reason="Connection interrupted")
                        failed = True
                if not failed:
                    return

    async def error(self, socket: WebSocket, message: str):
        async with self.delivery_lock:
            try:
                await asyncio.wait_for(socket.send_json({"type": "error", "detail": message}), timeout=2)
            except (WebSocketDisconnect, RuntimeError, OSError, asyncio.TimeoutError):
                await close_socket(socket, code=1011, reason="Connection interrupted")
