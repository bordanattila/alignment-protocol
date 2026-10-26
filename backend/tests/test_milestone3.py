"""Controlled-clock rule, transport, privacy and concurrency verification."""
import asyncio
import json
from contextlib import ExitStack
from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocket
from fastapi.testclient import TestClient

from app.connections import LobbyConnections
from app.domain import ChatIntent, Phase, VoteIntent
from app.main import create_app
from app.missions import MissionError, MissionStore
from app.voting import plurality
from test_foundation import authenticate, create


class Clock:
    def __init__(self):
        self.now = 1_000.0

    def __call__(self):
        return self.now


def setup(count=4):
    clock = Clock()
    store = MissionStore(clock)
    mission, host = store.create('Host')
    for i in range(count - 1):
        store.join(mission.token, f'Guest {i}')
    for player in mission.players:
        player.connected = True
    store.start(mission.token, host.credential)
    store.begin_discussion(mission.token, host.credential)
    return store, mission, clock


def expire(store, mission, clock):
    clock.now = mission.deadline
    assert store.advance_due(mission.token)


def cast(store, mission, choices):
    round_id = mission.rounds[-1].id
    for player, choice in zip(mission.players, choices):
        store.vote(mission.token, player.credential, round_id, choice)


@pytest.mark.parametrize('votes,leaders', [
    (['A','A','B','C'], ['A']), (['A','B','B','C'], ['B']),
    (['A','B','C'], ['A','B','C']), (['A','A','B','B'], ['A','B']),
    (['A','B'], ['A','B']), (['A'], ['A']), ([], []),
])
def test_pure_plurality(votes, leaders):
    totals, result = plurality(['A','B','C'], votes)
    assert result == leaders and sum(totals.values()) == len(votes)


def test_deadlines_and_duplicate_or_stale_ticks():
    store, mission, clock = setup()
    assert mission.deadline == 1060
    clock.now = 1059.999
    assert not store.advance_due(mission.token)
    expire(store, mission, clock)
    assert mission.phase == Phase.VOTING and mission.deadline == 1090
    assert len(mission.rounds) == 1
    for _ in range(3):
        assert not store.advance_due(mission.token)
    cast(store, mission, ['A','A','B','B'])
    assert mission.phase == Phase.CONSENSUS_WINDOW and mission.deadline == 1080
    assert not store.advance_due(mission.token)
    clock.now = 1079.999
    assert not store.advance_due(mission.token)
    expire(store, mission, clock)
    assert mission.rounds[-1].number == 2 and mission.deadline == 1110
    assert mission.rounds[-1].votes == {}
    assert not store.advance_due(mission.token)
    expire(store, mission, clock)
    assert mission.decision.reason == 'no_vote_ai_fallback'
    assert mission.decision.abstentions == 4
    clock.now += 1000
    assert not store.advance_due(mission.token)
    assert len(mission.rounds) == 2 and mission.deadline is None


@pytest.mark.parametrize('choices,phase', [
    (['A','A','B','C'], Phase.DECISION_LOCKED),
    (['A','A','B','B'], Phase.CONSENSUS_WINDOW),
    (['A','B','C'], Phase.CONSENSUS_WINDOW),
    (['A','B'], Phase.CONSENSUS_WINDOW),
])
def test_initial_distribution(choices, phase):
    store, mission, clock = setup(len(choices))
    expire(store, mission, clock)
    cast(store, mission, choices)
    assert mission.phase == phase
    if phase == Phase.DECISION_LOCKED:
        assert mission.decision.choice_id == 'A'
        assert mission.decision.reason == 'initial_plurality'
    if mission.decision:
        assert mission.metrics.model_dump() == {'infrastructure':78, 'public_trust':62, 'economy':72, 'safety':64}
    else:
        assert set(mission.metrics.model_dump().values()) == {70}


@pytest.mark.parametrize('choices,reason,winner', [
    (['B','B'], 'final_plurality', 'B'), (['B','C'], 'ai_tie_break', 'A'),
])
def test_fresh_final_votes(choices, reason, winner):
    store, mission, clock = setup(2)
    expire(store, mission, clock)
    first_id = mission.rounds[-1].id
    cast(store, mission, ['A','B'])
    assert mission.rounds[0].totals == {'A':1,'B':1,'C':0}
    expire(store, mission, clock)
    with pytest.raises(MissionError):
        store.vote(mission.token, mission.players[0].credential, first_id, 'C')
    cast(store, mission, choices)
    assert mission.decision.reason == reason and mission.decision.choice_id == winner
    assert mission.rounds[0].votes != mission.rounds[1].votes
    assert len(mission.rounds) == 2


@pytest.mark.parametrize('votes,expected,abstentions', [([], 'no_vote_ai_fallback', 4), (['B'], 'initial_plurality', 3), (['A','B'], None, 2)])
def test_deadline_nonresponses(votes, expected, abstentions):
    store, mission, clock = setup()
    expire(store, mission, clock)
    cast(store, mission, votes)
    mission.players[-1].connected = False
    expire(store, mission, clock)
    assert mission.rounds[0].abstentions == abstentions
    assert sum(mission.rounds[0].totals.values()) == len(votes)
    if expected:
        assert mission.decision.reason == expected
        assert mission.decision.choice_id == ('B' if votes else 'A')
    else:
        assert mission.phase == Phase.CONSENSUS_WINDOW


def test_vote_authorization_and_validation():
    store, mission, clock = setup(2)
    with pytest.raises(MissionError):
        store.vote(mission.token, mission.players[0].credential, 'wrong', 'A')
    expire(store, mission, clock)
    current = mission.rounds[-1]
    for credential, round_id, choice in [('wrong',current.id,'A'), (mission.players[0].credential,'stale','A'), (mission.players[0].credential,current.id,'invalid')]:
        with pytest.raises(MissionError):
            store.vote(mission.token, credential, round_id, choice)
    other, outsider = store.create('Outsider')
    with pytest.raises(MissionError):
        store.vote(mission.token, outsider.credential, current.id, 'A')
    cast(store, mission, ['B'])
    with pytest.raises(MissionError):
        store.vote(mission.token, mission.players[0].credential, current.id, 'C')
    assert len(mission.players[0].roles) == 2 and len(current.votes) == 1
    assert current.eligible == [p.id for p in mission.players]
    mission.players[1].connected = False
    assert current.eligible == [p.id for p in mission.players]
    mission.players[1].connected = True
    store.vote(mission.token, mission.players[1].credential, current.id, 'B')
    with pytest.raises(MissionError):
        store.vote(mission.token, mission.players[1].credential, current.id, 'A')
    assert store.get(other.token).rounds == []


def test_private_vote_and_intelligence_projection():
    store, mission, clock = setup()
    expire(store, mission, clock)
    cast(store, mission, ['B'])
    first, second = [store.project(mission.token, p.id) for p in mission.players[:2]]
    assert first['voting']['your_vote'] == 'B'
    assert second['voting']['your_vote'] is None
    assert second['voting']['submitted_count'] == 1
    assert second['closed_rounds'] == [] and second['decision'] is None
    assert 'votes' not in second and 'eligible' not in second
    public_first = {k:v for k,v in first.items() if k not in ('you','roles','private_intelligence','voting')}
    public_second = {k:v for k,v in second.items() if k not in ('you','roles','private_intelligence','voting')}
    assert public_first == public_second
    for p in mission.players:
        state = store.project(mission.token, p.id)
        for role, secret in mission.crisis.private_intelligence.items():
            assert (secret in json.dumps(state)) == (role in p.roles)
    with pytest.raises(MissionError):
        store.project(mission.token, 'outsider')


def test_chat_security_retention_rate_and_phases():
    store, mission, clock = setup(2)
    host = mission.players[0]
    _, outsider = store.create('Outsider')
    with pytest.raises(MissionError):
        store.send_chat(mission.token, outsider.credential, 'cross-mission')
    for bad in ['', '  ', 'x'*501, 123]:
        with pytest.raises(MissionError):
            store.send_chat(mission.token, host.credential, bad)
    text = '<script>alert("x")</script>'
    store.send_chat(mission.token, host.credential, text)
    message = mission.chat[0]
    assert message.callsign == host.callsign and message.sender_id == host.id
    assert message.text == text and message.timestamp == clock.now
    with pytest.raises(MissionError) as exc:
        store.send_chat(mission.token, host.credential, 'flood')
    assert exc.value.status == 429
    # Stay in discussion while testing retention; fake time can be controlled
    # independently from this phase deadline.
    mission.deadline = clock.now + 1000
    for i in range(101):
        clock.now += 1
        store.send_chat(mission.token, host.credential, str(i))
    assert len(mission.chat) == 100
    assert len({m.id for m in mission.chat}) == 100
    assert mission.chat[0].text == '1' and mission.chat[-1].text == '100'
    assert [m.timestamp for m in mission.chat] == sorted(m.timestamp for m in mission.chat)
    assert store.project(mission.token, mission.players[1].id)['chat'] == store.project(mission.token, host.id)['chat']
    expire(store, mission, clock)
    with pytest.raises(MissionError):
        store.send_chat(mission.token, host.credential, 'closed')
    cast(store, mission, ['A','B'])
    store.send_chat(mission.token, host.credential, 'negotiate')
    expire(store, mission, clock)
    cast(store, mission, ['B','B'])
    with pytest.raises(MissionError):
        store.send_chat(mission.token, host.credential, 'locked')


@pytest.mark.parametrize('model,payload', [
    (ChatIntent, {'type':'chat','text':'hello','callsign':'forged'}),
    (ChatIntent, {'type':'chat','text':123}),
    (ChatIntent, {'type':'chat','text':'x'*501}),
    (VoteIntent, {'type':'vote','round_id':'x','choice_id':'A','sender_id':'forged'}),
])
def test_strict_intents(model, payload):
    with pytest.raises(ValueError):
        model.model_validate(payload)


@pytest.mark.parametrize('timeout_first', [False, True])
def test_last_vote_and_timeout_are_atomic(timeout_first):
    async def run():
        store, mission, clock = setup(2)
        expire(store, mission, clock)
        cast(store, mission, ['B'])
        round_id = mission.rounds[-1].id
        clock.now = mission.deadline
        lock = asyncio.Lock()
        async def vote():
            async with lock:
                with pytest.raises(MissionError):
                    store.vote(mission.token, mission.players[1].credential, round_id, 'C')
        async def timeout():
            async with lock:
                store.advance_due(mission.token)
        await asyncio.gather(*( [timeout(), vote()] if timeout_first else [vote(), timeout()] ))
        assert mission.phase == Phase.DECISION_LOCKED
        assert mission.decision.reason == 'initial_plurality'
        assert mission.decision.abstentions == 1
        assert mission.decision.totals == {'A':0,'B':1,'C':0}
        before = mission.model_dump()
        assert not store.advance_due(mission.token)
        assert mission.model_dump() == before
    asyncio.run(run())


def test_delivery_does_not_hold_state_lock():
    async def run():
        store, mission, clock = setup(2)
        lock = asyncio.Lock()
        connections = LobbyConnections(store, lock)
        started, release = asyncio.Event(), asyncio.Event()
        socket = AsyncMock(spec=WebSocket)
        async def send(_frame):
            started.set()
            await release.wait()
        socket.send_json.side_effect = send
        connections.add(mission.token, mission.players[0].id, socket)
        delivery = asyncio.create_task(connections.broadcast(mission.token))
        await started.wait()
        async with asyncio.timeout(1):
            async with lock:
                expire(store, mission, clock)
        release.set()
        await delivery
        assert mission.phase == Phase.VOTING
    asyncio.run(run())


def test_complete_transport_cycle_reconnect_errors_and_scheduler_cleanup():
    clock = Clock()
    app = create_app(clock)
    with TestClient(app) as client:
        host = create(client)
        token = host['token']
        guest = client.post(f'/api/missions/{token}/join', json={'callsign':'Guest'}).json()
        url = f'/api/missions/{token}/ws'
        with ExitStack() as stack:
            sockets = [stack.enter_context(client.websocket_connect(url)) for _ in range(2)]
            authenticate(sockets[0], host['credential'])
            authenticate(sockets[1], guest['credential'])
            sockets[0].receive_json()
            headers = {'X-Mission-Session':host['credential']}
            assert client.post(f'/api/missions/{token}/start', headers=headers).status_code == 200
            for socket in sockets: socket.receive_json()
            # Chat cannot be posted before discussion.
            sockets[0].send_json({'type':'chat','text':'too early'})
            for socket in sockets: socket.receive_json()
            assert sockets[0].receive_json()['type'] == 'error'
            assert client.post(f'/api/missions/{token}/discussion', headers=headers).status_code == 200
            states = [s.receive_json()['mission'] for s in sockets]
            deadline = states[0]['deadline']
            def refresh(expected, vote=None):
                with client.websocket_connect(url) as tab:
                    state = authenticate(tab, host['credential'])
                    assert state['phase'] == expected
                    assert state['deadline'] == app.state.missions.get(token).deadline
                    assert state['roles'] == states[0]['roles']
                    if state['voting']: assert state['voting']['your_vote'] == vote
                    for socket in sockets: socket.receive_json()
                for socket in sockets: socket.receive_json()
                return state
            assert refresh('discussion')['deadline'] == deadline
            sockets[0].send_json({'type':'chat','text':'forged','sender_id':'fake'})
            assert sockets[0].receive_json()['type'] == 'error'
            sockets[0].send_json({'type':'chat','text':'x'*501})
            assert sockets[0].receive_json()['type'] == 'error'
            sockets[0].send_json({'type':'chat','text':'Compare the tradeoffs'})
            for socket in sockets:
                state = socket.receive_json()['mission']
                assert state['chat'][0]['callsign'] == 'Rivera'
            def tick():
                async def advance():
                    async with app.state.lock:
                        clock.now = app.state.missions.get(token).deadline
                    await app.state.tick()
                client.portal.call(advance)
                return [s.receive_json()['mission'] for s in sockets]
            vote_states = tick()
            first_id = vote_states[0]['voting']['round_id']
            sockets[0].send_json({'type':'vote','round_id':first_id,'choice_id':'A'})
            frames = [s.receive_json()['mission'] for s in sockets]
            assert frames[0]['voting']['your_vote'] == 'A'
            assert frames[1]['voting']['your_vote'] is None
            refresh('voting','A')
            sockets[1].send_json({'type':'vote','round_id':first_id,'choice_id':'B'})
            assert all(s.receive_json()['mission']['phase'] == 'consensus_window' for s in sockets)
            refresh('consensus_window','A')
            final_states = tick()
            final_id = final_states[0]['voting']['round_id']
            assert final_id != first_id and final_states[0]['voting']['your_vote'] is None
            sockets[0].send_json({'type':'vote','round_id':first_id,'choice_id':'C'})
            for socket in sockets: socket.receive_json()
            assert sockets[0].receive_json()['type'] == 'error'
            for socket, choice in zip(sockets, ['B','C']):
                socket.send_json({'type':'vote','round_id':final_id,'choice_id':choice})
                result = [s.receive_json()['mission'] for s in sockets]
            assert result[0]['decision'] == result[1]['decision']
            assert result[0]['decision']['reason'] == 'ai_tie_break'
            assert result[0]['decision']['choice_id'] == 'A'
            assert refresh('decision_locked','B')['decision'] == result[0]['decision']
        # Real disconnect/reconnect restores the same locked seat and result.
        with client.websocket_connect(url) as socket:
            state = authenticate(socket, host['credential'])
            assert state['decision'] == result[0]['decision']
            assert state['voting']['your_vote'] == 'B'

    assert app.state.scheduler_task.done()


def test_last_vote_before_deadline_makes_old_timeout_harmless():
    store, mission, clock = setup(2)
    expire(store, mission, clock)
    old_deadline = mission.deadline
    cast(store, mission, ['A'])
    clock.now = old_deadline - .001
    store.vote(mission.token, mission.players[1].credential, mission.rounds[-1].id, 'B')
    assert mission.phase == Phase.CONSENSUS_WINDOW
    new_deadline = mission.deadline
    clock.now = old_deadline
    assert not store.advance_due(mission.token)
    assert mission.deadline == new_deadline
    assert len(mission.rounds) == 1


def test_actual_disconnect_during_open_vote_keeps_eligibility_and_own_vote():
    store, mission, clock = setup(2)
    expire(store, mission, clock)
    cast(store, mission, ['B'])
    current = mission.rounds[-1]
    original = store.project(mission.token, mission.players[0].id)
    for player in mission.players:
        store.set_connected(mission.token, player.id, False)
    for player in mission.players:
        restored_mission, restored = store.join(mission.token, 'ignored', player.credential)
        assert restored.id == player.id and restored_mission is mission
        store.set_connected(mission.token, player.id, True)
    state = store.project(mission.token, mission.players[0].id)
    for field in ['deadline', 'voting', 'roles', 'crisis', 'private_intelligence']:
        assert state[field] == original[field]
    store.vote(mission.token, mission.players[1].credential, current.id, 'B')
    assert mission.decision.totals == {'A':0,'B':2,'C':0}
