"""Shared production/offline consequence rules; no transport or mutation."""
from .domain import Metrics, MetricDeltas


def apply_metric_deltas(metrics: Metrics, deltas: MetricDeltas) -> Metrics:
    changes = deltas.model_dump()
    return Metrics(**{key: max(0, min(100, value + changes[key]))
                      for key, value in metrics.model_dump().items()})


def collapsed_metrics(metrics: Metrics) -> list[str]:
    return [key for key, value in metrics.model_dump().items() if value == 0]
