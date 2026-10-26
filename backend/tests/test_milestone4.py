"""Consequences, persistent state and configured progression with controlled time."""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient

from app.crises import load_crisis_sequence, load_initial_crisis
from app.domain import Metrics, MetricDeltas, Phase
from app.main import create_app
from app.missions import MissionError, MissionStore
from test_foundation import authenticate, create
from test_milestone3 import Clock, expire, cast


def fixture_sequence():
    first = load_initial_crisis()
    second = first.model_copy(deep=True)
    second.id = 'fixture-second-crisis'
    second.title = 'Second crisis — test fixture'
    second.briefing = 'Public fixture briefing for crisis two.'
    second.private_intelligence = {role: f'Fixture two secret for {role}' for role in first.private_intelligence}
    for choice in second.choices:
        choice.consequence = f'Public fixture consequence {choice.id}.'
        choice.metric_deltas = MetricDeltas(infrastructure=1, public_trust=-2, economy=3, safety=-4)
    return [first, second]


def team(sequence=None, count=3):
    clock = Clock()
    store = MissionStore(clock, lambda: sequence if sequence is not None else fixture_sequence())
    mission, host = store.create('Host')
    for i in range(count - 1):
        store.join(mission.token, f'Guest {i}')
    for p in mission.players:
        p.connected = True
    store.start(mission.token, host.credential)
    return store, mission, host, clock


def open_initial(store, mission, host, clock):
    store.begin_discussion(mission.token, host.credential)
    expire(store, mission, clock)


def resolve(store, mission, host, clock, path):
    open_initial(store, mission, host, clock)
    if path == 'initial_plurality':
        cast(store, mission, ['B', 'B', 'A'])
    elif path == 'no_vote_ai_fallback':
        expire(store, mission, clock)
    else:
        cast(store, mission, ['A', 'B', 'C'])
        expire(store, mission, clock)
        cast(store, mission, ['B', 'B', 'A'] if path == 'final_plurality' else ['A', 'B', 'C'])


def assert_privacy(store, mission):
    for player in mission.players:
        state = store.project(mission.token, player.id)
        assert set(state['private_intelligence']) == set(player.roles)
        for role, secret in mission.crisis.private_intelligence.items():
            assert (secret in json.dumps(state)) == (role in player.roles)
            assert secret not in json.dumps(state['result'])
        assert 'sequence' not in state and 'results' not in state and 'acknowledged_results' not in state
        assert 'votes' not in json.dumps(state.get('result'))


def test_packaged_sequence_and_initial_metrics():
    sequence = load_crisis_sequence()
    assert [c.id for c in sequence] == ['grid-under-pressure']
    store, mission, _, _ = team()
    assert mission.metrics.model_dump() == dict.fromkeys(['infrastructure','public_trust','economy','safety'], 70)
    state = store.project(mission.token, mission.host_id)
    assert (state['crisis_number'], state['crisis_count'], state['result']) == (1, 2, None)


@pytest.mark.parametrize('path', ['initial_plurality','final_plurality','ai_tie_break','no_vote_ai_fallback'])
def test_all_decision_paths_apply_once_and_publish_a_complete_result(path):
    store, mission, host, clock = team()
    resolve(store, mission, host, clock, path)
    result = mission.results[0]
    winner = 'B' if 'plurality' in path else 'A'
    choice = next(c for c in mission.crisis.choices if c.id == winner)
    assert result.decision.reason == path
    assert result.decision.choice_id == winner
    assert result.outcome == choice.consequence
    assert result.choice_title == choice.title
    assert result.before == Metrics()
    assert result.authored_deltas == choice.metric_deltas
    assert result.after.model_dump() == {k: 70 + d for k,d in choice.metric_deltas.model_dump().items()}
    assert result.after == mission.metrics
    assert result.id == mission.decision.round_id
    original = mission.model_dump()
    for _ in range(4):
        assert store._apply_consequences(mission) == result
        store._resolve(mission)
        assert not store.advance_due(mission.token)
        store.project(mission.token, host.id)
    assert mission.model_dump() == original
    assert len(mission.results) == 1
    assert_privacy(store, mission)


@pytest.mark.parametrize('metric', ['infrastructure','public_trust','economy','safety'])
@pytest.mark.parametrize('delta,expected,applied', [(100,100,30), (-100,0,-70)])
def test_metric_clamping_and_immediate_collapse(metric, delta, expected, applied):
    sequence = fixture_sequence()
    setattr(sequence[0].choices[1].metric_deltas, metric, delta)
    store, mission, host, clock = team(sequence)
    resolve(store, mission, host, clock, 'initial_plurality')
    result = mission.results[0]
    assert getattr(mission.metrics, metric) == expected
    assert getattr(result.applied_deltas, metric) == applied
    assert getattr(result.authored_deltas, metric) == delta
    if expected == 0:
        assert mission.phase == Phase.FAILED and mission.collapsed_metrics == [metric]
        assert mission.deadline is None and mission.consensus_score is None
        before = mission.model_dump()
        with pytest.raises(MissionError):
            store.continue_mission(mission.token, host.credential, result.id)
        with pytest.raises(MissionError):
            store.begin_discussion(mission.token, host.credential)
        store._resolve(mission)
        store._apply_consequences(mission)
        assert mission.model_dump() == before
    else:
        assert mission.phase == Phase.DECISION_LOCKED


def test_multiple_zero_metrics_reported_together():
    sequence = fixture_sequence()
    sequence[0].choices[1].metric_deltas = MetricDeltas(infrastructure=-70, public_trust=-100, economy=0, safety=0)
    store, mission, host, clock = team(sequence)
    resolve(store, mission, host, clock, 'initial_plurality')
    assert mission.phase == Phase.FAILED
    assert mission.collapsed_metrics == ['infrastructure','public_trust']


def test_progression_preserves_metrics_roles_and_privacy_and_rejects_stale_votes():
    store, mission, host, clock = team()
    roles = {p.id: list(p.roles) for p in mission.players}
    identities = [p.id for p in mission.players]
    resolve(store, mission, host, clock, 'final_plurality')
    old_round = mission.rounds[-1].id
    first_result = mission.results[0].model_copy(deep=True)
    assert store.continue_mission(mission.token, host.credential, first_result.id)
    assert mission.phase == Phase.BRIEFING and mission.crisis_index == 1
    assert mission.crisis.id == 'fixture-second-crisis'
    assert mission.metrics == first_result.after
    assert mission.rounds == [] and mission.decision is None and mission.deadline is None
    assert [p.id for p in mission.players] == identities
    assert {p.id: p.roles for p in mission.players} == roles
    assert store.project(mission.token, host.id)['result'] is None
    assert store.project(mission.token, host.id)['voting'] is None
    assert_privacy(store, mission)
    assert not store.continue_mission(mission.token, host.credential, first_result.id)
    open_initial(store, mission, host, clock)
    assert mission.rounds[0].number == 1 and mission.rounds[0].votes == {}
    assert mission.rounds[0].id != old_round
    with pytest.raises(MissionError):
        store.vote(mission.token, host.credential, old_round, 'A')
    cast(store, mission, ['B','B','A'])
    assert len(mission.results) == 2
    assert mission.results[1].before == first_result.after
    assert mission.metrics.model_dump() == {'infrastructure':76,'public_trust':65,'economy':66,'safety':68}
    assert mission.results[0] == first_result
    assert not store.continue_mission(mission.token, host.credential, first_result.id)
    assert mission.phase == Phase.DECISION_LOCKED and mission.crisis_index == 1
    last = mission.results[-1]
    assert store.continue_mission(mission.token, host.credential, last.id)
    assert mission.phase == Phase.COMPLETED and mission.consensus_score == 68.75
    assert not store.continue_mission(mission.token, host.credential, last.id)
    before = mission.model_dump()
    store._resolve(mission)
    store._apply_consequences(mission)
    assert not store.advance_due(mission.token)
    assert mission.model_dump() == before
    with pytest.raises(MissionError):
        store.begin_discussion(mission.token, host.credential)


@pytest.mark.parametrize('count', [1,2,10])
def test_completion_uses_configured_length(count):
    sequence = [load_initial_crisis().model_copy(deep=True) for _ in range(count)]
    for index, crisis in enumerate(sequence):
        crisis.id = f'fixture-{index}'
        for choice in crisis.choices:
            choice.metric_deltas = MetricDeltas(infrastructure=0, public_trust=0, economy=0, safety=0)
    store, mission, host, clock = team(sequence)
    for index in range(count):
        resolve(store, mission, host, clock, 'initial_plurality')
        assert mission.phase == Phase.DECISION_LOCKED
        assert mission.crisis_index == index
        store.continue_mission(mission.token, host.credential, mission.results[-1].id)
        assert mission.phase == (Phase.COMPLETED if index == count - 1 else Phase.BRIEFING)
    assert mission.consensus_score == 70
    assert len(mission.results) == count and len(mission.sequence) == count


def test_continue_authority_phase_and_presence_guards():
    store, mission, host, clock = team()
    with pytest.raises(MissionError):
        store.continue_mission(mission.token, host.credential, 'missing')
    resolve(store, mission, host, clock, 'initial_plurality')
    result_id = mission.results[-1].id
    for credential in ['wrong', mission.players[1].credential]:
        with pytest.raises(MissionError):
            store.continue_mission(mission.token, credential, result_id)
    with pytest.raises(MissionError):
        store.continue_mission(mission.token, host.credential, 'wrong result')
    mission.players[1].connected = False
    with pytest.raises(MissionError):
        store.continue_mission(mission.token, host.credential, result_id)
    assert not mission.acknowledged_results
    mission.players[1].connected = True
    assert store.continue_mission(mission.token, host.credential, result_id)


def test_two_missions_do_not_share_sequence_or_metrics():
    sequence = fixture_sequence()
    store, mission, host, clock = team(sequence)
    other, other_host = store.create('Other')
    store.join(other.token, 'Other guest')
    for p in other.players: p.connected = True
    store.start(other.token, other_host.credential)
    resolve(store, mission, host, clock, 'initial_plurality')
    assert other.metrics == Metrics()
    mission.sequence[1].private_intelligence[next(iter(mission.sequence[1].private_intelligence))] = 'changed internal fixture'
    assert other.sequence[1] != mission.sequence[1]


def test_duplicate_continue_under_actual_transport_lock_advances_once():
    clock = Clock()
    app = create_app(clock, fixture_sequence)
    with TestClient(app) as client:
        session = create(client)
        token = session['token']
        guest = client.post(f'/api/missions/{token}/join',json={'callsign':'Guest'}).json()
        async def prepare():
            async with app.state.lock:
                store = app.state.missions
                mission = store.get(token)
                for p in mission.players: p.connected = True
                store.start(token,session['credential'])
                store.begin_discussion(token,session['credential'])
                expire(store,mission,clock)
                cast(store,mission,['B','B'])
                return mission.results[-1].id
        result_id = client.portal.call(prepare)
        url = f'/api/missions/{token}/continue'
        def advance():
            return client.post(url, headers={'X-Mission-Session':session['credential']}, json={'result_id':result_id})
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: advance(), range(2)))
        assert [r.status_code for r in responses] == [200,200]
        assert sorted(r.json()['advanced'] for r in responses) == [False,True]
        assert app.state.missions.get(token).crisis_index == 1
        assert client.post(url,headers={'X-Mission-Session':guest['credential']},json={'result_id':result_id}).status_code == 403
        assert client.post(url,headers={'X-Mission-Session':session['credential']},json={'result_id':result_id,'metrics':{}}).status_code == 422


@pytest.mark.parametrize('collapse', [False, True])
def test_websocket_result_progression_terminal_and_reconnect_consistency(collapse):
    clock = Clock()
    sequence = fixture_sequence()
    if collapse:
        sequence[0].choices[1].metric_deltas.safety = -70
    app = create_app(clock, lambda: sequence)
    with TestClient(app) as client:
        host = create(client)
        token = host['token']
        sessions = [host] + [client.post(f'/api/missions/{token}/join',json={'callsign':name}).json() for name in ['Lee','Chen']]
        url = f'/api/missions/{token}/ws'
        with ExitStack() as stack:
            sockets = []
            for session in sessions:
                socket = stack.enter_context(client.websocket_connect(url))
                authenticate(socket,session['credential'])
                for prior in sockets: prior.receive_json()
                sockets.append(socket)
            def states():
                frames = [s.receive_json()['mission'] for s in sockets]
                for key in ['phase','metrics','decision','result','crisis_number','collapsed_metrics','consensus_score']:
                    assert all(s[key] == frames[0][key] for s in frames)
                return frames
            def post(action, body=None):
                response = client.post(f'/api/missions/{token}/{action}',headers={'X-Mission-Session':host['credential']},json=body)
                assert response.status_code == 200
                return states()
            def tick():
                async def advance():
                    async with app.state.lock: clock.now = app.state.missions.get(token).deadline
                    await app.state.tick()
                client.portal.call(advance)
                return states()
            def vote(choices, round_id):
                for socket, choice in zip(sockets,choices):
                    socket.send_json({'type':'vote','round_id':round_id,'choice_id':choice})
                    frames = states()
                return frames
            post('start'); post('discussion')
            initial = tick()
            result = vote(['B','B','A'],initial[0]['voting']['round_id'])
            assert result[0]['result']['after'] == result[0]['metrics']
            expected_phase = 'failed' if collapse else 'decision_locked'
            assert result[0]['phase'] == expected_phase
            with client.websocket_connect(url) as refreshed:
                restored = authenticate(refreshed,host['credential'])
                for key in ['result','metrics','phase','roles','crisis_number']:
                    assert restored[key] == result[0][key]
                states()
            states()
            if collapse:
                assert result[0]['collapsed_metrics'] == ['safety']
                assert client.post(f'/api/missions/{token}/continue',headers={'X-Mission-Session':host['credential']},json={'result_id':result[0]['result']['id']}).status_code == 409
            else:
                second = post('continue',{'result_id':result[0]['result']['id']})
                assert second[0]['phase'] == 'briefing' and second[0]['crisis_number'] == 2
                assert second[0]['metrics'] == result[0]['metrics']
                assert all(s['voting'] is None and s['decision'] is None and s['result'] is None for s in second)
                assert_privacy(app.state.missions,app.state.missions.get(token))
                post('discussion')
                voting = tick()
                # Exercise the second-crisis tie handoff and final-vote reset.
                consensus = vote(['A','B','C'],voting[0]['voting']['round_id'])
                assert consensus[0]['phase'] == 'consensus_window'
                final = tick()
                result = vote(['B','B','A'],final[0]['voting']['round_id'])
                assert result[0]['decision']['reason'] == 'final_plurality'
                completed = post('continue',{'result_id':result[0]['result']['id']})
                assert completed[0]['phase'] == 'completed'
                assert completed[0]['consensus_score'] == 68.75
                assert completed[0]['result'] == result[0]['result']
        with client.websocket_connect(url) as refreshed:
            restored = authenticate(refreshed,host['credential'])
            assert restored['phase'] == ('failed' if collapse else 'completed')
            assert restored['metrics'] == result[0]['metrics']
            assert restored['result'] == result[0]['result']
