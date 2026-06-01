/**
 * TypeScript types mirroring backend Pydantic schemas.
 *
 * Sources of truth:
 *  - backend/app/api/schemas/dev.py — authoritative
 *  - backend/app/api/endpoints/dev.py — actual URL paths & query params
 *
 * Reference (with caveats): pipgraph-web/src/lib/api.ts — sibling client over the
 * same backend. Useful for cross-checking shapes, but contains known drift bugs
 * (wrong query param for /episodic, wrong path for /para-entity/list). Always
 * verify against dev.py.
 *
 * Convention: each interface comments the Pydantic class it mirrors. When
 * backend schemas change, the comment makes the drift obvious at review time.
 */

// ============================================================================
// Shared
// ============================================================================

export type ParaType = "Project" | "Area" | "Resource" | "Archive";

// `ParaEntityProperty` in schemas/dev.py
export interface ParaEntity {
  uuid: string;
  name: string;
  para_type: ParaType;
  created_at?: string | null;
  summary?: string | null;
  // Client-side filesystem binding (vault folder mirroring this entity).
  // Read-projection only — NOT identity (use `uuid`). Resolve folder→entity via
  // listParaEntities({ filePath }). Also duplicated inside `attributes`.
  file_path?: string | null;
  attributes: Record<string, unknown>;
}

// Episodic node properties as serialised by dev.py endpoints
// (list_all_episodic, get_episodic_by_path, list_unlinked_episodic).
// Backend returns `dict` in schemas, so this shape is reconstructed from the
// serialisation code in dev.py. Keep additive — backend may add fields.
export interface EpisodicNode {
  uuid: string;
  name: string;
  created_at?: string | null;
  valid_at?: string | null;
  source?: string | null;
  content?: string | null;
  source_description?: string | null;
  group_id?: string | null;
  // Path to the source note; persisted top-level on the Episodic node.
  file_path?: string | null;
}

// `ParaSuggestion` in schemas/dev.py
export interface ParaSuggestion {
  uuid: string;
  name: string;
  para_type: ParaType;
  summary: string;
  score: number;
  attributes: Record<string, unknown>;
}

// ============================================================================
// Request inputs (what callers pass)
// ============================================================================

// `ProcessNoteRequest` in schemas/dev.py
export interface ProcessNoteInput {
  name: string;
  episode_body: string;
  source_description?: string;
  reference_time?: string; // ISO datetime
  use_para_entities?: boolean;
}

// `CreateEpisodeRequest` in schemas/dev.py
export interface CreateEpisodeInput {
  content: string;
  name?: string;
  source_description?: string;
  reference_time?: string; // ISO datetime
  file_path?: string;
  frontmatter?: Record<string, unknown>;
}

// `CreateParaEntityRequest` in schemas/dev.py
export interface CreateParaEntityInput {
  para_type: ParaType;
  name: string;
  summary?: string;
  group_id?: string;
  file_path?: string;
  attributes?: Record<string, unknown>;
}

// `LinkEntityEpisodeRequest` in schemas/dev.py
export interface LinkEntityEpisodeInput {
  episodic_uuid: string;
  entity_uuid: string;
  created_at?: string; // ISO datetime
}

// `LinkParaNodesRequest` in schemas/dev.py.
// Creates (source)-[:BELONGS_TO]->(target), i.e. source is the child,
// target is the parent in the PARA hierarchy.
export interface LinkParaNodesInput {
  source_entity_uuid: string;
  target_entity_uuid: string;
  created_at?: string; // ISO datetime
}

// `MakeSuggestionsRequest` in schemas/dev.py
export interface MakeSuggestionsInput {
  episodic_uuid: string;
  limit?: number; // 1..50, default 10
  min_score?: number; // 0.0..1.0, default 0.0
}

// ============================================================================
// Result payloads (what client returns, AFTER envelope unwrapping)
// ============================================================================

// `ProcessNoteResponse` minus `success`/`error`
export interface ProcessNoteResult {
  episode_uuid?: string;
  nodes_count: number;
  edges_count: number;
}

// `CreateEpisodeResponse` minus envelope
export interface CreateEpisodeResult {
  uuid: string;
  name: string;
  created_at?: string;
}

// `CreateParaEntityResponse` minus envelope
export interface CreateParaEntityResult {
  uuid: string;
  para_type: ParaType;
  name: string;
  created_at?: string;
}

// `LinkEntityEpisodeResponse` minus envelope
export interface LinkEntityEpisodeResult {
  edge_uuid: string;
  episodic_uuid: string;
  entity_uuid: string;
  created_at?: string;
}

// `LinkParaNodesResponse` minus envelope
export interface LinkParaNodesResult {
  edge_uuid: string;
  source_entity_uuid: string;
  target_entity_uuid: string;
  created_at?: string;
}

// `DeleteNodeResponse` minus envelope
export interface DeleteNodeResult {
  node_uuid: string;
  node_type: string;
}

// `DeleteParaEntityResponse` minus envelope.
// Cascade delete: the entity plus every Episodic whose only MENTIONS edge
// pointed at it.
export interface DeleteParaEntityResult {
  entity_uuid: string;
  deleted_episodics_count: number;
}

// ============================================================================
// Raw response envelopes (internal — used only inside the client)
//
// Every dev.py response follows the shape `{success: bool, error?: str, ...}`.
// We declare these for the request helper; consumers should not need them.
// ============================================================================

export interface Envelope {
  success: boolean;
  error?: string | null;
}

export interface ListEpisodicEnvelope extends Envelope {
  episodics: EpisodicNode[];
  count: number;
}

export interface GetEpisodicEnvelope extends Envelope {
  episodic?: EpisodicNode | null;
}

export interface ListParaEntitiesEnvelope extends Envelope {
  entities: ParaEntity[];
  count: number;
}

export interface MakeSuggestionsEnvelope extends Envelope {
  episodic_uuid?: string | null;
  suggestions: ParaSuggestion[];
  count: number;
}

export interface CreateEpisodeEnvelope extends Envelope {
  uuid?: string | null;
  name?: string | null;
  created_at?: string | null;
}

export interface CreateParaEntityEnvelope extends Envelope {
  uuid?: string | null;
  para_type?: ParaType | null;
  name?: string | null;
  created_at?: string | null;
}

export interface LinkEntityEpisodeEnvelope extends Envelope {
  edge_uuid?: string | null;
  episodic_uuid?: string | null;
  entity_uuid?: string | null;
  created_at?: string | null;
}

export interface LinkParaNodesEnvelope extends Envelope {
  edge_uuid?: string | null;
  source_entity_uuid?: string | null;
  target_entity_uuid?: string | null;
  created_at?: string | null;
}

export interface DeleteNodeEnvelope extends Envelope {
  node_uuid?: string | null;
  node_type?: string | null;
}

export interface DeleteParaEntityEnvelope extends Envelope {
  entity_uuid?: string | null;
  deleted_episodics_count?: number | null;
}

export interface ProcessNoteEnvelope extends Envelope {
  episode_uuid?: string | null;
  nodes_count: number;
  edges_count: number;
}
