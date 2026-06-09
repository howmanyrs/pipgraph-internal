import type { App } from "obsidian";
import type { PipGraphSettings } from "../settings/PipGraphSettings";

/**
 * Low-level DOM host for the ghost-tree (M5b Phase 2). Two jobs while active:
 *  1. Hide the real subtree under root — the root folder and everything beneath
 *     it (including the real Inbox folder; the ghost tree redraws an Inbox row
 *     at its top, and it also stays reachable via the triage panel's Inbox tab,
 *     Q7 §4 revised 2026-06-07). Everything outside root stays visible.
 *     Implemented by tagging each real row wrapper whose `data-path` is hidden;
 *     a body class hides them via CSS.
 *  2. Inject a single ghost-tree container into the file-explorer.
 *
 * A MutationObserver re-applies both as Obsidian re-renders the explorer (lazy
 * mount on scroll, expand/collapse) — the same resilience pattern as
 * folderDecoration. Visual-only: it never touches files or the graph, and
 * {@link stop} restores the explorer to pristine.
 *
 * Unofficial-API caveat: relies on `.nav-folder-title` / `.nav-files-container`
 * internal markup. Worst case — the ghost doesn't appear and real files are
 * untouched.
 */

const BODY_CLASS = "pipgraph-focus-suggest";
const HIDDEN_CLASS = "pipgraph-fs-hidden";
const HOST_CLASS = "pipgraph-ghost-tree-host";
// The folder/file row wrapper. Obsidian's markup drifts between versions —
// older builds use `.nav-folder`/`.nav-file`, newer ones wrap rows in
// `.tree-item`. closest() returns the nearest matching ancestor, so listing all
// three is robust whichever the running version uses.
const WRAPPER_SELECTOR = ".nav-folder, .nav-file, .tree-item";

export class FocusSuggestMode {
  private observer: MutationObserver | null = null;
  private applyScheduled = false;
  private treeEl: HTMLElement | null = null;
  private hostEl: HTMLElement | null = null;

  constructor(
    private readonly app: App,
    private readonly settings: PipGraphSettings,
  ) {}

  get running(): boolean {
    return this.observer !== null;
  }

  start(): void {
    if (this.observer) return;
    document.body.addClass(BODY_CLASS);
    this.observer = new MutationObserver(() => this.scheduleApply());
    this.observeExplorers();
    this.apply();
  }

  stop(): void {
    this.observer?.disconnect();
    this.observer = null;
    document.body.removeClass(BODY_CLASS);
    document
      .querySelectorAll(`.${HIDDEN_CLASS}`)
      .forEach((el) => el.classList.remove(HIDDEN_CLASS));
    this.hostEl?.remove();
    this.hostEl = null;
    this.treeEl = null;
  }

  /** Swap the ghost-tree content; the host re-inserts it as the explorer churns. */
  setTree(treeEl: HTMLElement): void {
    this.treeEl = treeEl;
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
    if (!this.observer) return;
    // Re-attach in case the explorer leaf was created after start().
    this.observeExplorers();

    const titles = document.querySelectorAll<HTMLElement>(
      ".nav-folder-title[data-path], .nav-file-title[data-path]",
    );
    titles.forEach((el) => {
      // Hide the whole row wrapper (folder + its children). Hiding the root
      // wrapper alone covers everything under it; tagging each matched row too
      // is belt-and-suspenders for partial DOM re-renders.
      const wrapper = el.closest<HTMLElement>(WRAPPER_SELECTOR) ?? el;
      const path = el.getAttribute("data-path");
      wrapper.classList.toggle(
        HIDDEN_CLASS,
        path !== null && this.shouldHide(path),
      );
    });

    this.ensureHost();
  }

  /**
   * Real path hidden ⟺ it is the root folder or anything under it — including
   * the Inbox subtree. The ghost tree redraws an Inbox row at its top (so the
   * inbox is never lost from view), and it stays reachable via the triage
   * panel's Inbox tab (the drag source); the real explorer row is therefore
   * redundant (Q7 §4, revised 2026-06-07). Everything outside root stays visible.
   */
  private shouldHide(path: string): boolean {
    const root = this.settings.rootFolder.replace(/\/+$/, "");
    return path === root || path.startsWith(`${root}/`);
  }

  private ensureHost(): void {
    if (!this.treeEl) return;
    const explorer = this.app.workspace.getLeavesOfType("file-explorer")[0];
    const mount = explorer?.view.containerEl.querySelector<HTMLElement>(
      ".nav-files-container",
    );
    if (!mount) return;

    if (!this.hostEl) this.hostEl = createDiv({ cls: HOST_CLASS });
    if (this.hostEl.firstChild !== this.treeEl) {
      this.hostEl.empty();
      this.hostEl.appendChild(this.treeEl);
    }
    // Mount the ghost-tree at the very top of the explorer, above whatever real
    // folders stay visible (outside root). `prepend` is idempotent — it both
    // (re-)attaches a detached host and moves it back to first if Obsidian
    // inserted something ahead of it on a re-render.
    if (
      this.hostEl.parentElement !== mount ||
      mount.firstElementChild !== this.hostEl
    ) {
      mount.prepend(this.hostEl);
    }
  }
}
