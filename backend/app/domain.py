"""Domain foundations; transport and client projections must not serialize Mission."""
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, model_validator

from .callsigns import normalize_callsign


class Role(StrEnum):
    INFRASTRUCTURE = "infrastructure"
    COMMUNITY = "community"
    ECONOMY = "economy"
    SAFETY = "safety"


class Phase(StrEnum):
    LOBBY = "lobby"
    BRIEFING = "briefing"
    DISCUSSION = "discussion"
    VOTING = "voting"
    CONSENSUS_WINDOW = "consensus_window"
    DECISION_LOCKED = "decision_locked"
    RESOLUTION = "resolution"
    RECONNECT_WAIT = "reconnect_wait"
    COMPLETED = "completed"
    FAILED = "failed"


class Metrics(BaseModel):
    infrastructure: int = Field(default=70, ge=0, le=100)
    public_trust: int = Field(default=70, ge=0, le=100)
    economy: int = Field(default=70, ge=0, le=100)
    safety: int = Field(default=70, ge=0, le=100)


class MetricDeltas(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    infrastructure: int
    public_trust: int
    economy: int
    safety: int


AuthoredText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Choice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: AuthoredText
    title: AuthoredText
    description: AuthoredText
    consequence: AuthoredText
    metric_deltas: MetricDeltas


class Crisis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
    title: AuthoredText
    briefing: AuthoredText
    ai_recommendation_choice_id: AuthoredText
    private_intelligence: dict[Role, AuthoredText]
    choices: list[Choice] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_content(self):
        ids = {choice.id for choice in self.choices}
        if ids != {"A", "B", "C"} or self.ai_recommendation_choice_id not in ids:
            raise ValueError("Require choices A, B, C and a valid recommendation")
        if set(self.private_intelligence) != set(Role):
            raise ValueError("Require intelligence for all four roles")
        return self


Callsign = Annotated[str, StringConstraints(min_length=1, max_length=24), BeforeValidator(normalize_callsign)]


class JoinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    callsign: Callsign


class Player(BaseModel):
    id: str
    callsign: str
    credential: str
    connected: bool = False
    roles: list[Role] = Field(default_factory=list)


class ChatMessage(BaseModel):
    crisis_number: int = 1
    id: str
    sender_id: str
    callsign: str
    text: str
    timestamp: float


class VotingRound(BaseModel):
    id: str
    number: int
    eligible: list[str]
    deadline: float
    votes: dict[str, str] = Field(default_factory=dict)
    totals: dict[str, int] | None = None
    abstentions: int | None = None


class Decision(BaseModel):
    choice_id: str
    reason: Literal["initial_plurality", "final_plurality", "ai_tie_break", "no_vote_ai_fallback"]
    round_id: str
    totals: dict[str, int]
    abstentions: int
    ai_followed: bool


class CrisisResult(BaseModel):
    id: str
    crisis_id: str
    crisis_number: int
    crisis_title: str
    choice_title: str
    choice_description: str
    outcome: str
    decision: Decision
    before: Metrics
    after: Metrics
    authored_deltas: MetricDeltas
    applied_deltas: MetricDeltas


class ContinueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    result_id: str = Field(min_length=1, max_length=128)


class ChatIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["chat"]
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class VoteIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["vote"]
    round_id: str = Field(min_length=1, max_length=128)
    choice_id: str = Field(min_length=1, max_length=128)


class Mission(BaseModel):
    token: str
    host_id: str
    phase: Phase = Phase.LOBBY
    crisis: Crisis | None = None
    metrics: Metrics = Field(default_factory=Metrics)
    players: list[Player] = Field(default_factory=list)
    deadline: float | None = None
    rounds: list[VotingRound] = Field(default_factory=list)
    decision: Decision | None = None
    chat: list[ChatMessage] = Field(default_factory=list)
    last_chat_at: dict[str, float] = Field(default_factory=dict)
    sequence: list[Crisis] = Field(default_factory=list)
    crisis_index: int = 0
    results: list[CrisisResult] = Field(default_factory=list)
    acknowledged_results: set[str] = Field(default_factory=set)
    collapsed_metrics: list[str] = Field(default_factory=list)
    consensus_score: float | None = None
