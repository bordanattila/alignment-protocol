"""Lobby socket membership. Call under the transport's lock to order snapshots."""
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
    def __init__(self, store: MissionStore):
        self.store = store
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
        # On send failure remove the socket immediately, even if its receive task
        # has not exited yet. Republish corrected presence to surviving clients.
        # Each retry removes at least one socket, so this loop is bounded.
        while True:
            failed = False
            for player_id, connections in list(self.sockets.get(token, {}).items()):
                for socket in list(connections):
                    try:
                        await asyncio.wait_for(socket.send_json({
                            "type": "state", "mission": self.store.project(token, player_id)
                        }), timeout=2)
                    except (WebSocketDisconnect, RuntimeError, OSError, asyncio.TimeoutError):
                        self.remove(token, player_id, socket)
                        await close_socket(socket, code=1011, reason="Connection interrupted")
                        failed = True
            if not failed:
                return
