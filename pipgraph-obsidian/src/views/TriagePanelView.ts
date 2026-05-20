import { App, ItemView, WorkspaceLeaf } from "obsidian";
import type PipGraphPlugin from "../main";

export const TRIAGE_VIEW_TYPE = "pipgraph-triage-panel";

type ObsidianSettingApi = {
  setting: {
    open(): void;
    openTabById(id: string): void;
  };
};

export class TriagePanelView extends ItemView {
  constructor(
    leaf: WorkspaceLeaf,
    private readonly plugin: PipGraphPlugin,
  ) {
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
    this.render();
  }

  async onClose(): Promise<void> {
    // no-op
  }

  refresh(): void {
    this.render();
  }

  private render(): void {
    const container = this.containerEl.children[1] as HTMLElement;
    container.empty();
    container.addClass("pipgraph-triage-panel");
    container.createEl("h4", { text: "PipGraph Triage" });

    if (!this.plugin.settings.initialized) {
      this.renderFirstRunBanner(container);
      return;
    }

    container.createEl("p", {
      text: "Inbox is empty.",
      cls: "pipgraph-triage-panel__placeholder",
    });
  }

  private renderFirstRunBanner(container: HTMLElement): void {
    const banner = container.createDiv({
      cls: "pipgraph-triage-panel__first-run",
    });
    banner.createEl("p", {
      text: "Configure your PipGraph root folder to start triaging notes.",
    });
    const link = banner.createEl("a", {
      text: "Configure root folder →",
      cls: "pipgraph-triage-panel__first-run-link",
      href: "#",
    });
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const api = this.app as App & ObsidianSettingApi;
      api.setting.open();
      api.setting.openTabById(this.plugin.manifest.id);
    });
  }
}
