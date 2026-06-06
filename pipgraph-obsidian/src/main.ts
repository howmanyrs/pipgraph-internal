import { Plugin, WorkspaceLeaf } from "obsidian";
import { TriagePanelView, TRIAGE_VIEW_TYPE } from "./views/TriagePanelView";
import {
  DEFAULT_SETTINGS,
  PipGraphSettings,
  hasNonDefaultValues,
  isManagedFolderPath,
} from "./settings/PipGraphSettings";
import { PipGraphSettingTab } from "./settings/PipGraphSettingTab";
import { PipGraphClient } from "./backend";
import { registerCommands } from "./commands/register";
import { FolderMirror } from "./folder-mirror/FolderMirror";
import { FileDecorator } from "./folder-mirror/fileDecoration";
import { DragToPlace } from "./drag/DragToPlace";
import { CaptureOutbox } from "./outbox/CaptureOutbox";
import { ProcessingTracker } from "./outbox/ProcessingTracker";

export default class PipGraphPlugin extends Plugin {
  settings!: PipGraphSettings;
  client!: PipGraphClient;
  outbox!: CaptureOutbox;
  processing!: ProcessingTracker;
  folderMirror!: FolderMirror;
  fileDecorator!: FileDecorator;
  dragToPlace!: DragToPlace;
  /** Statusbar counter for in-flight capture + processing work (hidden when none). */
  private outboxStatusEl: HTMLElement | null = null;
  /** Folder last clicked in the explorer; the inspector tab reflects it. */
  lastInspectedFolderPath: string | null = null;

  async onload(): Promise<void> {
    await this.loadSettings();
    this.client = new PipGraphClient(this.settings);
    this.outbox = new CaptureOutbox(this);
    this.processing = new ProcessingTracker(this);
    this.fileDecorator = new FileDecorator(this.app);
    this.outboxStatusEl = this.addStatusBarItem();
    this.outbox.onChange = () => this.renderOutboxStatus();
    this.processing.onChange = () => this.refreshProcessingUi();
    this.renderOutboxStatus();

    this.registerView(
      TRIAGE_VIEW_TYPE,
      (leaf) => new TriagePanelView(leaf, this),
    );

    this.addSettingTab(new PipGraphSettingTab(this.app, this));

    this.addRibbonIcon("inbox", "Open PipGraph triage panel", () => {
      void this.activateTriagePanel();
    });

    registerCommands(this);

    this.folderMirror = new FolderMirror(this);
    this.folderMirror.start();

    this.fileDecorator.start();

    this.dragToPlace = new DragToPlace(this);
    this.dragToPlace.start();

    this.registerFolderClickInspector();

    // Resume delivery of any capture records a previous session left pending
    // (e.g. Obsidian or the backend died mid-flight). Fire-and-forget.
    void this.outbox.reconcile();
    // Re-seed the processing watch set from the server's in-flight status, so
    // markers resume for notes whose heavy job was enqueued before a restart.
    void this.processing.reconcile();
  }

  /**
   * Follow folder clicks in the file-explorer so the Entity Inspector tab
   * reflects the clicked folder. Uses the explorer's DOM (`.nav-folder-title`,
   * an unofficial-but-stable hook, same surface folderDecoration relies on)
   * because Obsidian fires no public event for folder selection.
   *
   * Deliberately non-intrusive: it only updates the inspector's *data*. It does
   * not open the panel, reveal its leaf, or switch the active tab — clicking a
   * folder must not yank the user out of whatever they were doing.
   */
  private registerFolderClickInspector(): void {
    this.registerDomEvent(document, "click", (evt) => {
      const target = evt.target as HTMLElement | null;
      const titleEl = target?.closest?.(
        ".nav-folder-title[data-path]",
      ) as HTMLElement | null;
      if (!titleEl) return;
      const path = titleEl.getAttribute("data-path");
      if (!path || !isManagedFolderPath(this.settings, path)) return;
      this.inspectFolderInPanel(path);
    });
  }

  private inspectFolderInPanel(path: string): void {
    this.lastInspectedFolderPath = path;
    this.app.workspace.getLeavesOfType(TRIAGE_VIEW_TYPE).forEach((leaf) => {
      const view = leaf.view;
      if (view instanceof TriagePanelView) {
        view.setInspectedFolder(path);
      }
    });
  }

  onunload(): void {
    this.app.workspace.detachLeavesOfType(TRIAGE_VIEW_TYPE);
    this.folderMirror?.stop();
    this.fileDecorator?.stop();
  }

  async loadSettings(): Promise<void> {
    const raw = (await this.loadData()) as Partial<PipGraphSettings> | null;
    this.settings = { ...DEFAULT_SETTINGS, ...(raw ?? {}) };
  }

  async saveSettings(): Promise<void> {
    if (!this.settings.initialized && hasNonDefaultValues(this.settings)) {
      this.settings.initialized = true;
    }
    await this.saveData(this.settings);
    // Rebuild the client so a new backendUrl / apiKey takes effect immediately.
    this.client = new PipGraphClient(this.settings);
    this.refreshTriagePanels();
  }

  /**
   * Reflect in-flight work in the statusbar: pending captures (hidden pending
   * files) + notes whose heavy processing job is running. Both are otherwise
   * invisible, so this is the ambient sign that work is in flight; we hide the
   * item entirely (empty text) when nothing is in flight.
   */
  private renderOutboxStatus(): void {
    if (!this.outboxStatusEl) return;
    const n = this.outbox.pendingCount + this.processing.inFlightCount;
    this.outboxStatusEl.setText(n > 0 ? `PipGraph: ${n} processing…` : "");
  }

  /**
   * Processing state changed: refresh the statusbar counter and re-paint the
   * file-explorer markers (in-flight / failed) from the tracker's path sets.
   */
  private refreshProcessingUi(): void {
    this.renderOutboxStatus();
    this.fileDecorator.setMarkedPaths(
      this.processing.processingPaths,
      this.processing.failedPaths,
    );
  }

  /** Re-render every open triage panel (settings changed, a note was placed). */
  refreshTriagePanels(): void {
    this.app.workspace.getLeavesOfType(TRIAGE_VIEW_TYPE).forEach((leaf) => {
      const view = leaf.view;
      if (view instanceof TriagePanelView) {
        view.refresh();
      }
    });
  }

  async activateTriagePanel(): Promise<void> {
    const { workspace } = this.app;
    const existing = workspace.getLeavesOfType(TRIAGE_VIEW_TYPE);

    let leaf: WorkspaceLeaf | null;
    if (existing.length > 0) {
      leaf = existing[0];
    } else {
      leaf = workspace.getRightLeaf(false);
      if (leaf) {
        await leaf.setViewState({ type: TRIAGE_VIEW_TYPE, active: true });
      }
    }

    if (leaf) {
      workspace.revealLeaf(leaf);
    }
  }
}
