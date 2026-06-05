/**
 * Episodic `status` taxonomy — the client mirror of the backend's
 * `app/services/jobs/status.py`. Keep the two in lockstep.
 *
 * Encoding (Variant B): an active job sets `status` to the job's type key; a
 * failure sets `failed:<job_type>`; a settled node has no status. The plugin
 * rarely needs the specific job type — for polling it only asks "in flight,
 * failed, or settled?" — so the predicates below stay job-agnostic.
 */

// Job-runner type keys (also the active `status` value while that job runs).
export const JOB_GENERATE_NAME = "generate_episode_name";
export const JOB_PROCESS_EXISTING = "process_existing_episode";

export const FAILED_PREFIX = "failed:";

/** True if `status` marks a terminal failure (`failed:<job>`). */
export function isFailedStatus(status: string | null | undefined): boolean {
  return typeof status === "string" && status.startsWith(FAILED_PREFIX);
}

/** True if `status` marks an active (non-failed, non-settled) job. */
export function isInFlightStatus(status: string | null | undefined): boolean {
  return typeof status === "string" && status.length > 0 && !isFailedStatus(status);
}

/** True if the node has settled — no job in flight (status absent/empty). */
export function isSettledStatus(status: string | null | undefined): boolean {
  return !status;
}
