/**
 * File-explorer decoration for PARA folder-entities with an empty summary.
 *
 * A freshly mirrored folder gets a PARA Entity with no summary yet — it
 * "describes nothing". This marks such folders in the explorer so the user
 * can see which nodes still need meaning (filled later via inspector/S8 or
 * graphiti summarisation when notes are processed into them).
 *
 * Mechanism: a MutationObserver over the file-explorer DOM re-applies a CSS
 * class to `.nav-folder-title[data-path]` rows as Obsidian renders them lazily
 * (folders mount/unmount on scroll and expand/collapse). This is the first
 * folder-level decoration in the plugin; the same pattern is reused later for
 * tree-as-decide-tool badges.
 *
 * Unofficial-API caveat: relies on the internal `.nav-folder-title` markup.
 * Additive and self-cleaning — `stop()` removes every class we added, so the
 * vault is untouched when the plugin is disabled.
 */

import type { App } from "obsidian";

const MARK_CLASS = "pipgraph-empty-summary";

export class FolderDecorator {
  private readonly app: App;
  private markedPaths: Set<string> = new Set();
  private observer: MutationObserver | null = null;
  private applyScheduled = false;

  constructor(app: App) {
    this.app = app;
  }

  start(): void {
    if (this.observer) return;
    this.observer = new MutationObserver(() => this.scheduleApply());
    this.observeExplorers();
    this.apply();
  }

  stop(): void {
    this.observer?.disconnect();
    this.observer = null;
    document
      .querySelectorAll(`.${MARK_CLASS}`)
      .forEach((el) => el.classList.remove(MARK_CLASS));
  }

  /** Replace the set of folder paths that should carry the marker. */
  setMarkedPaths(paths: Set<string>): void {
    this.markedPaths = paths;
    // (Re)attach in case the explorer leaf was created after start().
    if (this.observer) this.observeExplorers();
    this.apply();
  }

  private observeExplorers(): void {
    if (!this.observer) return;
    const leaves = this.app.workspace.getLeavesOfType("file-explorer");
    for (const leaf of leaves) {
      this.observer.observe(leaf.view.containerEl, {
        childList: true,
        subtree: true,
      });
    }
  }

  private scheduleApply(): void {
    if (this.applyScheduled) return;
    this.applyScheduled = true;
    requestAnimationFrame(() => {
      this.applyScheduled = false;
      this.apply();
    });
  }

  private apply(): void {
    const titles = document.querySelectorAll<HTMLElement>(
      ".nav-folder-title[data-path]",
    );
    titles.forEach((el) => {
      const path = el.getAttribute("data-path");
      const shouldMark = path !== null && this.markedPaths.has(path);
      el.classList.toggle(MARK_CLASS, shouldMark);
    });
  }
}
