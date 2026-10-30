"""Real local HTTP/WS receipt intervals with fake inference; not browser render time."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import time

import httpx
import uvicorn
from app.main import create_app
from app.generation.config import GenerationSettings
from test_live_generation import ProgressiveProvider
from smoke_live_generation import GeneratedServer, GeneratedGame
from smoke_milestone7 import PORT


class DelayedProvider(ProgressiveProvider):
    async def generate(self, request):
        # Intentional synthetic inference duration, not a synchronization sleep.
        await asyncio.sleep(.05)
        return await super().generate(request)


class Server(GeneratedServer):
    script = __file__


async def run(client, server):
    game = GeneratedGame(client)
    try:
        await game.open()
        ready = time.perf_counter()
        await game.post('start')
        await game.until(lambda s:s['phase']=='briefing')
        initial_receipt = time.perf_counter()-ready
        await game.open_vote(server)
        await game.choose('B')
        result = game.frames[0]['result']
        assert game.frames[0]['phase']=='decision_locked'
        # Correlate next readiness and receipt using this client's single clock.
        ready = time.perf_counter()
        await game.acknowledge()
        assert all(s['phase']=='preparing' and s['result']==result and s['crisis'] is None for s in game.frames)
        await game.until(lambda s:s['phase']=='briefing' and s['crisis_number']==2)
        next_receipt = time.perf_counter()-ready
        assert all(len(s['history'])==1 and s['crisis']==game.frames[0]['crisis'] for s in game.frames)
        return {'evidence':'real loopback HTTP/WebSocket clients; fake 0.05s provider',
                'clients':3,'initial_ready_to_all_client_receipts_seconds':round(initial_receipt,6),
                'next_ready_to_all_client_receipts_seconds':round(next_receipt,6),
                'pending_result_visible':True,'common_content':True,'browser_render_seconds':None,
                'real_provider_requests':0,'warning':'Includes local HTTP, ASGI, commit and socket delivery; not a real provider benchmark or browser timing.'}
    finally: await game.close()


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--serve':
        db,clock=map(Path,sys.argv[2:4])
        uvicorn.run(create_app(clock=lambda:float(clock.read_text()),database_path=db,
            generation_settings=GenerationSettings(enabled=True,timeout_seconds=60),
            generation_provider=DelayedProvider()),host='127.0.0.1',port=PORT,log_level='warning')
    else:
        parser=argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--output',type=Path,required=True)
        args=parser.parse_args()
        with tempfile.TemporaryDirectory(prefix='ce96-receipt-') as folder:
            server=Server(Path(folder))
            with httpx.Client(base_url=f'http://127.0.0.1:{PORT}',timeout=5) as client:
                try:
                    server.start(client)
                    result=asyncio.run(run(client,server))
                    args.output.write_text(json.dumps(result,indent=2)+'\n')
                    print('RESPONSIVENESS NETWORK SMOKE PASS: 3 clients; correlated receipt timing; pending public outcome; no browser timing claim')
                finally: server.kill()
