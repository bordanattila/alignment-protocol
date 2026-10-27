"""Offline seeded replay via production rules. Never runs during gameplay."""
import argparse
from collections import Counter
import json

from .campaign import Campaign, initial_sequence, load_campaign_catalog
from .consequences import apply_metric_deltas
from .domain import Phase
from .missions import MissionStore


def simulate(seed: str, path: str | None = None, policy: str = 'balanced') -> dict:
    if path is not None and (len(path) != 10 or set(path)-set('ABC')):
        raise ValueError('Replay requires exactly ten A/B/C choices')
    campaign=Campaign(seed=seed,scenarios=load_campaign_catalog());clock=[0.0]
    store=MissionStore(clock=lambda:clock[0],crisis_loader=lambda:initial_sequence(campaign))
    mission,host=store.create('Analysis host');store.join(mission.token,'Analysis guest')
    for player in mission.players:store.set_connected(mission.token,player.id,True)
    store.start(mission.token,host.credential);mission.campaign=campaign
    for index in range(10):
        store.begin_discussion(mission.token,host.credential);clock[0]=mission.deadline;store.advance_due(mission.token)
        if path:choice_id=path[index]
        elif policy=='AI':choice_id=mission.crisis.ai_recommendation_choice_id
        elif policy in 'ABC' and len(policy)==1:choice_id=policy
        elif policy=='balanced':
            choice_id=max(mission.crisis.choices,key=lambda c:min(apply_metric_deltas(mission.metrics,c.metric_deltas).model_dump().values())).id
        else:raise ValueError('Unknown analysis policy')
        for player in mission.players:store.vote(mission.token,player.credential,mission.rounds[-1].id,choice_id)
        if mission.phase==Phase.FAILED:break
        store.continue_mission(mission.token,host.credential,mission.results[-1].id)
    return {'seed':seed,'policy':policy,'path':''.join(r.decision.choice_id for r in mission.results),
            'phase':mission.phase,'scenario_ids':[r.crisis_id for r in mission.results],
            'metrics':mission.metrics.model_dump(),
            'score':sum(mission.metrics.model_dump().values())/4,
            'outcomes':[r.outcome for r in mission.results]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed');parser.add_argument('--choices');parser.add_argument('--sample',type=int,default=100)
    args=parser.parse_args()
    if args.seed is not None:result=simulate(args.seed,args.choices)
    else:
        if not 1<=args.sample<=1000:parser.error('--sample must be 1..1000')
        result={policy:dict(Counter(simulate(str(seed),policy=policy)['phase'] for seed in range(args.sample)))
                for policy in ['A','B','C','AI','balanced']}
    print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__=='__main__':main()
