"""Seeded ten-slot pacing and a single authored prior-decision prerequisite."""
import json
import random
import re
from pathlib import Path

from .domain import Crisis, CrisisResult, Campaign, Scenario


STAGES = (1, 1, 1, 2, 2, 2, 3, 3, 3, 4)


def validate_catalog(scenarios: list[Scenario]):
    by_id = {entry.crisis.id: entry for entry in scenarios}
    if len(by_id) != len(scenarios) or len({s.crisis.title for s in scenarios}) != len(scenarios):
        raise ValueError('Duplicate scenario identifier or title')
    if 'grid-under-pressure' not in by_id or by_id['grid-under-pressure'].stage != 1:
        raise ValueError('Missing introductory crisis')
    for stage in range(1, 5):
        needed = STAGES.count(stage)
        if sum(s.stage == stage and s.prerequisite is None for s in scenarios) < needed:
            raise ValueError('Each stage requires sufficient independent fallbacks')
    for entry in scenarios:
        prerequisite = entry.prerequisite
        if prerequisite:
            source = by_id.get(prerequisite.crisis_id)
            # Strictly earlier stages forbid cycles, self-links and impossible
            # same-stage chains. Dependencies never force a particular vote.
            if source is None or source.stage >= entry.stage or source.prerequisite:
                raise ValueError('Follow-up must reference an independent earlier-stage crisis')
            if len(set(prerequisite.choice_ids)) != len(prerequisite.choice_ids):
                raise ValueError('Duplicate prerequisite choice')


def load_campaign_catalog(directory: Path | None = None) -> list[Scenario]:
    directory = directory if directory is not None else Path(__file__).with_name('content')
    metadata = json.loads((directory/'expansion'/'catalog.json').read_text())
    if not isinstance(metadata, list) or not metadata: raise ValueError('Require a nonempty catalog')
    scenarios = []
    referenced = set()
    for record in metadata:
        if not isinstance(record, dict) or 'id' not in record: raise ValueError('Invalid catalog entry')
        record = dict(record)
        key = record.pop('id')
        # Validate identifiers before ever using one as a path.
        if not isinstance(key, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', key):
            raise ValueError('Invalid catalog identifier')
        path = directory/f'{key}.json'
        if not path.exists(): path = directory/'expansion'/f'{key}.json'
        crisis = Crisis.model_validate_json(path.read_text())
        if crisis.id != key: raise ValueError('Catalog/file identifier mismatch')
        referenced.add(path)
        scenarios.append(Scenario(crisis=crisis, **record))
    authored = set(directory.glob('*.json')) - {directory/'sequence.json'}
    authored |= set((directory/'expansion').glob('*.json')) - {directory/'expansion'/'catalog.json'}
    if authored != referenced: raise ValueError('Catalog must reference every authored crisis exactly once')
    validate_catalog(scenarios)
    return scenarios


def select_crisis(campaign: Campaign, index: int, results: list[CrisisResult]) -> Crisis:
    if not 0 <= index < 10: raise ValueError('Campaign slot must be between 0 and 9')
    used = {result.crisis_id for result in results}
    records = {result.crisis_id: result for result in results}
    candidates = [s for s in campaign.scenarios if s.stage == STAGES[index] and s.crisis.id not in used]
    eligible = [s for s in candidates if s.prerequisite and s.prerequisite.crisis_id in records
                and records[s.prerequisite.crisis_id].decision.choice_id in s.prerequisite.choice_ids]
    fallbacks = [s for s in candidates if s.prerequisite is None]
    options = eligible or fallbacks
    if index == 0: options = [s for s in options if s.crisis.id == 'grid-under-pressure']
    if not options: raise ValueError('No valid crisis available for this stage')
    selected = random.Random(f'{campaign.seed}:{index}').choice(sorted(options, key=lambda s:s.crisis.id))
    crisis = selected.crisis.model_copy(deep=True)
    if selected.prerequisite:
        source = records[selected.prerequisite.crisis_id]
        context = (f'Earlier decision — Crisis {source.crisis_number}, {source.crisis_title}: '
                   f'{source.decision.choice_id} — {source.choice_title}. {selected.prerequisite.context}')
        crisis.briefing += '\n\n' + context
        for choice in crisis.choices: choice.consequence += '\n\n' + context
    return crisis


def initial_sequence(campaign: Campaign) -> list[Crisis]:
    # Reserve independent fallback content for every slot. Selection at each
    # acknowledged boundary may substitute an eligible follow-up. No future
    # content or branch effects are projected to a client.
    sequence = []
    for index in range(10):
        excluded = {c.id for c in sequence}
        available = campaign.model_copy(update={'scenarios':[s for s in campaign.scenarios if s.crisis.id not in excluded]})
        sequence.append(select_crisis(available, index, []))
    return sequence

