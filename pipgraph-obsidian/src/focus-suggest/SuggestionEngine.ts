import type PipGraphPlugin from "../main";
import type { ParaEntity } from "../backend";

/**
 * One score result for a target note: the full PARA entity list (the tree's
 * structure source) plus a uuid→score map from the backend's ranked
 * suggestions. A score absent from the map means "no/zero match" for that
 * folder, rendered as "—".
 */
export interface FolderScores {
  /** The episodic the scores were computed for (null = note not in PipGraph). */
  episodicUuid: string | null;
  /** Every PARA entity (folder). Tree structure is derived from `file_path`. */
  entities: ParaEntity[];
  /** uuid → score (0..1) from make-suggestions. */
  scoreByUuid: Map<string, number>;
}

// Ghost-tree shows every folder, so ask for many suggestions (not the default
// top-10) — the cap is presentational (Q7 §2), not a hard limit here.
const SUGGESTION_LIMIT = 50;
const ENTITY_LIMIT = 500;

/**
 * The single `folder_path → score` engine behind both M5b renderers (ghost-tree
 * and, later, badges). Resolve target note → episodic, ask the backend for
 * ranked PARA suggestions, and join the scores onto the full entity list.
 *
 * A target with no episodic (not captured yet) still yields the entity list with
 * an empty score map — the tree renders, every folder "—". Score source is live
 * `make-suggestions` (the `pipgraph.candidates` cache is deferred, Q7).
 */
export class SuggestionEngine {
  constructor(private readonly plugin: PipGraphPlugin) {}

  async scoreFor(filePath: string | null): Promise<FolderScores> {
    const client = this.plugin.client;
    const entities = await client.listParaEntities({ limit: ENTITY_LIMIT });

    const empty: FolderScores = {
      episodicUuid: null,
      entities,
      scoreByUuid: new Map(),
    };
    if (!filePath) return empty;

    const episode = await client.resolveEpisodicByPath(filePath);
    if (!episode) return empty;

    const suggestions = await client.makeSuggestions({
      episodic_uuid: episode.uuid,
      limit: SUGGESTION_LIMIT,
    });
    const scoreByUuid = new Map<string, number>();
    for (const s of suggestions) scoreByUuid.set(s.uuid, s.score);

    return { episodicUuid: episode.uuid, entities, scoreByUuid };
  }
}
