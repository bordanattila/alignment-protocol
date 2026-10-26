import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.testclient import TestClient

from app.connections import LobbyConnections
from app.main import create_app
from app.missions import MissionError, MissionStore


@pytest.fixture
def client():
    with TestClient(create_app()) as client:
        yield client


def create(client, callsign="Rivera"):
    response = client.post("/api/missions", json={"callsign": callsign})
    assert response.status_code == 201
    return response.json()


def authenticate(socket, credential):
    socket.send_json({"type": "authenticate", "credential": credential})
    return socket.receive_json()["mission"]


def test_create_join_and_capacity(client):
    host = create(client, "  Rivera  ")
    token = host["token"]
    assert len(token) >= 32
    assert host["credential"] != token
    for name in ["Lee", "Ali", "Chen"]:
        response = client.post(f"/api/missions/{token}/join", json={"callsign": name})
        assert response.status_code == 200
        assert response.json()["credential"] != host["credential"]
    assert client.post(f"/api/missions/{token}/join", json={"callsign": "Fifth"}).status_code == 409
    # Restoring a full mission is still allowed and preserves the original seat.
    response = client.post(f"/api/missions/{token}/join", json={"callsign": "Rivera"},
                           headers={"X-Mission-Session": host["credential"]})
    assert response.json() == host
    with client.websocket_connect(f"/api/missions/{token}/ws") as socket:
        state = authenticate(socket, host["credential"])
        assert len(state["players"]) == 4
        assert state["players"][0]["callsign"] == "Rivera"
        assert state["host_id"] == state["you"]
        assert state["phase"] == "lobby"
        assert set(state["metrics"].values()) == {70}


def test_duplicate_callsign_and_missing_invite(client):
    host = create(client)
    assert client.post(f"/api/missions/{host['token']}/join", json={"callsign": "rivera"}).status_code == 409
    assert client.post("/api/missions/missing/join", json={"callsign": "Lee"}).status_code == 404


@pytest.mark.parametrize("callsign", ["", "   ", "x" * 25, None, 123])
def test_callsign_validation(client, callsign):
    assert client.post("/api/missions", json={"callsign": callsign}).status_code == 422


def test_untrusted_fields_rejected(client):
    assert client.post("/api/missions", json={"callsign": "Lee", "role": "safety"}).status_code == 422


@pytest.mark.parametrize("credential", ["wrong", "", "非ASCII"])
def test_invalid_join_credential_does_not_allocate(client, credential):
    host = create(client)
    response = client.post(f"/api/missions/{host['token']}/join", json={"callsign": "Lee"},
                           headers={"X-Mission-Session": credential} if credential.isascii() else
                           {"X-Mission-Session": credential.encode("utf-8")})
    assert response.status_code == 401
    assert len(client.app.state.missions.get(host["token"]).players) == 1


@pytest.mark.parametrize("credential", ["wrong", "", "非ASCII"])
def test_invalid_socket_credential(client, credential):
    host = create(client)
    with client.websocket_connect(f"/api/missions/{host['token']}/ws") as socket:
        socket.send_json({"type": "authenticate", "credential": credential})
        assert socket.receive()["code"] == 1008
    assert not client.app.state.missions.get(host["token"]).players[0].connected


def test_missing_socket_invite(client):
    with client.websocket_connect("/api/missions/missing/ws") as socket:
        socket.send_json({"type": "authenticate", "credential": "wrong"})
        assert socket.receive()["code"] == 1008


@pytest.mark.parametrize("frame", ["{", "[]", "null", '"text"', '{"type":"vote","choice":"A"}',
                                   '{"type":"authenticate","credential":123}',
                                   '{"type":"authenticate","credential":"x","extra":true}',
                                   "x" * 4097, "[" * 2000, b"binary"])
def test_malformed_authentication(client, frame):
    host = create(client)
    with client.websocket_connect(f"/api/missions/{host['token']}/ws") as socket:
        if isinstance(frame, bytes):
            socket.send_bytes(frame)
        else:
            socket.send_text(frame)
        assert socket.receive()["code"] == 1008


def test_cross_mission_credential_and_projection_authorization(client):
    first, second = create(client), create(client)
    with client.websocket_connect(f"/api/missions/{second['token']}/ws") as socket:
        socket.send_json({"type": "authenticate", "credential": first["credential"]})
        assert socket.receive()["code"] == 1008
    with pytest.raises(MissionError):
        client.app.state.missions.project(first["token"], "outsider")


def test_sync_privacy_multitab_disconnect_and_reconnect(client):
    host = create(client)
    token = host["token"]
    url = f"/api/missions/{token}/ws"
    with client.websocket_connect(url) as first:
        original = authenticate(first, host["credential"])
        guest = client.post(f"/api/missions/{token}/join", json={"callsign": "Lee"}).json()
        assert len(first.receive_json()["mission"]["players"]) == 2
        with client.websocket_connect(url) as second:
            guest_state = authenticate(second, guest["credential"])
            host_state = first.receive_json()["mission"]
            assert guest_state["players"] == host_state["players"]
            assert guest_state["you"] != host_state["you"]
            public = json.dumps(host_state)
            assert "credential" not in public
            assert host["credential"] not in public and guest["credential"] not in public
            with client.websocket_connect(url) as tab:
                restored = authenticate(tab, host["credential"])
                assert restored["you"] == original["you"]
                assert len(restored["players"]) == 2
                first.receive_json()
                second.receive_json()
            assert first.receive_json()["mission"]["players"][0]["connected"]
            second.receive_json()
        assert not first.receive_json()["mission"]["players"][1]["connected"]
        with client.websocket_connect(url) as refreshed:
            restored = authenticate(refreshed, guest["credential"])
            assert restored["you"] == guest_state["you"]
            assert len(restored["players"]) == 2
            assert first.receive_json()["mission"]["players"][1]["connected"]


@pytest.mark.parametrize("binary", [False, True])
def test_unsupported_action_disconnects_only_sender(client, binary):
    host = create(client)
    guest = client.post(f"/api/missions/{host['token']}/join", json={"callsign": "Lee"}).json()
    url = f"/api/missions/{host['token']}/ws"
    with client.websocket_connect(url) as first:
        authenticate(first, host["credential"])
        with client.websocket_connect(url) as second:
            authenticate(second, guest["credential"])
            first.receive_json()
            if binary:
                second.send_bytes(b"binary")
            else:
                second.send_json({"type": "start"})
            assert second.receive()["code"] == 1008
            state = first.receive_json()["mission"]
            assert state["players"][0]["connected"]
            assert not state["players"][1]["connected"]


def test_disconnect_before_auth_does_not_change_membership(client):
    host = create(client)
    with client.websocket_connect(f"/api/missions/{host['token']}/ws"):
        pass
    assert len(client.app.state.missions.get(host["token"]).players) == 1


@pytest.mark.parametrize("error", [OSError(), RuntimeError(), WebSocketDisconnect(), asyncio.TimeoutError()])
def test_failed_send_cleanup_and_presence_rebroadcast(error):
    async def run():
        store = MissionStore()
        mission, host = store.create("Rivera")
        _, guest = store.join(mission.token, "Lee")
        connections = LobbyConnections(store)
        healthy = AsyncMock(spec=WebSocket)
        broken = AsyncMock(spec=WebSocket)
        broken.send_json.side_effect = error
        broken.close.side_effect = OSError("Already disconnected")
        connections.add(mission.token, host.id, healthy)
        connections.add(mission.token, guest.id, broken)
        await connections.broadcast(mission.token)
        assert not guest.connected and host.connected
        assert broken.send_json.await_count == 1
        assert healthy.send_json.await_count == 2
        assert not healthy.send_json.call_args.args[0]["mission"]["players"][1]["connected"]
        # A delayed receive-loop cleanup must not remove a newly reconnected socket.
        replacement = AsyncMock(spec=WebSocket)
        connections.add(mission.token, guest.id, replacement)
        connections.remove(mission.token, guest.id, broken)
        assert guest.connected
        connections.remove(mission.token, guest.id, replacement)
        connections.remove(mission.token, host.id, healthy)
        assert not connections.sockets
    asyncio.run(run())


def test_failed_tab_preserves_other_tab_presence():
    async def run():
        store = MissionStore()
        mission, host = store.create("Rivera")
        connections = LobbyConnections(store)
        healthy, broken = AsyncMock(spec=WebSocket), AsyncMock(spec=WebSocket)
        broken.send_json.side_effect = OSError()
        connections.add(mission.token, host.id, healthy)
        connections.add(mission.token, host.id, broken)
        await connections.broadcast(mission.token)
        assert host.connected
        assert connections.sockets[mission.token][host.id] == {healthy}
    asyncio.run(run())
