"""Regression for the shipped v1 record column hidden by empty databases."""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.persistence import PersistenceError, canonical
from test_milestone3 import Clock
from test_persistence import team, voting, votes


LEGACY_TABLE = 'CREATE TABLE resolutions (mission_token TEXT NOT NULL REFERENCES missions(token), result_id TEXT NOT NULL, crisis_number INTEGER NOT NULL, record TEXT NOT NULL, PRIMARY KEY(mission_token,result_id), UNIQUE(mission_token,crisis_number))'


def empty_legacy(path):
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE missions (token TEXT PRIMARY KEY, format_version INTEGER NOT NULL, payload TEXT NOT NULL, checksum TEXT NOT NULL)')
        db.execute(LEGACY_TABLE)
        db.execute('PRAGMA user_version=1')


def downgrade_fixture(path, layout):
    with sqlite3.connect(path) as db:
        if layout=='record':
            db.execute('ALTER TABLE resolutions RENAME TO hash_fixture')
            db.execute(LEGACY_TABLE)
            for token,payload in db.execute('SELECT token,payload FROM missions').fetchall():
                for result in json.loads(payload)['results']:
                    db.execute('INSERT INTO resolutions VALUES (?,?,?,?)',(token,result['id'],result['crisis_number'],canonical(result)))
            db.execute('DROP TABLE hash_fixture')
        db.execute('PRAGMA user_version=1')


def test_actual_empty_v1_layout_http_creation_persistence_multiple_missions_and_restart(tmp_path):
    path=tmp_path/'missions.sqlite3'; empty_legacy(path)
    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.OperationalError,match='no such column: record_hash'):
            db.execute('SELECT result_id,record_hash FROM resolutions WHERE mission_token=?',('probe',))
    sessions=[]
    with TestClient(create_app(database_path=path)) as client:
        for name in ['First','Second','Third']:
            response=client.post('/api/missions',json={'callsign':name})
            assert response.status_code==201
            sessions.append(response.json())
        assert client.post('/api/missions',json={'callsign':' '}).status_code==422
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==2
        assert [row[1] for row in db.execute('PRAGMA table_info(resolutions)')][-1]=='record_hash'
        assert db.execute('SELECT count(*) FROM missions').fetchone()[0]==3
    with TestClient(create_app(database_path=path)) as client:
        for session in sessions:
            response=client.post(f"/api/missions/{session['token']}/join",headers={'X-Mission-Session':session['credential']},json={'callsign':'Ignored rename'})
            assert response.status_code==200 and response.json()==session
        assert client.post(f"/api/missions/{sessions[0]['token']}/join",headers={'X-Mission-Session':'invalid'},json={'callsign':'Ignored'}).status_code==401


@pytest.mark.parametrize('layout',['record','record_hash'])
def test_both_v1_layouts_preserve_complete_history_score_roles_and_exactly_once(tmp_path,layout):
    path=tmp_path/'missions.sqlite3'; clock=Clock(); store,mission,credentials=team(path,clock)
    token=mission.token; guest=mission.players[1].id
    for choice in 'BBBCCBCAAC':
        voting(store,mission,credentials,clock); votes(store,mission,credentials,[choice]*3)
        store.continue_mission(token,credentials[0],mission.results[-1].id)
    before=store.project(token,guest); result_id=mission.results[-1].id
    store.close(); downgrade_fixture(path,layout)
    with TestClient(create_app(clock,database_path=path)) as client:
        restored=client.app.state.missions
        player=restored.authorize(token,credentials[1])
        after=restored.project(token,player.id)
        for key in ['history','summary','metrics_timeline','metrics','roles','private_intelligence']:
            assert canonical(after[key])==canonical(before[key])
        assert after['summary']['consensus_score']==55.75
        assert not restored.continue_mission(token,credentials[0],result_id)
        assert len(restored.get(token).results)==10
        assert restored._apply_consequences(restored.get(token)).id==result_id
        assert client.post('/api/missions',json={'callsign':'New mission'}).status_code==201
        for role,text in restored.get(token).crisis.private_intelligence.items():
            assert (text in json.dumps(after))==(role in player.roles)
        with sqlite3.connect(path) as db:
            assert db.execute('PRAGMA user_version').fetchone()[0]==2
            assert db.execute('SELECT count(*) FROM resolutions').fetchone()[0]==10
            with pytest.raises(sqlite3.IntegrityError):
                db.execute('INSERT INTO resolutions VALUES (?,?,?,?)',(token,'duplicate-crisis',1,'invalid'))
    with TestClient(create_app(clock,database_path=path)) as client:
        after=client.app.state.missions.project(token,guest)
        assert after['history']==before['history'] and after['summary']==before['summary']


@pytest.mark.parametrize('damage',['invalid-json','wrong-id','different-outcome'])
def test_bad_legacy_history_rolls_back_migration_without_overwriting_data(tmp_path,damage):
    path=tmp_path/'missions.sqlite3'; clock=Clock(); store,mission,credentials=team(path,clock)
    voting(store,mission,credentials,clock); votes(store,mission,credentials,['B']*3)
    store.close(); downgrade_fixture(path,'record')
    with sqlite3.connect(path) as db:
        text=db.execute('SELECT record FROM resolutions').fetchone()[0]
        if damage=='invalid-json': text='{'
        else:
            record=json.loads(text); record['id' if damage=='wrong-id' else 'outcome']='Invalid historical mutation'; text=canonical(record)
        db.execute('UPDATE resolutions SET record=?',(text,))
        original=db.execute('SELECT * FROM missions').fetchall(),db.execute('SELECT * FROM resolutions').fetchall()
    with pytest.raises(PersistenceError):
        with TestClient(create_app(clock,database_path=path)): pass
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==1
        assert [row[1] for row in db.execute('PRAGMA table_info(resolutions)')][-1]=='record'
        assert (db.execute('SELECT * FROM missions').fetchall(),db.execute('SELECT * FROM resolutions').fetchall())==original


@pytest.mark.parametrize('version',[1,2])
def test_incompatible_empty_layout_fails_at_startup_instead_of_first_post(tmp_path,version):
    path=tmp_path/'missions.sqlite3'; empty_legacy(path)
    with sqlite3.connect(path) as db:
        if version==1: db.execute('ALTER TABLE resolutions RENAME COLUMN record TO unknown_column')
        db.execute(f'PRAGMA user_version={version}')
    with pytest.raises(PersistenceError,match='schema does not match'):
        with TestClient(create_app(database_path=path)): pass
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==version
        assert db.execute('SELECT count(*) FROM missions').fetchone()[0]==0
