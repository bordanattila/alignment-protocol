"""Test transport synchronization only; production WebSockets are untouched."""
import pytest
import starlette.testclient
from ws_harness import ManagedWebSocketSession


@pytest.fixture(autouse=True)
def managed_websocket_sessions(monkeypatch):
    monkeypatch.setattr(starlette.testclient, 'WebSocketTestSession', ManagedWebSocketSession)
