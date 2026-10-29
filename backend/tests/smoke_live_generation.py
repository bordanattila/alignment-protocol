"""Real three-client generated game with fake inference, fallback and process kill."""
import asyncio
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time

import httpx
import uvicorn
from websockets.asyncio.client import connect

from app.consequences import apply_metric_deltas
from app.domain import Metrics, MetricDeltas
from app.generation.config import GenerationSettings
from app.generation.provider import ProviderResponse
from app.generation.endgame import EndgameRequest
from app.main import create_app
from test_live_generation import ProgressiveProvider
from smoke_milestone7 import Server, Game, PORT, receive


class FixtureProvider(ProgressiveProvider):
    def __init__(self, directory):
        super().__init__();self.directory=directory

    async def generate(self,request):
        if isinstance(request,EndgameRequest):
            from test_adaptive_narrative import story
            return ProviderResponse(json.dumps(story(request)),200)
        # Test-only synthetic request journal: never writes credentials/chat/players.
        with (self.directory/'requests.jsonl').open('a') as stream:
            stream.write(request.model_dump_json()+'\n')
        if request.context.current_crisis_number==4:
            await asyncio.Event().wait()  # killed while pending, not retried on restart
        if request.context.current_crisis_number==3:
            return ProviderResponse('{"invalid":"proposal"}')
        return await super().generate(request)


class GeneratedServer(Server):
    script=__file__
    def start(self,client):
        self.process=subprocess.Popen([sys.executable,self.script,'--serve',str(self.db),str(self.clock)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(100):
            if self.process.poll() is not None:raise RuntimeError('Generated fixture server exited')
            try:
                if client.get('/api/health').status_code==200:return
            except httpx.ConnectError:pass
            time.sleep(.05)
        raise RuntimeError('Generated fixture server did not start')


class GeneratedGame(Game):
    def __init__(self,client):
        self.client=client
        host=client.post('/api/missions',json={'callsign':'Host','mode':'generated'}).json();self.token=host['token']
        self.sessions=[host]+[client.post(f'/api/missions/{self.token}/join',json={'callsign':name}).json() for name in ['Second','Third']]
        self.url=f'ws://127.0.0.1:{PORT}/api/missions/{self.token}/ws';self.sockets=[]

    async def until(self,predicate):
        frames=[]
        for socket in self.sockets:
            for _ in range(30):
                state=await receive(socket)
                if predicate(state):break
            else:raise AssertionError('Expected authoritative state not delivered')
            frames.append(state)
        self.frames=frames
        for key in ['phase','crisis','metrics','history','generation_status']:
            assert all(s[key]==frames[0][key] for s in frames),key
        return frames

    def request(self,action,body=None):
        response=self.client.post(f'/api/missions/{self.token}/{action}',headers={'X-Mission-Session':self.sessions[0]['credential']},json=body)
        assert response.status_code==200,response.text
        return response.json()


async def acceptance(client,server,directory):
    assert client.get('/api/capabilities').json()=={'generated_missions':True}
    game=GeneratedGame(client);await game.open();game.request('start')
    await game.until(lambda s:s['phase']=='briefing')
    identities=[(s['you'],s['roles']) for s in game.frames]
    for index in range(10):
        state=game.frames[0];assert state['crisis_number']==index+1
        for player,frame in enumerate(game.frames):
            assert (frame['you'],frame['roles'])==identities[player]
            assert set(frame['private_intelligence'])==set(frame['roles'])
            assert all(field not in frame for field in ['admissions','generation','generation_diagnostics','campaign','sequence','prompt'])
        crisis=state['crisis'];game.request('discussion');await game.until(lambda s:s['phase']=='discussion')
        if index==0:
            await game.sockets[1].send(json.dumps({'type':'chat','text':'PRIVATE-CHAT-CANARY'}))
            await game.until(lambda s:len(s['chat'])==1)
        server.set_time(game.frames[0]['deadline']);await game.until(lambda s:s['phase']=='voting')
        if index==1:
            # Actual disconnected transport and original credential, during voting.
            await game.sockets[2].close()
            for socket in game.sockets[:2]:
                while True:
                    frame=await receive(socket)
                    if not frame['players'][2]['connected']:break
            socket=await connect(game.url,close_timeout=1)
            await socket.send(json.dumps({'type':'authenticate','credential':game.sessions[2]['credential']}))
            restored=await receive(socket);game.sockets[2]=socket
            assert restored['crisis']==crisis and restored['roles']==identities[2][1]
            for prior in game.sockets[:2]:await receive(prior)
            print('PASS real voting reconnect: same identity, crisis, roles and intelligence',flush=True)
        # Read the fixture's private aggregate only to choose a survival path;
        # clients still receive no unexecuted effects.
        with sqlite3.connect(server.db) as connection:
            raw=json.loads(connection.execute('SELECT payload FROM missions WHERE token=?',(game.token,)).fetchone()[0])
        choices=raw['sequence'][index]['choices']
        choice=max(choices,key=lambda c:min(apply_metric_deltas(Metrics(**state['metrics']),MetricDeltas(**c['metric_deltas'])).model_dump().values()))['id']
        round_id=game.frames[0]['voting']['round_id']
        for player,socket in enumerate(game.sockets):
            await socket.send(json.dumps({'type':'vote','round_id':round_id,'choice_id':choice}))
            await game.until(lambda s:s['phase']=='decision_locked' if player==2 else s['voting']['submitted_count']==player+1)
        assert game.frames[0]['crisis']==crisis and len(game.frames[0]['history'])==index+1
        result=game.frames[0]['result']['id'];game.request('continue',{'result_id':result})
        assert game.request('continue',{'result_id':result})=={'advanced':False}
        if index==9:
            await game.until(lambda s:s['phase']=='completed');break
        if index==2:
            await game.until(lambda s:s['phase']=='preparing')
            # Provider call is recorded before the intentional stall.
            for _ in range(100):
                if len((directory/'requests.jsonl').read_text().splitlines())==4:break
                await asyncio.sleep(.02)
            else:raise AssertionError('Pending fourth request never launched')
            before=game.frames[0]['history'];server.kill();await game.close();server.start(client);await game.open()
            assert game.frames[0]['phase']=='briefing' and game.frames[0]['crisis_number']==4
            assert game.frames[0]['history']==before
            print('PASS killed process during generation: saved authored fallback admitted, no model replay',flush=True)
        else:await game.until(lambda s:s['phase']=='briefing' and s['crisis_number']==index+2)
    assert game.frames[0]['phase']=='completed' and len(game.frames[0]['history'])==10
    requests=[json.loads(line) for line in (directory/'requests.jsonl').read_text().splitlines()]
    assert [r['context']['current_crisis_number'] for r in requests]==list(range(1,11))
    assert requests[0]['context']['history']==[]
    assert all('PRIVATE-CHAT-CANARY' not in json.dumps(r) for r in requests)
    with sqlite3.connect(server.db) as connection:
        raw=json.loads(connection.execute('SELECT payload FROM missions WHERE token=?',(game.token,)).fetchone()[0])
        assert len(raw['admissions'])==10 and len({c['id'] for c in raw['sequence']})==10
        assert sum(r['source']=='authored_fallback' for r in raw['admissions'])==2
        diagnostics=raw['generation_diagnostics']
        assert [r['crisis_number'] for r in diagnostics]==list(range(1,11))
        assert all(r['source']==a['source'] for r,a in zip(diagnostics,raw['admissions']))
        assert diagnostics[2]['category']=='invalid_schema'
        assert diagnostics[3]['category']=='restart_recovery'
        assert all(r['category']=='success' for i,r in enumerate(diagnostics) if i not in (2,3))
        assert connection.execute('SELECT COUNT(*) FROM resolutions').fetchone()[0]==10
    await game.close()
    print('GENERATED LIVE SMOKE PASS: ten crises, three clients, two fallbacks, voting reconnect, pending restart, one inference attempt per slot, no private chat in context',flush=True)
    return game


def main():
    if len(sys.argv)>1 and sys.argv[1]=='--serve':
        db,clock=map(Path,sys.argv[2:4])
        uvicorn.run(create_app(clock=lambda:float(clock.read_text()),database_path=db,
                              generation_settings=GenerationSettings(enabled=True,timeout_seconds=15),
                              generation_provider=FixtureProvider(db.parent)),host='127.0.0.1',port=PORT,log_level='warning')
        return
    with tempfile.TemporaryDirectory(prefix='ce-9-2-live-') as temporary:
        directory=Path(temporary);server=GeneratedServer(directory)
        with httpx.Client(base_url=f'http://127.0.0.1:{PORT}',timeout=10) as client:
            try:
                server.start(client);asyncio.run(acceptance(client,server,directory))
            finally:server.kill()


if __name__=='__main__':main()
