"""Explicit proposal acceptance and existing authored selection fallback."""
import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
import logging
import time
from typing import Literal

from ..campaign import select_crisis, validate_catalog
from ..domain import Campaign, Crisis, CrisisResult
from .config import GenerationSettings
from .contract import AcceptedScenario, FailureCategory, GenerationError, GenerationRequest, accept_proposal, reference_history
from .provider import ChatCompletionsProvider, ProviderResponse, ScenarioProvider
from .measurement import GenerationTrace, GenerationMeasurement

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GenerationOutcome:
    snapshot: AcceptedScenario | None = field(default=None, repr=False)
    source: Literal['generated', 'authored'] | None = None
    failure: FailureCategory | None = None
    fallback_failure: Literal['missing_selector', 'invalid_state'] | None = None
    duration_seconds: float = 0.0
    http_status: int | None = None
    measurement: GenerationMeasurement | None = None


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
                 fallback: Callable[[], Crisis] | None = None, clock=time.perf_counter):
        self.settings = settings
        self.provider = provider
        self.fallback = fallback
        self.clock = clock

    async def generate(self, request: GenerationRequest) -> GenerationOutcome:
        started = self.clock()
        trace = GenerationTrace(self.settings, 'crisis', bool(reference_history(request.context)), self.clock)
        http_status = None

        def finish(**fields):
            outcome = GenerationOutcome(**fields, duration_seconds=round(self.clock() - started, 6),
                                        http_status=http_status, measurement=trace.measurement())
            log = logger.warning if outcome.failure else logger.info
            log('generation_result mode=generated crisis=%d source=%s success=%s failure=%s http_status=%s duration_seconds=%.3f',
                request.context.current_crisis_number, 'authored_fallback' if outcome.source == 'authored' else outcome.source or 'none',
                outcome.source == 'generated', outcome.failure.value if outcome.failure else 'none',
                outcome.http_status, outcome.duration_seconds)
            return outcome

        failure = FailureCategory.DISABLED
        if self.settings.enabled:
            try:
                provider = self.provider if self.provider is not None else ChatCompletionsProvider(self.settings)
                # Bound the entire provider operation, including slow streaming,
                # not just an individual HTTP read/connect. Cancellation is not
                # swallowed, so an obsolete developer request can stop cleanly.
                async with asyncio.timeout(self.settings.timeout_seconds):
                    response = await trace.call(provider, request)
                if not isinstance(response, ProviderResponse):
                    raise GenerationError(FailureCategory.UNSUPPORTED_RESPONSE)
                status = response.http_status
                http_status = status if type(status) is int and 100 <= status <= 599 else None
                accepted = trace.validate(lambda: accept_proposal(response.content, request.context))
                if self.settings.api_key and self.settings.api_key.get_secret_value() in accepted.canonical_json:
                    raise GenerationError(FailureCategory.INVALID_SCHEMA)
                trace.reference_count = len(accepted.continuity_references)
                return finish(snapshot=accepted, source='generated')
            except TimeoutError:
                failure = FailureCategory.TIMEOUT
            except GenerationError as exc:
                failure = exc.category
                trace.rejection_detail = exc.detail
                if exc.http_status is not None: http_status = exc.http_status
            except Exception:
                failure = FailureCategory.UNEXPECTED
        # Never log provider exceptions, HTTP bodies, configuration, or context.
        if self.fallback is None:
            return finish(failure=failure, fallback_failure='missing_selector')
        try:
            snapshot = trace.fallback(lambda: AcceptedScenario.from_crisis(self.fallback()))
            return finish(snapshot=snapshot, source='authored', failure=failure)
        except Exception:
            logger.warning('Scenario generation fallback unavailable: invalid_state')
            return finish(failure=failure, fallback_failure='invalid_state')
