import type { App, TFile } from "obsidian";

/**
 * Read `pipgraph.uuid` from a note's YAML frontmatter via the metadata cache.
 *
 * Read-only groundwork for uuid-primary note resolution (Q3 §1.1, Decision E3).
 * The capture flow does not write this field yet, so in practice this returns
 * null today — it exists so the resolver can switch to a uuid-primary strategy
 * once frontmatter writes land, without a second pass over the call sites.
 *
 * Accepts both the canonical nested form
 *
 *   pipgraph:
 *     uuid: <id>
 *
 * and a flat `pipgraph.uuid: <id>` key, defensively.
 */
export function readPipgraphUuid(app: App, file: TFile): string | null {
  const fm = app.metadataCache.getFileCache(file)?.frontmatter;
  if (!fm) return null;

  const nested = (fm.pipgraph as { uuid?: unknown } | undefined)?.uuid;
  const flat = fm["pipgraph.uuid"];
  const raw = nested ?? flat;

  return typeof raw === "string" && raw.length > 0 ? raw : null;
}
