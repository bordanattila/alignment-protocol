"""Live mission review acceptance, reusing the real three-client campaign driver."""
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import time

import httpx
import uvicorn

from app.main import create_app
from smoke_milestone5 import play


class ReviewEvidence:
    def __init__(self):
        self.history=[]
        self.terminal=None
        self.terminal_snapshots=0

    def check(self,state):
        history=state['history']
        assert history[:len(self.history)]==self.history
        assert [r['crisis_number'] for r in history]==list(range(1,len(history)+1))
        assert len({r['id'] for r in history})==len(history)
        assert state['metrics_timeline']==([{'crisis_number':0,'metrics':dict.fromkeys(['infrastructure','public_trust','economy','safety'],70)}]
            + [{'crisis_number':r['crisis_number'],'metrics':r['after']} for r in history])
        for result in history:
            assert result['applied_deltas']=={k:result['after'][k]-v for k,v in result['before'].items()}
            assert result['voting_rounds'][-1]['totals']==result['decision']['totals']
            assert len(result['choices'])==3
            assert all('votes' not in r for r in result['voting_rounds'])
        self.history=history
        if state['phase'] in ['failed','completed']:
            summary=state['summary']
            assert summary['final_metrics']==state['metrics']==state['metrics_timeline'][-1]['metrics']
            assert summary['consensus_score']==sum(state['metrics'].values())/4
            evidence={key:state[key] for key in ['phase','history','summary','metrics_timeline','metrics','collapsed_metrics','consensus_score']}
            if self.terminal is not None: assert evidence==self.terminal
            self.terminal=evidence
            self.terminal_snapshots+=1
        else: assert state['summary'] is None


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
            victory=ReviewEvidence(); defeat=ReviewEvidence()
            asyncio.run(play(client,'BBBCCBCAAC',on_state=victory.check))
            asyncio.run(play(client,'BAAAAAAAAA',collapse=True,on_state=defeat.check))
            assert victory.terminal['summary']['crises_completed']==10
            assert victory.terminal['summary']['consensus_score']==55.75
            assert victory.terminal['summary']['consensus_windows']==2
            assert victory.terminal['summary']['resolution_breakdown']=={'initial_plurality':8,'final_plurality':1,'ai_tie_break':1,'no_vote_ai_fallback':0}
            assert defeat.terminal['summary']['outcome']=='defeat'
            assert len(defeat.terminal['history'])==4 and defeat.terminal['history'][-1]['status']=='collapsed'
            assert victory.terminal_snapshots>=4 and defeat.terminal_snapshots>=4
            output=Path('/tmp/ce-m6-live.json'); output.write_text(json.dumps({'victory':victory.terminal,'defeat':defeat.terminal}))
            print('PASS: live three-client ten-crisis victory, separate Crisis 4 collapse, initial/final ties, identical history/summary after terminal reconnect',flush=True)
            print(f'Victory score: 55.75; defeat score: {defeat.terminal["summary"]["consensus_score"]}; review snapshots: {output}',flush=True)
    finally:
        server.terminate(); server.wait(timeout=5)


if __name__=='__main__':
    if '--serve' in sys.argv:
        uvicorn.run(create_app(clock=lambda:time.time()*20),host='127.0.0.1',port=18769,log_level='warning')
    else: main()
