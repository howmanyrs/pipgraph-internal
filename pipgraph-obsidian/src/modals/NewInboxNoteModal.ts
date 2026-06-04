import { Modal } from "obsidian";
import type PipGraphPlugin from "../main";
import { PipGraphApiError } from "../backend";

/**
 * Capture-flow modal for `pipgraph:new-inbox-note`.
 *
 * Flow: user types/pastes → Add → the note is handed to the durable capture
 * outbox and the modal closes immediately, so the user can capture the next one
 * without waiting on the backend. The outbox writes a hidden pending record,
 * creates the Episodic, waits for its async LLM name, then materialises the file
 * into the Inbox in the background (see CaptureOutbox).
 *
 * The modal only reports failures of the *durable write* — if that succeeds the
 * note is safe even if later delivery is retried after a restart.
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
    this.addButtonEl.setText("Saving…");
    this.setError(null);

    try {
      // Hand off to the durable outbox. This writes the pending record
      // synchronously, so once it resolves the note is safe; delivery and
      // materialisation into the Inbox happen in the background.
      await this.plugin.outbox.enqueue(content);
      this.close();
    } catch (err) {
      // Only a failed durable write lands here — surface it and keep the text.
      this.isSaving = false;
      this.addButtonEl.disabled = false;
      this.addButtonEl.setText("Add");
      this.setError(this.describeError(err));
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
}
