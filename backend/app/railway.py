"""Deployment boundary only; game rules and local development stay unchanged."""
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from starlette.responses import JSONResponse

from .generation.config import GenerationSettings
from .main import create_app


class SitesGateway:
    def __init__(self, app, secret: str, site_origin: str):
        self.app = app
        self.secret = secret
        self.site_origin = site_origin

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http', 'websocket'):
            return await self.app(scope, receive, send)
        # Railway probes contain no key; this endpoint reveals no mission state.
        if (scope['type'] == 'http' and scope['method'] == 'GET'
                and scope['path'] == '/api/health'):
            return await self.app(scope, receive, send)
        headers = {}
        for key, value in scope['headers']:
            headers.setdefault(key.lower(), []).append(value)
        keys = headers.get(b'x-consensus-gateway-key', [])
        origins = headers.get(b'origin', [])
        authorized = (len(keys) == 1 and secrets.compare_digest(keys[0], self.secret.encode())
                      and (not origins or origins == [self.site_origin.encode()]))
        if not authorized:
            if scope['type'] == 'websocket':
                await send({'type': 'websocket.close', 'code': 1008})
            else:
                await JSONResponse({'detail': 'Private playtest access required.'}, status_code=403,
                                   headers={'Cache-Control': 'no-store'})(scope, receive, send)
            return
        # Never pass deployment credentials into game handlers or projections.
        scope = dict(scope, headers=[(k, v) for k, v in scope['headers']
                                    if k.lower() != b'x-consensus-gateway-key'])
        await self.app(scope, receive, send)


def create_railway_app():
    secret = os.environ.get('CONSENSUS_GATEWAY_KEY', '')
    origin = os.environ.get('CONSENSUS_SITE_ORIGIN', '')
    parsed = urlsplit(origin)
    if (len(secret) < 32 or not secret.isascii() or not secret.isprintable()
            or not secret.strip() or parsed.scheme != 'https' or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.path or parsed.query or parsed.fragment):
        raise RuntimeError('Configure a strong gateway key and an exact HTTPS Sites origin.')
    if os.environ.get('CONSENSUS_LLM_ENABLED', 'false').lower() != 'false':
        raise RuntimeError('Railway playtests require CONSENSUS_LLM_ENABLED=false.')
    mount = Path(os.environ.get('RAILWAY_VOLUME_MOUNT_PATH', '/data'))
    database = Path(os.environ.get('CONSENSUS_DB_PATH', '/data/consensus-engine.sqlite3'))
    if (not mount.is_absolute() or not mount.is_mount()
            or not database.is_absolute() or not database.resolve().is_relative_to(mount.resolve())
            or database.resolve() == mount.resolve()):
        raise RuntimeError('A persistent volume must be mounted and contain CONSENSUS_DB_PATH.')
    return SitesGateway(create_app(database_path=database,
                                  generation_settings=GenerationSettings(enabled=False)), secret, origin)
