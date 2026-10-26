"""Offline campaign analysis: python -m app.campaign_analysis.

Enumerates all 3^10 paths with the same clamping/collapse functions as gameplay.
This module is never called by gameplay or exposed through an API.
"""
import json
from collections import Counter
from itertools import product

from .consequences import apply_metric_deltas, collapsed_metrics
from .crises import load_crisis_sequence
from .domain import Crisis, Metrics


def simulate(sequence: list[Crisis], path: str) -> dict:
    metrics = Metrics()
    raw_totals = dict.fromkeys(metrics.model_dump(), 0)
    for number, (crisis, choice_id) in enumerate(zip(sequence, path), 1):
        choice = next(c for c in crisis.choices if c.id == choice_id)
        for key, value in choice.metric_deltas.model_dump().items():
            raw_totals[key] += value
        metrics = apply_metric_deltas(metrics, choice.metric_deltas)
        if collapsed_metrics(metrics):
            return dict(path=path, survived=False, stopped_at=number, metrics=metrics.model_dump(),
                        score=None, executed_raw_deltas=raw_totals)
    return dict(path=path, survived=True, stopped_at=len(sequence), metrics=metrics.model_dump(),
                score=sum(metrics.model_dump().values()) / 4, executed_raw_deltas=raw_totals)


def analyze(sequence: list[Crisis] | None = None) -> dict:
    sequence = load_crisis_sequence() if sequence is None else sequence
    count = len(sequence)
    choices = [{c.id:c for c in crisis.choices} for crisis in sequence]
    dominated = []
    for crisis in sequence:
        for left, right in product(crisis.choices, repeat=2):
            a,b = left.metric_deltas.model_dump(), right.metric_deltas.model_dump()
            if all(a[k] >= b[k] for k in a) and any(a[k] > b[k] for k in a):
                dominated.append(dict(crisis=crisis.id, dominates=left.id, dominated=right.id))
    survivors = 0
    histogram = Counter()
    collapse_examples = {}
    zero_metrics = Counter()
    best = worst = robust = None
    for letters in product('ABC', repeat=count):
        path = ''.join(letters)
        result = simulate(sequence, path)
        if result['survived']:
            survivors += 1
            if best is None or result['score'] > best['score']: best = result
            if worst is None or result['score'] < worst['score']: worst = result
            if robust is None or min(result['metrics'].values()) > min(robust['metrics'].values()): robust = result
        else:
            stage = result['stopped_at']
            histogram[stage] += 1
            collapse_examples.setdefault(stage, result)
            for key,value in result['metrics'].items():
                if value == 0: zero_metrics[key] += 1
    strategies = {}
    for label,path in [('always_A','A'*count),('always_B','B'*count),('always_C','C'*count),
                       ('authored_AI',''.join(c.ai_recommendation_choice_id for c in sequence)),
                       ('alternating_ABC',('ABC'*count)[:count]),
                       ('alternating_CBA',('CBA'*count)[:count])]:
        result = simulate(sequence,path)
        # Full-horizon arithmetic is reported separately; never execute choices
        # after a collapse when describing a real playthrough.
        result['full_horizon_raw_deltas'] = {key:sum(choices[i][letter].metric_deltas.model_dump()[key]
                                                     for i,letter in enumerate(path))
                                             for key in Metrics().model_dump()}
        strategies[label] = result
    return dict(crises=count, paths=3**count, survivors=survivors, collapsed=3**count-survivors,
                survival_percent=round(survivors / 3**count * 100, 2),
                collapse_by_crisis=dict(sorted(histogram.items())), collapse_examples=collapse_examples,
                collapsed_metrics=dict(zero_metrics), pareto_dominance=dominated,
                recommendations=dict(Counter(c.ai_recommendation_choice_id for c in sequence)),
                strategies=strategies, best_score_path=best, lowest_surviving_score_path=worst,
                strongest_floor_path=robust)


if __name__ == '__main__':
    print(json.dumps(analyze(),indent=2))
