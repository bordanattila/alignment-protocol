"""Run from repository root: .venv/bin/python backend/tests/smoke_milestone3.py.

Uses a temporary real Uvicorn process, HTTP and actual WebSocket clients. No
clock overrides: waits through the production 60s discussion and 20s consensus.
"""
import asyncio
import json
import subprocess
import time

import httpx
from websockets.asyncio.client import connect


async def receive(socket):
    frame = json.loads(await asyncio.wait_for(socket.recv(), timeout=65))
    assert frame['type'] == 'state', frame
    return frame['mission']


async def cycle(client):
    host = client.post('/api/missions', json={'callsign': 'Host'}).json()
    token = host['token']
    guests = [client.post(f'/api/missions/{token}/join', json={'callsign': name}).json()
              for name in ('Guest', 'Third')]
    headers = {'X-Mission-Session': host['credential']}
    url = f'ws://127.0.0.1:18766/api/missions/{token}/ws'
    async with connect(url) as first, connect(url) as second, connect(url) as third:
        sockets = (first, second, third)
        for index, (socket, session) in enumerate(zip(sockets, (host, *guests))):
            await socket.send(json.dumps({'type': 'authenticate', 'credential': session['credential']}))
            await receive(socket)
            for existing in sockets[:index]:
                await receive(existing)
        assert client.post(f'/api/missions/{token}/start', headers=headers).status_code == 200
        briefing = [await receive(s) for s in sockets]
        assert all(state['crisis'] == briefing[0]['crisis'] for state in briefing)
        assert set(briefing[0]['private_intelligence']).isdisjoint(briefing[1]['private_intelligence'])
        assert client.post(f'/api/missions/{token}/discussion', headers=headers).status_code == 200
        discussion = [await receive(s) for s in sockets]
        assert all(s['phase'] == 'discussion' for s in discussion)
        assert 59 <= discussion[0]['deadline'] - discussion[0]['server_now'] <= 60
        await first.send(json.dumps({'type': 'chat', 'text': 'Please compare the grid and hospital risks.'}))
        for socket in sockets:
            assert (await receive(socket))['chat'][0]['callsign'] == 'Host'
        print('PASS: creation, join, briefing privacy, timed discussion, shared chat; waiting for 60s deadline', flush=True)
        states = [await receive(s) for s in sockets]
        assert all(s['phase'] == 'voting' for s in states)
        round_id = states[0]['voting']['round_id']
        for socket, choice in zip(sockets, ('A', 'B', 'C')):
            await socket.send(json.dumps({'type': 'vote', 'round_id': round_id, 'choice_id': choice}))
            states = [await receive(s) for s in sockets]
            if choice == 'A':
                assert states[0]['voting']['your_vote'] == 'A'
                assert states[1]['voting']['your_vote'] is None and states[1]['closed_rounds'] == []
        assert all(s['phase'] == 'consensus_window' for s in states)
        assert states[0]['closed_rounds'][0]['totals'] == {'A': 1, 'B': 1, 'C': 1}
        await second.send(json.dumps({'type': 'chat', 'text': 'Reconsider the burden before the final vote.'}))
        for socket in sockets:
            assert len((await receive(socket))['chat']) == 2
        print('PASS: automatic hidden voting, private vote, initial tie, consensus chat; waiting for 20s deadline', flush=True)
        states = [await receive(s) for s in sockets]
        assert all(s['phase'] == 'voting' and s['voting']['number'] == 2 for s in states)
        assert all(state['voting']['your_vote'] is None for state in states)
        assert all(29 <= state['deadline'] - state['server_now'] <= 30 for state in states)
        print('PASS: final voting broadcast to all three seats with fresh votes and a full 30s deadline', flush=True)
        round_id = states[0]['voting']['round_id']
        for socket, choice in zip(sockets, ('B', 'B', 'A')):
            await socket.send(json.dumps({'type': 'vote', 'round_id': round_id, 'choice_id': choice}))
            states = [await receive(s) for s in sockets]
        result = states[0]['decision']
        assert all(result == state['decision'] for state in states)
        assert result['reason'] == 'final_plurality' and result['choice_id'] == 'B'
        assert result['totals'] == {'A': 1, 'B': 2, 'C': 0}
        assert states[0]['metrics'] == {'infrastructure':75, 'public_trust':67, 'economy':63, 'safety':72}
        assert states[0]['result']['decision'] == result
    async with connect(url) as refresh:
        await refresh.send(json.dumps({'type': 'authenticate', 'credential': host['credential']}))
        state = await receive(refresh)
        assert state['phase'] == 'decision_locked' and state['decision'] == result
        assert state['voting']['your_vote'] == 'B'
        assert state['roles'] == briefing[0]['roles'] and len(state['chat']) == 2
    print('LIVE SMOKE PASS: three-player A/B/C tie, consensus chat, fresh B/B/A final plurality, authored B consequences, reconnect', flush=True)


def main():
    server = subprocess.Popen([
        '.venv/bin/python', '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '18766',
        '--ws-max-size', '4096',
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with httpx.Client(base_url='http://127.0.0.1:18766') as client:
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError('Temporary server exited')
                try:
                    if client.get('/api/health').status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                time.sleep(.05)
            else:
                raise RuntimeError('Temporary server did not start')
            assert client.get('/').status_code == 200
            asyncio.run(cycle(client))
    finally:
        server.terminate()
        server.wait(timeout=5)


if __name__ == '__main__':
    main()
