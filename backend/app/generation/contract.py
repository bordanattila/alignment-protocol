"""Versioned untrusted proposals reuse canonical Crisis/Choice/MetricDeltas."""
from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import json
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, StringConstraints, ValidationError, model_validator
from pydantic import BaseModel

from ..domain import Choice, Crisis, Metrics, MetricDeltas, Role

VERSION = '1.0'
MIN_EFFECT, MAX_EFFECT = -24, 18  # Observed extrema of the 30 authored crises.
MAX_CONTENT_BYTES = 65536
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=120)]
Narrative = Annotated[str, StringConstraints(strip_whitespace=True, min_length=80, max_length=2000)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=1000)]
Consequence = Annotated[str, StringConstraints(strip_whitespace=True, min_length=30, max_length=1200)]
Intelligence = Annotated[str, StringConstraints(strip_whitespace=True, min_length=40, max_length=1200)]
Effect = Annotated[int, Field(strict=True, ge=MIN_EFFECT, le=MAX_EFFECT)]
Identifier = Annotated[str, StringConstraints(pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$', max_length=128)]


class FailureCategory(StrEnum):
    DISABLED = 'disabled'
    CONFIGURATION = 'configuration'
    TIMEOUT = 'timeout'
    UNAVAILABLE = 'unavailable'
    AUTHENTICATION = 'authentication'
    RATE_LIMITED = 'rate_limited'
    UNSUPPORTED_RESPONSE = 'unsupported_response'
    INVALID_JSON = 'invalid_json'
    INVALID_SCHEMA = 'invalid_schema'
    INVALID_CONTINUITY = 'invalid_continuity'
    REFUSAL = 'refusal'
    UNEXPECTED = 'unexpected'


class GenerationError(Exception):
    def __init__(self, category: FailureCategory):
        self.category = FailureCategory(category)
        super().__init__(self.category.value)


def strict_json(text: str | bytes):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    def constant(_value):
        raise ValueError('Nonfinite JSON number')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


class FrozenMetrics(Metrics):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)


class DecisionContext(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)
    crisis_number: int = Field(ge=1, le=10)
    crisis_id: Identifier
    title: Title
    choice_id: Literal['A', 'B', 'C']
    choice_title: Title
    consequence: str = Field(min_length=1, max_length=600)


class GenerationContext(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)
    current_crisis_number: int = Field(ge=1, le=10)
    metrics: FrozenMetrics
    history: tuple[DecisionContext, ...] = Field(max_length=3)
    used_scenario_ids: tuple[Identifier, ...] = Field(max_length=10)


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)
    schema_version: Literal['1.0'] = VERSION
    context: GenerationContext


class ProposedEffects(MetricDeltas):
    infrastructure: Effect
    public_trust: Effect
    economy: Effect
    safety: Effect


class ProposedChoice(Choice):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: Annotated[str, StringConstraints(min_length=1, max_length=8)]
    title: Title
    description: Description
    consequence: Consequence
    metric_deltas: ProposedEffects


class ProposedCrisis(Crisis):
    model_config = ConfigDict(extra='forbid', strict=True)
    # A provider label is optional and untrusted; it is never used for identity.
    id: Identifier = 'unassigned'
    title: Title
    briefing: Narrative
    ai_recommendation_choice_id: Annotated[str, StringConstraints(min_length=1, max_length=8)]
    private_intelligence: dict[Role, Intelligence]
    choices: list[ProposedChoice] = Field(min_length=3, max_length=3)

    @model_validator(mode='before')
    @classmethod
    def normalize_options(cls, value):
        if not isinstance(value, dict): return value
        value = dict(value)
        if isinstance(value.get('choices'), list):
            choices = []
            for choice in value['choices']:
                choice = dict(choice) if isinstance(choice, dict) else choice
                if isinstance(choice, dict) and isinstance(choice.get('id'), str):
                    choice['id'] = choice['id'].strip().upper()
                choices.append(choice)
            value['choices'] = choices
        if isinstance(value.get('ai_recommendation_choice_id'), str):
            value['ai_recommendation_choice_id'] = value['ai_recommendation_choice_id'].strip().upper()
        return value

    @model_validator(mode='after')
    def strategic_options(self):
        if len({c.title.casefold() for c in self.choices}) != 3 or len({c.description.casefold() for c in self.choices}) != 3:
            raise ValueError('Options must be distinct')
        if len(set(self.private_intelligence.values())) != 4:
            raise ValueError('Intelligence must be role-specific')
        texts = [self.title, self.briefing, *self.private_intelligence.values()]
        texts.extend(text for choice in self.choices for text in (choice.title, choice.description, choice.consequence))
        if any((ord(char) < 32 and char not in '\n\t') or ord(char) == 127 for text in texts for char in text):
            raise ValueError('Control characters are not narrative text')
        for choice in self.choices:
            values = choice.metric_deltas.model_dump().values()
            if not any(v > 0 for v in values) or not any(v < 0 for v in values):
                raise ValueError('Each authored option has gains and costs')
            a = choice.metric_deltas.model_dump()
            for other in self.choices:
                b = other.metric_deltas.model_dump()
                if all(a[k] >= b[k] for k in a) and any(a[k] > b[k] for k in a):
                    raise ValueError('Dominated option')
        return self


class ContinuityReference(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)
    crisis_number: int = Field(ge=1, le=10)
    choice_id: Literal['A', 'B', 'C']


class CrisisProposal(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    schema_version: Literal['1.0']
    crisis: ProposedCrisis
    continuity_references: list[ContinuityReference] = Field(default_factory=list, max_length=3)


def proposal_schema() -> dict:
    """Strict structured-output schema, using the same Pydantic contract."""
    schema = CrisisProposal.model_json_schema()
    def visit(node):
        if isinstance(node, list):
            for child in node: visit(child)
        elif isinstance(node, dict):
            node.pop('default', None)
            if 'properties' in node:
                # Chat-compatible strict schemas require every property present;
                # optional continuity is expressed as an empty array.
                node['required'] = list(node['properties'])
                node['additionalProperties'] = False
                private = node['properties'].get('private_intelligence')
                if private is not None:
                    text = private['additionalProperties']
                    node['properties']['private_intelligence'] = {
                        'type': 'object', 'additionalProperties': False,
                        'properties': {role.value: dict(text) for role in Role},
                        'required': [role.value for role in Role],
                    }
            for child in node.values(): visit(child)
    visit(schema)
    return schema


@dataclass(frozen=True)
class AcceptedScenario:
    # Only immutable canonical bytes-as-text are kept. Mutable engine models are
    # fresh exports; editing an export cannot change the accepted consequences.
    canonical_json: str = field(repr=False)
    continuity_references: tuple[ContinuityReference, ...] = field(default=(), repr=False)

    @classmethod
    def from_crisis(cls, crisis: Crisis, references=()):
        validated = Crisis.model_validate_json(crisis.model_dump_json())
        return cls(canonical(validated.model_dump(mode='json')), tuple(references))

    def to_crisis(self) -> Crisis:
        return Crisis.model_validate_json(self.canonical_json)

    @property
    def fingerprint(self) -> str:
        material = self.canonical_json + canonical([r.model_dump() for r in self.continuity_references])
        return hashlib.sha256(material.encode()).hexdigest()


def accept_proposal(content: str, context: GenerationContext) -> AcceptedScenario:
    if not isinstance(content, str): raise GenerationError(FailureCategory.UNSUPPORTED_RESPONSE)
    try:
        if len(content.encode()) > MAX_CONTENT_BYTES: raise ValueError('Too large')
        parsed = strict_json(content)
    except (ValueError, UnicodeError, RecursionError):
        raise GenerationError(FailureCategory.INVALID_JSON) from None
    try:
        proposal = CrisisProposal.model_validate_json(json.dumps(parsed))
        known = {(r.crisis_number, r.choice_id) for r in context.history}
        references = sorted(proposal.continuity_references, key=lambda r:(r.crisis_number, r.choice_id))
        keys = [(r.crisis_number, r.choice_id) for r in references]
        if len(set(keys)) != len(keys) or any(key not in known for key in keys):
            raise GenerationError(FailureCategory.INVALID_CONTINUITY)
        data = proposal.crisis.model_dump(mode='json', exclude={'id'})
        data['choices'].sort(key=lambda choice:choice['id'])
        material = {'schema_version': VERSION, 'crisis': data,
                    'continuity_references': [r.model_dump() for r in references]}
        identifier = 'generated-' + hashlib.sha256(canonical(material).encode()).hexdigest()
        if identifier in context.used_scenario_ids:
            raise ValueError('Previously used content')
        crisis = Crisis.model_validate({**data, 'id': identifier})
        return AcceptedScenario.from_crisis(crisis, references)
    except (ValidationError, ValueError, TypeError, RecursionError):
        raise GenerationError(FailureCategory.INVALID_SCHEMA) from None
