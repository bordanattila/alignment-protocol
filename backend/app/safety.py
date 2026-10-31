"""Single-process admission controls. No identifiers or payloads in diagnostics."""
import asyncio
from collections import Counter
from dataclasses import dataclass, fields
import hashlib
import logging
import os
import time

from starlette.responses import JSONResponse


@dataclass(frozen=True)
class SafetySettings:
    http_body_bytes: int = 4096
    websocket_bytes: int = 4096
    body_timeout_seconds: int = 5
    http_concurrent: int = 32
    sockets_total: int = 128
    sockets_per_visitor: int = 16
    sockets_per_seat: int = 3
    limiter_keys: int = 4096
    create_per_10min: int = 5
    create_global_per_minute: int = 30
    joins_per_minute: int = 30
    http_per_minute: int = 120
    ws_attempts_per_minute: int = 60
    ws_global_per_minute: int = 300
    frames_per_10sec: int = 30
    chat_per_10sec: int = 10
    missions_total: int = 200
    missions_per_creator: int = 8
    database_max_bytes: int = 268435456
    disk_reserve_bytes: int = 67108864
    lobby_retention_seconds: int = 86400
    unfinished_retention_seconds: int = 604800
    completed_retention_seconds: int = 2592000
    cleanup_interval_seconds: int = 60
    cleanup_batch: int = 10
    startup_cleanup_grace_seconds: int = 300

    def __post_init__(self):
        if any(type(getattr(self, f.name)) is not int or getattr(self, f.name) <= 0 for f in fields(self)):
            raise ValueError('Safety settings must be positive integers.')
        if min(self.lobby_retention_seconds, self.unfinished_retention_seconds,
               self.completed_retention_seconds, self.startup_cleanup_grace_seconds) < 300:
            raise ValueError('Retention must preserve at least the reconnect grace period.')

    @classmethod
    def from_env(cls):
        try:
            return cls(**{f.name: int(os.environ['CONSENSUS_SAFETY_' + f.name.upper()])
                          for f in fields(cls) if 'CONSENSUS_SAFETY_' + f.name.upper() in os.environ})
        except ValueError:
            raise ValueError('Invalid CONSENSUS_SAFETY configuration.') from None


class SafetyLimit(Exception):
    def __init__(self, category, retry_after=10):
        self.category = category
        self.retry_after = retry_after


class SafetyControls:
    def __init__(self, settings=None, clock=time.monotonic):
        self.settings = settings or SafetySettings()
        self.clock = clock
        self.buckets = {}
        self.rejections = Counter()
        self.http_active = 0
        self.sockets_active = 0
        self.sockets_by_visitor = Counter()
        self._last_log = {}

    def record(self, category):
        self.rejections[category] += 1
        now = self.clock()
        if now - self._last_log.get(category, float('-inf')) >= 60:
            logging.getLogger('consensus.safety').warning('safety_rejected category=%s', category)
            self._last_log[category] = now

    def reject(self, category, retry=10):
        self.record(category)
        raise SafetyLimit(category, retry)

    def allow(self, category, identity, capacity, period):
        now = self.clock()
        key = (category, identity)
        if key not in self.buckets:
            if len(self.buckets) >= self.settings.limiter_keys:
                self.buckets = {k: v for k, v in self.buckets.items() if now - v[1] < 1200}
            if len(self.buckets) >= self.settings.limiter_keys:
                self.reject('limiter_capacity', 60)
        balance, previous = self.buckets.get(key, (float(capacity), now))
        balance = min(capacity, balance + max(0, now - previous) * capacity / period)
        if balance < 1:
            self.buckets[key] = (balance, now)
            self.reject(category, max(1, int((1 - balance) * period / capacity) + 1))
        self.buckets[key] = (balance - 1, now)

    def diagnostics(self):
        return {'rejections': dict(self.rejections), 'limiter_keys': len(self.buckets),
                'http_active': self.http_active, 'sockets_active': self.sockets_active}


def visitor_key(scope):
    # Only SitesGateway can set this scope value, after authenticating the relay.
    # Local/direct deployments use the real ASGI peer, never forwarding headers.
    value = scope.get('consensus.visitor')
    if value is None:
        value = 'peer:' + str((scope.get('client') or ('unknown', 0))[0])
    return hashlib.sha256(value.encode()).hexdigest()


class SafetyMiddleware:
    def __init__(self, app, controls):
        self.app = app
        self.controls = controls

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http', 'websocket') or scope['path'] == '/api/health':
            return await self.app(scope, receive, send)
        c, s = self.controls, self.controls.settings
        who = visitor_key(scope)
        websocket = scope['type'] == 'websocket'
        entered = False
        try:
            if len(scope['path']) > 512 or len(scope.get('query_string', b'')) > 1024:
                c.reject('request_target', 60)
            if websocket:
                c.allow('ws_attempt', who, s.ws_attempts_per_minute, 60)
                c.allow('ws_global', 'all', s.ws_global_per_minute, 60)
                if c.sockets_active >= s.sockets_total or c.sockets_by_visitor[who] >= s.sockets_per_visitor:
                    c.reject('socket_capacity')
                c.sockets_active += 1
                c.sockets_by_visitor[who] += 1
                entered = True
                return await self.app(scope, receive, send)
            c.allow('http', who, s.http_per_minute, 60)
            if c.http_active >= s.http_concurrent:
                c.reject('http_capacity')
            c.http_active += 1
            entered = True
            path = scope['path']
            if scope['method'] == 'POST' and path == '/api/missions':
                c.allow('create', who, s.create_per_10min, 600)
                c.allow('create_global', 'all', s.create_global_per_minute, 60)
            elif path.endswith('/join'):
                c.allow('join', who, s.joins_per_minute, 60)
            lengths = [v for k, v in scope['headers'] if k.lower() == b'content-length']
            sessions = [v for k, v in scope['headers'] if k.lower() == b'x-mission-session']
            if len(sessions) > 1 or any(len(value) > 128 for value in sessions):
                c.record('session_header')
                await JSONResponse({'detail': 'Invalid session header.'}, status_code=400)(scope, receive, send)
                return
            if len(lengths) > 1 or (lengths and (len(lengths[0]) > 10 or not lengths[0].isdigit() or int(lengths[0]) > s.http_body_bytes)):
                c.record('http_body')
                await JSONResponse({'detail': 'Request body too large or invalid.'}, status_code=413)(scope, receive, send)
                return
            body = bytearray()

            async def read_body():
                while True:
                    frame = await receive()
                    if frame['type'] == 'http.disconnect':
                        return False
                    chunk = frame.get('body', b'')
                    if len(body) + len(chunk) > s.http_body_bytes:
                        return None
                    body.extend(chunk)
                    if not frame.get('more_body', False):
                        return True

            try:
                complete = await asyncio.wait_for(read_body(), s.body_timeout_seconds)
            except asyncio.TimeoutError:
                c.record('body_timeout')
                await JSONResponse({'detail': 'Request body timed out.'}, status_code=408)(scope, receive, send)
                return
            if complete is not True:
                if complete is None:
                    c.record('http_body')
                    await JSONResponse({'detail': 'Request body too large.'}, status_code=413)(scope, receive, send)
                return
            replayed = False

            async def replay():
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
                return await receive()

            await self.app(scope, replay, send)
        except SafetyLimit as exc:
            if websocket:
                await send({'type': 'websocket.close', 'code': 1013, 'reason': 'Server busy; retry shortly.'})
            else:
                await JSONResponse({'detail': 'Too many requests. Retry shortly.', 'code': 'rate_limited'},
                                   status_code=429, headers={'Retry-After': str(exc.retry_after),
                                                           'Cache-Control': 'no-store'})(scope, receive, send)
        finally:
            if entered:
                if websocket:
                    c.sockets_active -= 1
                    c.sockets_by_visitor[who] -= 1
                    if not c.sockets_by_visitor[who]:
                        del c.sockets_by_visitor[who]
                else:
                    c.http_active -= 1
