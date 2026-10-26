import json
from contextlib import ExitStack

import pytest

from app.crises import load_initial_crisis
from app.domain import Phase, Role
from app.missions import MissionError, MissionStore
from test_foundation import authenticate, client, create


def team(count):
    store = MissionStore()
    mission, host = store.create('Host')
    for index in range(count - 1):
        store.join(mission.token, f'Guest {index}')
    for player in mission.players:
        store.set_connected(mission.token, player.id, True)
    return store, mission, host


@pytest.mark.parametrize('count,distribution', [(2, [2, 2]), (3, [1, 1, 2]), (4, [1, 1, 1, 1])])
def test_roles_and_private_projections(count, distribution):
    store, mission, host = team(count)
    store.start(mission.token, host.credential)
    assert mission.phase == Phase.BRIEFING
    assert sorted(len(p.roles) for p in mission.players) == distribution
    roles = [r for p in mission.players for r in p.roles]
    assert len(roles) == 4 and set(roles) == set(Role)
    common = None
    for player in mission.players:
        state = store.project(mission.token, player.id)
        assert state['roles'] == player.roles
        assert set(state['private_intelligence']) == set(player.roles)
        assert state['crisis'] == (common or state['crisis'])
        common = state['crisis']
        assert common['briefing'] == mission.crisis.briefing
        assert common['ai_recommendation_choice_id'] == 'A'
        shared = json.dumps({k: v for k, v in state.items() if k != 'private_intelligence'})
        full = json.dumps(state)
        for role, secret in mission.crisis.private_intelligence.items():
            assert secret not in shared
            assert (secret in full) == (role in player.roles)
        assert 'consequence' not in full and 'metric_deltas' not in full
    before = mission.model_dump()
    with pytest.raises(MissionError):
        store.start(mission.token, host.credential)
    assert mission.model_dump() == before


def test_authored_content():
    crisis = load_initial_crisis()
    assert crisis.id == 'grid-under-pressure'
    assert crisis.title == 'Grid Under Pressure'
    assert len(crisis.choices) == 3
    assert set(crisis.private_intelligence) == set(Role)


def test_guards_and_transitions():
    store, mission, host = team(1)
    with pytest.raises(MissionError):
        store.start(mission.token, host.credential)
    _, guest = store.join(mission.token, 'Guest')
    with pytest.raises(MissionError):
        store.start(mission.token, host.credential)
    guest.connected = True
    with pytest.raises(MissionError) as error:
        store.start(mission.token, guest.credential)
    assert error.value.status == 403
    with pytest.raises(MissionError):
        store.start(mission.token, 'wrong')
    with pytest.raises(MissionError):
        store.begin_discussion(mission.token, host.credential)
    assert mission.phase == Phase.LOBBY and not host.roles
    store.start(mission.token, host.credential)
    with pytest.raises(MissionError):
        store.join(mission.token, 'Late')
    with pytest.raises(MissionError):
        store.begin_discussion(mission.token, guest.credential)
    guest.connected = False
    with pytest.raises(MissionError):
        store.begin_discussion(mission.token, host.credential)
    guest.connected = True
    store.begin_discussion(mission.token, host.credential)
    assert mission.phase == Phase.DISCUSSION
    with pytest.raises(MissionError):
        store.begin_discussion(mission.token, host.credential)


@pytest.mark.parametrize('count', [2, 3, 4])
def test_http_websocket_delivery_and_refresh(client, count):
    host = create(client)
    token = host['token']
    sessions = [host] + [client.post(f'/api/missions/{token}/join', json={'callsign': f'Guest {i}'}).json() for i in range(count - 1)]
    url = f'/api/missions/{token}/ws'
    with ExitStack() as stack:
        sockets = []
        for session in sessions:
            socket = stack.enter_context(client.websocket_connect(url))
            authenticate(socket, session['credential'])
            for other in sockets:
                other.receive_json()
            sockets.append(socket)
        def action(name, credential):
            return client.post(f'/api/missions/{token}/{name}', headers={'X-Mission-Session': credential})
        assert action('start', sessions[1]['credential']).status_code == 403
        assert action('start', 'wrong').status_code == 401
        assert action('start', host['credential']).status_code == 200
        states = [s.receive_json()['mission'] for s in sockets]
        assert all(s['phase'] == 'briefing' for s in states)
        assert all(s['crisis'] == states[0]['crisis'] for s in states)
        for state in states:
            assert set(state['private_intelligence']) == set(state['roles'])
            for role, text in load_initial_crisis().private_intelligence.items():
                assert (text in json.dumps(state)) == (role in state['roles'])
        assert action('start', host['credential']).status_code == 409
        assert action('discussion', host['credential']).status_code == 200
        for socket in sockets:
            assert socket.receive_json()['mission']['phase'] == 'discussion'
    restored = client.post(f'/api/missions/{token}/join', json={'callsign': 'Ignored'}, headers={'X-Mission-Session': host['credential']})
    assert restored.json() == host
    with client.websocket_connect(url) as refreshed:
        state = authenticate(refreshed, host['credential'])
        assert state['phase'] == 'discussion'
        for key in ['you', 'roles', 'crisis', 'private_intelligence']:
            assert state[key] == states[0][key]
        assert len(state['players']) == count


def test_cannot_start_with_one_connected_player(client):
    host = create(client)
    with client.websocket_connect(f"/api/missions/{host['token']}/ws") as socket:
        authenticate(socket, host['credential'])
        assert client.post(f"/api/missions/{host['token']}/start", headers={'X-Mission-Session': host['credential']}).status_code == 409
