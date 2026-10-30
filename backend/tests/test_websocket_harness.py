"""Controlled reproduction of cancellation dropping an expected presence frame."""
import asyncio

from fastapi.testclient import TestClient
import pytest
import starlette.testclient

from app.connections import LobbyConnections
from app.main import create_app
from test_foundation import authenticate, create
from ws_harness import RawWebSocketSession


def gate_disconnect(monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()
    flags = {'next_cleanup': False, 'interrupted': False, 'completed': False}
    remove, broadcast = LobbyConnections.remove, LobbyConnections.broadcast

    def traced_remove(self, *args):
        remove(self, *args)
        flags['next_cleanup'] = True

    async def gated_broadcast(self, *args, **kwargs):
        if flags['next_cleanup']:
            flags['next_cleanup'] = False
            entered.set()
            try:
                await release.wait()
                await broadcast(self, *args, **kwargs)
                flags['completed'] = True
            except asyncio.CancelledError:
                flags['interrupted'] = True
                raise
        else:
            await broadcast(self, *args, **kwargs)

    monkeypatch.setattr(LobbyConnections, 'remove', traced_remove)
    monkeypatch.setattr(LobbyConnections, 'broadcast', gated_broadcast)
    return entered, release, flags


async def bounded(event):
    await asyncio.wait_for(event.wait(), 1)


def test_stock_testclient_cancels_disconnect_publication(monkeypatch):
    monkeypatch.setattr(starlette.testclient, 'WebSocketTestSession', RawWebSocketSession)
    entered, release, flags = gate_disconnect(monkeypatch)
    with TestClient(create_app()) as client:
        host = create(client)
        url = f"/api/missions/{host['token']}/ws"
        with client.websocket_connect(url) as first:
            authenticate(first, host['credential'])
            with client.websocket_connect(url) as tab:
                authenticate(tab, host['credential']);first.receive_json()
                tab.close()
                client.portal.call(bounded, entered)
            # Stock __exit__ canceled the real endpoint in its finally block.
            assert flags['interrupted'] and not flags['completed']
            async def no_presence_frame():
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(first._send_rx.receive(), .02)
            client.portal.call(no_presence_frame)
            client.portal.call(release.set)


def test_managed_exit_delivers_cleanup_before_cancel(monkeypatch):
    entered, release, flags = gate_disconnect(monkeypatch)
    with TestClient(create_app()) as client:
        host = create(client)
        url = f"/api/missions/{host['token']}/ws"
        with client.websocket_connect(url) as first:
            authenticate(first, host['credential'])
            async def allow_cleanup():
                await bounded(entered)
                release.set()
            client.portal.start_task_soon(allow_cleanup)
            with client.websocket_connect(url) as tab:
                authenticate(tab, host['credential']);first.receive_json()
            assert flags['completed'] and not flags['interrupted']
            assert first.receive_json()['mission']['players'][0]['connected']


def test_bounded_receive_reports_only_safe_categories():
    with TestClient(create_app()) as client:
        host = create(client)
        with client.websocket_connect(f"/api/missions/{host['token']}/ws") as socket:
            authenticate(socket, host['credential'])
            socket.timeout_seconds = .01
            with pytest.raises(AssertionError, match='observed categories=') as error:
                socket.receive_json()
            assert host['credential'] not in str(error.value) and host['token'] not in str(error.value)


def test_managed_cleanup_has_a_bounded_failure(monkeypatch):
    entered, release, flags = gate_disconnect(monkeypatch)
    with TestClient(create_app()) as client:
        host=create(client)
        with pytest.raises(AssertionError,match='ASGI cleanup did not finish'):
            with client.websocket_connect(f"/api/missions/{host['token']}/ws") as socket:
                authenticate(socket,host['credential'])
                socket.timeout_seconds=.01
        assert entered.is_set() and flags['interrupted'] and not flags['completed']
