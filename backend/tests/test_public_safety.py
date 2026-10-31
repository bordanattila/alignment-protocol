"""Deterministic, temporary-storage security and retention regressions."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.backup import backup_database, compact_offline, disk_status, readonly, restore_check, verify
from app.domain import Phase
from app.main import create_app
from app.missions import MissionStore, MissionError
from app.persistence import SQLiteMissions, PersistenceError, canonical
from app.railway import SitesGateway
from app.safety import SafetyControls, SafetyLimit, SafetySettings
from app.safety import SafetyMiddleware
from test_foundation import authenticate, create
from test_milestone3 import Clock
from test_persistence import team, ready, voting, votes


def settings(**kwargs):
    return replace(SafetySettings(), lobby_retention_seconds=300,
                   unfinished_retention_seconds=600, completed_retention_seconds=900, **kwargs)


def store_at(path, clock, limits=None):
    store = MissionStore(clock, persistence=SQLiteMissions(path), safety_settings=limits or settings())
    store.initialize()
    return store


def test_lobby_expiry_uses_committed_activity_not_timer_or_broadcast(tmp_path):
    clock = Clock(); path = tmp_path / 'missions.sqlite3'
    store = store_at(path, clock)
    mission, host = store.create('Host'); token = mission.token
    clock.now += 200
    store.bump_revision(token); store.advance_due(token)
    assert store.activity[token].last_activity == 1000
    store.close(); store = store_at(path, clock)
    assert store.activity[token].last_activity == 1000
    clock.now = 1299; assert store.cleanup_expired() == []
    clock.now = 1300; assert store.cleanup_expired() == [token]
    assert verify(path)['missions'] == 0
    with pytest.raises(MissionError): store.authorize(token, host.credential)
    store.close()


def test_connected_mission_and_legitimate_reconnect_never_expire(tmp_path):
    clock = Clock(); path = tmp_path / 'missions.sqlite3'; store = store_at(path, clock)
    mission, host = store.create('Host'); token = mission.token
    store.set_connected(token, host.id, True)
    clock.now += 100000; assert store.cleanup_expired() == []
    store.set_connected(token, host.id, False)
    clock.now += 299
    assert store.authorize(token, host.credential).id == host.id
    store.set_connected(token, host.id, True)
    store.set_connected(token, host.id, False)
    clock.now += 299; assert store.cleanup_expired() == []
    clock.now += 1; assert store.cleanup_expired() == [token]
    store.close()


def test_unfinished_expiration_and_legacy_full_grace(tmp_path):
    clock = Clock(); path = tmp_path / 'missions.sqlite3'
    store, mission, credentials = team(path, clock)
    token = mission.token; original = store.persistence.payload(mission)
    for player in mission.players: store.set_connected(token, player.id, False)
    store.close()
    with sqlite3.connect(path) as connection:
        connection.execute('DROP TABLE mission_activity')
    clock.now += 100000
    store = store_at(path, clock)
    assert store.persistence.payload(store.get(token)) != ''
    assert store.get(token).players[0].id == mission.players[0].id
    assert store.activity[token].created_at == clock.now
    clock.now += 599; assert store.cleanup_expired() == []
    clock.now += 1; assert store.cleanup_expired() == [token]
    store.close()


def test_finalized_history_immutable_until_whole_mission_retention(tmp_path):
    clock = Clock(); path = tmp_path / 'missions.sqlite3'
    store, mission, credentials = team(path, clock); store.safety_settings = settings()
    for choice in 'BBBCCBCAAC':
        voting(store, mission, credentials, clock); votes(store, mission, credentials, [choice] * 3)
        store.continue_mission(mission.token, credentials[0], mission.results[-1].id)
    assert mission.phase == Phase.COMPLETED
    for player in mission.players: store.set_connected(mission.token, player.id, False)
    with sqlite3.connect(path) as connection:
        hashes = connection.execute('SELECT record_hash FROM resolutions ORDER BY crisis_number').fetchall()
    clock.now += 899; assert store.cleanup_expired() == []
    store.close(); store = store_at(path, clock)
    with sqlite3.connect(path) as connection:
        assert hashes == connection.execute('SELECT record_hash FROM resolutions ORDER BY crisis_number').fetchall()
    clock.now += 1; assert store.cleanup_expired() == [mission.token]
    assert verify(path)['results'] == 0
    store.close()


def test_activity_rolls_back_on_storage_failure_and_invalid_intents_do_not_extend(tmp_path, monkeypatch):
    clock = Clock(); store = store_at(tmp_path / 'db.sqlite3', clock)
    mission, host = store.create('Host'); before = replace(store.activity[mission.token]); clock.now += 20
    with pytest.raises(MissionError): store.join(mission.token, 'Bad', 'wrong')
    assert store.activity[mission.token] == before
    def fail(*_args, **_kwargs): raise PersistenceError('temporary')
    monkeypatch.setattr(store.persistence, 'save', fail)
    with pytest.raises(PersistenceError): store.join(mission.token, 'Guest')
    assert store.activity[mission.token] == before and len(mission.players) == 1
    store.close()


def test_cleanup_failure_preserves_cache_and_rows(tmp_path, monkeypatch):
    clock = Clock(); store = store_at(tmp_path / 'db.sqlite3', clock)
    mission, _ = store.create('Host'); clock.now += 301
    def fail(_tokens): raise PersistenceError('temporary')
    monkeypatch.setattr(store.persistence, 'delete_expired', fail)
    with pytest.raises(PersistenceError): store.cleanup_expired()
    assert store.get(mission.token) == mission
    assert verify(tmp_path / 'db.sqlite3')['missions'] == 1
    store.close()


def test_cleanup_releases_pages_and_offline_compaction_reclaims_disk(tmp_path):
    clock = Clock(); path = tmp_path / 'db.sqlite3'; store = store_at(path, clock)
    for i in range(20):
        mission, host = store.create(f'Host {i}'); store.join(mission.token, 'Guest')
        ready(store, mission); store.start(mission.token, host.credential)
        for player in mission.players: store.set_connected(mission.token, player.id, False)
    store.persistence.checkpoint(); initial = disk_status(path)['logical_bytes']
    clock.now += 601
    assert len(store.cleanup_expired()) == 10 and len(store.cleanup_expired()) == 10
    store.persistence.checkpoint()
    assert disk_status(path)['reusable_bytes'] > 0
    with pytest.raises(PersistenceError): compact_offline(path)
    store.close()
    compact_offline(path)
    assert path.stat().st_size < initial
    assert verify(path)['missions'] == 0


@pytest.mark.parametrize('terminal', [False, True])
def test_online_backup_contains_wal_and_restore_matches_roles_history_results(tmp_path, terminal):
    clock = Clock(); path = tmp_path / 'live.sqlite3'
    store, mission, credentials = team(path, clock)
    choices = 'BBBCCBCAAC' if terminal else 'B'
    for choice in choices:
        voting(store, mission, credentials, clock); votes(store, mission, credentials, [choice] * 3)
        store.continue_mission(mission.token, credentials[0], mission.results[-1].id)
    assert Path(str(path) + '-wal').stat().st_size > 0
    expected = store.persistence.payload(mission)
    original_rows = store.persistence.connection.execute('SELECT * FROM resolutions ORDER BY crisis_number').fetchall()
    output = tmp_path / 'operator-backups' / 'snapshot.sqlite3'
    report = backup_database(path, output)
    assert report['integrity'] == 'ok' and report['results'] == len(choices)
    assert output.stat().st_mode & 0o777 == 0o600
    assert restore_check(output)['isolated_restore'] == 'identical'
    restored = MissionStore(clock, persistence=SQLiteMissions(output)); restored.initialize()
    recovered = restored.get(mission.token)
    for credential, player in zip(credentials, mission.players):
        assert restored.authorize(mission.token, credential).roles == player.roles
    assert recovered.metrics == mission.metrics and recovered.results == mission.results
    with readonly(output) as connection:
        assert connection.execute('SELECT * FROM resolutions ORDER BY crisis_number').fetchall() == original_rows
    assert store.persistence.payload(mission) == expected  # Live mission unchanged.
    restored.close(); store.close()


def test_backup_refuses_overwrite_symlink_and_live_restore_and_corruption(tmp_path):
    clock = Clock(); path = tmp_path / 'live.sqlite3'; store = store_at(path, clock); store.create('Host')
    with pytest.raises(ValueError): backup_database(path, path)
    other = tmp_path / 'backup.sqlite3'; backup_database(path, other)
    with pytest.raises(FileExistsError): backup_database(path, other)
    link = tmp_path / 'linked.sqlite3'; link.symlink_to(other)
    with pytest.raises(FileExistsError): backup_database(path, link)
    repo = tmp_path / 'source-repo'; (repo / '.git').mkdir(parents=True)
    with pytest.raises(ValueError, match='outside Git'):
        backup_database(path, repo / 'private' / 'snapshot.sqlite3')
    corrupt = tmp_path / 'corrupt.sqlite3'; corrupt.write_bytes(b'not a database')
    with pytest.raises(sqlite3.DatabaseError): verify(corrupt)
    store.close()


def test_token_buckets_bound_keys_refill_and_sanitized_diagnostics(caplog):
    clock = Clock(); controls = SafetyControls(SafetySettings(limiter_keys=2), clock)
    controls.allow('chat', 'PRIVATE-ID', 1, 10)
    with pytest.raises(SafetyLimit): controls.allow('chat', 'PRIVATE-ID', 1, 10)
    assert 'PRIVATE-ID' not in caplog.text and 'PRIVATE-ID' not in json.dumps(controls.diagnostics())
    controls.allow('chat', 'second', 1, 10)
    with pytest.raises(SafetyLimit): controls.allow('chat', 'third', 1, 10)
    clock.now += 1201; controls.allow('chat', 'third', 1, 10)
    assert len(controls.buckets) == 1


def gateway_app(tmp_path, **limits):
    app = create_app(database_path=tmp_path / 'app.sqlite3', safety_settings=SafetySettings(**limits))
    return app, SitesGateway(app, 'k' * 48, 'https://site.example', require_visitor=True)


def headers(visitor='a'):
    return {'X-Consensus-Gateway-Key': 'k' * 48, 'X-Consensus-Visitor': visitor * 64,
            'Origin': 'https://site.example', 'X-Forwarded-For': 'untrusted'}


def test_proxy_visitors_independent_and_forwarding_headers_cannot_rotate_limits(tmp_path):
    app, gateway = gateway_app(tmp_path, create_per_10min=1)
    with TestClient(gateway) as client:
        assert client.post('/api/missions', headers=headers(), json={'callsign': 'A'}).status_code == 201
        denied = client.post('/api/missions', headers={**headers(), 'X-Forwarded-For': 'different'}, json={'callsign': 'B'})
        assert denied.status_code == 429 and int(denied.headers['Retry-After']) > 0
        assert client.post('/api/missions', headers=headers('b'), json={'callsign': 'B'}).status_code == 201
        for spoofed in [{}, {'X-Consensus-Visitor': 'b' * 64}, {'X-Consensus-Gateway-Key': 'k' * 48}]:
            assert client.post('/api/missions', headers=spoofed, json={'callsign': 'C'}).status_code == 403
        assert len(app.state.missions.mission_tokens()) == 2


def test_http_byte_limit_and_seat_credential_cannot_restore_another_mission(tmp_path):
    app = create_app(safety_settings=SafetySettings(http_body_bytes=100))
    with TestClient(app) as client:
        assert client.post('/api/missions', content=b'x' * 101).status_code == 413
        assert client.post('/api/missions', content='\u00e9' * 51).status_code == 413
        host = create(client); other = create(client, 'Other')
        assert client.post(f'/api/missions/{host["token"]}/join', headers={'X-Mission-Session': other['credential']}, json={'callsign': 'X'}).status_code == 401
        assert len(app.state.missions.get(host['token']).players) == 1


def test_concurrent_create_is_atomic_and_bounded(tmp_path):
    async def run():
        app = create_app(database_path=tmp_path / 'concurrent.sqlite3', safety_settings=SafetySettings(
            create_per_10min=100, create_global_per_minute=100, missions_per_creator=100, missions_total=10))
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://local') as client:
                responses = await asyncio.gather(*(client.post('/api/missions', json={'callsign': f'Host {i}'}) for i in range(30)))
                assert sum(r.status_code == 201 for r in responses) == 10
                assert all(r.status_code in (201, 503) for r in responses)
                assert len({r.json()['token'] for r in responses if r.status_code == 201}) == 10
                assert verify(tmp_path / 'concurrent.sqlite3')['missions'] == 10
        return app
    asyncio.run(run())


def test_socket_cap_excess_tab_cannot_disconnect_existing_seat(tmp_path):
    app = create_app(safety_settings=SafetySettings(sockets_per_seat=1))
    with TestClient(app) as client:
        host = create(client); route = f'/api/missions/{host["token"]}/ws'
        with client.websocket_connect(route) as first:
            state = authenticate(first, host['credential'])
            with client.websocket_connect(route) as extra:
                extra.send_json({'type': 'authenticate', 'credential': host['credential']})
                with pytest.raises(WebSocketDisconnect): extra.receive_json()
            assert app.state.missions.get(host['token']).players[0].connected
            assert app.state.safety.sockets_active == 1
        assert app.state.safety.sockets_active == 0


def test_websocket_frame_byte_and_attempt_limits(tmp_path):
    app = create_app(safety_settings=SafetySettings(websocket_bytes=200, ws_attempts_per_minute=2))
    with TestClient(app) as client:
        host = create(client); route = f'/api/missions/{host["token"]}/ws'
        for _ in range(2):
            with client.websocket_connect(route) as socket:
                authenticate(socket, host['credential'])
                socket.send_text(json.dumps({'type': 'chat', 'text': '\u00e9' * 100}, ensure_ascii=False))
                with pytest.raises(WebSocketDisconnect): socket.receive_json()
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(route): pass
        assert app.state.safety.sockets_active == 0


def test_chat_limit_never_appends_rejected_message_or_advances_state():
    clock = Clock(); app = create_app(clock=clock, safety_settings=SafetySettings(chat_per_10sec=1))
    with TestClient(app) as client:
        host = create(client); guest = client.post(f'/api/missions/{host["token"]}/join', json={'callsign': 'Guest'}).json()
        route = f'/api/missions/{host["token"]}'
        with client.websocket_connect(route + '/ws') as a, client.websocket_connect(route + '/ws') as b:
            authenticate(a, host['credential']); authenticate(b, guest['credential']); a.receive_json()
            client.post(route + '/start', headers={'X-Mission-Session': host['credential']}); a.receive_json(); b.receive_json()
            client.post(route + '/discussion', headers={'X-Mission-Session': host['credential']}); a.receive_json(); b.receive_json()
            a.send_json({'type': 'chat', 'text': 'Allowed'}); first = a.receive_json()['mission']; b.receive_json()
            a.send_json({'type': 'chat', 'text': 'Rejected'})
            assert a.receive_json()['type'] == 'error'
            mission = app.state.missions.get(host['token'])
            assert len(mission.chat) == 1 and mission.revision == first['revision']
            assert mission.phase == Phase.DISCUSSION
            clock.now += 10
            a.send_json({'type': 'chat', 'text': 'Allowed later'})
            assert len(a.receive_json()['mission']['chat']) == 2; b.receive_json()


def test_config_invalid_values_fail_closed(monkeypatch):
    monkeypatch.setenv('CONSENSUS_SAFETY_MISSIONS_TOTAL', 'secret-invalid-value')
    with pytest.raises(ValueError, match='Invalid CONSENSUS_SAFETY'): SafetySettings.from_env()
    with pytest.raises(ValueError): SafetySettings(lobby_retention_seconds=299)
    with pytest.raises(ValueError): SafetySettings(sockets_total=0)


@pytest.mark.parametrize('limit', ['sockets_total', 'sockets_per_visitor'])
def test_total_and_visitor_socket_caps_release_after_disconnect(limit):
    app = create_app(safety_settings=SafetySettings(**{limit: 1}))
    with TestClient(app) as client:
        host = create(client); route = f'/api/missions/{host["token"]}/ws'
        with client.websocket_connect(route) as first:
            authenticate(first, host['credential'])
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(route): pass
        with client.websocket_connect(route) as replacement:
            assert authenticate(replacement, host['credential'])['you']
        assert not app.state.safety.sockets_by_visitor


def test_creation_per_creator_and_storage_headroom_limits(tmp_path):
    clock = Clock(); path = tmp_path / 'capacity.sqlite3'
    store = store_at(path, clock, settings(missions_per_creator=1))
    store.create('A', creator_key='a' * 64)
    with pytest.raises(MissionError) as exc: store.create('B', creator_key='a' * 64)
    assert exc.value.code == 'creator_capacity'
    store.create('B', creator_key='b' * 64)
    store.safety_settings = replace(store.safety_settings, database_max_bytes=1)
    with pytest.raises(MissionError) as exc: store.create('C')
    assert exc.value.code == 'storage_capacity'
    assert len(store.mission_tokens()) == 2
    store.close()


def test_startup_grace_allows_restore_before_old_activity_is_cleaned(tmp_path):
    clock = Clock(); path = tmp_path / 'grace.sqlite3'
    store = store_at(path, clock); mission, host = store.create('Host'); store.close()
    clock.now += 1000
    app = create_app(clock=clock, database_path=path, safety_settings=settings())
    with TestClient(app):
        asyncio.run(app.state.tick())
        assert app.state.missions.authorize(mission.token, host.credential).id == host.id
        app.state.missions.set_connected(mission.token, host.id, True)
        clock.now += 301; asyncio.run(app.state.tick())
        assert app.state.missions.get(mission.token).players[0].connected


def test_raw_streamed_body_limits_timeout_and_concurrent_http(monkeypatch):
    async def run():
        entered = asyncio.Event(); release = asyncio.Event()
        async def endpoint(scope, receive, send):
            entered.set(); await release.wait()
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'ok'})
        controls = SafetyControls(SafetySettings(http_concurrent=1, http_body_bytes=4))
        app = SafetyMiddleware(endpoint, controls)
        scope = {'type': 'http', 'path': '/api/test', 'method': 'POST', 'headers': [], 'client': ('peer', 1)}
        async def request(messages):
            iterator = iter(messages); output = []
            async def receive(): return next(iterator)
            async def send(frame): output.append(frame)
            await app(scope, receive, send)
            return output
        oversize = await request([{'type': 'http.request', 'body': b'123', 'more_body': True},
                                  {'type': 'http.request', 'body': b'45'}])
        assert oversize[0]['status'] == 413 and controls.http_active == 0
        pending = asyncio.create_task(request([{'type': 'http.request', 'body': b'1234'}]))
        await entered.wait()
        denied = await request([{'type': 'http.request', 'body': b''}])
        assert denied[0]['status'] == 429
        release.set(); assert (await pending)[0]['status'] == 200
        assert controls.http_active == 0
        real_wait_for = asyncio.wait_for
        async def timeout(coro, _seconds):
            coro.close(); raise asyncio.TimeoutError
        monkeypatch.setattr('app.safety.asyncio.wait_for', timeout)
        timed_out = await request([])
        assert timed_out[0]['status'] == 408
        monkeypatch.setattr('app.safety.asyncio.wait_for', real_wait_for)
    asyncio.run(run())


def test_defeat_backup_and_retention_preserve_final_result_until_expiry(tmp_path):
    from app.crises import load_crisis_sequence
    crisis = load_crisis_sequence()[0].model_copy(deep=True)
    crisis.choices[0].metric_deltas.infrastructure = -70
    clock = Clock(); path = tmp_path / 'defeat.sqlite3'
    store = MissionStore(clock, crisis_loader=lambda: [crisis], persistence=SQLiteMissions(path), safety_settings=settings())
    store.initialize(); mission, host = store.create('Host'); store.join(mission.token, 'Guest')
    ready(store, mission); store.start(mission.token, host.credential)
    credentials = [p.credential for p in mission.players]
    voting(store, mission, credentials, clock); votes(store, mission, credentials, [crisis.choices[0].id] * 2)
    assert mission.phase == Phase.FAILED and mission.metrics.infrastructure == 0
    for player in mission.players: store.set_connected(mission.token, player.id, False)
    output = tmp_path / 'failed-backup.sqlite3'
    assert backup_database(path, output)['results'] == 1
    assert restore_check(output)['isolated_restore'] == 'identical'
    clock.now += 899; assert store.cleanup_expired() == []
    clock.now += 1; assert store.cleanup_expired() == [mission.token]
    assert verify(path)['missions'] == 0 and verify(output)['results'] == 1
    store.close()


def test_scheduler_does_not_copy_idle_retained_aggregates(monkeypatch):
    clock = Clock(); app = create_app(clock=clock)
    with TestClient(app) as client:
        create(client)
        def unexpected(_token): raise AssertionError('Idle mission must not serialize on scheduler wakeup')
        monkeypatch.setattr(app.state.missions, 'advance_due', unexpected)
        asyncio.run(app.state.tick())


def test_continuous_failed_recipient_churn_has_bounded_retry_waves(monkeypatch):
    from unittest.mock import AsyncMock
    from fastapi import WebSocket
    from app.connections import LobbyConnections
    store = MissionStore(); mission, host = store.create('Host')
    connections = LobbyConnections(store)
    count = 0
    def broken():
        socket = AsyncMock(spec=WebSocket)
        socket.send_json.side_effect = RuntimeError('test disconnect')
        return socket
    original = connections.remove
    def replace_failed(token, player, socket):
        nonlocal count
        count += 1; original(token, player, socket)
        connections.add(token, player, broken())
    monkeypatch.setattr(connections, 'remove', replace_failed)
    connections.add(mission.token, host.id, broken())
    asyncio.run(connections.broadcast(mission.token))
    assert count == 2 and mission.token in connections.pending


def test_slow_mission_cannot_block_another_missions_publication():
    from unittest.mock import AsyncMock
    from fastapi import WebSocket
    from app.connections import LobbyConnections
    async def run():
        store = MissionStore(); first, a = store.create('A'); second, b = store.create('B')
        connections = LobbyConnections(store)
        entered = asyncio.Event(); release = asyncio.Event()
        async def slow(_frame): entered.set(); await release.wait()
        pending_socket = AsyncMock(spec=WebSocket); pending_socket.send_json.side_effect = slow
        healthy = AsyncMock(spec=WebSocket)
        connections.add(first.token, a.id, pending_socket); connections.add(second.token, b.id, healthy)
        pending = asyncio.create_task(connections.broadcast(first.token))
        await entered.wait()
        await asyncio.wait_for(connections.broadcast(second.token), 1)
        assert healthy.send_json.await_count == 1
        release.set(); await pending
    asyncio.run(run())
