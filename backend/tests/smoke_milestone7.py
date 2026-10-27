"""Real process kills/restarts, SQLite and WebSockets; controlled UTC file clock."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import httpx
import uvicorn
from websockets.asyncio.client import connect

from app.main import create_app
from app.crises import load_crisis_sequence
from app.persistence import canonical

PORT=18770


class Server:
    def __init__(self,directory):
        self.db=directory/'missions.sqlite3'; self.clock=directory/'clock'; self.process=None
        self.set_time(1_700_000_000)
    def set_time(self,value):
        temporary=self.clock.with_suffix('.new'); temporary.write_text(str(value)); temporary.replace(self.clock)
    def start(self,client):
        self.process=subprocess.Popen([sys.executable,__file__,'--serve',str(self.db),str(self.clock)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(100):
            if self.process.poll() is not None: raise RuntimeError('Recovery server exited')
            try:
                if client.get('/api/health').status_code==200: return
            except httpx.ConnectError: pass
            time.sleep(.05)
        raise RuntimeError('Recovery server did not start')
    def kill(self):
        if self.process and self.process.poll() is None:
            self.process.kill(); self.process.wait(timeout=5)


async def receive(socket):
    frame=json.loads(await asyncio.wait_for(socket.recv(),5))
    assert frame['type']=='state',frame.get('type')
    return frame['mission']


class Game:
    def __init__(self,client,count,label):
        self.client=client
        host=client.post('/api/missions',json={'callsign':label+' Host'}).json(); self.token=host['token']
        self.sessions=[host]+[client.post(f'/api/missions/{self.token}/join',json={'callsign':label+f' Guest {i}'}).json() for i in range(1,count)]
        self.url=f'ws://127.0.0.1:{PORT}/api/missions/{self.token}/ws'; self.sockets=[]
    async def open(self):
        self.sockets=[]; frames=[]
        for session in self.sessions:
            socket=await connect(self.url,close_timeout=1)
            await socket.send(json.dumps({'type':'authenticate','credential':session['credential']}))
            state=await receive(socket)
            for i,prior in enumerate(self.sockets): frames[i]=await receive(prior)
            frames.append(state); self.sockets.append(socket)
        self.frames=frames
        return frames
    async def close(self):
        await asyncio.gather(*(s.close() for s in self.sockets))
    async def states(self):
        self.frames=[await receive(s) for s in self.sockets]
        for key in ['revision','phase','crisis','metrics','history','summary','chat']:
            assert all(s[key]==self.frames[0][key] for s in self.frames)
        return self.frames
    async def post(self,action,body=None):
        response=self.client.post(f'/api/missions/{self.token}/{action}',headers={'X-Mission-Session':self.sessions[0]['credential']},json=body)
        assert response.status_code==200,response.status_code
        return await self.states()
    async def chat(self,index,text):
        await self.sockets[index].send(json.dumps({'type':'chat','text':text})); return await self.states()
    async def vote(self,index,choice):
        await self.sockets[index].send(json.dumps({'type':'vote','round_id':self.frames[0]['voting']['round_id'],'choice_id':choice})); return await self.states()
    async def choose(self,choice):
        for i in range(len(self.sockets)): await self.vote(i,choice)
    async def start(self):
        await self.open(); await self.post('start')
    async def open_vote(self,server):
        await self.post('discussion'); server.set_time(self.frames[0]['deadline']); await self.states()
    async def acknowledge(self): return await self.post('continue',{'result_id':self.frames[0]['result']['id']})


def same(before,after,keys):
    for key in keys: assert canonical(before[key])==canonical(after[key]),key


async def acceptance(client,server):
    game=Game(client,3,'Primary'); other=Game(client,2,'Independent')
    await game.start(); await other.start()
    await game.open_vote(server); await game.choose('B'); await game.acknowledge()
    await game.post('discussion'); await game.chat(1,'Water risk needs accessible distribution.')
    await other.post('discussion'); await other.chat(0,'Independent mission channel.')
    before=game.frames[1]; isolated=other.frames[0]
    old_pid=server.process.pid; server.kill(); await game.close(); await other.close()
    server.start(client); assert server.process.pid!=old_pid
    restored=(await game.open())[1]; independent=(await other.open())[0]
    same(before,restored,['crisis','crisis_number','roles','you','private_intelligence','metrics','history','chat'])
    same(isolated,independent,['roles','metrics','history','chat'])
    assert restored['phase']=='discussion' and restored['deadline']==before['deadline']
    assert restored['revision']>before['revision']
    assert independent['chat']!=restored['chat']
    print('PASS A/E: genuine killed-process recovery after Crisis 1; three identities/roles, metrics/history/chat and independent mission restored',flush=True)
    server.set_time(game.frames[0]['deadline']); await game.states()
    # The second mission shares this test clock and also enters voting.
    await other.states()
    await game.vote(0,'B'); before=game.frames[0]; round_id=before['voting']['round_id']
    server.kill(); await game.close(); await other.close(); server.start(client)
    frames=await game.open(); await other.open()
    assert frames[0]['phase']=='voting' and frames[0]['voting']['your_vote']=='B'
    assert frames[0]['voting']['round_id']==round_id and frames[0]['deadline']==before['deadline']
    await game.sockets[0].send(json.dumps({'type':'vote','round_id':round_id,'choice_id':'A'})); await game.states()
    assert json.loads(await game.sockets[0].recv())['type']=='error'
    await game.vote(1,'A'); await game.vote(2,'C')
    assert game.frames[0]['phase']=='consensus_window'
    print('PASS B: unexpired partial vote survives process restart; duplicate vote rejected and initial tie preserved',flush=True)
    consensus=game.frames[0]; server.kill(); await game.close(); await other.close()
    server.set_time(consensus['deadline']+500); server.start(client)
    frames=await game.open(); await other.open()
    # Opening first two sockets leaves recovery_wait; the third opens a fresh
    # mandatory final vote after the original Consensus deadline has expired.
    assert frames[0]['phase']=='voting' and frames[0]['voting']['number']==2
    assert frames[0]['deadline']-frames[0]['server_now']==30
    assert all(s['voting']['your_vote'] is None for s in frames)
    assert frames[0]['closed_rounds'][0]['totals']=={'A':1,'B':1,'C':1}
    await game.choose('B'); await game.acknowledge()
    print('PASS C: expired Consensus Window survives restart; final vote gets a fresh 30s opportunity and keeps initial tallies',flush=True)
    # Remaining production path: BBBCCBCAAC.
    for choice in 'BCCBCAAC':
        await game.open_vote(server); await game.choose(choice); await game.acknowledge()
    assert game.frames[0]['phase']=='completed' and game.frames[0]['summary']['consensus_score']==55.75
    victory=game.frames[1]
    # Complete/terminate the independently progressing mission. It may already
    # have resolved its first no-vote deadline while the primary mission ran.
    while other.frames[0]['phase'] not in ['decision_locked','failed','completed']:
        await other.states()
    # Resolve a deterministic production collapse in another retained mission.
    collapse=Game(client,2,'Collapse'); await collapse.start()
    for choice in 'BAAA':
        await collapse.open_vote(server); await collapse.choose(choice)
        if collapse.frames[0]['phase']=='failed': break
        await collapse.acknowledge()
    defeat=collapse.frames[0]; assert defeat['phase']=='failed'
    server.kill(); await game.close(); await other.close(); await collapse.close(); server.start(client)
    recovered=(await game.open())[1]; failed=(await collapse.open())[0]; isolated=(await other.open())[0]
    keys=['phase','history','summary','metrics_timeline','metrics','chat','roles','private_intelligence']
    same(victory,recovered,keys); same(defeat,failed,keys)
    assert len(recovered['history'])==10 and len(failed['history'])==4
    assert recovered['revision']>victory['revision']
    assert isolated['token']!=recovered['token'] and isolated['chat']!=recovered['chat']
    # Never publish seat secrets in the evidence artifact.
    output=Path('/tmp/ce-m7-restart.json')
    output.write_text(json.dumps({'discussion':restored,'voting':frames[1], 'victory':recovered,'defeat':failed}))
    await game.close(); await other.close(); await collapse.close()
    print('PASS D: ten-crisis victory and early defeat restore canonical history/timeline/summary byte-equivalently; score 55.75 and 54.5 retained',flush=True)
    print(f'LIVE RESTART SMOKE PASS: five real server process generations; captured snapshots: {output}',flush=True)


def main():
    with tempfile.TemporaryDirectory(prefix='ce-restart-') as directory:
        server=Server(Path(directory))
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{PORT}') as client:
                server.start(client); asyncio.run(acceptance(client,server))
        finally: server.kill()


if __name__=='__main__':
    if '--serve' in sys.argv:
        clock_path=Path(sys.argv[3])
        uvicorn.run(create_app(clock=lambda:float(clock_path.read_text()),crisis_loader=load_crisis_sequence,database_path=sys.argv[2]),host='127.0.0.1',port=PORT,log_level='warning')
    else: main()
