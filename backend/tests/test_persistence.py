"""Real new stores/apps over temporary SQLite, deterministic UTC test clocks."""
from contextlib import ExitStack
import hashlib
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.crises import load_crisis_sequence
from app.domain import Phase
from app.main import create_app
from app.missions import MissionStore, MissionError
from app.persistence import SQLiteMissions, PersistenceError, canonical
from test_foundation import authenticate, create
from test_milestone3 import Clock


def open_store(path, clock):
    store=MissionStore(clock, persistence=SQLiteMissions(path)); store.initialize()
    return store


def team(path,clock):
    store=open_store(path,clock); mission,host=store.create('Host')
    credentials=[host.credential]
    for name in ['Guest','Third']: credentials.append(store.join(mission.token,name)[1].credential)
    ready(store,mission)
    store.start(mission.token,credentials[0])
    return store,mission,credentials


def ready(store,mission):
    for player in list(mission.players): store.set_connected(mission.token,player.id,True)


def voting(store,mission,credentials,clock):
    store.begin_discussion(mission.token,credentials[0]); clock.now=mission.deadline; store.advance_due(mission.token)


def votes(store,mission,credentials,choices):
    round_id=mission.rounds[-1].id
    for credential,choice in zip(credentials,choices): store.vote(mission.token,credential,round_id,choice)


def restart(store,path,clock):
    store.close(); return open_store(path,clock)


def test_mission_join_and_independent_identities_survive_new_store_without_plaintext_secrets(tmp_path):
    path=tmp_path/'missions.sqlite3'; clock=Clock(); store=open_store(path,clock)
    first,host=store.create('Host'); second,other=store.create('Other')
    guest=store.join(first.token,'Guest')[1]
    token=first.token; identities=[p.id for p in first.players]
    credentials=[host.credential,guest.credential,other.credential]
    store=restart(store,path,clock)
    assert store.get(token).phase==Phase.LOBBY
    assert [p.id for p in store.get(token).players]==identities
    assert store.authorize(token,credentials[1]).callsign=='Guest'
    assert store.get(second.token).players[0].callsign=='Other'
    with pytest.raises(MissionError): store.authorize(token,credentials[2])
    with pytest.raises(MissionError): store.authorize(token,'invalid')
    with pytest.raises(MissionError): store.join(token,'Guest')
    with sqlite3.connect(path) as connection:
        payload=''.join(row[0] for row in connection.execute('SELECT payload FROM missions'))
        assert all(secret not in payload for secret in credentials)
        assert connection.execute('PRAGMA user_version').fetchone()[0]==2
    for file in tmp_path.glob('missions.sqlite3*'):
        assert all(secret.encode() not in file.read_bytes() for secret in credentials)
    assert path.stat().st_mode & 0o777==0o600
    store.close()


def test_roles_private_content_chat_and_revision_restore_without_reloading_authored_pool(tmp_path):
    path=tmp_path/'missions.sqlite3'; clock=Clock(); store,mission,credentials=team(path,clock)
    store.begin_discussion(mission.token,credentials[0]); store.send_chat(mission.token,credentials[1],'Compare the hospital risk.')
    store.bump_revision(mission.token); state=store.project(mission.token,mission.players[1].id)
    token=mission.token; roles=[list(p.roles) for p in mission.players]
    original_deadline=mission.deadline; store.close()
    def unavailable(): raise AssertionError('Recovery must not reload authored pool')
    store=MissionStore(clock,unavailable,SQLiteMissions(path)); store.initialize(); mission=store.get(token)
    assert mission.phase==Phase.RECONNECT_WAIT and mission.recovery_deadline==original_deadline
    assert not any(p.connected for p in mission.players)
    assert [p.roles for p in mission.players]==roles
    assert store.project(token,mission.players[1].id)['chat']==state['chat']
    assert mission.revision>state['revision']
    for i,player in enumerate(mission.players):
        assert store.authorize(token,credentials[i]).id==player.id
        projected=store.project(token,player.id)
        assert projected['private_intelligence']=={r:mission.crisis.private_intelligence[r] for r in player.roles}
        for role,secret in mission.crisis.private_intelligence.items():
            assert (secret in json.dumps(projected))==(role in player.roles)
    ready(store,mission); assert mission.phase==Phase.DISCUSSION and mission.deadline==original_deadline
    assert mission.sequence==load_crisis_sequence()
    with pytest.raises(MissionError): store.send_chat(token,credentials[1],'Still rate limited')
    clock.now+=1; store.send_chat(token,credentials[1],'Confirmed after restart.')
    chat=store.project(token,mission.players[1].id)['chat']
    store=restart(store,path,clock)
    assert store.project(token,mission.players[1].id)['chat']==chat and len(chat)==2
    store.close()


@pytest.mark.parametrize('phase',['discussion','voting','consensus_window','final_voting'])
@pytest.mark.parametrize('expired',[False,True])
def test_timer_recovery_preserves_deadlines_votes_and_mandatory_opportunities(tmp_path,phase,expired):
    path=tmp_path/'missions.sqlite3'; clock=Clock(); store,mission,credentials=team(path,clock)
    store.begin_discussion(mission.token,credentials[0])
    if phase!='discussion': clock.now=mission.deadline; store.advance_due(mission.token)
    if phase in ['consensus_window','final_voting']:
        votes(store,mission,credentials,['A','B','C'])
        if phase=='final_voting': clock.now=mission.deadline; store.advance_due(mission.token)
    if phase in ['voting','final_voting']: store.vote(mission.token,credentials[0],mission.rounds[-1].id,'B')
    old_deadline=mission.deadline; old_rounds=[r.model_dump() for r in mission.rounds]; token=mission.token
    clock.now=old_deadline+(1000 if expired else -5)
    store=restart(store,path,clock); mission=store.get(token)
    if expired and phase in ['voting','final_voting']:
        assert mission.phase==Phase.DECISION_LOCKED
        assert len(mission.results)==1 and mission.decision.choice_id=='B'
        assert mission.results[0].voting_rounds[-1].abstentions==2
        before=canonical(mission.results[0].model_dump(mode='json'))
        store=restart(store,path,clock); mission=store.get(token)
        assert canonical(mission.results[0].model_dump(mode='json'))==before
    else:
        assert mission.phase==Phase.RECONNECT_WAIT and mission.deadline is None
        assert mission.recovery_deadline==old_deadline
        with pytest.raises(MissionError): store.vote(token,credentials[0],'stale','A')
        ready(store,mission)
        if expired:
            assert mission.phase==Phase.VOTING and mission.deadline==clock.now+30
            assert mission.rounds[-1].number==(2 if phase=='consensus_window' else 1)
        else:
            expected=Phase.VOTING if phase in ['voting','final_voting'] else Phase(phase)
            assert mission.phase==expected and mission.deadline==old_deadline
            assert [r.model_dump() for r in mission.rounds]==old_rounds
    store.close()


def test_expired_tied_vote_holds_new_consensus_until_all_seats_then_fresh_final_vote(tmp_path):
    path=tmp_path/'missions.sqlite3'; clock=Clock(); store,mission,credentials=team(path,clock)
    voting(store,mission,credentials,clock)
    store.vote(mission.token,credentials[0],mission.rounds[-1].id,'A')
    store.vote(mission.token,credentials[1],mission.rounds[-1].id,'B')
    clock.now=mission.deadline+500; token=mission.token
    store=restart(store,path,clock); mission=store.get(token)
    assert mission.phase==Phase.RECONNECT_WAIT and mission.recovery_phase==Phase.CONSENSUS_WINDOW
    assert mission.recovery_deadline is None
    assert mission.rounds[0].totals=={'A':1,'B':1,'C':0}
    clock.now+=1000
    store=restart(store,path,clock); mission=store.get(token)
    assert mission.recovery_deadline is None
    ready(store,mission); assert mission.phase==Phase.CONSENSUS_WINDOW and mission.deadline==clock.now+20
    clock.now=mission.deadline; store.advance_due(token)
    assert mission.phase==Phase.VOTING and mission.deadline==clock.now+30
    votes(store,mission,credentials,['A','B','C'])
    assert mission.decision.reason=='ai_tie_break'
    assert len(mission.results)==1
    store.close()


def test_waiting_vote_expires_during_recovery_and_rejects_late_submission(tmp_path):
    path=tmp_path/'missions.sqlite3'; clock=Clock(); store,mission,credentials=team(path,clock)
    voting(store,mission,credentials,clock); round_id=mission.rounds[-1].id; token=mission.token
    store=restart(store,path,clock); mission=store.get(token)
    clock.now=mission.recovery_deadline+1
    with pytest.raises(MissionError): store.vote(token,credentials[0],round_id,'B')
    assert mission.phase==Phase.DECISION_LOCKED and mission.decision.reason=='no_vote_ai_fallback'
    store=restart(store,path,clock)
    assert len(store.get(token).results)==1
    store.close()


def test_duplicate_saved_vote_and_consequence_and_ack_are_idempotent_after_restart(tmp_path):
    path=tmp_path/'missions.sqlite3'; clock=Clock(); store,mission,credentials=team(path,clock)
    voting(store,mission,credentials,clock); round_id=mission.rounds[-1].id; token=mission.token
    store.vote(token,credentials[0],round_id,'B'); store=restart(store,path,clock); mission=store.get(token); ready(store,mission)
    with pytest.raises(MissionError): store.vote(token,credentials[0],round_id,'A')
    store.vote(token,credentials[1],round_id,'B'); store.vote(token,credentials[2],round_id,'A')
    metrics=mission.metrics.model_dump(); record=mission.results[0].model_dump(mode='json')
    store=restart(store,path,clock); mission=store.get(token); ready(store,mission)
    assert store._apply_consequences(mission).model_dump(mode='json')==record
    assert mission.metrics.model_dump()==metrics
    assert store.continue_mission(token,credentials[0],round_id)
    store=restart(store,path,clock); mission=store.get(token)
    assert not store.continue_mission(token,credentials[0],round_id)
    assert mission.crisis_index==1 and len(mission.results)==1
    store.close()


@pytest.mark.parametrize('collapse',[False,True])
def test_full_production_victory_or_defeat_canonical_review_equal_after_restart(tmp_path,collapse):
    path=tmp_path/'missions.sqlite3'; clock=Clock(); store,mission,credentials=team(path,clock)
    token=mission.token; guest_id=mission.players[1].id
    for choice in ('BAAA' if collapse else 'BBBCCBCAAC'):
        voting(store,mission,credentials,clock); votes(store,mission,credentials,[choice]*3)
        if mission.phase==Phase.FAILED: break
        store.continue_mission(token,credentials[0],mission.results[-1].id)
    before=store.project(token,guest_id)
    store=restart(store,path,clock); mission=store.get(token); after=store.project(token,guest_id)
    assert after['phase']==('failed' if collapse else 'completed')
    for key in ['history','metrics_timeline','summary','chat','metrics','roles','private_intelligence']:
        assert canonical(after[key])==canonical(before[key])
    assert len(after['history'])==(4 if collapse else 10)
    assert after['revision']>before['revision']
    store.close()


def test_storage_failure_rolls_back_resolving_vote_metrics_and_ledger_atomically(tmp_path):
    path=tmp_path/'missions.sqlite3'; clock=Clock(); store,mission,credentials=team(path,clock)
    voting(store,mission,credentials,clock); token=mission.token; round_id=mission.rounds[-1].id
    for credential in credentials[:2]: store.vote(token,credential,round_id,'B')
    before=mission.model_dump()
    store.persistence.connection.execute("CREATE TRIGGER fail_results BEFORE INSERT ON resolutions BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
    with pytest.raises(PersistenceError): store.vote(token,credentials[2],round_id,'A')
    assert mission.model_dump()==before
    store.persistence.connection.execute('DROP TRIGGER fail_results')
    store=restart(store,path,clock); mission=store.get(token); ready(store,mission)
    assert not mission.results and len(mission.rounds[-1].votes)==2
    store.vote(token,credentials[2],round_id,'A')
    assert len(mission.results)==1
    with sqlite3.connect(path) as connection: assert connection.execute('SELECT count(*) FROM resolutions').fetchone()[0]==1
    store.close()


def test_failed_create_not_acknowledged_and_cache_restored(tmp_path,monkeypatch):
    clock=Clock(); store=open_store(tmp_path/'missions.sqlite3',clock)
    def fail(_mission, **_metadata): raise PersistenceError('Storage unavailable')
    monkeypatch.setattr(store.persistence,'save',fail)
    with pytest.raises(PersistenceError): store.create('Host')
    assert not store._missions
    store.close()


@pytest.mark.parametrize('mode',['corrupt-file','schema','record-version','checksum','valid-json-invalid-model','result-index'])
def test_corrupt_or_unsupported_database_fails_closed_without_deleting_records(tmp_path,mode):
    path=tmp_path/'missions.sqlite3'; clock=Clock()
    if mode=='corrupt-file': path.write_bytes(b'not a database')
    else:
        store,mission,credentials=team(path,clock)
        voting(store,mission,credentials,clock); votes(store,mission,credentials,['B']*3); store.close()
        with sqlite3.connect(path) as connection:
            if mode=='schema': connection.execute('PRAGMA user_version=999')
            elif mode=='record-version': connection.execute('UPDATE missions SET format_version=999')
            elif mode=='checksum': connection.execute("UPDATE missions SET checksum='bad'")
            elif mode=='result-index': connection.execute('DELETE FROM resolutions')
            else:
                payload='{}'; connection.execute('UPDATE missions SET payload=?,checksum=?',(payload,hashlib.sha256(payload.encode()).hexdigest()))
    with pytest.raises(PersistenceError): open_store(path,clock)
    assert path.exists() and path.stat().st_size>0


def test_single_owner_prevents_conflicting_runtime_caches(tmp_path):
    path=tmp_path/'missions.sqlite3'; clock=Clock(); store=open_store(path,clock)
    with pytest.raises(PersistenceError): open_store(path,clock)
    store.close(); other=open_store(path,clock); other.close()


def test_real_new_application_same_database_restores_identity_snapshots_and_credentials(tmp_path):
    path=tmp_path/'missions.sqlite3'; clock=Clock(); app=create_app(clock,database_path=path)
    with TestClient(app) as client:
        host=create(client,'Host'); token=host['token']
        guest=client.post(f'/api/missions/{token}/join',json={'callsign':'Guest'}).json()
        with ExitStack() as stack:
            first=stack.enter_context(client.websocket_connect(f'/api/missions/{token}/ws')); authenticate(first,host['credential'])
            second=stack.enter_context(client.websocket_connect(f'/api/missions/{token}/ws')); authenticate(second,guest['credential']); first.receive_json()
            headers={'X-Mission-Session':host['credential']}
            client.post(f'/api/missions/{token}/start',headers=headers)
            before=first.receive_json()['mission']; second.receive_json()
    fresh=create_app(clock,database_path=path)
    assert fresh is not app and fresh.state.missions is not app.state.missions
    with TestClient(fresh) as client:
        restored=client.post(f'/api/missions/{token}/join',json={'callsign':'Ignored'},headers={'X-Mission-Session':guest['credential']})
        assert restored.json()==guest
        assert client.post(f'/api/missions/{token}/join',json={'callsign':'Ignored'},headers={'X-Mission-Session':'invalid'}).status_code==401
        with client.websocket_connect(f'/api/missions/{token}/ws') as socket:
            state=authenticate(socket,host['credential'])
            for key in ['phase','roles','metrics','history','crisis','private_intelligence']: assert state[key]==before[key]
            assert state['revision']>before['revision']


def test_sqlite_prevents_duplicate_crisis_records_and_history_mutation(tmp_path):
    path=tmp_path/'missions.sqlite3'; clock=Clock(); store,mission,credentials=team(path,clock)
    voting(store,mission,credentials,clock); votes(store,mission,credentials,['B']*3)
    with pytest.raises(sqlite3.IntegrityError):
        with store.persistence.connection:
            store.persistence.connection.execute('INSERT INTO resolutions VALUES (?,?,?,?)',(mission.token,'other-round',1,'{}'))
    record=mission.results[0]
    mission.results[0]=record.model_copy(update={'outcome':'Changed'})
    with pytest.raises(PersistenceError): store.persistence.save(mission)
    mission.results[0]=record
    store.close()


def test_http_storage_failure_returns_503_without_accepting_a_mission(tmp_path,monkeypatch):
    app=create_app(database_path=tmp_path/'missions.sqlite3')
    with TestClient(app) as client:
        def fail(_mission, **_metadata): raise PersistenceError('Storage unavailable')
        monkeypatch.setattr(app.state.missions.persistence,'save',fail)
        response=client.post('/api/missions',json={'callsign':'Host'})
        assert response.status_code==503 and response.json()['code']=='storage_unavailable'
        assert not app.state.missions._missions


def test_restore_final_voting_and_tallies_after_unexpired_consensus_restart(tmp_path):
    path=tmp_path/'missions.sqlite3'; clock=Clock(); store,mission,credentials=team(path,clock)
    voting(store,mission,credentials,clock); votes(store,mission,credentials,['A','B','C'])
    token=mission.token; store=restart(store,path,clock); mission=store.get(token); ready(store,mission)
    assert mission.phase==Phase.CONSENSUS_WINDOW
    clock.now=mission.deadline; store.advance_due(token)
    votes(store,mission,credentials,['A','B','C'])
    before=store.project(token,mission.host_id)
    store=restart(store,path,clock); after=store.project(token,mission.host_id)
    assert after['history']==before['history'] and after['closed_rounds']==before['closed_rounds']
    assert after['history'][0]['decision']['reason']=='ai_tie_break'
    assert len(after['history'][0]['voting_rounds'])==2
    store.close()


def test_transient_disconnect_is_not_rolled_back_when_storage_is_unavailable(tmp_path,monkeypatch):
    path=tmp_path/'missions.sqlite3'; clock=Clock(); store,mission,_=team(path,clock)
    def fail(_mission, **_metadata): raise PersistenceError('Storage unavailable')
    monkeypatch.setattr(store.persistence,'save',fail)
    store.set_connected(mission.token,mission.players[1].id,False)
    assert not mission.players[1].connected
    store.close()


def test_failed_publication_is_retried_without_new_gameplay_action(tmp_path,monkeypatch):
    app=create_app(Clock(),database_path=tmp_path/'missions.sqlite3')
    with TestClient(app) as client:
        host=create(client,'Host'); token=host['token']
        guest=client.post(f'/api/missions/{token}/join',json={'callsign':'Guest'}).json()
        with ExitStack() as stack:
            first=stack.enter_context(client.websocket_connect(f'/api/missions/{token}/ws')); authenticate(first,host['credential'])
            second=stack.enter_context(client.websocket_connect(f'/api/missions/{token}/ws')); authenticate(second,guest['credential']); first.receive_json()
            original=app.state.missions.bump_revision; unavailable=True
            def fail_publication(token):
                if unavailable: raise PersistenceError('Storage unavailable')
                return original(token)
            monkeypatch.setattr(app.state.missions,'bump_revision',fail_publication)
            assert client.post(f'/api/missions/{token}/start',headers={'X-Mission-Session':host['credential']}).status_code==503
            unavailable=False
            client.portal.call(app.state.tick)
            assert first.receive_json()['mission']['phase']=='briefing'
            assert second.receive_json()['mission']['phase']=='briefing'
