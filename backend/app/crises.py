"""Validate authored content independently from mission rules and transport."""
from pathlib import Path

from .domain import Crisis


def load_initial_crisis() -> Crisis:
    source = Path(__file__).with_name("content") / "grid-under-pressure.json"
    return Crisis.model_validate_json(source.read_text(encoding="utf-8"))
