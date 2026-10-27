"""Real expanded ten-crisis game, branch context, process restart and review."""
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import httpx
import uvicorn

from app.campaign import load_campaign_catalog
from app.consequences import apply_metric_deltas
from app.domain import Metrics
from app.main import create_app
from smoke_milestone7 import Game, Server, PORT


class ExpandedServer(Server):
    def start(self,client):
        self.process=subprocess.Popen([sys.executable,__file__,'--serve',str(self.db),str(self.clock)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(100):
            if self.process.poll() is not None:raise RuntimeError('Expanded server exited')
            try:
                if client.get('/api/health').status_code==200:return
            except httpx.ConnectError:pass
            time.sleep(.05)
        raise RuntimeError('Expanded server did not start')


async def acceptance(client,server):
    catalog={s.crisis.id:s for s in load_campaign_catalog()}
    game=Game(client,3,'Expanded');await game.start()
    identity=[(frame['you'],frame['roles']) for frame in game.frames]
    seen=[];followups=[]
    for index in range(10):
        await game.open_vote(server)
        if index==0:
            for player,choice in enumerate('ABC'):await game.vote(player,choice)
            assert all(s['phase']=='consensus_window' for s in game.frames)
            server.set_time(game.frames[0]['deadline']);await game.states()
            assert all(s['voting']['number']==2 for s in game.frames)
        state=game.frames[0];key=state['crisis']['id'];seen.append(key)
        entry=catalog[key]
        if entry.prerequisite:
            source=next(r for r in state['history'] if r['crisis_id']==entry.prerequisite.crisis_id)
            assert source['decision']['choice_id'] in entry.prerequisite.choice_ids
            assert 'Earlier decision — Crisis' in state['crisis']['briefing'];followups.append(key)
        choice='A' if index==0 else max(entry.crisis.choices,
            key=lambda c:min(apply_metric_deltas(Metrics(**state['metrics']),c.metric_deltas).model_dump().values())).id
        expected=apply_metric_deltas(Metrics(**state['metrics']),next(c for c in entry.crisis.choices if c.id==choice).metric_deltas)
        await game.choose(choice)
        assert all(s['metrics']==expected.model_dump() and len(s['history'])==index+1 for s in game.frames)
        assert all(s['phase']=='decision_locked' for s in game.frames)
        assert len({json.dumps(s['history'],sort_keys=True) for s in game.frames})==1
        for player,state in enumerate(game.frames):
            assert (state['you'],state['roles'])==identity[player]
            assert 'campaign' not in state and 'sequence' not in state
            for scenario in catalog.values():
                for role,secret in scenario.crisis.private_intelligence.items():
                    assert (secret in json.dumps(state,ensure_ascii=False))==(scenario.crisis.id==key and role in state['roles'])
        result=game.frames[0]['result']['id']
        await game.acknowledge()
        # Repeated acknowledgement is never another transition/consequence.
        duplicate=client.post(f'/api/missions/{game.token}/continue',headers={'X-Mission-Session':game.sessions[0]['credential']},json={'result_id':result})
        assert duplicate.json()=={'advanced':False};await game.states()
        if index==2:
            before=game.frames
            server.kill();server.start(client);await game.open()
            for old,new in zip(before,game.frames):
                for field in ['you','roles','crisis','history','metrics','private_intelligence']:
                    assert old[field]==new[field]
                assert new['revision']>old['revision']
            print('PASS new campaign restart: same saved content, identities, roles, history and branch-ready state',flush=True)
    final=game.frames[0]
    assert final['phase']=='completed' and len(set(seen))==len(seen)==10
    assert final['summary']['consensus_score']==sum(final['metrics'].values())/4
    assert len(final['summary']['notable_decisions'])==3 and final['history'][-1]['outcome'] in final['summary']['narrative_outcome']
    assert followups,'Opening A should make an eligible follow-up available in stage 2'
    public={k:final[k] for k in ['phase','history','summary','metrics_timeline','metrics','collapsed_metrics','consensus_score']}
    output=Path('/tmp/ce-m8-live.json');output.write_text(json.dumps(public,ensure_ascii=False));output.chmod(0o600)
    print('PASS ten real crises: common history/metrics, final voting, authored follow-ups, no duplicate IDs, privacy and exactly-once acknowledgements',flush=True)
    print(f'EXPANSION LIVE SMOKE PASS; score={final["summary"]["consensus_score"]}; followups={len(followups)}; review=/tmp/ce-m8-live.json',flush=True)
    await game.close()


def main():
    with tempfile.TemporaryDirectory(prefix='ce-expanded-') as directory:
        server=ExpandedServer(Path(directory))
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{PORT}') as client:
                server.start(client);asyncio.run(acceptance(client,server))
        finally:server.kill()


if __name__=='__main__':
    if '--serve' in sys.argv:
        clock=Path(sys.argv[3]);uvicorn.run(create_app(clock=lambda:float(clock.read_text()),database_path=sys.argv[2]),host='127.0.0.1',port=PORT,log_level='warning')
    else:main()
