"""Live three-client identity/completion acceptance; automated, not a browser.

Run from root: .venv/bin/python backend/tests/smoke_milestone4_1.py
Preserved Crisis 01 in a one-crisis fixture; injected 10x clock, unchanged timing constants.
"""
import asyncio
from contextlib import AsyncExitStack
import json
import subprocess
import sys
import time

import httpx
import uvicorn
from websockets.asyncio.client import connect

from app.main import create_app
from app.crises import load_initial_crisis


async def receive(socket):
    frame = json.loads(await asyncio.wait_for(socket.recv(), timeout=20))
    assert frame['type'] == 'state', frame
    return frame['mission']


async def acceptance(client):
    host_response = client.post('/api/missions',json={'callsign':'Eagle1'})
    assert host_response.status_code == 201
    host = host_response.json(); token = host['token']
    join_url = f'/api/missions/{token}/join'
    guest = client.post(join_url,json={'callsign':'Eagle2'}).json()
    duplicate = client.post(join_url,json={'callsign':'Eagle2'})
    assert duplicate.status_code == 409 and duplicate.json()['code'] == 'callsign_taken'
    third = client.post(join_url,json={'callsign':'Eagle3'}).json()
    url = f'ws://127.0.0.1:18768/api/missions/{token}/ws'
    headers = {'X-Mission-Session':host['credential']}
    async with AsyncExitStack() as stack:
        sockets = []
        for session in [host,guest,third]:
            socket = await stack.enter_async_context(connect(url))
            await socket.send(json.dumps({'type':'authenticate','credential':session['credential']}))
            await receive(socket)
            for prior in sockets: await receive(prior)
            sockets.append(socket)
        async def states(): return [await receive(socket) for socket in sockets]
        async def post(action, body=None):
            response = client.post(f'/api/missions/{token}/{action}',headers=headers,json=body)
            assert response.status_code == 200
            return await states()
        briefing = await post('start')
        assert [p['callsign'] for p in briefing[0]['players']] == ['Eagle1','Eagle2','Eagle3']
        assert len(briefing[0]['players']) == 3
        a,b,c = sockets
        await b.close()
        for socket in [a,c]: assert not (await receive(socket))['players'][1]['connected']
        restored_session = client.post(join_url,json={'callsign':'Ignored attempted rename'},headers={'X-Mission-Session':guest['credential']})
        assert restored_session.json() == guest
        for socket in [a,c]: await receive(socket)
        replacement = await stack.enter_async_context(connect(url))
        await replacement.send(json.dumps({'type':'authenticate','credential':guest['credential']}))
        restored = await receive(replacement)
        for key in ['you','roles','crisis','phase','private_intelligence']:
            assert restored[key] == briefing[1][key]
        assert restored['players'][1]['callsign'] == 'Eagle2'
        for socket in [a,c]: await receive(socket)
        sockets[1] = replacement
        print('PASS: duplicate rejected, seat available, three unique names, actual disconnect/reconnect retains ID/roles/callsign',flush=True)
        await post('discussion')
        for index, socket in enumerate(sockets):
            await socket.send(json.dumps({'type':'chat','text':f'Briefing check from player {index + 1}.'}))
            frames = await states()
            assert all(len(state['chat']) == index + 1 for state in frames)
        voting = await states()
        assert all(state['phase'] == 'voting' for state in voting)
        for socket, choice in zip(sockets,['A','A','B']):
            await socket.send(json.dumps({'type':'vote','round_id':voting[0]['voting']['round_id'],'choice_id':choice}))
            result = await states()
        completed = await post('continue',{'result_id':result[0]['result']['id']})
        assert all(state['phase'] == 'completed' and state['consensus_score'] == 69 for state in completed)
        assert all(state['metrics'] == {'infrastructure':78,'public_trust':62,'economy':72,'safety':64} for state in completed)
    async with connect(url) as refresh:
        await refresh.send(json.dumps({'type':'authenticate','credential':guest['credential']}))
        restored = await receive(refresh)
        assert restored['phase'] == 'completed' and restored['consensus_score'] == 69
        assert restored['you'] == briefing[1]['you'] and restored['roles'] == briefing[1]['roles']
        assert restored['result'] == completed[1]['result']
        assert len(restored['players']) == 3
    print('PASS: shared discussion chat, voting, completion score 69 for all three clients and after restoration',flush=True)


def main():
    server = subprocess.Popen([sys.executable,__file__,'--serve'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        with httpx.Client(base_url='http://127.0.0.1:18768') as client:
            for _ in range(100):
                if server.poll() is not None: raise RuntimeError('Temporary server exited')
                try:
                    if client.get('/api/health').status_code == 200: break
                except httpx.ConnectError: pass
                time.sleep(.05)
            else: raise RuntimeError('Temporary server did not start')
            asyncio.run(acceptance(client))
            print('MILESTONE 4.1 LIVE SMOKE PASS (automated; 10x injected clock)',flush=True)
    finally:
        server.terminate(); server.wait(timeout=5)


if __name__ == '__main__':
    if '--serve' in sys.argv:
        uvicorn.run(create_app(clock=lambda:time.time()*10, crisis_loader=lambda:[load_initial_crisis()]),host='127.0.0.1',port=18768,ws_max_size=4096,log_level='warning')
    else: main()
