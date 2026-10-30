"""Private deployment access must guard both transports before game handlers."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from app.railway import SitesGateway, create_railway_app


KEY = 'test-only-gateway-key-' + 'x' * 32
ORIGIN = 'https://private-site.example'
HEADERS = {'X-Consensus-Gateway-Key': KEY, 'Origin': ORIGIN}


def test_gateway_protects_http_and_websocket_and_preserves_identity(tmp_path):
    gateway = SitesGateway(create_app(database_path=tmp_path / 'missions.sqlite3'), KEY, ORIGIN)
    with TestClient(gateway) as client:
        assert client.get('/api/health').status_code == 200
        assert client.get('/api/capabilities').status_code == 403
        assert client.post('/api/missions', json={'callsign': 'Host'}).status_code == 403
        assert client.post('/api/missions', headers={**HEADERS, 'Origin': 'https://other.example'},
                           json={'callsign': 'Host'}).status_code == 403
        host = client.post('/api/missions', headers=HEADERS, json={'callsign': 'Host'}).json()
        # Knowing an invite or spoofing the Sites Origin must not bypass the key.
        join = f'/api/missions/{host["token"]}/join'
        for spoofed in ({}, {'Origin': ORIGIN}, {'X-Consensus-Gateway-Key': 'wrong', 'Origin': ORIGIN}):
            assert client.post(join, headers=spoofed, json={'callsign': 'Intruder'}).status_code == 403
            assert client.post('/api/missions', headers=spoofed, json={'callsign': 'Intruder'}).status_code == 403
        route = f'/api/missions/{host["token"]}/ws'
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(route):
                pass
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(route, headers={**HEADERS, 'Origin': 'https://other.example'}):
                pass
        with client.websocket_connect(route, headers=HEADERS) as socket:
            socket.send_json({'type': 'authenticate', 'credential': host['credential']})
            before = socket.receive_json()['mission']
            assert before['players'][0]['connected']
            assert KEY not in str(before)
        with client.websocket_connect(route, headers=HEADERS) as socket:
            socket.send_json({'type': 'authenticate', 'credential': host['credential']})
            after = socket.receive_json()['mission']
            assert after['you'] == before['you']
            assert len(after['players']) == 1
    # New application process restores the same persisted mission/credential.
    with TestClient(SitesGateway(create_app(database_path=tmp_path / 'missions.sqlite3'), KEY, ORIGIN)) as client:
        with client.websocket_connect(route, headers=HEADERS) as socket:
            socket.send_json({'type': 'authenticate', 'credential': host['credential']})
            assert socket.receive_json()['mission']['you'] == before['you']


def configure(monkeypatch, tmp_path):
    monkeypatch.setenv('CONSENSUS_GATEWAY_KEY', KEY)
    monkeypatch.setenv('CONSENSUS_SITE_ORIGIN', ORIGIN)
    monkeypatch.setenv('CONSENSUS_LLM_ENABLED', 'false')
    monkeypatch.setenv('RAILWAY_VOLUME_MOUNT_PATH', str(tmp_path))
    monkeypatch.setenv('CONSENSUS_DB_PATH', str(tmp_path / 'missions.sqlite3'))


def test_factory_rejects_unmounted_volume(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    with pytest.raises(RuntimeError, match='persistent volume'):
        create_railway_app()


@pytest.mark.parametrize('setting,value', [
    ('CONSENSUS_GATEWAY_KEY', ''), ('CONSENSUS_GATEWAY_KEY', 'short'),
    ('CONSENSUS_SITE_ORIGIN', 'http://private-site.example'),
    ('CONSENSUS_SITE_ORIGIN', ORIGIN + '/'),
    ('CONSENSUS_SITE_ORIGIN', ORIGIN + '?secret=x'),
    ('CONSENSUS_LLM_ENABLED', 'true'),
    ('CONSENSUS_DB_PATH', '/outside-volume/missions.sqlite3'),
])
def test_factory_rejects_unsafe_configuration(monkeypatch, tmp_path, setting, value):
    configure(monkeypatch, tmp_path)
    monkeypatch.setattr('pathlib.Path.is_mount', lambda _: True)
    monkeypatch.setenv(setting, value)
    with pytest.raises(RuntimeError):
        create_railway_app()


def test_factory_disables_generation_and_keeps_authored_mode(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    monkeypatch.setattr('pathlib.Path.is_mount', lambda _: True)
    with TestClient(create_railway_app()) as client:
        assert client.get('/api/capabilities', headers=HEADERS).json() == {'generated_missions': False}
        response = client.post('/api/missions', headers=HEADERS, json={'callsign': 'Host', 'mode': 'generated'})
        assert response.status_code == 409
        assert response.json()['code'] == 'generation_unavailable'
        assert client.post('/api/missions', headers=HEADERS,
                           json={'callsign': 'Host', 'mode': 'authored'}).status_code == 201
