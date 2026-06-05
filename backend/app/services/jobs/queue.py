"""In-process job queue + single background worker.

Owns work that is too slow to run inside a request: LLM episode-name generation
(``generate_episode_name``) and the heavy extraction pipeline
(``process_existing_episode``, P2). The queue lives on the server and is shared
by every client interface — the backend is the engine, clients are thin senders
(process-queue plan, "движок + интерфейсы").

Scope guard: this is a **job-runner**, not a workflow engine. A job is a flat
``{"type": str, "args": dict}`` dispatched to exactly one handler. No multi-step
graphs, no conditional branching — keep it that way.

Durability: the queue is in-memory, so anything still queued is lost if the
backend restarts. The *status* of in-flight work survives on the Episodic node
(``status="processing"``); server-side re-enqueue on startup is Phase 3.
Concurrency is fixed at 1 (one worker) — sequential processing by design.
"""

import asyncio
import logging
from typing import Any, Awaitable, Callable

from app.services.jobs.status import (
    JOB_GENERATE_NAME,
    JOB_PROCESS_EXISTING,
    failed,
)

logger = logging.getLogger(__name__)

# A job is a flat dict: {"type": <handler key>, "args": {...}}.
Job = dict[str, Any]
JobHandler = Callable[[dict[str, Any]], Awaitable[None]]


class _JobRunner:
    """Singleton holding the queue, the worker task, and the handler registry."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Job | None] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._handlers: dict[str, JobHandler] = {}

    def register(self, job_type: str, handler: JobHandler) -> None:
        self._handlers[job_type] = handler

    def enqueue(self, job_type: str, args: dict[str, Any]) -> None:
        """Add a job. Safe to call from request handlers; returns immediately."""
        if job_type not in self._handlers:
            # Fail loud in logs but don't break the caller — the node already exists.
            logger.error(f"[jobs] enqueue of unknown job type '{job_type}' — dropping")
            return
        self._queue.put_nowait({"type": job_type, "args": args})
        logger.info(f"[jobs] enqueued '{job_type}' (queue size ~{self._queue.qsize()})")

    async def _worker(self) -> None:
        logger.info("[jobs] worker started (concurrency=1)")
        while True:
            job = await self._queue.get()
            try:
                if job is None:  # sentinel: graceful stop
                    logger.info("[jobs] worker received stop sentinel")
                    return
                handler = self._handlers.get(job["type"])
                if handler is None:
                    logger.error(f"[jobs] no handler for '{job['type']}' — skipping")
                    continue
                logger.info(f"[jobs] running '{job['type']}'")
                await handler(job["args"])
            except Exception:
                # A failed job must never kill the worker — log and move on.
                logger.exception(f"[jobs] job failed: {job}")
            finally:
                self._queue.task_done()

    def start(self) -> None:
        if self._worker_task is not None:
            return
        self._worker_task = asyncio.create_task(self._worker(), name="pipgraph-job-worker")

    async def stop(self) -> None:
        """Graceful drain: let the in-flight job finish, then stop the worker.

        We push a ``None`` sentinel so the worker exits after the current job
        completes rather than being cancelled mid-LLM-call. Anything still queued
        behind the sentinel is dropped (acceptable: status stays ``processing``
        and is re-driven by the client outbox / Phase-3 server re-enqueue).
        """
        if self._worker_task is None:
            return
        self._queue.put_nowait(None)
        try:
            await asyncio.wait_for(self._worker_task, timeout=30.0)
        except asyncio.TimeoutError:
            logger.warning("[jobs] worker drain timed out — cancelling")
            self._worker_task.cancel()
        self._worker_task = None
        logger.info("[jobs] worker stopped")


_runner = _JobRunner()


# --- Handlers -------------------------------------------------------------

async def _handle_generate_episode_name(args: dict[str, Any]) -> None:
    """Generate an Episodic's name via LLM and finalize it.

    args: {"episodic_uuid": str, "content": str}

    On success: overwrites the provisional name and clears ``status``.
    On failure: marks the node ``status="failed:generate_episode_name"`` so the
    client/visual layer can surface a retry and a re-enqueue knows which job to
    re-run. Imports are local to avoid an import cycle with the manager.
    """
    from app.services.graphiti import get_graphiti, PipGraphManager
    from app.services.graphiti.name_generator import generate_episode_name

    episodic_uuid = args["episodic_uuid"]
    content = args["content"]

    graphiti = await get_graphiti()
    manager = PipGraphManager(graphiti)

    try:
        name = await generate_episode_name(
            episode_body=content,
            llm_client=manager.clients.llm_client,
        )
        await manager.finalize_episode_name(episodic_uuid, name)
        logger.info(f"[jobs] named episode {episodic_uuid} -> '{name}'")
    except Exception:
        logger.exception(f"[jobs] naming failed for {episodic_uuid}")
        await manager.set_episodic_status(episodic_uuid, failed(JOB_GENERATE_NAME))
        raise


async def _handle_process_existing_episode(args: dict[str, Any]) -> None:
    """Run the heavy extraction pipeline on an already-linked Episodic (P2).

    args: {"episodic_uuid": str}

    The node is expected to already carry ``status="process_existing_episode"``
    (stamped synchronously at enqueue time by ``place_episode``), so the durable
    "in flight" record exists the moment the job is queued — not when the worker
    picks it up. ``process_existing_episode`` itself carries that flag past its
    internal bulk-save (the ``episode.save()`` re-apply); here we only resolve the
    terminal state:

    - On success: clear ``status`` (settled).
    - On failure: mark ``status="failed:process_existing_episode"`` for retry.

    Imports are local to avoid an import cycle with the manager.
    """
    from app.services.graphiti import get_graphiti, PipGraphManager

    episodic_uuid = args["episodic_uuid"]

    graphiti = await get_graphiti()
    manager = PipGraphManager(graphiti)

    try:
        await manager.process_existing_episode(episodic_uuid=episodic_uuid)
        await manager.clear_episodic_status(episodic_uuid)
        logger.info(f"[jobs] processed existing episode {episodic_uuid} (status cleared)")
    except Exception:
        logger.exception(f"[jobs] processing failed for {episodic_uuid}")
        await manager.set_episodic_status(episodic_uuid, failed(JOB_PROCESS_EXISTING))
        raise


_runner.register(JOB_GENERATE_NAME, _handle_generate_episode_name)
_runner.register(JOB_PROCESS_EXISTING, _handle_process_existing_episode)


# --- Public API -----------------------------------------------------------

def enqueue(job_type: str, args: dict[str, Any]) -> None:
    _runner.enqueue(job_type, args)


def start_worker() -> None:
    _runner.start()


async def stop_worker() -> None:
    await _runner.stop()
