import { Modal, Notice, TFolder } from "obsidian";
import type PipGraphPlugin from "../main";
import { getInboxPath } from "../settings/PipGraphSettings";
import { PipGraphApiError } from "../backend";

/**
 * Capture-flow modal for `pipgraph:new-inbox-note`.
 *
 * Flow: user types/pastes → Add → backend creates Episodic (auto-names it) →
 * we write the file under <inbox>/<sanitized-name>.md → open it.
 *
 * Backend is the source of truth here: if the create call fails we never
 * touch disk, so we don't leave an orphan note.
 */
export class NewInboxNoteModal extends Modal {
  private readonly plugin: PipGraphPlugin;
  private textareaEl!: HTMLTextAreaElement;
  private addButtonEl!: HTMLButtonElement;
  private errorEl!: HTMLDivElement;
  private isSaving = false;

  constructor(plugin: PipGraphPlugin) {
    super(plugin.app);
    this.plugin = plugin;
  }

  onOpen(): void {
    const { contentEl, titleEl } = this;
    titleEl.setText("New inbox note");

    contentEl.addClass("pipgraph-new-inbox-modal");

    this.textareaEl = contentEl.createEl("textarea", {
      cls: "pipgraph-new-inbox-modal__textarea",
      attr: {
        rows: "10",
        placeholder:
          "Type or paste your note. Backend will name it. Ctrl/Cmd+Enter to add.",
      },
    });
    this.textareaEl.addEventListener("input", () => this.refreshAddButton());
    this.textareaEl.addEventListener("keydown", (ev) => {
      if ((ev.ctrlKey || ev.metaKey) && ev.key === "Enter") {
        ev.preventDefault();
        void this.handleAdd();
      }
    });

    this.errorEl = contentEl.createDiv({
      cls: "pipgraph-new-inbox-modal__error",
    });

    const buttonsEl = contentEl.createDiv({
      cls: "pipgraph-new-inbox-modal__buttons",
    });

    const cancelEl = buttonsEl.createEl("button", { text: "Cancel" });
    cancelEl.addEventListener("click", () => this.close());

    this.addButtonEl = buttonsEl.createEl("button", {
      text: "Add",
      cls: "mod-cta",
    });
    this.addButtonEl.disabled = true;
    this.addButtonEl.addEventListener("click", () => void this.handleAdd());

    window.setTimeout(() => this.textareaEl.focus(), 0);
  }

  onClose(): void {
    this.contentEl.empty();
  }

  private refreshAddButton(): void {
    if (this.isSaving) return;
    this.addButtonEl.disabled = this.textareaEl.value.trim().length === 0;
  }

  private setError(message: string | null): void {
    this.errorEl.empty();
    if (message) {
      this.errorEl.setText(message);
    }
  }

  private async handleAdd(): Promise<void> {
    const content = this.textareaEl.value;
    if (!content.trim() || this.isSaving) return;

    this.isSaving = true;
    this.addButtonEl.disabled = true;
    const originalText = this.addButtonEl.textContent;
    this.addButtonEl.setText("Saving…");
    this.setError(null);

    try {
      const inboxPath = getInboxPath(this.plugin.settings);
      await this.ensureFolder(inboxPath);

      const created = await this.plugin.client.createEpisode({ content });

      const baseName = sanitiseForFilename(created.name);
      const fileName = await this.resolveUniqueName(inboxPath, baseName);
      const path = `${inboxPath}/${fileName}`;

      const file = await this.plugin.app.vault.create(path, content);
      await this.plugin.app.workspace.getLeaf(false).openFile(file);

      // TODO(E3, Q3 §1.1): once frontmatter writes land, stamp `pipgraph.uuid`
      // (created.uuid) into this note so resolution becomes uuid-primary.

      this.close();

      // The backend named the episode, but *we* own the final collision-resolved
      // path, so we write it back (resolve-then-act, E2). Best-effort: the file
      // already exists on disk; if the PATCH fails the episode just keeps a null
      // file_path until a later sync, so we surface a notice rather than rolling
      // back the note the user just captured.
      void this.syncFilePath(created.uuid, path);
    } catch (err) {
      this.isSaving = false;
      this.addButtonEl.disabled = false;
      if (originalText !== null) this.addButtonEl.setText(originalText);
      this.setError(this.describeError(err));
    }
  }

  private async syncFilePath(uuid: string, path: string): Promise<void> {
    try {
      await this.plugin.client.updateEpisodic(uuid, { file_path: path });
    } catch (err) {
      new Notice(
        `Note saved, but recording its path in PipGraph failed: ${this.describeError(err)}`,
      );
    }
  }

  private describeError(err: unknown): string {
    if (err instanceof PipGraphApiError) {
      switch (err.kind) {
        case "network":
          return "Backend unreachable. Start the backend and try again.";
        case "timeout":
          return "Backend timed out. Try again.";
        case "http":
          return `Backend error: ${err.message}`;
        case "parse":
          return "Unexpected response from backend.";
      }
    }
    return err instanceof Error ? err.message : String(err);
  }

  private async ensureFolder(path: string): Promise<void> {
    const existing = this.plugin.app.vault.getAbstractFileByPath(path);
    if (existing instanceof TFolder) return;
    if (existing) {
      throw new Error(`"${path}" exists but is not a folder.`);
    }
    await this.plugin.app.vault.createFolder(path);
  }

  private async resolveUniqueName(
    folder: string,
    baseName: string,
  ): Promise<string> {
    const vault = this.plugin.app.vault;
    let candidate = `${baseName}.md`;
    if (!vault.getAbstractFileByPath(`${folder}/${candidate}`)) return candidate;
    for (let i = 1; i < 1000; i++) {
      candidate = `${baseName} (${i}).md`;
      if (!vault.getAbstractFileByPath(`${folder}/${candidate}`)) return candidate;
    }
    throw new Error("Could not find a free filename in the inbox.");
  }
}

function sanitiseForFilename(name: string): string {
  const trimmed = name.replace(/[\\/:*?"<>|]/g, "_").trim();
  const collapsed = trimmed.replace(/\s+/g, " ");
  const limited = collapsed.slice(0, 100).trim();
  return limited.length > 0 ? limited : "Untitled";
}
