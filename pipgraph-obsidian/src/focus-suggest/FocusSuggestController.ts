import { Menu, TFolder, TFile, debounce, type Debouncer } from "obsidian";
import type { TAbstractFile } from "obsidian";
import type PipGraphPlugin from "../main";
import { TRIAGE_VIEW_TYPE } from "../views/TriagePanelView";
import { placeNoteInFolder } from "../drag/placeNote";
import { SuggestionEngine, type FolderScores } from "./SuggestionEngine";
import { FocusSuggestMode } from "./FocusSuggestMode";
import { FolderScoreDecorator } from "./FolderScoreDecorator";
import { buildGhostTree, type GhostNode } from "./GhostTree";

/** Which renderer paints the scores: ghost-tree (Phase 2) or real-tree badges (Phase 1). */
type Renderer = "ghost" | "badges";

/**
 * Orchestrates "Focus suggest" (M5b). One scoring engine, two renderers under a
 * single panel toggle:
 *  - toggle OFF → {@link FolderScoreDecorator} paints %-badges on the real tree.
 *  - toggle ON  → {@link FocusSuggestMode} replaces the real subtree with a
 *    ghost-tree of candidates.
 *
 * Active ⟺ a triage panel is open (either renderer); the toggle only chooses
 * *which* renderer. Closing the panel deactivates (explorer returns to pristine)
 * without flipping the persisted toggle (Q7). Flipping the toggle swaps the
 * renderer in place, reusing the already-computed scores (same target → no
 * re-fetch). The scoring target is the active editor note, falling back to the
 * last Inbox-tab selection; recomputed (debounced) on active-leaf-change.
 */
export class FocusSuggestController {
  private readonly engine: SuggestionEngine;
  private readonly ghost: FocusSuggestMode;
  private readonly decorator: FolderScoreDecorator;
  /** The renderer currently running, or null when no panel is open. */
  private renderer: Renderer | null = null;
  private targetFile: TFile | null = null;
  private scores: FolderScores | null = null;
  private loading = false;
  /** Monotonic guard so a slow scoring call can't overwrite a newer one. */
  private computeSeq = 0;
  private readonly recompute: Debouncer<[], void>;

  constructor(private readonly plugin: PipGraphPlugin) {
    this.engine = new SuggestionEngine(plugin);
    this.ghost = new FocusSuggestMode(plugin.app, plugin.settings);
    this.decorator = new FolderScoreDecorator(plugin.app);
    this.recompute = debounce(() => void this.compute(), 300, true);
  }

  start(): void {
    // Recompute as the active editor leaf changes (the "what am I reading" cue).
    this.plugin.registerEvent(
      this.plugin.app.workspace.on("active-leaf-change", () => {
        if (this.renderer) this.recompute();
      }),
    );
    // Real-mode candidate folders get a "Confirm placement here" item in the
    // native folder context menu (Q7 §3 — menu, not single-click, no misfires).
    this.plugin.registerEvent(
      this.plugin.app.workspace.on("file-menu", (menu, file) =>
        this.onFolderMenu(menu, file),
      ),
    );
    this.sync();
  }

  stop(): void {
    this.deactivate();
  }

  get enabled(): boolean {
    return this.plugin.settings.focusSuggest;
  }

  /** Flip the persisted toggle and swap the renderer to match. */
  async setEnabled(enabled: boolean): Promise<void> {
    this.plugin.settings.focusSuggest = enabled;
    await this.plugin.saveSettings();
    this.sync();
  }

  onPanelOpened(): void {
    this.sync();
  }

  onPanelClosed(): void {
    // onClose can fire before the leaf is fully detached — defer the recount.
    window.setTimeout(() => this.sync(), 0);
  }

  private panelOpen(): boolean {
    return (
      this.plugin.app.workspace.getLeavesOfType(TRIAGE_VIEW_TYPE).length > 0
    );
  }

  /** Reconcile the running renderer with (panel open?) + (toggle position). */
  private sync(): void {
    const desired: Renderer | null = this.panelOpen()
      ? this.enabled
        ? "ghost"
        : "badges"
      : null;
    if (desired === this.renderer) return;

    this.stopRenderer();
    this.renderer = desired;

    if (desired === null) {
      this.scores = null;
      this.targetFile = null;
      this.loading = false;
      return;
    }

    if (desired === "ghost") this.ghost.start();
    else this.decorator.start();

    // Reuse scores across a toggle flip (target is unchanged); first activation
    // has none yet, so compute.
    if (this.scores) this.render();
    else this.recompute();
  }

  private stopRenderer(): void {
    if (this.renderer === "ghost") this.ghost.stop();
    else if (this.renderer === "badges") this.decorator.stop();
  }

  private deactivate(): void {
    if (!this.renderer) return;
    this.stopRenderer();
    this.renderer = null;
    this.scores = null;
    this.targetFile = null;
    this.loading = false;
  }

  private resolveTarget(): TFile | null {
    const active = this.plugin.app.workspace.getActiveFile();
    if (active && active.extension === "md") return active;
    const fallback = this.plugin.lastInboxSelectionPath;
    if (fallback) {
      const f = this.plugin.app.vault.getAbstractFileByPath(fallback);
      if (f instanceof TFile) return f;
    }
    return null;
  }

  private async compute(): Promise<void> {
    if (!this.renderer) return;
    const target = this.resolveTarget();
    this.targetFile = target;
    const seq = ++this.computeSeq;
    this.loading = true;
    this.render();

    try {
      const scores = await this.engine.scoreFor(target?.path ?? null);
      if (seq !== this.computeSeq) return;
      this.scores = scores;
    } catch (err) {
      if (seq !== this.computeSeq) return;
      console.warn("[pipgraph] focus-suggest scoring failed", err);
      this.scores = null;
    } finally {
      if (seq === this.computeSeq) {
        this.loading = false;
        this.render();
      }
    }
  }

  private render(): void {
    if (this.renderer === "ghost") this.renderGhost();
    else if (this.renderer === "badges") this.renderBadges();
  }

  private renderGhost(): void {
    const tree = buildGhostTree(
      this.plugin.settings.rootFolder,
      this.scores ?? {
        episodicUuid: null,
        entities: [],
        scoreByUuid: new Map(),
      },
      this.targetFile,
      {
        onOpenNote: () => this.openTarget(),
        onConfirm: (node) => void this.confirm(node.path),
        onSkip: () => this.skip(),
        onDropNote: (node, sourcePath) => void this.dropNote(node, sourcePath),
        onSortChange: (mode) => void this.setSortMode(mode),
      },
      {
        loading: this.loading,
        processingPaths: this.plugin.processing.processingPaths,
        sortMode: this.plugin.settings.focusSuggestSort,
      },
    );
    this.ghost.setTree(tree);
  }

  /**
   * Flip the persisted ghost-tree sort order and repaint. Cheap — reuses the
   * current scores (no re-fetch); only the row order changes.
   */
  private async setSortMode(mode: "score" | "alpha"): Promise<void> {
    if (this.plugin.settings.focusSuggestSort === mode) return;
    this.plugin.settings.focusSuggestSort = mode;
    await this.plugin.saveSettings();
    if (this.renderer === "ghost") this.renderGhost();
  }

  /**
   * A processing job changed state (placed / settled / failed): repaint the
   * ghost tree so the in-flight note rows (spinning `⟳`) appear and disappear.
   * Cheap — reuses the current scores, no re-fetch. No-op unless the ghost
   * renderer is the one running.
   */
  refreshProcessing(): void {
    if (this.renderer === "ghost") this.renderGhost();
  }

  private renderBadges(): void {
    this.decorator.setScores(this.scoresByPath());
  }

  /** Folder path → score, from the entity list joined with the suggestion map. */
  private scoresByPath(): Map<string, number> {
    const map = new Map<string, number>();
    const s = this.scores;
    if (!s) return map;
    for (const entity of s.entities) {
      if (!entity.file_path) continue;
      const score = s.scoreByUuid.get(entity.uuid);
      if (score != null) map.set(entity.file_path, score);
    }
    return map;
  }

  /** Add "Confirm placement here" to a candidate folder's native context menu. */
  private onFolderMenu(menu: Menu, file: TAbstractFile): void {
    if (this.renderer !== "badges" || !this.targetFile) return;
    if (!(file instanceof TFolder)) return;
    const score = this.decorator.scoreForPath(file.path);
    if (score == null) return;

    const pct = Math.round(score * 100);
    const note = this.targetFile;
    menu.addItem((item) =>
      item
        .setTitle(`PipGraph: place "${note.basename}" here (${pct}%)`)
        .setIcon("check")
        .onClick(() => void this.confirm(file.path)),
    );
  }

  private openTarget(): void {
    if (this.targetFile) {
      void this.plugin.app.workspace.getLeaf(false).openFile(this.targetFile);
    }
  }

  /** Place the target note into a folder-entity (shared move+link), then re-score. */
  private async confirm(folderPath: string): Promise<void> {
    if (!this.targetFile) return;
    const ok = await placeNoteInFolder(this.plugin, this.targetFile, folderPath);
    // On success the note moved; re-score for the next target.
    if (ok) this.recompute();
  }

  /** Inbox note dropped onto a ghost folder: move+link, then re-score. */
  private async dropNote(node: GhostNode, sourcePath: string): Promise<void> {
    if (!node.entity) return;
    const file = this.plugin.app.vault.getAbstractFileByPath(sourcePath);
    if (!(file instanceof TFile)) return;
    const ok = await placeNoteInFolder(this.plugin, file, node.path);
    if (ok) this.recompute();
  }

  private skip(): void {
    // Drop the current note's scores but keep the tree structure visible.
    this.scores = this.scores
      ? { ...this.scores, scoreByUuid: new Map() }
      : null;
    this.targetFile = null;
    this.render();
  }
}
