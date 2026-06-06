import { Notice } from "obsidian";
import type PipGraphPlugin from "../main";
import {
  JOB_PROCESS_EXISTING,
  failedStatus,
  isFailedStatus,
  isSettledStatus,
} from "../backend";

const POLL_INTERVAL_MS = 2000;
// Heavy extraction can be slow; give each note a generous ceiling before we stop
// actively polling it. The durable record is server-side (status on the node),
// so a dropped poll is recovered by the next reconcile, not lost.
const POLL_MAX_ATTEMPTS = 150; // ~5 min at 2s

/**
 * Processing tracker (process-queue P2 + P3).
 *
 * Heavy `process_existing_episode` work runs as a server-side job; the client
 * only needs to know when a note settles (drop the "in flight" indicator) or
 * fails (show a "failed" indicator until retried). Unlike {@link CaptureOutbox},
 * there is **no client-side durable record**: the note already exists as a real
 * vault file and the node + link already exist in the graph, so the durable
 * "processing" record lives entirely server-side as the node's `status`. This
 * tracker is therefore just an in-memory poller plus the path bookkeeping the
 * file-tree decoration needs.
 *
 * The in-memory `inFlight` set **gates** the single poll loop: the loop runs
 * only while something is in flight and stops when the set drains, so the plugin
 * never scans the backend in the background. On start, {@link reconcile} asks the
 * server once "what's still processing / what failed?" to re-seed both sets
 * (resuming markers after a restart); after that, polling is point-by-uuid.
 *
 * P3 additions: a `failed` set (markers persist until {@link retryFailed}) and a
 * uuid→path map so the {@link FileDecorator} can mark the right explorer rows.
 */
export class ProcessingTracker {
  private readonly plugin: PipGraphPlugin;
  private readonly inFlight = new Set<string>();
  private readonly failed = new Set<string>();
  /** uuid → file_path, for both in-flight and failed nodes (drives decoration). */
  private readonly paths = new Map<string, string>();
  private readonly attempts = new Map<string, number>();
  private looping = false;

  /** Fired whenever the tracked sets change (drives statusbar + decoration). */
  onChange: (() => void) | null = null;

  constructor(plugin: PipGraphPlugin) {
    this.plugin = plugin;
  }

  /** Notes whose processing the client is currently watching (statusbar). */
  get inFlightCount(): number {
    return this.inFlight.size;
  }

  /** Notes whose processing failed and await a manual retry. */
  get failedCount(): number {
    return this.failed.size;
  }

  /** File paths of in-flight notes (FileDecorator: "processing" marker). */
  get processingPaths(): Set<string> {
    return this.pathsFor(this.inFlight);
  }

  /** File paths of failed notes (FileDecorator: "failed" marker). */
  get failedPaths(): Set<string> {
    return this.pathsFor(this.failed);
  }

  /**
   * Reverse-lookup: the failed-set uuid whose tracked path matches `path`, or
   * undefined. Backs the per-file "Process note" context-menu item — both its
   * visibility (defined ⇒ show) and the retry target. In-memory only: failed
   * uuids carry a known path (seeded on {@link reconcile}, kept across the
   * failed transition), so no backend round-trip is needed here.
   */
  failedUuidForPath(path: string): string | undefined {
    for (const uuid of this.failed) {
      if (this.paths.get(uuid) === path) return uuid;
    }
    return undefined;
  }

  /**
   * Start watching a note's processing job (no-op if already watched). An
   * optional `path` seeds the decoration map up front (the drop site knows the
   * post-move path); otherwise it is filled in from the node on the next sweep.
   */
  track(uuid: string, path?: string): void {
    this.failed.delete(uuid); // a fresh run supersedes a prior failure
    if (path) this.paths.set(uuid, path);
    if (this.inFlight.has(uuid)) return;
    this.inFlight.add(uuid);
    this.attempts.set(uuid, 0);
    this.onChange?.();
    void this.ensureLooping();
  }

  /**
   * Re-seed the watch + failed sets from server status (called once on plugin
   * load). Resumes markers for jobs enqueued before a restart, without a
   * standing background scan — two queries, then point polling.
   */
  async reconcile(): Promise<void> {
    try {
      const processing = await this.plugin.client.listEpisodicsByStatus(JOB_PROCESS_EXISTING);
      for (const ep of processing) this.track(ep.uuid, ep.file_path ?? undefined);
    } catch {
      // backend unreachable on load — markers resume on a later reconcile
    }
    try {
      const failures = await this.plugin.client.listEpisodicsByStatus(
        failedStatus(JOB_PROCESS_EXISTING),
      );
      for (const ep of failures) this.markFailed(ep.uuid, ep.file_path ?? undefined);
    } catch {
      // ditto
    }
  }

  /**
   * Re-queue every failed note (the "process all failed notes" command). Each
   * goes back to the server via reprocess, then re-enters the in-flight set so
   * the marker flips from failed → processing. Returns how many were retried.
   */
  async retryFailed(): Promise<number> {
    const uuids = [...this.failed];
    let retried = 0;
    for (const uuid of uuids) {
      if (await this.retryOne(uuid)) retried++;
    }
    return retried;
  }

  /**
   * Re-queue a single failed note via reprocess, then move it back into the
   * in-flight set (failed→processing, marker flips). Returns false — leaving it
   * in the failed set — if the uuid isn't currently failed or the server
   * rejected it. Backs the per-file "Process note" menu action; {@link
   * retryFailed} fans out over this.
   */
  async retryOne(uuid: string): Promise<boolean> {
    if (!this.failed.has(uuid)) return false;
    try {
      await this.plugin.client.reprocessEpisodic(uuid);
      this.track(uuid); // failed→inFlight; keeps the known path
      return true;
    } catch {
      return false; // stays failed; the user can retry again later
    }
  }

  // -- poll loop --------------------------------------------------------------

  /** The single poll loop. Runs only while the watch set is non-empty. */
  private async ensureLooping(): Promise<void> {
    if (this.looping) return;
    this.looping = true;
    try {
      while (this.inFlight.size > 0) {
        await sleep(POLL_INTERVAL_MS);
        await this.sweep();
      }
    } finally {
      this.looping = false;
    }
  }

  private async sweep(): Promise<void> {
    // Snapshot — settle()/markFailed() mutate the set as we go.
    for (const uuid of [...this.inFlight]) {
      let episodic;
      try {
        episodic = await this.plugin.client.getEpisodicByUuid(uuid);
      } catch {
        continue; // transient backend hiccup — retry next sweep
      }
      if (episodic?.file_path) this.paths.set(uuid, episodic.file_path);

      if (episodic && isFailedStatus(episodic.status)) {
        new Notice(`PipGraph: processing failed for "${episodic.name}".`);
        this.markFailed(uuid);
        continue;
      }
      if (episodic && isSettledStatus(episodic.status)) {
        this.settle(uuid); // done — marker drops
        continue;
      }

      // Still processing (or not yet visible) — bump the attempt ceiling.
      const next = (this.attempts.get(uuid) ?? 0) + 1;
      if (next >= POLL_MAX_ATTEMPTS) {
        // Stop actively polling; the server-side status persists and a later
        // reconcile re-seeds this note if it is genuinely still in flight.
        this.settle(uuid);
      } else {
        this.attempts.set(uuid, next);
      }
    }
  }

  /** Drop a note from every set (settled successfully) and refresh the UI. */
  private settle(uuid: string): void {
    this.inFlight.delete(uuid);
    this.failed.delete(uuid);
    this.attempts.delete(uuid);
    this.paths.delete(uuid);
    this.onChange?.();
    this.plugin.refreshTriagePanels();
  }

  /** Move a note from in-flight to the failed set (marker persists until retry). */
  private markFailed(uuid: string, path?: string): void {
    if (path) this.paths.set(uuid, path);
    this.inFlight.delete(uuid);
    this.attempts.delete(uuid);
    this.failed.add(uuid);
    this.onChange?.();
    this.plugin.refreshTriagePanels();
  }

  private pathsFor(uuids: Set<string>): Set<string> {
    const out = new Set<string>();
    for (const uuid of uuids) {
      const path = this.paths.get(uuid);
      if (path) out.add(path);
    }
    return out;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
