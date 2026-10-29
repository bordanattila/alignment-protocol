"""Versioned story data contains interpretation and bounded public references only."""
from typing import Annotated, Literal
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, model_validator
from .generation.errors import FailureCategory

StoryText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=40, max_length=900)]


class StorySection(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)
    text: StoryText
    # Stable public crisis numbers identify decisions; no private voting round IDs.
    references: Annotated[tuple[Annotated[int, Field(ge=1, le=10)], ...],
                          BeforeValidator(lambda value: tuple(value) if isinstance(value, list) else value)] = Field(min_length=1, max_length=3)


class EndgameNarrative(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)
    schema_version: Literal['endgame-1.0']
    journey: StorySection
    cost: StorySection
    standing: StorySection


class EndgameDiagnostic(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    operation: Literal['endgame'] = 'endgame'
    source: Literal['generated', 'deterministic_fallback']
    category: FailureCategory | Literal['success', 'restart_recovery', 'internal_state', 'canceled']
    duration_seconds: float = Field(ge=0, allow_inf_nan=False, strict=True)
    http_status: int | None = Field(default=None, ge=100, le=599, strict=True)

    @model_validator(mode='after')
    def consistent(self):
        if (self.category == 'success') != (self.source == 'generated'):
            raise ValueError('Story source/category mismatch')
        return self


class ConclusionState(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    id: str = Field(min_length=1, max_length=128)
    basis_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    status: Literal['pending', 'generated', 'fallback'] = 'pending'
    narrative: EndgameNarrative | None = None
    diagnostic: EndgameDiagnostic | None = None

    @model_validator(mode='after')
    def consistent(self):
        if (self.status == 'generated') != (self.narrative is not None):
            raise ValueError('Story status mismatch')
        if (self.status == 'pending') != (self.diagnostic is None):
            raise ValueError('Story diagnostic mismatch')
        if self.diagnostic and (self.status == 'generated') != (self.diagnostic.source == 'generated'):
            raise ValueError('Story diagnostic source mismatch')
        return self
