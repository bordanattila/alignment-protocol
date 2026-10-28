"""Context-specific prompt/schema guidance plus unchanged independent validation."""
import asyncio
import json

import httpx
import pytest

from app.generation.contract import (DecisionContext, GenerationContext, GenerationRequest, FrozenMetrics,
                                     GenerationError, accept_proposal, proposal_schema)
from app.generation.provider import ChatCompletionsProvider, continuity_instructions
from app.generation.service import GenerationService
from test_generation_contract import proposal
from test_generation_provider import settings, fallback, wire


def history():
    return (
        DecisionContext(crisis_number=1,crisis_id='first-crisis',title='First crisis',choice_id='B',
                        choice_title='Executed response',consequence='The city restored access with a public trust cost.'),
        DecisionContext(crisis_number=2,crisis_id='second-crisis',title='Second crisis',choice_id='C',
                        choice_title='Another response',consequence='Resources shifted toward emergency preparedness.'),
    )


def context(records=()):
    return GenerationContext(current_crisis_number=3 if records else 1, metrics=FrozenMetrics(),
                             history=records, used_scenario_ids=tuple(r.crisis_id for r in records))


@pytest.mark.parametrize('format',['json_schema','json_object'])
@pytest.mark.parametrize('records',[(),history()])
def test_actual_adapter_request_aligns_prompt_serialized_context_and_schema(format,records):
    ctx=context(records);calls=[]
    def handler(request):
        calls.append(request);payload=json.loads(request.content)
        prompt=payload['messages'][0]['content']
        assert 'Narrative continuity is optional' in prompt
        assert 'used_scenario_ids is an exclusion list' in prompt
        assert json.loads(payload['messages'][1]['content'])==json.loads(GenerationRequest(context=ctx).model_dump_json())
        embedded=json.loads(prompt.split('\nJSON contract: ',1)[1])
        assert embedded==proposal_schema(ctx)
        refs=embedded['properties']['continuity_references']
        assert refs['maxItems']==len(records)
        if records:
            assert 'Do not invent missing/older history' in prompt
            assert json.dumps({'crisis_number':1,'choice_id':'B'}) in prompt
        else:
            assert 'This is Crisis 1, the opening crisis.' in prompt
            assert 'NO previous player decisions exist' in prompt
            assert 'continuity_references: [] exactly' in prompt
        if format=='json_schema': assert payload['response_format']['json_schema']['schema']==embedded
        else: assert payload['response_format']=={'type':'json_object'}
        return httpx.Response(200,json=wire())
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result=await ChatCompletionsProvider(settings(response_format=format),client).generate(GenerationRequest(context=ctx))
            assert result.http_status==200
    asyncio.run(run());assert len(calls)==1


def test_schema_binds_exact_historical_pairs_and_remains_optional_without_cross_product():
    schema=proposal_schema(context(history()))
    refs=schema['properties']['continuity_references']
    assert refs.get('minItems',0)==0 and refs['maxItems']==2
    variants=refs['items']['anyOf']
    pairs={(v['properties']['crisis_number']['enum'][0],v['properties']['choice_id']['enum'][0]) for v in variants}
    assert pairs=={(1,'B'),(2,'C')}
    assert (1,'C') not in pairs and (2,'B') not in pairs
    assert all(v['additionalProperties'] is False and set(v['required'])=={'crisis_number','choice_id'} for v in variants)
    assert 'continuity_references' in schema['required']  # wire presence, not a required narrative dependency
    assert proposal_schema()['properties']['continuity_references']['maxItems']==3
    assert proposal_schema(context())['properties']['continuity_references']['maxItems']==0


@pytest.mark.parametrize('omit',[False,True])
@pytest.mark.parametrize('records',[(),history()])
def test_standalone_crisis_with_empty_or_omitted_references_is_accepted(omit,records):
    raw=proposal()
    if omit:raw.pop('continuity_references')
    result=accept_proposal(json.dumps(raw),context(records))
    assert result.continuity_references==()


def test_valid_supplied_reference_pair_is_still_accepted():
    raw=proposal();raw['continuity_references']=[{'crisis_number':2,'choice_id':'C'}]
    result=accept_proposal(json.dumps(raw),context(history()))
    assert [(r.crisis_number,r.choice_id) for r in result.continuity_references]==[(2,'C')]


@pytest.mark.parametrize('records,refs',[
    ((),[{'crisis_number':1,'choice_id':'A'}]),
    (history(),[{'crisis_number':9,'choice_id':'B'}]),
    (history(),[{'crisis_number':1,'choice_id':'C'}]),
    (history(),[{'crisis_number':2,'choice_id':'B'}]),
    (history(),[{'crisis_number':1,'choice_id':'B'}]*2),
])
def test_fabricated_wrong_choice_and_duplicate_references_still_fail_closed(records,refs):
    raw=proposal();raw['continuity_references']=refs
    with pytest.raises(GenerationError) as failure:accept_proposal(json.dumps(raw),context(records))
    assert failure.value.category=='invalid_continuity'


def test_misbehaving_provider_ignoring_empty_history_schema_still_triggers_authored_fallback():
    raw=proposal();raw['continuity_references']=[{'crisis_number':1,'choice_id':'A'}]
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=wire(json.dumps(raw))))) as client:
            config=settings()
            result=await GenerationService(config,ChatCompletionsProvider(config,client),fallback()).generate(GenerationRequest(context=context()))
            assert result.failure=='invalid_continuity' and result.source=='authored'
    asyncio.run(run())


def test_unused_scenario_ids_do_not_create_a_continuity_dependency():
    ctx=context().model_copy(update={'used_scenario_ids':('selected-but-not-executed',)})
    assert proposal_schema(ctx)['properties']['continuity_references']['maxItems']==0
    assert 'NO previous player decisions exist' in continuity_instructions(ctx)
