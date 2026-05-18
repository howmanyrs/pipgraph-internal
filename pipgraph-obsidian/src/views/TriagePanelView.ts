import { ItemView, WorkspaceLeaf } from "obsidian";

export const TRIAGE_VIEW_TYPE = "pipgraph-triage-panel";

export class TriagePanelView extends ItemView {
  constructor(leaf: WorkspaceLeaf) {
    super(leaf);
  }

  getViewType(): string {
    return TRIAGE_VIEW_TYPE;
  }

  getDisplayText(): string {
    return "PipGraph Triage";
  }

  getIcon(): string {
    return "inbox";
  }

  async onOpen(): Promise<void> {
    const container = this.containerEl.children[1];
    container.empty();
    container.addClass("pipgraph-triage-panel");
    container.createEl("h4", { text: "PipGraph Triage" });
    container.createEl("p", {
      text: "Coming soon.",
      cls: "pipgraph-triage-panel__placeholder",
    });
  }

  async onClose(): Promise<void> {
    // no-op
  }
}
