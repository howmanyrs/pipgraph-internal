import { Plugin, WorkspaceLeaf } from "obsidian";
import { TriagePanelView, TRIAGE_VIEW_TYPE } from "./views/TriagePanelView";

export default class PipGraphPlugin extends Plugin {
  async onload(): Promise<void> {
    this.registerView(TRIAGE_VIEW_TYPE, (leaf) => new TriagePanelView(leaf));

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
