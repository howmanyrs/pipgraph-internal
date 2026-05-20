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

type StringKey = "backendUrl" | "apiKey" | "rootFolder";

export class PipGraphSettingTab extends PluginSettingTab {
  private warningEl: HTMLDivElement | null = null;

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
  backendUrl: "http://localhost:8000",
  apiKey: "",
  rootFolder: "PipGraph",
};
