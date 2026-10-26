"""Production authored content, exhaustive balance and full multiplayer runs."""
import hashlib
import json
from contextlib import ExitStack
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.campaign_analysis import analyze, simulate
from app.consequences import apply_metric_deltas
from app.crises import load_crisis_sequence
from app.domain import Crisis, Metrics, Phase, Role
from app.main import create_app
from app.missions import MissionError, MissionStore
from test_foundation import authenticate, create
from test_milestone3 import Clock, cast, expire

IDS = ['grid-under-pressure','waterline-alert','care-at-capacity','essential-corridor',
       'signal-and-rumour','services-under-intrusion','storm-at-the-barrier','credit-under-strain',
       'a-fair-share','the-last-coordination']
SURVIVAL_PATH = 'BBBCCBCAAC'
CONTENT = Path(__file__).resolve().parents[1] / 'app' / 'content'


@pytest.fixture(scope='module')
def balance():
    return analyze()


def test_complete_campaign_catalog_and_preserved_intro():
    sequence = load_crisis_sequence()
    assert [c.id for c in sequence] == IDS
    assert len({c.title for c in sequence}) == 10
    assert {p.stem for p in CONTENT.glob('*.json')} == {*IDS,'sequence'}
    assert hashlib.sha256((CONTENT/'grid-under-pressure.json').read_bytes()).hexdigest() == '1a83bdb443c9a0b893b48271c3523cf6c9f47e7e92a0f2037d7acdf1801c29ac'


@pytest.mark.parametrize('crisis',load_crisis_sequence(),ids=IDS)
def test_each_authored_crisis_is_complete_and_has_genuine_tradeoffs(crisis):
    assert len(crisis.briefing) > 100 and crisis.title.strip()
    assert set(crisis.private_intelligence) == set(Role)
    assert len(set(crisis.private_intelligence.values())) == 4
    assert all(len(text) > 50 and text not in crisis.briefing for text in crisis.private_intelligence.values())
    assert {c.id for c in crisis.choices} == {'A','B','C'}
    assert len({c.title for c in crisis.choices}) == 3
    assert len({c.description for c in crisis.choices}) == 3
    assert len({c.consequence for c in crisis.choices}) == 3
    assert sum(c.id == crisis.ai_recommendation_choice_id for c in crisis.choices) == 1
    for choice in crisis.choices:
        assert len(choice.consequence) > 50 and choice.consequence != choice.description
        deltas = choice.metric_deltas.model_dump()
        assert set(deltas) == set(Metrics().model_dump())
        assert any(x > 0 for x in deltas.values()) and any(x < 0 for x in deltas.values())
        assert all(type(value) is int for value in deltas.values())


@pytest.mark.parametrize('field', ['title','briefing','description','consequence','private','choices','recommendation','metrics','unknown'])
def test_malformed_content_fails_existing_schema(field):
    raw = load_crisis_sequence()[1].model_dump(mode='json')
    if field in ['title','briefing']: raw[field] = ' '
    elif field in ['description','consequence']: raw['choices'][0][field] = ''
    elif field == 'private': raw['private_intelligence']['safety'] = ' '
    elif field == 'choices': raw['choices'][0]['id'] = 'D'
    elif field == 'recommendation': raw['ai_recommendation_choice_id'] = 'unknown'
    elif field == 'metrics': raw['choices'][0]['metric_deltas'].pop('safety')
    else: raw['typo_field'] = 'unrecognised'
    with pytest.raises(ValueError): Crisis.model_validate(raw)


@pytest.mark.parametrize('mode', ['missing','unreachable','duplicate','wrong-id','malformed-json'])
def test_catalog_reference_errors_fail_clearly(tmp_path,mode):
    raw = load_crisis_sequence()[0].model_dump(mode='json')
    (tmp_path/'grid-under-pressure.json').write_text(json.dumps(raw))
    ids = ['grid-under-pressure']
    if mode == 'missing': ids.append('missing')
    elif mode == 'unreachable': (tmp_path/'orphan.json').write_text(json.dumps(raw))
    elif mode == 'duplicate': ids.append(ids[0])
    elif mode == 'wrong-id':
        raw['id'] = 'other-id'; (tmp_path/'grid-under-pressure.json').write_text(json.dumps(raw))
    elif mode == 'malformed-json': (tmp_path/'grid-under-pressure.json').write_text('{')
    (tmp_path/'sequence.json').write_text(json.dumps(ids))
    with pytest.raises(ValueError): load_crisis_sequence(tmp_path)


def test_exhaustive_balance_has_survival_collapse_and_no_dominant_option(balance):
    assert balance['paths'] == 59049
    assert balance['survivors'] + balance['collapsed'] == 59049
    assert 30 < balance['survival_percent'] < 70
    assert balance['pareto_dominance'] == []
    assert set(balance['collapsed_metrics']) == set(Metrics().model_dump())
    assert all(n > 0 for n in balance['collapsed_metrics'].values())
    assert balance['recommendations'] == {'A':3,'B':3,'C':4}
    for label in ['always_A','always_B','always_C','authored_AI','alternating_ABC','alternating_CBA']:
        assert len(balance['strategies'][label]['full_horizon_raw_deltas']) == 4
    assert not balance['strategies']['always_A']['survived']
    assert not balance['strategies']['always_C']['survived']
    assert balance['strategies']['authored_AI']['survived']
    assert balance['strategies']['always_B']['score'] < balance['best_score_path']['score']
    assert balance['lowest_surviving_score_path']['score'] < balance['strategies']['authored_AI']['score'] < balance['best_score_path']['score']
    assert min(balance['strongest_floor_path']['metrics'].values()) >= 50


@pytest.mark.parametrize('path',['AAAAAAAAAA','BBBBBBBBBB','CCCCCCCCCC','ABACACBCCB','ABCABCABCA','CBACBACBAC',SURVIVAL_PATH,'BBCCCBCCAB'])
def test_analysis_matches_actual_production_store(path):
    sequence = load_crisis_sequence(); clock = Clock(); store = MissionStore(clock)
    mission,host = store.create('Host')
    store.join(mission.token,'Guest')
    for p in mission.players: p.connected = True
    store.start(mission.token,host.credential)
    for choice in path:
        store.begin_discussion(mission.token,host.credential); expire(store,mission,clock)
        cast(store,mission,[choice,choice])
        if mission.phase == Phase.FAILED: break
        store.continue_mission(mission.token,host.credential,mission.results[-1].id)
    expected = simulate(sequence,path)
    assert mission.metrics.model_dump() == expected['metrics']
    assert mission.crisis_index + 1 == expected['stopped_at']
    assert (mission.phase == Phase.COMPLETED) == expected['survived']
    assert mission.consensus_score == expected['score']


@pytest.mark.parametrize('stage',[4,6,10])
def test_real_choices_can_collapse_early_middle_and_late_and_block_advancement(balance,stage):
    example = balance['collapse_examples'][stage]
    clock=Clock(); store=MissionStore(clock); mission,host=store.create('Host')
    store.join(mission.token,'Guest')
    for p in mission.players: p.connected=True
    store.start(mission.token,host.credential)
    for choice in example['path']:
        store.begin_discussion(mission.token,host.credential); expire(store,mission,clock)
        cast(store,mission,[choice,choice])
        if mission.phase == Phase.FAILED: break
        store.continue_mission(mission.token,host.credential,mission.results[-1].id)
    assert mission.phase == Phase.FAILED and mission.crisis_index + 1 == stage
    assert mission.consensus_score is None
    original=mission.model_dump()
    with pytest.raises(MissionError): store.continue_mission(mission.token,host.credential,mission.results[-1].id)
    store._resolve(mission); store._apply_consequences(mission)
    assert mission.model_dump() == original


class CampaignClients:
    def __init__(self,count):
        self.count=count; self.clock=Clock(); self.app=create_app(self.clock)
        self.stack=ExitStack()

    def __enter__(self):
        self.client=self.stack.enter_context(TestClient(self.app))
        self.host=create(self.client,'Eagle1'); self.token=self.host['token']
        self.sessions=[self.host]+[self.client.post(f'/api/missions/{self.token}/join',json={'callsign':f'Eagle{i+2}'}).json() for i in range(self.count-1)]
        self.url=f'/api/missions/{self.token}/ws'; self.sockets=[]
        for session in self.sessions:
            socket=self.stack.enter_context(self.client.websocket_connect(self.url))
            authenticate(socket,session['credential'])
            for old in self.sockets: old.receive_json()
            self.sockets.append(socket)
        self.store=self.app.state.missions; self.mission=self.store.get(self.token)
        return self

    def __exit__(self,*args): return self.stack.__exit__(*args)

    def states(self):
        frames=[s.receive_json()['mission'] for s in self.sockets]
        for key in ['phase','crisis','metrics','result','decision','crisis_number','deadline','consensus_score']:
            assert all(frame[key] == frames[0][key] for frame in frames)
        for player,state in zip(self.mission.players,frames):
            assert state['private_intelligence'] == ({r:self.mission.crisis.private_intelligence[r] for r in player.roles} if self.mission.crisis else {})
            for crisis in self.mission.sequence:
                for role,text in crisis.private_intelligence.items():
                    if crisis.id != self.mission.crisis.id or role not in player.roles:
                        assert text not in json.dumps(state)
            assert len(state['closed_rounds']) <= 2 and len(state['chat']) <= 100
            assert 'sequence' not in state and 'results' not in state
        return frames

    def post(self,action,body=None):
        response=self.client.post(f'/api/missions/{self.token}/{action}',headers={'X-Mission-Session':self.host['credential']},json=body)
        assert response.status_code == 200,response.text
        return response.json(),self.states()

    def tick(self):
        async def advance():
            async with self.app.state.lock: self.clock.now=self.mission.deadline
            await self.app.state.tick()
        self.client.portal.call(advance)
        return self.states()

    def votes(self,choices):
        round_id=self.mission.rounds[-1].id
        for socket,choice in zip(self.sockets,choices):
            socket.send_json({'type':'vote','round_id':round_id,'choice_id':choice})
            frames=self.states()
        return frames

    def restore(self,viewer,original):
        with self.client.websocket_connect(self.url) as restored:
            state=authenticate(restored,self.sessions[viewer]['credential'])
            for key in ['you','roles','phase','deadline','crisis','metrics','private_intelligence','voting','result','consensus_score']:
                assert state[key] == original[key]
            self.states()
        self.states()


def plurality_votes(count,choice):
    alternatives=[c for c in 'ABC' if c != choice]
    return [choice,choice]+(alternatives[:count-2] if count > 2 else [])


def tied_votes(count):
    return ['A','B'] if count==2 else ['A','B','C'] if count==3 else ['A','A','B','B']


@pytest.mark.parametrize('count',[2,3,4])
def test_ten_crisis_multiplayer_campaign_with_ties_privacy_reconnect_and_once_only(count):
    with CampaignClients(count) as game:
        _,frames=game.post('start')
        assert frames[0]['crisis_count'] == 10
        assert sorted(len(p.roles) for p in game.mission.players) == {2:[2,2],3:[1,1,2],4:[1,1,1,1]}[count]
        original_roles={p.id:list(p.roles) for p in game.mission.players}
        expected=Metrics(); seen=[]; previous_rounds=set()
        for number,(crisis,choice) in enumerate(zip(load_crisis_sequence(),SURVIVAL_PATH),1):
            assert game.mission.crisis.id == crisis.id
            assert game.mission.crisis_index + 1 == number
            assert game.mission.metrics == expected
            assert not game.mission.rounds and game.mission.decision is None and game.mission.deadline is None
            assert game.store.project(game.token,game.mission.host_id)['result'] is None
            _,frames=game.post('discussion')
            assert frames[0]['deadline']-frames[0]['server_now'] == 60
            game.sockets[0].send_json({'type':'chat','text':f'Review crisis {number} together.'})
            frames=game.states()
            assert frames[0]['chat'][-1]['crisis_number'] == number
            frames=game.tick()
            assert frames[0]['phase'] == 'voting'
            assert frames[0]['deadline']-frames[0]['server_now'] == 30
            assert game.mission.rounds[0].id not in previous_rounds
            if number in [2,4]:
                frames=game.votes(tied_votes(count))
                assert frames[0]['phase'] == 'consensus_window'
                assert frames[0]['deadline']-frames[0]['server_now'] == 20
                if number==4: game.restore(1,frames[1])
                frames=game.tick()
                assert all(s['voting']['your_vote'] is None for s in frames)
                assert frames[0]['deadline']-frames[0]['server_now'] == 30
                frames=game.votes(tied_votes(count) if number==4 else plurality_votes(count,choice))
                assert frames[0]['decision']['reason'] == ('ai_tie_break' if number==4 else 'final_plurality')
            else:
                if number==8: game.restore(1,frames[1])
                frames=game.votes(plurality_votes(count,choice))
            expected=apply_metric_deltas(expected,next(c for c in crisis.choices if c.id==choice).metric_deltas)
            assert frames[0]['metrics'] == expected.model_dump()
            assert frames[0]['result']['decision']['choice_id'] == choice
            assert frames[0]['decision']['abstentions'] == 0
            assert len(game.mission.results) == number
            seen.append(game.mission.crisis.id)
            previous_rounds.update(r.id for r in game.mission.rounds)
            async def repeat():
                async with game.app.state.lock:
                    game.store._resolve(game.mission); game.store._apply_consequences(game.mission)
                    assert not game.store.advance_due(game.token)
            game.client.portal.call(repeat)
            assert len(game.mission.results) == number and game.mission.metrics == expected
            if number==9: game.restore(1,frames[1])
            result_id=frames[0]['result']['id']
            response,frames=game.post('continue',{'result_id':result_id})
            assert response['advanced']
            response,frames=game.post('continue',{'result_id':result_id})
            assert not response['advanced']
            assert {p.id:p.roles for p in game.mission.players} == original_roles
            assert frames[0]['phase'] == ('completed' if number==10 else 'briefing')
        assert seen == IDS
        assert frames[0]['crisis_number'] == 10
        assert frames[0]['metrics'] == {'infrastructure':63,'public_trust':55,'economy':53,'safety':52}
        assert frames[0]['consensus_score'] == 55.75
        game.restore(1,frames[1])
        assert len(game.mission.rounds) <= 2 and len(game.mission.results) == 10
