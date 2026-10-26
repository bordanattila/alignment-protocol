"""Single-process, in-memory mission boundary. No transport objects live here."""
import secrets
import time
from collections.abc import Callable

from .domain import Mission, Player, Phase, Role, VotingRound, Decision, ChatMessage
from .voting import plurality
from .crises import load_initial_crisis


class MissionError(Exception):
    def __init__(self, message: str, status: int = 400):
        self.message = message
        self.status = status


class MissionStore:
    def __init__(self, clock: Callable[[], float] = time.time):
        self.clock = clock
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
        mission.deadline = self.clock() + 60

    def advance_due(self, token: str) -> bool:
        """Called under the state lock; re-check current state, never a stale callback.

        Late scheduler wakeups open a fresh full-duration phase rather than
        consuming a voting window players never had the opportunity to use.
        """
        mission = self.get(token)
        if mission.deadline is None or self.clock() < mission.deadline:
            return False
        if mission.phase in (Phase.DISCUSSION, Phase.CONSENSUS_WINDOW):
            self._open_vote(mission)
        elif mission.phase == Phase.VOTING:
            self._resolve(mission)
        else:
            return False
        return True

    def advance_all_due(self) -> list[str]:
        return [token for token in self._missions if self.advance_due(token)]

    def _open_vote(self, mission: Mission):
        mission.phase = Phase.VOTING
        mission.deadline = self.clock() + 30
        # All started seats still participate, including temporarily offline ones.
        mission.rounds.append(VotingRound(
            id=secrets.token_urlsafe(16), number=len(mission.rounds) + 1,
            eligible=[p.id for p in mission.players if p.roles], deadline=mission.deadline))

    def vote(self, token: str, credential: str, round_id: str, choice_id: str):
        player = self.authorize(token, credential)
        self.advance_due(token)
        mission = self.get(token)
        if mission.phase != Phase.VOTING:
            raise MissionError("Voting is not open.", 409)
        current = mission.rounds[-1]
        if current.id != round_id:
            raise MissionError("This voting round has closed.", 409)
        if player.id not in current.eligible:
            raise MissionError("This seat is not eligible to vote.", 403)
        if choice_id not in {c.id for c in mission.crisis.choices}:
            raise MissionError("Choose one of the authored responses.")
        if player.id in current.votes:
            raise MissionError("Your vote is already final for this round.", 409)
        current.votes[player.id] = choice_id
        if len(current.votes) == len(current.eligible):
            self._resolve(mission)

    def _resolve(self, mission: Mission):
        current = mission.rounds[-1]
        totals, leaders = plurality((c.id for c in mission.crisis.choices), current.votes.values())
        current.totals = totals
        current.abstentions = len(current.eligible) - len(current.votes)
        if len(leaders) > 1 and current.number == 1:
            mission.phase = Phase.CONSENSUS_WINDOW
            mission.deadline = self.clock() + 20
            return
        if not leaders:
            choice, reason = mission.crisis.ai_recommendation_choice_id, "no_vote_ai_fallback"
        elif len(leaders) > 1:
            choice, reason = mission.crisis.ai_recommendation_choice_id, "ai_tie_break"
        else:
            choice = leaders[0]
            reason = "initial_plurality" if current.number == 1 else "final_plurality"
        mission.decision = Decision(choice_id=choice, reason=reason, round_id=current.id,
                                    totals=totals, abstentions=current.abstentions,
                                    ai_followed=choice == mission.crisis.ai_recommendation_choice_id)
        mission.phase = Phase.DECISION_LOCKED
        mission.deadline = None

    def send_chat(self, token: str, credential: str, text: str):
        player = self.authorize(token, credential)
        self.advance_due(token)
        mission = self.get(token)
        if mission.phase not in (Phase.DISCUSSION, Phase.CONSENSUS_WINDOW):
            raise MissionError("Chat is read-only in this phase.", 409)
        # Domain callers also enforce bounds; the transport validates exact fields/types.
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 500:
            raise MissionError("Messages must contain 1–500 characters.")
        now = self.clock()
        if now - mission.last_chat_at.get(player.id, float("-inf")) < 1:
            raise MissionError("Please wait a second before sending another message.", 429)
        mission.last_chat_at[player.id] = now
        mission.chat.append(ChatMessage(id=secrets.token_urlsafe(16), sender_id=player.id,
                                        callsign=player.callsign, text=text.strip(), timestamp=now))
        mission.chat = mission.chat[-100:]

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
            "server_now": self.clock(),
            "deadline": mission.deadline,
            "chat": [message.model_dump() for message in mission.chat],
            "voting": None if not mission.rounds else {
                "round_id": mission.rounds[-1].id, "number": mission.rounds[-1].number,
                "eligible_count": len(mission.rounds[-1].eligible),
                "submitted_count": len(mission.rounds[-1].votes),
                "your_vote": mission.rounds[-1].votes.get(viewer_id),
            },
            "closed_rounds": [{"round_id": r.id, "number": r.number,
                               "totals": dict(r.totals), "abstentions": r.abstentions}
                              for r in mission.rounds if r.totals is not None],
            "decision": mission.decision.model_dump() if mission.decision else None,
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
