"""Offline evaluation by default. This command has no live-provider mode."""
import argparse
import asyncio
import json
import logging
from pathlib import Path
import sqlite3
import sys

from pydantic import ValidationError
from ..crises import load_crisis_sequence
from ..domain import GenerationDiagnostic
from .config import GenerationSettings
from .service import GenerationService
from .contract import accept_proposal
from .conclusion_live import generate_conclusion
from .evaluation_fixtures import (HISTORIES, fixture, FixtureProvider, SimulationClock, scenario,
                                  CONTINUITY_CASES, ContinuityFixtureProvider)
from .evaluation_report import EvaluationRecord, Pricing, report, estimate_cost
from .inspect_diagnostics import inspect

CRITERIA={
    'clarity':['Situation and decision are incomprehensible','Major ambiguities impede choice','Understandable with minor gaps','Clear constraints and choices','Immediately clear, concise and well contextualized'],
    'plausibility':['Incompatible with civic setting or known events','Major unexplained leaps','Mostly plausible with some gaps','Credible constraints and mechanisms','Convincing civic situation grounded in established events'],
    'distinctiveness':['Essentially repeats an earlier crisis','Mostly a renamed repeat','Some novelty but familiar structure','Clearly different pressure or tradeoff','Fresh challenge that develops the mission without repetition'],
    'tradeoffs':['One obvious or identical choice','Weak or cosmetic differences','Real gains and costs with uneven options','Three credible strategically distinct options','Three compelling competing strategies with no obvious universal answer'],
    'metric_relevance':['Contradicts current conditions','Mostly ignores current strengths and costs','Some relevant pressures','Choices reflect current strengths and weaknesses','Specific and coherent use of actual metric trajectory'],
    'consequence_coherence':['Outcomes contradict choices or recorded facts','Major causal gaps','Mostly coherent with minor gaps','Clear causal costs and benefits','Precise causal outcomes consistent with established facts'],
    'role_relevance':['Roles irrelevant or private information leaked publicly','Mostly redundant intelligence','Some useful differences','Each role contributes useful distinct perspective','Distinct role perspectives materially change strategic assessment without leakage'],
    'historical_continuity':['Invents or contradicts completed decisions','Superficial or misleading linkage','Valid but standalone or weakly connected','Meaningful use of an actual decision and consequence','Strong coherent development of actual decisions without forced sequels'],
    'engagement':['Confusing or uninteresting','Little reason to discuss','Adequate civic stakes','Engaging stakes and productive disagreement','Memorable stakes and sustained cooperative deliberation'],
}


def review_template(case_ids):
    return {'version':'review-1.0','instructions':'Human judgments, not verified properties. Review in game against public history. Do not copy private intelligence, chat, identities, credentials or provider errors into notes.',
        'anchors':{key:{str(i+1):text for i,text in enumerate(values)} for key,values in CRITERIA.items()},
        'cases':[{'case_id':key,'scores':{criterion:None for criterion in CRITERIA},'notes':'','review_status':'not_reviewed'} for key in case_ids]}


async def run_offline(*, include_continuity=False):
    records=[]
    cases=[(name,'valid') for name in HISTORIES]+[(name,'linked') for name in HISTORIES if name!='fresh']
    cases += [('resolved',mode) for mode in ('schema','malformed','provider-error','timeout','invented','repeated-title','repeated-content','duplicate-choice-text','identical-effects','missing-usage','disabled')]
    for name,mode in cases:
        request=fixture(name);clock=SimulationClock();provider=FixtureProvider(clock,mode)
        if mode=='repeated-content':
            previous=accept_proposal(scenario(request),request.context).to_crisis().id
            request=request.model_copy(update={'context':request.context.model_copy(update={
                'used_scenario_ids':request.context.used_scenario_ids+(previous,)})})
        config=GenerationSettings(enabled=mode!='disabled',model='fixture-model-v1',timeout_seconds=60)
        fallback=lambda:load_crisis_sequence()[request.context.current_crisis_number-1]
        outcome=await GenerationService(config,provider,fallback,clock).generate(request)
        diagnostic=GenerationDiagnostic(crisis_number=request.context.current_crisis_number,
            source='generated' if outcome.source=='generated' else 'authored_fallback' if outcome.snapshot else None,
            category=outcome.failure or 'success',duration_seconds=outcome.duration_seconds,
            http_status=outcome.http_status,measurement=outcome.measurement)
        assert provider.calls==(0 if mode=='disabled' else 1)
        records.append(EvaluationRecord(case_id=f'{name}-{mode}',diagnostic=diagnostic))
    for name,mode in [('victory','valid'),('defeat','valid'),('victory','provider-error'),('victory','timeout'),('defeat','invented'),('victory','schema'),('victory','disabled')]:
        request=fixture(name);clock=SimulationClock();provider=FixtureProvider(clock,mode)
        config=GenerationSettings(enabled=mode!='disabled',model='fixture-model-v1',timeout_seconds=60)
        outcome=await generate_conclusion(config,provider,request,clock)
        assert provider.calls==(0 if mode=='disabled' else 1)
        records.append(EvaluationRecord(case_id=f'endgame-{name}-{mode}',diagnostic=outcome.diagnostic))
    if include_continuity:
        for case,name in CONTINUITY_CASES:
            request=fixture(name);clock=SimulationClock();provider=ContinuityFixtureProvider(clock,case)
            config=GenerationSettings(enabled=True,model='fixture-model-v1',timeout_seconds=60)
            selector=lambda:load_crisis_sequence()[request.context.current_crisis_number-1]
            outcome=await GenerationService(config,provider,selector,clock).generate(request)
            diagnostic=GenerationDiagnostic(crisis_number=request.context.current_crisis_number,
                source='generated' if outcome.source=='generated' else 'authored_fallback',category=outcome.failure or 'success',
                duration_seconds=outcome.duration_seconds,http_status=outcome.http_status,measurement=outcome.measurement)
            assert provider.calls==1
            records.append(EvaluationRecord(case_id='continuity-'+case,diagnostic=diagnostic))
    return records


def result_document(records,evidence_mode,prices=None,missions=1):
    return {'schema_version':'evaluation-1.0','evidence_mode':evidence_mode,
        'timings_and_usage':('scripted monotonic seconds and synthetic tokens; not real-provider performance or cost' if evidence_mode=='offline-simulation' else
                            'operator diagnostic measurements; missing historical fields remain unknown'),
        'records':[r.model_dump(mode='json') for r in records],'summary':report(records),
        'cost':estimate_cost(records,prices,missions) if prices is not None else None,
        'manual_review_status':'not_reviewed'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,help='Machine-readable sanitized JSON')
    parser.add_argument('--review-template',type=Path)
    parser.add_argument('--database',type=Path,help='Explicit opt-in read-only operator database; never mutated')
    parser.add_argument('--mission-index',type=int,default=1)
    parser.add_argument('--pricing',type=Path,help='Explicit model -> input_per_million/output_per_million JSON')
    parser.add_argument('--missions',type=int,default=1)
    parser.add_argument('--continuity-cases',action='store_true',help='Add ten scripted contrasts; semantic ratings remain human review')
    args=parser.parse_args()
    logging.getLogger('app.generation').setLevel(logging.CRITICAL)
    try:
        if args.missions<1:raise ValueError('Invalid mission count')
        if args.database and args.continuity_cases:raise ValueError('Fixture contrasts cannot be mixed with operator records')
        if args.database:
            protected=[args.database]+[Path(str(args.database)+suffix) for suffix in ('-wal','-shm','.lock')]
            for target in (args.output,args.review_template):
                if target and any(target.resolve()==path.resolve() or (target.exists() and path.exists() and target.samefile(path)) for path in protected):
                    raise ValueError('Output must not overwrite the database or its sidecars')
        if args.database:
            records=[EvaluationRecord(case_id=f'crisis-{raw["crisis_number"]}',diagnostic=GenerationDiagnostic.model_validate(raw)) for raw in inspect(args.database,args.mission_index)]
            from ..narrative_models import EndgameDiagnostic
            records += [EvaluationRecord(case_id='endgame',diagnostic=EndgameDiagnostic.model_validate(raw)) for raw in inspect(args.database,args.mission_index,'endgame')]
        else:records=asyncio.run(run_offline(include_continuity=args.continuity_cases))
        prices=None
        if args.pricing:
            raw=json.loads(args.pricing.read_text());prices={model:Pricing.model_validate(value) for model,value in raw.items()}
        document=result_document(records,'operator-records' if args.database else 'offline-simulation',prices,args.missions)
        if args.output:args.output.write_text(json.dumps(document,sort_keys=True,indent=2)+'\n')
        if args.review_template:args.review_template.write_text(json.dumps(review_template([r.case_id for r in records]),sort_keys=True,indent=2)+'\n')
        summary=document['summary']['all']
        print(f'{document["evidence_mode"]}: {summary["record_count"]} outcomes; {summary["provider_attempts"]} known attempts; '
              f'{summary["accepted_count"]} accepted; {summary["fallback_count"]} fallbacks; '
              f'{summary["attempt_status_unknown_count"]} unknown attempts. Semantic quality requires human review.')
        if not args.output:print(json.dumps(document,sort_keys=True,indent=2))
    except (OSError,sqlite3.Error,ValueError,TypeError,AttributeError,ValidationError):
        print('Evaluation unavailable: check fixture, database, pricing and output arguments.',file=sys.stderr)
        raise SystemExit(1) from None


if __name__=='__main__':main()
