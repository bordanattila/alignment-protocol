"""Expanded catalog, deterministic branching, durable legacy compatibility and multiplayer."""
import hashlib
import json
import sqlite3
from collections import Counter

import pytest

from app.campaign import Campaign, initial_sequence, load_campaign_catalog, select_crisis, validate_catalog, STAGES
from app.consequences import apply_metric_deltas
from app.domain import Crisis, Metrics, Phase, Role, Scenario
from app.missions import MissionStore, MissionError
from app.persistence import SQLiteMissions, canonical, PersistenceError
from test_campaign import CampaignClients
from test_milestone3 import Clock
from test_persistence import voting, votes, ready


def team(seed='test',path=None):
    clock=Clock();campaign=Campaign(seed=seed,scenarios=load_campaign_catalog())
    store=MissionStore(clock,crisis_loader=lambda:initial_sequence(campaign),persistence=SQLiteMissions(path) if path else None)
    store.initialize();mission,host=store.create('Host');_,guest=store.join(mission.token,'Guest')
    credentials=[host.credential,guest.credential];ready(store,mission);store.start(mission.token,credentials[0])
    mission.campaign=campaign
    # Persist via the same revision-intent boundary, with no fabricated ledger.
    store.bump_revision(mission.token)
    return store,mission,credentials,clock


def resolve(store,mission,credentials,clock,choice):
    voting(store,mission,credentials,clock);votes(store,mission,credentials,[choice]*len(credentials))


def balanced(mission):
    return max(mission.crisis.choices,key=lambda c:min(apply_metric_deltas(mission.metrics,c.metric_deltas).model_dump().values())).id


def test_thirty_unique_authored_scenarios_full_role_intelligence_and_no_dominated_choice():
    catalog=load_campaign_catalog()
    assert len(catalog)==30 and len({s.crisis.id for s in catalog})==30
    assert {s.category for s in catalog}=={'infrastructure','public_trust','economy','safety','environment','ethics'}
    assert sum(s.prerequisite is not None for s in catalog)==5
    assert set(Counter(s.crisis.ai_recommendation_choice_id for s in catalog))=={'A','B','C'}
    for entry in catalog:
        crisis=entry.crisis
        assert Crisis.model_validate(crisis.model_dump())==crisis
        assert len(crisis.briefing)>100 and set(crisis.private_intelligence)==set(Role)
        assert len(set(crisis.private_intelligence.values()))==4
        assert all(len(text)>50 for text in crisis.private_intelligence.values())
        assert len({c.description for c in crisis.choices})==3
        for a in crisis.choices:
            x=a.metric_deltas.model_dump()
            assert any(v>0 for v in x.values()) and any(v<0 for v in x.values())
            assert len(a.consequence)>50 and a.description!=a.consequence
            for b in crisis.choices:
                y=b.metric_deltas.model_dump()
                assert a is b or not(all(x[k]>=y[k] for k in x) and any(x[k]>y[k] for k in x))


@pytest.mark.parametrize('error',['duplicate','missing-source','same-stage','cycle','fallback-shortage','choice-duplicate'])
def test_catalog_dependency_errors_rejected_before_mutation(error):
    pool=load_campaign_catalog();dependent=next(s for s in pool if s.prerequisite)
    if error=='duplicate':pool.append(pool[0])
    elif error=='missing-source':dependent.prerequisite.crisis_id='missing'
    elif error=='same-stage':dependent.stage=1
    elif error=='cycle':next(s for s in pool if s.crisis.id==dependent.prerequisite.crisis_id).prerequisite=dependent.prerequisite
    elif error=='fallback-shortage':pool=[s for s in pool if s.stage!=3 or s.prerequisite]
    else:dependent.prerequisite.choice_ids=['A','A']
    with pytest.raises(ValueError):validate_catalog(pool)
    store=MissionStore(campaign_loader=lambda:pool);mission,host=store.create('Host');store.join(mission.token,'Guest');ready(store,mission)
    with pytest.raises(ValueError):store.start(mission.token,host.credential)
    assert mission.phase==Phase.LOBBY and not any(p.roles for p in mission.players)


@pytest.mark.parametrize('error',['bad-id','bad-choice','missing-metric','extra-metric','float-delta','wrong-role'])
def test_expanded_scenario_schema_rejects_invalid_content(error):
    raw=load_campaign_catalog()[-1].crisis.model_dump(mode='json')
    if error=='bad-id':raw['id']='../secret'
    elif error=='bad-choice':raw['choices'][1]['id']='A'
    elif error=='missing-metric':del raw['choices'][0]['metric_deltas']['safety']
    elif error=='extra-metric':raw['choices'][0]['metric_deltas']['unknown']=1
    elif error=='float-delta':raw['choices'][0]['metric_deltas']['safety']=1.1
    else:raw['private_intelligence']['unknown']='secret'
    with pytest.raises(ValueError):Crisis.model_validate(raw)


def test_seeded_selection_is_reproducible_varied_paced_and_exactly_ten():
    pool=load_campaign_catalog();plans=[];stages={s.crisis.id:s.stage for s in pool}
    for seed in range(100):
        campaign=Campaign(seed=str(seed),scenarios=pool)
        first=initial_sequence(campaign);second=initial_sequence(campaign)
        assert first==second and len({c.id for c in first})==10
        assert tuple(stages[c.id] for c in first)==STAGES
        assert first[0].id=='grid-under-pressure' and first[-1].id=='the-last-coordination'
        assert not any(next(s for s in pool if s.crisis.id==c.id).prerequisite for c in first)
        plans.append(tuple(c.id for c in first))
    assert len(set(plans))>90


@pytest.mark.parametrize('first_choice',['A','B'])
def test_prior_choice_selects_followup_or_safe_fallback_and_records_public_context(first_choice):
    store,mission,credentials,clock=team('branch')
    original=mission.campaign.model_dump_json()
    for index in range(3):
        resolve(store,mission,credentials,clock,first_choice if index==0 else 'C')
        store.continue_mission(mission.token,credentials[0],mission.results[-1].id)
    if first_choice=='A':
        assert mission.crisis.id=='substation-reckoning'
        assert 'Earlier decision — Crisis 1, Grid Under Pressure: A' in mission.crisis.briefing
        # Outcomes are still private until executed; context is shared public history.
        before=store.project(mission.token,mission.players[0].id)
        assert mission.crisis.choices[0].consequence not in json.dumps(before)
        resolve(store,mission,credentials,clock,'B')
        assert 'Earlier decision — Crisis 1' in mission.results[-1].outcome
    else:assert mission.crisis.id!='substation-reckoning'
    assert mission.campaign.model_dump_json()==original  # materialization does not mutate templates
    assert len(mission.sequence)==len({c.id for c in mission.sequence})==10


def test_expanded_ten_crisis_victory_and_summary_come_only_from_actual_results():
    store,mission,credentials,clock=team('victory')
    for _ in range(10):
        before=mission.metrics;choice=next(c for c in mission.crisis.choices if c.id==balanced(mission))
        resolve(store,mission,credentials,clock,choice.id)
        assert mission.metrics==apply_metric_deltas(before,choice.metric_deltas)
        assert store._apply_consequences(mission).id==mission.results[-1].id
        store.continue_mission(mission.token,credentials[0],mission.results[-1].id)
    assert mission.phase==Phase.COMPLETED and len(mission.results)==10
    state=store.project(mission.token,mission.host_id);summary=state['summary']
    assert summary['consensus_score']==sum(mission.metrics.model_dump().values())/4
    assert mission.results[-1].outcome in summary['narrative_outcome']
    assert len(summary['notable_decisions'])==3
    for highlight in summary['notable_decisions']:
        result=mission.results[highlight['crisis_number']-1]
        assert highlight['outcome']==result.outcome and highlight['choice_title']==result.choice_title
    assert not store.continue_mission(mission.token,credentials[0],mission.results[-1].id)


def test_expanded_clamping_and_zero_defeat_keep_existing_rules():
    store,mission,credentials,clock=team('collapse');mission.metrics=Metrics(infrastructure=99,public_trust=1,economy=70,safety=70)
    mission.initial_metrics=mission.metrics.model_copy(deep=True)
    resolve(store,mission,credentials,clock,'A')
    assert mission.phase==Phase.FAILED and mission.metrics.infrastructure==100 and mission.metrics.public_trust==0
    assert mission.results[0].applied_deltas.infrastructure==1
    summary=store.project(mission.token,mission.host_id)['summary']
    assert 'Public Trust reached zero' in summary['narrative_outcome']
    assert summary['consensus_score']==sum(mission.metrics.model_dump().values())/4


def test_expanded_seed_catalog_history_and_future_branch_survive_restart_without_content_reads(tmp_path):
    path=tmp_path/'missions.sqlite3';store,mission,credentials,clock=team('restart',path)
    token=mission.token
    for i in range(3):
        resolve(store,mission,credentials,clock,'A' if i==0 else 'C')
        store.continue_mission(token,credentials[0],mission.results[-1].id)
    assert mission.crisis.id=='substation-reckoning'
    before=store.project(token,mission.host_id);sequence=mission.sequence;campaign=mission.campaign
    store.close()
    def unavailable():raise AssertionError('Recovery must not reload authored content')
    store=MissionStore(clock,crisis_loader=unavailable,campaign_loader=unavailable,persistence=SQLiteMissions(path));store.initialize()
    try:
        restored=store.get(token);assert restored.campaign==campaign and restored.sequence==sequence
        ready(store,restored);after=store.project(token,restored.host_id)
        for key in ['crisis','history','roles','private_intelligence','metrics']:assert before[key]==after[key]
        resolve(store,restored,credentials,clock,'B')
        store.continue_mission(token,credentials[0],restored.results[-1].id)
        assert len(restored.results)==4
    finally:store.close()


def test_pre_milestone8_payload_without_campaign_field_and_result_hashes_stays_recoverable(tmp_path):
    from test_persistence import team as legacy_team
    path=tmp_path/'legacy.sqlite3';clock=Clock();store,mission,credentials=legacy_team(path,clock)
    resolve(store,mission,credentials,clock,'B');token=mission.token;before=canonical(mission.results[0].model_dump(mode='json'));store.close()
    with sqlite3.connect(path) as db:
        payload=json.loads(db.execute('SELECT payload FROM missions').fetchone()[0]);payload.pop('campaign')
        text=canonical(payload);db.execute('UPDATE missions SET payload=?,checksum=?',(text,hashlib.sha256(text.encode()).hexdigest()))
        hashes=db.execute('SELECT * FROM resolutions').fetchall()
    store=MissionStore(clock,persistence=SQLiteMissions(path));store.initialize()
    try:
        restored=store.get(token);assert restored.campaign is None
        assert canonical(restored.results[0].model_dump(mode='json'))==before
        assert store.persistence.connection.execute('SELECT * FROM resolutions').fetchall()==hashes
        assert store.persistence.connection.execute('PRAGMA user_version').fetchone()[0]==2
    finally:store.close()


@pytest.mark.parametrize('count',[2,3,4])
def test_expanded_multiplayer_ten_crisis_consensus_privacy_presence_and_history(count):
    with CampaignClients(count,crisis_loader=None) as game:
        game.post('start');assert game.mission.campaign is not None
        for index in range(10):
            game.post('discussion');game.tick()
            if index==1:
                # Tie the first vote and exercise the unchanged final opportunity.
                first=['A','B'] if count==2 else ['A','B','C'] if count==3 else ['A','B','A','B']
                game.votes(first);assert game.mission.phase==Phase.CONSENSUS_WINDOW;game.tick()
            choice=balanced(game.mission);frames=game.votes([choice]*count)
            assert all(s['history']==frames[0]['history'] and s['metrics']==frames[0]['metrics'] for s in frames)
            assert all(len(s['history'])==index+1 for s in frames)
            for player,frame in zip(game.mission.players,frames):
                for entry in game.mission.campaign.scenarios:
                    for role,secret in entry.crisis.private_intelligence.items():
                        assert (secret in json.dumps(frame,ensure_ascii=False))==(entry.crisis.id==game.mission.crisis.id and role in player.roles)
                assert 'campaign' not in frame and 'sequence' not in frame
            game.post('continue',{'result_id':frames[0]['result']['id']})
        assert game.mission.phase==Phase.COMPLETED


@pytest.mark.parametrize('error',['missing','orphan','invalid-id','wrong-id','duplicate','bad-metadata'])
def test_expansion_loader_rejects_broken_catalog_references(tmp_path,error):
    from pathlib import Path
    from shutil import copytree
    root=Path(__file__).resolve().parents[1]/'app'/'content'
    copytree(root,tmp_path/'content');directory=tmp_path/'content';manifest=directory/'expansion'/'catalog.json'
    records=json.loads(manifest.read_text());key=records[-1]['id'];path=directory/'expansion'/f'{key}.json'
    if error=='missing':path.unlink()
    elif error=='orphan':(directory/'expansion'/'orphan.json').write_text(path.read_text())
    elif error=='invalid-id':records[-1]['id']='../private'
    elif error=='wrong-id':raw=json.loads(path.read_text());raw['id']='wrong-id';path.write_text(json.dumps(raw))
    elif error=='duplicate':records.append(records[-1])
    else:records={}
    manifest.write_text(json.dumps(records))
    with pytest.raises((ValueError,FileNotFoundError)):load_campaign_catalog(directory)


def test_replay_preserves_decision_dependent_sequence_metrics_and_outcomes():
    from app.expansion_analysis import simulate
    first=simulate('reproducible')
    assert first['phase']=='completed' and len(first['path'])==10
    replay=simulate('reproducible',first['path'])
    for key in ['scenario_ids','metrics','score','outcomes','path']:assert replay[key]==first[key]


@pytest.mark.parametrize('child',[s.crisis.id for s in load_campaign_catalog() if s.prerequisite])
def test_each_authored_followup_selects_only_for_its_recorded_parent_choice(child):
    pool=load_campaign_catalog();entry=next(s for s in pool if s.crisis.id==child)
    parent=next(s.crisis for s in pool if s.crisis.id==entry.prerequisite.crisis_id)
    store,mission,credentials,clock=team();resolve(store,mission,credentials,clock,'A')
    base=mission.results[0];slot=3 if entry.stage==2 else 6
    for choice in parent.choices:
        record=base.model_copy(update={'crisis_id':parent.id,'crisis_title':parent.title,
            'choice_title':choice.title,'choice_description':choice.description,
            'decision':base.decision.model_copy(update={'choice_id':choice.id})})
        selected=select_crisis(Campaign(seed='followup-test',scenarios=pool),slot,[record])
        if choice.id in entry.prerequisite.choice_ids:
            assert selected.id==child
            assert parent.title in selected.briefing and choice.title in selected.briefing
            assert all(entry.prerequisite.context in c.consequence for c in selected.choices)
        else:
            assert selected.id!=child
            assert next(s for s in pool if s.crisis.id==selected.id).prerequisite is None


def test_authored_ai_advice_can_succeed_or_fail_and_deliberate_tradeoffs_can_survive():
    from app.expansion_analysis import simulate
    assert simulate('0',policy='AI')['phase']=='completed'
    assert simulate('11',policy='AI')['phase']=='failed'
    assert simulate('11',policy='balanced')['phase']=='completed'
