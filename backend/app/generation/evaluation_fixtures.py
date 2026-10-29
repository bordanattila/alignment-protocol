"""Deterministic synthetic histories played through production rules; no network."""
import json
from ..crises import load_crisis_sequence
from ..domain import Phase
from ..missions import MissionStore
from ..consequences import apply_metric_deltas
from .context import build_context
from .contract import GenerationRequest, GenerationError, FailureCategory, reference_history
from .endgame import EndgameRequest, build_endgame_request
from .provider import ProviderResponse
from .measurement import TokenUsage

HISTORIES=('fresh','resolved','infrastructure-damage','declining-trust','interconnected','varied')


def fixture(name):
    if name not in HISTORIES+('victory','defeat'):raise ValueError('Unknown fixture')
    now=[1_700_000_000.0];store=MissionStore(clock=lambda:now[0])
    mission,host=store.create('Fixture Host');credentials=[host.credential]
    for label in ('Fixture Second','Fixture Third'):credentials.append(store.join(mission.token,label)[1].credential)
    for p in mission.players:store.set_connected(mission.token,p.id,True)
    store.start(mission.token,credentials[0])
    count={'fresh':0,'resolved':3,'infrastructure-damage':4,'declining-trust':4,'interconnected':3,'varied':5,'victory':10,'defeat':4}[name]
    for index in range(count):
        choices=mission.crisis.choices
        if name=='defeat':choice=next(c for c in choices if c.id=='BAAA'[index])
        elif name in ('infrastructure-damage','declining-trust'):
            key='infrastructure' if name=='infrastructure-damage' else 'public_trust'
            viable=[c for c in choices if min(apply_metric_deltas(mission.metrics,c.metric_deltas).model_dump().values())>0]
            choice=min(viable or choices,key=lambda c:apply_metric_deltas(mission.metrics,c.metric_deltas).model_dump()[key])
        elif name=='interconnected':choice=next(c for c in choices if c.id=='ABA'[index])
        else:choice=max(choices,key=lambda c:min(apply_metric_deltas(mission.metrics,c.metric_deltas).model_dump().values()))
        store.begin_discussion(mission.token,credentials[0]);now[0]=mission.deadline;store.advance_due(mission.token)
        round_id=mission.rounds[-1].id
        for credential in credentials:store.vote(mission.token,credential,round_id,choice.id)
        if mission.phase==Phase.FAILED:break
        store.continue_mission(mission.token,credentials[0],mission.results[-1].id)
    if name in ('victory','defeat'):
        assert mission.phase==(Phase.COMPLETED if name=='victory' else Phase.FAILED)
        return build_endgame_request(mission)
    assert mission.phase==Phase.BRIEFING
    return GenerationRequest(context=build_context(mission))


class SimulationClock:
    """Scripted monotonic seconds, not measured hardware/provider performance."""
    def __init__(self):self.now=0.0
    def __call__(self):self.now+=.001;return round(self.now,6)
    def advance(self,seconds):self.now+=seconds


def scenario(request, mode='valid'):
    crisis=load_crisis_sequence()[0].model_dump(mode='json')
    crisis['title']='A New Civic Coordination Challenge'
    refs=[]
    history=reference_history(request.context)
    if mode=='linked' and history:
        decision=history[-1]
        refs=[{'crisis_number':decision.crisis_number,'choice_id':decision.choice_id}]
        crisis['briefing']='A new allocation dispute follows the recorded response. '+decision.consequence
    elif mode=='invented':refs=[{'crisis_number':10,'choice_id':'C'}]
    elif mode=='repeated-title':crisis['title']=request.context.narrative_memory.used_titles[-1]
    elif mode=='identical-effects':crisis['choices'][1]['metric_deltas']=crisis['choices'][0]['metric_deltas']
    elif mode=='duplicate-choice-text':crisis['choices'][1]['title']=crisis['choices'][0]['title']
    elif mode=='malformed':return '{invalid'
    elif mode=='schema':crisis['choices'][0]['metric_deltas']['safety']=999
    return json.dumps({'schema_version':'1.0','crisis':crisis,'continuity_references':refs})


def story(request,mode='valid'):
    refs=[request.context.history[-1].crisis_number]
    data={'schema_version':'endgame-1.0',
        'journey':{'text':'The team met civic pressures with the recorded responses, carrying their costs into later choices.','references':refs},
        'cost':{'text':'The final balance reflects real gains and losses rather than a costless path through the mission.','references':refs},
        'standing':{'text':('The city survived; its future rests on the tradeoffs accepted during the recorded journey.' if request.context.outcome=='victory' else
                           'The city collapsed; the recorded responses reveal the tradeoffs that preceded that ending.'),'references':refs}}
    if mode=='invented':data['journey']['references']=[10] if request.context.crises_completed<10 else [1,1]
    if mode=='schema':data['score']=100
    return json.dumps(data)


class FixtureProvider:
    def __init__(self,clock,mode):self.clock=clock;self.mode=mode;self.calls=0
    async def generate(self,request):
        self.calls+=1
        self.clock.advance(60.0 if self.mode=='timeout' else .2)
        if self.mode=='timeout':raise TimeoutError()
        if self.mode=='provider-error':raise GenerationError(FailureCategory.UNAVAILABLE,503)
        content=story(request,self.mode) if isinstance(request,EndgameRequest) else scenario(request,self.mode)
        usage=None if self.mode=='missing-usage' else TokenUsage(input_tokens=1000,output_tokens=600,total_tokens=1600)
        return ProviderResponse(content,200,usage)
