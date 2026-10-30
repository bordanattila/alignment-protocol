"""Offline readiness checks. No test may dispatch a real provider request."""
import asyncio
from decimal import Decimal
import json

import pytest
from app.generation.config import GenerationSettings
from app.generation.evaluation_fixtures import fixture
from app.generation.evaluation_report import EvaluationRecord
from app.generation.provider import ProviderResponse
import revalidate_stage_b as protocol


def config():return GenerationSettings(enabled=True,model='gpt-6-luna',timeout_seconds=60)


def test_four_original_cases_and_exact_planned_cost():
    assert protocol.CASES==[('crisis-fresh','fresh'),('crisis-infrastructure','infrastructure-damage'),
        ('crisis-trust','declining-trust'),('crisis-interconnected','interconnected')]
    assert (5000*protocol.PRICE.input_per_million+2000*protocol.PRICE.output_per_million)/1_000_000*4==Decimal('.0060')


def test_fifth_call_is_blocked_and_attempt_is_journaled_before_dispatch(tmp_path,monkeypatch):
    provider=protocol.BudgetProvider(config(),tmp_path,False)
    async def fake(self,request):
        stored=json.loads((tmp_path/'attempt-journal.json').read_text())
        assert len(stored)==len(provider.attempts) and stored[-1]['status']=='attempted'
        return ProviderResponse('{}',200)
    monkeypatch.setattr(protocol.fixtures.FixtureProvider,'generate',fake)
    async def run():
        for case,name in protocol.CASES:
            provider.case=case;await provider.generate(fixture(name))
        with pytest.raises(protocol.BatchStop,match='request_budget_exhausted'):
            await provider.generate(fixture('fresh'))
    asyncio.run(run());assert len(provider.attempts)==4


def test_spend_guard_blocks_before_count_or_provider_call(tmp_path):
    provider=protocol.BudgetProvider(config(),tmp_path,False);provider.spent=Decimal('.999')
    with pytest.raises(protocol.BatchStop,match='projected_spending_limit'):
        asyncio.run(provider.generate(fixture('fresh')))
    assert not provider.attempts and not (tmp_path/'attempt-journal.json').exists()


def test_endgame_and_changed_configuration_are_refused(tmp_path):
    provider=protocol.BudgetProvider(config(),tmp_path,False)
    with pytest.raises(protocol.BatchStop,match='endgame_not_authorized'):
        asyncio.run(provider.generate(fixture('victory')))
    wrong=protocol.BudgetProvider(GenerationSettings(enabled=True,model='fixture',timeout_seconds=60),tmp_path,False)
    with pytest.raises(protocol.BatchStop,match='configuration_mismatch'):
        asyncio.run(wrong.generate(fixture('fresh')))
    assert not provider.attempts and not wrong.attempts


def test_timeout_still_consumes_one_attempt_without_retry(tmp_path,monkeypatch):
    provider=protocol.BudgetProvider(config(),tmp_path,False)
    async def timeout(*args):raise TimeoutError()
    monkeypatch.setattr(protocol.fixtures.FixtureProvider,'generate',timeout)
    with pytest.raises(TimeoutError):asyncio.run(provider.generate(fixture('fresh')))
    assert len(provider.attempts)==1
    assert len(json.loads((tmp_path/'attempt-journal.json').read_text()))==1


def test_unknown_usage_stops_without_calling_it_free(tmp_path):
    from app.domain import GenerationDiagnostic
    provider=protocol.BudgetProvider(config(),tmp_path,False)
    provider.attempts.append({'operation':'crisis'})
    provider.account(GenerationDiagnostic(crisis_number=1,source='authored_fallback',category='timeout',duration_seconds=60.0))
    assert provider.stop_reason=='unknown_billing_stop' and provider.reserved>0
    assert 'known_estimated_cost_usd' not in provider.attempts[-1]


def test_dry_run_preserves_real_baseline_and_leaves_real_comparison_pending(tmp_path,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('Real adapter or credential loading forbidden in offline mode')
    monkeypatch.setattr(protocol,'ChatCompletionsProvider',forbidden)
    monkeypatch.setattr(GenerationSettings,'from_env',forbidden)
    root=tmp_path/'isolated'
    asyncio.run(protocol.run(False,root))
    data=json.loads((root/'evaluation.json').read_text())
    assert data['authorization']['actual_attempts']==4 and not data['authorization']['is_real_provider_run']
    compare=json.loads((root/'comparison.json').read_text())
    assert compare['baseline']['metrics']['crisis']['accepted_count']==4
    assert compare['baseline']['cost']['known_usage_subtotal']=='0.0047954'
    assert compare['revalidation']['metrics'] is None and compare['revalidation']['cost'] is None
    assert all(row['revalidation_category'] is None for row in compare['per_case'])
    assert json.loads((root/'restart-checks.json').read_text())['passed']
    with pytest.raises(FileExistsError):asyncio.run(protocol.run(False,root))
    protocol.verify_preserved()


def test_human_reviews_remain_unassigned(tmp_path,monkeypatch):
    monkeypatch.setattr(protocol,'ChatCompletionsProvider',lambda *a:pytest.fail('No real adapter'))
    root=tmp_path/'dry';asyncio.run(protocol.run(False,root))
    rows=json.loads((root/'human-review.json').read_text())['cases']
    assert len(rows)==4
    assert all(row['continuity_classification'] is None and row['review_status']=='not_reviewed' for row in rows)
    assert all(score is None for row in rows for score in row['scores'].values())
