"""One bounded endgame request after completion; snapshots commit before broadcast."""
import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass, field
import time

from ..domain import Phase
from ..narrative_models import EndgameNarrative, EndgameDiagnostic
from ..persistence import PersistenceError
from .contract import GenerationError, FailureCategory
from .endgame import build_endgame_request, accept_endgame
from .provider import ChatCompletionsProvider, ProviderResponse

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoryOutcome:
    narrative: EndgameNarrative | None = field(default=None, repr=False)
    diagnostic: EndgameDiagnostic | None = None


async def generate_conclusion(settings, provider, request) -> StoryOutcome:
    started=time.perf_counter();status=None;narrative=None;category=FailureCategory.DISABLED
    if settings.enabled:
        try:
            adapter=provider if provider is not None else ChatCompletionsProvider(settings)
            async with asyncio.timeout(settings.timeout_seconds):
                response=await adapter.generate(request)
            if not isinstance(response,ProviderResponse):raise GenerationError(FailureCategory.UNSUPPORTED_RESPONSE)
            status=response.http_status if type(response.http_status) is int and 100<=response.http_status<=599 else None
            narrative=accept_endgame(response.content,request.context)
            if settings.api_key and settings.api_key.get_secret_value() in narrative.model_dump_json():
                raise GenerationError(FailureCategory.INVALID_SCHEMA)
            category='success'
        except TimeoutError:category=FailureCategory.TIMEOUT;narrative=None
        except GenerationError as exc:category=exc.category;status=exc.http_status or status;narrative=None
        except Exception:category=FailureCategory.UNEXPECTED;narrative=None
    diagnostic=EndgameDiagnostic(source='generated' if narrative else 'deterministic_fallback', category=category,
        duration_seconds=round(time.perf_counter()-started,3),http_status=status)
    return StoryOutcome(narrative,diagnostic)


class LiveConclusions:
    def __init__(self, store, lock, connections, settings, provider=None):
        self.store,self.lock,self.connections=store,lock,connections
        self.settings,self.provider=settings,provider
        self.tasks={};self.completed={};self.stopping=False

    def launch_pending(self):
        if self.stopping:return
        for token in self.store.mission_tokens():
            mission=self.store.get(token);state=mission.conclusion
            if mission.phase not in (Phase.COMPLETED,Phase.FAILED) or not state or state.status!='pending':continue
            key=(token,state.id)
            if key in self.tasks:continue
            try:request=build_endgame_request(mission)
            except (ValueError,TypeError,AttributeError):
                self.store.finish_conclusion(token,state.id,state.basis_hash,None,
                    EndgameDiagnostic(source='deterministic_fallback',category='internal_state',duration_seconds=0.0))
                self.connections.pending.add(token)
                continue
            self.tasks[key]=asyncio.create_task(self._run(key,state.basis_hash,request))

    async def _run(self,key,basis,request):
        token,attempt=key
        started=time.perf_counter()
        try:
            outcome=self.completed.get(key)
            if outcome is None:
                outcome=await generate_conclusion(self.settings,self.provider,request)
                self.completed[key]=outcome
            async with self.lock:
                admitted=self.store.finish_conclusion(token,attempt,basis,outcome.narrative,outcome.diagnostic)
            self.completed.pop(key,None)
            if admitted:
                record=outcome.diagnostic
                logging.getLogger('uvicorn.error').info(
                    'generation_result operation=endgame source=%s category=%s duration_seconds=%.3f http_status=%s',
                    record.source,record.category,record.duration_seconds,record.http_status)
                await self.connections.broadcast(token)
        except PersistenceError:
            logger.error('Conclusion waiting for storage recovery.')
        except asyncio.CancelledError:
            await self._fallback(key,basis,'canceled',round(time.perf_counter()-started,3))
            raise
        except Exception:
            await self._fallback(key,basis,'internal_state',round(time.perf_counter()-started,3))
        finally:self.tasks.pop(key,None)

    async def _fallback(self,key,basis,category,duration=0.0):
        self.completed.pop(key,None)
        try:
            async with self.lock:
                changed=self.store.finish_conclusion(*key,basis,None,
                    EndgameDiagnostic(source='deterministic_fallback',category=category,duration_seconds=duration))
            if changed and not self.stopping:await self.connections.broadcast(key[0])
        except PersistenceError:logger.error('Conclusion fallback waiting for storage recovery.')

    async def close(self):
        self.stopping=True
        tasks=list(self.tasks.values())
        for task in tasks:task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):await task
        self.completed.clear()
