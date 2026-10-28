"""Independent harness, deterministic continuation fallback and opt-out live game."""
import asyncio
from contextlib import ExitStack
import json

from fastapi.testclient import TestClient

from app.campaign import select_crisis
from app.generation.cli import run
from app.generation.config import GenerationSettings
from app.generation.context import build_context
from app.generation.contract import FailureCategory, GenerationRequest
from app.generation.provider import ProviderResponse
from app.generation.service import GenerationService, authored_selector
from app.main import create_app
from test_expansion import team, resolve
from test_foundation import create, authenticate
from test_generation_contract import proposal, context


class ValidProvider:
    async def generate(self,request):return ProviderResponse(json.dumps(proposal()))


def test_standalone_generation_and_fallback_do_not_change_mission_or_results():
    store,mission,credentials,clock=team('foundation-isolated')
    before=mission.model_dump_json()
    request=GenerationRequest(context=build_context(mission))
    selector=authored_selector(mission.campaign,0,[])
    result=asyncio.run(GenerationService(GenerationSettings(enabled=True),ValidProvider(),selector).generate(request))
    assert result.source=='generated' and result.snapshot.to_crisis().id!=mission.crisis.id
    assert mission.model_dump_json()==before and not mission.results
    assert 'PRIVATE-API-KEY' not in repr(result)


def test_followup_fallback_is_exact_milestone8_selection_without_state_mutation():
    store,mission,credentials,clock=team('foundation-followup')
    for index in range(3):
        resolve(store,mission,credentials,clock,'A' if index==0 else 'C')
        store.continue_mission(mission.token,credentials[0],mission.results[-1].id)
    expected=select_crisis(mission.campaign,3,mission.results)
    assert expected.id=='substation-reckoning'
    before=mission.model_dump_json()
    service=GenerationService(GenerationSettings(),fallback=authored_selector(mission.campaign,3,mission.results))
    first=asyncio.run(service.generate(GenerationRequest(context=build_context(mission))))
    second=asyncio.run(service.generate(GenerationRequest(context=build_context(mission))))
    assert first.snapshot==second.snapshot and first.snapshot.to_crisis()==expected
    assert mission.model_dump_json()==before


def test_default_application_never_calls_generation_even_when_environment_enabled(monkeypatch):
    monkeypatch.setenv('CONSENSUS_LLM_ENABLED','true')
    monkeypatch.setenv('CONSENSUS_LLM_API_KEY','PRIVATE-API-KEY-NEVER-SEND')
    def forbidden(*args,**kwargs):raise AssertionError('Live gameplay must not call generation')
    monkeypatch.setattr(GenerationService,'generate',forbidden)
    with TestClient(create_app()) as client:
        host=create(client);guest=client.post(f"/api/missions/{host['token']}/join",json={'callsign':'Guest'}).json()
        with ExitStack() as stack:
            first=stack.enter_context(client.websocket_connect(f"/api/missions/{host['token']}/ws"));authenticate(first,host['credential'])
            second=stack.enter_context(client.websocket_connect(f"/api/missions/{host['token']}/ws"));authenticate(second,guest['credential']);first.receive_json()
            response=client.post(f"/api/missions/{host['token']}/start",headers={'X-Mission-Session':host['credential']})
            assert response.status_code==200
            state=first.receive_json()['mission'];second.receive_json()
            assert state['crisis']['id']=='grid-under-pressure' and state['crisis_count']==10
            assert 'PRIVATE-API-KEY' not in json.dumps(state) and 'generated' not in state
            assert len(client.app.state.missions.get(host['token']).campaign.scenarios)==30
        assert all('generation' not in getattr(route,'path','') for route in client.app.routes)


def test_harness_fake_success_failure_and_disabled_modes_need_no_credentials(monkeypatch):
    for name in ['CONSENSUS_LLM_ENABLED','CONSENSUS_LLM_API_KEY','CONSENSUS_LLM_ENDPOINT','CONSENSUS_LLM_MODEL']:
        monkeypatch.delenv(name,raising=False)
    for mode,source,failure in [('disabled','authored','disabled'),('fake','generated',None),('failure','authored','unavailable'),('live','authored','disabled')]:
        result=asyncio.run(run(mode))
        assert result['source']==source and result['failure']==failure and result['scenario'] is not None


def test_default_harness_stays_offline_even_if_generation_env_is_enabled(monkeypatch):
    monkeypatch.setenv('CONSENSUS_LLM_ENABLED','true');monkeypatch.setenv('CONSENSUS_LLM_MODEL','fixture-model')
    monkeypatch.setenv('CONSENSUS_LLM_ENDPOINT','http://127.0.0.1:1/would-be-live')
    result=asyncio.run(run('disabled'))
    assert result['failure']=='disabled' and result['source']=='authored'
    monkeypatch.setenv('CONSENSUS_LLM_TIMEOUT_SECONDS','SECRET-INVALID-CONFIG')
    result=asyncio.run(run('fake'))
    assert result['failure']=='configuration' and result['source']=='authored'
    assert 'SECRET-INVALID-CONFIG' not in json.dumps(result)


def test_invalid_fallback_is_typed_without_logging_its_error(caplog):
    def broken():raise RuntimeError('PRIVATE-MISSION-DATA-FALLBACK')
    result=asyncio.run(GenerationService(GenerationSettings(),fallback=broken).generate(GenerationRequest(context=context())))
    assert result.snapshot is None and result.fallback_failure=='invalid_state' and result.failure==FailureCategory.DISABLED
    assert 'PRIVATE-MISSION-DATA-FALLBACK' not in caplog.text


def test_control_characters_cannot_masquerade_as_narrative_text():
    raw=proposal();raw['crisis']['briefing']='\0'*100
    class Provider:
        async def generate(self,request):return ProviderResponse(json.dumps(raw))
    result=asyncio.run(GenerationService(GenerationSettings(enabled=True),Provider()).generate(GenerationRequest(context=context())))
    assert result.snapshot is None and result.failure=='invalid_schema'
