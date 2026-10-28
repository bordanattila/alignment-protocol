"""Single-owner preparation tasks; capture/admit under lock, inference outside it."""
import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from typing import TYPE_CHECKING

from .config import GenerationSettings
from .context import build_context
from .contract import GenerationRequest
from .provider import ScenarioProvider
from .service import GenerationOutcome, GenerationService, authored_selector
from ..domain import Crisis, Phase
from ..persistence import PersistenceError

if TYPE_CHECKING:
    from ..missions import MissionStore
    from ..connections import LobbyConnections

logger = logging.getLogger(__name__)


class LiveGeneration:
    def __init__(self, store: 'MissionStore', lock: asyncio.Lock, connections: 'LobbyConnections',
                 settings: GenerationSettings, provider: ScenarioProvider | None = None):
        self.store, self.lock, self.connections = store, lock, connections
        self.settings, self.provider = settings, provider
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
                self.store.fail_generation(token, attempt.id)
                self.connections.pending.add(token)
                logger.error('Crisis preparation unavailable: internal_state')
                continue
            task = asyncio.create_task(self._run(key, request, fallback))
            self.tasks[key] = task

    async def _run(self, key: tuple[str, str], request: GenerationRequest, fallback: Callable[[], Crisis]):
        token, attempt_id = key
        try:
            outcome = self.completed.get(key)
            if outcome is None:
                outcome = await GenerationService(self.settings, self.provider, fallback).generate(request)
                self.completed[key] = outcome
            async with self.lock:
                if outcome.snapshot is None:
                    self.store.fail_generation(token, attempt_id)
                else:
                    self.store.accept_generation(token, attempt_id, outcome.snapshot,
                                                 'generated' if outcome.source == 'generated' else 'authored_fallback')
                self.publishing.add(key)
            self.completed.pop(key, None)
            await self.connections.broadcast(token)
        except PersistenceError:
            logger.error('Crisis preparation waiting for storage recovery.')
        except asyncio.CancelledError:
            self.completed.pop(key, None)
            raise
        except Exception:
            # A broken context/selector/admission has an explicit host-retry path.
            # No exception body, provider diagnostic or prompt is published/logged.
            logger.error('Crisis preparation unavailable: internal_state')
            self.completed.pop(key, None)
            try:
                async with self.lock:
                    self.store.fail_generation(token, attempt_id)
                await self.connections.broadcast(token)
            except PersistenceError:
                logger.error('Crisis preparation waiting for storage recovery.')
        finally:
            self.publishing.discard(key)
            self.tasks.pop(key, None)

    async def close(self):
        self.stopping = True
        tasks = list(self.tasks.values())
        for task in tasks: task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError): await task
        self.completed.clear()
