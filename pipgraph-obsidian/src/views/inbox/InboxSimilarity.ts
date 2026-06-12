/**
 * Seam for "highlight similar Inbox notes" (inbox-tuning 01, §3).
 *
 * The Inbox tab can dim-highlight notes that are *similar* to the currently
 * selected one (toggle A), and optionally auto-check them into the batch
 * (toggle B). Computing similarity needs a backend that ranks notes against a
 * note — which does not exist yet. So this increment ships only the seam: a
 * provider interface plus a no-op implementation. A future
 * `BackendSimilarityProvider` (new endpoint) is a drop-in replacement for the
 * `plugin.inboxSimilarity` field — the plugin is "a client, not a brain".
 */

/** A note found similar to the selection. `score` is an optional 0..1 strength. */
export interface SimilarHit {
  path: string;
  score?: number;
}

export interface InboxSimilarityProvider {
  /**
   * Which of `candidates` are similar to `selectedPath`. Async — a future
   * backend call slots in here without touching the call sites.
   */
  similarTo(selectedPath: string, candidates: string[]): Promise<SimilarHit[]>;
}

/** The only implementation in this increment: never finds anything similar. */
export class NoopSimilarityProvider implements InboxSimilarityProvider {
  async similarTo(): Promise<SimilarHit[]> {
    return [];
  }
}
