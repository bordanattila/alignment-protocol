"""Explicit proposal acceptance and existing authored selection fallback; no live hook."""
import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
import logging
from typing import Literal

from ..campaign import select_crisis, validate_catalog
from ..domain import Campaign, Crisis, CrisisResult
from .config import GenerationSettings
from .contract import AcceptedScenario, FailureCategory, GenerationError, GenerationRequest, accept_proposal
from .provider import ChatCompletionsProvider, ProviderResponse, ScenarioProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GenerationOutcome:
    snapshot: AcceptedScenario | None = field(default=None, repr=False)
    source: Literal['generated', 'authored'] | None = None
    failure: FailureCategory | None = None
    fallback_failure: Literal['missing_selector', 'invalid_state'] | None = None


def authored_selector(campaign: Campaign, index: int, results: Sequence[CrisisResult]) -> Callable[[], Crisis]:
    # Capture under the caller's existing state lock, then release it before any
    # await. A delayed provider response cannot observe a later mutable mission.
    saved = campaign.model_copy(deep=True)
    history = [result.model_copy(deep=True) for result in results]
    def select():
        validate_catalog(saved.scenarios)
        if not 0 <= index < 10 or len(history) != index:
            raise ValueError('Explicit target slot and prior results are required')
        return select_crisis(saved, index, history)
    return select


class GenerationService:
    def __init__(self, settings: GenerationSettings, provider: ScenarioProvider | None = None,
                 fallback: Callable[[], Crisis] | None = None):
        self.settings = settings
        self.provider = provider
        self.fallback = fallback

    async def generate(self, request: GenerationRequest) -> GenerationOutcome:
        failure = FailureCategory.DISABLED
        if self.settings.enabled:
            try:
                provider = self.provider if self.provider is not None else ChatCompletionsProvider(self.settings)
                # Bound the entire provider operation, including slow streaming,
                # not just an individual HTTP read/connect. Cancellation is not
                # swallowed, so an obsolete developer request can stop cleanly.
                async with asyncio.timeout(self.settings.timeout_seconds):
                    response = await provider.generate(request)
                if not isinstance(response, ProviderResponse):
                    raise GenerationError(FailureCategory.UNSUPPORTED_RESPONSE)
                accepted = accept_proposal(response.content, request.context)
                if self.settings.api_key and self.settings.api_key.get_secret_value() in accepted.canonical_json:
                    raise GenerationError(FailureCategory.INVALID_SCHEMA)
                return GenerationOutcome(snapshot=accepted, source='generated')
            except TimeoutError:
                failure = FailureCategory.TIMEOUT
            except GenerationError as exc:
                failure = exc.category
            except Exception:
                failure = FailureCategory.UNEXPECTED
        # Never log provider exceptions, HTTP bodies, configuration, or context.
        logger.warning('Scenario generation fallback: %s', failure.value)
        if self.fallback is None:
            return GenerationOutcome(failure=failure, fallback_failure='missing_selector')
        try:
            snapshot = AcceptedScenario.from_crisis(self.fallback())
            return GenerationOutcome(snapshot=snapshot, source='authored', failure=failure)
        except Exception:
            logger.warning('Scenario generation fallback unavailable: invalid_state')
            return GenerationOutcome(failure=failure, fallback_failure='invalid_state')
