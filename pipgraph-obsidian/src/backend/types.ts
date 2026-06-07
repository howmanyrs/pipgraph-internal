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
  // Transient job-runner status (taxonomy in src/backend/status.ts): the job's
  // type key while a job is in flight ("generate_episode_name" /
  // "process_existing_episode"), "failed:<job>" on error, absent/null once
  // settled. Poll this until it clears; use the status.ts predicates, not "==".
  status?: string | null;
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
  // Client-supplied UUID (e.g. crypto.randomUUID()). The server MERGEs on it, so
  // re-posting the same UUID upserts the same Episodic instead of duplicating
  // (idempotent outbox delivery). Omit to let the server generate one.
  uuid?: string;
  // Defer name generation to the backend job queue: the node is created
  // immediately with a provisional name + status="generate_episode_name"; a
  // background job overwrites the name and clears status. Poll getEpisodicByUuid
  // until cleared.
  generate_name?: boolean;
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

// `UpdateParaEntityRequest` in schemas/dev.py.
// Only `summary` is editable for now (S8 partial); name/file_path are not
// handled yet. Fields left undefined are unchanged.
export interface UpdateParaEntityInput {
  summary?: string;
}

// `UpdateEpisodicRequest` in schemas/dev.py.
// Narrow by design (Episodic mirror of S1): only `file_path` is editable.
// Left undefined → unchanged. The client owns the final, collision-resolved
// path and writes it here after creating the file (resolve-then-act, E2).
export interface UpdateEpisodicInput {
  file_path?: string;
}

// `PlaceEpisodeRequest` in schemas/dev.py.
// Move+link in one act (E7): set the Episodic's `file_path` to its new
// (cross-folder) location AND MERGE the MENTIONS edge to the entity. Used by
// drag-from-Inbox-to-folder. The physical file move is the client's job; we
// pass the real post-move path here.
export interface PlaceEpisodeInput {
  episodic_uuid: string;
  entity_uuid: string;
  file_path: string;
  // If true, the backend enqueues the heavy extraction pipeline after linking
  // (P2): the node is stamped status="process_existing_episode" atomically with
  // the move+link, and the client polls getEpisodicByUuid until status clears.
  // Omit/false for plain move+link (synchronous).
  process?: boolean;
}

// `ProcessExistingEpisodeRequest` in schemas/dev.py.
// Re-run LLM extraction over an already-linked Episodic (≥1 MENTIONS).
export interface ProcessExistingEpisodeInput {
  episodic_uuid: string;
  update_communities?: boolean;
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
  // "generate_episode_name" when generate_name=true (an async naming job was
  // enqueued); null/absent otherwise. Poll getEpisodicByUuid until it clears.
  status?: string | null;
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

// `PlaceEpisodeResponse` minus envelope
export interface PlaceEpisodeResult {
  episodic: EpisodicNode;
  entity_uuid: string;
  edge_uuid?: string;
}

// `ProcessExistingEpisodeResponse` minus envelope
export interface ProcessExistingEpisodeResult {
  episode_uuid?: string;
  nodes_count: number;
  edges_count: number;
  episodic_edges_count: number;
  para_entities_updated: string[];
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

// `ClearGraphResponse` minus envelope. Full debug wipe — every node + edge.
export interface ClearGraphResult {
  deleted_nodes_count: number;
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

// `UpdateParaEntityResponse` in schemas/dev.py — returns the updated entity.
export interface UpdateParaEntityEnvelope extends Envelope {
  entity?: ParaEntity | null;
}

// `UpdateEpisodicResponse` in schemas/dev.py — returns the updated episodic.
export interface UpdateEpisodicEnvelope extends Envelope {
  episodic?: EpisodicNode | null;
}

// `PlaceEpisodeResponse` in schemas/dev.py.
export interface PlaceEpisodeEnvelope extends Envelope {
  episodic?: EpisodicNode | null;
  entity_uuid?: string | null;
  edge_uuid?: string | null;
}

// `ProcessExistingEpisodeResponse` in schemas/dev.py.
export interface ProcessExistingEpisodeEnvelope extends Envelope {
  episode_uuid?: string | null;
  nodes_count: number;
  edges_count: number;
  episodic_edges_count: number;
  para_entities_updated: string[];
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
  status?: string | null;
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

export interface ClearGraphEnvelope extends Envelope {
  deleted_nodes_count?: number | null;
}

export interface ProcessNoteEnvelope extends Envelope {
  episode_uuid?: string | null;
  nodes_count: number;
  edges_count: number;
}

// ============================================================================
// LLM provider configuration (/dev/llm-config)
//
// The backend owns the LLM config (single Graphiti singleton). The plugin only
// reads/dispatches; changes apply on backend restart. Shapes mirror schemas/dev.py
// (snake_case, like the rest of this file). The api_key is never returned — only
// `api_key_set` + a 4-char `api_key_hint`.
// ============================================================================

export type LlmProvider = "cloudru" | "openrouter";

// `LlmProviderDefaults` in schemas/dev.py — per-provider defaults (no key) for prefill.
export interface LlmProviderDefaults {
  base_url: string;
  main_model: string;
  small_model: string;
  embedding_model: string;
}

// `LlmConfigEntry` in schemas/dev.py — a resolved config; the key is masked.
export interface LlmConfigEntry {
  provider: LlmProvider;
  base_url: string;
  main_model: string;
  small_model: string;
  embedding_model: string;
  api_key_set: boolean;
  api_key_hint?: string | null;
}

// `UpdateLlmConfigRequest` in schemas/dev.py. Omitted model/base_url → provider
// defaults; empty/omitted api_key keeps the saved key (unless provider changed).
export interface UpdateLlmConfigInput {
  provider: LlmProvider;
  api_key?: string;
  main_model?: string;
  small_model?: string;
  embedding_model?: string;
  base_url?: string;
}

// `GetLlmConfigResponse` minus envelope. `active` = what the running singleton was
// built on (null before first build); `saved` = what applies after restart.
export interface LlmConfigState {
  active: LlmConfigEntry | null;
  saved: LlmConfigEntry | null;
  restart_required: boolean;
  providers: Record<string, LlmProviderDefaults>;
}

// `LlmConfigUpdateResponse` minus envelope (PATCH / reset).
export interface LlmConfigUpdateResult {
  restart_required: boolean;
  saved: LlmConfigEntry | null;
  warnings: string[];
}

// `GetLlmConfigResponse` in schemas/dev.py.
export interface GetLlmConfigEnvelope extends Envelope {
  active?: LlmConfigEntry | null;
  saved?: LlmConfigEntry | null;
  restart_required: boolean;
  providers: Record<string, LlmProviderDefaults>;
}

// `LlmConfigUpdateResponse` in schemas/dev.py.
export interface LlmConfigUpdateEnvelope extends Envelope {
  restart_required: boolean;
  saved?: LlmConfigEntry | null;
  warnings?: string[] | null;
}
