"""Live HTTP/WebSocket acceptance using two crises confined to test fixtures.

Run from root: .venv/bin/python backend/tests/smoke_milestone4.py
A 10x injected clock shortens real waits; production duration constants are
unchanged. This is automated transport evidence, not browser verification.
"""
import asyncio
import json
import subprocess
import sys
import time

import httpx
import uvicorn
from websockets.asyncio.client import connect

from app.main import create_app
from test_milestone4 import fixture_sequence


def smoke_sequence():
    sequence = fixture_sequence()
    sequence[1].choices[2].metric_deltas.safety = -100
    return sequence


async def receive(socket):
    frame = json.loads(await asyncio.wait_for(socket.recv(), timeout=20))
    assert frame['type'] == 'state', frame
    return frame['mission']


async def scenario(client, collapse=False):
    host = client.post('/api/missions',json={'callsign':'Host'}).json()
    token = host['token']
    guests = [client.post(f'/api/missions/{token}/join',json={'callsign':name}).json() for name in ['Lee','Chen']]
    headers = {'X-Mission-Session':host['credential']}
    url = f'ws://127.0.0.1:18767/api/missions/{token}/ws'
    async with connect(url) as a, connect(url) as b, connect(url) as c:
        sockets = [a,b,c]
        for index, (socket, session) in enumerate(zip(sockets,[host,*guests])):
            await socket.send(json.dumps({'type':'authenticate','credential':session['credential']}))
            await receive(socket)
            for old in sockets[:index]: await receive(old)
        async def states():
            frames = [await receive(s) for s in sockets]
            for key in ['phase','metrics','result','decision','crisis_number','consensus_score','collapsed_metrics']:
                assert all(s[key] == frames[0][key] for s in frames)
            return frames
        async def post(action, body=None):
            response = client.post(f'/api/missions/{token}/{action}',headers=headers,json=body)
            assert response.status_code == 200, response.text
            return await states()
        async def votes(round_id, choices):
            for socket, choice in zip(sockets,choices):
                await socket.send(json.dumps({'type':'vote','round_id':round_id,'choice_id':choice}))
                result = await states()
            return result
        async def voting():
            await post('discussion')
            frames = await states()  # authoritative scheduler opens initial voting
            assert all(s['phase'] == 'voting' and s['voting']['number'] == 1 for s in frames)
            return frames[0]['voting']['round_id']
        async def revote(round_id, choices):
            consensus = await votes(round_id,['A','B','C'])
            assert consensus[0]['phase'] == 'consensus_window'
            await b.send(json.dumps({'type':'chat','text':'Reconsider before the final vote.'}))
            await states()
            final = await states()
            assert all(s['phase'] == 'voting' and s['voting']['number'] == 2 and s['voting']['your_vote'] is None for s in final)
            return await votes(final[0]['voting']['round_id'],choices)
        fresh = await post('start')
        assert all(set(s['metrics'].values()) == {70} for s in fresh)
        round_id = await voting()
        result = await revote(round_id,['A','B','C']) if collapse else await votes(round_id,['B','B','A'])
        assert result[0]['phase'] == 'decision_locked'
        expected = {'infrastructure':78,'public_trust':62,'economy':72,'safety':64} if collapse else {'infrastructure':75,'public_trust':67,'economy':63,'safety':72}
        assert result[0]['metrics'] == expected
        assert result[0]['decision']['reason'] == ('ai_tie_break' if collapse else 'initial_plurality')
        assert result[0]['result']['after'] == expected
        # Multiple result observers/refreshes cannot reapply effects.
        for _ in range(2):
            async with connect(url) as refresh:
                await refresh.send(json.dumps({'type':'authenticate','credential':host['credential']}))
                restored = await receive(refresh)
                assert restored['metrics'] == expected and restored['result'] == result[0]['result']
                await states()
            await states()
        result_id = result[0]['result']['id']
        second = await post('continue',{'result_id':result_id})
        assert second[0]['phase'] == 'briefing' and second[0]['crisis_number'] == 2
        assert second[0]['metrics'] == expected
        assert all(s['voting'] is None and s['result'] is None and s['decision'] is None for s in second)
        again = await post('continue',{'result_id':result_id})
        assert again[0]['crisis_number'] == 2 and again[0]['metrics'] == expected
        for state in second:
            player = next(p for p in state['players'] if p['id'] == state['you'])
            assert set(state['private_intelligence']) == set(player['roles'])
        round_id = await voting()
        result = await votes(round_id,['C','C','A']) if collapse else await revote(round_id,['B','B','A'])
        if collapse:
            assert result[0]['phase'] == 'failed' and result[0]['collapsed_metrics'] == ['safety']
            assert result[0]['metrics'] == {'infrastructure':79,'public_trust':60,'economy':75,'safety':0}
            assert client.post(f'/api/missions/{token}/continue',headers=headers,json={'result_id':result[0]['result']['id']}).status_code == 409
        else:
            assert result[0]['decision']['reason'] == 'final_plurality'
            assert result[0]['metrics'] == {'infrastructure':76,'public_trust':65,'economy':66,'safety':68}
            completed = await post('continue',{'result_id':result[0]['result']['id']})
            assert completed[0]['phase'] == 'completed' and completed[0]['consensus_score'] == 68.75
    async with connect(url) as refresh:
        await refresh.send(json.dumps({'type':'authenticate','credential':host['credential']}))
        restored = await receive(refresh)
        assert restored['phase'] == ('failed' if collapse else 'completed')
        assert restored['metrics'] == result[0]['metrics']
        assert restored['result'] == result[0]['result']
    print('PASS: ' + ('AI final tie, exactly-once result, second crisis, collapse, terminal reconnect' if collapse else 'plurality, persistent results, duplicate-safe progression, final revote, completion score, reconnect'),flush=True)


def main():
    server = subprocess.Popen([sys.executable,__file__,'--serve'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        with httpx.Client(base_url='http://127.0.0.1:18767') as client:
            for _ in range(100):
                if server.poll() is not None: raise RuntimeError('Fixture server exited')
                try:
                    if client.get('/api/health').status_code == 200: break
                except httpx.ConnectError: pass
                time.sleep(.05)
            else: raise RuntimeError('Fixture server failed to start')
            assert client.get('/').status_code == 200
            asyncio.run(scenario(client))
            asyncio.run(scenario(client,collapse=True))
            print('MILESTONE 4 LIVE SMOKE PASS (automated, fixture sequence and 10x clock)',flush=True)
    finally:
        server.terminate(); server.wait(timeout=5)


if __name__ == '__main__':
    if '--serve' in sys.argv:
        uvicorn.run(create_app(clock=lambda:time.time()*10,crisis_loader=smoke_sequence),host='127.0.0.1',port=18767,ws_max_size=4096,log_level='warning')
    else:
        main()
