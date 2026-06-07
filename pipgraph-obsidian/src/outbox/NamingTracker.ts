import type PipGraphPlugin from "../main";
import { JOB_GENERATE_NAME, failedStatus } from "../backend";

/**
 * Naming tracker (inbox-in-process, Model 2).
 *
 * A sibling of {@link ProcessingTracker}, but for **materialised fallback-named
 * notes** — Episodics that carry `status="failed:generate_episode_name"` *and* a
 * `file_path`. The backend's naming job no longer masks an LLM failure: on a
 * fallback it stores a real (text-derived) name but keeps the failed status, so
 * the note materialises into the Inbox like any other while still being flagged.
 *
 * This tracker holds just the uuid↔path bookkeeping that drives:
 *  - the file-explorer `❗` marker (via {@link FileDecorator}'s third path set), and
 *  - the "Regenerate name with LLM" context-menu item (visibility + target).
 *
 * Unlike {@link ProcessingTracker} there is **no poll loop**: a fallback note is
 * a terminal-until-acted-on state, not in-flight work. It is seeded once on load
 * (`reconcile`) and mutated point-by-point as captures materialise
 * (`markFallback`) or are regenerated/placed (`clear`).
 *
 * Not counted in the statusbar — a fallback name is not "processing".
 */
export class NamingTracker {
  private readonly plugin: PipGraphPlugin;
  /** uuid → file_path for fallback-named materialised notes. */
  private readonly fallback = new Map<string, string>();
  /**
   * File paths whose naming job is *being re-run right now* ("Regenerate name
   * with LLM"). Same server queue as a fresh capture — this set just drives the
   * in-flight `⟳` so a regenerate is as visible as an add (it overrides the `❗`
   * while it runs). Keyed by path because the regen command works from a TFile.
   */
  private readonly regenerating = new Set<string>();

  /** Fired whenever the tracked set changes (drives the `❗` decoration). */
  onChange: (() => void) | null = null;

  constructor(plugin: PipGraphPlugin) {
    this.plugin = plugin;
  }

  /** File paths carrying the fallback-name `❗` marker (FileDecorator). */
  get paths(): Set<string> {
    return new Set(this.fallback.values());
  }

  /** File paths showing the in-flight `⟳` because a regenerate is running. */
  get regeneratingPaths(): Set<string> {
    return new Set(this.regenerating);
  }

  /** How many regenerate jobs are in flight (feeds the statusbar counter). */
  get regeneratingCount(): number {
    return this.regenerating.size;
  }

  /** Is this path's naming job being re-run? (panel row shows `⟳` not `❗`). */
  isRegenerating(path: string): boolean {
    return this.regenerating.has(path);
  }

  /** Mark/unmark a path as having its naming job in flight. */
  markRegenerating(path: string): void {
    if (!this.regenerating.has(path)) {
      this.regenerating.add(path);
      this.onChange?.();
    }
  }

  unmarkRegenerating(path: string): void {
    if (this.regenerating.delete(path)) this.onChange?.();
  }

  /**
   * The fallback uuid whose tracked path matches `path`, or undefined. Backs the
   * "Regenerate name with LLM" menu — both its visibility (defined ⇒ show) and
   * the regenerate target. In-memory only, no backend round-trip.
   */
  uuidForPath(path: string): string | undefined {
    for (const [uuid, p] of this.fallback) {
      if (p === path) return uuid;
    }
    return undefined;
  }

  /** Flag a materialised note as fallback-named (or update its path). */
  markFallback(uuid: string, path: string): void {
    if (this.fallback.get(uuid) === path) return;
    this.fallback.set(uuid, path);
    this.onChange?.();
  }

  /**
   * Drop a uuid from the fallback set — its name was regenerated, or it was
   * placed/processed (which overwrites the status). No-op if not tracked.
   */
  clear(uuid: string): void {
    if (this.fallback.delete(uuid)) this.onChange?.();
  }

  /**
   * Re-seed the fallback set from server status (called once on plugin load).
   * Only nodes with a `file_path` belong here — a `failed:generate_episode_name`
   * node *without* a path is still pre-materialisation and owned by the capture
   * outbox, not this tracker.
   */
  async reconcile(): Promise<void> {
    let changed = false;
    try {
      const fallbacks = await this.plugin.client.listEpisodicsByStatus(
        failedStatus(JOB_GENERATE_NAME),
      );
      for (const ep of fallbacks) {
        if (!ep.file_path) continue; // still pending → outbox owns it
        if (this.fallback.get(ep.uuid) !== ep.file_path) {
          this.fallback.set(ep.uuid, ep.file_path);
          changed = true;
        }
      }
    } catch {
      // backend unreachable on load — markers resume on a later reconcile
    }
    if (changed) this.onChange?.();
  }
}
