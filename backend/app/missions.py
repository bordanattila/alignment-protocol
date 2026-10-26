"""Single-process, in-memory mission boundary. No transport objects live here."""
import secrets

from .domain import Mission, Player, Phase, Role
from .crises import load_initial_crisis


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

    def start(self, token: str, credential: str):
        mission = self.get(token)
        self._host(token, credential)
        if mission.phase != Phase.LOBBY:
            raise MissionError("This mission has already started.", 409)
        if not 2 <= len(mission.players) <= 4 or not all(p.connected for p in mission.players):
            raise MissionError("Start requires 2–4 players with every occupied seat connected.", 409)
        # Validate content before mutating the mission. Join order gives stable,
        # balanced assignment; reconnect never reruns assignment.
        crisis = load_initial_crisis()
        for index, role in enumerate(Role):
            mission.players[index % len(mission.players)].roles.append(role)
        mission.crisis = crisis
        mission.phase = Phase.BRIEFING

    def begin_discussion(self, token: str, credential: str):
        mission = self.get(token)
        self._host(token, credential)
        if mission.phase != Phase.BRIEFING:
            raise MissionError("Discussion can only begin after the briefing.", 409)
        if not all(p.connected for p in mission.players):
            raise MissionError("Wait for every player to reconnect before continuing.", 409)
        mission.phase = Phase.DISCUSSION

    def _host(self, token: str, credential: str):
        player = self.authorize(token, credential)
        if player.id != self.get(token).host_id:
            raise MissionError("Only the mission host can do that.", 403)

    def project(self, token: str, viewer_id: str) -> dict:
        mission = self.get(token)
        if viewer_id not in {p.id for p in mission.players}:
            raise MissionError("You are not a member of this mission.", 403)
        viewer = next(p for p in mission.players if p.id == viewer_id)
        crisis = mission.crisis
        # Explicit allowlist: never return credentials or future private engine state.
        return {
            "token": mission.token,
            "phase": mission.phase,
            "host_id": mission.host_id,
            "you": viewer_id,
            "metrics": mission.metrics.model_dump(),
            "roles": list(viewer.roles),
            "crisis": None if crisis is None else {
                "id": crisis.id, "title": crisis.title, "briefing": crisis.briefing,
                "ai_recommendation_choice_id": crisis.ai_recommendation_choice_id,
                "choices": [{"id": c.id, "title": c.title, "description": c.description}
                            for c in crisis.choices],
            },
            "private_intelligence": {} if crisis is None else {
                role: crisis.private_intelligence[role] for role in viewer.roles
            },
            "players": [{"id": p.id, "callsign": p.callsign, "connected": p.connected, "roles": list(p.roles)}
                        for p in mission.players],
        }

    @staticmethod
    def _player(callsign: str) -> Player:
        return Player(id=secrets.token_urlsafe(16), callsign=callsign,
                      credential=secrets.token_urlsafe(32))
