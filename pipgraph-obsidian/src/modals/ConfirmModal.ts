import { App, Modal } from "obsidian";

export interface ConfirmModalOptions {
  title: string;
  /** Body text; lines are rendered as separate paragraphs. */
  body: string | string[];
  /** Confirm-button label (defaults to "Delete"). */
  confirmText?: string;
  /** When true, the confirm button is styled as a destructive (red) action. */
  destructive?: boolean;
}

/**
 * Minimal yes/no confirmation dialog. Resolves `true` if the user confirms,
 * `false` if they cancel or dismiss. Used by the settings "Danger zone" so the
 * irreversible debug resets can't fire on a single misclick.
 */
export class ConfirmModal extends Modal {
  private resolved = false;

  private constructor(
    app: App,
    private readonly options: ConfirmModalOptions,
    private readonly resolve: (confirmed: boolean) => void,
  ) {
    super(app);
  }

  /** Open the dialog and await the user's choice. */
  static confirm(app: App, options: ConfirmModalOptions): Promise<boolean> {
    return new Promise((resolve) => {
      new ConfirmModal(app, options, resolve).open();
    });
  }

  onOpen(): void {
    const { contentEl, titleEl } = this;
    titleEl.setText(this.options.title);

    const lines = Array.isArray(this.options.body)
      ? this.options.body
      : [this.options.body];
    for (const line of lines) {
      contentEl.createEl("p", { text: line });
    }

    const buttonsEl = contentEl.createDiv({ cls: "modal-button-container" });

    const cancelEl = buttonsEl.createEl("button", { text: "Cancel" });
    cancelEl.addEventListener("click", () => this.close());

    const confirmEl = buttonsEl.createEl("button", {
      text: this.options.confirmText ?? "Delete",
      cls: this.options.destructive ? "mod-warning" : "mod-cta",
    });
    confirmEl.addEventListener("click", () => {
      this.resolved = true;
      this.resolve(true);
      this.close();
    });
    window.setTimeout(() => confirmEl.focus(), 0);
  }

  onClose(): void {
    this.contentEl.empty();
    if (!this.resolved) this.resolve(false);
  }
}
