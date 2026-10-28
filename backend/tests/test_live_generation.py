"""Live admission, asynchronous races, recovery and full generated campaign."""
import asyncio
from contextlib import ExitStack
import hashlib
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.campaign import load_campaign_catalog, select_crisis
from app.domain import Phase
from app.generation.config import GenerationSettings
from app.generation.contract import AcceptedScenario, GenerationError, FailureCategory
from app.generation.live import LiveGeneration
from app.generation.provider import ProviderResponse
from app.main import create_app
from app.missions import MissionStore, MissionError
from app.persistence import SQLiteMissions, PersistenceError, canonical
from test_milestone3 import Clock
from test_persistence import ready, voting, votes
from test_foundation import authenticate


class ProgressiveProvider:
    def __init__(self, failures=None, held=False):
        self.requests = []
        self.failures = failures or {}
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        if not held: self.release.set()
        self.cancelled = False

    async def generate(self, request):
        self.requests.append(request)
        self.entered.set()
        try: await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        number = request.context.current_crisis_number
        if number in self.failures:
            failure = self.failures[number]
            if failure == 'invalid': return ProviderResponse('{"schema_version":"bad"}')
            raise GenerationError(failure)
        crisis = load_campaign_catalog()[0].crisis.model_dump(mode='json')
        crisis.pop('id')
        crisis['title'] = f'Civic Coordination {number}'
        crisis['briefing'] += f' This is crisis {number}; Public Trust is {request.context.metrics.public_trust}.'
        effects = [(3, -2, 1, -1), (-2, 3, -1, 1), (1, -1, -2, 3)]
        for choice, values in zip(crisis['choices'], effects):
            choice['metric_deltas'] = dict(zip(('infrastructure','public_trust','economy','safety'), values))
        refs = []
        if request.context.history:
            previous = request.context.history[-1]
            refs = [{'crisis_number':previous.crisis_number, 'choice_id':previous.choice_id}]
            crisis['briefing'] += f' Earlier decision: {previous.choice_title}. {previous.consequence}'
        return ProviderResponse(json.dumps({'schema_version':'1.0','crisis':crisis,'continuity_references':refs}))


class Publications:
    def __init__(self, store): self.store, self.frames, self.pending = store, [], set()
    async def broadcast(self, token):
        self.frames.append([self.store.project(token,p.id) for p in self.store.get(token).players])


def setup(path=None, provider=None, timeout=1):
    clock = Clock()
    store = MissionStore(clock, campaign_loader=load_campaign_catalog, generation_enabled=True,
                         persistence=SQLiteMissions(path) if path else None)
    store.initialize()
    mission, host = store.create('Host', 'generated')
    credentials = [host.credential]
    for name in ['Second','Third']: credentials.append(store.join(mission.token,name)[1].credential)
    ready(store,mission)
    store.start(mission.token,credentials[0])
    publications = Publications(store)
    live = LiveGeneration(store, asyncio.Lock(), publications, GenerationSettings(enabled=True,timeout_seconds=timeout), provider or ProgressiveProvider())
    return store, mission, credentials, clock, live


async def launch(live):
    async with live.lock: live.launch_pending()


async def settle(live):
    if live.tasks: await asyncio.wait_for(asyncio.gather(*list(live.tasks.values())), 2)


def test_mode_api_defaults_availability_and_validation():
    with TestClient(create_app()) as client:
        assert client.get('/api/capabilities').json() == {'generated_missions':False}
        response = client.post('/api/missions',json={'callsign':'Legacy'})
        assert response.status_code == 201
        assert client.app.state.missions.get(response.json()['token']).mode == 'authored'
        response = client.post('/api/missions',json={'callsign':'Host','mode':'generated'})
        assert response.status_code == 409 and response.json()['code'] == 'generation_unavailable'
        for mode in ['invalid', True, None, 1]:
            assert client.post('/api/missions',json={'callsign':'Host','mode':mode}).status_code == 422
    with TestClient(create_app(generation_settings=GenerationSettings(enabled=True),generation_provider=ProgressiveProvider())) as client:
        assert client.get('/api/capabilities').json() == {'generated_missions':True}
        assert client.post('/api/missions',json={'callsign':'Host','mode':'generated'}).status_code == 201


def test_incomplete_or_invalid_server_configuration_does_not_offer_generated_mode(monkeypatch):
    monkeypatch.setenv('CONSENSUS_LLM_ENABLED','true')
    monkeypatch.delenv('CONSENSUS_LLM_ENDPOINT',raising=False)
    with TestClient(create_app()) as client:
        assert not client.get('/api/capabilities').json()['generated_missions']
    monkeypatch.setenv('CONSENSUS_LLM_TIMEOUT_SECONDS','invalid-secret-value')
    with TestClient(create_app()) as client:
        assert not client.get('/api/capabilities').json()['generated_missions']


def test_progressive_ten_crises_with_fallback_privacy_metrics_and_context(tmp_path):
    async def exercise():
        provider = ProgressiveProvider({3:'invalid',6:FailureCategory.UNAVAILABLE})
        store, mission, credentials, clock, live = setup(tmp_path/'ten.sqlite3',provider)
        try:
            assert mission.crisis is None and not mission.sequence and mission.phase == Phase.PREPARING
            for index in range(10):
                metrics = mission.metrics.model_dump(); history = list(mission.results)
                await launch(live); await settle(live)
                assert mission.phase == Phase.BRIEFING and len(mission.sequence) == index+1
                request = provider.requests[-1]
                assert request.context.current_crisis_number == index+1
                assert request.context.metrics.model_dump() == metrics
                assert [r.choice_id for r in request.context.history] == [r.decision.choice_id for r in history[-3:]]
                assert request.context.used_scenario_ids == tuple(r.crisis_id for r in history)
                if index in (2,5):
                    assert mission.crisis == select_crisis(mission.campaign,index,history)
                    assert mission.admissions[-1].source == 'authored_fallback'
                else: assert mission.admissions[-1].source == 'generated'
                frames = live.connections.frames[-1]
                assert all(s['crisis']==frames[0]['crisis'] and s['crisis_count']==10 for s in frames)
                for state, player in zip(frames,mission.players):
                    assert state['private_intelligence'] == {r:mission.crisis.private_intelligence[r] for r in player.roles}
                    assert all(secret not in json.dumps(state) for role,secret in mission.crisis.private_intelligence.items() if role not in player.roles)
                    assert all(name not in state for name in ['generation','admissions','campaign','sequence','prompt','failure'])
                    assert 'metric_deltas' not in json.dumps(state['crisis'])
                frozen = mission.admissions[-1].canonical_json
                voting(store,mission,credentials,clock)
                # Generated choices keep A viable; authored fallbacks choose the best weakest metric.
                from test_expansion import balanced
                choice = balanced(mission)
                votes(store,mission,credentials,[choice]*3)
                assert mission.results[-1].crisis_id == mission.crisis.id
                assert mission.results[-1].authored_deltas == next(c.metric_deltas for c in mission.crisis.choices if c.id==choice)
                assert mission.admissions[-1].canonical_json == frozen and not mission.collapsed_metrics
                result_id = mission.results[-1].id
                assert store.continue_mission(mission.token,credentials[0],result_id)
                assert not store.continue_mission(mission.token,credentials[0],result_id)
                if index<9: assert mission.crisis_index==index and mission.phase==Phase.PREPARING
            assert mission.phase==Phase.COMPLETED and len(mission.results)==10 and len(provider.requests)==10
            assert len({c.id for c in mission.sequence})==10
            assert mission.consensus_score==sum(mission.metrics.model_dump().values())/4
            SQLiteMissions.validate_generated(mission)
        finally:
            await live.close();store.close()
    asyncio.run(exercise())


def test_single_attempt_concurrent_launch_reconnect_and_presence_gating():
    async def exercise():
        provider=ProgressiveProvider(held=True)
        store,mission,credentials,clock,live=setup(provider=provider)
        await asyncio.gather(*(launch(live) for _ in range(8)))
        await asyncio.wait_for(provider.entered.wait(),1)
        assert len(provider.requests)==1
        with pytest.raises(MissionError):store.start(mission.token,credentials[0])
        store.set_connected(mission.token,mission.players[-1].id,False)
        assert store.project(mission.token,mission.host_id)['generation_status']=='preparing'
        assert store.project(mission.token,mission.host_id)['crisis'] is None
        provider.release.set();await settle(live)
        assert mission.phase==Phase.BRIEFING
        with pytest.raises(MissionError):store.begin_discussion(mission.token,credentials[0])
        ready(store,mission);voting(store,mission,credentials,clock)
        original=mission.crisis.model_dump_json()
        store.set_connected(mission.token,mission.players[-1].id,False)
        store.set_connected(mission.token,mission.players[-1].id,True)
        await launch(live);assert len(provider.requests)==1 and mission.crisis.model_dump_json()==original
        votes(store,mission,credentials,['A']*3)
        await asyncio.gather(*(async_continue(live,store,mission,credentials[0]) for _ in range(6)))
        await settle(live)
        assert len(provider.requests)==2 and len(mission.sequence)==2 and mission.crisis_index==1
        await live.close()
    asyncio.run(exercise())


async def async_continue(live,store,mission,credential):
    async with live.lock:
        store.continue_mission(mission.token,credential,mission.results[-1].id)
        live.launch_pending()


@pytest.mark.parametrize('failure',[FailureCategory.TIMEOUT,FailureCategory.AUTHENTICATION,FailureCategory.UNAVAILABLE,'invalid'])
def test_invalid_or_unavailable_generation_admits_exact_authored_fallback_once(failure):
    async def exercise():
        provider=ProgressiveProvider({1:failure})
        store,mission,credentials,clock,live=setup(provider=provider)
        expected=select_crisis(mission.campaign,0,[])
        await launch(live);await settle(live);await launch(live)
        assert mission.crisis==expected and mission.admissions[0].source=='authored_fallback'
        assert len(provider.requests)==1 and len(mission.sequence)==1
        await live.close()
    asyncio.run(exercise())


def test_total_timeout_does_not_hold_mission_lock_or_block_other_missions():
    async def exercise():
        provider=ProgressiveProvider(held=True)
        store,mission,credentials,clock,live=setup(provider=provider,timeout=.02)
        await launch(live);await provider.entered.wait()
        async with live.lock:
            other,_=store.create('Other')
            assert other.phase==Phase.LOBBY
        await settle(live)
        assert mission.phase==Phase.BRIEFING and provider.cancelled and mission.admissions[0].source=='authored_fallback'
        await live.close()
    asyncio.run(exercise())


def test_shutdown_pending_attempt_restarts_as_authored_without_inference(tmp_path):
    async def exercise():
        provider=ProgressiveProvider(held=True);path=tmp_path/'pending.sqlite3'
        store,mission,credentials,clock,live=setup(path,provider)
        await launch(live);await provider.entered.wait();await live.close()
        assert provider.cancelled and mission.phase==Phase.PREPARING
        token=mission.token;store.close()
        restored=MissionStore(clock,persistence=SQLiteMissions(path));restored.initialize()
        recovered=restored.get(token)
        assert recovered.mode=='generated' and recovered.phase==Phase.BRIEFING and recovered.crisis_index==0
        assert recovered.admissions[0].source=='authored_fallback' and recovered.crisis.id=='grid-under-pressure'
        assert all(not p.connected for p in recovered.players)
        with pytest.raises(MissionError):restored.begin_discussion(token,credentials[0])
        restored.close()
    asyncio.run(exercise())


def test_restart_accepted_generated_crisis_voting_and_history_hashes(tmp_path):
    async def exercise():
        path=tmp_path/'accepted.sqlite3';store,mission,credentials,clock,live=setup(path)
        await launch(live);await settle(live)
        original=mission.crisis.model_dump_json();roles=[list(p.roles) for p in mission.players]
        voting(store,mission,credentials,clock);round_id=mission.rounds[-1].id
        store.vote(mission.token,credentials[0],round_id,'B')
        token=mission.token;await live.close();store.close()
        restored=MissionStore(clock,persistence=SQLiteMissions(path));restored.initialize();mission=restored.get(token)
        assert mission.phase==Phase.RECONNECT_WAIT and mission.crisis.model_dump_json()==original
        ready(restored,mission)
        assert mission.phase==Phase.VOTING and mission.rounds[-1].id==round_id
        assert [p.roles for p in mission.players]==roles and mission.rounds[-1].votes[mission.host_id]=='B'
        for credential in credentials[1:]:restored.vote(token,credential,round_id,'B')
        result=mission.results[-1];digest=hashlib.sha256(canonical(result.model_dump(mode='json')).encode()).hexdigest()
        with sqlite3.connect(path) as connection:
            assert connection.execute('SELECT record_hash FROM resolutions').fetchone()[0]==digest
        restored.close()
        again=MissionStore(clock,persistence=SQLiteMissions(path));again.initialize()
        assert again.get(token).results[-1]==result and again.get(token).crisis.model_dump_json()==original
        again.close()
    asyncio.run(exercise())


def test_transient_admission_storage_failure_retains_result_without_regeneration(tmp_path,monkeypatch):
    async def exercise():
        provider=ProgressiveProvider();store,mission,credentials,clock,live=setup(tmp_path/'storage.sqlite3',provider)
        save=store.persistence.save
        def broken(mission):raise PersistenceError('safe test failure')
        monkeypatch.setattr(store.persistence,'save',broken)
        await launch(live);await settle(live)
        assert mission.phase==Phase.PREPARING and len(provider.requests)==1 and not mission.sequence
        monkeypatch.setattr(store.persistence,'save',save)
        await launch(live);await settle(live)
        assert mission.phase==Phase.BRIEFING and len(provider.requests)==1 and not live.completed
        await live.close();store.close()
    asyncio.run(exercise())


def test_stale_response_cannot_overwrite_new_attempt_or_terminal_state():
    async def exercise():
        provider=ProgressiveProvider(held=True);store,mission,credentials,clock,live=setup(provider=provider)
        await launch(live);await provider.entered.wait();old=mission.generation.id
        store.fail_generation(mission.token,old)
        store.retry_generation(mission.token,credentials[0])
        provider.release.set();await settle(live)
        assert mission.phase==Phase.PREPARING and not mission.sequence and mission.generation.id!=old
        await launch(live);await settle(live)
        accepted=mission.crisis.model_dump_json()
        mission.phase=Phase.FAILED
        assert not store.accept_generation(mission.token,old,AcceptedScenario.from_crisis(load_campaign_catalog()[0].crisis),'authored_fallback')
        assert mission.crisis.model_dump_json()==accepted and len(mission.sequence)==1
        await live.close()
    asyncio.run(exercise())


def test_invalid_fallback_has_explicit_retry_path_without_advancing_counter(monkeypatch):
    async def exercise():
        store,mission,credentials,clock,live=setup(provider=ProgressiveProvider({1:FailureCategory.UNAVAILABLE}))
        import app.generation.live as module
        original=module.authored_selector
        def broken(*args):
            def select():raise ValueError('PRIVATE-DIAGNOSTIC')
            return select
        monkeypatch.setattr(module,'authored_selector',broken)
        await launch(live);await settle(live)
        assert mission.generation.status=='error' and mission.crisis_index==0 and not mission.sequence
        assert store.project(mission.token,mission.host_id)['generation_status']=='unavailable'
        with pytest.raises(MissionError):store.retry_generation(mission.token,credentials[1])
        monkeypatch.setattr(module,'authored_selector',original)
        store.retry_generation(mission.token,credentials[0]);await launch(live);await settle(live)
        assert mission.phase==Phase.BRIEFING and mission.crisis_index==0
        await live.close()
    asyncio.run(exercise())


def test_accepted_snapshot_and_mode_cannot_be_rewritten_in_storage(tmp_path):
    async def exercise():
        store,mission,credentials,clock,live=setup(tmp_path/'immutable.sqlite3')
        await launch(live);await settle(live)
        mission.sequence[0].choices[0].metric_deltas.safety=17
        with pytest.raises(ValueError):store.bump_revision(mission.token)
        # Even changing both the snapshot and its checksum cannot replace a persisted admission.
        crisis=mission.sequence[0]
        content=canonical(crisis.model_dump(mode='json'))
        mission.admissions[0]=mission.admissions[0].model_copy(update={'canonical_json':content,'content_hash':hashlib.sha256(content.encode()).hexdigest()})
        with pytest.raises(PersistenceError):store.bump_revision(mission.token)
        mission.mode='authored';mission.admissions=[]
        with pytest.raises(PersistenceError):store.bump_revision(mission.token)
        await live.close();store.close()
    asyncio.run(exercise())


def test_three_http_websocket_clients_reconnect_during_preparation_and_share_accepted_crisis(tmp_path):
    provider=ProgressiveProvider(held=True)
    app=create_app(database_path=tmp_path/'ws.sqlite3',generation_settings=GenerationSettings(enabled=True),generation_provider=provider)
    with TestClient(app) as client, ExitStack() as stack:
        host=client.post('/api/missions',json={'callsign':'Host','mode':'generated'}).json()
        sessions=[host]+[client.post(f"/api/missions/{host['token']}/join",json={'callsign':name}).json() for name in ['Second','Third']]
        sockets=[]
        for session in sessions:
            socket=stack.enter_context(client.websocket_connect(f"/api/missions/{host['token']}/ws"));authenticate(socket,session['credential'])
            for prior in sockets:prior.receive_json()
            sockets.append(socket)
        headers={'X-Mission-Session':host['credential']}
        assert client.post(f"/api/missions/{host['token']}/start",headers=headers).status_code==200
        states=[socket.receive_json()['mission'] for socket in sockets]
        assert all(s['phase']=='preparing' and s['crisis'] is None for s in states)
        client.portal.call(provider.entered.wait)
        # Another browser using the existing credential reconnects without allocating a seat or generation.
        reconnected=stack.enter_context(client.websocket_connect(f"/api/missions/{host['token']}/ws"))
        state=authenticate(reconnected,sessions[1]['credential'])
        assert state['phase']=='preparing'
        for socket in sockets:socket.receive_json()
        client.portal.call(provider.release.set)
        client.portal.call(settle,app.state.generation)
        states=[socket.receive_json()['mission'] for socket in sockets]
        restored=reconnected.receive_json()['mission']
        assert len(provider.requests)==1 and len({s['crisis']['id'] for s in states+[restored]})==1
        assert restored['private_intelligence']==states[1]['private_intelligence']
        assert all(s['phase']=='briefing' and s['mode']=='generated' for s in states)


def test_live_context_excludes_chat_names_tokens_roles_credentials_and_private_reports():
    async def exercise():
        provider=ProgressiveProvider();store,mission,credentials,clock,live=setup(provider=provider)
        await launch(live);await settle(live)
        mission.players[0].callsign='PRIVATE-NAME-CANARY'
        store.begin_discussion(mission.token,credentials[0])
        store.send_chat(mission.token,credentials[1],'PRIVATE-CHAT-CANARY')
        clock.now=mission.deadline;store.advance_due(mission.token)
        votes(store,mission,credentials,['A']*3)
        store.continue_mission(mission.token,credentials[0],mission.results[-1].id)
        await launch(live);await settle(live)
        text=provider.requests[-1].model_dump_json()
        assert all(value not in text for value in ['PRIVATE-NAME-CANARY','PRIVATE-CHAT-CANARY',mission.token,*credentials])
        assert all(p.id not in text for p in mission.players)
        assert all(secret not in text for s in load_campaign_catalog() for secret in s.crisis.private_intelligence.values())
        assert set(json.loads(text)['context'])=={'current_crisis_number','metrics','history','used_scenario_ids'}
        await live.close()
    asyncio.run(exercise())


def test_generated_effects_clamp_and_collapse_immediately_without_next_request():
    async def exercise():
        provider=ProgressiveProvider();store,mission,credentials,clock,live=setup(provider=provider)
        mission.metrics.infrastructure=99;mission.metrics.safety=1
        mission.initial_metrics=mission.metrics.model_copy(deep=True)
        await launch(live);await settle(live)
        voting(store,mission,credentials,clock);votes(store,mission,credentials,['A']*3)
        assert mission.phase==Phase.FAILED and mission.metrics.infrastructure==100 and mission.metrics.safety==0
        assert store.project(mission.token,mission.host_id)['summary']['total_crises']==10
        with pytest.raises(MissionError):store.continue_mission(mission.token,credentials[0],mission.results[-1].id)
        await launch(live);assert len(provider.requests)==1
        await live.close()
    asyncio.run(exercise())


def test_generated_tied_rounds_reuse_frozen_consequences_and_existing_ai_tie_break():
    async def exercise():
        provider=ProgressiveProvider();store,mission,credentials,clock,live=setup(provider=provider)
        await launch(live);await settle(live);snapshot=mission.crisis.model_dump_json()
        voting(store,mission,credentials,clock);votes(store,mission,credentials,['A','B','C'])
        assert mission.phase==Phase.CONSENSUS_WINDOW
        clock.now=mission.deadline;store.advance_due(mission.token)
        votes(store,mission,credentials,['A','B','C'])
        assert mission.decision.reason=='ai_tie_break' and mission.decision.choice_id==mission.crisis.ai_recommendation_choice_id
        assert mission.crisis.model_dump_json()==snapshot and len(provider.requests)==1
        await live.close()
    asyncio.run(exercise())


def test_pending_next_crisis_restart_and_disabled_configuration_use_saved_authored_selector(tmp_path):
    async def exercise():
        path=tmp_path/'next.sqlite3';provider=ProgressiveProvider();store,mission,credentials,clock,live=setup(path,provider)
        await launch(live);await settle(live)
        voting(store,mission,credentials,clock);votes(store,mission,credentials,['A']*3)
        result_id=mission.results[-1].id
        store.continue_mission(mission.token,credentials[0],result_id)
        expected=select_crisis(mission.campaign,1,mission.results)
        token=mission.token;first=mission.sequence[0].model_dump_json();await live.close();store.close()
        restored=MissionStore(clock,persistence=SQLiteMissions(path));restored.initialize();mission=restored.get(token)
        assert mission.crisis==expected and mission.crisis_index==1 and mission.sequence[0].model_dump_json()==first
        ready(restored,mission)
        assert not restored.continue_mission(token,credentials[0],result_id)
        voting(restored,mission,credentials,clock);votes(restored,mission,credentials,['B']*3)
        restored.continue_mission(token,credentials[0],mission.results[-1].id)
        offline=LiveGeneration(restored,asyncio.Lock(),Publications(restored),GenerationSettings(),provider)
        await launch(offline);await settle(offline)
        assert mission.phase==Phase.BRIEFING and mission.admissions[-1].source=='authored_fallback' and len(provider.requests)==1
        await offline.close();restored.close()
    asyncio.run(exercise())


def test_legacy_aggregate_without_generation_fields_keeps_authored_mode_and_history_hash(tmp_path):
    from test_persistence import team as legacy_team
    path=tmp_path/'legacy.sqlite3';clock=Clock();store,mission,credentials=legacy_team(path,clock)
    voting(store,mission,credentials,clock);votes(store,mission,credentials,['B']*3)
    token=mission.token;result=mission.results[0];store.close()
    with sqlite3.connect(path) as connection:
        record_hash=connection.execute('SELECT record_hash FROM resolutions').fetchone()[0]
        payload=json.loads(connection.execute('SELECT payload FROM missions').fetchone()[0])
        for key in ['mode','generation','admissions']:payload.pop(key)
        text=canonical(payload)
        connection.execute('UPDATE missions SET payload=?,checksum=?',(text,hashlib.sha256(text.encode()).hexdigest()))
    restored=MissionStore(clock,persistence=SQLiteMissions(path));restored.initialize()
    assert restored.get(token).mode=='authored' and restored.get(token).results[0]==result
    assert restored.persistence.connection.execute('SELECT record_hash FROM resolutions').fetchone()[0]==record_hash
    restored.close()


def test_repeated_generated_content_is_rejected_then_authored_fallback_is_not_duplicated():
    from app.generation.cli import FakeProvider
    async def exercise():
        store,mission,credentials,clock,live=setup(provider=FakeProvider())
        await launch(live);await settle(live);original=mission.crisis.id
        voting(store,mission,credentials,clock);votes(store,mission,credentials,['B']*3)
        store.continue_mission(mission.token,credentials[0],mission.results[-1].id)
        await launch(live);await settle(live)
        assert mission.crisis.id!=original and mission.admissions[-1].source=='authored_fallback'
        await live.close()
    asyncio.run(exercise())


def test_scheduler_does_not_cancel_successful_state_publication():
    async def exercise():
        store,mission,credentials,clock,live=setup()
        class SlowPublications(Publications):
            def __init__(self,store):super().__init__(store);self.entered=asyncio.Event();self.release=asyncio.Event()
            async def broadcast(self,token):
                self.entered.set();await self.release.wait();await super().broadcast(token)
        live.connections=SlowPublications(store)
        await launch(live);await live.connections.entered.wait()
        assert mission.phase==Phase.BRIEFING
        await launch(live);live.connections.release.set();await settle(live)
        assert len(live.connections.frames)==1
        await live.close()
    asyncio.run(exercise())
