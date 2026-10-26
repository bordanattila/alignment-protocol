"""Validate packaged authored content independently from rules and transport."""
import json
import re
from pathlib import Path

from .domain import Crisis


def load_crisis_sequence(directory: Path | None = None) -> list[Crisis]:
    directory = directory if directory is not None else Path(__file__).with_name("content")
    ids = json.loads((directory / "sequence.json").read_text(encoding="utf-8"))
    if (not isinstance(ids, list) or not ids
            or any(not isinstance(key, str) or not re.fullmatch(r"[a-z0-9-]+", key) for key in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("Require a nonempty sequence of distinct authored crisis IDs")
    available = {path.stem for path in directory.glob("*.json") if path.name != "sequence.json"}
    if set(ids) != available:
        raise ValueError(f"Sequence/content mismatch: missing={sorted(set(ids) - available)}, "
                         f"unreachable={sorted(available - set(ids))}")
    crises = [Crisis.model_validate_json((directory / f"{key}.json").read_text(encoding="utf-8"))
              for key in ids]
    if [crisis.id for crisis in crises] != ids:
        raise ValueError("Crisis IDs must match the configured sequence")
    return crises


def load_initial_crisis() -> Crisis:
    return load_crisis_sequence()[0]
