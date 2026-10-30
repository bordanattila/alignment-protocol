"""One-shot Stage B revalidation: fake providers unless separately authorized. No retries, production edits, or raw response logs."""
import argparse
import asyncio
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values
from pydantic import ValidationError
from app.campaign import Campaign, load_campaign_catalog
from app.domain import Phase, GenerationAttempt, CrisisAdmission, GenerationDiagnostic
from app.generation.config import GenerationSettings
from app.generation.contract import AcceptedScenario, CrisisProposal
from app.generation.endgame import EndgameRequest
from app.generation.evaluation import review_template, result_document
from app.generation.evaluation_report import EvaluationRecord, Pricing
import app.generation.evaluation_fixtures as fixtures
from app.generation.provider import ChatCompletionsProvider
from app.generation.service import GenerationService, authored_selector
from app.missions import MissionStore
from app.persistence import SQLiteMissions

CASES=[('crisis-fresh','fresh'),('crisis-infrastructure','infrastructure-damage'),
       ('crisis-trust','declining-trust'),('crisis-interconnected','interconnected')]
PRICE=Pricing(input_per_million='0.10',output_per_million='0.50')
LIMIT=Decimal('1.00')

class BatchStop(BaseException): pass
STOP={'authentication','configuration','disabled','quota_exceeded','model_unavailable','unsupported_format','invalid_provider_schema'}
FIELDS={'schema_version','crisis','choices','private_intelligence','infrastructure','community','economy','safety',
        'public_trust','metric_deltas','title','description','consequence','briefing','ai_recommendation_choice_id',
        'id','continuity_references','choice_id','crisis_number','journey','cost','standing','text','references'}


def write(path,value):
    text=json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True)+'\n'
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as stream:stream.write(text);stream.flush();os.fsync(stream.fileno())


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def history(mission):
    return [{'crisis_number':r.crisis_number,'crisis_id':r.crisis_id,'title':r.crisis_title,
             'briefing':r.briefing,'choice_id':r.decision.choice_id,'choice_title':r.choice_title,
             'outcome':r.outcome,'before':r.before.model_dump(),'after':r.after.model_dump(),
             'applied_deltas':r.applied_deltas.model_dump()} for r in mission.results]


def build(name):
    """Capture the existing fixture's store, without altering its choices or rules."""
    captured=[];original=fixtures.MissionStore
    class CapturedStore(MissionStore):
        def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);captured.append(self)
    fixtures.MissionStore=CapturedStore
    try:request=fixtures.fixture(name)
    finally:fixtures.MissionStore=original
    store=captured[0];mission=store.get(store.mission_tokens()[0])
    # Seed a generated-mode test aggregate with locally executed authored history.
    # No provider attempts are attributed to these reference snapshots.
    mission.mode='generated';mission.campaign=Campaign(seed='stage-a-'+name,scenarios=load_campaign_catalog())
    mission.sequence=mission.sequence[:len(mission.results)]
    mission.admissions=[]
    for crisis in mission.sequence:
        snapshot=AcceptedScenario.from_crisis(crisis)
        mission.admissions.append(CrisisAdmission(source='authored_fallback',canonical_json=snapshot.canonical_json,
            content_hash=hashlib.sha256(snapshot.canonical_json.encode()).hexdigest()))
    if isinstance(request,EndgameRequest):raise BatchStop('endgame_not_authorized')
    mission.phase=Phase.PREPARING;mission.crisis_index=max(0,len(mission.results)-1)
    mission.crisis=mission.sequence[-1] if mission.sequence else None
    mission.generation=GenerationAttempt(id=os.urandom(24).hex(),target_index=len(mission.results))
    mission.deadline=None;mission.rounds=[];mission.decision=None
    return request,store,mission


BASELINE=Path('docs/acceptance/milestone_9_5_stage_a')
PRESERVED=Path('docs/revalidation/milestone_9_5_stage_b/preserved-evidence.json')


def verify_preserved():
    manifest=json.loads(PRESERVED.read_text())
    if any(not Path(name).is_file() or digest(name)!=expected for name,expected in manifest.items()):
        raise BatchStop('preserved_evidence_changed')


def comparison(records,live):
    from app.generation.evaluation_report import report,estimate_cost
    old=[EvaluationRecord.model_validate(r) for r in json.loads((BASELINE/'diagnostics.json').read_text()) if r['case_id'] in {key for key,name in CASES}]
    def paired(record):
        if record is None:return None
        d=record.diagnostic;m=d.measurement
        return {'source':d.source,'category':str(d.category),'http_status':d.http_status,
                'schema_accepted':d.source=='generated' and d.category=='success',
                'total_seconds':d.duration_seconds,'provider_seconds':m.provider_seconds if m else None,
                'validation_seconds':m.validation_seconds if m else None,
                'reference_count':m.reference_count if m else None,
                'usage':m.usage.model_dump() if m and m.usage else None,
                'calculated_cost':estimate_cost([record],{'gpt-6-luna':PRICE})}
    return {'baseline':{'evidence_mode':'real-stage-a','metrics':report(old),'cost':estimate_cost(old,{'gpt-6-luna':PRICE}),
                        'human_meaningful_continuity':'pending'},
            'revalidation':{'status':'executed' if live else 'not_executed_authorization_pending',
                            'metrics':report(records) if live else None,
                            'cost':estimate_cost(records,{'gpt-6-luna':PRICE}) if live else None,
                            'human_meaningful_continuity':'pending'},
            'dry_run_functional_checks':report(records) if not live else None,
            'per_case':[{'case_id':r.case_id,'stage_a_category':r.diagnostic.category,
                         'stage_a_references':r.diagnostic.measurement.reference_count,
                         'stage_a':paired(r),'revalidation':paired(next((n for n in records if n.case_id==r.case_id),None)) if live else None,
                         'revalidation_category':next((n.diagnostic.category for n in records if n.case_id==r.case_id),None) if live else None,
                         'human_comparison':'pending'} for r in old],
            'warning':'Fake results test the harness only. Valid references are not a human semantic score.'}


class BudgetProvider:
    def __init__(self,settings,folder,live):
        self.settings=settings;self.folder=folder;self.live=live
        self.adapter=ChatCompletionsProvider(settings) if live else None
        self.attempts=[];self.spent=Decimal(0);self.reserved=Decimal(0);self.largest={}
        self.case=None;self.operation=None;self.response=None;self.stop_reason=None
    def estimated(self,op):return max(Decimal('.0015' if op=='crisis' else '.0023'),self.largest.get(op,Decimal(0)))
    async def generate(self,request):
        if len(self.attempts)>=4:raise BatchStop('request_budget_exhausted')
        if self.settings.model!='gpt-6-luna' or self.settings.timeout_seconds!=60:raise BatchStop('configuration_mismatch')
        if isinstance(request,EndgameRequest):raise BatchStop('endgame_not_authorized')
        op='crisis'
        pending=CASES[len(self.attempts):]
        projected=self.spent+self.reserved+sum((self.estimated('endgame' if key.startswith('endgame') else 'crisis') for key,name in pending),Decimal(0))
        if projected>LIMIT:raise BatchStop('projected_spending_limit')
        item={'attempt':len(self.attempts)+1,'case_id':self.case,'operation':op,
              'status':'attempted','projected_total_before_dispatch_usd':str(projected)}
        self.attempts.append(item)
        write(self.folder/'attempt-journal.json',self.attempts)  # Count BEFORE dispatch.
        print(json.dumps({'event':'dispatch',**item}),flush=True)
        if self.live:self.response=await self.adapter.generate(request)
        else:self.response=await fixtures.FixtureProvider(fixtures.SimulationClock(),'valid').generate(request)
        return self.response
    def account(self,diagnostic):
        m=diagnostic.measurement;u=m.usage if m else None
        op=self.attempts[-1]['operation']
        if u and u.input_tokens is not None and u.output_tokens is not None:
            amount=(u.input_tokens*PRICE.input_per_million+u.output_tokens*PRICE.output_per_million)/Decimal(1_000_000)
            self.spent+=amount;self.largest[op]=max(amount,self.largest.get(op,Decimal(0)))
            self.attempts[-1]['known_estimated_cost_usd']=str(amount)
        else:
            # Unknown billing is reserved conservatively, never treated as free.
            reserve=10*self.estimated(op);self.reserved+=reserve
            self.stop_reason='unknown_billing_stop'
            self.attempts[-1]['unknown_billing_reserve_usd']=str(reserve)
        self.attempts[-1]['status']='completed-or-fallback'
        write(self.folder/'attempt-journal.json',self.attempts)
        if self.spent+self.reserved>LIMIT:self.stop_reason='observed_spending_limit'


def schema_issues(response,request):
    if response is None:return []
    try:
        CrisisProposal.model_validate_json(response.content)
        return []
    except ValidationError as exc:
        return [{'path':[part if type(part) is int else part if part in FIELDS else 'extra_field' for part in e['loc']],
                 'type':e['type']} for e in exc.errors(include_input=False,include_context=False,include_url=False)][:12]
    except (ValueError,TypeError,RecursionError):return [{'path':[],'type':'invalid_json'}]


async def run(live=False, output=None):
    settings=(GenerationSettings.from_env({k:v for k,v in dotenv_values('backend/.env').items() if v is not None}) if live else
              GenerationSettings(enabled=True,model='gpt-6-luna',timeout_seconds=60,response_format='json_schema'))
    assert settings.model=='gpt-6-luna' and settings.timeout_seconds==60 and settings.enabled
    assert settings.response_format=='json_schema'
    if live:assert settings.api_key and urlsplit(settings.endpoint).hostname=='api.openai.com'
    verify_preserved()
    root=Path(output) if output else Path('/tmp/ce95b-revalidation-live' if live else '/tmp/ce95b-revalidation-dry')
    root.mkdir(mode=0o700,exist_ok=False)  # Refuse rerunning/replacing an existing batch.
    provider=BudgetProvider(settings,root,live)
    source_files=['backend/app/generation/provider.py','backend/app/generation/service.py','backend/app/generation/contract.py',
                  'backend/app/generation/context.py','backend/app/generation/endgame.py','backend/app/generation/conclusion_live.py',
                  'backend/app/generation/config.py','backend/app/missions.py']
    before={p:digest(p) for p in source_files}
    db=SQLiteMissions(root/'isolated.sqlite3');db.open()
    stage_a_public={r['case_id']:r for r in json.loads((BASELINE/'public-review.json').read_text())}
    records=[];public=[];checks=[];saved=[];stop_reason=None
    try:
        for case,name in CASES:
            verify_preserved()
            request,store,mission=build(name)
            original=stage_a_public[case]
            assert history(mission)==original['authoritative_history'] and mission.metrics.model_dump()==original['metrics']
            store.persistence=db;db.save(mission)
            base_history=[r.model_dump_json() for r in mission.results];base_metrics=mission.metrics.model_dump()
            original_hashes=db.connection.execute('SELECT result_id,record_hash FROM resolutions WHERE mission_token=?',(mission.token,)).fetchall()
            provider.case=case;provider.response=None
            attempt=mission.generation
            outcome=await GenerationService(settings,provider,authored_selector(mission.campaign,attempt.target_index,mission.results)).generate(request)
            diagnostic=GenerationDiagnostic(crisis_number=request.context.current_crisis_number,
                source='generated' if outcome.source=='generated' else 'authored_fallback' if outcome.snapshot else None,
                category=outcome.failure or 'success',duration_seconds=outcome.duration_seconds,
                http_status=outcome.http_status,measurement=outcome.measurement)
            assert outcome.snapshot is not None
            assert store.accept_generation(mission.token,attempt.id,outcome.snapshot,diagnostic.source,diagnostic)
            references=[r.model_dump() for r in outcome.snapshot.continuity_references] if diagnostic.source=='generated' else []
            public_content=store.project(mission.token,mission.host_id)['crisis']
            records.append(EvaluationRecord(case_id=case,diagnostic=diagnostic))
            provider.account(diagnostic)
            unchanged=base_history==[r.model_dump_json() for r in mission.results] and base_metrics==mission.metrics.model_dump()
            assert unchanged
            assert original_hashes==db.connection.execute('SELECT result_id,record_hash FROM resolutions WHERE mission_token=?',(mission.token,)).fetchall()
            frames=[store.project(mission.token,p.id) for p in mission.players]
            for p,frame in zip(mission.players,frames):
                assert set(frame['private_intelligence'])==set(p.roles)
                assert all(text not in json.dumps(frame) for role,text in mission.crisis.private_intelligence.items() if role not in p.roles)
                assert 'measurement' not in json.dumps(frame) and 'basis_hash' not in json.dumps(frame)
            assert all(f['crisis']==frames[0]['crisis'] for f in frames)
            issues=schema_issues(provider.response,request) if diagnostic.category!='success' else []
            item={'case_id':case,'operation':'crisis',
                'source':diagnostic.source,'category':str(diagnostic.category),'public_content':public_content,
                'authoritative_history':history(mission),'metrics':base_metrics,'validated_references':references,
                'schema_issues':issues,'human_scores_status':'pending','continuity_human_classification':None}
            public.append(item)
            checks.append({'case_id':case,'history_and_metrics_unchanged':unchanged,'private_projections_passed':True,
                           'common_public_content_passed':True,'result_hashes_unchanged':True})
            saved.append((mission.token,case,mission.crisis.model_dump_json(),store._summary(mission),[list(p.roles) for p in mission.players]))
            write(root/'diagnostics.json',[r.model_dump(mode='json') for r in records])
            write(root/'public-review.json',public)
            write(root/'automated-checks.json',checks)
            print(json.dumps({'event':'outcome','case_id':case,'source':diagnostic.source,'category':str(diagnostic.category),
                'seconds':diagnostic.duration_seconds,'usage':diagnostic.measurement.usage.model_dump() if diagnostic.measurement and diagnostic.measurement.usage else None,
                'known_estimated_cumulative_cost_usd':str(provider.spent),'schema_issues':issues}),flush=True)
            provider.response=None
            if provider.stop_reason:
                stop_reason=provider.stop_reason;break
            if str(diagnostic.category) in STOP:
                stop_reason='unexpected_authorization_or_configuration';break
        assert before=={p:digest(p) for p in source_files}
        write(root/'source-integrity.json',{'unchanged':True,'sha256':before})
    except BatchStop as reason:
        stop_reason=str(reason)
    finally:
        provider.response=None;db.close()
        document=result_document(records,'real-provider-stage-b-revalidation' if live else 'offline-dry-run-not-real-revalidation',{'gpt-6-luna':PRICE})
        document['authorization']={'request_limit':4,'administrative_ceiling_usd':'1.00','automatic_retries':False,
                                   'actual_attempts':len(provider.attempts),'is_real_provider_run':live}
        document['stop_reason']=stop_reason
        document['known_estimated_cost_usd']=str(provider.spent)
        document['unknown_billing_reserve_usd']=str(provider.reserved)
        write(root/'evaluation.json',document)
        sheet=review_template([case for case,name in CASES])
        for row in sheet['cases']:row['continuity_classification']=None
        write(root/'human-review.json',sheet)
        write(root/'comparison.json',comparison(records,live))
    restored=MissionStore(persistence=SQLiteMissions(root/'isolated.sqlite3'));restored.initialize()
    try:
        for token,case,crisis,summary,roles in saved:
            mission=restored.get(token)
            assert json.loads(mission.crisis.model_dump_json())==json.loads(crisis) and restored._summary(mission)==summary
            assert [list(p.roles) for p in mission.players]==roles
        write(root/'restart-checks.json',{'passed':True,'cases':len(saved),'provider_requests_during_restart':0})
    finally:restored.close()
    print(json.dumps({'event':'batch_finished','live':live,'attempts':len(provider.attempts),'folder':str(root),
                      'known_estimated_cost_usd':str(provider.spent),'unknown_billing_reserve_usd':str(provider.reserved)}),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorized-live-four',action='store_true',help='Requires separate explicit human approval; NOT authorized by preparation')
    parser.add_argument('--output',type=Path,help='New isolated directory; cannot exist already')
    args=parser.parse_args()
    asyncio.run(run(args.authorized_live_four,args.output))
