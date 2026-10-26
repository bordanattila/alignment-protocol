"""Domain foundations; transport and client projections must not serialize Mission."""
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


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
    infrastructure: int
    public_trust: int
    economy: int
    safety: int


class Choice(BaseModel):
    id: str
    title: str
    description: str
    consequence: str
    metric_deltas: MetricDeltas


class Crisis(BaseModel):
    id: str
    title: str
    briefing: str
    ai_recommendation_choice_id: str
    private_intelligence: dict[Role, str]
    choices: list[Choice] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_content(self):
        ids = {choice.id for choice in self.choices}
        if len(ids) != 3 or self.ai_recommendation_choice_id not in ids:
            raise ValueError("Require three distinct choices and a valid recommendation")
        if set(self.private_intelligence) != set(Role):
            raise ValueError("Require intelligence for all four roles")
        return self


Callsign = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=24)]


class JoinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    callsign: Callsign


class Player(BaseModel):
    id: str
    callsign: str
    credential: str
    connected: bool = False
    roles: list[Role] = Field(default_factory=list)


class Mission(BaseModel):
    token: str
    host_id: str
    phase: Phase = Phase.LOBBY
    crisis: Crisis | None = None
    metrics: Metrics = Field(default_factory=Metrics)
    players: list[Player] = Field(default_factory=list)
