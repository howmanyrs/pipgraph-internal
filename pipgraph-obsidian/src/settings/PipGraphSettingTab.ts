import {
  App,
  Notice,
  PluginSettingTab,
  Setting,
  TFile,
  TFolder,
  debounce,
} from "obsidian";
import type PipGraphPlugin from "../main";
import { ConfirmModal } from "../modals/ConfirmModal";
import { FolderSuggest } from "./FolderSuggest";
import type {
  LlmConfigState,
  LlmProvider,
  PromptEntry,
} from "../backend/types";

type StringKey =
  | "backendUrl"
  | "apiKey"
  | "rootFolder"
  | "inboxRelativePath"
  | "draftsRelativePath";

interface LlmFormState {
  provider: LlmProvider;
  api_key: string;
  main_model: string;
  small_model: string;
  embedding_model: string;
}

const PROVIDER_LABELS: Record<string, string> = {
  cloudru: "Cloud.ru",
  openrouter: "OpenRouter",
};

const MODEL_FIELDS: ReadonlyArray<{
  key: "main_model" | "small_model" | "embedding_model";
  name: string;
}> = [
  { key: "main_model", name: "Main model" },
  { key: "small_model", name: "Small model" },
  { key: "embedding_model", name: "Embedding model" },
];

export class PipGraphSettingTab extends PluginSettingTab {
  private warningEl: HTMLDivElement | null = null;
  private llmSectionEl: HTMLDivElement | null = null;
  private llmState: LlmConfigState | null = null;
  private llmForm: LlmFormState | null = null;
  private promptsSectionEl: HTMLDivElement | null = null;

  constructor(
    app: App,
    private readonly plugin: PipGraphPlugin,
  ) {
    super(app, plugin);
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    new Setting(containerEl)
      .setName("Backend URL")
      .setDesc("Base URL of the PipGraph backend.")
      .addText((text) =>
        text
          .setPlaceholder(DEFAULT_PLACEHOLDER.backendUrl)
          .setValue(this.plugin.settings.backendUrl)
          .onChange(this.makeSaver("backendUrl")),
      );

    new Setting(containerEl)
      .setName("API key")
      .setDesc(
        "Reserved for future authentication. Stored unencrypted in data.json.",
      )
      .addText((text) => {
        text.inputEl.type = "password";
        text
          .setPlaceholder("")
          .setValue(this.plugin.settings.apiKey)
          .onChange(this.makeSaver("apiKey"));
      });

    new Setting(containerEl)
      .setName("Root folder")
      .setDesc(
        "Vault folder where PipGraph manages the PARA structure. Must exist or be created.",
      )
      .addText((text) => {
        text
          .setPlaceholder(DEFAULT_PLACEHOLDER.rootFolder)
          .setValue(this.plugin.settings.rootFolder)
          .onChange(this.makeSaver("rootFolder"));
        new FolderSuggest(this.app, text.inputEl, (path) => {
          this.plugin.settings.rootFolder = path;
          void this.plugin.saveSettings();
          this.refreshWarning();
        });
      });

    this.warningEl = containerEl.createDiv({
      cls: "pipgraph-settings__warning",
    });
    this.refreshWarning();

    new Setting(containerEl)
      .setName("Inbox folder name")
      .setDesc(
        "Subfolder under the root where new notes land. New notes here are sent to the backend as Episodics when auto-ingest is on.",
      )
      .addText((text) =>
        text
          .setPlaceholder(DEFAULT_PLACEHOLDER.inboxRelativePath)
          .setValue(this.plugin.settings.inboxRelativePath)
          .onChange(this.makeSaver("inboxRelativePath")),
      );

    new Setting(containerEl)
      .setName("Drafts subfolder name")
      .setDesc(
        "Subfolder inside Inbox for raw drafts. Use the 'Process current draft' command to ingest them.",
      )
      .addText((text) =>
        text
          .setPlaceholder(DEFAULT_PLACEHOLDER.draftsRelativePath)
          .setValue(this.plugin.settings.draftsRelativePath)
          .onChange(this.makeSaver("draftsRelativePath")),
      );

    new Setting(containerEl)
      .setName("Auto-mirror folders to backend")
      .setDesc(
        'When on, every folder under the root (except Inbox and freshly-created "Untitled" folders) is mirrored to a PARA entity automatically — on creation, rename, and plugin load. When off, mirror a folder explicitly via right-click → "PipGraph: Sync folder to backend".',
      )
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.autoMirrorFolders)
          .onChange(async (value) => {
            this.plugin.settings.autoMirrorFolders = value;
            await this.plugin.saveSettings();
            // Flipping it on should pick up existing folders right away.
            if (value) void this.plugin.folderMirror?.reconcile();
          }),
      );

    // LLM provider section — backend is the source of truth, so it loads lazily
    // from /dev/llm-config and degrades gracefully when the backend is offline.
    this.renderLlmHeading(containerEl);
    void this.reloadLlm();

    // Editable prompts — same shape as the LLM section: lazy load from
    // /dev/prompts, graceful absence when the backend is offline.
    this.renderPromptsHeading(containerEl);
    void this.reloadPrompts();

    // Debug-only destructive actions, fenced off at the bottom.
    this.renderDangerZone(containerEl);
  }

  // --------------------------------------------------------------------------
  // Danger zone (debug resets)
  // --------------------------------------------------------------------------

  private renderDangerZone(containerEl: HTMLElement): void {
    const section = containerEl.createDiv({ cls: "pipgraph-settings__danger" });
    section.createEl("h3", { text: "Danger zone" });
    section.createEl("p", {
      cls: "setting-item-description",
      text:
        "Destructive debugging actions. Each is irreversible and asks for " +
        "confirmation. Intended for local development, not everyday use.",
    });

    new Setting(section)
      .setName("Delete all graph nodes & edges")
      .setDesc(
        "Wipe the entire backend graph — every Episodic, PARA entity and " +
          "relationship. Does not touch your vault files.",
      )
      .addButton((btn) =>
        btn
          .setButtonText("Wipe graph")
          .setWarning()
          .onClick(() => void this.handleWipeGraph()),
      );

    new Setting(section)
      .setName("Delete all notes & pending files in the PipGraph folder")
      .setDesc(
        `Delete every note under "${this.plugin.settings.rootFolder}", remove ` +
          "the emptied PARA subfolders (the root folder itself is kept), and " +
          "clear pending capture files. Deleted notes follow your Obsidian " +
          '"Deleted files" setting. Does not touch the graph.',
      )
      .addButton((btn) =>
        btn
          .setButtonText("Clear vault folder")
          .setWarning()
          .onClick(() => void this.handleClearVault()),
      );
  }

  private async handleWipeGraph(): Promise<void> {
    const confirmed = await ConfirmModal.confirm(this.app, {
      title: "Wipe the entire graph?",
      body: [
        "This deletes every node and relationship in the backend graph.",
        "It cannot be undone. Your vault files are not affected.",
      ],
      confirmText: "Wipe graph",
      destructive: true,
    });
    if (!confirmed) return;

    try {
      const result = await this.plugin.client.clearGraph();
      new Notice(
        `PipGraph: wiped the graph (${result.deleted_nodes_count} node(s) deleted).`,
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      new Notice(`PipGraph: failed to wipe the graph: ${message}`);
    }
  }

  private async handleClearVault(): Promise<void> {
    const rootPath = this.plugin.settings.rootFolder.trim();
    const confirmed = await ConfirmModal.confirm(this.app, {
      title: "Clear the PipGraph folder?",
      body: [
        `This deletes every note under "${rootPath}", removes the emptied ` +
          "PARA subfolders, and clears pending capture files.",
        "Deleted notes follow your Obsidian “Deleted files” setting. " +
          "The graph is not affected.",
      ],
      confirmText: "Clear folder",
      destructive: true,
    });
    if (!confirmed) return;

    try {
      const { notes, folders } = await this.clearVaultFolder(rootPath);
      const pending = await this.plugin.outbox.purgePending();
      new Notice(
        `PipGraph: removed ${notes} note(s), ${folders} folder(s), ` +
          `and ${pending} pending file(s).`,
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      new Notice(`PipGraph: failed to clear the folder: ${message}`);
    }
  }

  /**
   * Delete all markdown notes under the root folder, then remove every
   * subfolder that ends up empty (deepest first), keeping the root itself.
   * Uses `trashFile` so deletions honour the user's Obsidian trash preference.
   */
  private async clearVaultFolder(
    rootPath: string,
  ): Promise<{ notes: number; folders: number }> {
    const root = this.app.vault.getAbstractFileByPath(rootPath);
    if (!(root instanceof TFolder)) {
      throw new Error(`Root folder "${rootPath}" does not exist.`);
    }

    const files: TFile[] = [];
    const folders: TFolder[] = [];
    const walk = (folder: TFolder): void => {
      for (const child of folder.children) {
        if (child instanceof TFolder) {
          folders.push(child);
          walk(child);
        } else if (child instanceof TFile && child.extension === "md") {
          files.push(child);
        }
      }
    };
    walk(root);

    let notesRemoved = 0;
    for (const file of files) {
      try {
        await this.app.fileManager.trashFile(file);
        notesRemoved++;
      } catch {
        // leave a stubborn file; the user can remove it manually
      }
    }

    // Deepest folders first, so a parent is empty by the time we reach it.
    folders.sort((a, b) => b.path.length - a.path.length);
    let foldersRemoved = 0;
    for (const folder of folders) {
      const current = this.app.vault.getAbstractFileByPath(folder.path);
      if (current instanceof TFolder && current.children.length === 0) {
        try {
          await this.app.fileManager.trashFile(current);
          foldersRemoved++;
        } catch {
          // non-empty (a non-md file survived) or locked — leave it
        }
      }
    }

    return { notes: notesRemoved, folders: foldersRemoved };
  }

  // --------------------------------------------------------------------------
  // LLM provider section
  // --------------------------------------------------------------------------

  private renderLlmHeading(containerEl: HTMLElement): void {
    containerEl.createEl("h3", { text: "LLM provider" });
    containerEl.createEl("p", {
      cls: "setting-item-description",
      text:
        "Provider, API key and model names live on the backend. Changes apply " +
        "after a backend restart — the running LLM is not rebuilt in place.",
    });
    this.llmSectionEl = containerEl.createDiv({ cls: "pipgraph-settings__llm" });
  }

  /** Re-fetch the LLM config from the backend and re-render the section. */
  private async reloadLlm(): Promise<void> {
    const el = this.llmSectionEl;
    if (!el) return;
    el.empty();
    el.createEl("p", { text: "Loading LLM config from backend…" });

    try {
      const state = await this.plugin.client.getLlmConfig();
      this.llmState = state;

      const base = state.saved ?? state.active;
      const provider: LlmProvider = base?.provider ?? "cloudru";
      const defaults = state.providers[provider];
      this.llmForm = {
        provider,
        api_key: "", // never prefilled — backend masks the key
        main_model: base?.main_model ?? defaults?.main_model ?? "",
        small_model: base?.small_model ?? defaults?.small_model ?? "",
        embedding_model:
          base?.embedding_model ?? defaults?.embedding_model ?? "",
      };
      this.renderLlmForm();
    } catch (err) {
      this.llmState = null;
      this.llmForm = null;
      el.empty();
      const message = err instanceof Error ? err.message : String(err);
      el.createEl("p", {
        cls: "pipgraph-settings__warning",
        text: `LLM config unavailable — is the backend running? (${message})`,
      });
      new Setting(el).addButton((btn) =>
        btn.setButtonText("Retry").onClick(() => void this.reloadLlm()),
      );
    }
  }

  private renderLlmForm(): void {
    const el = this.llmSectionEl;
    const state = this.llmState;
    const form = this.llmForm;
    if (!el || !state || !form) return;
    el.empty();

    if (state.restart_required) {
      el.createEl("p", {
        cls: "pipgraph-settings__warning",
        text:
          "Saved config differs from the running backend — restart the backend to apply.",
      });
    }

    new Setting(el)
      .setName("Provider")
      .setDesc("Selects the OpenAI-compatible backend. base_url is fixed per provider.")
      .addDropdown((dropdown) => {
        for (const name of Object.keys(state.providers)) {
          dropdown.addOption(name, PROVIDER_LABELS[name] ?? name);
        }
        dropdown.setValue(form.provider);
        dropdown.onChange((value) => this.onProviderChange(value as LlmProvider));
      });

    const saved = state.saved;
    const keyPlaceholder =
      saved?.api_key_set
        ? `•••• ${saved.api_key_hint ?? ""} — leave blank to keep`
        : "not set";
    new Setting(el)
      .setName("API key")
      .setDesc(
        "Provider API key. Leave blank to keep the saved key. Stored unencrypted on the backend.",
      )
      .addText((text) => {
        text.inputEl.type = "password";
        text
          .setPlaceholder(keyPlaceholder)
          .setValue(form.api_key)
          .onChange((value) => {
            form.api_key = value;
          });
      });

    const providerDefaults = state.providers[form.provider];
    for (const field of MODEL_FIELDS) {
      new Setting(el).setName(field.name).addText((text) => {
        text
          .setPlaceholder(providerDefaults?.[field.key] ?? "")
          .setValue(form[field.key])
          .onChange((value) => {
            form[field.key] = value;
          });
      });
    }

    // Embedding-change warning: switching provider or embedding model makes the
    // existing name_embedding vectors incompatible (re-embedding is not performed).
    const active = state.active;
    if (active) {
      const embeddingChanged =
        (!!form.embedding_model && form.embedding_model !== active.embedding_model) ||
        form.provider !== active.provider;
      if (embeddingChanged) {
        el.createEl("p", {
          cls: "pipgraph-settings__warning",
          text:
            "Changing the embedding model or provider invalidates existing vectors — " +
            "search and suggestions will be wrong until re-embedding (not performed here).",
        });
      }
    }

    new Setting(el)
      .addButton((btn) =>
        btn
          .setButtonText("Save to backend")
          .setCta()
          .onClick(() => void this.saveLlm()),
      )
      .addButton((btn) =>
        btn.setButtonText("Reset to defaults").onClick(() => void this.resetLlm()),
      );
  }

  /**
   * On provider switch, repopulate model fields that are untouched (empty or
   * still equal to the old provider's default) with the new provider's defaults;
   * keep any value the user customised.
   */
  private onProviderChange(next: LlmProvider): void {
    const state = this.llmState;
    const form = this.llmForm;
    if (!state || !form) return;

    const oldDefaults = state.providers[form.provider];
    const newDefaults = state.providers[next];
    for (const field of MODEL_FIELDS) {
      const current = form[field.key];
      if (!current || current === oldDefaults?.[field.key]) {
        form[field.key] = newDefaults?.[field.key] ?? "";
      }
    }
    form.provider = next;
    this.renderLlmForm();
  }

  private async saveLlm(): Promise<void> {
    const form = this.llmForm;
    if (!form) return;
    try {
      const result = await this.plugin.client.updateLlmConfig({
        provider: form.provider,
        main_model: form.main_model,
        small_model: form.small_model,
        embedding_model: form.embedding_model,
        // Omit empty key so the backend keeps the saved one.
        ...(form.api_key.trim() ? { api_key: form.api_key.trim() } : {}),
      });
      new Notice(
        result.restart_required
          ? "LLM config saved — restart the backend to apply."
          : "LLM config saved.",
      );
      for (const warning of result.warnings) new Notice(warning, 8000);
      await this.reloadLlm();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      new Notice(`Failed to save LLM config: ${message}`);
    }
  }

  private async resetLlm(): Promise<void> {
    try {
      const result = await this.plugin.client.resetLlmConfig();
      new Notice(
        result.restart_required
          ? "LLM config reset — restart the backend to apply."
          : "LLM config reset to defaults.",
      );
      await this.reloadLlm();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      new Notice(`Failed to reset LLM config: ${message}`);
    }
  }

  // --------------------------------------------------------------------------
  // Editable prompts section (/dev/prompts)
  //
  // The backend owns the prompt text and overlays it onto graphiti; this section
  // only shows each prompt's editable domain block + a read-only response-format
  // example. Unlike the LLM section, an edit applies live (no backend restart).
  // --------------------------------------------------------------------------

  private renderPromptsHeading(containerEl: HTMLElement): void {
    containerEl.createEl("h3", { text: "Промпты" });
    containerEl.createEl("p", {
      cls: "setting-item-description",
      text:
        "Доменные guidelines промптов извлечения живут на бэкенде. Правка " +
        "применяется к следующей обработке заметки — без рестарта. Пример формата " +
        "ответа — только для чтения.",
    });
    this.promptsSectionEl = containerEl.createDiv({
      cls: "pipgraph-settings__prompts",
    });
  }

  /** Re-fetch the tunable prompts from the backend and re-render the cards. */
  private async reloadPrompts(): Promise<void> {
    const el = this.promptsSectionEl;
    if (!el) return;
    el.empty();
    el.createEl("p", { text: "Загрузка промптов с бэкенда…" });

    try {
      const prompts = await this.plugin.client.listPrompts();
      el.empty();
      if (prompts.length === 0) {
        el.createEl("p", {
          cls: "setting-item-description",
          text: "На бэкенде не зарегистрировано редактируемых промптов.",
        });
        return;
      }
      for (const entry of prompts) this.renderPromptCard(el, entry);
    } catch (err) {
      el.empty();
      const message = err instanceof Error ? err.message : String(err);
      el.createEl("p", {
        cls: "pipgraph-settings__warning",
        text: `Промпты недоступны — бэкенд запущен? (${message})`,
      });
      new Setting(el).addButton((btn) =>
        btn.setButtonText("Повторить").onClick(() => void this.reloadPrompts()),
      );
    }
  }

  private renderPromptCard(parent: HTMLElement, entry: PromptEntry): void {
    const card = parent.createDiv({ cls: "pipgraph-prompt-card" });

    const header = card.createDiv({ cls: "pipgraph-prompt-card__header" });
    header.createEl("span", {
      cls: "pipgraph-prompt-card__title",
      text: entry.title,
    });
    header.createEl("code", {
      cls: "pipgraph-prompt-card__key",
      text: entry.key,
    });
    header.createEl("span", {
      cls: `pipgraph-prompt-card__badge pipgraph-prompt-card__badge--${entry.mode}`,
      text: entry.mode,
    });
    if (entry.is_customized) {
      header.createEl("span", {
        cls: "pipgraph-prompt-card__customised",
        text: "изменено",
      });
    }

    card.createEl("p", {
      cls: "setting-item-description",
      text: entry.description,
    });

    // Editable domain block — the same text feeds both append and replace modes.
    card.createEl("label", {
      cls: "pipgraph-prompt-card__label",
      text: "Доменные указания (редактируемо):",
    });
    const textarea = card.createEl("textarea", {
      cls: "pipgraph-prompt-card__textarea",
    });
    textarea.value = entry.domain_block;
    textarea.rows = 6;
    textarea.disabled = !entry.editable;

    new Setting(card)
      .addButton((btn) =>
        btn
          .setButtonText("Сохранить")
          .setCta()
          .setDisabled(!entry.editable)
          .onClick(() => void this.savePrompt(entry.key, textarea.value)),
      )
      .addButton((btn) =>
        btn
          .setButtonText("Сбросить к дефолту")
          .setDisabled(!entry.editable)
          .onClick(() => void this.resetPrompt(entry.key)),
      );

    // Read-only response-format example — the exact example the LLM is shown
    // (goes through the same example_for() on the backend, so it can't disagree).
    if (entry.example_preview) {
      card.createEl("label", {
        cls: "pipgraph-prompt-card__label",
        text: "Формат ответа (только чтение):",
      });
      const pre = card.createEl("pre", {
        cls: "pipgraph-prompt-card__example",
      });
      pre.createEl("code", { text: entry.example_preview });
    }
  }

  private async savePrompt(key: string, domainBlock: string): Promise<void> {
    try {
      await this.plugin.client.updatePrompt(key, domainBlock);
      new Notice(
        "Промпт сохранён — применится со следующей обработки заметки (без рестарта).",
      );
      await this.reloadPrompts();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      new Notice(`Не удалось сохранить промпт: ${message}`);
    }
  }

  private async resetPrompt(key: string): Promise<void> {
    try {
      await this.plugin.client.resetPrompt(key);
      new Notice("Промпт сброшен к значению по умолчанию.");
      await this.reloadPrompts();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      new Notice(`Не удалось сбросить промпт: ${message}`);
    }
  }

  private makeSaver(key: StringKey): (value: string) => void {
    const save = debounce(
      async (value: string) => {
        this.plugin.settings[key] = value;
        await this.plugin.saveSettings();
        if (key === "rootFolder") {
          this.refreshWarning();
        }
      },
      300,
      true,
    );
    return (value: string) => save(value);
  }

  private refreshWarning(): void {
    if (!this.warningEl) return;
    this.warningEl.empty();

    const path = this.plugin.settings.rootFolder.trim();
    if (!path) {
      this.warningEl.createEl("p", {
        text: "Root folder is empty. Set a folder name to continue.",
      });
      return;
    }

    const existing = this.app.vault.getAbstractFileByPath(path);
    if (existing instanceof TFolder) {
      return;
    }
    if (existing) {
      this.warningEl.createEl("p", {
        text: `"${path}" exists but is not a folder.`,
      });
      return;
    }

    this.warningEl.createEl("p", {
      text: `Folder "${path}" does not exist.`,
    });
    new Setting(this.warningEl).addButton((btn) =>
      btn
        .setButtonText("Create folder")
        .setCta()
        .onClick(async () => {
          try {
            await this.app.vault.createFolder(path);
            new Notice(`Created folder "${path}".`);
            this.refreshWarning();
          } catch (err) {
            const message =
              err instanceof Error ? err.message : String(err);
            new Notice(`Failed to create folder: ${message}`);
          }
        }),
    );
  }
}

const DEFAULT_PLACEHOLDER: Record<StringKey, string> = {
  backendUrl: "http://localhost:8001",
  apiKey: "",
  rootFolder: "PipGraph",
  inboxRelativePath: "00_Inbox",
  draftsRelativePath: "drafts",
};
