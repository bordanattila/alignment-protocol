"""Reuse authored ten-crisis acceptance through the deployment gateway locally.

Real HTTP/WebSockets, process restart, controlled fixture clock, temporary SQLite.
No Railway account, Sites deployment, provider credentials or paid API calls.
"""
import asyncio
from functools import partial
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import httpx
import uvicorn

from app.generation.config import GenerationSettings
from app.main import create_app
from app.railway import SitesGateway
import smoke_milestone7
from smoke_milestone8 import acceptance

KEY = 'local-fixture-only-' + 'x' * 32
ORIGIN = 'https://private-site.example'
HEADERS = {'X-Consensus-Gateway-Key': KEY, 'Origin': ORIGIN}
PORT = smoke_milestone7.PORT


class GatewayServer(smoke_milestone7.Server):
    def start(self, client):
        self.process = subprocess.Popen(
            [sys.executable, __file__, '--serve', str(self.db), str(self.clock)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            if self.process.poll() is not None:
                raise RuntimeError('Gateway fixture exited')
            try:
                if client.get('/api/health').status_code == 200:
                    return
            except httpx.ConnectError:
                pass
            time.sleep(.05)
        raise RuntimeError('Gateway fixture did not start')


def main():
    # Keep production clients/engine intact; supply deployment headers only in
    # this local fixture, as the server-only Sites relay would do in production.
    smoke_milestone7.connect = partial(smoke_milestone7.connect, additional_headers=HEADERS)
    with tempfile.TemporaryDirectory(prefix='ce-gateway-') as directory:
        server = GatewayServer(Path(directory))
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{PORT}', headers=HEADERS) as client:
                server.start(client)
                assert httpx.get(f'http://127.0.0.1:{PORT}/api/capabilities').status_code == 403
                assert client.get('/api/capabilities').json() == {'generated_missions': False}
                assert client.post('/api/missions', json={'callsign': 'Blocked', 'mode': 'generated'}).status_code == 409
                asyncio.run(acceptance(client, server))
                print('PASS gateway: private access enforced; generation disabled; full authored multiplayer acceptance passed')
        finally:
            server.kill()


if __name__ == '__main__':
    if '--serve' in sys.argv:
        clock = Path(sys.argv[3])
        application = create_app(clock=lambda: float(clock.read_text()), database_path=sys.argv[2],
                                 generation_settings=GenerationSettings(enabled=False))
        uvicorn.run(SitesGateway(application, KEY, ORIGIN), host='127.0.0.1', port=PORT, log_level='warning')
    else:
        main()
