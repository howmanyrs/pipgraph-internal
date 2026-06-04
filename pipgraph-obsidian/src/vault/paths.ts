import type { Vault } from "obsidian";

/**
 * Find a free `.md` path for `baseName` inside `folder`, suffixing ` (1)`,
 * ` (2)`, … on collision (mirrors Obsidian's own rename behaviour). Returns the
 * full vault-relative path. `baseName` must already be sanitised for filenames.
 *
 * Shared by the capture modal (Inbox) and drag-to-place (target PARA folder):
 * both need a collision-resolved path because the client owns the final path
 * (resolve-then-act, Decision E2).
 */
export function resolveUniqueFilePath(
  vault: Vault,
  folder: string,
  baseName: string,
): string {
  let candidate = `${baseName}.md`;
  if (!vault.getAbstractFileByPath(`${folder}/${candidate}`)) {
    return `${folder}/${candidate}`;
  }
  for (let i = 1; i < 1000; i++) {
    candidate = `${baseName} (${i}).md`;
    if (!vault.getAbstractFileByPath(`${folder}/${candidate}`)) {
      return `${folder}/${candidate}`;
    }
  }
  throw new Error(`Could not find a free filename in "${folder}".`);
}

/**
 * Turn an arbitrary string (e.g. an LLM-generated episode name) into a safe
 * Markdown filename base: strips path/illegal characters, collapses whitespace,
 * caps length. Never returns empty — falls back to "Untitled". The caller pairs
 * this with resolveUniqueFilePath, which appends `.md` and resolves collisions.
 *
 * Shared by the capture outbox (materialising into the Inbox) and any other
 * flow that derives a filename from backend-supplied text.
 */
export function sanitiseForFilename(name: string): string {
  const trimmed = name.replace(/[\\/:*?"<>|]/g, "_").trim();
  const collapsed = trimmed.replace(/\s+/g, " ");
  const limited = collapsed.slice(0, 100).trim();
  return limited.length > 0 ? limited : "Untitled";
}
