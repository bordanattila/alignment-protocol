"""Summaries of existing sanitized diagnostic records; no content or model judge."""
from collections import Counter
from decimal import Decimal
import math
from statistics import median
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field
from ..domain import GenerationDiagnostic
from ..narrative_models import EndgameDiagnostic


class EvaluationRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')
    case_id: str = Field(pattern=r'^[a-z0-9-]{1,80}$')
    diagnostic: GenerationDiagnostic | EndgameDiagnostic


PROVIDER_ERRORS = {'authentication','rate_limited','quota_exceeded','model_unavailable','unsupported_format',
                   'invalid_provider_schema','unsupported_response','unavailable','refusal','unexpected'}
REJECTIONS = {'invalid_json','invalid_schema','invalid_continuity'}


def operation(record):
    return 'endgame' if isinstance(record.diagnostic,EndgameDiagnostic) else 'crisis'


def attempted(record):
    m=record.diagnostic.measurement
    return m.provider_attempted if m else None


def accepted(record):
    return record.diagnostic.source=='generated' and record.diagnostic.category=='success'


def fallback(record):
    return record.diagnostic.source in ('authored_fallback','deterministic_fallback')


def rate(numerator,denominator):
    return numerator/denominator if denominator else None


def distribution(values):
    values=sorted(values)
    return {'sample_count':len(values),'min':values[0] if values else None,
            'p50':round(median(values),6) if values else None,
            'p95':values[math.ceil(.95*len(values))-1] if values else None,
            'max':values[-1] if values else None}


def summarize(records):
    attempts=[r for r in records if attempted(r) is True]
    with_refs=[r for r in attempts if accepted(r) and r.diagnostic.measurement.reference_count is not None]
    history=[r for r in with_refs if r.diagnostic.measurement.history_available]
    fallback_records=[r for r in records if fallback(r)]
    result={
        'record_count':len(records),'provider_attempts':len(attempts),
        'not_attempted_count':sum(attempted(r) is False for r in records),
        'disabled_count':sum(r.diagnostic.category=='disabled' for r in records),
        'configuration_count':sum(r.diagnostic.category=='configuration' for r in records),
        'attempt_status_unknown_count':sum(attempted(r) is None for r in records),
        'accepted_count':sum(accepted(r) for r in records),
        'rejected_count':sum(str(r.diagnostic.category) in REJECTIONS for r in attempts),
        'fallback_count':len(fallback_records),
        'fallback_by_reason':dict(sorted(Counter(str(r.diagnostic.category) for r in fallback_records).items())),
        'fallback_rate_by_reason':{key:rate(value,len(records)) for key,value in sorted(Counter(str(r.diagnostic.category) for r in fallback_records).items())},
        'attempted_fallback_rate_by_reason':{key:rate(value,len(attempts)) for key,value in sorted(Counter(str(r.diagnostic.category) for r in attempts if fallback(r)).items())},
        'timeout_count':sum(r.diagnostic.category=='timeout' for r in attempts),
        'provider_error_count':sum(str(r.diagnostic.category) in PROVIDER_ERRORS for r in attempts),
        'schema_rejection_count':sum(r.diagnostic.category=='invalid_schema' for r in attempts),
        'historical_reference_rejection_count':sum(r.diagnostic.category=='invalid_continuity' for r in attempts),
        'objective_repetition_count':sum(bool(r.diagnostic.measurement.rejection_detail) for r in attempts),
        'accepted_rate':rate(sum(accepted(r) for r in attempts),len(attempts)),
        'rejection_rate':rate(sum(str(r.diagnostic.category) in REJECTIONS for r in attempts),len(attempts)),
        'attempted_fallback_rate':rate(sum(fallback(r) for r in attempts),len(attempts)),
        'outcome_fallback_rate':rate(len(fallback_records),len(records)),
        'rate_denominators':{'accepted_rate':'known provider attempts','rejection_rate':'known provider attempts',
            'attempted_fallback_rate':'known provider attempts','outcome_fallback_rate':'all supplied outcome records',
            'fallback_rate_by_reason':'all supplied outcome records','attempted_fallback_rate_by_reason':'known provider attempts'},
        'continuity':{'accepted_with_supported_references':sum(r.diagnostic.measurement.reference_count>0 for r in with_refs),
            'accepted_without_references':sum(r.diagnostic.measurement.reference_count==0 for r in with_refs),
            'accepted_with_history_sample_count':len(history),
            'explicit_reference_utilization_rate':rate(sum(r.diagnostic.measurement.reference_count>0 for r in history),len(history)),
            'utilization_denominator':'accepted known-attempt outputs with history and measured reference count',
            'semantic_consistency':'manual_review_required','meaningful_utilization':'manual_review_required'},
        'latency':{'total_generation_seconds':distribution([r.diagnostic.duration_seconds for r in records]),
            'timeout_total_seconds':distribution([r.diagnostic.duration_seconds for r in attempts if r.diagnostic.category=='timeout']),
            'fallback_total_seconds':distribution([r.diagnostic.duration_seconds for r in fallback_records])},
    }
    for field in ('provider_seconds','validation_seconds','fallback_seconds','availability_seconds'):
        result['latency'][field]=distribution([getattr(r.diagnostic.measurement,field) for r in records
            if r.diagnostic.measurement and getattr(r.diagnostic.measurement,field) is not None])
    result['usage']={}
    for field in ('input_tokens','output_tokens','total_tokens'):
        known=[getattr(r.diagnostic.measurement.usage,field) for r in attempts
               if r.diagnostic.measurement.usage and getattr(r.diagnostic.measurement.usage,field) is not None]
        result['usage'][field]={'known_sum':sum(known),'known_request_count':len(known),'unknown_request_count':len(attempts)-len(known)}
    models=Counter(r.diagnostic.measurement.model for r in attempts)
    result['configured_models']=[{'model':key,'known_attempts':value} for key,value in sorted(models.items(),key=lambda item:item[0] or '')]
    return result


def report(records):
    return {'all':summarize(records), **{op:summarize([r for r in records if operation(r)==op]) for op in ('crisis','endgame')},
        'coverage':'supplied outcome records only; production final-per-crisis records are not a full retry audit',
        'percentile_method':'nearest-rank p95; median p50; empty samples remain null',
        'timing_boundary':'provider_seconds measures the full adapter call, not network-only latency; availability is unknown'}


class Pricing(BaseModel):
    model_config = ConfigDict(extra='forbid')
    input_per_million: Annotated[Decimal,Field(ge=0,allow_inf_nan=False)]
    output_per_million: Annotated[Decimal,Field(ge=0,allow_inf_nan=False)]


def estimate_cost(records, prices: dict[str,Pricing], missions=1):
    if type(missions) is not int or missions<1:raise ValueError('Mission count must be positive')
    known={'crisis':[],'endgame':[]};unknown=0;unknown_attempts=0
    for record in records:
        if attempted(record) is None:unknown_attempts+=1;continue
        if not attempted(record):continue
        m=record.diagnostic.measurement;usage=m.usage;price=prices.get(m.model)
        if usage is None or usage.input_tokens is None or usage.output_tokens is None or price is None:
            unknown+=1;continue
        known[operation(record)].append((usage.input_tokens*price.input_per_million+usage.output_tokens*price.output_per_million)/Decimal(1_000_000))
    means={op:sum(values)/len(values) if values else None for op,values in known.items()}
    per_mission=10*means['crisis']+means['endgame'] if all(value is not None for value in means.values()) else None
    subtotal=sum((sum(values) for values in known.values()),Decimal(0))
    def amount(value):return str(value) if value is not None else None
    return {'known_request_count':sum(len(values) for values in known.values()),'unknown_cost_request_count':unknown,
        'unknown_attempt_count':unknown_attempts,'known_usage_subtotal':amount(subtotal),
        'complete_observed_batch_estimate':amount(subtotal) if not unknown and not unknown_attempts else None,
        'per_crisis_known_sample_mean':amount(means['crisis']),'per_endgame_known_sample_mean':amount(means['endgame']),
        'projected_ten_crisis_mission':amount(per_mission),
        'projected_repeated_missions':amount(per_mission*missions) if per_mission is not None else None,
        'missions':missions,'pricing':{model:price.model_dump(mode='json') for model,price in sorted(prices.items())},
        'assumptions':['Prices are operator-supplied currency units per million tokens; no current price is assumed.',
            'Known-usage means include rejected responses and fallbacks, not only accepted outputs.',
            'Projection assumes known samples represent future attempts: ten crisis requests plus one endgame request.',
            'Unknown usage can still be billable. This is a conditional projection, not a spending cap or provider invoice.',
            'Flat input/output rates do not model cached-token discounts, service tiers or retries.']}
