"""Snapshot under the state lock; send outside it, ordered by a delivery lock."""
import asyncio

from fastapi import WebSocket, WebSocketDisconnect

from .missions import MissionStore, MissionError
from .persistence import PersistenceError


async def close_socket(socket: WebSocket, code: int = 1008, reason: str = ""):
    try:
        await asyncio.wait_for(socket.close(code=code, reason=reason), timeout=2)
    except (WebSocketDisconnect, RuntimeError, OSError, asyncio.TimeoutError):
        # A failed transport must not prevent membership cleanup or other sends.
        pass


class LobbyConnections:
    def __init__(self, store: MissionStore, lock: asyncio.Lock | None = None, max_per_seat: int = 3):
        self.store = store
        self.lock = lock or asyncio.Lock()
        self.delivery_lock = asyncio.Lock()
        self.delivery_locks: dict[str, asyncio.Lock] = {}
        self.pending: set[str] = set()
        self.sockets: dict[str, dict[str, set[WebSocket]]] = {}
        self.max_per_seat = max_per_seat

    def add(self, token: str, player_id: str, socket: WebSocket):
        existing = self.sockets.get(token, {}).get(player_id, set())
        if len(existing) >= self.max_per_seat:
            raise MissionError('Too many connections for this seat.', 429, 'socket_capacity')
        self.store.set_connected(token, player_id, True)
        self.sockets.setdefault(token, {}).setdefault(player_id, set()).add(socket)

    def remove(self, token: str, player_id: str, socket: WebSocket):
        players = self.sockets.get(token, {})
        connections = players.get(player_id, set())
        connections.discard(socket)
        if not connections:
            players.pop(player_id, None)
            self.store.set_connected(token, player_id, False)
        if not players:
            self.sockets.pop(token, None)

    async def broadcast(self, token: str, retry_only: bool = False):
        # Callers release the state lock before publishing. Capture fresh immutable
        # projections only after acquiring the delivery lock, preventing old
        # broadcasts from overtaking newer snapshots. Never await network under
        # the state lock. Failed sends republish corrected presence.
        async with self.delivery_locks.setdefault(token, asyncio.Lock()):
            if retry_only and token not in self.pending:
                return
            self.pending.discard(token)
            try:
                # Churn must not hold a publisher indefinitely. A subsequent
                # scheduler pass retries corrected state after two waves.
                for _ in range(2):
                    async with self.lock:
                        self.store.bump_revision(token)
                        frames = [(player_id, socket, self.store.project(token, player_id))
                                  for player_id, sockets in self.sockets.get(token, {}).items()
                                  for socket in list(sockets)]
                    async def deliver(player_id, socket, state):
                        try:
                            await asyncio.wait_for(socket.send_json({
                                "type": "state", "mission": state
                            }), timeout=2)
                        except (WebSocketDisconnect, RuntimeError, OSError, asyncio.TimeoutError):
                            async with self.lock:
                                self.remove(token, player_id, socket)
                            await close_socket(socket, code=1011, reason="Connection interrupted")
                            return True
                        return False
                    failed = any(await asyncio.gather(*(deliver(*frame) for frame in frames)))
                    if not failed:
                        self.pending.discard(token)
                        return
                self.pending.add(token)
            except PersistenceError:
                self.pending.add(token)
                raise

    async def error(self, socket: WebSocket, message: str):
        async with self.delivery_lock:
            try:
                await asyncio.wait_for(socket.send_json({"type": "error", "detail": message}), timeout=2)
            except (WebSocketDisconnect, RuntimeError, OSError, asyncio.TimeoutError):
                await close_socket(socket, code=1011, reason="Connection interrupted")
