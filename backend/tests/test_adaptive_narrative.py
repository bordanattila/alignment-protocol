"""Offline narrative memory, strict output, durable lifecycle and operator boundary."""
import asyncio
import hashlib
import json
import sqlite3

import httpx
import pytest

from app.domain import Phase, Metrics
from app.missions import MissionStore
from app.persistence import SQLiteMissions, PersistenceError, canonical
from app.narrative_models import EndgameDiagnostic
from app.generation.config import GenerationSettings
from app.generation.context import build_context
from app.generation.contract import accept_proposal, proposal_schema, GenerationError, FailureCategory, reference_history
from app.generation.endgame import build_endgame_request, accept_endgame, endgame_schema, basis_hash
from app.generation.conclusion_live import LiveConclusions, generate_conclusion
from app.generation.provider import ChatCompletionsProvider, ProviderResponse
from app.generation.inspect_diagnostics import inspect
from test_generation_contract import proposal
from test_generation_provider import wire
from test_live_generation import setup, launch, settle, ProgressiveProvider
from test_persistence import voting, votes, ready


def story(request):
    history=request.context.history
    return {'schema_version':'endgame-1.0',
        'journey':{'text':'The city repeatedly weighed shared services against the burdens of keeping them running.',
                   'references':[history[0].crisis_number,history[-1].crisis_number] if len(history)>1 else [1]},
        'cost':{'text':'Each recorded response carried a cost as well as a gain. The final balance reflects those choices.',
                'references':[history[-1].crisis_number]},
        'standing':{'text':('The city survived, with a civic future shaped by the tradeoffs its team accepted.' if request.context.outcome=='victory' else
                           'The city collapsed. Its recorded responses explain the losses without erasing the attempts to protect it.'),
                    'references':[history[-1].crisis_number]}}


class StoryProvider:
    def __init__(self,failure=None,held=False):
        self.requests=[];self.failure=failure;self.entered=asyncio.Event();self.release=asyncio.Event()
        if not held:self.release.set()
    async def generate(self,request):
        self.requests.append(request);self.entered.set();await self.release.wait()
        if isinstance(self.failure,FailureCategory):raise GenerationError(self.failure,503)
        raw=story(request)
        if self.failure=='reference':raw['journey']['references']=[99]
        if self.failure=='schema':raw['score']=100
        return ProviderResponse(json.dumps(raw),200)


async def completed(path=None,early=False):
    store,mission,credentials,clock,live=setup(path)
    if early:mission.metrics=Metrics(infrastructure=70,public_trust=1,economy=70,safety=70);mission.initial_metrics=mission.metrics.model_copy()
    for _ in range(1 if early else 10):
        await launch(live);await settle(live)
        voting(store,mission,credentials,clock);votes(store,mission,credentials,['A']*3)
        if mission.phase!=Phase.FAILED:store.continue_mission(mission.token,credentials[0],mission.results[-1].id)
    assert mission.phase==(Phase.FAILED if early else Phase.COMPLETED)
    return store,mission,credentials,clock,live


def coordinator(store,live,provider,timeout=1):
    return LiveConclusions(store,live.lock,live.connections,GenerationSettings(enabled=True,timeout_seconds=timeout),provider)


def test_empty_and_progressive_memory_is_factual_bounded_and_keeps_important_earlier_decisions():
    async def run():
        store,mission,credentials,clock,live=setup()
        initial=build_context(mission)
        assert not initial.history and not initial.narrative_memory.established_events
        assert not initial.narrative_memory.open_pressures and not initial.narrative_memory.recurring_costs
        for number in range(1,10):
            await launch(live);await settle(live)
            request=live.provider.requests[-1];ctx=request.context
            assert len(ctx.history)<=3 and len(ctx.narrative_memory.significant_earlier_decisions)<=2
            assert len(ctx.model_dump_json().encode())<16000
            for decision in reference_history(ctx):
                recorded=mission.results[decision.crisis_number-1]
                assert decision.crisis_id==recorded.crisis_id and decision.choice_id==recorded.decision.choice_id
                assert decision.applied_deltas.model_dump()==recorded.applied_deltas.model_dump()
                assert decision.consequence==recorded.outcome[:600]
            for event in ctx.narrative_memory.established_events:
                assert event.situation==mission.results[event.crisis_number-1].briefing[:300]
            for pressure in ctx.narrative_memory.open_pressures:
                assert pressure.current_value==mission.metrics.model_dump()[pressure.metric]
                assert pressure.change_since_start==pressure.current_value-70
                assert all(mission.results[n-1].applied_deltas.model_dump()[pressure.metric]<0 for n in pressure.contributing_decisions)
            voting(store,mission,credentials,clock);votes(store,mission,credentials,['A']*3)
            store.continue_mission(mission.token,credentials[0],mission.results[-1].id)
        ctx=build_context(mission)
        assert [r.crisis_number for r in ctx.history]==[7,8,9]
        assert [r.crisis_number for r in ctx.narrative_memory.significant_earlier_decisions]==[1,2]
        raw=proposal();raw['continuity_references']=[{'crisis_number':1,'choice_id':'A'}]
        assert accept_proposal(json.dumps(raw),ctx).continuity_references
        raw['continuity_references'][0]['choice_id']='B'
        with pytest.raises(GenerationError,match='invalid_continuity'):accept_proposal(json.dumps(raw),ctx)
        assert proposal_schema(ctx)['properties']['continuity_references']['maxItems']==3
        await live.close();store.close()
    asyncio.run(run())


@pytest.mark.parametrize('kind',['repeated_title','identical_effects'])
def test_objective_narrative_repetition_is_rejected_without_keyword_filters(kind):
    async def run():
        store,mission,credentials,clock,live=setup();await launch(live);await settle(live)
        voting(store,mission,credentials,clock);votes(store,mission,credentials,['A']*3)
        store.continue_mission(mission.token,credentials[0],mission.results[-1].id)
        raw=proposal()
        if kind=='repeated_title':raw['crisis']['title']='  '+mission.results[0].crisis_title.upper()+' '
        else:raw['crisis']['choices'][1]['metric_deltas']=raw['crisis']['choices'][0]['metric_deltas']
        with pytest.raises(GenerationError,match='invalid_schema'):accept_proposal(json.dumps(raw),build_context(mission))
        await live.close();store.close()
    asyncio.run(run())


@pytest.mark.parametrize('early',[False,True])
def test_endgame_context_and_generated_story_use_finalized_public_facts(tmp_path,early):
    async def run():
        store,mission,credentials,clock,live=await completed(tmp_path/'story.sqlite3',early)
        state=mission.conclusion;assert state.status=='pending'
        request=build_endgame_request(mission)
        assert request.context.crises_completed==len(mission.results)
        assert request.context.final_metrics.model_dump()==mission.metrics.model_dump()
        assert request.context.consensus_score==sum(mission.metrics.model_dump().values())/4
        assert request.context.outcome==('defeat' if early else 'victory')
        assert len(request.model_dump_json().encode())<24000
        text=request.model_dump_json()
        assert all(value not in text for value in [mission.token,*credentials,*[p.id for p in mission.players]])
        assert all(value not in text for crisis in mission.sequence for value in crisis.private_intelligence.values())
        before=[r.model_dump_json() for r in mission.results];metrics=mission.metrics.model_copy()
        provider=StoryProvider();end=coordinator(store,live,provider)
        for _ in range(4):
            if not early:assert not store.continue_mission(mission.token,credentials[0],mission.results[-1].id)
            await launch(end)
        await settle(end);await launch(end);await settle(end)
        assert len(provider.requests)==1 and mission.conclusion.status=='generated'
        assert mission.conclusion.basis_hash==basis_hash(mission)
        assert [r.model_dump_json() for r in mission.results]==before and mission.metrics==metrics
        for p in mission.players:
            frame=store.project(mission.token,p.id)
            assert frame['summary']['conclusion']['status']=='generated'
            assert 'basis_hash' not in json.dumps(frame) and 'duration_seconds' not in json.dumps(frame)
            assert 'diagnostic' not in json.dumps(frame)
            assert all(r['crisis_id'] in {result.crisis_id for result in mission.results} for section in frame['summary']['conclusion']['sections'] for r in section['references'])
        hashes=store.persistence.connection.execute('SELECT record_hash FROM resolutions').fetchall()
        saved=mission.conclusion;token=mission.token
        await end.close();await live.close();store.close()
        restored=MissionStore(clock,persistence=SQLiteMissions(tmp_path/'story.sqlite3'));restored.initialize()
        assert restored.get(token).conclusion==saved
        assert restored.persistence.connection.execute('SELECT record_hash FROM resolutions').fetchall()==hashes
        assert inspect(tmp_path/'story.sqlite3',operation='endgame')[0]['operation']=='endgame'
        assert len(inspect(tmp_path/'story.sqlite3'))==len(mission.results)
        restored.close()
    asyncio.run(run())


@pytest.mark.parametrize('failure,category',[(FailureCategory.UNAVAILABLE,'unavailable'),('schema','invalid_schema'),('reference','invalid_schema'),(None,'timeout')])
def test_endgame_failure_and_timeout_keep_deterministic_ending(tmp_path,failure,category):
    async def run():
        store,mission,credentials,clock,live=await completed(tmp_path/'failure.sqlite3')
        before=store.project(mission.token,mission.host_id)['summary']['narrative_outcome']
        provider=StoryProvider(failure,held=failure is None);end=coordinator(store,live,provider,timeout=.01)
        await launch(end);await settle(end)
        assert mission.conclusion.status=='fallback' and mission.conclusion.diagnostic.category==category
        assert store.project(mission.token,mission.host_id)['summary']['narrative_outcome']==before
        await launch(end);assert not end.tasks and len(provider.requests)==1
        await end.close();await live.close();store.close()
    asyncio.run(run())


@pytest.mark.parametrize('mutation',[
    lambda raw:raw.update(outcome='victory'),lambda raw:raw.update(metrics={'safety':100}),
    lambda raw:raw.update(schema_version='bad'),lambda raw:raw.pop('cost'),
    lambda raw:raw['journey'].update(text='short'),lambda raw:raw['journey'].update(references=[1,1]),
    lambda raw:raw['journey'].update(references=[9]),lambda raw:raw['journey'].update(crisis_id='invented'),
])
def test_strict_endgame_schema_and_supported_references(mutation):
    async def run():
        store,mission,credentials,clock,live=await completed(early=True)
        request=build_endgame_request(mission);raw=story(request);mutation(raw)
        with pytest.raises(GenerationError):accept_endgame(json.dumps(raw),request.context)
        schema=endgame_schema(request.context)
        assert schema['additionalProperties'] is False
        assert schema['$defs']['StorySection']['properties']['references']['items']['enum']==[1]
        await live.close();store.close()
    asyncio.run(run())


def test_pending_restart_is_fallback_and_obsolete_response_cannot_replace_it(tmp_path):
    async def run():
        path=tmp_path/'restart.sqlite3';store,mission,credentials,clock,live=await completed(path)
        provider=StoryProvider(held=True);end=coordinator(store,live,provider)
        await launch(end);await provider.entered.wait()
        for p in mission.players:
            assert store.project(mission.token,p.id)['summary']['conclusion']['status']=='pending'
        # Load a consistent copy while the original fake request remains pending.
        copy=tmp_path/'copy.sqlite3'
        with sqlite3.connect(copy) as db:store.persistence.connection.backup(db)
        restored=MissionStore(clock,persistence=SQLiteMissions(copy));restored.initialize();recovered=restored.get(mission.token)
        assert recovered.conclusion.status=='fallback' and recovered.conclusion.diagnostic.category=='restart_recovery'
        request=build_endgame_request(recovered)
        assert not restored.finish_conclusion(mission.token,mission.conclusion.id,mission.conclusion.basis_hash,
            accept_endgame(json.dumps(story(request)),request.context),EndgameDiagnostic(source='generated',category='success',duration_seconds=1.0))
        assert len(provider.requests)==1
        await end.close();await live.close();store.close();restored.close()
    asyncio.run(run())


def test_stale_attempt_and_changed_basis_are_rejected():
    async def run():
        store,mission,credentials,clock,live=await completed()
        request=build_endgame_request(mission);narrative=accept_endgame(json.dumps(story(request)),request.context)
        diagnostic=EndgameDiagnostic(source='generated',category='success',duration_seconds=1.0)
        state=mission.conclusion
        assert not store.finish_conclusion(mission.token,'obsolete',state.basis_hash,narrative,diagnostic)
        assert not store.finish_conclusion(mission.token,state.id,'0'*64,narrative,diagnostic)
        assert mission.conclusion.status=='pending'
        await live.close();store.close()
    asyncio.run(run())


def test_storage_failure_reuses_story_without_a_second_inference_and_snapshot_is_immutable(tmp_path,monkeypatch):
    async def run():
        path=tmp_path/'storage.sqlite3';store,mission,credentials,clock,live=await completed(path)
        provider=StoryProvider();end=coordinator(store,live,provider);save=store.persistence.save
        def broken(mission, **_metadata):raise PersistenceError('temporary')
        monkeypatch.setattr(store.persistence,'save',broken)
        await launch(end);await settle(end)
        assert mission.conclusion.status=='pending' and len(provider.requests)==1
        monkeypatch.setattr(store.persistence,'save',save)
        await launch(end);await settle(end)
        assert mission.conclusion.status=='generated' and len(provider.requests)==1
        mission.conclusion=mission.conclusion.model_copy(update={'narrative':mission.conclusion.narrative.model_copy(update={
            'journey':mission.conclusion.narrative.journey.model_copy(update={'text':'A changed interpretation that must not overwrite the accepted immutable story.'})})})
        with pytest.raises(PersistenceError,match='Finalized conclusion'):store.bump_revision(mission.token)
        mission.conclusion=None
        with pytest.raises(PersistenceError,match='Finalized conclusion'):store.bump_revision(mission.token)
        await end.close();await live.close();store.close()
    asyncio.run(run())


def test_endgame_cancellation_is_durable_and_does_not_leave_a_pending_screen(tmp_path):
    async def run():
        path=tmp_path/'cancel.sqlite3';store,mission,credentials,clock,live=await completed(path)
        provider=StoryProvider(held=True);end=coordinator(store,live,provider)
        await launch(end);await provider.entered.wait();await end.close()
        assert mission.conclusion.status=='fallback'
        diagnostic=inspect(path,operation='endgame')[0]
        assert diagnostic['category']=='canceled' and diagnostic['duration_seconds']>=0
        assert len(provider.requests)==1
        await live.close();store.close()
    asyncio.run(run())


def test_disabled_endgame_does_not_invoke_provider_and_keeps_deterministic_ending():
    async def run():
        store,mission,credentials,clock,live=await completed(early=True)
        provider=StoryProvider()
        outcome=await generate_conclusion(GenerationSettings(),provider,build_endgame_request(mission))
        assert not provider.requests and outcome.narrative is None and outcome.diagnostic.category=='disabled'
        await live.close();store.close()
    asyncio.run(run())


def test_legacy_terminal_generated_mission_without_story_does_not_trigger_inference(tmp_path):
    async def run():
        path=tmp_path/'legacy.sqlite3';store,mission,credentials,clock,live=await completed(path)
        token=mission.token;await live.close();store.close()
        with sqlite3.connect(path) as db:
            raw=json.loads(db.execute('SELECT payload FROM missions').fetchone()[0]);raw.pop('conclusion')
            text=canonical(raw);db.execute('UPDATE missions SET payload=?,checksum=?',(text,hashlib.sha256(text.encode()).hexdigest()))
        restored=MissionStore(clock,persistence=SQLiteMissions(path));restored.initialize()
        assert restored.get(token).conclusion is None
        end=coordinator(restored,live,StoryProvider());await launch(end)
        assert not end.tasks and not end.provider.requests
        assert inspect(path,operation='endgame')==[]
        await end.close();restored.close()
    asyncio.run(run())


@pytest.mark.parametrize('response_format',['json_schema','json_object'])
def test_endgame_uses_existing_http_adapter_with_separate_contract(response_format):
    async def run():
        store,mission,credentials,clock,live=await completed(early=True);request=build_endgame_request(mission)
        calls=[]
        def handler(req):
            payload=json.loads(req.content);calls.append(payload)
            assert 'endgame-1.0' in payload['messages'][0]['content']
            assert json.loads(payload['messages'][1]['content'])==json.loads(request.model_dump_json())
            if response_format=='json_schema':
                assert payload['response_format']['json_schema']['name']=='endgame_narrative_v1'
                assert payload['response_format']['json_schema']['schema']==endgame_schema(request.context)
            return httpx.Response(200,json=wire(json.dumps(story(request))))
        config=GenerationSettings(enabled=True,endpoint='http://localhost/fixture',model='fixture',require_api_key=False,response_format=response_format)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            outcome=await generate_conclusion(config,ChatCompletionsProvider(config,client),request)
            assert outcome.narrative and outcome.diagnostic.http_status==200
        assert len(calls)==1
        await live.close();store.close()
    asyncio.run(run())
