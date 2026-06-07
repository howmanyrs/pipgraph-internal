import { Notice, TFile, TFolder } from "obsidian";
import type PipGraphPlugin from "../main";
import {
  getDraftsPath,
  getInboxPath,
} from "../settings/PipGraphSettings";
import { NewInboxNoteModal } from "../modals/NewInboxNoteModal";
import {
  PipGraphApiError,
  isFailedStatus,
  isSettledStatus,
} from "../backend";
import { resolveUniqueFilePath, sanitiseForFilename } from "../vault/paths";

const REGEN_POLL_INTERVAL_MS = 1500;
const REGEN_POLL_MAX_ATTEMPTS = 60; // ~90s, mirrors the capture outbox

export function registerCommands(plugin: PipGraphPlugin): void {
  plugin.addCommand({
    id: "open-triage-panel",
    name: "Open triage panel",
    callback: () => {
      void plugin.activateTriagePanel();
    },
  });

  plugin.addCommand({
    id: "new-inbox-note",
    name: "New inbox note",
    callback: () => {
      new NewInboxNoteModal(plugin).open();
    },
  });

  plugin.addCommand({
    id: "draft-inbox-note",
    name: "New draft inbox note",
    callback: () => {
      void createDraftNote(plugin);
    },
  });

  plugin.addCommand({
    id: "process-current-draft",
    name: "Process current draft",
    checkCallback: (checking) => {
      const file = plugin.app.workspace.getActiveFile();
      const draftsPath = `${getDraftsPath(plugin.settings)}/`;
      const isDraft =
        file !== null &&
        file.extension === "md" &&
        file.path.startsWith(draftsPath);
      if (!isDraft) return false;
      if (checking) return true;
      void processDraft(plugin, file!);
      return true;
    },
  });

  plugin.addCommand({
    id: "refresh-triage",
    name: "Refresh triage queue",
    callback: () => {
      plugin.refreshTriagePanels();
    },
  });

  plugin.addCommand({
    // id kept stable (was "Retry failed processing") so existing hotkeys survive.
    id: "retry-failed-processing",
    name: "Process all failed notes",
    checkCallback: (checking) => {
      const failedCount = plugin.processing.failedCount;
      if (failedCount === 0) return false;
      if (checking) return true;
      void retryFailedProcessing(plugin, failedCount);
      return true;
    },
  });

  plugin.addCommand({
    id: "sync-from-backend",
    name: "Sync from backend",
    callback: () => {
      new Notice("Sync from backend: not implemented yet — coming in M4.");
    },
  });

  plugin.addCommand({
    id: "auto-process-inbox",
    name: "Auto-process inbox",
    callback: () => {
      new Notice(
        "Auto-process inbox: not implemented yet — coming in M8 Phase 1.",
      );
    },
  });

  registerFailedNoteMenu(plugin);
  registerFallbackNameMenu(plugin);
}

/**
 * Per-file "Process note" item on the file-explorer context menu, shown only
 * for notes currently in the failed-processing set (process-queue P3). It
 * retries exactly that note — the single-note counterpart of the "Process all
 * failed notes" command. Visibility + the retry target both come from the
 * tracker's in-memory uuid↔path map, so no backend round-trip on right-click.
 */
function registerFailedNoteMenu(plugin: PipGraphPlugin): void {
  plugin.registerEvent(
    plugin.app.workspace.on("file-menu", (menu, file) => {
      if (!(file instanceof TFile) || file.extension !== "md") return;
      const uuid = plugin.processing.failedUuidForPath(file.path);
      if (!uuid) return;
      menu.addItem((item) => {
        item
          .setTitle("Process note")
          .setIcon("refresh-cw")
          .onClick(() => {
            void processFailedNote(plugin, uuid, file.basename);
          });
      });
    }),
  );
}

async function processFailedNote(
  plugin: PipGraphPlugin,
  uuid: string,
  name: string,
): Promise<void> {
  const ok = await plugin.processing.retryOne(uuid);
  new Notice(
    ok
      ? `Processing "${name}"…`
      : `Couldn't re-queue "${name}" (backend unreachable?).`,
  );
}

/**
 * Per-file "Regenerate name with LLM" item, shown only for materialised
 * fallback-named notes — those the NamingTracker flags `❗` (inbox-in-process,
 * Model 2). Re-runs the naming job and, on success, renames the file in-folder
 * to the new LLM name. Mirror of {@link registerFailedNoteMenu}: visibility +
 * target both come from the tracker's in-memory uuid↔path map.
 */
function registerFallbackNameMenu(plugin: PipGraphPlugin): void {
  plugin.registerEvent(
    plugin.app.workspace.on("file-menu", (menu, file) => {
      if (!(file instanceof TFile) || file.extension !== "md") return;
      const uuid = plugin.naming.uuidForPath(file.path);
      if (!uuid) return;
      menu.addItem((item) => {
        item
          .setTitle("Regenerate name with LLM")
          .setIcon("sparkles")
          .onClick(() => {
            void regenerateName(plugin, uuid, file);
          });
      });
    }),
  );
}

/**
 * Re-enqueue the naming job for a fallback-named note and, on a fresh LLM name,
 * rename the file **in the same folder** (the E6 guard allows first-bind +
 * same-folder rename) and sync `file_path`. Obsidian fixes `[[links]]` across
 * the rename. On another fallback the file is left untouched and the `❗` stays.
 *
 * No new endpoint: re-POST /episode with the current `file_path` preserved
 * re-enqueues naming (idempotent MERGE on uuid).
 */
export async function regenerateName(
  plugin: PipGraphPlugin,
  uuid: string,
  file: TFile,
): Promise<void> {
  // Captured up front: the file may be renamed before we unmark, so we always
  // clear the `⟳` against the *original* path (where it was set).
  const startPath = file.path;
  await withRegenerating(plugin, startPath, () =>
    runRegeneration(plugin, uuid, file),
  );
}

/** Show the in-flight `⟳`/statusbar while `job` runs, clearing it on any exit. */
async function withRegenerating(
  plugin: PipGraphPlugin,
  path: string,
  job: () => Promise<void>,
): Promise<void> {
  plugin.naming.markRegenerating(path);
  try {
    await job();
  } finally {
    plugin.naming.unmarkRegenerating(path);
  }
}

async function runRegeneration(
  plugin: PipGraphPlugin,
  uuid: string,
  file: TFile,
): Promise<void> {
  const { app, client } = plugin;

  let content: string;
  try {
    content = await app.vault.read(file);
  } catch (err) {
    new Notice(`Couldn't read the note: ${describeError(err)}`);
    return;
  }

  new Notice(`Regenerating a name for "${file.basename}"…`);
  try {
    // Re-enqueue naming, preserving file_path so the node stays bound here.
    await client.createEpisode({
      uuid,
      content,
      file_path: file.path,
      generate_name: true,
    });
  } catch (err) {
    new Notice(`Couldn't start regeneration: ${describeError(err)}`);
    return;
  }

  // Poll until the naming job settles (cleared = real name; failed = fallback).
  for (let attempt = 0; attempt < REGEN_POLL_MAX_ATTEMPTS; attempt++) {
    await sleep(REGEN_POLL_INTERVAL_MS);
    let episodic;
    try {
      episodic = await client.getEpisodicByUuid(uuid);
    } catch {
      continue; // transient hiccup — keep polling
    }
    if (!episodic) continue;

    if (isFailedStatus(episodic.status)) {
      // Fell back again — leave the file and the `❗` as they are.
      new Notice("Still couldn't auto-name this note. The fallback name stays.");
      return;
    }
    if (isSettledStatus(episodic.status)) {
      await applyRegeneratedName(plugin, uuid, file, episodic.name);
      return;
    }
  }
  new Notice("Naming is taking a while — it'll resync on the next reload.");
}

/** Same-folder rename to the new LLM name + file_path sync; clears the `❗`. */
async function applyRegeneratedName(
  plugin: PipGraphPlugin,
  uuid: string,
  file: TFile,
  name: string,
): Promise<void> {
  const { app, client } = plugin;
  const dir = file.parent?.path ?? "";
  const base = sanitiseForFilename(name);
  const target = resolveUniqueFilePath(app.vault, dir, base);

  try {
    await app.fileManager.renameFile(file, target);
  } catch (err) {
    new Notice(`Got a name, but renaming the file failed: ${describeError(err)}`);
    return;
  }

  try {
    await client.updateEpisodic(uuid, { file_path: target });
  } catch (err) {
    // The file moved but the node's path lagged — naming.reconcile() re-syncs.
    new Notice(
      `Renamed, but recording the new path failed: ${describeError(err)}. ` +
        `It'll resync on the next reload.`,
    );
    return;
  }

  plugin.naming.clear(uuid);
  new Notice(`Renamed to "${base}".`);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function retryFailedProcessing(
  plugin: PipGraphPlugin,
  failedCount: number,
): Promise<void> {
  new Notice(`Retrying ${failedCount} failed note(s)…`);
  const retried = await plugin.processing.retryFailed();
  if (retried < failedCount) {
    new Notice(
      `Re-queued ${retried} of ${failedCount}; the rest stayed failed (backend unreachable?).`,
    );
  }
}

async function createDraftNote(plugin: PipGraphPlugin): Promise<void> {
  const { app } = plugin;
  const draftsPath = getDraftsPath(plugin.settings);

  const existing = app.vault.getAbstractFileByPath(draftsPath);
  if (existing && !(existing instanceof TFolder)) {
    new Notice(`"${draftsPath}" exists but is not a folder.`);
    return;
  }
  if (!existing) {
    try {
      await app.vault.createFolder(draftsPath);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      new Notice(`Failed to create drafts folder: ${message}`);
      return;
    }
  }

  const stamp = new Date()
    .toISOString()
    .replace(/[:.]/g, "")
    .replace("T", "-");
  const path = `${draftsPath}/Draft-${stamp}.md`;

  let file: TFile;
  try {
    file = await app.vault.create(path, "");
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    new Notice(`Failed to create draft: ${message}`);
    return;
  }

  await app.workspace.getLeaf(false).openFile(file);
}

async function processDraft(
  plugin: PipGraphPlugin,
  file: TFile,
): Promise<void> {
  const { app } = plugin;
  const body = await app.vault.read(file);
  if (!body.trim()) {
    new Notice("Draft is empty — type something before processing.");
    return;
  }

  const inboxPath = getInboxPath(plugin.settings);
  const targetPath = `${inboxPath}/${file.name}`;
  if (app.vault.getAbstractFileByPath(targetPath)) {
    new Notice(
      `Cannot move draft: "${targetPath}" already exists. Rename the draft first.`,
    );
    return;
  }

  // Unlike the capture modal, the final path is known up front here (we abort
  // above if the target is taken, rather than auto-resolving a suffix), so
  // file_path is set at create time and no follow-up PATCH is needed.
  // TODO(E3, Q3 §1.1): stamp `pipgraph.uuid` into frontmatter once writes land.
  try {
    await plugin.client.createEpisode({
      name: file.basename,
      content: body,
      file_path: targetPath,
      source_description: "obsidian:process-draft",
    });
  } catch (err) {
    new Notice(`Failed to process draft: ${describeError(err)}`);
    return;
  }

  try {
    await app.fileManager.renameFile(file, targetPath);
  } catch (err) {
    new Notice(
      `Episodic created in Neo4j, but moving the file failed: ${describeError(err)}`,
    );
    return;
  }

  new Notice("Draft processed.");
}

function describeError(err: unknown): string {
  if (err instanceof PipGraphApiError) {
    if (err.kind === "network") return "backend unreachable";
    if (err.kind === "timeout") return "backend timed out";
    return err.message;
  }
  return err instanceof Error ? err.message : String(err);
}
