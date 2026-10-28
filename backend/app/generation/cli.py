"""Developer-only synthetic exercise. Never imports or persists an active mission."""
import argparse
import asyncio
from dataclasses import replace
import json

from ..campaign import load_campaign_catalog
from ..domain import Campaign
from .config import ConfigurationError, GenerationSettings
from .contract import (FailureCategory, FrozenMetrics, GenerationContext, GenerationError,
                       GenerationRequest, VERSION, proposal_schema)
from .provider import ProviderResponse
from .service import GenerationService, authored_selector


class FakeProvider:
    def __init__(self, failure: FailureCategory | None = None):
        self.failure = failure

    async def generate(self, request: GenerationRequest) -> ProviderResponse:
        if self.failure: raise GenerationError(self.failure)
        # This is explicitly a fake, not evidence of model compatibility. Reuse
        # an authored schema-valid payload to exercise validation/normalization.
        crisis = load_campaign_catalog()[0].crisis.model_dump(mode='json')
        crisis.pop('id')
        return ProviderResponse(json.dumps({'schema_version': VERSION, 'crisis': crisis,
                                            'continuity_references': []}))


async def run(mode: str):
    context = GenerationContext(current_crisis_number=1, metrics=FrozenMetrics(), history=(), used_scenario_ids=())
    request = GenerationRequest(context=context)
    selector = authored_selector(Campaign(seed='generation-harness', scenarios=load_campaign_catalog()), 0, [])
    try:
        settings = GenerationSettings.from_env()
        provider = None
        if mode == 'disabled': settings = replace(settings, enabled=False)
        elif mode == 'fake':
            settings = replace(settings, enabled=True)
            provider = FakeProvider()
        elif mode == 'failure':
            settings = replace(settings, enabled=True)
            provider = FakeProvider(FailureCategory.UNAVAILABLE)
        # live requires both the explicit mode and ENABLED=true configuration.
    except ConfigurationError:
        settings = GenerationSettings(enabled=True)
        provider = FakeProvider(FailureCategory.CONFIGURATION)
    outcome = await GenerationService(settings, provider, selector).generate(request)
    return {'mode': mode, 'source': outcome.source, 'failure': outcome.failure,
            'fallback_failure': outcome.fallback_failure,
            'scenario': outcome.snapshot.to_crisis().model_dump(mode='json') if outcome.snapshot else None,
            'fingerprint': outcome.snapshot.fingerprint if outcome.snapshot else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['disabled', 'fake', 'failure', 'live'], default='disabled')
    parser.add_argument('--schema', action='store_true')
    args = parser.parse_args()
    print(json.dumps(proposal_schema() if args.schema else asyncio.run(run(args.mode)), indent=2, ensure_ascii=False))


if __name__ == '__main__': main()
