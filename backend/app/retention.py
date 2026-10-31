"""Additive operator metadata; never part of game projections or result hashes."""
from dataclasses import dataclass
import math


@dataclass
class MissionActivity:
    created_at: float
    last_activity: float
    finalized_at: float | None = None
    creator: str = ''

    def validate(self):
        values = [self.created_at, self.last_activity]
        if self.finalized_at is not None:
            values.append(self.finalized_at)
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
            raise ValueError('Invalid activity timestamps')
        if self.last_activity < self.created_at or len(self.creator) > 64:
            raise ValueError('Invalid activity metadata')
