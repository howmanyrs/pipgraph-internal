import { Notice, TFile, TFolder } from "obsidian";
import type PipGraphPlugin from "../main";
import { resolveUniqueFilePath } from "../vault/paths";
import { PipGraphApiError } from "../backend";

/**
 * Move a note into a PARA folder and link it to that folder's entity in one act
 * (move+link, E7) — the shared core behind drag-to-place and the ghost-tree
 * "Confirm placement here". Vault-first: move the file, then record placement
 * via `place-episode` with the real, collision-resolved post-move path.
 *
 * Returns true when the graph link succeeded. On a partial outcome (file moved
 * but linking failed) it surfaces a notice, refreshes panels, and returns false
 * — the file already landed where the user asked; a later sync reconciles.
 */
export async function placeNoteInFolder(
  plugin: PipGraphPlugin,
  file: TFile,
  folderPath: string,
): Promise<boolean> {
  const { app, client } = plugin;

  const folder = app.vault.getAbstractFileByPath(folderPath);
  if (!(folder instanceof TFolder)) return false;

  // Resolve-then-act (1): note → episode.
  let episode;
  try {
    episode = await client.resolveEpisodicByPath(file.path);
  } catch (err) {
    new Notice(`PipGraph: ${describeError(err)}`);
    return false;
  }
  if (!episode) {
    new Notice("This note isn't in PipGraph yet — capture it first.");
    return false;
  }

  // Resolve-then-act (2): folder → entity.
  let entity;
  try {
    entity = (await client.listParaEntities({ filePath: folderPath }))[0];
  } catch (err) {
    new Notice(`PipGraph: ${describeError(err)}`);
    return false;
  }
  if (!entity) {
    new Notice(
      `"${folder.name}" has no graph node yet — sync the folder first.`,
    );
    return false;
  }

  // Resolve-then-act (3): compute the collision-resolved target path. If the
  // note is already in this folder, keep its path (re-link only, no move).
  const alreadyHere = file.parent?.path === folderPath;
  const targetPath = alreadyHere
    ? file.path
    : resolveUniqueFilePath(app.vault, folderPath, file.basename);

  // Move the file first (vault), then record placement in the graph.
  if (!alreadyHere) {
    try {
      await app.fileManager.renameFile(file, targetPath);
    } catch (err) {
      new Notice(`PipGraph: couldn't move the note: ${describeError(err)}`);
      return false;
    }
  }

  try {
    // process:true — move+link is synchronous, but the heavy extraction
    // pipeline runs as a server-side job (P2). The call returns immediately
    // with the node stamped status="process_existing_episode"; we watch it via
    // the in-memory ProcessingTracker until it settles (non-blocking).
    await client.placeEpisode({
      episodic_uuid: episode.uuid,
      entity_uuid: entity.uuid,
      file_path: targetPath,
      process: true,
    });
  } catch (err) {
    // Best-effort: the file already moved on disk. Surface the graph failure
    // rather than rolling the move back; a later sync reconciles.
    new Notice(
      `Note moved to ${folder.name}, but linking it in PipGraph failed: ${describeError(err)}`,
    );
    plugin.refreshTriagePanels();
    return false;
  }

  plugin.processing.track(episode.uuid, targetPath);
  // If this note was fallback-named (`❗`), placing it overwrites
  // `failed:generate_episode_name` with `process_existing_episode` — so the
  // fallback marker yields to the processing `⟳`. Drop it from the naming set.
  plugin.naming.clear(episode.uuid);
  new Notice(`Placed in ${folder.name} — processing…`);
  plugin.refreshTriagePanels();
  return true;
}

/**
 * Place several notes into one folder, sequentially (inbox-tuning 01, §4). Each
 * note goes through the same single-note {@link placeNoteInFolder} — its own
 * move + link + enqueue — so the per-note contract is unchanged; we just drive
 * it in a loop. Sequential (not parallel) keeps the existing server queue happy
 * and avoids interleaved notices. Returns the counts; callers report/clean up.
 */
export async function placeNotesInFolder(
  plugin: PipGraphPlugin,
  files: TFile[],
  folderPath: string,
): Promise<{ placed: number; failed: number }> {
  let placed = 0;
  let failed = 0;
  for (const file of files) {
    const ok = await placeNoteInFolder(plugin, file, folderPath);
    if (ok) placed += 1;
    else failed += 1;
  }
  return { placed, failed };
}

/**
 * Place a note on a folder, carrying the checked batch only when the gesture
 * note itself belongs to that batch (inbox-tuning 01, §4; refines D1).
 *
 * The "checked group" is every visually-checked Inbox row = the primary
 * (`lastInboxSelectionPath`, always checked+locked) plus `inboxBatch`.
 *  - Gesture note IS in the group → place the whole group together
 *    (`dedup([primary, ...inboxBatch])`) and clear the batch.
 *  - Gesture note is OUTSIDE the group → it's a standalone placement: only that
 *    note moves, the checked batch is left untouched (owner decision — dragging
 *    an unchecked note into any folder must not drag the batch along).
 *
 * The single call site for confirm-menu placement, ghost-drop, and drag-drop.
 */
export async function placeBatch(
  plugin: PipGraphPlugin,
  gestureFile: TFile,
  folderPath: string,
): Promise<{ placed: number; failed: number }> {
  const primary = plugin.lastInboxSelectionPath;
  const inGroup =
    gestureFile.path === primary || plugin.inboxBatch.has(gestureFile.path);

  // Standalone: a note dragged from outside the checked group goes alone.
  if (!inGroup) {
    return placeNotesInFolder(plugin, [gestureFile], folderPath);
  }

  // Group: the gesture note + the primary + every checked note, deduped.
  const files: TFile[] = [gestureFile];
  const seen = new Set<string>([gestureFile.path]);
  const members = primary ? [primary, ...plugin.inboxBatch] : [...plugin.inboxBatch];
  for (const path of members) {
    if (seen.has(path)) continue;
    seen.add(path);
    const f = plugin.app.vault.getAbstractFileByPath(path);
    if (f instanceof TFile) files.push(f);
  }

  const result = await placeNotesInFolder(plugin, files, folderPath);
  if (result.placed > 0) plugin.clearInboxBatch();
  return result;
}

export function describeError(err: unknown): string {
  if (err instanceof PipGraphApiError) {
    if (err.kind === "network") return "backend unreachable";
    if (err.kind === "timeout") return "backend timed out";
    return err.message;
  }
  return err instanceof Error ? err.message : String(err);
}
