"""Opt-in real provider: at most two synthetic crises, isolated SQLite, no retries."""
import argparse
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import time

from dotenv import dotenv_values

from app.campaign import load_campaign_catalog
from app.domain import Phase
from app.generation.config import GenerationSettings
from app.generation.live import LiveGeneration
from app.generation.provider import ChatCompletionsProvider
from app.missions import MissionStore
from app.persistence import SQLiteMissions


class RecordedProvider:
    def __init__(self, settings):
        self.provider = ChatCompletionsProvider(settings)
        self.requests = []

    async def generate(self, request):
        if len(self.requests) >= 2: raise RuntimeError('Smoke request budget exhausted')
        self.requests.append(request)
        return await self.provider.generate(request)


class NoSockets:
    pending = set()
    async def broadcast(self, token): pass


async def exercise(settings):
    provider = RecordedProvider(settings)
    now = [1_700_000_000.0]
    with tempfile.TemporaryDirectory(prefix='ce-provider-progression-') as temporary:
        path = Path(temporary) / 'synthetic.sqlite3'
        store = MissionStore(clock=lambda: now[0], campaign_loader=load_campaign_catalog,
                             persistence=SQLiteMissions(path), generation_enabled=True)
        store.initialize()
        live = LiveGeneration(store, asyncio.Lock(), NoSockets(), settings, provider)
        try:
            mission, host = store.create('Synthetic Host', 'generated')
            credentials = [host.credential]
            for name in ['Synthetic Second', 'Synthetic Third']:
                credentials.append(store.join(mission.token, name)[1].credential)
            for player in mission.players: store.set_connected(mission.token, player.id, True)
            store.start(mission.token, credentials[0])
            for index in range(2):
                expected_metrics = mission.metrics.model_dump()
                started = time.perf_counter()
                async with live.lock: live.launch_pending()
                await asyncio.gather(*list(live.tasks.values()))
                source = mission.admissions[-1].source if mission.admissions else 'none'
                request = provider.requests[-1]
                assert request.context.current_crisis_number == index + 1
                assert request.context.metrics.model_dump() == expected_metrics
                assert len(request.context.history) == index
                if index:
                    assert request.context.history[-1].choice_id == 'A'
                    assert request.context.used_scenario_ids == (mission.results[0].crisis_id,)
                print(json.dumps({'crisis_number': index + 1, 'source': source,
                                  'duration_seconds': round(time.perf_counter() - started, 3),
                                  'context_matches_authority': True,
                                  'history_count': len(request.context.history),
                                  'generated_identity': bool(mission.crisis and mission.crisis.id.startswith('generated-'))}), flush=True)
                if source != 'generated': return False  # no paid retry or second request on failure
                assert mission.phase == Phase.BRIEFING
                if index == 0:
                    store.begin_discussion(mission.token, credentials[0])
                    now[0] = mission.deadline
                    store.advance_due(mission.token)
                    round_id = mission.rounds[-1].id
                    for credential in credentials: store.vote(mission.token, credential, round_id, 'A')
                    assert mission.phase == Phase.DECISION_LOCKED
                    store.continue_mission(mission.token, credentials[0], mission.results[-1].id)
            token, accepted = mission.token, mission.crisis.model_dump_json()
            await live.close()
            store.close()
            restored = MissionStore(persistence=SQLiteMissions(path))
            try:
                restored.initialize()
                assert restored.get(token).mode == 'generated'
                assert restored.get(token).crisis.model_dump_json() == accepted
                assert len(provider.requests) == 2
            finally: restored.close()
            print(json.dumps({'result':'passed', 'provider_requests':2, 'restart_preserved_snapshot':True}), flush=True)
            return True
        finally:
            await live.close()
            store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Explicitly authorize up to two real model requests')
    parser.add_argument('--env-file', type=Path, help='Explicit server configuration file; never printed')
    parser.add_argument('--model', help='Explicit override for this smoke only; does not edit configuration')
    parser.add_argument('--timeout-seconds', type=float, help='Bounded per-request timeout override for this smoke only')
    args = parser.parse_args()
    if not args.live: parser.error('--live is required; this test can incur provider charges')
    settings = GenerationSettings.from_env(
        {k:v for k,v in dotenv_values(args.env_file).items() if v is not None} if args.env_file else None)
    if args.model: settings = replace(settings, model=args.model)
    if args.timeout_seconds is not None: settings = replace(settings, timeout_seconds=args.timeout_seconds)
    if not settings.enabled: parser.error('Generation must be explicitly enabled')
    raise SystemExit(0 if asyncio.run(exercise(settings)) else 1)


if __name__ == '__main__': main()
