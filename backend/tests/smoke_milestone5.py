"""Real HTTP/WebSocket ten-crisis acceptance; 20x injected clock, not a browser."""
import asyncio
from contextlib import AsyncExitStack
import json
import subprocess
import sys
import time

import httpx
import uvicorn
from websockets.asyncio.client import connect

from app.crises import load_crisis_sequence
from app.main import create_app


async def receive(socket):
    frame = json.loads(await asyncio.wait_for(socket.recv(), 15))
    assert frame['type'] == 'state', frame
    return frame['mission']


async def play(client, path, collapse=False):
    host = client.post('/api/missions', json={'callsign':'Eagle1'}).json()
    token = host['token']; endpoint = f'/api/missions/{token}'
    sessions = [host]+[client.post(endpoint+'/join',json={'callsign':name}).json() for name in ['Eagle2','Eagle3']]
    headers = {'X-Mission-Session':host['credential']}
    url = f'ws://127.0.0.1:18769{endpoint}/ws'
    catalog = load_crisis_sequence(); log=[]
    async with AsyncExitStack() as stack:
        sockets=[]
        for session in sessions:
            socket=await stack.enter_async_context(connect(url))
            await socket.send(json.dumps({'type':'authenticate','credential':session['credential']}))
            await receive(socket)
            for old in sockets: await receive(old)
            sockets.append(socket)
        async def states():
            frames=[await receive(s) for s in sockets]
            for key in ['phase','crisis','metrics','result','decision','deadline','crisis_number']:
                assert all(s[key]==frames[0][key] for s in frames)
            for state in frames:
                current=catalog[state['crisis_number']-1]
                assert state['private_intelligence']=={r:current.private_intelligence[r] for r in state['roles']}
                for crisis in catalog:
                    for role,text in crisis.private_intelligence.items():
                        if crisis.id!=current.id or role not in state['roles']: assert text not in json.dumps(state)
            return frames
        async def post(action,body=None):
            response=client.post(endpoint+'/'+action,headers=headers,json=body)
            assert response.status_code==200,response.text
            return response.json(),await states()
        async def vote(frames,choices):
            for socket,choice in zip(sockets,choices):
                await socket.send(json.dumps({'type':'vote','round_id':frames[0]['voting']['round_id'],'choice_id':choice}))
                frames=await states()
            return frames
        async def reconnect(frames):
            original=frames[1]; await sockets[1].close()
            for i in [0,2]: assert not (await receive(sockets[i]))['players'][1]['connected']
            response=client.post(endpoint+'/join',headers={'X-Mission-Session':sessions[1]['credential']},json={'callsign':'Ignored rename'})
            assert response.json()==sessions[1]
            for i in [0,2]: await receive(sockets[i])
            replacement=await stack.enter_async_context(connect(url))
            await replacement.send(json.dumps({'type':'authenticate','credential':sessions[1]['credential']}))
            restored=await receive(replacement)
            for key in ['you','roles','phase','deadline','crisis','metrics','private_intelligence','voting','result']:
                assert restored[key]==original[key],key
            for i in [0,2]: await receive(sockets[i])
            sockets[1]=replacement
            print(f"PASS: actual reconnect at crisis {restored['crisis_number']} / {restored['phase']}",flush=True)
        _,frames=await post('start'); roles=[s['roles'] for s in frames]
        for number,choice in enumerate(path,1):
            assert frames[0]['phase']=='briefing' and frames[0]['crisis_number']==number
            _,frames=await post('discussion')
            if number==6: await reconnect(frames)
            await sockets[0].send(json.dumps({'type':'chat','text':f'Assess crisis {number}.'}))
            frames=await states()
            assert frames[0]['chat'][-1]['crisis_number']==number
            frames=await states(); assert frames[0]['phase']=='voting'
            if number in [2,4] and not collapse:
                frames=await vote(frames,'ABC'); assert frames[0]['phase']=='consensus_window'
                frames=await states(); assert frames[0]['voting']['number']==2
                assert all(s['voting']['your_vote'] is None for s in frames)
                frames=await vote(frames,'ABC' if number==4 else 'BBA')
                assert frames[0]['decision']['reason']==('ai_tie_break' if number==4 else 'final_plurality')
            else:
                if number==8:
                    await sockets[1].send(json.dumps({'type':'vote','round_id':frames[0]['voting']['round_id'],'choice_id':choice}))
                    frames=await states(); await reconnect(frames)
                    for i in [0,2]:
                        await sockets[i].send(json.dumps({'type':'vote','round_id':frames[0]['voting']['round_id'],'choice_id':choice}))
                        frames=await states()
                else: frames=await vote(frames,[choice,choice,next(c for c in 'ABC' if c!=choice)])
            assert frames[0]['decision']['choice_id']==choice
            if number==9: await reconnect(frames)
            result=frames[0]['result']
            row=dict(crisis=number,title=catalog[number-1].title,choice=choice,reason=frames[0]['decision']['reason'],deltas=next(c for c in catalog[number-1].choices if c.id==choice).metric_deltas.model_dump(),metrics=frames[0]['metrics'])
            if frames[0]['phase']=='failed':
                assert collapse
                assert client.post(endpoint+'/continue',headers=headers,json={'result_id':result['id']}).status_code==409
                row['next_phase']='failed'; log.append(row); break
            response,frames=await post('continue',{'result_id':result['id']}); assert response['advanced']
            response,frames=await post('continue',{'result_id':result['id']}); assert not response['advanced']
            assert [s['roles'] for s in frames]==roles
            row['next_phase']=frames[0]['phase']; log.append(row)
        expected_phase='failed' if collapse else 'completed'
        assert all(s['phase']==expected_phase for s in frames)
        if not collapse: assert all(s['consensus_score']==55.75 for s in frames)
    async with connect(url) as socket:
        await socket.send(json.dumps({'type':'authenticate','credential':sessions[1]['credential']}))
        restored=await receive(socket)
        assert restored['phase']==expected_phase and restored['roles']==roles[1]
        assert restored['metrics']==frames[1]['metrics'] and restored['result']==frames[1]['result']
    return log


def main():
    server=subprocess.Popen([sys.executable,__file__,'--serve'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        with httpx.Client(base_url='http://127.0.0.1:18769') as client:
            for _ in range(100):
                if server.poll() is not None: raise RuntimeError('Temporary server exited')
                try:
                    if client.get('/api/health').status_code==200: break
                except httpx.ConnectError: pass
                time.sleep(.05)
            else: raise RuntimeError('Temporary server did not start')
            complete=asyncio.run(play(client,'BBBCCBCAAC'))
            collapse=asyncio.run(play(client,'BAAAAAAAAA',True))
            print(json.dumps(dict(complete=complete,collapse=collapse),indent=2),flush=True)
            print('MILESTONE 5 LIVE SMOKE PASS: production content, three clients, ten crises, ties, reconnects, completion and natural collapse (20x clock)',flush=True)
    finally:
        server.terminate(); server.wait(timeout=5)


if __name__=='__main__':
    if '--serve' in sys.argv:
        uvicorn.run(create_app(clock=lambda:time.time()*20),host='127.0.0.1',port=18769,log_level='warning')
    else: main()
