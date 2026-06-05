"""Server-side background job-runner for PipGraph.

A deliberately minimal in-process queue: an ``asyncio.Queue`` drained by a single
worker started in the FastAPI ``lifespan``. It is a *job-runner*, not a workflow
engine — each job is ``{type, args}`` dispatched to one manager method, with no
steps, branches, or orchestration (a guard against re-growing the removed
LangGraph layer). See ``pipgraph-obsidian/.docs/plans/process-queue/``.
"""

from app.services.jobs.queue import enqueue, start_worker, stop_worker
from app.services.jobs.status import (
    JOB_GENERATE_NAME,
    JOB_PROCESS_EXISTING,
    failed,
    is_failed,
    is_in_flight,
    job_type_of,
)

__all__ = [
    "enqueue",
    "start_worker",
    "stop_worker",
    "JOB_GENERATE_NAME",
    "JOB_PROCESS_EXISTING",
    "failed",
    "is_failed",
    "is_in_flight",
    "job_type_of",
]
