"""Mocked provider/HTTP failure paths and one local fixture HTTP round-trip."""
import asyncio
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

import httpx
import pytest
from pydantic import SecretStr

from app.campaign import Campaign, load_campaign_catalog
from app.generation.config import ConfigurationError, GenerationSettings
from app.generation.contract import FailureCategory, GenerationError, GenerationRequest
from app.generation.provider import ChatCompletionsProvider, ProviderResponse
from app.generation.service import GenerationService, authored_selector
from test_generation_contract import context, proposal

SECRET='API-KEY-DO-NOT-LOG-OR-RETURN-9-1'
ENDPOINT='http://127.0.0.1:1234/v1/chat/completions'


def settings(**values):
    return GenerationSettings(enabled=True,endpoint=ENDPOINT,model='fixture-model',require_api_key=False,**values)


def fallback(index=0):
    return authored_selector(Campaign(seed='generation-test',scenarios=load_campaign_catalog()),index,[])


def wire(content=None):
    return {'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(proposal()) if content is None else content}}]}


def exercise(handler,configuration=None):
    async def run():
        config=configuration or settings()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider=ChatCompletionsProvider(config,client)
            result=await GenerationService(config,provider,fallback()).generate(GenerationRequest(context=context()))
            assert not client.is_closed  # Injected client ownership stays with caller.
            return result
    return asyncio.run(run())


def test_configuration_is_disabled_by_default_and_redacts_secrets():
    assert GenerationSettings.from_env({})==GenerationSettings()
    configured=GenerationSettings.from_env({'CONSENSUS_LLM_ENABLED':'true','CONSENSUS_LLM_ENDPOINT':ENDPOINT,
        'CONSENSUS_LLM_MODEL':'local-fixture','CONSENSUS_LLM_REQUIRE_API_KEY':'false','CONSENSUS_LLM_TIMEOUT_SECONDS':'3.5',
        'CONSENSUS_LLM_API_KEY':SECRET,'CONSENSUS_LLM_RESPONSE_FORMAT':'json_object'})
    assert configured.enabled and configured.timeout_seconds==3.5 and not configured.require_api_key
    assert configured.api_key.get_secret_value()==SECRET
    assert SECRET not in repr(configured) and ENDPOINT not in repr(configured)


@pytest.mark.parametrize('env',[
    {'CONSENSUS_LLM_ENABLED':'yes'}, {'CONSENSUS_LLM_TIMEOUT_SECONDS':'not-number'},
    {'CONSENSUS_LLM_TIMEOUT_SECONDS':'nan'}, {'CONSENSUS_LLM_TIMEOUT_SECONDS':'inf'},
    {'CONSENSUS_LLM_TIMEOUT_SECONDS':'0'}, {'CONSENSUS_LLM_TIMEOUT_SECONDS':'121'},
    {'CONSENSUS_LLM_REQUIRE_API_KEY':'maybe'}, {'CONSENSUS_LLM_RESPONSE_FORMAT':'text'},
    {'CONSENSUS_LLM_ENDPOINT':'ftp://localhost/model'}, {'CONSENSUS_LLM_ENDPOINT':'http://public.invalid/model'},
    {'CONSENSUS_LLM_ENDPOINT':'https://user:'+SECRET+'@fixture.invalid/model'},
    {'CONSENSUS_LLM_ENDPOINT':'https://fixture.invalid/path?api_key='+SECRET},
    {'CONSENSUS_LLM_ENDPOINT':'https://fixture.invalid/#'+SECRET},
    {'CONSENSUS_LLM_ENDPOINT':'http://[::1]:bad/endpoint'}, {'CONSENSUS_LLM_API_KEY':'bad\n'+SECRET},
])
def test_invalid_configuration_is_safe(env):
    with pytest.raises(ConfigurationError) as failure:GenerationSettings.from_env(env)
    assert SECRET not in str(failure.value) and list(env.values())[0] not in str(failure.value)


@pytest.mark.parametrize('endpoint',['http://localhost:1234/chat','http://127.0.0.1/chat','http://[::1]:1234/chat','https://fixture.invalid/custom/path'])
def test_local_and_configured_secure_endpoints_are_supported(endpoint):
    assert GenerationSettings(endpoint=endpoint).endpoint==endpoint


@pytest.mark.parametrize('error',['endpoint','model','key'])
def test_required_configuration_missing_returns_authored_fallback_without_network(error):
    config=settings();changes={'endpoint':None} if error=='endpoint' else {'model':None} if error=='model' else {'require_api_key':True}
    calls=[]
    def handler(request):calls.append(request);raise AssertionError('Must not call provider')
    result=exercise(handler,replace(config,**changes))
    assert result.source=='authored' and result.failure==FailureCategory.CONFIGURATION and calls==[]


@pytest.mark.parametrize('format',['json_schema','json_object'])
@pytest.mark.parametrize('authenticate',[True,False])
def test_adapter_posts_structured_request_without_private_context_or_key_in_prompt(format,authenticate):
    calls=[]
    def handler(request):
        calls.append(request);payload=json.loads(request.content)
        assert str(request.url)==ENDPOINT and payload['model']=='fixture-model'
        assert payload['response_format']['type']==format and payload['stream'] is False
        assert 'tools' not in payload and 'user' not in payload
        if format=='json_schema':assert payload['response_format']['json_schema']['strict'] is True
        assert SECRET not in request.content.decode()
        if authenticate:assert request.headers['Authorization']=='Bearer '+SECRET
        else:assert 'Authorization' not in request.headers
        ctx=json.loads(payload['messages'][1]['content'])['context']
        assert set(ctx)=={'current_crisis_number','metrics','history','used_scenario_ids','narrative_memory'}
        return httpx.Response(200,json=wire())
    config=settings(response_format=format,api_key=SecretStr(SECRET) if authenticate else None)
    outcome=exercise(handler,config)
    assert outcome.source=='generated' and outcome.failure is None and len(calls)==1
    assert outcome.snapshot.to_crisis().id.startswith('generated-')


@pytest.mark.parametrize('status,category',[(400,'unsupported_response'),(401,'authentication'),(403,'authentication'),
    (408,'timeout'),(429,'rate_limited'),(500,'unavailable'),(502,'unavailable'),(504,'timeout'),(302,'unsupported_response')])
def test_http_errors_are_sanitized_and_not_retried_or_redirected(status,category,caplog):
    requests=[]
    def handler(request):
        requests.append(request)
        return httpx.Response(status,text='private server error '+SECRET,headers={'Location':'https://never-follow.invalid/'+SECRET})
    result=exercise(handler)
    assert result.failure==category and result.source=='authored' and len(requests)==1
    assert SECRET not in caplog.text and SECRET not in repr(result)


@pytest.mark.parametrize('exception,category',[(httpx.ReadTimeout,'timeout'),(httpx.ConnectTimeout,'timeout'),
    (httpx.ConnectError,'unavailable'),(httpx.RemoteProtocolError,'unavailable')])
def test_timeout_and_network_errors_fall_back(exception,category,caplog):
    def handler(request):raise exception('DO NOT LOG '+SECRET,request=request)
    result=exercise(handler)
    assert result.failure==category and result.source=='authored' and SECRET not in caplog.text


@pytest.mark.parametrize('error',['no-choices','multiple','wrong-role','content-list','content-null','content-number',
    'length','tool-calls','function-call','refusal','bad-envelope','oversized-envelope','invalid-json-content'])
def test_unsupported_or_invalid_provider_responses(error,caplog):
    body=wire();message=body['choices'][0]['message'];category='unsupported_response'
    if error=='no-choices':body['choices']=[]
    elif error=='multiple':body['choices']*=2
    elif error=='wrong-role':message['role']='tool'
    elif error=='content-list':message['content']=[]
    elif error=='content-null':message['content']=None
    elif error=='content-number':message['content']=3
    elif error=='length':body['choices'][0]['finish_reason']='length'
    elif error=='tool-calls':message['tool_calls']=[{'name':'never_execute'}]
    elif error=='function-call':message['function_call']={'name':'never_execute'}
    elif error=='refusal':message['refusal']=SECRET;category='refusal'
    elif error=='invalid-json-content':message['content']='not JSON '+SECRET;category='invalid_json'
    def handler(request):
        if error=='bad-envelope':return httpx.Response(200,text='invalid '+SECRET)
        if error=='oversized-envelope':return httpx.Response(200,content=b'x'*131073)
        return httpx.Response(200,json=body)
    result=exercise(handler)
    assert result.source=='authored' and result.failure==category and SECRET not in caplog.text


@pytest.mark.parametrize('escape',[False,True])
def test_provider_cannot_echo_its_authentication_secret_into_accepted_content(escape):
    raw=proposal();raw['crisis']['briefing']+=' '+SECRET
    content=json.dumps(raw)
    if escape:content=content.replace(SECRET,''.join(f'\\u{ord(c):04x}' for c in SECRET))
    outcome=exercise(lambda request:httpx.Response(200,json=wire(content)),settings(api_key=SecretStr(SECRET)))
    assert outcome.source=='authored' and outcome.failure=='invalid_schema'
    assert SECRET not in outcome.snapshot.canonical_json


def test_total_timeout_cancels_inference_and_does_not_block_the_event_loop():
    async def run():
        entered=asyncio.Event();cancelled=asyncio.Event()
        class StalledProvider:
            async def generate(self,request):
                entered.set()
                try:await asyncio.Event().wait()
                finally:cancelled.set()
        service=GenerationService(settings(timeout_seconds=.02),StalledProvider(),fallback())
        pending=asyncio.create_task(service.generate(GenerationRequest(context=context())))
        await entered.wait()
        # Another coroutine can run while inference is pending; no synchronous IO.
        assert not pending.done()
        result=await pending
        assert result.failure=='timeout' and result.source=='authored' and cancelled.is_set()
    asyncio.run(run())


def test_parent_cancellation_does_not_publish_or_run_fallback():
    async def run():
        entered=asyncio.Event();calls=[]
        class Provider:
            async def generate(self,request):entered.set();await asyncio.Event().wait()
        pending=asyncio.create_task(GenerationService(settings(),Provider(),lambda:calls.append('fallback')).generate(GenerationRequest(context=context())))
        await entered.wait();pending.cancel()
        with pytest.raises(asyncio.CancelledError):await pending
        assert calls==[]
    asyncio.run(run())


@pytest.mark.parametrize('category',['unavailable','authentication','invalid_schema','invalid_continuity','unexpected'])
def test_explicit_and_unexpected_provider_failures_log_only_category(category,caplog):
    class Provider:
        async def generate(self,request):
            if category=='unexpected':raise RuntimeError('PRIVATE-PLAYER-NAME '+SECRET)
            raise GenerationError(FailureCategory(category))
    result=asyncio.run(GenerationService(settings(),Provider(),fallback()).generate(GenerationRequest(context=context())))
    assert result.failure==category and result.source=='authored'
    assert SECRET not in caplog.text and 'PRIVATE-PLAYER-NAME' not in caplog.text
    assert category in caplog.text


def test_disabled_service_never_calls_provider_and_missing_state_is_typed():
    class Provider:
        async def generate(self,request):raise AssertionError('disabled')
    request=GenerationRequest(context=context())
    disabled=asyncio.run(GenerationService(GenerationSettings(),Provider(),fallback()).generate(request))
    assert disabled.failure=='disabled' and disabled.source=='authored'
    missing=asyncio.run(GenerationService(GenerationSettings()).generate(request))
    assert missing.snapshot is None and missing.fallback_failure=='missing_selector'
    invalid=asyncio.run(GenerationService(GenerationSettings(),fallback=fallback(10)).generate(request))
    assert invalid.snapshot is None and invalid.fallback_failure=='invalid_state'


def test_real_http_roundtrip_against_a_scripted_local_fixture_not_a_model():
    received=[]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append((self.path,self.headers.get('Authorization'),json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            body=json.dumps(wire()).encode();self.send_response(200);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        config=settings();config=replace(config,endpoint=f'http://127.0.0.1:{server.server_port}/compatible/chat')
        outcome=asyncio.run(GenerationService(config,fallback=fallback()).generate(GenerationRequest(context=context())))
        assert outcome.source=='generated' and len(received)==1
        assert received[0][0]=='/compatible/chat' and received[0][1] is None
    finally:server.shutdown();server.server_close();thread.join(timeout=2)
