import {
  App,
  ItemView,
  Notice,
  WorkspaceLeaf,
  setIcon,
} from "obsidian";
import type PipGraphPlugin from "../main";
import { getInboxPath } from "../settings/PipGraphSettings";
import { PipGraphApiError, type EpisodicNode, type ParaEntity } from "../backend";

export const TRIAGE_VIEW_TYPE = "pipgraph-triage-panel";

type ObsidianSettingApi = {
  setting: {
    open(): void;
    openTabById(id: string): void;
  };
};

type PanelTab = "inbox" | "inspector";

/**
 * The plugin's right-sidebar panel. Hosts tabbed sections; today:
 *  - Inbox — a list of notes physically under the vault Inbox folder. Mirrors
 *    the file-explorer Inbox on purpose: it's the seam where inbox-specific
 *    triage UI will grow later.
 *  - Entity Inspector — the Neo4j folder-entity behind a selected PARA folder
 *    (name, type, path, editable summary, recent episodics).
 *
 * The inspector follows folder clicks in the file-explorer (wired in main.ts via
 * `setInspectedFolder`), but a click only updates the inspector's *data* — it
 * never makes this panel or the inspector tab active. The user stays where they
 * are; switching to the inspector tab shows the most recently clicked folder.
 */
export class TriagePanelView extends ItemView {
  private activeTab: PanelTab = "inbox";
  private inspectedPath: string | null = null;
  /** Monotonic guard so a slow inspector fetch can't overwrite a newer one. */
  private renderSeq = 0;
  private panelContentEl: HTMLElement | null = null;
  private tabButtons: Partial<Record<PanelTab, HTMLElement>> = {};

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
    return "PipGraph";
  }

  getIcon(): string {
    return "inbox";
  }

  async onOpen(): Promise<void> {
    // Pick up the folder the user last clicked while the panel was closed.
    this.inspectedPath = this.plugin.lastInspectedFolderPath;
    this.render();
  }

  async onClose(): Promise<void> {
    this.panelContentEl = null;
    this.tabButtons = {};
  }

  /** Full re-render (settings changed, tab structure). */
  refresh(): void {
    this.render();
  }

  /**
   * Point the inspector at a folder. Updates the inspector tab's content but
   * does NOT activate this panel or switch the visible tab — see class doc.
   */
  setInspectedFolder(path: string): void {
    this.inspectedPath = path;
    if (this.activeTab === "inspector" && this.panelContentEl) {
      void this.renderContent();
    }
  }

  // --------------------------------------------------------------------------
  // Layout
  // --------------------------------------------------------------------------

  private render(): void {
    const root = this.containerEl.children[1] as HTMLElement;
    root.empty();
    root.addClass("pipgraph-panel");

    if (!this.plugin.settings.initialized) {
      root.createEl("h4", { text: "PipGraph" });
      this.renderFirstRunBanner(root);
      return;
    }

    this.renderTabBar(root);
    this.panelContentEl = root.createDiv({ cls: "pipgraph-panel__content" });
    void this.renderContent();
  }

  private renderTabBar(root: HTMLElement): void {
    const bar = root.createDiv({ cls: "pipgraph-panel__tabs" });
    this.tabButtons = {};
    const tabs: { id: PanelTab; label: string }[] = [
      { id: "inbox", label: "Inbox" },
      { id: "inspector", label: "Entity Inspector" },
    ];
    for (const tab of tabs) {
      const btn = bar.createEl("button", {
        text: tab.label,
        cls: "pipgraph-panel__tab",
      });
      btn.toggleClass("is-active", this.activeTab === tab.id);
      btn.addEventListener("click", () => this.setActiveTab(tab.id));
      this.tabButtons[tab.id] = btn;
    }
  }

  private setActiveTab(tab: PanelTab): void {
    if (this.activeTab === tab) return;
    this.activeTab = tab;
    for (const [id, btn] of Object.entries(this.tabButtons)) {
      btn?.toggleClass("is-active", id === tab);
    }
    void this.renderContent();
  }

  private async renderContent(): Promise<void> {
    const host = this.panelContentEl;
    if (!host) return;
    host.empty();
    if (this.activeTab === "inbox") {
      this.renderInbox(host);
    } else {
      await this.renderInspector(host);
    }
  }

  // --------------------------------------------------------------------------
  // Inbox tab
  // --------------------------------------------------------------------------

  private renderInbox(host: HTMLElement): void {
    const inboxPath = getInboxPath(this.plugin.settings);
    const prefix = `${inboxPath}/`;
    const files = this.plugin.app.vault
      .getMarkdownFiles()
      .filter((f) => f.path.startsWith(prefix))
      .sort((a, b) => b.stat.mtime - a.stat.mtime);

    if (files.length === 0) {
      host.createEl("p", {
        text: "Inbox is empty.",
        cls: "pipgraph-panel__placeholder",
      });
      return;
    }

    const list = host.createDiv({ cls: "pipgraph-inbox-list" });
    for (const file of files) {
      const row = list.createDiv({ cls: "pipgraph-inbox-row" });
      row.createSpan({ cls: "pipgraph-inbox-row__title", text: file.basename });
      const rel = file.parent?.path.slice(inboxPath.length).replace(/^\//, "");
      if (rel) {
        row.createSpan({ cls: "pipgraph-inbox-row__path", text: rel });
      }
      row.addEventListener("click", () => {
        void this.plugin.app.workspace.getLeaf(false).openFile(file);
      });
    }
  }

  // --------------------------------------------------------------------------
  // Entity Inspector tab
  // --------------------------------------------------------------------------

  private async renderInspector(host: HTMLElement): Promise<void> {
    const path = this.inspectedPath;
    if (!path) {
      host.createEl("p", {
        text: "Click a folder under your PipGraph root to inspect its graph node here.",
        cls: "pipgraph-panel__placeholder",
      });
      return;
    }

    const seq = ++this.renderSeq;
    host.createEl("p", {
      text: "Loading…",
      cls: "pipgraph-panel__placeholder",
    });

    let entity: ParaEntity | undefined;
    try {
      const matches = await this.plugin.client.listParaEntities({ filePath: path });
      entity = matches[0];
    } catch (err) {
      if (seq !== this.renderSeq) return;
      host.empty();
      this.renderError(host, err);
      return;
    }

    if (seq !== this.renderSeq) return;
    host.empty();

    if (!entity) {
      host.createEl("p", {
        text: `No graph node for "${path}" yet.`,
        cls: "pipgraph-panel__placeholder",
      });
      host.createEl("p", {
        text: "Mirror it via right-click → “PipGraph: Sync folder to backend”, or enable auto-mirror in settings.",
        cls: "pipgraph-panel__hint",
      });
      return;
    }

    this.renderEntityCard(host, entity);
  }

  private renderEntityCard(host: HTMLElement, entity: ParaEntity): void {
    const card = host.createDiv({ cls: "pipgraph-inspector-card" });

    // Header: 📁 name [type]
    const header = card.createDiv({ cls: "pipgraph-inspector-card__header" });
    const icon = header.createSpan({ cls: "pipgraph-inspector-card__icon" });
    setIcon(icon, "folder");
    header.createSpan({
      cls: "pipgraph-inspector-card__name",
      text: entity.name,
    });
    header.createSpan({
      cls: "pipgraph-inspector-card__type",
      text: entity.para_type,
    });

    // Read-only fields.
    this.renderField(card, "Path", entity.file_path ?? "—");
    if (entity.created_at) {
      this.renderField(card, "Created", entity.created_at.slice(0, 10));
    }

    // Editable summary.
    card.createEl("label", {
      cls: "pipgraph-inspector-card__field-label",
      text: "Summary",
    });
    const textarea = card.createEl("textarea", {
      cls: "pipgraph-inspector-card__summary",
    });
    textarea.value = entity.summary ?? "";
    textarea.placeholder =
      "No summary yet — describe this area so the backend can match new notes to it.";

    const actions = card.createDiv({ cls: "pipgraph-inspector-card__actions" });
    const saveBtn = actions.createEl("button", {
      text: "Save summary",
      cls: "mod-cta",
    });
    saveBtn.addEventListener("click", () => {
      void this.saveSummary(entity.uuid, textarea.value, saveBtn);
    });

    // Recent episodics.
    void this.renderRecentEpisodics(card, entity.uuid);
  }

  private async saveSummary(
    uuid: string,
    summary: string,
    button: HTMLButtonElement,
  ): Promise<void> {
    button.disabled = true;
    button.setText("Saving…");
    try {
      await this.plugin.client.updateParaEntity(uuid, { summary });
      // Clear the "empty summary" folder marker if it now has text.
      await this.plugin.folderMirror?.refreshDecorations();
      new Notice("PipGraph: summary saved.");
      // Re-pull so the card (and recent episodics) reflect the saved state.
      await this.renderContent();
    } catch (err) {
      console.warn("[pipgraph] saveSummary failed", err);
      new Notice("PipGraph: failed to save summary (see console).");
      button.disabled = false;
      button.setText("Save summary");
    }
  }

  private async renderRecentEpisodics(
    card: HTMLElement,
    entityUuid: string,
  ): Promise<void> {
    const seq = this.renderSeq;
    let episodics: EpisodicNode[];
    try {
      episodics = await this.plugin.client.getEpisodicsByEntity(entityUuid, 5);
    } catch {
      return; // Non-fatal: just omit the section.
    }
    if (seq !== this.renderSeq || !card.isConnected) return;
    if (episodics.length === 0) return;

    card.createEl("div", {
      cls: "pipgraph-inspector-card__field-label",
      text: `Recent notes (${episodics.length})`,
    });
    const list = card.createDiv({ cls: "pipgraph-episodic-list" });
    for (const ep of episodics) {
      const row = list.createDiv({ cls: "pipgraph-episodic-row" });
      const date = ep.valid_at ?? ep.created_at;
      if (date) {
        row.createSpan({
          cls: "pipgraph-episodic-row__date",
          text: date.slice(0, 10),
        });
      }
      row.createSpan({ cls: "pipgraph-episodic-row__name", text: ep.name });
    }
  }

  private renderField(card: HTMLElement, label: string, value: string): void {
    const field = card.createDiv({ cls: "pipgraph-inspector-card__field" });
    field.createSpan({
      cls: "pipgraph-inspector-card__field-label",
      text: label,
    });
    field.createSpan({
      cls: "pipgraph-inspector-card__field-value",
      text: value,
    });
  }

  private renderError(host: HTMLElement, err: unknown): void {
    const offline =
      err instanceof PipGraphApiError &&
      (err.kind === "network" || err.kind === "timeout");
    host.createEl("p", {
      cls: "pipgraph-panel__placeholder",
      text: offline
        ? "Backend unreachable. Check that it's running and the URL in settings."
        : "Couldn't load this folder's node (see console).",
    });
    if (!offline) console.warn("[pipgraph] inspector load failed", err);
  }

  // --------------------------------------------------------------------------
  // First run
  // --------------------------------------------------------------------------

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
