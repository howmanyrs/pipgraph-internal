import { Notice, TFile } from "obsidian";
import type PipGraphPlugin from "../main";
import { isManagedFolderPath } from "../settings/PipGraphSettings";
import { placeNoteInFolder } from "./placeNote";

/**
 * Drag-to-place: drag a note from the Inbox tab onto a PARA folder in the
 * file-explorer to **move + link** it (cluster step 3, Decision E4).
 *
 * Model: physical location ⟺ graph placement. A note in a PARA folder is
 * `MENTIONS`-linked to that folder's entity. The drop does both, in one
 * gesture, via the backend `place-episode` operation (E7).
 *
 * Mechanics:
 *  - Inbox rows are `draggable` and stamp the file path onto `dataTransfer`
 *    under our private MIME type (see TriagePanelView.renderInbox).
 *  - Drop targets are `.nav-folder-title[data-path]` rows — the same unofficial
 *    explorer DOM hook folderDecoration / folder-click already rely on. We gate
 *    on `isManagedFolderPath` (under root, not Inbox).
 *  - Order is **move file first, then backend place** (best-effort): mirrors the
 *    capture flow's vault-first model and lets us send the real, collision-
 *    resolved post-move path (E2). If the backend call fails the note still
 *    landed where the user dropped it; we surface a notice and the graph catches
 *    up on a later sync.
 *
 * Unofficial-API caveat: relies on `.nav-folder-title` markup. Additive — uses
 * `plugin.registerDomEvent`, so listeners are removed on plugin unload.
 */

export const PIPGRAPH_DRAG_MIME = "application/x-pipgraph-inbox";
const DROP_TARGET_CLASS = "pipgraph-drop-target";

export class DragToPlace {
  private currentTarget: HTMLElement | null = null;

  constructor(private readonly plugin: PipGraphPlugin) {}

  start(): void {
    const { plugin } = this;
    plugin.registerDomEvent(document, "dragover", (evt) => this.onDragOver(evt));
    plugin.registerDomEvent(document, "drop", (evt) => void this.onDrop(evt));
    plugin.registerDomEvent(document, "dragend", () => this.clearTarget());
  }

  private folderTitleAt(evt: DragEvent): HTMLElement | null {
    const target = evt.target as HTMLElement | null;
    return (
      (target?.closest?.(".nav-folder-title[data-path]") as HTMLElement | null) ??
      null
    );
  }

  private managedFolderPathAt(evt: DragEvent): {
    el: HTMLElement;
    path: string;
  } | null {
    const el = this.folderTitleAt(evt);
    const path = el?.getAttribute("data-path") ?? null;
    if (!el || !path || !isManagedFolderPath(this.plugin.settings, path)) {
      return null;
    }
    return { el, path };
  }

  private onDragOver(evt: DragEvent): void {
    // Only react to our own drags — leave native file-explorer drags alone.
    if (!evt.dataTransfer?.types.includes(PIPGRAPH_DRAG_MIME)) return;

    const hit = this.managedFolderPathAt(evt);
    if (!hit) {
      this.clearTarget();
      return;
    }
    // preventDefault marks this element as a valid drop target.
    evt.preventDefault();
    evt.dataTransfer.dropEffect = "move";
    if (this.currentTarget !== hit.el) {
      this.clearTarget();
      hit.el.classList.add(DROP_TARGET_CLASS);
      this.currentTarget = hit.el;
    }
  }

  private async onDrop(evt: DragEvent): Promise<void> {
    const sourcePath = evt.dataTransfer?.getData(PIPGRAPH_DRAG_MIME);
    if (!sourcePath) return; // not our drag

    const hit = this.managedFolderPathAt(evt);
    this.clearTarget();
    if (!hit) return; // dropped on Inbox/root/non-folder — silently ignore

    evt.preventDefault();
    await this.place(sourcePath, hit.path);
  }

  private clearTarget(): void {
    this.currentTarget?.classList.remove(DROP_TARGET_CLASS);
    this.currentTarget = null;
  }

  private async place(sourcePath: string, folderPath: string): Promise<void> {
    const file = this.plugin.app.vault.getAbstractFileByPath(sourcePath);
    if (!(file instanceof TFile)) {
      new Notice("PipGraph: couldn't find the dragged note.");
      return;
    }
    // move+link is shared with the ghost-tree "Confirm placement here".
    await placeNoteInFolder(this.plugin, file, folderPath);
  }
}
