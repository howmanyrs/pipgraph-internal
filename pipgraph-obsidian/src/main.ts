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
import { DragToPlace } from "./drag/DragToPlace";

export default class PipGraphPlugin extends Plugin {
  settings!: PipGraphSettings;
  client!: PipGraphClient;
  folderMirror!: FolderMirror;
  dragToPlace!: DragToPlace;
  /** Folder last clicked in the explorer; the inspector tab reflects it. */
  lastInspectedFolderPath: string | null = null;

  async onload(): Promise<void> {
    await this.loadSettings();
    this.client = new PipGraphClient(this.settings);

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

    this.dragToPlace = new DragToPlace(this);
    this.dragToPlace.start();

    this.registerFolderClickInspector();
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
