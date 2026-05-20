import { Plugin, WorkspaceLeaf } from "obsidian";
import { TriagePanelView, TRIAGE_VIEW_TYPE } from "./views/TriagePanelView";
import {
  DEFAULT_SETTINGS,
  PipGraphSettings,
  hasNonDefaultValues,
} from "./settings/PipGraphSettings";
import { PipGraphSettingTab } from "./settings/PipGraphSettingTab";

export default class PipGraphPlugin extends Plugin {
  settings!: PipGraphSettings;

  async onload(): Promise<void> {
    await this.loadSettings();

    this.registerView(
      TRIAGE_VIEW_TYPE,
      (leaf) => new TriagePanelView(leaf, this),
    );

    this.addSettingTab(new PipGraphSettingTab(this.app, this));

    this.addRibbonIcon("inbox", "Open PipGraph triage panel", () => {
      void this.activateTriagePanel();
    });

    this.addCommand({
      id: "open-triage-panel",
      name: "Open triage panel",
      callback: () => {
        void this.activateTriagePanel();
      },
    });
  }

  onunload(): void {
    this.app.workspace.detachLeavesOfType(TRIAGE_VIEW_TYPE);
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
    this.notifyTriageViews();
  }

  private notifyTriageViews(): void {
    this.app.workspace.getLeavesOfType(TRIAGE_VIEW_TYPE).forEach((leaf) => {
      const view = leaf.view;
      if (view instanceof TriagePanelView) {
        view.refresh();
      }
    });
  }

  private async activateTriagePanel(): Promise<void> {
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
