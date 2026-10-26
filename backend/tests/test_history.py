"""Authoritative public ledger, derived review and synchronized recovery."""
import json

import pytest
from pydantic import ValidationError

from app.domain import Phase, Metrics
from app.missions import MissionError
from test_campaign import CampaignClients, SURVIVAL_PATH
from test_milestone3 import cast, expire
from test_milestone4 import team, resolve, open_initial


def projection(store, mission):
    return store.project(mission.token, mission.host_id)


def test_actual_starting_snapshot_and_no_summary_before_terminal():
    store,mission,host,clock=team()
    state=projection(store,mission)
    assert state['history']==[] and state['summary'] is None
    assert state['metrics_timeline']==[{'crisis_number':0,'metrics':Metrics().model_dump()}]
    mission.metrics.infrastructure=60
    assert projection(store,mission)['metrics_timeline'][0]['metrics']['infrastructure']==70


@pytest.mark.parametrize('reason',['initial_plurality','final_plurality','ai_tie_break','no_vote_ai_fallback'])
def test_result_history_preserves_public_context_tallies_flags_and_applied_values(reason):
    store,mission,host,clock=team()
    resolve(store,mission,host,clock,reason)
    state=projection(store,mission); entry=state['history'][0]
    assert len(state['history'])==1 and state['summary'] is None
    assert entry['crisis_number']==1 and entry['crisis_id']=='grid-under-pressure'
    assert entry['briefing']==mission.crisis.briefing
    assert entry['choices']==[{'id':c.id,'title':c.title,'description':c.description} for c in mission.crisis.choices]
    assert entry['decision']['reason']==reason
    final=reason in ('final_plurality','ai_tie_break')
    assert entry['consensus_window_occurred']==final and entry['final_vote_occurred']==final
    assert len(entry['voting_rounds'])==(2 if final else 1)
    if final: assert entry['voting_rounds'][0]['totals']=={'A':1,'B':1,'C':1}
    assert entry['voting_rounds'][-1]['totals']==entry['decision']['totals']
    assert entry['voting_rounds'][-1]['abstentions']==(3 if reason=='no_vote_ai_fallback' else 0)
    assert entry['before']==Metrics().model_dump()
    assert entry['after']==state['metrics_timeline'][-1]['metrics']==state['metrics']
    assert entry['applied_deltas']=={k:entry['after'][k]-entry['before'][k] for k in entry['before']}
    assert entry['status']=='resolved'
    assert all('votes' not in r and 'eligible' not in r for r in entry['voting_rounds'])


def test_two_one_one_is_initial_plurality_history():
    store,mission,host,clock=team(count=4); open_initial(store,mission,host,clock)
    cast(store,mission,['B','B','A','C'])
    entry=projection(store,mission)['history'][0]
    assert entry['decision']['reason']=='initial_plurality'
    assert entry['voting_rounds'][0]['totals']=={'A':1,'B':2,'C':1}
    assert not entry['consensus_window_occurred']


def test_tie_has_no_finalized_history_until_final_vote_and_records_abstentions():
    store,mission,host,clock=team(); open_initial(store,mission,host,clock)
    cast(store,mission,['A','B','C'])
    state=projection(store,mission)
    assert state['phase']=='consensus_window' and state['history']==[]
    assert len(state['metrics_timeline'])==1
    expire(store,mission,clock)
    store.vote(mission.token,host.credential,mission.rounds[-1].id,'B')
    expire(store,mission,clock)
    entry=projection(store,mission)['history'][0]
    assert entry['decision']['reason']=='final_plurality'
    assert entry['voting_rounds'][1]['totals']=={'A':0,'B':1,'C':0}
    assert entry['voting_rounds'][1]['abstentions']==2


def test_history_protected_from_live_objects_public_projection_and_later_crises():
    store,mission,host,clock=team(); resolve(store,mission,host,clock,'final_plurality')
    expected=projection(store,mission)['history']
    record=mission.results[0]
    with pytest.raises(ValidationError): record.crisis_title='Changed'
    mission.rounds[0].totals['A']=99
    mission.decision.totals['B']=99
    mission.crisis.briefing='Later mutation'
    mission.crisis.choices[0].description='Later mutation'
    mission.metrics.infrastructure=1
    assert projection(store,mission)['history']==expected
    mutable=projection(store,mission)
    mutable['history'][0]['before']['infrastructure']=0
    mutable['history'][0]['voting_rounds'][0]['totals']['A']=0
    mutable['history'].clear()
    assert projection(store,mission)['history']==expected
    store.continue_mission(mission.token,host.credential,record.id)
    assert projection(store,mission)['history']==expected
    assert mission.rounds==[] and mission.decision is None


def test_duplicate_resolution_ack_and_stale_callbacks_never_duplicate_history():
    store,mission,host,clock=team(); resolve(store,mission,host,clock,'initial_plurality')
    expected=projection(store,mission)['history']; result=mission.results[0]
    for _ in range(3): store._resolve(mission); assert store._apply_consequences(mission)==result
    store.continue_mission(mission.token,host.credential,result.id)
    for _ in range(3):
        assert not store.continue_mission(mission.token,host.credential,result.id)
        store._resolve(mission)
    assert projection(store,mission)['history']==expected


def test_history_uses_actual_clamped_deltas():
    store,mission,host,clock=team(); mission.metrics.infrastructure=99
    resolve(store,mission,host,clock,'initial_plurality')
    entry=projection(store,mission)['history'][0]
    assert entry['authored_deltas']['infrastructure']==5
    assert entry['before']['infrastructure']==99 and entry['after']['infrastructure']==100
    assert entry['applied_deltas']['infrastructure']==1


def test_history_mission_isolation_and_membership():
    store,mission,host,clock=team(); resolve(store,mission,host,clock,'initial_plurality')
    other,outsider=store.create('Other host')
    assert projection(store,other)['history']==[] and projection(store,other)['summary'] is None
    with pytest.raises(MissionError): store.project(mission.token,outsider.id)
    with pytest.raises(MissionError): store.authorize(mission.token,outsider.credential)


@pytest.mark.parametrize('collapse',[False,True])
def test_three_client_full_victory_or_early_defeat_summary_and_reconnect(collapse):
    with CampaignClients(3) as game:
        game.post('start'); expected_roles=[p.roles.copy() for p in game.mission.players]
        path='BAAA' if collapse else SURVIVAL_PATH
        previous=None
        for number,choice in enumerate(path,1):
            game.post('discussion'); game.tick()
            if number==2:
                frames=game.votes(['A','B','C'])
                assert frames[0]['phase']=='consensus_window'
                assert len(frames[0]['history'])==number-1
                game.tick()
            frames=game.votes([choice,choice,'A' if choice!='A' else 'B'])
            assert all(s['history']==frames[0]['history'] for s in frames)
            assert len(frames[0]['history'])==number
            if previous is not None: assert frames[0]['history'][:-1]==previous
            previous=frames[0]['history']
            for state in frames:
                history=json.dumps(state['history'])
                for crisis in game.mission.sequence:
                    for secret in crisis.private_intelligence.values(): assert secret not in history
                for player in game.mission.players: assert player.id not in history and player.credential not in history
            if game.mission.phase==Phase.FAILED: break
            _,frames=game.post('continue',{'result_id':frames[0]['result']['id']})
        state=frames[0]; summary=state['summary']
        assert state['phase']==('failed' if collapse else 'completed')
        assert summary['outcome']==('defeat' if collapse else 'victory')
        assert summary['crises_completed']==(4 if collapse else 10) and summary['total_crises']==10
        assert summary['final_metrics']==state['metrics']
        assert summary['consensus_score']==sum(state['metrics'].values())/4
        assert summary['consensus_windows']==summary['final_vote_crises']==1
        assert summary['resolution_breakdown']=={'initial_plurality':len(path)-1,'final_plurality':1,'ai_tie_break':0,'no_vote_ai_fallback':0}
        assert len(state['metrics_timeline'])==len(path)+1
        assert [p['crisis_number'] for p in state['metrics_timeline']]==list(range(len(path)+1))
        assert state['metrics_timeline'][-1]['metrics']==state['metrics']
        assert len({r['id'] for r in state['history']})==len(path)
        assert [p.roles for p in game.mission.players]==expected_roles
        if collapse:
            assert state['history'][-1]['status']=='collapsed' and 0 in state['history'][-1]['after'].values()
            assert state['consensus_score'] is None  # preserve existing live score contract
            assert game.client.post(f'/api/missions/{game.token}/continue',headers={'X-Mission-Session':game.host['credential']},json={'result_id':state['result']['id']}).status_code==409
        else: assert summary['consensus_score']==55.75
        # Fresh authenticated socket receives identical final history and summary.
        with game.client.websocket_connect(game.url) as restored:
            restored.send_json({'type':'authenticate','credential':game.sessions[1]['credential']})
            snapshot=restored.receive_json()['mission']
            for key in ['history','summary','metrics_timeline']: assert snapshot[key]==state[key]
            assert snapshot['revision']>state['revision']
            game.states()
        game.states()


def test_clients_cannot_submit_history_or_change_it_via_extra_intent_fields():
    with CampaignClients(3) as game:
        game.post('start'); game.post('discussion'); game.tick()
        game.sockets[0].send_json({'type':'vote','round_id':game.mission.rounds[-1].id,'choice_id':'A','history':[{'fake':True}]})
        assert game.sockets[0].receive_json()['type']=='error'
        assert not game.mission.results and not game.mission.rounds[-1].votes
        frames=game.votes(['B','B','A']); expected=frames[0]['history']
        response=game.client.post(f'/api/missions/{game.token}/continue',headers={'X-Mission-Session':game.host['credential']},json={'result_id':frames[0]['result']['id'],'history':[]})
        assert response.status_code==422 and projection(game.store,game.mission)['history']==expected


def test_snapshot_revisions_monotonic_across_broadcasts_and_identical_for_all_clients():
    with CampaignClients(3) as game:
        _,first=game.post('start'); _,second=game.post('discussion')
        assert first[0]['revision']<second[0]['revision']
        assert len({s['revision'] for s in first})==len({s['revision'] for s in second})==1
