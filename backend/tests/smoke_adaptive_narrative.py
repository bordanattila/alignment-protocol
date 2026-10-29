"""Offline three-browser-equivalent journeys, held endgame, fallback and restart."""
import asyncio
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

import httpx
import uvicorn

from app.main import create_app
from app.generation.config import GenerationSettings
from app.generation.contract import FailureCategory, GenerationError
from app.generation.endgame import EndgameRequest
from app.generation.provider import ProviderResponse
from smoke_live_generation import FixtureProvider, GeneratedServer, acceptance
from smoke_milestone7 import PORT
from test_adaptive_narrative import story


class NarrativeProvider(FixtureProvider):
    async def generate(self,request):
        if not isinstance(request,EndgameRequest):return await super().generate(request)
        # Synthetic fixtures only. The production diagnostic path never stores context.
        with (self.directory/'endgame-requests.jsonl').open('a') as stream:
            stream.write(request.model_dump_json()+'\n')
        while not (self.directory/'release-endgame').exists():await asyncio.sleep(.01)
        if (self.directory/'mode').read_text()=='failure':raise GenerationError(FailureCategory.UNAVAILABLE,503)
        return ProviderResponse(json.dumps(story(request)),200)


class NarrativeServer(GeneratedServer):
    script=__file__


async def verify(client,server,directory,mode):
    game=await acceptance(client,server,directory)
    for _ in range(100):
        if (directory/'endgame-requests.jsonl').exists():break
        await asyncio.sleep(.01)
    else:raise AssertionError('No endgame request')
    await game.open()
    assert all(s['summary']['conclusion']['status']=='pending' for s in game.frames)
    final=game.frames[0]
    assert final['phase']=='completed' and len(final['history'])==10
    # Real reconnect while the asynchronous request is held; deterministic ending remains.
    await game.close();await game.open()
    assert all(s['summary']['narrative_outcome']==final['summary']['narrative_outcome'] for s in game.frames)
    if mode=='restart':
        server.kill();await game.close();server.start(client);await game.open()
        assert all(s['summary']['conclusion']['status']=='fallback' for s in game.frames)
    else:
        (directory/'release-endgame').touch()
        expected='generated' if mode=='success' else 'fallback'
        await game.until(lambda s:s['summary']['conclusion']['status']==expected)
        assert all(s['summary']==game.frames[0]['summary'] for s in game.frames)
        if mode=='success':
            accepted=game.frames[0]['summary']['conclusion']
            assert len(accepted['sections'])==3
            server.kill();await game.close();server.start(client);await game.open()
            assert all(s['summary']['conclusion']==accepted for s in game.frames)
    for frame in game.frames:
        for key in ('phase','metrics','history','metrics_timeline','consensus_score'):
            assert frame[key]==final[key]
        assert all(k not in json.dumps(frame) for k in ('basis_hash','duration_seconds','http_status','endgame-1.0'))
    requests=[json.loads(line) for line in (directory/'endgame-requests.jsonl').read_text().splitlines()]
    assert len(requests)==1 and requests[0]['context']['crises_completed']==10
    assert requests[0]['context']['final_metrics']==final['metrics']
    assert [r['crisis_id'] for r in requests[0]['context']['history']]==[r['crisis_id'] for r in final['history']]
    assert 'PRIVATE-CHAT-CANARY' not in json.dumps(requests)
    with sqlite3.connect(server.db) as db:
        raw=json.loads(db.execute('SELECT payload FROM missions WHERE token=?',(game.token,)).fetchone()[0])
    assert raw['conclusion']['diagnostic']['category']=={'success':'success','restart':'restart_recovery','failure':'unavailable'}[mode]
    assert len(raw['generation_diagnostics'])==10
    await game.close()
    print(f'ADAPTIVE NARRATIVE SMOKE PASS: {mode}; ten crises, three clients, mixed sources, pending reconnect, one endgame request, stable final records',flush=True)


def main():
    if len(sys.argv)>1 and sys.argv[1]=='--serve':
        db,clock=map(Path,sys.argv[2:4])
        uvicorn.run(create_app(clock=lambda:float(clock.read_text()),database_path=db,
            generation_settings=GenerationSettings(enabled=True,timeout_seconds=15),
            generation_provider=NarrativeProvider(db.parent)),host='127.0.0.1',port=PORT,log_level='warning')
        return
    for mode in ('success','restart','failure'):
        with tempfile.TemporaryDirectory(prefix='ce-9-3-') as temporary:
            directory=Path(temporary);(directory/'mode').write_text(mode)
            server=NarrativeServer(directory)
            with httpx.Client(base_url=f'http://127.0.0.1:{PORT}',timeout=10) as client:
                try:server.start(client);asyncio.run(verify(client,server,directory,mode))
                finally:server.kill()


if __name__=='__main__':main()
