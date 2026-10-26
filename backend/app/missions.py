"""Single-process, in-memory mission boundary. No transport objects live here."""
import secrets

from .domain import Mission, Player


class MissionError(Exception):
    def __init__(self, message: str, status: int = 400):
        self.message = message
        self.status = status


class MissionStore:
    def __init__(self):
        self._missions: dict[str, Mission] = {}

    def get(self, token: str) -> Mission:
        if token not in self._missions:
            raise MissionError("This mission invite is unavailable.", 404)
        return self._missions[token]

    def create(self, callsign: str) -> tuple[Mission, Player]:
        player = self._player(callsign)
        mission = Mission(token=secrets.token_urlsafe(24), host_id=player.id, players=[player])
        self._missions[mission.token] = mission
        return mission, player

    def join(self, token: str, callsign: str, credential: str | None = None) -> tuple[Mission, Player]:
        mission = self.get(token)
        if credential is not None:
            return mission, self.authorize(token, credential)
        if mission.phase != "lobby":
            raise MissionError("This mission has already started.", 409)
        if len(mission.players) >= 4:
            raise MissionError("This mission has all four seats filled.", 409)
        if any(p.callsign.casefold() == callsign.casefold() for p in mission.players):
            raise MissionError("That callsign is already in use.", 409)
        player = self._player(callsign)
        mission.players.append(player)
        return mission, player

    def authorize(self, token: str, credential: str) -> Player:
        for player in self.get(token).players:
            if secrets.compare_digest(player.credential.encode(), credential.encode()):
                return player
        raise MissionError("Your mission session could not be restored.", 401)

    def set_connected(self, token: str, player_id: str, connected: bool):
        player = next(p for p in self.get(token).players if p.id == player_id)
        player.connected = connected

    def project(self, token: str, viewer_id: str) -> dict:
        mission = self.get(token)
        if viewer_id not in {p.id for p in mission.players}:
            raise MissionError("You are not a member of this mission.", 403)
        # Explicit allowlist: never return credentials or future private engine state.
        return {
            "token": mission.token,
            "phase": mission.phase,
            "host_id": mission.host_id,
            "you": viewer_id,
            "metrics": mission.metrics.model_dump(),
            "players": [{"id": p.id, "callsign": p.callsign, "connected": p.connected}
                        for p in mission.players],
        }

    @staticmethod
    def _player(callsign: str) -> Player:
        return Player(id=secrets.token_urlsafe(16), callsign=callsign,
                      credential=secrets.token_urlsafe(32))
