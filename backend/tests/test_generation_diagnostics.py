"""Sanitized provider classifications and correlation-free generation diagnostics."""
import asyncio
import json
import logging

import httpx
import pytest

from app.generation.contract import GenerationError, FailureCategory, GenerationRequest
from app.generation.provider import classify_http_error, ProviderResponse, MAX_ERROR_BYTES
from app.generation.service import GenerationService
from test_generation_contract import context, proposal
from test_generation_provider import exercise, fallback, settings, wire, SECRET
from test_live_generation import setup, launch, settle, ProgressiveProvider


@pytest.mark.parametrize('status,error,category',[
    (404,{'code':'model_not_found','message':SECRET},'model_unavailable'),
    (400,{'code':'unsupported_model','message':SECRET},'model_unavailable'),
    (429,{'code':'insufficient_quota','message':SECRET},'quota_exceeded'),
    (429,{'type':'insufficient_quota','code':'provider-specific','message':SECRET},'quota_exceeded'),
    (402,{'code':'billing_not_active','message':SECRET},'quota_exceeded'),
    (429,{'code':'credit_balance_exhausted','message':SECRET},'quota_exceeded'),
    (429,{'code':'project_spend_limit_exceeded','message':SECRET},'quota_exceeded'),
    (429,{'code':'organization_spend_limit_exceeded','message':SECRET},'quota_exceeded'),
    (429,{'code':'organization_usage_limit_exceeded','message':SECRET},'quota_exceeded'),
    (429,{'code':'rate_limit_exceeded','message':SECRET},'rate_limited'),
    (400,{'code':'unsupported_value','param':'response_format','message':'json_schema is not supported '+SECRET},'unsupported_format'),
    (400,{'param':'response_format.type','message':'Unsupported format '+SECRET},'unsupported_format'),
    (400,{'code':'invalid_json_schema','message':SECRET},'invalid_provider_schema'),
    (400,{'message':'schema validation failed '+SECRET},'unsupported_response'),
    (401,{'code':'invalid_api_key','message':SECRET},'authentication'),
    (403,{'message':SECRET},'authentication'),
])
def test_error_body_is_classified_without_logging_or_retaining_untrusted_fields(status,error,category,caplog):
    result=exercise(lambda request:httpx.Response(status,json={'error':error}))
    assert result.failure==category and result.http_status==status and result.source=='authored'
    assert f'failure={category}' in caplog.text and f'http_status={status}' in caplog.text
    assert 'mode=generated crisis=2 source=authored_fallback success=False' in caplog.text
    assert 'duration_seconds=' in caplog.text and result.duration_seconds>=0
    assert SECRET not in caplog.text and SECRET not in repr(result)


@pytest.mark.parametrize('body',[b'not json',b'[]',b'null',b'{"error":[]}',b'{"error":{"code":[],"type":{},"param":{},"message":[]}}',b'x'*(MAX_ERROR_BYTES+1)])
def test_malformed_and_oversized_errors_fail_safely(body):
    assert classify_http_error(400,body)==FailureCategory.UNSUPPORTED_RESPONSE
    assert classify_http_error(429,body)==FailureCategory.RATE_LIMITED


def test_http_200_validation_failure_retains_status_and_never_logs_generated_private_text(caplog):
    bad=proposal();bad['crisis']['choices'][0]['metric_deltas']['safety']=999
    bad['crisis']['private_intelligence']['safety']=SECRET*3
    result=exercise(lambda request:httpx.Response(200,json=wire(json.dumps(bad))))
    assert result.failure=='invalid_schema' and result.http_status==200
    assert SECRET not in caplog.text and 'failure=invalid_schema http_status=200' in caplog.text


def test_success_diagnostics_are_visible_and_contain_only_safe_scalar_metadata(caplog):
    caplog.set_level(logging.INFO)
    result=exercise(lambda request:httpx.Response(200,json=wire()))
    assert result.source=='generated' and result.http_status==200
    assert 'mode=generated crisis=2 source=generated success=True failure=none http_status=200 duration_seconds=' in caplog.text
    assert result.snapshot.to_crisis().briefing not in caplog.text
    assert all(text not in caplog.text for text in result.snapshot.to_crisis().private_intelligence.values())


def test_untrusted_http_status_cannot_inject_a_secret_into_diagnostics(caplog):
    class Provider:
        async def generate(self,request):return ProviderResponse(json.dumps(proposal()),http_status=SECRET)
    caplog.set_level(logging.INFO)
    result=asyncio.run(GenerationService(settings(),Provider(),fallback()).generate(GenerationRequest(context=context())))
    assert result.http_status is None and SECRET not in caplog.text
    assert GenerationError(FailureCategory.INVALID_SCHEMA,SECRET).http_status is None


def test_admission_diagnostics_follow_commit_and_do_not_duplicate_on_storage_retry(tmp_path,monkeypatch,caplog):
    caplog.set_level(logging.INFO)
    from app.persistence import PersistenceError
    async def run():
        store,mission,credentials,clock,live=setup(tmp_path/'logging.sqlite3')
        save=store.persistence.save
        def broken(mission, **_metadata):raise PersistenceError('safe temporary failure')
        monkeypatch.setattr(store.persistence,'save',broken)
        await launch(live);await settle(live)
        assert 'crisis_admitted' not in caplog.text
        monkeypatch.setattr(store.persistence,'save',save)
        await launch(live);await settle(live)
        assert caplog.text.count('crisis_admitted mode=generated crisis=1 source=generated')==1
        assert caplog.text.count('generation_result mode=generated crisis=1')==1
        assert mission.token not in caplog.text and all(value not in caplog.text for value in credentials)
        await live.close();store.close()
    asyncio.run(run())


def test_real_smoke_fixture_harness_can_prove_two_crises_without_api_calls(monkeypatch):
    # Exercise the exact controlled harness with a deterministic fake; the real
    # invocation is optional and never part of the normal suite.
    import smoke_provider_progression as smoke
    monkeypatch.setattr(smoke,'ChatCompletionsProvider',lambda settings:ProgressiveProvider())
    assert asyncio.run(smoke.exercise(settings()))
