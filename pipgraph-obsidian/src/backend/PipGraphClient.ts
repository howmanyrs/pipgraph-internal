/**
 * Typed wrapper over the backend REST API at `<backendUrl>/api/v1/dev`.
 *
 * Every other plugin module that needs graph state goes through this class —
 * no raw fetch / requestUrl calls outside src/backend/.
 *
 * Sources:
 *  - Endpoint paths & query params: backend/app/api/endpoints/dev.py
 *  - Request/response shapes:       backend/app/api/schemas/dev.py
 *  - Cross-reference (with caveats):
 *    pipgraph-web/src/lib/api.ts — sibling client; useful for shapes, but
 *    has known drift bugs (uses `uuid` query param for /episodic, points
 *    /para-entity/list at the wrong path). Always verify against dev.py.
 *
 * Design choices specific to this client (vs pipgraph-web):
 *  - Envelopes `{success, error, ...payload}` are unwrapped here. `success: false`
 *    raises PipGraphApiError(kind: 'http'). Callers see clean payload types and
 *    use try/catch uniformly.
 *  - Transport is injectable (Fetcher) so M5 decoration work and console
 *    debugging can substitute fakes without monkey-patching globals.
 *  - Timeouts are explicit per-method (reads 10s, process-note 60s).
 *  - No caching, no retries — see ../../.docs/plans/03-backend-client.md
 *    "Deferred decisions" for the rationale.
 */

import type { PipGraphSettings } from "../settings/PipGraphSettings";
import { PipGraphApiError } from "./errors";
import { obsidianFetcher, type Fetcher, type RequestSpec } from "./transport";
import type {
  CreateEpisodeEnvelope,
  CreateEpisodeInput,
  CreateEpisodeResult,
  CreateParaEntityEnvelope,
  CreateParaEntityInput,
  CreateParaEntityResult,
  DeleteNodeEnvelope,
  DeleteNodeResult,
  DeleteParaEntityEnvelope,
  DeleteParaEntityResult,
  Envelope,
  EpisodicNode,
  GetEpisodicEnvelope,
  LinkEntityEpisodeEnvelope,
  LinkEntityEpisodeInput,
  LinkEntityEpisodeResult,
  LinkParaNodesEnvelope,
  LinkParaNodesInput,
  LinkParaNodesResult,
  ListEpisodicEnvelope,
  ListParaEntitiesEnvelope,
  MakeSuggestionsEnvelope,
  MakeSuggestionsInput,
  ParaEntity,
  ParaSuggestion,
  ParaType,
  ProcessNoteEnvelope,
  ProcessNoteInput,
  ProcessNoteResult,
} from "./types";

const API_PREFIX = "/api/v1/dev";

const TIMEOUT_READ_MS = 10_000;
const TIMEOUT_WRITE_MS = 15_000;
const TIMEOUT_LLM_MS = 60_000;
const TIMEOUT_PING_MS = 3_000;

export class PipGraphClient {
  private readonly settings: PipGraphSettings;
  private readonly fetcher: Fetcher;

  constructor(settings: PipGraphSettings, fetcher: Fetcher = obsidianFetcher) {
    this.settings = settings;
    this.fetcher = fetcher;
  }

  // --------------------------------------------------------------------------
  // Read endpoints
  // --------------------------------------------------------------------------

  async listEpisodics(limit = 100): Promise<EpisodicNode[]> {
    const env = await this.request<ListEpisodicEnvelope>({
      method: "GET",
      path: `/episodic/list`,
      query: { limit },
      timeoutMs: TIMEOUT_READ_MS,
    });
    return env.episodics;
  }

  /**
   * Backend lookup is by `note_path` (file name), NOT by UUID.
   * See `get_episodic_by_path` in backend/app/api/endpoints/dev.py:115.
   * Returns null when the backend reports "not found" rather than throwing,
   * because absence is a normal control-flow case for the triage panel.
   */
  async getEpisodicByPath(notePath: string): Promise<EpisodicNode | null> {
    try {
      const env = await this.request<GetEpisodicEnvelope>({
        method: "GET",
        path: `/episodic`,
        query: { note_path: notePath },
        timeoutMs: TIMEOUT_READ_MS,
      });
      return env.episodic ?? null;
    } catch (err) {
      if (
        err instanceof PipGraphApiError &&
        err.kind === "http" &&
        typeof err.message === "string" &&
        err.message.toLowerCase().includes("not found")
      ) {
        return null;
      }
      throw err;
    }
  }

  async listUnlinkedEpisodics(limit = 100): Promise<EpisodicNode[]> {
    const env = await this.request<ListEpisodicEnvelope>({
      method: "GET",
      path: `/episodic/unlinked`,
      query: { limit },
      timeoutMs: TIMEOUT_READ_MS,
    });
    return env.episodics;
  }

  async listParaEntities(opts: {
    limit?: number;
    paraTypes?: ParaType[];
    // Resolve folder → entity: filters via the backend's generic property_filters
    // (`?file_path=<path>` → `n.file_path = …`). This is the read-step in the
    // resolve-then-act pattern; mutations stay UUID-addressed.
    filePath?: string;
  } = {}): Promise<ParaEntity[]> {
    const env = await this.request<ListParaEntitiesEnvelope>({
      method: "GET",
      // NB: real path is `/para-entity/list`. pipgraph-web/src/lib/api.ts:355
      // points at `/para-entities` — that's a bug there, not here.
      path: `/para-entity/list`,
      query: {
        limit: opts.limit ?? 100,
        // Backend uses repeated `para_type` query params; URLSearchParams
        // handles arrays natively via the helper below.
        para_type: opts.paraTypes,
        file_path: opts.filePath,
      },
      timeoutMs: TIMEOUT_READ_MS,
    });
    return env.entities;
  }

  async makeSuggestions(input: MakeSuggestionsInput): Promise<ParaSuggestion[]> {
    const env = await this.request<MakeSuggestionsEnvelope>({
      method: "POST",
      path: `/make-suggestions`,
      body: input,
      timeoutMs: TIMEOUT_LLM_MS,
    });
    return env.suggestions;
  }

  // --------------------------------------------------------------------------
  // Write endpoints
  // --------------------------------------------------------------------------

  async createEpisode(input: CreateEpisodeInput): Promise<CreateEpisodeResult> {
    const env = await this.request<CreateEpisodeEnvelope>({
      method: "POST",
      path: `/episode`,
      body: input,
      // Create may auto-generate name via LLM — give it room.
      timeoutMs: TIMEOUT_LLM_MS,
    });
    if (!env.uuid || !env.name) {
      throw new PipGraphApiError({
        kind: "parse",
        message: "createEpisode succeeded but response missing uuid or name",
        body: JSON.stringify(env),
      });
    }
    return {
      uuid: env.uuid,
      name: env.name,
      created_at: env.created_at ?? undefined,
    };
  }

  async createParaEntity(
    input: CreateParaEntityInput,
  ): Promise<CreateParaEntityResult> {
    const env = await this.request<CreateParaEntityEnvelope>({
      method: "POST",
      path: `/para-entity`,
      body: input,
      timeoutMs: TIMEOUT_WRITE_MS,
    });
    if (!env.uuid || !env.para_type || !env.name) {
      throw new PipGraphApiError({
        kind: "parse",
        message: "createParaEntity succeeded but response missing fields",
        body: JSON.stringify(env),
      });
    }
    return {
      uuid: env.uuid,
      para_type: env.para_type,
      name: env.name,
      created_at: env.created_at ?? undefined,
    };
  }

  async linkEntityToEpisode(
    input: LinkEntityEpisodeInput,
  ): Promise<LinkEntityEpisodeResult> {
    const env = await this.request<LinkEntityEpisodeEnvelope>({
      method: "POST",
      path: `/link-entity-episode`,
      body: input,
      timeoutMs: TIMEOUT_WRITE_MS,
    });
    if (!env.edge_uuid || !env.episodic_uuid || !env.entity_uuid) {
      throw new PipGraphApiError({
        kind: "parse",
        message: "linkEntityToEpisode succeeded but response missing fields",
        body: JSON.stringify(env),
      });
    }
    return {
      edge_uuid: env.edge_uuid,
      episodic_uuid: env.episodic_uuid,
      entity_uuid: env.entity_uuid,
      created_at: env.created_at ?? undefined,
    };
  }

  /**
   * Create a BELONGS_TO edge between two PARA entities.
   * Direction: (source)-[:BELONGS_TO]->(target) — source is the child,
   * target is the parent. Idempotent on the backend (MERGE).
   */
  async linkParaNodes(
    input: LinkParaNodesInput,
  ): Promise<LinkParaNodesResult> {
    const env = await this.request<LinkParaNodesEnvelope>({
      method: "POST",
      path: `/link-para-nodes`,
      body: input,
      timeoutMs: TIMEOUT_WRITE_MS,
    });
    if (!env.edge_uuid || !env.source_entity_uuid || !env.target_entity_uuid) {
      throw new PipGraphApiError({
        kind: "parse",
        message: "linkParaNodes succeeded but response missing fields",
        body: JSON.stringify(env),
      });
    }
    return {
      edge_uuid: env.edge_uuid,
      source_entity_uuid: env.source_entity_uuid,
      target_entity_uuid: env.target_entity_uuid,
      created_at: env.created_at ?? undefined,
    };
  }

  async processNote(input: ProcessNoteInput): Promise<ProcessNoteResult> {
    const env = await this.request<ProcessNoteEnvelope>({
      method: "POST",
      path: `/process-note`,
      body: input,
      timeoutMs: TIMEOUT_LLM_MS,
    });
    return {
      episode_uuid: env.episode_uuid ?? undefined,
      nodes_count: env.nodes_count,
      edges_count: env.edges_count,
    };
  }

  /**
   * Delete a PARA entity and cascade-delete its orphaned Episodics — every
   * Episodic whose ONLY MENTIONS edge pointed at this entity. Episodics that
   * mention other entities survive (they just lose this one edge).
   *
   * Backs the folder-mirror delete flow. This is a hard delete; a bi-temporal
   * soft-invalidation model is the conceptual successor (tracked separately).
   * Throws PipGraphApiError(kind:'http') if the entity is not found.
   */
  async deleteParaEntityCascade(
    entityUuid: string,
  ): Promise<DeleteParaEntityResult> {
    const env = await this.request<DeleteParaEntityEnvelope>({
      method: "DELETE",
      path: `/para-entity/${encodeURIComponent(entityUuid)}`,
      timeoutMs: TIMEOUT_WRITE_MS,
    });
    return {
      entity_uuid: env.entity_uuid ?? entityUuid,
      deleted_episodics_count: env.deleted_episodics_count ?? 0,
    };
  }

  /**
   * Hard-delete any node (Episodic or Entity) by UUID via DETACH DELETE.
   * Type-agnostic primitive — mainly for manual/debug cleanup. For folder
   * deletion use deleteParaEntityCascade (orphan-aware).
   */
  async deleteNode(nodeUuid: string): Promise<DeleteNodeResult> {
    const env = await this.request<DeleteNodeEnvelope>({
      method: "DELETE",
      path: `/node/${encodeURIComponent(nodeUuid)}`,
      timeoutMs: TIMEOUT_WRITE_MS,
    });
    if (!env.node_uuid || !env.node_type) {
      throw new PipGraphApiError({
        kind: "parse",
        message: "deleteNode succeeded but response missing fields",
        body: JSON.stringify(env),
      });
    }
    return { node_uuid: env.node_uuid, node_type: env.node_type };
  }

  // --------------------------------------------------------------------------
  // Connectivity
  // --------------------------------------------------------------------------

  /**
   * Lightweight reachability check for the "Backend reachable?" indicator.
   * Backend has no dedicated health endpoint today, so we ask for one
   * Episodic — cheap, exercises both routing and DB connectivity.
   */
  async ping(): Promise<void> {
    await this.request<ListEpisodicEnvelope>({
      method: "GET",
      path: `/episodic/list`,
      query: { limit: 1 },
      timeoutMs: TIMEOUT_PING_MS,
    });
  }

  // --------------------------------------------------------------------------
  // Internal: request pipeline
  // --------------------------------------------------------------------------

  private async request<T extends Envelope>(opts: {
    method: RequestSpec["method"];
    path: string;
    query?: Record<string, unknown>;
    body?: unknown;
    timeoutMs: number;
  }): Promise<T> {
    const url = this.buildUrl(opts.path, opts.query);
    const headers: Record<string, string> = {
      Accept: "application/json",
    };
    let body: string | undefined;
    if (opts.body !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(opts.body);
    }
    if (this.settings.apiKey) {
      headers["Authorization"] = `Bearer ${this.settings.apiKey}`;
    }

    const raw = await this.fetcher({
      url,
      method: opts.method,
      headers,
      body,
      timeoutMs: opts.timeoutMs,
    });

    // Non-2xx → HTTP error. Try to surface backend's `error` field if present.
    if (raw.status < 200 || raw.status >= 300) {
      const message = extractErrorMessage(raw.body) ?? `HTTP ${raw.status}`;
      throw new PipGraphApiError({
        kind: "http",
        status: raw.status,
        message,
        url,
        body: raw.body,
      });
    }

    let parsed: T;
    try {
      parsed = JSON.parse(raw.body) as T;
    } catch (cause) {
      throw new PipGraphApiError({
        kind: "parse",
        message: `Response from ${url} was not valid JSON`,
        url,
        body: raw.body,
        cause,
      });
    }

    // Envelope unwrap: success:false is a logical HTTP failure even at status 200.
    if (parsed.success === false) {
      throw new PipGraphApiError({
        kind: "http",
        status: raw.status,
        message: parsed.error ?? "Backend reported success: false",
        url,
        body: raw.body,
      });
    }

    return parsed;
  }

  private buildUrl(path: string, query?: Record<string, unknown>): string {
    const base = this.settings.backendUrl.replace(/\/+$/, "");
    const url = `${base}${API_PREFIX}${path}`;
    if (!query) return url;

    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null) continue;
      if (Array.isArray(value)) {
        for (const v of value) {
          if (v !== undefined && v !== null) params.append(key, String(v));
        }
      } else {
        params.set(key, String(value));
      }
    }
    const qs = params.toString();
    return qs ? `${url}?${qs}` : url;
  }
}

function extractErrorMessage(body: string): string | undefined {
  if (!body) return undefined;
  try {
    const parsed = JSON.parse(body) as { error?: string; detail?: string };
    return parsed.error ?? parsed.detail ?? undefined;
  } catch {
    return undefined;
  }
}
