import { AbstractInputSuggest, App, TFolder } from "obsidian";

export class FolderSuggest extends AbstractInputSuggest<TFolder> {
  constructor(
    app: App,
    private readonly inputEl: HTMLInputElement,
    private readonly onPick: (path: string) => void,
  ) {
    super(app, inputEl);
  }

  protected getSuggestions(query: string): TFolder[] {
    const lower = query.toLowerCase();
    const matches: TFolder[] = [];
    for (const file of this.app.vault.getAllLoadedFiles()) {
      if (file instanceof TFolder && file.path.toLowerCase().includes(lower)) {
        matches.push(file);
      }
    }
    return matches;
  }

  renderSuggestion(folder: TFolder, el: HTMLElement): void {
    el.setText(folder.path || "/");
  }

  selectSuggestion(folder: TFolder): void {
    this.inputEl.value = folder.path;
    this.onPick(folder.path);
    this.close();
  }
}
