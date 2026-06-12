/**
 * Seam for Inbox sorting + a future "Semantic" order (inbox-tuning 01, §3b).
 *
 * Today the Inbox sorts by `ctime` ("Date added") with notes grouped by day.
 * A future increment (plan 02 — semantic pre-extraction) will pre-extract a
 * note's topic/tags during naming and store them in frontmatter, enabling a
 * "Semantic" sort/group. This increment ships only the seam: the sort type, the
 * semantic shape we'll accumulate, a provider interface, and a no-op
 * implementation. A future `BackendSemanticProvider` (or a frontmatter reader)
 * is a drop-in replacement for the `plugin.inboxSemantic` field.
 */

export type InboxSort = "date" | "semantic";

/** What plan 02 will accumulate per note (in frontmatter, then maybe the DB). */
export interface SemanticInfo {
  topic?: string;
  tags?: string[];
}

export interface InboxSemanticProvider {
  /**
   * Semantic info for the given paths. An empty map means "no data yet" — the
   * Inbox then falls back to the `date` order and the "Semantic" sort option
   * stays disabled.
   */
  semanticsFor(paths: string[]): Map<string, SemanticInfo>;
}

/** The only implementation in this increment: always returns no data. */
export class NoopSemanticProvider implements InboxSemanticProvider {
  semanticsFor(): Map<string, SemanticInfo> {
    return new Map();
  }
}
