"""Room-scoped normalized names, real lock concurrency and stable seat recovery."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.crises import load_initial_crisis
from app.missions import MissionError, MissionStore
from test_foundation import client, create, authenticate
from test_milestone3 import Clock


@pytest.mark.parametrize('existing,attempt', [
    ('Eagel2','Eagel2'), ('Eagle1','eagle1'), ('Eagle1','EAGLE1'),
    ('Eagle1',' Eagle1 '), ('Eagle1','\tEagle1\n'), ('Eagle1','\u00a0Eagle1\u00a0'),
    ('Eagle1','Ｅａｇｌｅ１'), ('Éagle','E\u0301agle'),
    ('Straße','STRASSE'), ('Eagle 2','Eagle  2'),
])
def test_duplicates_do_not_allocate_seats_and_have_stable_code(client, existing, attempt):
    host = create(client,existing)
    store = client.app.state.missions
    before = store.get(host['token']).model_dump()
    response = client.post(f"/api/missions/{host['token']}/join",json={'callsign':attempt})
    assert response.status_code == 409
    assert response.json() == {'code':'callsign_taken','detail':'That callsign is already taken in this mission. Choose another.'}
    assert store.get(host['token']).model_dump() == before


@pytest.mark.parametrize('suffix', ['\u200b','\u200d','\u202e','\x00','\nHidden'])
def test_invisible_formatting_cannot_create_a_visually_identical_seat(client, suffix):
    host = create(client,'Eagel2')
    response = client.post(f"/api/missions/{host['token']}/join",json={'callsign':'Eagel2'+suffix})
    assert response.status_code == 422
    assert len(client.app.state.missions.get(host['token']).players) == 1


def test_direct_store_uses_same_normalization_and_reconnect_precedes_name_validation():
    store = MissionStore()
    mission, host = store.create('  Éagle  ')
    assert host.callsign == 'Éagle'
    for name in ['E\u0301agle','  Éagle ','ÉAGLE']:
        with pytest.raises(MissionError) as exc:
            store.join(mission.token,name)
        assert exc.value.code == 'callsign_taken'
    # Valid credential restores the original seat; the attempted new name has
    # no authority, including a value not valid for a new seat.
    _, restored = store.join(mission.token,'\u200b',host.credential)
    assert restored is host and restored.callsign == 'Éagle'
    assert len(mission.players) == 1
    with pytest.raises(MissionError):
        store.join(mission.token,'Éagle','wrong')
    with pytest.raises(MissionError):
        store.create('Invalid\u200b')


def test_different_names_and_same_names_in_different_rooms(client):
    first = create(client,'Eagle1')
    second = create(client,'Eagle1')
    for session in [first,second]:
        assert client.post(f"/api/missions/{session['token']}/join",json={'callsign':'Eagle2'}).status_code == 200
        assert client.post(f"/api/missions/{session['token']}/join",json={'callsign':'Eagle3'}).status_code == 200
        assert len(client.app.state.missions.get(session['token']).players) == 3


@pytest.mark.parametrize('names', [('Eagle2','Eagle2'), ('Eagle2',' EAGLE2 '), ('Éagle','E\u0301agle')])
def test_concurrent_duplicate_joins_use_the_existing_atomic_room_lock(client, names):
    host = create(client,'Eagle1')
    def join(name):
        return client.post(f"/api/missions/{host['token']}/join",json={'callsign':name})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(join,names))
    assert sorted(r.status_code for r in responses) == [200,409]
    assert next(r for r in responses if r.status_code == 409).json()['code'] == 'callsign_taken'
    assert len(client.app.state.missions.get(host['token']).players) == 2


def test_reserved_disconnected_name_cannot_be_impersonated(client):
    host = create(client,'Eagle1')
    token = host['token']
    guest = client.post(f'/api/missions/{token}/join',json={'callsign':'Eagle2'}).json()
    response = client.post(f'/api/missions/{token}/join',json={'callsign':'Eagle2'})
    assert response.status_code == 409
    restored = client.post(f'/api/missions/{token}/join',json={'callsign':'Different name'},headers={'X-Mission-Session':guest['credential']})
    assert restored.json() == guest
    mission = client.app.state.missions.get(token)
    assert mission.players[1].callsign == 'Eagle2' and len(mission.players) == 2


def test_three_client_identity_and_completed_score_restore():
    clock = Clock()
    app = create_app(clock, lambda: [load_initial_crisis()])
    with TestClient(app) as client:
        host = create(client,'Eagle1')
        token = host['token']
        guest = client.post(f'/api/missions/{token}/join',json={'callsign':'Eagle2'}).json()
        duplicate = client.post(f'/api/missions/{token}/join',json={'callsign':'Eagle2'})
        assert duplicate.status_code == 409
        assert len(app.state.missions.get(token).players) == 2
        third = client.post(f'/api/missions/{token}/join',json={'callsign':'Eagle3'}).json()
        url = f'/api/missions/{token}/ws'
        headers = {'X-Mission-Session':host['credential']}
        with ExitStack() as stack:
            sockets = []
            for session in [host,guest,third]:
                socket = stack.enter_context(client.websocket_connect(url))
                authenticate(socket,session['credential'])
                for prior in sockets: prior.receive_json()
                sockets.append(socket)
            def states(): return [socket.receive_json()['mission'] for socket in sockets]
            assert client.post(f'/api/missions/{token}/start',headers=headers).status_code == 200
            original = states()
            assert [p['callsign'] for p in original[0]['players']] == ['Eagle1','Eagle2','Eagle3']
            with client.websocket_connect(url) as refresh:
                restored = authenticate(refresh,guest['credential'])
                for key in ['you','roles','crisis','phase','private_intelligence']:
                    assert restored[key] == original[1][key]
                states()
            states()
            assert client.post(f'/api/missions/{token}/discussion',headers=headers).status_code == 200
            states()
            async def advance():
                async with app.state.lock: clock.now = app.state.missions.get(token).deadline
                await app.state.tick()
            client.portal.call(advance)
            voting = states()
            for socket, choice in zip(sockets,['A','A','B']):
                socket.send_json({'type':'vote','round_id':voting[0]['voting']['round_id'],'choice_id':choice})
                result = states()
            assert client.post(f'/api/missions/{token}/continue',headers=headers,json={'result_id':result[0]['result']['id']}).status_code == 200
            completed = states()
            assert all(s['phase'] == 'completed' and s['consensus_score'] == 69 for s in completed)
        # Actual all-sockets-closed recovery, including role and original callsign.
        with client.websocket_connect(url) as refresh:
            restored = authenticate(refresh,guest['credential'])
            assert restored['you'] == original[1]['you']
            assert restored['roles'] == original[1]['roles']
            assert restored['consensus_score'] == 69
            assert restored['metrics'] == {'infrastructure':78,'public_trust':62,'economy':72,'safety':64}
            assert next(p for p in restored['players'] if p['id'] == restored['you'])['callsign'] == 'Eagle2'
            assert len(restored['players']) == 3


def test_preexisting_legacy_invisible_seat_does_not_break_join_or_restore():
    store = MissionStore()
    mission, player = store.create('Eagel2')
    # Simulate a seat created before the normalization fix.
    player.callsign = 'Eagel2\u200b'
    with pytest.raises(MissionError) as error:
        store.join(mission.token, 'Eagel2')
    assert error.value.code == 'callsign_taken'
    _, restored = store.join(mission.token, 'ignored', player.credential)
    assert restored.id == player.id and restored.callsign == 'Eagel2\u200b'
    assert len(mission.players) == 1


def test_duplicate_code_is_stable_even_when_lobby_is_full(client):
    host = create(client,'Eagle1')
    token = host['token']
    for name in ['Eagle2','Eagle3','Eagle4']:
        assert client.post(f'/api/missions/{token}/join',json={'callsign':name}).status_code == 200
    response = client.post(f'/api/missions/{token}/join',json={'callsign':' eagle2 '})
    assert response.status_code == 409 and response.json()['code'] == 'callsign_taken'
    assert len(client.app.state.missions.get(token).players) == 4
