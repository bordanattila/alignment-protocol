"""Offline synthetic lifecycle intervals, not provider/network performance evidence."""
import argparse
import asyncio
import json
from pathlib import Path

from app.domain import Phase
from app.generation.contract import FailureCategory, GenerationError
from test_live_generation import setup, launch, settle, ProgressiveProvider
from test_persistence import voting, votes


class MonotonicClock:
    def __init__(self): self.now = 0.0
    def __call__(self): return self.now
    def advance(self, seconds): self.now += seconds


class TimedProvider(ProgressiveProvider):
    def __init__(self, clock):
        super().__init__()
        self.clock, self.delay, self.failure = clock, 0.0, None

    async def generate(self, request):
        self.clock.advance(self.delay)
        if self.failure:
            self.requests.append(request)
            raise GenerationError(self.failure)
        return await super().generate(request)


async def measure(name, delay, failure=None):
    monotonic = MonotonicClock()
    provider = TimedProvider(monotonic)
    store, mission, credentials, game_clock, live = setup(provider=provider, timeout=60)
    live.clock = monotonic
    try:
        await launch(live); await settle(live)
        voting(store, mission, credentials, game_clock); votes(store, mission, credentials, ['A']*3)
        assert mission.phase == Phase.DECISION_LOCKED
        # Reading a resolved result currently does not start inference.
        monotonic.advance(10)
        await launch(live)
        assert len(provider.requests) == 1 and not live.tasks
        provider.delay, provider.failure = float(delay), failure
        ready_at = monotonic()
        store.continue_mission(mission.token, credentials[0], mission.results[-1].id)
        assert store.project(mission.token, mission.host_id)['result'] is not None
        await launch(live); await settle(live)
        admitted_at = monotonic()
        sample = dict(live.lifecycle[-1])
        assert mission.phase == Phase.BRIEFING and len(provider.requests) == 2
        # Nothing waits for inference after admission; normal presence gate applies.
        before = monotonic()
        store.begin_discussion(mission.token, credentials[0])
        assert mission.phase == Phase.DISCUSSION
        return {'case': name, 'evidence': 'injected-clock fake-provider simulation',
                'review_seconds': 10, 'review_inference_overlap_seconds': 0,
                'simulated_server_ready_to_admission_seconds': admitted_at-ready_at,
                'after_admission_progression_wait_seconds': monotonic()-before,
                'lifecycle': sample, 'source': mission.admissions[-1].source,
                'category': str(mission.generation_diagnostics[-1].category),
                'new_provider_attempts': 1, 'browser_render_seconds': None}
    finally:
        await live.close(); store.close()


async def measurements():
    cases = [('immediate',0,None),('5 seconds',5,None),('15 seconds',15,None),
             ('30 seconds',30,None),('timeout',60,FailureCategory.TIMEOUT),
             ('failure',5,FailureCategory.UNAVAILABLE)]
    return [await measure(*case) for case in cases]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(asyncio.run(measurements()), indent=2)+'\n')
