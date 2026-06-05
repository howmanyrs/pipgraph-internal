import { Notice } from "obsidian";
import type PipGraphPlugin from "../main";
import {
  JOB_PROCESS_EXISTING,
  isFailedStatus,
  isSettledStatus,
} from "../backend";

const POLL_INTERVAL_MS = 2000;
// Heavy extraction can be slow; give each note a generous ceiling before we stop
// actively polling it. The durable record is server-side (status on the node),
// so a dropped poll is recovered by the next reconcile, not lost.
const POLL_MAX_ATTEMPTS = 150; // ~5 min at 2s

/**
 * Processing tracker (process-queue P2).
 *
 * Heavy `process_existing_episode` work runs as a server-side job; the client
 * only needs to know when a note settles so it can drop the "in flight"
 * indicator. Unlike {@link CaptureOutbox}, there is **no client-side durable
 * record**: the note already exists as a real vault file and the node + link
 * already exist in the graph, so the durable "processing" record lives entirely
 * server-side as the node's `status`. This tracker is therefore just an
 * in-memory poller.
 *
 * The in-memory `inFlight` set **gates** the single poll loop: the loop runs
 * only while something is in flight and stops when the set drains, so the plugin
 * never scans the backend in the background. On start, {@link reconcile} asks the
 * server once "what's still processing?" to re-seed the set (resuming markers
 * after a restart); after that, polling is point-by-uuid for known nodes only.
 */
export class ProcessingTracker {
  private readonly plugin: PipGraphPlugin;
  private readonly inFlight = new Set<string>();
  private readonly attempts = new Map<string, number>();
  private looping = false;

  /** Fired whenever {@link inFlightCount} changes (drives the statusbar). */
  onChange: (() => void) | null = null;

  constructor(plugin: PipGraphPlugin) {
    this.plugin = plugin;
  }

  /** Notes whose processing the client is currently watching. */
  get inFlightCount(): number {
    return this.inFlight.size;
  }

  /** Start watching a note's processing job (no-op if already watched). */
  track(uuid: string): void {
    if (this.inFlight.has(uuid)) return;
    this.inFlight.add(uuid);
    this.attempts.set(uuid, 0);
    this.onChange?.();
    void this.ensureLooping();
  }

  /**
   * Re-seed the watch set from the server's in-flight status (called once on
   * plugin load). Resumes markers for jobs enqueued before a restart, without a
   * standing background scan — a single query, then point polling.
   */
  async reconcile(): Promise<void> {
    let episodics;
    try {
      episodics = await this.plugin.client.listEpisodicsByStatus(JOB_PROCESS_EXISTING);
    } catch {
      return; // backend unreachable on load — markers resume on a later reconcile
    }
    for (const ep of episodics) this.track(ep.uuid);
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
    // Snapshot — settle() mutates the set as we go.
    for (const uuid of [...this.inFlight]) {
      let episodic;
      try {
        episodic = await this.plugin.client.getEpisodicByUuid(uuid);
      } catch {
        continue; // transient backend hiccup — retry next sweep
      }

      if (episodic && isFailedStatus(episodic.status)) {
        new Notice(`PipGraph: processing failed for "${episodic.name}".`);
        this.settle(uuid);
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

  /** Drop a note from the watch set and refresh the UI. */
  private settle(uuid: string): void {
    this.inFlight.delete(uuid);
    this.attempts.delete(uuid);
    this.onChange?.();
    this.plugin.refreshTriagePanels();
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
