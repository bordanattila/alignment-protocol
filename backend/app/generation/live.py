"""Single-owner preparation tasks; capture/admit under lock, inference outside it."""
import asyncio
import logging
import time
import json
from collections import deque
from collections.abc import Callable
from contextlib import suppress
from typing import TYPE_CHECKING

from .config import GenerationSettings
from .context import build_context
from .contract import GenerationRequest
from .provider import ScenarioProvider
from .service import GenerationOutcome, GenerationService, authored_selector
from ..domain import Crisis, Phase, GenerationDiagnostic
from ..persistence import PersistenceError

if TYPE_CHECKING:
    from ..missions import MissionStore
    from ..connections import LobbyConnections

logger = logging.getLogger(__name__)


class LiveGeneration:
    def __init__(self, store: 'MissionStore', lock: asyncio.Lock, connections: 'LobbyConnections',
                 settings: GenerationSettings, provider: ScenarioProvider | None = None,
                 clock: Callable[[], float] = time.perf_counter):
        self.store, self.lock, self.connections = store, lock, connections
        self.settings, self.provider = settings, provider
        self.clock = clock
        # Process-local intervals only. No mission/player identifiers or content.
        # Existing persisted outcome diagnostics remain immutable and unchanged.
        self.lifecycle = deque(maxlen=100)
        self.scheduled: dict[tuple[str, str], float] = {}
        self.executing: dict[tuple[str, str], float] = {}
        self.ready: dict[tuple[str, str], float] = {}
        self.tasks: dict[tuple[str, str], asyncio.Task] = {}
        # Retain the accepted result on transient storage failure. Never repeat
        # inference merely because admission/publication could not commit.
        self.completed: dict[tuple[str, str], GenerationOutcome] = {}
        self.publishing: set[tuple[str, str]] = set()
        self.stopping = False

    def launch_pending(self):
        """Caller holds the state lock. Reconnect/ticks cannot duplicate an attempt."""
        for key, task in list(self.tasks.items()):
            token, attempt_id = key
            mission = self.store.get(token)
            if key not in self.publishing and (mission.phase != Phase.PREPARING or not mission.generation or mission.generation.id != attempt_id):
                task.cancel()
        if self.stopping: return
        for token in self.store.mission_tokens():
            mission = self.store.get(token)
            attempt = mission.generation
            if mission.phase != Phase.PREPARING or not attempt or attempt.status != 'pending': continue
            key = (token, attempt.id)
            if key in self.tasks: continue
            try:
                request = GenerationRequest(context=build_context(mission))
                fallback = authored_selector(mission.campaign, attempt.target_index, mission.results)
            except (ValueError, TypeError, AttributeError):
                self.store.fail_generation(token, attempt.id, GenerationDiagnostic(
                    crisis_number=attempt.target_index + 1, source=None, category='internal_state', duration_seconds=0.0))
                self.connections.pending.add(token)
                logger.error('Crisis preparation unavailable: internal_state')
                continue
            self.scheduled.setdefault(key, self.clock())
            task = asyncio.create_task(self._run(key, request, fallback))
            self.tasks[key] = task

    async def _run(self, key: tuple[str, str], request: GenerationRequest, fallback: Callable[[], Crisis]):
        token, attempt_id = key
        started = self.clock()
        first_started = self.executing.setdefault(key, started)
        try:
            outcome = self.completed.get(key)
            if outcome is None:
                outcome = await GenerationService(self.settings, self.provider, fallback, clock=self.clock).generate(request)
                self.completed[key] = outcome
                self.ready[key] = self.clock()
            ready_at = self.ready[key]
            async with self.lock:
                source = ('generated' if outcome.source == 'generated' else 'authored_fallback') if outcome.snapshot else None
                diagnostic = GenerationDiagnostic(
                    crisis_number=request.context.current_crisis_number, source=source,
                    category=outcome.failure or 'success', duration_seconds=outcome.duration_seconds,
                    http_status=outcome.http_status, measurement=outcome.measurement)
                if outcome.snapshot is None:
                    self.store.fail_generation(token, attempt_id, diagnostic)
                    status = 'unavailable'
                else:
                    admitted = self.store.accept_generation(token, attempt_id, outcome.snapshot, source, diagnostic)
                    status = 'admitted' if admitted else 'stale'
                    if admitted:
                        # Uvicorn's INFO logger makes success visible with the
                        # standard server command, without configuring root logging.
                        logging.getLogger('uvicorn.error').info(
                            'crisis_admitted mode=generated crisis=%d source=%s success=%s failure=%s http_status=%s duration_seconds=%.3f',
                            request.context.current_crisis_number, source, outcome.source == 'generated',
                            outcome.failure.value if outcome.failure else 'none', outcome.http_status, outcome.duration_seconds)
                committed_at = self.clock()
                self.publishing.add(key)
            self.completed.pop(key, None)
            await self.connections.broadcast(token)
            published_at = self.clock()
            sample = {
                'crisis_number': request.context.current_crisis_number,
                'status': status, 'source': source,
                'queue_seconds': round(max(0.0, first_started - self.scheduled[key]), 6),
                'generation_seconds': outcome.duration_seconds,
                # Includes lock contention, storage retries and synchronous commit.
                'admission_seconds': round(max(0.0, committed_at - ready_at), 6),
                'server_preparation_seconds': round(max(0.0, committed_at - self.scheduled[key]), 6),
                # Send completion, not receipt acknowledgement or browser rendering.
                'publication_seconds': round(max(0.0, published_at - committed_at), 6),
                'player_visible_wait_seconds': None,
                'browser_render_seconds': None,
            }
            self.lifecycle.append(sample)
            logging.getLogger('uvicorn.error').info('crisis_lifecycle %s', json.dumps(sample, sort_keys=True))
            self.scheduled.pop(key, None)
            self.executing.pop(key, None)
            self.ready.pop(key, None)
        except PersistenceError:
            logger.error('Crisis preparation waiting for storage recovery.')
        except asyncio.CancelledError:
            self.completed.pop(key, None)
            try:
                async with self.lock:
                    self.store.interrupt_generation(token, attempt_id, GenerationDiagnostic(
                        crisis_number=request.context.current_crisis_number, source=None, category='canceled',
                        duration_seconds=round(max(0.0, self.clock() - started), 3)))
            except PersistenceError:
                logger.error('Crisis preparation cancellation waiting for storage recovery.')
            raise
        except Exception:
            # A broken context/selector/admission has an explicit host-retry path.
            # No exception body, provider diagnostic or prompt is published/logged.
            logger.error('Crisis preparation unavailable: internal_state')
            self.completed.pop(key, None)
            try:
                async with self.lock:
                    self.store.fail_generation(token, attempt_id, GenerationDiagnostic(
                        crisis_number=request.context.current_crisis_number, source=None, category='internal_state',
                        duration_seconds=round(max(0.0, self.clock() - started), 3)))
                await self.connections.broadcast(token)
            except PersistenceError:
                logger.error('Crisis preparation waiting for storage recovery.')
        finally:
            self.publishing.discard(key)
            self.tasks.pop(key, None)
            if key not in self.completed:
                self.scheduled.pop(key, None)
                self.executing.pop(key, None)
                self.ready.pop(key, None)

    async def close(self):
        self.stopping = True
        tasks = list(self.tasks.values())
        for task in tasks: task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError): await task
        self.completed.clear()
        self.scheduled.clear()
        self.executing.clear()
        self.ready.clear()
