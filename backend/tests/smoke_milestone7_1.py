"""Reload-mode migration/creation smoke, preserving a source DB via backup."""
import asyncio
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time

import httpx
from websockets.asyncio.client import connect


async def identity(token,credential):
    async with connect(f'ws://127.0.0.1:18771/api/missions/{token}/ws') as socket:
        await socket.send(json.dumps({'type':'authenticate','credential':credential}))
        frame=json.loads(await socket.recv())
        assert frame['type']=='state'
        return frame['mission']['you']


def main():
    source=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else None
    root=Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix='ce-7-1-reload-') as folder:
        directory=Path(folder); database=directory/'missions.sqlite3'; watch=directory/'watch'; watch.mkdir()
        if source:
            with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as original:
                with sqlite3.connect(database) as copied: original.backup(copied)
        else:
            with sqlite3.connect(database) as db:
                db.execute('CREATE TABLE missions (token TEXT PRIMARY KEY, format_version INTEGER NOT NULL, payload TEXT NOT NULL, checksum TEXT NOT NULL)')
                db.execute('CREATE TABLE resolutions (mission_token TEXT NOT NULL REFERENCES missions(token), result_id TEXT NOT NULL, crisis_number INTEGER NOT NULL, record TEXT NOT NULL, PRIMARY KEY(mission_token,result_id), UNIQUE(mission_token,crisis_number))')
                db.execute('PRAGMA user_version=1')
        probe=watch/'probe.py'; probe.write_text('generation = 0\n')
        log_path=directory/'server.log'
        with log_path.open('w') as log:
            process=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--reload','--reload-dir',str(watch),'--host','127.0.0.1','--port','18771'],cwd=root/'backend',env={**os.environ,'CONSENSUS_DB_PATH':str(database)},stdout=log,stderr=log,start_new_session=True)
            try:
                with httpx.Client(base_url='http://127.0.0.1:18771') as client:
                    for _ in range(150):
                        if process.poll() is not None: raise RuntimeError('Reload server exited')
                        try:
                            if client.get('/api/health').status_code==200: break
                        except httpx.ConnectError: pass
                        time.sleep(.1)
                    else: raise RuntimeError('Reload server failed startup')
                    with sqlite3.connect(database) as db: original_count=db.execute('SELECT count(*) FROM missions').fetchone()[0]
                    sessions=[]
                    for callsign in ['Reload Host','Another Host']:
                        response=client.post('/api/missions',json={'callsign':callsign})
                        assert response.status_code==201,response.status_code
                        sessions.append(response.json())
                    first=sessions[0]; before=asyncio.run(identity(first['token'],first['credential']))
                    probe.write_text('generation = 1\n')
                    for attempt in range(200):
                        # The server can become healthy before the parent's lazy
                        # watcher starts. Retry the test-file change until seen.
                        if attempt and attempt % 10 == 0:
                            probe.write_text(f'generation = {attempt + 1}\n')
                        log_text=log_path.read_text()
                        if log_text.count('Application startup complete.')>=2:
                            try:
                                if client.get('/api/health').status_code==200: break
                            except httpx.ConnectError: pass
                        time.sleep(.1)
                    else: raise RuntimeError('Reload worker did not recover')
                    response=client.post(f"/api/missions/{first['token']}/join",headers={'X-Mission-Session':first['credential']},json={'callsign':'Ignored'})
                    assert response.status_code==200 and response.json()==first
                    assert asyncio.run(identity(first['token'],first['credential']))==before
                    assert client.post('/api/missions',json={'callsign':'After Reload'}).status_code==201
                    with sqlite3.connect(database) as db:
                        assert db.execute('PRAGMA user_version').fetchone()[0]==2
                        assert db.execute('SELECT count(*) FROM missions').fetchone()[0]==original_count+3
                    print('PASS: v1 database copy migrates to v2; three creation requests return 201; actual reload worker restart retains seat identity and credential; source database untouched.')
            finally:
                os.killpg(process.pid,signal.SIGTERM); process.wait(timeout=10)
                Path('/tmp/ce-7-1-after-server.log').write_text(log_path.read_text())


if __name__=='__main__': main()
