import {
  App,
  ItemView,
  Menu,
  Notice,
  WorkspaceLeaf,
  setIcon,
} from "obsidian";
import type PipGraphPlugin from "../main";
import type { TFile } from "obsidian";
import type { CaptureRecord } from "../outbox/CaptureOutbox";
import { getInboxPath } from "../settings/PipGraphSettings";
import { PIPGRAPH_DRAG_MIME } from "../drag/DragToPlace";
import { regenerateName } from "../commands/register";
import { PipGraphApiError, type EpisodicNode, type ParaEntity } from "../backend";
import type { SimilarHit } from "./inbox/InboxSimilarity";
import type { InboxSort } from "./inbox/InboxSemantic";

export const TRIAGE_VIEW_TYPE = "pipgraph-triage-panel";

/**
 * Data backing one rich Inbox row (inbox-tuning 01). The first line shows the
 * title + markers + checkbox; the second (small) line the added date + a body
 * snippet. The snippet is lazy (`null` until {@link TriagePanelView.fillSnippet}
 * loads the body), so the row paints synchronously without reading every file.
 */
interface InboxItemData {
  file: TFile;
  added: string; // formatDay(file.stat.ctime) — "YYYY-MM-DD" (D3)
  fallbackUuid: string | null; // ❗ (NamingTracker) — auto-name failed
  regenerating: boolean; // ⟳ — naming job re-running
}

/** Local day key / display date — "YYYY-MM-DD" from an epoch-ms timestamp (D3). */
function formatDay(ms: number): string {
  const d = new Date(ms);
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${month}-${day}`;
}

/**
 * First readable line of a note's body for the Inbox snippet (D4): strip a
 * leading YAML frontmatter block and markdown heading lines, take the first
 * non-empty line, and trim to ~120 chars. Returns null when there's nothing.
 */
function extractSnippet(content: string): string | null {
  let text = content;
  if (text.startsWith("---")) {
    const close = text.indexOf("\n---", 3);
    if (close !== -1) {
      const nl = text.indexOf("\n", close + 1);
      text = nl !== -1 ? text.slice(nl + 1) : "";
    }
  }
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    return line.length > 120 ? `${line.slice(0, 120).trimEnd()}…` : line;
  }
  return null;
}

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
  /** Lazy body-snippet cache, invalidated per file by mtime (D4). */
  private snippetCache = new Map<string, { mtime: number; snippet: string | null }>();
  /** Monotonic guard so a slow similarity call can't paint a stale selection. */
  private similarSeq = 0;

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
    // Adopt an already-open inbox note before the first paint, so its row paints
    // `is-selected`; onPanelOpened() → sync() then scores it.
    this.adoptActiveInboxNote();
    this.render();
    // Focus-suggest is active only while a panel is open (Q7).
    this.plugin.focusSuggest.onPanelOpened();
  }

  async onClose(): Promise<void> {
    this.panelContentEl = null;
    this.tabButtons = {};
    this.plugin.focusSuggest.onPanelClosed();
  }

  /** Full re-render (settings changed, tab structure). */
  refresh(): void {
    this.render();
  }

  /**
   * Re-render only the Inbox tab's content (a capture phantom changed). No-op
   * unless the Inbox tab is the active one — cheaper than {@link refresh}, and
   * it never re-pings the backend via the dev strip.
   */
  refreshInboxContent(): void {
    if (this.activeTab !== "inbox" || !this.panelContentEl) return;
    void this.renderContent();
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

    this.renderDevStrip(root);
    this.renderModeToggle(root);
    this.renderTabBar(root);
    this.panelContentEl = root.createDiv({ cls: "pipgraph-panel__content" });
    void this.renderContent();
  }

  // --------------------------------------------------------------------------
  // Focus-suggest toggle (panel-global — sits above the tab bar). While a panel
  // is open the explorer becomes a decision tool for the active/selected note;
  // the toggle picks the renderer (M5b): OFF = match-% badges on the real folder
  // tree (Phase 1), ON = ghost-tree that replaces it (Phase 2). Persisted;
  // active only while a panel is open.
  // --------------------------------------------------------------------------

  private renderModeToggle(root: HTMLElement): void {
    const bar = root.createDiv({ cls: "pipgraph-panel__mode" });
    const label = bar.createEl("label", { cls: "pipgraph-panel__mode-label" });
    label.setAttr(
      "title",
      "While the panel is open, candidate folders are scored for the selected Inbox note.\n" +
        "Off: match-% badges on the real folder tree.\n" +
        "On: a ghost-tree of candidates replaces the real tree.",
    );
    const checkbox = label.createEl("input", { type: "checkbox" });
    checkbox.checked = this.plugin.focusSuggest.enabled;
    label.createSpan({ text: "Focus suggest: ghost tree" });
    checkbox.addEventListener("change", () => {
      void this.plugin.focusSuggest.setEnabled(checkbox.checked);
    });
  }

  // --------------------------------------------------------------------------
  // Dev strip (Ping / Refresh / Process selected) — manual backend levers.
  // --------------------------------------------------------------------------

  private renderDevStrip(root: HTMLElement): void {
    const strip = root.createDiv({ cls: "pipgraph-panel__devstrip" });

    const status = strip.createSpan({ cls: "pipgraph-devstrip__status" });

    const pingBtn = strip.createEl("button", {
      text: "Ping",
      cls: "pipgraph-devstrip__btn",
    });
    pingBtn.addEventListener("click", () => void this.runPing(status, pingBtn));

    const refreshBtn = strip.createEl("button", {
      text: "Refresh",
      cls: "pipgraph-devstrip__btn",
    });
    refreshBtn.addEventListener("click", () => void this.renderContent());

    const processBtn = strip.createEl("button", {
      text: "Process selected",
      cls: "pipgraph-devstrip__btn",
    });
    processBtn.addEventListener("click", () => void this.processSelected(processBtn));

    // Colour the status dot on first paint.
    void this.runPing(status, pingBtn);
  }

  private async runPing(
    dot: HTMLElement,
    btn: HTMLButtonElement,
  ): Promise<void> {
    btn.disabled = true;
    dot.removeClass("is-online", "is-offline");
    try {
      await this.plugin.client.ping();
      dot.addClass("is-online");
      dot.setAttr("aria-label", "Backend reachable");
    } catch {
      dot.addClass("is-offline");
      dot.setAttr("aria-label", "Backend unreachable");
    } finally {
      btn.disabled = false;
    }
  }

  /**
   * Run `process-existing-episode` (LLM) on the active editor note. Placed notes
   * leave the Inbox tab, so the active file — not the inbox list — is the
   * selection source. Validated at click time (resolve → must be linked) rather
   * than pre-disabling the button, which would need a network probe on every
   * active-leaf change.
   */
  private async processSelected(btn: HTMLButtonElement): Promise<void> {
    const file = this.plugin.app.workspace.getActiveFile();
    if (!file || file.extension !== "md") {
      new Notice("Open the note you want to process first.");
      return;
    }

    btn.disabled = true;
    const original = btn.textContent;
    btn.setText("Processing…");
    try {
      const episode = await this.plugin.client.resolveEpisodicByPath(file.path);
      if (!episode) {
        new Notice("This note isn't in PipGraph yet.");
        return;
      }
      // process-existing-episode requires ≥1 MENTIONS — reject unlinked notes
      // with a clear next step rather than a backend precondition error.
      const unlinked = await this.plugin.client.listUnlinkedEpisodics();
      if (unlinked.some((e) => e.uuid === episode.uuid)) {
        new Notice(
          "Place this note in a folder first (drag it onto one), then process.",
        );
        return;
      }
      const result = await this.plugin.client.processExistingEpisode({
        episodic_uuid: episode.uuid,
      });
      const summaries = result.para_entities_updated.length;
      new Notice(
        `Processed: ${result.nodes_count} entities, ${result.edges_count} relations` +
          (summaries ? `, ${summaries} summary updated.` : "."),
      );
    } catch (err) {
      new Notice(`Process failed: ${this.describeError(err)}`);
    } finally {
      btn.disabled = false;
      if (original !== null) btn.setText(original);
    }
  }

  private describeError(err: unknown): string {
    if (err instanceof PipGraphApiError) {
      if (err.kind === "network") return "backend unreachable";
      if (err.kind === "timeout") return "backend timed out";
      return err.message;
    }
    return err instanceof Error ? err.message : String(err);
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
    // Switching onto the Inbox tab adopts an already-open inbox note (the ghost
    // renderer is live, so selectInbox recomputes); renderContent paints its row.
    if (tab === "inbox") this.adoptActiveInboxNote();
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
      .filter((f) => f.path.startsWith(prefix));

    const records = this.plugin.outbox.listRecords();

    if (files.length === 0 && records.length === 0) {
      host.createEl("p", {
        text: "Inbox is empty.",
        cls: "pipgraph-panel__placeholder",
      });
      return;
    }

    // "Semantic" sort needs pre-extracted data; the no-op provider has none, so
    // it stays disabled and the order falls back to "date" (the "B requires A"
    // pattern). Real data (plan 02) flips this on without touching the call.
    const semanticReady =
      this.plugin.inboxSemantic.semanticsFor(files.map((f) => f.path)).size > 0;

    this.renderInboxToolbar(host, semanticReady);

    if (this.plugin.inboxBatch.size > 0) {
      const strip = host.createDiv({ cls: "pipgraph-inbox-batchbar" });
      strip.createSpan({ text: `${this.plugin.inboxBatch.size} selected` });
      const clear = strip.createEl("button", {
        text: "Clear",
        cls: "pipgraph-inbox-batch-clear",
      });
      clear.addEventListener("click", () => this.plugin.clearInboxBatch());
    }

    const list = host.createDiv({ cls: "pipgraph-inbox-list" });

    // Phantom rows for in-flight / failed-create captures, above every group.
    for (const record of records) {
      this.renderPhantomRow(list, record);
    }

    // Date order (D8): newest first by ctime, split into day groups (D7). When a
    // future semantic provider has data and the user picked it, render flat in
    // that order instead (drop-in seam — never reached with the no-op provider).
    const sorted = [...files].sort((a, b) => b.stat.ctime - a.stat.ctime);
    const useSemantic =
      this.plugin.settings.inboxSort === "semantic" && semanticReady;

    if (useSemantic) {
      for (const file of sorted) {
        this.renderInboxItem(list, this.buildItemData(file), inboxPath);
      }
    } else {
      let group: HTMLElement | null = null;
      let currentDay = "";
      for (const file of sorted) {
        const day = formatDay(file.stat.ctime);
        if (!group || day !== currentDay) {
          group = list.createDiv({ cls: "pipgraph-inbox-daygroup" });
          currentDay = day;
        }
        this.renderInboxItem(group, this.buildItemData(file), inboxPath);
      }
    }

    // Apply the dependent "similar" dim + auto-select for the current selection
    // (no-op provider → nothing happens; the path stays live for a real one).
    void this.applySimilarHighlight();
  }

  /**
   * Inbox-tab toolbar (inbox-tuning 01): a sort pill switch (Date added /
   * Semantic) plus the two local toggles — A "Highlight similar" and B
   * "Auto-select similar" (B requires A). All three persist in settings.
   */
  private renderInboxToolbar(host: HTMLElement, semanticReady: boolean): void {
    const bar = host.createDiv({ cls: "pipgraph-inbox-toolbar" });

    const sort = bar.createDiv({ cls: "pipgraph-inbox-sort" });
    this.renderSortPill(sort, "date", "Date added", false);
    this.renderSortPill(sort, "semantic", "Semantic", !semanticReady);

    const toggles = bar.createDiv({ cls: "pipgraph-inbox-toggles" });
    const a = this.plugin.settings.inboxHighlightSimilar;
    const b = this.plugin.settings.inboxAutoSelectSimilar;

    const aLabel = toggles.createEl("label", { cls: "pipgraph-inbox-toggle" });
    aLabel.setAttr("title", "Dim-highlight Inbox notes similar to the selected one.");
    const aBox = aLabel.createEl("input", { type: "checkbox" });
    aBox.checked = a;
    aLabel.createSpan({ text: "Highlight similar" });
    aBox.addEventListener("change", () =>
      void this.setSimilarToggle("inboxHighlightSimilar", aBox.checked),
    );

    const bLabel = toggles.createEl("label", { cls: "pipgraph-inbox-toggle" });
    bLabel.toggleClass("is-disabled", !a);
    bLabel.setAttr(
      "title",
      "Auto-check the highlighted notes into the placement batch. Requires “Highlight similar”.",
    );
    const bBox = bLabel.createEl("input", { type: "checkbox" });
    bBox.checked = a && b;
    bBox.disabled = !a;
    bLabel.createSpan({ text: "Auto-select similar" });
    bBox.addEventListener("change", () =>
      void this.setSimilarToggle("inboxAutoSelectSimilar", bBox.checked),
    );
  }

  private renderSortPill(
    group: HTMLElement,
    value: InboxSort,
    label: string,
    disabled: boolean,
  ): void {
    const pill = group.createSpan({ cls: "pipgraph-inbox-sort-pill", text: label });
    pill.toggleClass("is-active", this.plugin.settings.inboxSort === value);
    if (disabled) {
      pill.addClass("is-disabled");
      pill.setAttr("aria-disabled", "true");
      pill.setAttr("title", "Semantic order needs pre-extracted data (coming later).");
      return;
    }
    pill.addEventListener("click", () => void this.setInboxSort(value));
  }

  private async setInboxSort(value: InboxSort): Promise<void> {
    if (this.plugin.settings.inboxSort === value) return;
    this.plugin.settings.inboxSort = value;
    await this.plugin.saveData(this.plugin.settings);
    this.plugin.refreshInboxTabs();
  }

  private async setSimilarToggle(
    key: "inboxHighlightSimilar" | "inboxAutoSelectSimilar",
    on: boolean,
  ): Promise<void> {
    this.plugin.settings[key] = on;
    await this.plugin.saveData(this.plugin.settings);
    // Re-render rebuilds the toolbar (B's enabled state tracks A) and re-runs
    // applySimilarHighlight for the current selection.
    this.plugin.refreshInboxTabs();
  }

  private buildItemData(file: TFile): InboxItemData {
    return {
      file,
      added: formatDay(file.stat.ctime),
      fallbackUuid: this.plugin.naming.uuidForPath(file.path) ?? null,
      regenerating: this.plugin.naming.isRegenerating(file.path),
    };
  }

  /**
   * Repaint selection-dependent state (the `.is-selected` highlight + the
   * primary note's checked+locked checkbox) on every Inbox item — pure DOM, no
   * list rebuild (keeps scroll position). Followed by the async similar pass.
   */
  private onInboxSelectionChanged(): void {
    const sel = this.plugin.lastInboxSelectionPath;
    // Invariant: the primary lives in lastInboxSelectionPath, never in the batch
    // set (its checkbox is checked+locked on its own account). Drop it if a
    // manual check had added it before it became the selection.
    if (sel) this.plugin.inboxBatch.delete(sel);
    this.panelContentEl
      ?.querySelectorAll<HTMLElement>(".pipgraph-inbox-item[data-path]")
      .forEach((el) => {
        const path = el.getAttribute("data-path");
        const isPrimary = !!path && path === sel;
        el.toggleClass("is-selected", isPrimary);
        const check = el.querySelector<HTMLInputElement>(
          ".pipgraph-inbox-item__check",
        );
        if (check) {
          check.checked = isPrimary || (!!path && this.plugin.inboxBatch.has(path));
          check.disabled = isPrimary;
        }
      });
    // Selection changed → recompute the auto-select batch (Q2). Plain re-renders
    // (capture phantoms, processing markers) must NOT, or they'd wipe the user's
    // manual un-checks — those only reset on the next selection change.
    void this.applySimilarHighlight(true);
  }

  /**
   * Dependent "similar" highlight + auto-select (inbox-tuning 01, §3). With A
   * on, dim notes the similarity provider deems similar to the primary (the
   * primary itself shows the stronger `.is-selected`). With B on (⇒ A on) AND
   * `recomputeBatch`, the batch is fully recomputed (Q2) to those hits, minus
   * the primary. Painting the dim class is idempotent and runs on every render;
   * the batch recompute only on a selection change. The provider is a no-op this
   * increment, so nothing lights up — but the path is live for a real provider.
   */
  private async applySimilarHighlight(recomputeBatch = false): Promise<void> {
    const host = this.panelContentEl;
    if (!host || this.activeTab !== "inbox") return;

    const primary = this.plugin.lastInboxSelectionPath;
    const items = () =>
      Array.from(
        host.querySelectorAll<HTMLElement>(".pipgraph-inbox-item[data-path]"),
      );

    if (!this.plugin.settings.inboxHighlightSimilar || !primary) {
      items().forEach((el) => el.removeClass("is-similar"));
      return;
    }

    const candidates = items()
      .map((el) => el.getAttribute("data-path"))
      .filter((p): p is string => !!p && p !== primary);

    const seq = ++this.similarSeq;
    let hits: SimilarHit[];
    try {
      hits = await this.plugin.inboxSimilarity.similarTo(primary, candidates);
    } catch {
      hits = [];
    }
    if (seq !== this.similarSeq || !host.isConnected) return;

    const hitPaths = new Set(hits.map((h) => h.path));
    items().forEach((el) => {
      const p = el.getAttribute("data-path");
      el.toggleClass("is-similar", !!p && hitPaths.has(p));
    });

    if (recomputeBatch && this.plugin.settings.inboxAutoSelectSimilar) {
      // Full recompute (Q2): the batch becomes exactly the similar hits, minus
      // the primary (which is always placed). setInboxBatch is idempotent, so
      // the refresh it triggers re-enters here (recomputeBatch=false) and settles.
      this.plugin.setInboxBatch(
        hits.map((h) => h.path).filter((p) => p !== primary),
      );
    }
  }

  /**
   * If the editor's active note lives under the Inbox folder, adopt it as the
   * focus-suggest target (highlight + score). Lets opening the panel / switching
   * to the Inbox tab pick up an already-open inbox note, so the highlight and the
   * recommendations stay in sync. Notes outside the Inbox are ignored.
   */
  private adoptActiveInboxNote(): void {
    const active = this.plugin.app.workspace.getActiveFile();
    if (!active) return;
    const prefix = `${getInboxPath(this.plugin.settings)}/`;
    if (!active.path.startsWith(prefix)) return;
    this.plugin.focusSuggest.selectInbox(active.path);
  }

  /**
   * Render a rich, two-line Inbox item (inbox-tuning 01). Line 1: batch checkbox
   * + title + path-badge + markers (`❗`/`⟳`). Line 2 (small): added date + a
   * lazily-loaded body snippet. A note whose name is a *text fallback* gets the
   * `❗` marker + a right-click → "Regenerate name with LLM" (mirrors the
   * file-explorer menu). The primary (selected) note's checkbox is checked+locked
   * — it's always part of the placement batch (Q3).
   */
  private renderInboxItem(
    list: HTMLElement,
    data: InboxItemData,
    inboxPath: string,
  ): void {
    const { file } = data;
    const isPrimary = file.path === this.plugin.lastInboxSelectionPath;

    const item = list.createDiv({ cls: "pipgraph-inbox-item" });
    item.setAttr("data-path", file.path);
    item.toggleClass("is-selected", isPrimary);

    // Batch checkbox. Primary → checked+disabled (always placed). stopPropagation
    // so toggling it doesn't open the note via the row click.
    const check = item.createEl("input", {
      type: "checkbox",
      cls: "pipgraph-inbox-item__check",
    });
    check.checked = isPrimary || this.plugin.inboxBatch.has(file.path);
    check.disabled = isPrimary;
    check.setAttr(
      "aria-label",
      isPrimary
        ? "Selected note — always placed with the batch"
        : "Add this note to the placement batch",
    );
    check.addEventListener("click", (ev) => ev.stopPropagation());
    check.addEventListener("change", () => this.plugin.toggleInboxBatch(file.path));

    const body = item.createDiv({ cls: "pipgraph-inbox-item__body" });
    const main = body.createDiv({ cls: "pipgraph-inbox-item__main" });
    main.createSpan({ cls: "pipgraph-inbox-item__title", text: file.basename });
    const rel = file.parent?.path.slice(inboxPath.length).replace(/^\//, "");
    if (rel) {
      main.createSpan({ cls: "pipgraph-inbox-item__path", text: rel });
    }

    if (data.regenerating) {
      // Naming job re-running — show the same in-flight `⟳` an add shows, in
      // place of the `❗`. No menu while it's working.
      const spin = main.createSpan({ cls: "pipgraph-inbox-item__regen" });
      setIcon(spin, "loader");
      spin.setAttr("aria-label", "Regenerating the name with the LLM…");
    } else if (data.fallbackUuid) {
      const fallbackUuid = data.fallbackUuid;
      const tooltip =
        "Couldn't auto-name this note with the LLM — possibly an LLM provider " +
        "connection error. Right-click to regenerate the name.";
      item.addClass("pipgraph-inbox-item--fallback");
      const marker = main.createSpan({
        cls: "pipgraph-inbox-item__fallback",
        text: "❗",
      });
      marker.setAttr("aria-label", tooltip);
      item.addEventListener("contextmenu", (ev) => {
        ev.preventDefault();
        const menu = new Menu();
        menu.addItem((mItem) =>
          mItem
            .setTitle("Regenerate name with LLM")
            .setIcon("sparkles")
            .onClick(() => void regenerateName(this.plugin, fallbackUuid, file)),
        );
        menu.showAtMouseEvent(ev);
      });
    }

    const meta = body.createDiv({ cls: "pipgraph-inbox-item__meta" });
    meta.createSpan({ cls: "pipgraph-inbox-item__date", text: data.added });
    void this.fillSnippet(file, meta);

    item.addEventListener("click", () => {
      // This selection is the focus-suggest scoring target: set it (recompute)
      // via the controller, repaint selection state, then open the note.
      this.plugin.focusSuggest.selectInbox(file.path);
      this.onInboxSelectionChanged();
      void this.plugin.app.workspace.getLeaf(false).openFile(file);
    });
    // Drag onto a PARA folder to move+link (DragToPlace handles the drop). The
    // batch rides along on drop — the MIME still carries just this one path.
    item.draggable = true;
    item.addEventListener("dragstart", (ev) => {
      ev.dataTransfer?.setData(PIPGRAPH_DRAG_MIME, file.path);
      ev.dataTransfer?.setData("text/plain", file.path);
      if (ev.dataTransfer) ev.dataTransfer.effectAllowed = "move";
    });
  }

  /**
   * Lazily load a note's body snippet into its meta line (D4). Reads via
   * `cachedRead` (cheap, cache-backed), memoises per file by mtime, and guards
   * against a stale paint (the meta element being replaced by a re-render).
   */
  private async fillSnippet(file: TFile, metaEl: HTMLElement): Promise<void> {
    const cached = this.snippetCache.get(file.path);
    let snippet: string | null;
    if (cached && cached.mtime === file.stat.mtime) {
      snippet = cached.snippet;
    } else {
      try {
        const content = await this.plugin.app.vault.cachedRead(file);
        snippet = extractSnippet(content);
      } catch {
        snippet = null;
      }
      this.snippetCache.set(file.path, { mtime: file.stat.mtime, snippet });
    }
    if (!snippet || !metaEl.isConnected) return;
    metaEl.createSpan({ cls: "pipgraph-inbox-item__snippet", text: snippet });
  }

  /**
   * Render a phantom row for a pre-materialisation capture (Model 2):
   *  - `inflight`     — a static `⟳`, non-interactive (the naming job runs).
   *  - `failed-create`— a `⚠`; left-click retries, right-click offers
   *    Retry adding note / Save to drafts / Discard.
   * Phantoms back no file, so they are never draggable. One-line, but laid out on
   * the item grid (a checkbox-column spacer) so titles line up with real items.
   */
  private renderPhantomRow(list: HTMLElement, record: CaptureRecord): void {
    const inflight = record.state === "inflight";
    const row = list.createDiv({
      cls: `pipgraph-inbox-item pipgraph-inbox-phantom pipgraph-inbox-phantom--${
        inflight ? "inflight" : "failed"
      }`,
    });
    row.createDiv({ cls: "pipgraph-inbox-item__check-spacer" });

    const body = row.createDiv({ cls: "pipgraph-inbox-item__body" });
    const main = body.createDiv({ cls: "pipgraph-inbox-item__main" });
    const iconEl = main.createSpan({ cls: "pipgraph-inbox-phantom__icon" });
    setIcon(iconEl, inflight ? "loader" : "alert-triangle");
    main.createSpan({
      cls: "pipgraph-inbox-item__title",
      text: record.preview,
    });
    main.createSpan({
      cls: "pipgraph-inbox-phantom__hint",
      text: inflight ? "adding…" : "couldn't add",
    });

    if (inflight) {
      row.setAttr("aria-label", "Adding this note — naming it…");
      return; // non-interactive while in flight
    }

    row.setAttr(
      "aria-label",
      "Couldn't add this note to PipGraph. Click to retry, or right-click for options.",
    );
    row.addClass("is-clickable");
    row.addEventListener("click", () => this.plugin.outbox.retry(record.uuid));
    row.addEventListener("contextmenu", (ev) => {
      ev.preventDefault();
      const menu = new Menu();
      menu.addItem((item) =>
        item
          .setTitle("Retry adding note")
          .setIcon("refresh-cw")
          .onClick(() => this.plugin.outbox.retry(record.uuid)),
      );
      menu.addItem((item) =>
        item
          .setTitle("Save to drafts")
          .setIcon("file-pen")
          .onClick(() => void this.plugin.outbox.saveToDraft(record.uuid)),
      );
      menu.addItem((item) =>
        item
          .setTitle("Discard")
          .setIcon("trash")
          .onClick(() => void this.plugin.outbox.discard(record.uuid)),
      );
      menu.showAtMouseEvent(ev);
    });
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
