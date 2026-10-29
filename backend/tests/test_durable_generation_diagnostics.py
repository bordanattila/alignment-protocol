"""Durable sanitized outcomes, private inspection, legacy records and content edits."""
import asyncio
import hashlib
import json
import sqlite3
import subprocess
import sys

import pytest
from pydantic import ValidationError

from app.campaign import load_campaign_catalog
from app.domain import GenerationDiagnostic, Phase
from app.generation.contract import FailureCategory
from app.generation.inspect_diagnostics import inspect
from app.missions import MissionStore
from app.persistence import SQLiteMissions, canonical, PersistenceError
from test_live_generation import setup, launch, settle, ProgressiveProvider
from test_persistence import ready, voting, votes


FIELDS={'crisis_number','source','category','duration_seconds','http_status','measurement'}


@pytest.mark.parametrize('failure,category,source',[
    (None,'success','generated'),
    (FailureCategory.UNAVAILABLE,'unavailable','authored_fallback'),
    (FailureCategory.TIMEOUT,'timeout','authored_fallback'),
    (FailureCategory.MODEL_UNAVAILABLE,'model_unavailable','authored_fallback'),
    (FailureCategory.QUOTA_EXCEEDED,'quota_exceeded','authored_fallback'),
    ('invalid','invalid_schema','authored_fallback'),
    (FailureCategory.INVALID_CONTINUITY,'invalid_continuity','authored_fallback'),
])
def test_result_diagnostic_commits_with_admission_and_survives_restart(tmp_path,failure,category,source):
    async def run():
        path=tmp_path/'results.sqlite3'
        provider=ProgressiveProvider({1:failure} if failure else None)
        store,mission,credentials,clock,live=setup(path,provider)
        await launch(live);await settle(live)
        assert len(provider.requests)==1 and len(mission.generation_diagnostics)==1
        record=mission.generation_diagnostics[0].model_dump(mode='json')
        assert set(record)==FIELDS and record['category']==category and record['source']==source
        assert record['crisis_number']==1 and record['duration_seconds']>=0
        token=mission.token;await live.close();store.close()
        assert inspect(path)==[record]
        restored=MissionStore(clock,persistence=SQLiteMissions(path));restored.initialize()
        mission=restored.get(token)
        assert mission.generation_diagnostics[0].model_dump(mode='json')==record
        assert len(provider.requests)==1
        restored.close()
    asyncio.run(run())


def test_http_status_and_duration_are_preserved_without_error_payload(tmp_path):
    from app.generation.provider import ChatCompletionsProvider
    from app.generation.config import GenerationSettings
    import httpx
    async def run():
        config=GenerationSettings(enabled=True,endpoint='http://localhost/fixture',model='fixture',require_api_key=False)
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(429,json={
            'error':{'code':'insufficient_quota','message':'PRIVATE-KEY-AND-PROMPT'}}))) as client:
            store,mission,credentials,clock,live=setup(tmp_path/'http.sqlite3',ChatCompletionsProvider(config,client))
            await launch(live);await settle(live)
            record=inspect(tmp_path/'http.sqlite3')[0]
            assert record['http_status']==429 and record['category']=='quota_exceeded'
            assert 'PRIVATE' not in json.dumps(record) and set(record)==FIELDS
            await live.close();store.close()
    asyncio.run(run())


def test_reconnect_and_public_projection_never_expose_private_diagnostics(tmp_path):
    async def run():
        path=tmp_path/'privacy.sqlite3';store,mission,credentials,clock,live=setup(path)
        await launch(live);await settle(live)
        token=mission.token;await live.close();store.close()
        restored=MissionStore(clock,persistence=SQLiteMissions(path));restored.initialize();mission=restored.get(token)
        ready(restored,mission)
        for player in mission.players:
            frame=restored.project(token,player.id)
            assert not any(key in frame for key in ('generation_diagnostics','admissions','category','http_status','duration_seconds'))
            assert set(frame['private_intelligence'])==set(player.roles)
            assert all(secret not in json.dumps(frame) for role,secret in mission.crisis.private_intelligence.items() if role not in player.roles)
        assert mission.generation_diagnostics
        restored.close()
    asyncio.run(run())


def test_cancel_and_restart_are_explicit_without_replaying_provider(tmp_path):
    async def run():
        path=tmp_path/'pending.sqlite3';provider=ProgressiveProvider(held=True)
        store,mission,credentials,clock,live=setup(path,provider)
        await launch(live);await provider.entered.wait();await live.close()
        assert mission.phase==Phase.PREPARING and inspect(path)[0]['category']=='canceled'
        token=mission.token;store.close()
        restored=MissionStore(clock,persistence=SQLiteMissions(path));restored.initialize()
        record=inspect(path)[0]
        assert record['category']=='restart_recovery' and record['source']=='authored_fallback'
        assert record['http_status'] is None and len(provider.requests)==1
        assert restored.get(token).phase==Phase.BRIEFING
        restored.close()
    asyncio.run(run())


def test_storage_retry_and_duplicate_progression_do_not_repeat_inference_or_diagnostics(tmp_path,monkeypatch):
    async def run():
        path=tmp_path/'retry.sqlite3';provider=ProgressiveProvider()
        store,mission,credentials,clock,live=setup(path,provider)
        save=store.persistence.save
        def broken(mission):raise PersistenceError('temporary')
        monkeypatch.setattr(store.persistence,'save',broken)
        await launch(live);await settle(live)
        assert not mission.generation_diagnostics and inspect(path)==[] and len(provider.requests)==1
        monkeypatch.setattr(store.persistence,'save',save)
        await launch(live);await settle(live)
        assert len(mission.generation_diagnostics)==1 and len(provider.requests)==1
        voting(store,mission,credentials,clock);votes(store,mission,credentials,['A']*3)
        result=mission.results[-1].id
        store.continue_mission(mission.token,credentials[0],result)
        for _ in range(4):
            assert not store.continue_mission(mission.token,credentials[0],result)
            await launch(live)
        await settle(live)
        assert len(provider.requests)==2
        assert [r['crisis_number'] for r in inspect(path)]==[1,2]
        await live.close();store.close()
    asyncio.run(run())


def test_stale_outcome_cannot_replace_newer_diagnostics(tmp_path):
    async def run():
        path=tmp_path/'stale.sqlite3';provider=ProgressiveProvider(held=True)
        store,mission,credentials,clock,live=setup(path,provider)
        await launch(live);await provider.entered.wait();old=mission.generation.id
        store.fail_generation(mission.token,old,GenerationDiagnostic(crisis_number=1,source=None,category='internal_state',duration_seconds=0.0))
        store.retry_generation(mission.token,credentials[0])
        provider.release.set();await settle(live)
        await launch(live);await settle(live)
        before=inspect(path)
        store.interrupt_generation(mission.token,old,GenerationDiagnostic(crisis_number=1,source=None,category='canceled',duration_seconds=1.0))
        assert inspect(path)==before and before[0]['category']=='success'
        await live.close();store.close()
    asyncio.run(run())


def test_legacy_payload_without_diagnostics_loads_without_inventing_historical_causes(tmp_path):
    async def run():
        path=tmp_path/'legacy.sqlite3';store,mission,credentials,clock,live=setup(path)
        await launch(live);await settle(live)
        voting(store,mission,credentials,clock);votes(store,mission,credentials,['B']*3)
        token=mission.token;old_crisis=mission.crisis.model_dump_json();old_result=mission.results[0]
        await live.close();store.close()
        with sqlite3.connect(path) as db:
            old_hash=db.execute('SELECT record_hash FROM resolutions').fetchone()[0]
            raw=json.loads(db.execute('SELECT payload FROM missions').fetchone()[0]);raw.pop('generation_diagnostics')
            text=canonical(raw);db.execute('UPDATE missions SET payload=?,checksum=?',(text,hashlib.sha256(text.encode()).hexdigest()))
        restored=MissionStore(clock,persistence=SQLiteMissions(path));restored.initialize();mission=restored.get(token)
        assert mission.generation_diagnostics==[] and inspect(path)==[]
        assert mission.crisis.model_dump_json()==old_crisis and mission.results[0]==old_result
        assert restored.persistence.connection.execute('SELECT record_hash FROM resolutions').fetchone()[0]==old_hash
        restored.close()
    asyncio.run(run())


def test_finalized_diagnostics_cannot_be_changed_or_removed(tmp_path):
    async def run():
        path=tmp_path/'immutable.sqlite3';store,mission,credentials,clock,live=setup(path)
        await launch(live);await settle(live)
        before=mission.generation_diagnostics[0]
        mission.generation_diagnostics[0]=before.model_copy(update={'duration_seconds':999.0})
        with pytest.raises(PersistenceError):store.bump_revision(mission.token)
        mission.generation_diagnostics=[]
        with pytest.raises(PersistenceError):store.bump_revision(mission.token)
        await live.close();store.close()
    asyncio.run(run())


def test_diagnostic_model_forbids_payloads_and_invalid_metadata():
    base={'crisis_number':1,'source':'generated','category':'success','duration_seconds':1.0,'http_status':200}
    for update in [{'prompt':'PRIVATE'},{'category':'PRIVATE'},{'http_status':'PRIVATE'},
                   {'duration_seconds':float('nan')},{'crisis_number':11},{'category':'timeout'}]:
        with pytest.raises(ValidationError):GenerationDiagnostic(**(base|update))


def test_developer_inspection_is_read_only_and_prints_only_bounded_fields(tmp_path):
    async def run():
        path=tmp_path/'inspection.sqlite3';store,mission,credentials,clock,live=setup(path)
        await launch(live);await settle(live)
        before=store.persistence.connection.execute('SELECT payload,checksum FROM missions').fetchall()
        assert all(set(r)==FIELDS for r in inspect(path))
        process=subprocess.run([sys.executable,'-m','app.generation.inspect_diagnostics',
            '--database',str(path)],capture_output=True,text=True,check=True)
        assert json.loads(process.stdout)==inspect(path) and not process.stderr
        assert store.persistence.connection.execute('SELECT payload,checksum FROM missions').fetchall()==before
        with pytest.raises(ValueError):inspect(path,0)
        with pytest.raises(sqlite3.Error):inspect(tmp_path/'missing.sqlite3')
        assert not (tmp_path/'missing.sqlite3').exists()
        await live.close();store.close()
    asyncio.run(run())


def test_authored_briefings_do_not_duplicate_the_recommendation_and_cooling_effects_are_preserved():
    catalog=load_campaign_catalog()
    assert len(catalog)==30
    for entry in catalog:
        assert 'AI recommendation:' not in entry.crisis.briefing
    cooling=next(entry.crisis for entry in catalog if entry.crisis.id=='cooling-access')
    assert cooling.briefing==('Cooling halls are near capacity during a second hot afternoon. '
        'The city must choose how to distribute staff, electricity and access before the overnight heat peak.')
    assert cooling.ai_recommendation_choice_id=='B'
    assert next(c.description for c in cooling.choices if c.id=='B')=='Staff the central halls and provide scheduled transport.'
    assert [c.metric_deltas.model_dump() for c in cooling.choices]==[
        {'infrastructure':-5,'public_trust':3,'economy':4,'safety':-4},
        {'infrastructure':4,'public_trust':-5,'economy':2,'safety':5},
        {'infrastructure':-3,'public_trust':6,'economy':-5,'safety':3}]


def test_previously_saved_briefing_and_result_hash_are_not_rewritten_by_source_content_fix(tmp_path):
    from test_milestone3 import Clock
    clock=Clock();path=tmp_path/'old-content.sqlite3'
    old=next(s.crisis for s in load_campaign_catalog() if s.crisis.id=='cooling-access').model_copy(deep=True)
    old.briefing+=' AI recommendation: Staff the central halls and provide scheduled transport. This prioritizes immediate safety under the current constraints.'
    store=MissionStore(clock,crisis_loader=lambda:[old],persistence=SQLiteMissions(path));store.initialize()
    mission,host=store.create('Host');guest=store.join(mission.token,'Guest')[1]
    ready(store,mission);store.start(mission.token,host.credential)
    credentials=[host.credential,guest.credential]
    voting(store,mission,credentials,clock);votes(store,mission,credentials,['B','B'])
    token=mission.token;result=mission.results[0];old_hash=store.persistence.connection.execute('SELECT record_hash FROM resolutions').fetchone()[0]
    store.close()
    restored=MissionStore(clock,persistence=SQLiteMissions(path));restored.initialize()
    assert restored.get(token).crisis.briefing==old.briefing
    assert restored.get(token).results[0]==result
    assert restored.persistence.connection.execute('SELECT record_hash FROM resolutions').fetchone()[0]==old_hash
    restored.close()
