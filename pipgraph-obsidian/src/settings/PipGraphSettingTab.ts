import {
  App,
  Notice,
  PluginSettingTab,
  Setting,
  TFolder,
  debounce,
} from "obsidian";
import type PipGraphPlugin from "../main";
import { FolderSuggest } from "./FolderSuggest";
import type {
  LlmConfigState,
  LlmProvider,
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
  inboxRelativePath: "Inbox",
  draftsRelativePath: "drafts",
};
