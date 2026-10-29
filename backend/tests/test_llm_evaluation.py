"""Evaluation accounting, privacy, actual adapter usage and reproducible offline runs."""
import asyncio
import hashlib
import json
import sqlite3
import subprocess
import sys

import httpx
import pytest
from pydantic import ValidationError

from app.domain import GenerationDiagnostic
from app.generation.config import GenerationSettings
from app.generation.contract import GenerationRequest
from app.generation.evaluation import run_offline, result_document, review_template
from app.generation.evaluation_fixtures import fixture, HISTORIES
from app.generation.evaluation_report import EvaluationRecord, Pricing, report, estimate_cost, distribution
from app.generation.measurement import TokenUsage, GenerationTrace, GenerationMeasurement, extract_usage
from app.generation.provider import ChatCompletionsProvider
from app.generation.service import GenerationService
from app.missions import MissionStore
from app.persistence import SQLiteMissions, canonical
from test_generation_contract import context
from test_generation_provider import settings, fallback, wire
from test_live_generation import setup, launch, settle
from test_adaptive_narrative import completed, coordinator, StoryProvider
from test_persistence import ready, voting, votes


def offline():return asyncio.run(run_offline())


def test_offline_counts_reasons_denominators_and_endgame_breakdown():
    records=offline();r=report(records);all=r['all']
    assert all['record_count']==29 and all['provider_attempts']==27
    assert all['not_attempted_count']==2 and all['attempt_status_unknown_count']==0
    assert all['accepted_count']==14 and all['fallback_count']==15 and all['rejected_count']==9
    assert all['fallback_by_reason']=={'disabled':2,'invalid_continuity':2,'invalid_json':1,'invalid_schema':6,'timeout':2,'unavailable':2}
    assert all['schema_rejection_count']==6 and all['historical_reference_rejection_count']==2
    assert all['objective_repetition_count']==4 and all['timeout_count']==2 and all['provider_error_count']==2
    assert all['accepted_rate']==14/27 and all['attempted_fallback_rate']==13/27
    assert all['disabled_count']==2
    assert all['attempted_fallback_rate_by_reason']['invalid_schema']==6/27
    assert all['usage']['input_tokens']=={'known_sum':22000,'known_request_count':22,'unknown_request_count':5}
    assert r['endgame']['record_count']==7 and r['endgame']['accepted_count']==2
    assert r['crisis']['record_count']==22 and r['crisis']['accepted_count']==12


def test_validity_does_not_imply_utilization_or_semantic_truth():
    r=report(offline())['crisis']['continuity']
    assert r['accepted_with_supported_references']==5 and r['accepted_without_references']==7
    assert r['explicit_reference_utilization_rate']==5/11
    assert r['meaningful_utilization']==r['semantic_consistency']=='manual_review_required'
    assert r['accepted_with_history_sample_count']==11


def test_legacy_unknown_attempts_are_not_success_denominators():
    old=GenerationDiagnostic(crisis_number=1,source='authored_fallback',category='timeout',duration_seconds=60.0)
    r=report([EvaluationRecord(case_id='legacy',diagnostic=old)])['all']
    assert r['provider_attempts']==0 and r['attempt_status_unknown_count']==1
    assert r['accepted_rate'] is None and r['attempted_fallback_rate'] is None
    assert r['fallback_count']==1 and r['outcome_fallback_rate']==1
    assert r['latency']['provider_seconds']['sample_count']==0


@pytest.mark.parametrize('values,expected',[
    ([],{'sample_count':0,'min':None,'p50':None,'p95':None,'max':None}),
    ([9],{'sample_count':1,'min':9,'p50':9,'p95':9,'max':9}),
    (list(range(1,21)),{'sample_count':20,'min':1,'p50':10.5,'p95':19,'max':20}),
])
def test_documented_latency_percentiles(values,expected):assert distribution(values)==expected


@pytest.mark.parametrize('raw',[
    None,{},[],{'prompt_tokens':True}, {'prompt_tokens':-1}, {'completion_tokens':'PRIVATE'},
    {'prompt_tokens':100,'completion_tokens':50,'total_tokens':99}, {'prompt_tokens':100,'total_tokens':2},
    {'prompt_tokens':1_000_000_001},
])
def test_missing_unreliable_usage_is_unknown_and_never_repaired(raw):assert extract_usage(raw) is None


def test_partial_usage_retains_unknowns_and_ignores_unrelated_provider_fields():
    u=extract_usage({'prompt_tokens':100,'model':'PRIVATE','prompt':'PRIVATE'})
    assert u.input_tokens==100 and u.output_tokens is None and u.total_tokens is None
    assert 'PRIVATE' not in u.model_dump_json()


@pytest.mark.parametrize('content,expected',[('valid','success'),('invalid','invalid_schema'),('refusal','refusal')])
def test_actual_adapter_usage_survives_accepted_and_rejected_responses(content,expected):
    async def run():
        payload=wire() if content=='valid' else wire('{"invalid":true}')
        payload['usage']={'prompt_tokens':100,'completion_tokens':50,'total_tokens':150,'private':'PRIVATE'}
        if content=='refusal':payload['choices'][0]['message']['refusal']='PRIVATE refusal message'
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,json=payload))) as client:
            config=settings();outcome=await GenerationService(config,ChatCompletionsProvider(config,client),fallback()).generate(GenerationRequest(context=context()))
        assert (outcome.failure or 'success')==expected
        m=outcome.measurement
        assert m.usage==TokenUsage(input_tokens=100,output_tokens=50,total_tokens=150)
        assert m.provider_attempted and m.provider_seconds>=0
        assert m.validation_seconds is not None if content!='refusal' else m.validation_seconds is None
        assert 'PRIVATE' not in m.model_dump_json()
    asyncio.run(run())


def test_configuration_failure_is_not_a_provider_attempt():
    async def run():
        config=GenerationSettings(enabled=True)
        outcome=await GenerationService(config,fallback=fallback()).generate(GenerationRequest(context=context()))
        assert outcome.failure=='configuration' and not outcome.measurement.provider_attempted
        assert outcome.measurement.provider_seconds is None and outcome.measurement.validation_seconds is None
    asyncio.run(run())


def test_scripted_timing_boundaries_and_unknown_delivery_time():
    records=offline()
    valid=next(r.diagnostic for r in records if r.case_id=='fresh-valid')
    timeout=next(r.diagnostic for r in records if r.case_id=='resolved-timeout')
    assert valid.measurement.provider_seconds==.201 and valid.measurement.validation_seconds==.001
    assert timeout.measurement.provider_seconds==60.001 and timeout.measurement.validation_seconds is None
    assert timeout.measurement.fallback_seconds==.001
    assert valid.measurement.availability_seconds is None
    assert valid.duration_seconds>=valid.measurement.provider_seconds+valid.measurement.validation_seconds


def test_cost_includes_rejected_usage_and_unknown_fallback_is_not_free():
    records=offline();prices={'fixture-model-v1':Pricing(input_per_million='1',output_per_million='2')}
    cost=estimate_cost(records,prices,missions=3)
    assert cost['known_request_count']==22 and cost['unknown_cost_request_count']==5
    assert cost['known_usage_subtotal']=='0.0484'
    assert cost['complete_observed_batch_estimate'] is None
    assert cost['per_crisis_known_sample_mean']=='0.0022'
    assert cost['per_endgame_known_sample_mean']=='0.0022'
    assert cost['projected_ten_crisis_mission']=='0.0242' and cost['projected_repeated_missions']=='0.0726'
    assert estimate_cost(records,{})['projected_ten_crisis_mission'] is None


@pytest.mark.parametrize('rate',['-1','NaN','Infinity','private text'])
def test_invalid_pricing_rejected(rate):
    with pytest.raises(ValidationError):Pricing(input_per_million=rate,output_per_million='1')


def test_pricing_matches_model_and_partial_usage_is_not_complete_cost():
    records=offline();assert estimate_cost(records,{'different-model':Pricing(input_per_million=1,output_per_million=2)})['known_request_count']==0
    old=EvaluationRecord(case_id='old',diagnostic=GenerationDiagnostic(crisis_number=1,source='generated',category='success',duration_seconds=1.0))
    assert estimate_cost([old],{})['unknown_attempt_count']==1
    with pytest.raises(ValueError):estimate_cost(records,{},missions=0)


def test_reproducible_offline_results_need_no_credentials_or_provider(monkeypatch):
    import app.generation.provider as provider
    def forbidden(*args,**kwargs):raise AssertionError('Network or environment access forbidden')
    monkeypatch.setattr(provider.ChatCompletionsProvider,'generate',forbidden)
    monkeypatch.setattr(GenerationSettings,'from_env',forbidden)
    monkeypatch.setenv('CONSENSUS_LLM_API_KEY','PRIVATE-API-KEY-CANARY')
    a=result_document(offline(),'offline-simulation');b=result_document(offline(),'offline-simulation')
    assert canonical(a)==canonical(b)
    text=json.dumps(a)
    for secret in ('PRIVATE-API-KEY-CANARY','Fixture Host','private_intelligence','briefing','consequence','credential','prompt'):
        assert secret not in text
    assert a['cost'] is None and a['manual_review_status']=='not_reviewed'


def test_all_six_history_fixtures_are_distinct_production_contexts():
    contexts={name:fixture(name).context for name in HISTORIES}
    assert not contexts['fresh'].history
    assert contexts['infrastructure-damage'].metrics.infrastructure<70
    assert contexts['declining-trust'].metrics.public_trust<70
    assert all(ctx.history for name,ctx in contexts.items() if name!='fresh')
    assert len({ctx.model_dump_json() for ctx in contexts.values()})==6


def test_review_template_has_defined_anchors_and_no_automatic_semantic_scores():
    sheet=review_template(['fixture-one'])
    assert len(sheet['anchors'])==9
    assert all(set(scale)=={'1','2','3','4','5'} for scale in sheet['anchors'].values())
    assert all(value is None for value in sheet['cases'][0]['scores'].values())
    assert sheet['cases'][0]['notes']=='' and sheet['cases'][0]['review_status']=='not_reviewed'


def test_measurements_persist_without_gameplay_exposure_and_old_records_load_unchanged(tmp_path):
    async def run():
        path=tmp_path/'measurement.sqlite3';store,mission,credentials,clock,live=setup(path)
        await launch(live);await settle(live)
        assert mission.generation_diagnostics[0].measurement.provider_attempted
        assert 'measurement' not in json.dumps(store.project(mission.token,mission.host_id))
        token=mission.token;await live.close();store.close()
        # Model a real legacy record; same accepted crisis and immutable result hashes.
        with sqlite3.connect(path) as db:
            raw=json.loads(db.execute('SELECT payload FROM missions').fetchone()[0])
            for record in raw['generation_diagnostics']:record.pop('measurement',None)
            old=list(raw['generation_diagnostics']);text=canonical(raw)
            db.execute('UPDATE missions SET payload=?,checksum=?',(text,hashlib.sha256(text.encode()).hexdigest()))
        restored=MissionStore(clock,persistence=SQLiteMissions(path));restored.initialize()
        m=restored.get(token)
        assert m.generation_diagnostics[0].measurement is None
        assert [r.model_dump(mode='json') for r in m.generation_diagnostics]==old
        restored.close()
    asyncio.run(run())


def test_pending_endgame_does_not_block_another_missions_timers_votes_or_reconnect():
    async def run():
        store,mission,credentials,clock,live=await completed()
        provider=StoryProvider(held=True);end=coordinator(store,live,provider)
        await launch(end);await provider.entered.wait()
        other,host=store.create('Other Host');guest=store.join(other.token,'Other Guest')[1]
        ready(store,other);store.start(other.token,host.credential)
        voting(store,other,[host.credential,guest.credential],clock)
        votes(store,other,[host.credential,guest.credential],['A','A'])
        assert other.results and other.metrics!=other.initial_metrics
        p=mission.players[1];before=list(p.roles)
        store.set_connected(mission.token,p.id,False);store.set_connected(mission.token,p.id,True)
        assert p.roles==before and store.project(mission.token,p.id)['summary']['conclusion']['status']=='pending'
        assert not provider.release.is_set()
        provider.release.set();await settle(end)
        assert mission.conclusion.diagnostic.measurement.operation=='endgame'
        await end.close();await live.close();store.close()
    asyncio.run(run())


def test_offline_cli_produces_sanitized_json_review_sheet_and_summary(tmp_path):
    output=tmp_path/'result.json';review=tmp_path/'review.json'
    result=subprocess.run([sys.executable,'-m','app.generation.evaluation','--output',str(output),
                           '--review-template',str(review)],capture_output=True,text=True,check=True)
    assert '27 known attempts' in result.stdout and not result.stderr
    data=json.loads(output.read_text());assert data['schema_version']=='evaluation-1.0'
    assert data['summary']['all']['record_count']==29
    assert json.loads(review.read_text())['version']=='review-1.0'


def test_private_measurement_fields_are_bounded_and_configuration_key_cannot_become_model_metadata():
    from pydantic import SecretStr
    config=GenerationSettings(model='secret-key-canary',api_key=SecretStr('secret-key-canary'))
    assert GenerationTrace(config,'crisis',False).measurement().model is None
    with pytest.raises(ValidationError):TokenUsage(input_tokens=1,prompt='PRIVATE')
    with pytest.raises(ValidationError):GenerationMeasurement(operation='crisis',provider_attempted=True,history_available=False,response='PRIVATE')


def test_legacy_finalized_endgame_diagnostic_is_unchanged_after_restart(tmp_path):
    async def run():
        path=tmp_path/'legacy-story.sqlite3';store,mission,credentials,clock,live=await completed(path)
        end=coordinator(store,live,StoryProvider());await launch(end);await settle(end)
        token=mission.token;await end.close();await live.close();store.close()
        with sqlite3.connect(path) as db:
            raw=json.loads(db.execute('SELECT payload FROM missions').fetchone()[0])
            raw['conclusion']['diagnostic'].pop('measurement',None)
            for record in raw['generation_diagnostics']:record.pop('measurement',None)
            old=raw['conclusion'];text=canonical(raw)
            db.execute('UPDATE missions SET payload=?,checksum=?',(text,hashlib.sha256(text.encode()).hexdigest()))
        restored=MissionStore(clock,persistence=SQLiteMissions(path));restored.initialize()
        assert restored.get(token).conclusion.model_dump(mode='json')==old
        restored.close()
    asyncio.run(run())


def test_operator_evaluation_refuses_to_overwrite_database(tmp_path):
    path=tmp_path/'state.sqlite3';path.write_bytes(b'unchanged private database')
    result=subprocess.run([sys.executable,'-m','app.generation.evaluation','--database',str(path),
        '--output',str(path)],capture_output=True,text=True)
    assert result.returncode==1 and path.read_bytes()==b'unchanged private database'
    assert 'unchanged private' not in result.stderr
