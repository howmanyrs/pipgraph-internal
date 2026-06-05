"""Episodic ``status`` taxonomy for the job-runner.

The ``status`` property on an Episodic is the durable, server-side record of
*what async work is in flight for this node* (process-queue plan, P2). It is the
single source of truth that the polling endpoint, the client reconcile, and the
Phase-3 server re-enqueue all read.

Encoding (Variant B — job kind carried in the value, not a second field):

- **Active job**  → ``status`` equals the **job-runner type key** itself
  (``"generate_episode_name"`` / ``"process_existing_episode"``). This makes
  re-enqueue a direct map: ``enqueue(node.status, …)`` with no lookup table.
- **Failed job**  → ``"failed:<job_type>"`` (e.g. ``"failed:process_existing_episode"``).
  The ``failed:`` prefix is the terminal marker; the suffix preserves which job
  failed so a retry knows what to re-run.
- **Settled**     → property absent (``None``). No job in flight.

Why bare ``"processing"`` was dropped: it collided across the two job kinds
(naming vs heavy extraction), so a status-filtered list or a restart re-enqueue
could not tell which job a stuck node needed.
"""

# Job-runner type keys. These double as the *active* ``status`` value of a node
# whose job is in flight (see module docstring). Keep in sync with the handler
# registrations in ``queue.py``.
JOB_GENERATE_NAME = "generate_episode_name"
JOB_PROCESS_EXISTING = "process_existing_episode"

FAILED_PREFIX = "failed:"


def failed(job_type: str) -> str:
    """Status value for a failed job of the given type (``"failed:<job_type>"``)."""
    return f"{FAILED_PREFIX}{job_type}"


def is_failed(status: str | None) -> bool:
    """True if ``status`` marks a terminal failure."""
    return status is not None and status.startswith(FAILED_PREFIX)


def is_in_flight(status: str | None) -> bool:
    """True if ``status`` marks an active (non-failed, non-settled) job."""
    return status is not None and not status.startswith(FAILED_PREFIX)


def job_type_of(status: str | None) -> str | None:
    """The underlying job-runner type for a status, stripping any ``failed:``.

    ``None`` for a settled (absent) status. Used by the Phase-3 re-enqueue to map
    a stuck node back to the handler that should re-run it.
    """
    if status is None:
        return None
    if status.startswith(FAILED_PREFIX):
        return status[len(FAILED_PREFIX):]
    return status
