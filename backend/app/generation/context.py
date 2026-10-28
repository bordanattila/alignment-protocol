"""Explicit allowlist; no mission serialization, chat, identities or vote tallies."""
from ..domain import Mission
from .contract import DecisionContext, FrozenMetrics, GenerationContext


def build_context(mission: Mission) -> GenerationContext:
    history = tuple(DecisionContext(
        crisis_number=result.crisis_number, crisis_id=result.crisis_id,
        title=result.crisis_title[:120], choice_id=result.decision.choice_id,
        choice_title=result.choice_title[:120], consequence=result.outcome[:600],
    ) for result in mission.results[-3:])
    used = list(dict.fromkeys(result.crisis_id for result in mission.results))
    if mission.crisis is not None and mission.crisis.id not in used:
        used.append(mission.crisis.id)
    return GenerationContext(
        current_crisis_number=mission.crisis_index + 1,
        metrics=FrozenMetrics(**mission.metrics.model_dump()),
        history=history, used_scenario_ids=tuple(used),
    )
