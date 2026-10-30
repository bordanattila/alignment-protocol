"""Prompt preference and structural continuity contrasts, without a semantic judge."""
import asyncio
import json
import subprocess
import sys

import httpx
import pytest

from app.domain import GenerationDiagnostic
from app.generation.config import GenerationSettings
from app.generation.contract import (GenerationContext, GenerationRequest, FrozenMetrics, GenerationError,
                                     accept_proposal, proposal_schema, reference_history)
from app.generation.evaluation import run_offline, result_document, review_template
from app.generation.evaluation_fixtures import (fixture, CONTINUITY_CASES, ContinuityFixtureProvider,
                                               SimulationClock, continuity_scenario, scenario)
from app.generation.evaluation_report import EvaluationRecord, report
from app.generation.provider import ChatCompletionsProvider, continuity_instructions
from app.generation.service import GenerationService
from app.crises import load_crisis_sequence

EXPECTED_REFS={'fresh-opening':0,'one-supported-reference':1,'multiple-supported-references':2,
    'relevant-without-reference':0,'invented-reference':None,'contradictory-prose':1,'superficial-reference':1,
    'develop-recorded-consequence':1,'interacting-decisions':2,'independent-emergency':0}


async def generate(case,name):
    request=fixture(name);clock=SimulationClock();provider=ContinuityFixtureProvider(clock,case)
    before=request.model_dump_json()
    outcome=await GenerationService(GenerationSettings(enabled=True,model='fixture-model-v1'),provider,
        lambda:load_crisis_sequence()[request.context.current_crisis_number-1],clock).generate(request)
    assert request.model_dump_json()==before and provider.calls==1
    return request,outcome


@pytest.mark.parametrize('format',['json_schema','json_object'])
@pytest.mark.parametrize('name',['fresh','infrastructure-damage','declining-trust','interconnected'])
def test_request_prefers_recorded_constraints_only_when_history_exists(format,name):
    request=fixture(name);captured=[]
    def handler(req):
        payload=json.loads(req.content);captured.append(payload)
        assert set(payload)=={'model','stream','messages','response_format'}
        assert payload['model']=='fixture-model-v1' and payload['stream'] is False
        prompt=payload['messages'][0]['content'];ctx=json.loads(payload['messages'][1]['content'])
        assert ctx==json.loads(request.model_dump_json())
        assert json.loads(prompt.split('\nJSON contract: ',1)[1])==proposal_schema(request.context)
        if name=='fresh':
            assert 'NO previous player decisions exist' in prompt and 'continuity_references: [] exactly' in prompt
            assert 'Prefer a crisis whose constraints' not in prompt
        else:
            for instruction in ('Prefer a crisis whose constraints or choices are materially shaped',
                'State that connection in the public briefing','not merely be named',
                "Distinguish a new emergency's cause from historical constraints",'use [] when no supported connection fits'):
                assert instruction in prompt
            assert 'A standalone crisis is always allowed' not in prompt
            for decision in reference_history(request.context):
                assert json.dumps({'crisis_number':decision.crisis_number,'choice_id':decision.choice_id}) in prompt
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':scenario(request)}}]})
    async def run():
        config=GenerationSettings(enabled=True,model='fixture-model-v1',endpoint='http://localhost/mock',require_api_key=False,response_format=format)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await ChatCompletionsProvider(config,client).generate(request)
    asyncio.run(run());assert len(captured)==1


@pytest.mark.parametrize('case,name',CONTINUITY_CASES)
def test_ten_structural_cases_and_explicit_reference_counts(case,name):
    request,outcome=asyncio.run(generate(case,name))
    assert outcome.measurement.history_available==bool(request.context.history)
    if case=='invented-reference':
        assert outcome.source=='authored' and outcome.failure=='invalid_continuity'
        assert outcome.measurement.reference_count is None
    else:
        assert outcome.source=='generated' and outcome.failure is None
        assert outcome.measurement.reference_count==EXPECTED_REFS[case]
        allowed={(d.crisis_number,d.choice_id) for d in reference_history(request.context)}
        assert all((r.crisis_number,r.choice_id) in allowed for r in outcome.snapshot.continuity_references)
    assert outcome.measurement.usage.total_tokens==1600


@pytest.mark.parametrize('case',['contradictory-prose','superficial-reference','relevant-without-reference'])
def test_structural_acceptance_does_not_become_a_semantic_quality_score(case):
    request,outcome=asyncio.run(generate(case,'interconnected'))
    record=EvaluationRecord(case_id=case,diagnostic=GenerationDiagnostic(crisis_number=request.context.current_crisis_number,
        source='generated',category='success',duration_seconds=outcome.duration_seconds,measurement=outcome.measurement))
    stats=report([record])['crisis']['continuity']
    assert stats['semantic_consistency']==stats['meaningful_utilization']=='manual_review_required'
    assert review_template([case])['cases'][0]['review_status']=='not_reviewed'
    assert all(score is None for score in review_template([case])['cases'][0]['scores'].values())


def test_wrong_executed_choice_and_outside_window_are_rejected():
    request=fixture('interconnected');raw=json.loads(continuity_scenario(request,'multiple-supported-references'))
    raw['continuity_references'][0]['choice_id']='A'  # actual water response was B
    with pytest.raises(GenerationError,match='invalid_continuity'):accept_proposal(json.dumps(raw),request.context)
    completed=fixture('victory').context.history[:9]
    metrics={key:70+sum(d.applied_deltas.model_dump()[key] for d in completed) for key in FrozenMetrics.model_fields}
    ctx=GenerationContext(current_crisis_number=10,metrics=FrozenMetrics(**metrics),history=completed[-3:],
        used_scenario_ids=tuple(d.crisis_id for d in completed))
    raw=json.loads(scenario(GenerationRequest(context=ctx)))
    old=completed[2];raw['continuity_references']=[{'crisis_number':old.crisis_number,'choice_id':old.choice_id}]
    # A real older decision in the exclusion list is not a visible reference entry.
    with pytest.raises(GenerationError,match='invalid_continuity'):accept_proposal(json.dumps(raw),ctx)


def test_contract_still_accepts_standalone_history_and_requires_empty_opening_refs():
    for name in ('fresh','interconnected'):
        request=fixture(name);schema=proposal_schema(request.context)['properties']['continuity_references']
        assert schema.get('minItems',0)==0
        assert accept_proposal(scenario(request),request.context).continuity_references==()
    fresh=fixture('fresh');bad=json.loads(scenario(fresh));bad['continuity_references']=[{'crisis_number':1,'choice_id':'A'}]
    with pytest.raises(GenerationError,match='invalid_continuity'):accept_proposal(json.dumps(bad),fresh.context)


def test_fallback_for_bad_reference_is_repeatable_without_state_mutation():
    async def run():
        request,a=await generate('invented-reference','interconnected')
        _,b=await generate('invented-reference','interconnected')
        assert a.snapshot.canonical_json==b.snapshot.canonical_json
    asyncio.run(run())


def test_extended_evaluator_is_opt_in_reproducible_private_and_keeps_base_accounting(monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('Real adapter must not be used')
    monkeypatch.setattr(ChatCompletionsProvider,'generate',forbidden)
    base=asyncio.run(run_offline());a=asyncio.run(run_offline(include_continuity=True));b=asyncio.run(run_offline(include_continuity=True))
    assert len(base)==29 and len(a)==39
    assert [r.model_dump(mode='json') for r in a[:29]]==[r.model_dump(mode='json') for r in base]
    assert [r.model_dump(mode='json') for r in a]==[r.model_dump(mode='json') for r in b]
    summary=report(a)['all']
    assert summary['provider_attempts']==37 and summary['accepted_count']==23 and summary['fallback_count']==16
    text=json.dumps(result_document(a,'offline-simulation'))
    assert 'private_intelligence' not in text and 'Fixture Host' not in text and 'briefing' not in text


def test_extended_cli_outputs_measured_structure_and_unreviewed_human_sheet(tmp_path):
    target=tmp_path/'result.json';sheet=tmp_path/'review.json'
    subprocess.run([sys.executable,'-m','app.generation.evaluation','--continuity-cases','--output',str(target),
                    '--review-template',str(sheet)],check=True,capture_output=True,text=True)
    data=json.loads(target.read_text());assert len(data['records'])==39
    assert data['manual_review_status']=='not_reviewed'
    assert all(r['review_status']=='not_reviewed' for r in json.loads(sheet.read_text())['cases'])


@pytest.mark.parametrize('count',[2,3,4])
def test_ai_advice_is_common_through_consensus_but_does_not_override_a_plurality(count):
    from test_milestone3 import setup, expire, cast
    from app.domain import Phase
    store,mission,clock=setup(count);ai=mission.crisis.ai_recommendation_choice_id
    def check():
        for p in mission.players:
            frame=store.project(mission.token,p.id)
            assert frame['crisis']['ai_recommendation_choice_id']==ai
            assert set(frame['private_intelligence'])==set(p.roles)
            assert all(text not in json.dumps(frame) for role,text in mission.crisis.private_intelligence.items() if role not in p.roles)
    check();expire(store,mission,clock);check()
    cast(store,mission,{2:['A','B'],3:['A','B','C'],4:['A','B','A','B']}[count])
    assert mission.phase==Phase.CONSENSUS_WINDOW;check()
    expire(store,mission,clock);assert mission.rounds[-1].number==2;check()
    other='B' if ai!='B' else 'C';cast(store,mission,[other]*count)
    assert mission.decision.choice_id==other and not mission.decision.ai_followed
    check()
    assert all(store.project(mission.token,p.id)['history'][0]['ai_recommendation_choice_id']==ai for p in mission.players)
