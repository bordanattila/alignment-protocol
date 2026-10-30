"""Concurrency, honest process-local timing, and review-period responsiveness."""
import asyncio
import json

import pytest
from app.domain import Phase
from app.missions import MissionError
from app.persistence import PersistenceError
from app.generation.context import build_memory
from app.generation.contract import FailureCategory
from test_live_generation import setup, launch, settle, ProgressiveProvider
from test_persistence import voting, votes
from measure_responsiveness import MonotonicClock, measure


@pytest.mark.parametrize('delay',[0,5,15,30])
def test_review_is_preserved_during_measured_preparation_without_speculative_overlap(delay):
    result = asyncio.run(measure(str(delay),delay))
    assert result['simulated_server_ready_to_admission_seconds'] == delay
    assert result['lifecycle']['generation_seconds'] == delay
    assert result['lifecycle']['server_preparation_seconds'] == delay
    assert result['review_inference_overlap_seconds'] == 0
    assert result['after_admission_progression_wait_seconds'] == 0
    assert result['source'] == 'generated'
    assert result['lifecycle']['player_visible_wait_seconds'] is None
    assert result['browser_render_seconds'] is None


@pytest.mark.parametrize('failure',[FailureCategory.TIMEOUT,FailureCategory.UNAVAILABLE])
def test_simulated_failure_preserves_deterministic_fallback(failure):
    result=asyncio.run(measure('failure',60,failure))
    assert result['source']=='authored_fallback' and result['category']==failure.value
    assert result['new_provider_attempts']==1
    assert result['simulated_server_ready_to_admission_seconds']==60


@pytest.mark.parametrize('all_players',[False,True])
@pytest.mark.parametrize('reconnect_before_completion',[False,True])
def test_disconnects_and_reconnects_cannot_repeat_or_prematurely_present_generation(all_players,reconnect_before_completion):
    async def run():
        provider = ProgressiveProvider(held=True)
        store, mission, credentials, clock, live = setup(provider=provider)
        try:
            await launch(live); await asyncio.wait_for(provider.entered.wait(),1)
            players = mission.players if all_players else mission.players[-1:]
            original_roles = [list(p.roles) for p in mission.players]
            for p in players: store.set_connected(mission.token,p.id,False)
            if reconnect_before_completion:
                for p in players: store.set_connected(mission.token,p.id,True)
                await launch(live)
                assert mission.phase == Phase.PREPARING
                assert store.project(mission.token,mission.host_id)['crisis'] is None
            provider.release.set(); await settle(live)
            if not reconnect_before_completion:
                assert mission.phase == Phase.BRIEFING
                with pytest.raises(MissionError): store.begin_discussion(mission.token,credentials[0])
                for p in players: store.set_connected(mission.token,p.id,True)
            await launch(live)
            assert len(provider.requests) == 1 and len(mission.admissions) == 1
            assert original_roles == [list(p.roles) for p in mission.players]
            for p in mission.players:
                frame = store.project(mission.token,p.id)
                assert set(frame['private_intelligence']) == set(p.roles)
                assert all(text not in json.dumps(frame) for role,text in mission.crisis.private_intelligence.items() if role not in p.roles)
                assert 'lifecycle' not in frame and 'measurement' not in frame
            store.begin_discussion(mission.token,credentials[0])
        finally: await live.close(); store.close()
    asyncio.run(run())


def test_next_request_uses_final_consequences_memory_and_host_gate_once():
    async def run():
        provider = ProgressiveProvider()
        store, mission, credentials, clock, live = setup(provider=provider)
        try:
            await launch(live); await settle(live)
            voting(store,mission,credentials,clock); votes(store,mission,credentials,['B']*3)
            result = mission.results[-1]
            await launch(live)
            assert len(provider.requests)==1
            with pytest.raises(MissionError): store.continue_mission(mission.token,credentials[1],result.id)
            memory, metrics = build_memory(mission), mission.metrics.model_dump()
            store.continue_mission(mission.token,credentials[0],result.id)
            for _ in range(5): assert not store.continue_mission(mission.token,credentials[0],result.id)
            await asyncio.gather(*(launch(live) for _ in range(5))); await settle(live)
            request = provider.requests[-1].context
            assert request.current_crisis_number == 2 and request.metrics.model_dump()==metrics
            assert request.history[-1].choice_id=='B' and request.history[-1].consequence==result.outcome
            assert request.narrative_memory == memory and len(provider.requests)==2
        finally: await live.close(); store.close()
    asyncio.run(run())


def test_admission_lock_and_publication_intervals_are_separate_from_inference(caplog):
    async def run():
        class Provider(ProgressiveProvider):
            def __init__(self): super().__init__(held=True); self.generated=asyncio.Event()
            async def generate(self,request):
                response=await super().generate(request)
                self.generated.set()
                return response
        provider=Provider(); store,mission,credentials,game_clock,live=setup(provider=provider)
        clock=MonotonicClock(); live.clock=clock
        original=live.connections.broadcast
        async def publish(token):
            clock.advance(.25)
            await original(token)
        live.connections.broadcast=publish
        try:
            await launch(live); await asyncio.wait_for(provider.entered.wait(),1)
            async with live.lock:
                provider.release.set(); await asyncio.wait_for(provider.generated.wait(),1)
                assert live.completed and mission.phase==Phase.PREPARING
                clock.advance(2.5)
            await settle(live)
            row=live.lifecycle[-1]
            assert row['admission_seconds']==2.5 and row['publication_seconds']==.25
            assert row['generation_seconds']==0 and row['server_preparation_seconds']==2.5
            assert row['browser_render_seconds'] is None and row['player_visible_wait_seconds'] is None
            assert set(row)=={'crisis_number','status','source','queue_seconds','generation_seconds','admission_seconds',
                              'server_preparation_seconds','publication_seconds','player_visible_wait_seconds','browser_render_seconds'}
            assert all(secret not in json.dumps(row) for secret in [mission.token,*credentials,*[p.id for p in mission.players]])
        finally: await live.close(); store.close()
    asyncio.run(run())


def test_other_mission_voting_deadline_advances_during_held_inference():
    async def run():
        provider=ProgressiveProvider(held=True)
        store,mission,credentials,clock,live=setup(provider=provider)
        try:
            await launch(live); await asyncio.wait_for(provider.entered.wait(),1)
            async with live.lock:
                other,host=store.create('Other')
                store.join(other.token,'Guest')
                for p in other.players: store.set_connected(other.token,p.id,True)
                store.start(other.token,host.credential)
                store.begin_discussion(other.token,host.credential)
                clock.now=other.deadline
                assert store.advance_due(other.token) and other.phase==Phase.VOTING
                clock.now=other.deadline
                assert store.advance_due(other.token) and other.phase==Phase.DECISION_LOCKED
                assert other.decision.reason=='no_vote_ai_fallback'
            assert mission.phase==Phase.PREPARING and len(provider.requests)==1
            provider.release.set(); await settle(live)
        finally: await live.close(); store.close()
    asyncio.run(run())


def test_admission_retry_retains_ready_time_without_repeating_inference(tmp_path,monkeypatch):
    async def run():
        provider=ProgressiveProvider()
        store,mission,credentials,game_clock,live=setup(tmp_path/'retry.sqlite3',provider)
        clock=MonotonicClock(); live.clock=clock
        save=store.persistence.save
        def unavailable(mission): raise PersistenceError('test storage outage')
        try:
            monkeypatch.setattr(store.persistence,'save',unavailable)
            await launch(live); await settle(live)
            assert live.completed and not live.lifecycle and mission.phase==Phase.PREPARING
            clock.advance(10)
            monkeypatch.setattr(store.persistence,'save',save)
            await launch(live); await settle(live)
            assert len(provider.requests)==1 and len(live.lifecycle)==1
            assert live.lifecycle[-1]['admission_seconds']==10
            assert live.lifecycle[-1]['queue_seconds']==0
            assert not live.ready and not live.executing and not live.scheduled
        finally: await live.close(); store.close()
    asyncio.run(run())
