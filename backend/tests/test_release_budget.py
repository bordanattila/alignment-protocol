"""Release controls only: isolated ledgers and fake HTTP, never live inference."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3

import httpx
import pytest
from pydantic import SecretStr

from app.generation.config import GenerationSettings
from app.generation.contract import GenerationRequest,GenerationError
from app.generation.provider import ProviderResponse
from app.generation.release_budget import (ReleaseBudget,BoundedReleaseProvider,BudgetUnavailable,
    MAX_REQUEST_BYTES,OUTPUT_TOKEN_BOUND,INPUT_TOKEN_BOUND)
from app.generation.service import GenerationService
from test_generation_contract import context,proposal


def settings(**changes):
    return GenerationSettings(enabled=True,endpoint='https://api.openai.com/v1/chat/completions',
        model='gpt-6-luna',api_key=SecretStr('test-not-a-real-key'),timeout_seconds=60,**changes)


def test_exclusive_initialization_and_missing_or_corrupt_never_reset(tmp_path):
    path=tmp_path/'budget.sqlite3'
    with pytest.raises(BudgetUnavailable):ReleaseBudget(path).status()
    b=ReleaseBudget.initialize(path);b.reserve('crisis')
    with pytest.raises(FileExistsError):ReleaseBudget.initialize(path)
    assert ReleaseBudget(path).status()['attempts']==1
    with sqlite3.connect(path) as db:db.execute('DELETE FROM attempts')
    with pytest.raises(BudgetUnavailable):b.reserve('crisis')


def test_acceptance_exactly_one_then_operator_verified_public_lifetime_ceiling(tmp_path):
    path=tmp_path/'budget.sqlite3';b=ReleaseBudget.initialize(path)
    with pytest.raises(BudgetUnavailable):b.open_public()
    b.reserve('crisis')
    with pytest.raises(BudgetUnavailable):ReleaseBudget(path).reserve('crisis')
    b.mark_verified();b.open_public()
    def reserve(_):
        try:ReleaseBudget(path).reserve('crisis');return True
        except BudgetUnavailable:return False
    with ThreadPoolExecutor(max_workers=8) as workers:results=list(workers.map(reserve,range(120)))
    assert sum(results)==99
    assert ReleaseBudget(path).status()['reserved_microusd']==1_000_000
    assert ReleaseBudget(path).status()['attempts']==100
    with pytest.raises(BudgetUnavailable):b.reserve('endgame')


def fake_response(usage=True):
    value={'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(proposal())}}]}
    if usage:value['usage']={'prompt_tokens':3000,'completion_tokens':2000,'total_tokens':5000}
    return value


def test_actual_adapter_reserves_before_http_and_bounds_payload(tmp_path):
    b=ReleaseBudget.initialize(tmp_path/'budget.sqlite3');seen=[]
    def handle(request):
        assert b.status()['attempts']==1
        data=json.loads(request.content);seen.append(data)
        assert data['max_completion_tokens']==OUTPUT_TOKEN_BOUND
        assert data['service_tier']=='default' and data['store'] is False
        assert len(json.dumps(data,ensure_ascii=False,separators=(',',':')).encode())<=MAX_REQUEST_BYTES
        return httpx.Response(200,json=fake_response())
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            p=BoundedReleaseProvider(settings(),b,client)
            response=await p.generate(GenerationRequest(context=context()))
            assert response.usage.input_tokens==3000
            with pytest.raises(GenerationError):await p.generate(GenerationRequest(context=context()))
    asyncio.run(run());assert len(seen)==1 and not b.status()['halted']


@pytest.mark.parametrize('failure',['missing_usage','partial_usage','timeout','quota','oversize'])
def test_failures_preserve_reservation_halt_paid_calls_and_use_authored_fallback(tmp_path,failure):
    b=ReleaseBudget.initialize(tmp_path/'budget.sqlite3');seen=[]
    def handle(request):
        seen.append(True)
        if failure=='timeout':raise httpx.ReadTimeout('test')
        if failure=='quota':return httpx.Response(429,json={'error':{'code':'insufficient_quota'}})
        data=fake_response(failure!='missing_usage')
        if failure=='partial_usage':data['usage']={'prompt_tokens':3000}
        if failure=='oversize':data['usage']={'prompt_tokens':INPUT_TOKEN_BOUND+1,'completion_tokens':2}
        return httpx.Response(200,json=data)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            p=BoundedReleaseProvider(settings(),b,client)
            from app.campaign import load_campaign_catalog
            fallback=lambda:load_campaign_catalog()[0].crisis
            outcome=await GenerationService(settings(),p,fallback).generate(GenerationRequest(context=context()))
            assert outcome.source=='authored' and outcome.snapshot
            outcome=await GenerationService(settings(),p,fallback).generate(GenerationRequest(context=context()))
            assert outcome.source=='authored'
    asyncio.run(run())
    assert len(seen)==1 and b.status()['attempts']==1 and b.status()['halted']


def test_large_input_rejected_without_reservation_or_dispatch(tmp_path):
    b=ReleaseBudget.initialize(tmp_path/'budget.sqlite3');p=BoundedReleaseProvider(settings(),b)
    with pytest.raises(GenerationError):p.prepare_payload({'oversize':'x'*MAX_REQUEST_BYTES},GenerationRequest(context=context()))
    assert b.status()['attempts']==0


def test_no_public_promotion_after_failed_acceptance(tmp_path):
    b=ReleaseBudget.initialize(tmp_path/'budget.sqlite3');b.reserve('crisis');b.halt()
    with pytest.raises(BudgetUnavailable):b.mark_verified()
    with pytest.raises(BudgetUnavailable):b.open_public()


def test_endpoint_and_model_cannot_drift_into_other_paid_services(tmp_path):
    from dataclasses import replace
    b=ReleaseBudget.initialize(tmp_path/'budget.sqlite3')
    for value in (replace(settings(),model='other'),replace(settings(),endpoint='https://other.example'),
                  replace(settings(),require_api_key=False),replace(settings(),timeout_seconds=61)):
        with pytest.raises(ValueError):BoundedReleaseProvider(value,b)


def test_exact_acceptance_workflow_and_isolated_restore_uses_only_one_request(tmp_path):
    from app.generation.release_acceptance import run
    path=tmp_path/'budget.sqlite3';ReleaseBudget.initialize(path);seen=[]
    def handle(request):
        seen.append(True)
        return httpx.Response(200,json=fake_response())
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            report=await run(path,settings(),client)
            assert report['passed'] and report['integrity']=='ok' and report['live_mission_writes']==0
            with pytest.raises(RuntimeError):await run(path,settings(),client)
    asyncio.run(exercise());assert len(seen)==1
