/**
 * File-explorer decoration for notes whose heavy processing job is in flight
 * or has failed (process-queue P3).
 *
 * The file-level twin of {@link FolderDecorator}: a MutationObserver over the
 * file-explorer DOM re-applies a CSS class to `.nav-file-title[data-path]` rows
 * as Obsidian renders them lazily (files mount/unmount on scroll and
 * expand/collapse). Two mutually-exclusive markers — `pipgraph-processing`
 * (a spinner-ish glyph) and `pipgraph-failed` (a warning glyph) — driven by the
 * path sets the {@link ProcessingTracker} exposes; `failed` wins when a path is
 * somehow in both.
 *
 * Source of truth is the in-memory tracker (re-seeded from the backend on load),
 * not frontmatter — so this stays purely a view layer and writes nothing to the
 * vault (process-queue P3 decision: tracker-driven, frontmatter deferred).
 *
 * Unofficial-API caveat: relies on the internal `.nav-file-title` markup.
 * Additive and self-cleaning — `stop()` removes every class we added, so the
 * vault is untouched when the plugin is disabled.
 */

import type { App } from "obsidian";

const PROCESSING_CLASS = "pipgraph-processing";
const FAILED_CLASS = "pipgraph-failed";

export class FileDecorator {
  private readonly app: App;
  private processingPaths: Set<string> = new Set();
  private failedPaths: Set<string> = new Set();
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
      .querySelectorAll(`.${PROCESSING_CLASS}, .${FAILED_CLASS}`)
      .forEach((el) => el.classList.remove(PROCESSING_CLASS, FAILED_CLASS));
  }

  /** Replace the path sets that should carry each marker. */
  setMarkedPaths(processing: Set<string>, failed: Set<string>): void {
    this.processingPaths = processing;
    this.failedPaths = failed;
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
      ".nav-file-title[data-path]",
    );
    titles.forEach((el) => {
      const path = el.getAttribute("data-path");
      const failed = path !== null && this.failedPaths.has(path);
      const processing = !failed && path !== null && this.processingPaths.has(path);
      el.classList.toggle(FAILED_CLASS, failed);
      el.classList.toggle(PROCESSING_CLASS, processing);
    });
  }
}
