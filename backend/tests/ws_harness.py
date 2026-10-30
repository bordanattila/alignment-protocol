"""Test-only bounded receives and graceful ASGI cleanup before portal cancellation."""
import asyncio
from collections import deque
import json

from starlette.testclient import WebSocketTestSession as RawWebSocketSession


class ManagedWebSocketSession(RawWebSocketSession):
    timeout_seconds = 3

    def __init__(self, app, scope, portal_factory):
        self.finished = asyncio.Event()
        self.observed = deque(maxlen=12)

        async def observed_app(scope, receive, send):
            try:
                await app(scope, receive, send)
            finally:
                self.finished.set()

        super().__init__(observed_app, scope, portal_factory)

    def receive(self):
        async def bounded_receive():
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    return await self._send_rx.receive()
            except TimeoutError:
                raise AssertionError(
                    f'WebSocket expected state/error/close within {self.timeout_seconds}s; '
                    f'observed categories={list(self.observed)}; '
                    f'ASGI finished={self.finished.is_set()}; pending tasks={len(asyncio.all_tasks())}'
                ) from None
        message = self.portal.call(bounded_receive)
        category = message['type']
        if category == 'websocket.send':
            try:
                data = json.loads(message.get('text', '{}'))
                category = data.get('type') if data.get('type') in ('state', 'error') else 'other'
                phase = data.get('mission', {}).get('phase')
                if phase in {'lobby','preparing','briefing','discussion','voting','consensus_window',
                             'decision_locked','completed','failed','reconnect_wait'}:
                    category += ':' + phase
            except (ValueError, AttributeError, TypeError):
                category = 'unparsed'
        self.observed.append(category)
        return message

    def __exit__(self, *args):
        # Stock TestClient queues disconnect then immediately cancels its ASGI
        # scope. That can cancel the endpoint's finally/broadcast. Wait for the
        # handler to finish first; normal portal/stream cleanup still runs.
        async def wait_finished():
            async with asyncio.timeout(self.timeout_seconds):
                await self.finished.wait()
        try:
            self.close()
            try:
                self.portal.call(wait_finished)
            except TimeoutError:
                raise AssertionError(
                    f'WebSocket ASGI cleanup did not finish within {self.timeout_seconds}s; '
                    f'observed categories={list(self.observed)}'
                ) from None
        finally:
            super().__exit__(*args)
