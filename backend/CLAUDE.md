# PipGraph Backend — Direction & Environment

> **Purpose of this file.** Orient Claude (and the next implementer) to *where this component sits*, *what it is responsible for*, *what its current API surface looks like*, and *which docs to consult before doing anything non-trivial*. Conceptual narrative ("what is PARA", "why graphs") lives in [`README.md`](./README.md); this file is the working manual.

## What this is

`backend/` is the **single source of truth** for graph state in the PipGraph monorepo. It is a FastAPI service that:

- Owns the Neo4j connection — no other component talks to the database directly.
- Owns all LLM calls — clients never invoke an LLM provider themselves.
- Exposes one HTTP surface (`/api/v1/dev`) that both clients consume:
  - [`../pipgraph-web/`](../pipgraph-web) — Next.js browser prototype.
  - [`../pipgraph-obsidian/`](../pipgraph-obsidian) — Obsidian plugin (pre-implementation, becoming the primary client).

Anything that touches Neo4j or an LLM **must go through this service**. Clients that bypass it are buggy by definition.

## Current state at a glance

- **API**: stable enough that two clients depend on it; still under `/dev` because the contract is allowed to evolve (no `/v1` freeze yet).
- **No workflow orchestration.** The prior LangGraph experiment was removed (archived under `.docs/DEPRECATED/`). Processing is direct: request → manager → graph.
- **In-process job-runner** (`app/services/jobs/queue.py`) — a single `asyncio.Queue` worker started in `lifespan` for slow LLM work that shouldn't block a request. Two job types today: async episode naming (`generate_episode_name`, via `POST /dev/episode` `generate_name=true`) and the heavy extraction pipeline (`process_existing_episode`, via `POST /dev/place-episode` `process=true`). Deliberately a **job-runner, not a workflow engine**: each job is a flat `{type, args}` → one manager method, no steps/branches (guard against re-growing LangGraph). In-memory + concurrency=1; the status of in-flight work survives on the Episodic (`status` property). On startup (`lifespan`) the runner **re-enqueues** nodes still marked `process_existing_episode` (`queue.requeue_in_flight`), so a crash mid-pipeline self-heals — best-effort, scoped to that job only (the naming job is re-driven durably by the Obsidian capture outbox, so re-enqueuing it server-side would double-run it). Anything *queued but never started* is otherwise lost on restart. **Status taxonomy** (`app/services/jobs/status.py`): a node's `status` is the active job's **type key** while it runs (`generate_episode_name` / `process_existing_episode`), `failed:<job_type>` on error, absent once settled — so a status-filtered list (`GET /dev/episodic/by-status`) and a future re-enqueue can tell which job a node needs.
- **Single manager.** `PipGraphManager` is the only legitimate entry point to Neo4j. The old `EpisodicCRUD` / `PARAContainerCRUD` classes are gone; `app/crud/` retains only `EntityCRUD` and `RelationshipCRUD`, used **from inside** the manager, not from endpoints.
- **Client-driven evolution.** The Obsidian plugin is now the contract's main driver: recent additions (`file_path` persistence on entities, the cascade-delete endpoint below) landed to serve its folder↔graph mirror. The *next* gaps it needs are catalogued — not yet built — in [`../pipgraph-obsidian/.docs/overview/future-methods.md`](../pipgraph-obsidian/.docs/overview/future-methods.md); skim it before adding an endpoint so you extend the backlog rather than fork it.
- **Future work** is staged in [`.docs/.todo/`](./.docs/.todo) (retro vault import, cascade summary, oversaturation detection, `:Entity:Task`, alias/archetype layer). Each item is a design note, not an implementation — consult before inventing a parallel approach.

## The live contract: `/api/v1/dev`

All endpoints live in [`app/api/endpoints/dev.py`](./app/api/endpoints/dev.py). The table below is a **snapshot** — re-check the file before relying on any specific row.

| Method | Path | Purpose |
|---|---|---|
| POST | `/dev/process-note` | Create Episodic + run full LLM extraction pipeline (entities, edges, summaries). |
| POST | `/dev/episode` | Create Episodic only (no LLM extraction). Lightweight ingestion. Accepts a client-supplied `uuid` → server `MERGE`s on it, so re-posting the same UUID upserts (idempotent outbox delivery). Naming: `generate_name=true` defers naming to the job queue (node created immediately with provisional name + `status="processing"`; a background job overwrites `name` and clears `status`) — poll `GET /dev/episodic/{uuid}`. Without the flag: name stored as-is, or generated synchronously if absent (legacy). |
| GET | `/dev/episodic?note_path=…` | Fetch one Episodic by `name` (path-like). |
| GET | `/dev/episodic/list?limit=…` | List all Episodics (debug/inspection). |
| GET | `/dev/episodic/unlinked?limit=…` | Episodics without any `MENTIONS` edge — i.e. the triage inbox. |
| GET | `/dev/episodic/by-status?status=…&limit=…` | Episodics with an exact `status` value (e.g. `process_existing_episode`, `failed:…`). Backs the plugin's startup reconcile (re-seed the processing poll set) and future server-side re-enqueue. Declared before `/episodic/{uuid}` so the literal wins. |
| GET | `/dev/episodics/by-entity?entity_uuid=…&limit=…` | Episodics that `MENTIONS` a given entity. |
| GET | `/dev/episodic/{episodic_uuid}` | Fetch one Episodic by UUID — the status-polling endpoint (returns `status`, `name`, `file_path`, …). Correlation key is the UUID, not `file_path`. |
| PATCH | `/dev/episodic/{episodic_uuid}` | Update an Episodic in place, keeping UUID + edges. **Only `file_path` editable** (Episodic mirror of S1). No embeddings/indexes recomputed. **Transition-guard (E6):** first-bind + same-folder rename allowed; **cross-folder move rejected** → `200 {success:false}` (placement change must go through the move+link op, which re-points `MENTIONS`). All Episodic read endpoints now return `file_path` top-level. |
| POST | `/dev/episodic/{episodic_uuid}/reprocess` | Re-stamp `status="process_existing_episode"` and enqueue the heavy job — manual retry for a node stuck at `failed:process_existing_episode` (P3). Returns immediately; poll `GET /episodic/{uuid}`. No move/re-link (note already placed). |
| POST | `/dev/process-existing-episode` | Run extraction on an already-linked Episodic (updates summaries, adds new mentions only). |
| POST | `/dev/para-entity` | Create a PARA entity (`:Entity:Project|Area|Resource|Archive`) without LLM. |
| PATCH | `/dev/para-entity/{entity_uuid}` | Update a PARA entity in place, keeping UUID + edges. **Only `summary` editable today** (S8 partial; `name`/`file_path` pending). Summary feeds the `make-suggestions` BM25 index; `name_embedding` is not recomputed. |
| GET | `/dev/para-entity/list?limit=…&para_type=…&<prop>=…` | List PARA entities. Extra query params become property filters. |
| POST | `/dev/link-entity-episode` | Create `MENTIONS` edge (Episodic → Entity). Idempotent (`MERGE`). |
| POST | `/dev/place-episode` | **Move+link (E7):** set Episodic `file_path` to a new (cross-folder) location **and** `MERGE` its `MENTIONS` to an entity, in one act. Backs the plugin's drag-from-Inbox gesture. Idempotent on the (episode, entity) pair — MERGEs on the *relationship pattern*, not a fresh edge uuid. Physical file move is the client's job. **`process=true` (P2):** stamps `status="process_existing_episode"` atomically with the link and enqueues the heavy pipeline as a background job (returns immediately; poll `GET /episodic/{uuid}` until `status` clears). |
| POST | `/dev/link-para-nodes` | Create `BELONGS_TO` edge (Entity → Entity) for hierarchy. Idempotent. |
| POST | `/dev/make-suggestions` | Hybrid search (BM25 + vector + MMR) returning ranked PARA entities for an Episodic. |
| GET | `/dev/para-tree` | Hierarchical PARA tree built from `BELONGS_TO` edges. |
| DELETE | `/dev/node/{node_uuid}` | Delete an Episodic or Entity with `DETACH DELETE`. Auto-detects type. Irreversible. |
| DELETE | `/dev/para-entity/{entity_uuid}` | Delete a PARA entity **and cascade-delete its orphaned Episodics** (those whose only `MENTIONS` pointed at it). Backs the Obsidian folder-mirror delete. Irreversible hard delete; bi-temporal soft-invalidation is the deferred successor. |
| GET | `/dev/llm-config` | Active LLM config (provider, base_url, models) for each provider + the resolved active one. `api_key` is **masked**, never returned. Includes `restart_required` (active snapshot ≠ resolved config) and embedding-change warnings. |
| PATCH | `/dev/llm-config` | Update the runtime overlay (`config/llm_config.json`, gitignored): `provider` + per-field `base_url`/`api_key`/`*_model`. Applied **on backend restart** — the Graphiti singleton is never rebuilt in place. Returns `restart_required` + embedding-warning. |
| POST | `/dev/llm-config/reset` | Delete the runtime overlay → revert to pure `settings`/`.env` defaults. Applied on restart. |

**OpenAPI** is served at `http://localhost:8001/docs` when the server is running — use it as the cross-check, not this table.

### Conventions across the surface

- Responses follow `{success: bool, …payload…, error: str|None}` — endpoints return HTTP 200 even on validation failure, with `success=false` and `error` populated. Clients must check `success`.
- Identifiers are **UUIDs** for nodes/edges, and **path-like `name`** for Episodics.
- `MENTIONS` and `BELONGS_TO` use `MERGE` — calling a link endpoint twice is safe.
- The `/dev/llm-config` endpoints are the one **legitimate** bypass of the manager: they touch no graph state, so they call `services/graphiti/llm_config.py` directly (no Cypher, no `PipGraphManager`).

## Layered architecture

```
HTTP request
   │
   ▼
app/api/endpoints/dev.py        ← thin: Pydantic validate → call manager → wrap response
   │
   ▼
app/services/graphiti/
   pipgraph_manager.py          ← all business logic, all Graphiti orchestration
   setup_graphiti.py            ← Graphiti singleton, built from the active LLM config
   llm_config.py                ← active LLM config: provider defaults + runtime overlay; restart snapshot
   patched_client.py            ← provider-agnostic PatchedLLMClient (Cloud.ru, OpenRouter; example-not-schema)
   name_generator.py            ← LLM-based episode-name generation
   para_tree.py                 ← BELONGS_TO tree builder
   │
   ▼
app/crud/                       ← atomic Cypher helpers, called *only* from the manager
   entity_crud.py
   relationship_crud.py
   │
   ▼
Neo4j (bolt://…)
```

**Rules of the road:**

- Endpoints never write Cypher. They call a manager method.
- The manager never returns raw `neo4j` driver objects to endpoints — it returns Graphiti node objects (`EpisodicNode`, `EntityNode`) or domain types from `app/models/`.
- `app/crud/` helpers are private to the service layer. New endpoints don't import them directly.

## `PipGraphManager` — the single entry point

Defined in [`app/services/graphiti/pipgraph_manager.py`](./app/services/graphiti/pipgraph_manager.py). All methods are async. Methods grouped by purpose (line numbers drift — grep before quoting):

**Episodic lifecycle**
- `process_note(name, episode_body, …)` — full LLM pipeline (extract nodes → resolve → edges → bulk save).
- `create_episode(content, …, name=None, uuid=None, status=None)` — lightweight ingestion, no LLM (except optional sync name generation). `uuid` lets a client supply the node UUID (saved via `MERGE` → idempotent retry); `status` stamps a transient flag (e.g. `"processing"` while an async naming job is in flight).
- `finalize_episode_name(uuid, name)` — set final `name` + clear `status` (naming job). `set_episodic_status(uuid, status)` — set the transient `status` (e.g. `failed:<job>`). `clear_episodic_status(uuid)` — remove `status` on success of a job that doesn't change `name` (the `process_existing_episode` job).
- `process_existing_episode(episodic_uuid, …)` — re-run extraction on an Episodic already linked to a PARA entity. Runs as the `process_existing_episode` job when triggered via `place-episode` `process=true`.
- `get_episodic_by_name(name)`, `list_episodics(limit)`, `list_unlinked_episodics(limit)`, `list_episodics_by_status(status, limit)`, `get_episodics_by_entity_uuid(uuid, limit)`.
- `update_episodic_timestamp(uuid, valid_at)`, `update_episodic_file_path(uuid, file_path)` (narrow patch, mirrors `update_para_entity`; E6 transition-guard — raises `CrossFolderFilePathError` on a cross-folder move), `delete_episodic(uuid)`, `delete_node(uuid)` (type-agnostic).

**PARA entity lifecycle**
- `create_para_entity(para_type, name, summary, …)` — labels become `:Entity:Project|Area|Resource|Archive`.
- `update_para_entity(uuid, *, summary=…)` — patch in place, preserving edges. Summary-only for now (S8 partial); does not recompute `name_embedding`.
- `get_para_entity_by_uuid(uuid)`, `get_para_entity_by_name(name, para_type=…)`, `list_para_entities(limit, para_types, property_filters)`.
- `ensure_inbox_exists()` — idempotent Inbox singleton.

**Relationships**
- `link_entity_to_episode(episodic_uuid, entity_uuid)` — `MENTIONS`.
- `place_episode(episodic_uuid, entity_uuid, file_path, status=None)` — move+link (E7): cross-folder `SET file_path` + `MERGE MENTIONS` on the pattern (idempotent on the pair). Bypasses the E6 guard by design. Optional `status` is stamped in the **same** statement (P2 passes `"process_existing_episode"` so the in-flight record commits atomically with the link, before the job is enqueued).
- `link_para_nodes(source, target)` — `BELONGS_TO`.

**Discovery**
- `make_suggestions(episodic_uuid, limit, min_score)` — hybrid search ranking PARA entities for a note.

If a new endpoint needs a database operation that doesn't exist yet, **add a method to `PipGraphManager` first** — do not write Cypher in the endpoint.

## Data model (Neo4j)

```
(:Episodic {uuid, name, content, created_at, valid_at, source, source_description, group_id, file_path?, frontmatter?, status?})
  // status: transient job flag — active job's type key ("generate_episode_name"/"process_existing_episode"),
  //         "failed:<job>" on error, absent = settled. Managed by the job-runner (app/services/jobs/status.py).

(:Entity:Project)   ┐
(:Entity:Area)      │ {uuid, name, summary, name_embedding, attributes, created_at}
(:Entity:Resource)  │
(:Entity:Archive)   ┘

(:Episodic)-[:MENTIONS]->(:Entity)         ← only edge allowed from Episodic (Graphiti constraint)
(:Entity)-[:BELONGS_TO]->(:Entity)         ← PARA hierarchy
(:Entity)-[:RELATES_TO]->(:Entity)         ← LLM-extracted semantic relations
```

Schemas are owned by Graphiti and the manager. **Never `CREATE` a node from a raw Cypher call** — go through `PipGraphManager` so labels, embeddings, and `created_at` stay consistent.

## Configuration

`config/settings.py` exposes a global `settings` object (pydantic-settings). Read via:

```python
from config.settings import settings
settings.NEO4J_URI, settings.CLOUDRU_API_KEY, …
```

Required `.env` keys (see [`.docs/CONFIGURATION.md`](./.docs/CONFIGURATION.md) for the full list and provider notes):

```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=…

LLM_PROVIDER=cloudru             # "cloudru" | "openrouter" — picks which block below is active
CLOUDRU_API_KEY=…                # or OPENROUTER_API_KEY, depending on provider
CLOUDRU_BASE_URL=https://…/v1
```

`.env` is the **default** LLM config. A gitignored runtime overlay (`config/llm_config.json`, written by `PATCH /dev/llm-config`) overrides individual fields and is applied **on restart** — the active config is resolved in `services/graphiti/llm_config.py`, and `get_graphiti()` snapshots what it built on so `restart_required` can be reported honestly. The Graphiti singleton is never rebuilt in place.

Startup (`app/api/main.py:lifespan`) actively verifies both Neo4j and the LLM provider (on the *active* config) — the server refuses to come up if either is unreachable.

## Running locally

```bash
cd backend/
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env   # then fill in keys

uvicorn app.api.main:app --reload
# API:  http://localhost:8001
# Docs: http://localhost:8001/docs
```

CORS is preconfigured for `localhost:3000` / `:3001` so the web client works out of the box. The Obsidian plugin runs in-process inside Obsidian and is not subject to CORS.

## Testing

**There is no automated test suite.** All verification is manual:

- Start the server (`./run-backend.sh` from the repo root, or `uvicorn app.api.main:app --reload`).
- Hit endpoints via Swagger UI at `http://localhost:8001/docs` or `curl`.
- Inspect graph state in Neo4j Browser at `http://localhost:7474`. Useful Cypher snippets live in [`.docs/neo4j_verification_queries.md`](./.docs/neo4j_verification_queries.md).

Startup itself is a smoke test: the server refuses to come up if Neo4j or the LLM provider is unreachable (see `app/api/main.py:lifespan`).

## Documentation layout

```
backend/
├── README.md                 ← project narrative (in Russian) — philosophy, "what is this"
├── CLAUDE.md                 ← you are here (direction, API surface, layering)
├── ISSUES.md                 ← rolling notes on known issues
└── .docs/                    ← gitignored personal/working docs
    ├── CONFIGURATION.md      ← full .env reference, provider notes
    ├── about_graphiti/       ← background on Graphiti integration patterns
    ├── custom_entities/      ← notes on PARA entity-type customisation
    ├── neo4j_verification_queries.md
    ├── new_claude_and_skills/
    ├── DONES/                ← historical "what landed" notes
    ├── DEPRECATED/           ← prior LangGraph workflow design (kept for context)
    ├── EXPERIMENTAL_*.md     ← parked ideas — do NOT implement; framing-only
    └── .todo/                ← *future* features — read before designing anything new
```

### Parked ideas (do not implement)

Если ловишь себя на дизайне фичи, которая «концептуально расширяет» одну из заметок ниже — **остановись и прочитай её**. Эти идеи отложены сознательно; их преждевременная имплементация была бы over-engineering'ом текущего этапа.

- [`./.docs/EXPERIMENTAL_multi_classification_views.md`](./.docs/EXPERIMENTAL_multi_classification_views.md) — заметка одновременно в нескольких классификационных «срезах» / папках. Сейчас инвариант: один Episodic = один `file_path`. Visual multi-presence решается на стороне плагина (ghost-rows), не backend'а.
- [`./.docs/EXPERIMENTAL_ambient_intelligence_layer.md`](./.docs/EXPERIMENTAL_ambient_intelligence_layer.md) — founding vision PipGraph'а как «reflection surface»: pattern detection, trend tracking, gap detection, self-deception, active reminders, Facts vs TODOs distinction. Сейчас фокус — базовый triage flow; analytical layer накладывается на накопленный граф позже, когда есть данные.

The `.docs/` tree is **not under version control** (see root `.gitignore`). Anything that must be shared (architecture decisions, API contracts) belongs in `README.md` or in a PR description, not here.

## Working principles

1. **The manager is the API.** All graph operations route through `PipGraphManager`. New CRUD logic goes there.
2. **The endpoint layer stays thin.** Endpoints validate input, call one manager method, wrap the result in the response schema. No business logic, no Cypher.
3. **The contract is the file, not this doc.** `dev.py` is authoritative for routes and shapes. This file points to it; OpenAPI at `/docs` is the live mirror.
4. **Non-destructive towards the user's notes.** The backend reads note bodies but only writes to its own database. Anything that writes back to a note's body is out of scope; frontmatter writes are the client's job (see [`../pipgraph-obsidian/CLAUDE.md`](../pipgraph-obsidian/CLAUDE.md)).
5. **Two clients, same contract.** When changing an endpoint, check both [`../pipgraph-web/src/lib/api.ts`](../pipgraph-web/src/lib/api.ts) and [`../pipgraph-obsidian/src/backend/PipGraphClient.ts`](../pipgraph-obsidian/src/backend/PipGraphClient.ts) before merging — and update the Obsidian plugin's [`.docs/overview/api-surface.md`](../pipgraph-obsidian/.docs/overview/api-surface.md) snapshot if the change is material.
6. **Read `.docs/.todo/` before designing.** Many "obvious" missing features (retro vault import, cascade summary, `:Entity:Task`, oversaturation, aliases) already have design notes. Extend them; don't fork them.
7. **Iterate the `/dev` surface freely; rename with notice.** The `dev` prefix is a deliberate signal that the contract is mutable. When you rename a path, fix both clients and the Obsidian overview snapshot in the same PR.

## Where to look next

- **Implementing an endpoint** → [`app/api/endpoints/dev.py`](./app/api/endpoints/dev.py) + [`app/api/schemas/dev.py`](./app/api/schemas/dev.py).
- **Implementing graph logic** → [`app/services/graphiti/pipgraph_manager.py`](./app/services/graphiti/pipgraph_manager.py).
- **Designing a future capability** → check [`.docs/.todo/`](./.docs/.todo) first.
- **Understanding the consumers** → [`../pipgraph-obsidian/.docs/overview/`](../pipgraph-obsidian/.docs/overview) maps every endpoint to its plugin/web usage and flags gaps.
- **Configuration / secrets** → [`.docs/CONFIGURATION.md`](./.docs/CONFIGURATION.md).
- **Manual verification queries** → [`.docs/neo4j_verification_queries.md`](./.docs/neo4j_verification_queries.md).
- **Monorepo overview** → [`../CLAUDE.md`](../CLAUDE.md).

---

**For Claude Code working in this directory:** Do not duplicate `pipgraph_manager.py` logic in endpoints. Do not write Cypher in endpoints. Do not invent new endpoints for capabilities that already have a `.docs/.todo/` design — propose extending the existing note instead. When in doubt about a route's exact shape, consult `dev.py` (or `/docs`), not this snapshot.
