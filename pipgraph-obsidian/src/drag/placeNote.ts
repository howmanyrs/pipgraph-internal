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

export function describeError(err: unknown): string {
  if (err instanceof PipGraphApiError) {
    if (err.kind === "network") return "backend unreachable";
    if (err.kind === "timeout") return "backend timed out";
    return err.message;
  }
  return err instanceof Error ? err.message : String(err);
}
