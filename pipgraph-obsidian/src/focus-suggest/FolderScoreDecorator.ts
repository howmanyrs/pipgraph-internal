import type { App } from "obsidian";

/**
 * Real-mode renderer for M5b (Phase 1 / Step 3): the second renderer under the
 * "Focus suggest" toggle. While the toggle is OFF (and a triage panel is open),
 * candidate PARA folders get a match-% badge on their real explorer row — the
 * real tree stays intact, unlike the ghost-tree (Phase 2) which replaces it.
 *
 * Mechanism is the same observer-resilience pattern as folderDecoration: a
 * MutationObserver over the file-explorer DOM re-injects a `%` badge into
 * `.nav-folder-title[data-path]` rows as Obsidian renders them lazily (folders
 * mount/unmount on scroll and expand/collapse). The score→treatment mapping
 * mirrors the ghost-tree's (M5b score table).
 *
 * Visual-only and self-cleaning: {@link stop} removes every badge and class we
 * added, so the explorer is pristine when the toggle flips or the plugin
 * unloads. Context-menu actions on a candidate folder are owned by the
 * controller (it has the target note), wired via the native `file-menu` event.
 *
 * Unofficial-API caveat: relies on the internal `.nav-folder-title` markup.
 * Worst case — badges don't appear and real folders are untouched.
 */

const BADGE_CLASS = "pipgraph-folder-score";
const CANDIDATE_CLASS = "pipgraph-folder-candidate";

// Score → treatment (mirrors the ghost-tree thresholds). Below MIN: no badge.
const SCORE_MIN = 0.1;
const SCORE_HIGH = 0.7;
const SCORE_MID = 0.4;

export class FolderScoreDecorator {
  private scoreByPath: Map<string, number> = new Map();
  private observer: MutationObserver | null = null;
  private applyScheduled = false;

  constructor(private readonly app: App) {}

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
      .querySelectorAll(`.${BADGE_CLASS}`)
      .forEach((el) => el.remove());
    document
      .querySelectorAll(`.${CANDIDATE_CLASS}`)
      .forEach((el) => el.classList.remove(CANDIDATE_CLASS));
  }

  /** Replace the folder-path → score map and repaint. */
  setScores(scoreByPath: Map<string, number>): void {
    this.scoreByPath = scoreByPath;
    if (this.observer) this.observeExplorers();
    this.apply();
  }

  /** The score currently shown for a folder (≥ MIN), else undefined. */
  scoreForPath(path: string): number | undefined {
    const score = this.scoreByPath.get(path);
    return score != null && score >= SCORE_MIN ? score : undefined;
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
      // Clear any prior badge first so re-applies don't stack or go stale.
      el.querySelector(`:scope > .${BADGE_CLASS}`)?.remove();
      const path = el.getAttribute("data-path");
      const score = path != null ? this.scoreByPath.get(path) : undefined;
      const candidate = score != null && score >= SCORE_MIN;
      el.classList.toggle(CANDIDATE_CLASS, candidate);
      if (!candidate) return;

      const badge = el.createSpan({ cls: BADGE_CLASS });
      badge.setText(`${Math.round(score! * 100)}%`);
      badge.addClass(treatmentClass(score!));
    });
  }
}

function treatmentClass(score: number): string {
  if (score >= SCORE_HIGH) return `${BADGE_CLASS}--high`;
  if (score >= SCORE_MID) return `${BADGE_CLASS}--mid`;
  return `${BADGE_CLASS}--low`;
}
