"""Bounded deterministic memory from public snapshots and executed consequences."""
from ..domain import Mission, Metrics
from .contract import (DecisionContext, FrozenMetrics, FrozenDeltas, GenerationContext,
                       NarrativeMemory, EstablishedEvent, MetricPressure)


def decision_context(result) -> DecisionContext:
    return DecisionContext(
        crisis_number=result.crisis_number, crisis_id=result.crisis_id,
        title=result.crisis_title[:120], choice_id=result.decision.choice_id,
        choice_title=result.choice_title[:120], consequence=result.outcome[:600],
        applied_deltas=FrozenDeltas(**result.applied_deltas.model_dump()))


def build_memory(mission: Mission) -> NarrativeMemory:
    current = mission.metrics.model_dump()
    initial = (mission.initial_metrics or Metrics()).model_dump()
    earlier = sorted(mission.results[:-3], key=lambda r:(-sum(abs(v) for v in r.applied_deltas.model_dump().values()), r.crisis_number))[:2]
    earlier.sort(key=lambda r:r.crisis_number)
    def pressure(key):
        return MetricPressure(metric=key, current_value=current[key], change_since_start=current[key]-initial[key],
            contributing_decisions=tuple(r.crisis_number for r in mission.results if r.applied_deltas.model_dump()[key]<0)[-3:])
    return NarrativeMemory(
        significant_earlier_decisions=tuple(decision_context(r) for r in earlier),
        established_events=tuple(EstablishedEvent(crisis_id=r.crisis_id, crisis_number=r.crisis_number,
                                                  situation=r.briefing[:300]) for r in mission.results[-3:]),
        open_pressures=tuple(pressure(k) for k in current if current[k]<initial[k]),
        recurring_costs=tuple(pressure(k) for k in current if sum(r.applied_deltas.model_dump()[k]<0 for r in mission.results)>=2),
        strengths=tuple(k for k in current if current[k]==max(current.values())),
        weaknesses=tuple(k for k in current if current[k]==min(current.values())),
        used_titles=tuple(c.title[:120] for c in mission.sequence[:len(mission.results)]))


def build_context(mission: Mission) -> GenerationContext:
    used = list(dict.fromkeys(result.crisis_id for result in mission.results))
    if mission.crisis is not None and mission.crisis.id not in used:
        used.append(mission.crisis.id)
    return GenerationContext(
        current_crisis_number=(mission.generation.target_index if mission.generation else mission.crisis_index) + 1,
        metrics=FrozenMetrics(**mission.metrics.model_dump()),
        history=tuple(decision_context(r) for r in mission.results[-3:]),
        used_scenario_ids=tuple(used), narrative_memory=build_memory(mission))
