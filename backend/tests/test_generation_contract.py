"""Untrusted JSON boundaries, shared schema, frozen acceptance and public context."""
from dataclasses import FrozenInstanceError
import json

import pytest
from pydantic import ValidationError

from app.campaign import Campaign, load_campaign_catalog, select_crisis
from app.domain import Crisis, ChatMessage
from app.generation.contract import (AcceptedScenario, ContinuityReference, DecisionContext, FailureCategory,
    FrozenMetrics, GenerationContext, GenerationError, MAX_EFFECT, MIN_EFFECT, accept_proposal, proposal_schema)
from app.generation.context import build_context
from app.generation.service import authored_selector
from test_expansion import team, resolve, balanced


def context(history=()):
    return GenerationContext(current_crisis_number=2, metrics=FrozenMetrics(), history=tuple(history), used_scenario_ids=())


def proposal():
    crisis = load_campaign_catalog()[0].crisis.model_dump(mode='json')
    crisis['id'] = 'untrusted-provider-id'
    return {'schema_version':'1.0','crisis':crisis,'continuity_references':[]}


def accepted(raw=None, ctx=None):
    return accept_proposal(json.dumps(proposal() if raw is None else raw), context() if ctx is None else ctx)


def test_shared_crisis_conversion_normalization_and_stable_server_identity():
    raw=proposal();first=accepted(raw);crisis=first.to_crisis()
    assert type(crisis) is Crisis and crisis.id.startswith('generated-') and len(crisis.id)==74
    assert crisis.id!=raw['crisis']['id']
    raw['crisis']['id']='another-provider-id';raw['crisis']['title']='  '+raw['crisis']['title']+'  '
    raw['crisis']['choices'].reverse()
    for choice in raw['crisis']['choices']:choice['id']=' '+choice['id'].lower()+' '
    raw['crisis']['ai_recommendation_choice_id']=' a '
    assert accepted(raw)==first
    assert [choice.id for choice in crisis.choices]==['A','B','C']
    changed=proposal();changed['crisis']['choices'][0]['metric_deltas']['infrastructure']=9
    assert accepted(changed).to_crisis().id!=crisis.id
    with pytest.raises(GenerationError):
        accepted(ctx=context().model_copy(update={'used_scenario_ids':(crisis.id,)}))


def test_accepted_snapshot_has_no_mutable_consequence_aliases():
    raw=proposal();snapshot=accepted(raw);fingerprint=snapshot.fingerprint
    with pytest.raises(FrozenInstanceError):snapshot.canonical_json='{}'
    exported=snapshot.to_crisis();exported.choices[0].metric_deltas.safety=999
    exported.private_intelligence.clear();exported.choices.clear();raw['crisis']['briefing']='changed'
    assert snapshot.fingerprint==fingerprint and len(snapshot.to_crisis().choices)==3
    assert len(snapshot.to_crisis().private_intelligence)==4
    assert snapshot.to_crisis().choices[0].metric_deltas.safety==-6
    assert 'Grid Under Pressure' not in repr(snapshot)  # No accidental private content repr.


@pytest.mark.parametrize('version',[None,'2.0','1',1,{},True])
def test_contract_version_is_exact(version):
    raw=proposal();raw['schema_version']=version
    with pytest.raises(GenerationError) as failure:accepted(raw)
    assert failure.value.category==FailureCategory.INVALID_SCHEMA


@pytest.mark.parametrize('size',[0,1,2,4])
def test_exactly_three_options_required(size):
    raw=proposal();raw['crisis']['choices']=(raw['crisis']['choices']*2)[:size]
    with pytest.raises(GenerationError):accepted(raw)


@pytest.mark.parametrize('error',['duplicate-id','duplicate-title','duplicate-description','missing-title','short-title',
    'long-title','short-briefing','long-briefing','short-description','long-description','short-consequence',
    'long-consequence','missing-intelligence','extra-role','short-intelligence','long-intelligence','duplicate-intelligence',
    'bad-recommendation','bad-id','missing-version','missing-deltas','missing-metric','extra-metric','high-effect','low-effect',
    'float-effect','bool-effect','string-effect','no-cost','dominant','nested-value'])
def test_invalid_proposals_fail_closed(error):
    raw=proposal();crisis=raw['crisis'];choice=crisis['choices'][0]
    if error=='duplicate-id':crisis['choices'][1]['id']='a'
    elif error=='duplicate-title':crisis['choices'][1]['title']=choice['title']
    elif error=='duplicate-description':crisis['choices'][1]['description']=choice['description']
    elif error=='missing-title':del crisis['title']
    elif error=='short-title':crisis['title']='x'
    elif error=='long-title':crisis['title']='x'*121
    elif error=='short-briefing':crisis['briefing']='Too short.'
    elif error=='long-briefing':crisis['briefing']='x'*2001
    elif error=='short-description':choice['description']='x'
    elif error=='long-description':choice['description']='x'*1001
    elif error=='short-consequence':choice['consequence']='x'
    elif error=='long-consequence':choice['consequence']='x'*1201
    elif error=='missing-intelligence':del crisis['private_intelligence']['safety']
    elif error=='extra-role':crisis['private_intelligence']['mayor']='Unauthorized extra field'
    elif error=='short-intelligence':crisis['private_intelligence']['safety']='x'
    elif error=='long-intelligence':crisis['private_intelligence']['safety']='x'*1201
    elif error=='duplicate-intelligence':crisis['private_intelligence']['safety']=crisis['private_intelligence']['economy']
    elif error=='bad-recommendation':crisis['ai_recommendation_choice_id']='D'
    elif error=='bad-id':choice['id']='first-option'
    elif error=='missing-version':del raw['schema_version']
    elif error=='missing-deltas':del choice['metric_deltas']
    elif error=='missing-metric':del choice['metric_deltas']['safety']
    elif error=='extra-metric':choice['metric_deltas']['unrest']=1
    elif error=='high-effect':choice['metric_deltas']['safety']=19
    elif error=='low-effect':choice['metric_deltas']['safety']=-25
    elif error=='float-effect':choice['metric_deltas']['safety']=3.0
    elif error=='bool-effect':choice['metric_deltas']['safety']=True
    elif error=='string-effect':choice['metric_deltas']['safety']='3'
    elif error=='no-cost':choice['metric_deltas']={key:1 for key in choice['metric_deltas']}
    elif error=='dominant':choice['metric_deltas']={'infrastructure':18,'public_trust':18,'economy':18,'safety':-1}
    else:choice['metric_deltas']['safety']={'current_value':70}
    with pytest.raises(GenerationError) as failure:accepted(raw)
    assert failure.value.category==FailureCategory.INVALID_SCHEMA


@pytest.mark.parametrize('field',['players','votes','voting','deadline','roles','connected','metrics','phase','consensus_score','token','tools'])
@pytest.mark.parametrize('level',['envelope','crisis','choice','effects'])
def test_unexpected_authoritative_fields_are_rejected_at_every_level(field,level):
    raw=proposal();target={'envelope':raw,'crisis':raw['crisis'],'choice':raw['crisis']['choices'][0],
        'effects':raw['crisis']['choices'][0]['metric_deltas']}[level]
    target[field]={'injected':'cannot apply'}
    with pytest.raises(GenerationError):accepted(raw)


@pytest.mark.parametrize('text',['plain prose','```json\n{}\n```','{"schema_version":"1.0",',
    '{"crisis":1,"crisis":2}','{"value":NaN}','{"value":Infinity}','['*1100, 'x'*65537])
def test_invalid_json_is_not_repaired_or_salvaged(text):
    with pytest.raises(GenerationError) as failure:accept_proposal(text,context())
    assert failure.value.category==FailureCategory.INVALID_JSON


def test_valid_reference_requires_exact_visible_historical_choice():
    previous=DecisionContext(crisis_number=1,crisis_id='previous-crisis',title='Earlier public event',choice_id='B',
        choice_title='Shared response',consequence='Recorded public consequence.')
    raw=proposal();raw['continuity_references']=[{'crisis_number':1,'choice_id':'B'}]
    snapshot=accepted(raw,context([previous]));assert snapshot.continuity_references==(ContinuityReference(crisis_number=1,choice_id='B'),)
    for references in [[{'crisis_number':1,'choice_id':'A'}],[{'crisis_number':9,'choice_id':'B'}],raw['continuity_references']*2]:
        raw['continuity_references']=references
        with pytest.raises(GenerationError) as failure:accepted(raw,context([previous]))
        assert failure.value.category==FailureCategory.INVALID_CONTINUITY


def test_effect_limits_match_authored_extrema_and_schema_is_strict():
    values=[v for s in load_campaign_catalog() for c in s.crisis.choices for v in c.metric_deltas.model_dump().values()]
    assert (min(values),max(values))==(MIN_EFFECT,MAX_EFFECT)
    schema=proposal_schema()
    def check(node):
        if isinstance(node,list):
            for child in node:check(child)
        elif isinstance(node,dict):
            if node.get('type')=='object':
                assert node['additionalProperties'] is False
                assert set(node['required'])==set(node['properties'])
            assert 'default' not in node
            for child in node.values():check(child)
    check(schema)
    roles=schema['$defs']['ProposedCrisis']['properties']['private_intelligence']
    assert set(roles['properties'])=={'infrastructure','community','economy','safety'}


def test_context_uses_public_history_only_without_mutating_or_serializing_a_mission():
    store,mission,credentials,clock=team('llm-context')
    for _ in range(4):
        resolve(store,mission,credentials,clock,balanced(mission))
        store.continue_mission(mission.token,credentials[0],mission.results[-1].id)
    canaries=['PRIVATE-CHAT-CANARY','PRIVATE-CALLSIGN-CANARY','PRIVATE-TOKEN-CANARY','PRIVATE-CREDENTIAL-CANARY',
        'PRIVATE-INTELLIGENCE-CANARY','PRIVATE-VOTE-ID-CANARY']
    mission.chat.append(ChatMessage(id='private-message-id',sender_id='private-sender',callsign=canaries[1],text=canaries[0],timestamp=clock.now))
    mission.players[0].callsign=canaries[1];mission.token=canaries[2];mission.players[0].credential=canaries[3]
    mission.crisis.private_intelligence['safety']=canaries[4]
    mission.results[0]=mission.results[0].model_copy(update={'id':canaries[5]})
    before=mission.model_dump_json();result=build_context(mission);text=result.model_dump_json()
    assert not any(value in text for value in canaries)
    assert not any(player.id in text for player in mission.players)
    assert not any(secret in text for entry in mission.campaign.scenarios for secret in entry.crisis.private_intelligence.values())
    assert result.metrics.model_dump()==mission.metrics.model_dump() and result.current_crisis_number==5
    assert [r.crisis_number for r in result.history]==[2,3,4]
    assert len(result.used_scenario_ids)==5 and mission.model_dump_json()==before
    assert set(json.loads(text))=={'current_crisis_number','metrics','history','used_scenario_ids','narrative_memory'}
    with pytest.raises(ValidationError):result.metrics.safety=0
    assert mission.metrics.safety!=0


def test_authored_selector_exactly_reuses_seeded_selection_and_captures_state():
    pool=load_campaign_catalog();campaign=Campaign(seed='fallback',scenarios=pool)
    select=authored_selector(campaign,0,[]);expected=select_crisis(campaign,0,[])
    campaign.scenarios.clear()
    assert select()==expected
    assert AcceptedScenario.from_crisis(select()).to_crisis()==expected
