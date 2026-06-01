/**
 * Folder ↔ Entity mirror (M2.5-partial).
 *
 * Makes the vault the source of truth for PARA folder structure: every folder
 * under `<root>` (except the Inbox subtree) is mirrored to a `(:Entity:Area)`
 * in Neo4j, bound by `file_path`, and its place in the tree becomes the
 * `BELONGS_TO` hierarchy. The flow is one-directional by initiative
 * (vault → graph): the user creates/deletes folders natively in Obsidian and
 * the plugin mirrors the change.
 *
 * Auto-mirroring (create / rename-promote / reconcile blanket-create) only
 * happens when `settings.autoMirrorFolders` is on. Regardless of that flag,
 * freshly-created "Untitled" folders are never sent — Obsidian's native
 * "New folder" always creates an "Untitled" placeholder first and only renames
 * it once the user types a name, so we wait for that rename. A folder can
 * always be mirrored explicitly via the file-explorer context menu
 * ("PipGraph: Sync folder to backend"), which is gated to managed folders.
 *
 * Scope of this partial:
 *  - create  → `ensureEntityForFolder` (idempotent on file_path; parent edge
 *              derived from `folder.parent`). Skipped for "Untitled" blanks.
 *  - rename  → if the old path had an entity → stale until rename-sync (S8,
 *              log-warning stub). If it never did (its "Untitled" create was
 *              skipped) → treat the rename into a real name as the deferred
 *              create.
 *  - delete  → cascade: delete the folder's entity + every Episodic whose only
 *              MENTIONS pointed at it (server-side, orphan-aware).
 *  - onload  → reconcile (root-first ensure + orphan detection + decorations).
 *
 * Deletion is a hard delete here, intended for the mirror flow and manual
 * debugging. A bi-temporal soft-invalidation model (Graphiti
 * `expired_at`/`invalid_at`) is the conceptual successor, deferred on purpose.
 */

import { Notice, TAbstractFile, TFolder } from "obsidian";
import type PipGraphPlugin from "../main";
import {
  isManagedFolderPath,
  type PipGraphSettings,
} from "../settings/PipGraphSettings";
import { FolderDecorator } from "./folderDecoration";
import { PipGraphApiError } from "../backend";
import type { ParaEntity } from "../backend";

export class FolderMirror {
  private readonly plugin: PipGraphPlugin;
  private readonly decorator: FolderDecorator;

  // Shadow set of managed folder paths currently known to exist. Kept in sync
  // with vault events so a folder `delete` (which fires only for the deleted
  // root, not its children) can still find descendant folders to clean up.
  private shadow: Set<string> = new Set();

  // In-flight ensure() promises keyed by path. Guards the TOCTOU race when a
  // nested folder is created: the child's own `create` event and the parent's
  // recursive ensure can otherwise both miss the file_path lookup and create
  // duplicate entities.
  private inFlight: Map<string, Promise<string>> = new Map();

  constructor(plugin: PipGraphPlugin) {
    this.plugin = plugin;
    this.decorator = new FolderDecorator(plugin.app);
  }

  private get settings(): PipGraphSettings {
    return this.plugin.settings;
  }

  /** Always read the live client — it is rebuilt when settings change. */
  private get client() {
    return this.plugin.client;
  }

  /** Wire vault events + run the initial reconcile once the layout is ready. */
  start(): void {
    this.plugin.app.workspace.onLayoutReady(() => {
      this.registerEvents();
      this.decorator.start();
      void this.reconcile();
    });
  }

  stop(): void {
    this.decorator.stop();
  }

  // --------------------------------------------------------------------------
  // Events
  // --------------------------------------------------------------------------

  private registerEvents(): void {
    const { plugin } = this;
    const { vault } = plugin.app;

    plugin.registerEvent(
      vault.on("create", (file) => this.handleCreate(file)),
    );
    plugin.registerEvent(
      vault.on("delete", (file) => this.handleDelete(file)),
    );
    plugin.registerEvent(
      vault.on("rename", (file, oldPath) => this.handleRename(file, oldPath)),
    );

    // Context menu — appears ONLY when right-clicking a managed folder (under
    // root, not Inbox). Keeps the rest of Obsidian's UI untouched. Works
    // regardless of the auto-mirror flag — it's an explicit user action.
    plugin.registerEvent(
      plugin.app.workspace.on("file-menu", (menu, file) => {
        if (!(file instanceof TFolder)) return;
        if (!isManagedFolderPath(this.settings, file.path)) return;
        menu.addItem((item) =>
          item
            .setTitle("PipGraph: Sync folder to backend")
            .setIcon("sync")
            .onClick(() => void this.syncFolderManually(file)),
        );
      }),
    );
  }

  private handleCreate(file: TAbstractFile): void {
    if (!(file instanceof TFolder)) return;
    if (!this.settings.autoMirrorFolders) return;
    if (!isManagedFolderPath(this.settings, file.path)) return;
    // Native "New folder" creates an "Untitled" placeholder first; wait for
    // the user to rename it before mirroring (see handleRename promote path).
    if (isDefaultFolderName(file.name)) return;

    void this.ensureEntityForFolder(file)
      .then(() => this.refreshDecorations())
      .catch((err) =>
        console.warn(
          `[pipgraph] ensureEntityForFolder failed for ${file.path}`,
          err,
        ),
      );
  }

  /** Explicit, flag-independent mirror of one folder (context-menu action). */
  private async syncFolderManually(folder: TFolder): Promise<void> {
    try {
      await this.ensureEntityForFolder(folder);
      await this.refreshDecorations();
      new Notice(`PipGraph: synced "${folder.name}" to backend.`);
    } catch (err) {
      console.warn(`[pipgraph] manual sync failed for ${folder.path}`, err);
      new Notice(`PipGraph: failed to sync "${folder.name}" (see console).`);
    }
  }

  private handleDelete(file: TAbstractFile): void {
    if (!(file instanceof TFolder)) return;
    // Only act if the deleted path is (or contains) something we manage.
    const underRoot =
      isManagedFolderPath(this.settings, file.path) ||
      [...this.shadow].some((p) => p.startsWith(`${file.path}/`));
    if (!underRoot) return;

    void this.cascadeDeleteFolder(file.path).catch((err) =>
      console.warn(`[pipgraph] cascadeDeleteFolder failed for ${file.path}`, err),
    );
  }

  private handleRename(file: TAbstractFile, oldPath: string): void {
    if (!(file instanceof TFolder)) return;
    const wasManaged = isManagedFolderPath(this.settings, oldPath);
    const isManaged = isManagedFolderPath(this.settings, file.path);
    if (!wasManaged && !isManaged) return;

    // Keep the shadow set aligned with the vault so future deletes resolve the
    // right paths, regardless of what we do with the graph entity.
    this.rebuildShadow();

    void this.onFolderRenamed(file, oldPath).catch((err) =>
      console.warn(`[pipgraph] rename handling failed for ${file.path}`, err),
    );
  }

  /**
   * A managed folder was renamed/moved. Two cases, decided by whether the OLD
   * path was ever mirrored:
   *  - had an entity → a genuine rename of a mirrored folder. The graph entity
   *    can't follow yet (needs PATCH /para-entity, S8) — log + notify, stale.
   *  - had none → its "Untitled" create was skipped; the rename into a real
   *    name is the deferred create. Mirror it now (auto-mirror on, managed
   *    target, non-blank name).
   */
  private async onFolderRenamed(
    folder: TFolder,
    oldPath: string,
  ): Promise<void> {
    const existing = await this.client.listParaEntities({ filePath: oldPath });

    if (existing.length > 0) {
      console.warn(
        `[pipgraph] folder renamed ${oldPath} → ${folder.path}; ` +
          `graph entity not updated yet (rename-sync pending, S8). Entity is stale.`,
      );
      new Notice(
        "PipGraph: folder renamed — graph not updated yet (rename sync pending).",
      );
      return;
    }

    if (
      this.settings.autoMirrorFolders &&
      isManagedFolderPath(this.settings, folder.path) &&
      !isDefaultFolderName(folder.name)
    ) {
      await this.ensureEntityForFolder(folder);
      await this.refreshDecorations();
    }
  }

  // --------------------------------------------------------------------------
  // ensureEntityForFolder — single chokepoint (idempotent + FS-derived parent)
  // --------------------------------------------------------------------------

  /**
   * Ensure a `(:Entity:Area)` exists for `folder`, creating it (and, lazily,
   * its managed ancestors) if needed. Returns the entity UUID. Idempotent on
   * `file_path`; concurrent calls for the same path share one promise.
   */
  async ensureEntityForFolder(folder: TFolder): Promise<string> {
    const pending = this.inFlight.get(folder.path);
    if (pending) return pending;

    const run = this.doEnsure(folder).finally(() =>
      this.inFlight.delete(folder.path),
    );
    this.inFlight.set(folder.path, run);
    return run;
  }

  private async doEnsure(folder: TFolder): Promise<string> {
    // 1. Idempotency — entity already bound to this path?
    const existing = await this.client.listParaEntities({
      filePath: folder.path,
    });
    if (existing.length > 0) {
      this.shadow.add(folder.path);
      return existing[0].uuid;
    }

    // 2. Parent from the filesystem hierarchy (BELONGS_TO). A folder directly
    //    under root has a non-managed parent (the root) → no edge (top-level).
    let parentUuid: string | undefined;
    const parent = folder.parent;
    if (parent && isManagedFolderPath(this.settings, parent.path)) {
      parentUuid = await this.ensureEntityForFolder(parent);
    }

    // 3. Create the node with an empty summary (the marker highlights it).
    const entity = await this.client.createParaEntity({
      name: folder.name,
      para_type: "Area",
      file_path: folder.path,
    });

    // 4. Link to parent: (child)-[:BELONGS_TO]->(parent).
    if (parentUuid) {
      await this.client.linkParaNodes({
        source_entity_uuid: entity.uuid,
        target_entity_uuid: parentUuid,
      });
    }

    this.shadow.add(folder.path);
    return entity.uuid;
  }

  // --------------------------------------------------------------------------
  // Cascade delete
  // --------------------------------------------------------------------------

  /**
   * A folder was deleted in the vault. Delete its entity and the entities of
   * any managed descendant folders (Obsidian fires a single `delete` for the
   * branch root). Each entity delete cascades to its orphaned Episodics on the
   * backend.
   */
  private async cascadeDeleteFolder(deletedPath: string): Promise<void> {
    const targets = [...this.shadow]
      .filter((p) => p === deletedPath || p.startsWith(`${deletedPath}/`))
      .sort((a, b) => b.split("/").length - a.split("/").length); // deepest first

    // The deleted path itself may not be in the shadow set (e.g. created while
    // the backend was offline) — include it so we still resolve its entity.
    if (!targets.includes(deletedPath)) targets.unshift(deletedPath);

    let deletedEntities = 0;
    let deletedEpisodics = 0;

    for (const path of targets) {
      try {
        const entities = await this.client.listParaEntities({ filePath: path });
        for (const entity of entities) {
          const res = await this.client.deleteParaEntityCascade(entity.uuid);
          deletedEntities += 1;
          deletedEpisodics += res.deleted_episodics_count;
        }
      } catch (err) {
        console.warn(`[pipgraph] failed to delete entity for ${path}`, err);
      }
      this.shadow.delete(path);
    }

    if (deletedEntities > 0) {
      new Notice(
        `PipGraph: removed ${deletedEntities} folder node(s)` +
          (deletedEpisodics > 0 ? `, ${deletedEpisodics} note(s)` : "") +
          ".",
      );
    }
    await this.refreshDecorations();
  }

  // --------------------------------------------------------------------------
  // Reconcile (onload)
  // --------------------------------------------------------------------------

  async reconcile(): Promise<void> {
    try {
      this.rebuildShadow();

      // Phase 1: vault → graph, root-first so parents exist before children.
      // Only when auto-mirror is on — otherwise mirroring is explicit-only and
      // reconcile must not create entities for folders the user didn't sync.
      // "Untitled" blanks are skipped either way.
      if (this.settings.autoMirrorFolders) {
        const folders = this.listManagedFolders()
          .filter((f) => !isDefaultFolderName(f.name))
          .sort((a, b) => a.path.split("/").length - b.path.split("/").length);
        for (const folder of folders) {
          try {
            await this.ensureEntityForFolder(folder);
          } catch (err) {
            console.warn(
              `[pipgraph] reconcile ensure failed for ${folder.path}`,
              err,
            );
          }
        }
      }

      // Phase 2: graph → vault. Surface entities whose folder is gone, but do
      // NOT auto-delete — that's destructive and only happens on an explicit
      // folder delete.
      const entities = await this.client.listParaEntities({ limit: 1000 });
      for (const entity of entities) {
        if (
          entity.file_path &&
          !this.plugin.app.vault.getAbstractFileByPath(entity.file_path)
        ) {
          console.warn(
            `[pipgraph] orphan entity ${entity.uuid} at ${entity.file_path} ` +
              `(folder no longer exists)`,
          );
        }
      }

      this.applyDecorations(entities);
    } catch (err) {
      if (err instanceof PipGraphApiError && err.kind === "network") {
        console.warn("[pipgraph] folder reconcile skipped — backend offline");
      } else {
        console.warn("[pipgraph] folder reconcile failed", err);
      }
    }
  }

  // --------------------------------------------------------------------------
  // Decorations
  // --------------------------------------------------------------------------

  private async refreshDecorations(): Promise<void> {
    try {
      const entities = await this.client.listParaEntities({ limit: 1000 });
      this.applyDecorations(entities);
    } catch (err) {
      console.warn("[pipgraph] refreshDecorations failed", err);
    }
  }

  private applyDecorations(entities: ParaEntity[]): void {
    const marked = new Set<string>();
    for (const entity of entities) {
      if (entity.file_path && !hasSummary(entity.summary)) {
        marked.add(entity.file_path);
      }
    }
    this.decorator.setMarkedPaths(marked);
  }

  // --------------------------------------------------------------------------
  // Shadow set helpers
  // --------------------------------------------------------------------------

  private rebuildShadow(): void {
    this.shadow = new Set(this.listManagedFolders().map((f) => f.path));
  }

  private listManagedFolders(): TFolder[] {
    return this.plugin.app.vault
      .getAllLoadedFiles()
      .filter(
        (f): f is TFolder =>
          f instanceof TFolder && isManagedFolderPath(this.settings, f.path),
      );
  }
}

function hasSummary(summary: string | null | undefined): boolean {
  return typeof summary === "string" && summary.trim().length > 0;
}

/**
 * Obsidian's native "New folder" creates an "Untitled" placeholder (then
 * "Untitled 1", "Untitled 2", … on collision) and drops the user straight into
 * rename mode. We never auto-mirror such a blank — we wait for the rename.
 */
function isDefaultFolderName(name: string): boolean {
  return /^Untitled( \d+)?$/.test(name);
}
