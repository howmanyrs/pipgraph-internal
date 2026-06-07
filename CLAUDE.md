# CLAUDE.md — PipGraph monorepo

Orientation for Claude Code at the repo root. Component-specific guidance lives in each subdirectory's own `CLAUDE.md`; read this file for *where to start* and *who depends on whom*.

## What PipGraph is

A "second brain" pipeline that ingests Markdown notes (typically an Obsidian vault), extracts entities with an LLM, and stores everything in Neo4j on the PARA model (Projects / Areas / Resources / Archives) — without ever rewriting the body of the user's notes.

The architecture is **backend-centric**: one FastAPI service owns Neo4j and the LLM; every other component is a thin client over its HTTP surface.

## Monorepo layout

```
pipgraph/
├── backend/              ← FastAPI service (Python, uv, Neo4j, Graphiti). Single source of truth.
│   ├── app/api/          ← REST endpoints (/api/v1/dev/*)
│   ├── app/services/     ← PipGraphManager + Graphiti integration
│   ├── app/crud/         ← Atomic Neo4j helpers (private to services)
│   ├── .docs/            ← gitignored working docs (CONFIGURATION.md, .todo/, …)
│   ├── CLAUDE.md         ← backend direction & API table
│   └── README.md         ← Russian narrative
│
├── pipgraph-web/         ← Next.js 16 browser client (React 19, TanStack Query, shadcn/ui)
│   ├── src/lib/api.ts    ← backend API wrapper
│   └── CLAUDE.md
│
├── pipgraph-obsidian/    ← Obsidian plugin (TypeScript, iterative build — the primary client)
│   ├── src/backend/PipGraphClient.ts
│   ├── .docs/{suggestions,plans,overview,extra}/   ← gitignored design + roadmap
│   └── CLAUDE.md
│
├── pipgraph-cli/         ← Terminal client (Python, rich) — workflow + interactive modes
│   └── CLAUDE.md
│
├── run-backend.sh / stop-backend.sh / start-web-dev.sh / run-cli.sh
├── CLAUDE.md             ← this file
└── README.md             ← full architecture overview (Russian)
```

Notes:
- `pipgraph-obsidian/` is being built **iteratively** (see its `CLAUDE.md` and `.docs/plans/`); treat its code as provisional unless marked otherwise.
- Helper scripts at the root start/stop services without `cd`-ing into each subdirectory.

## Where to start, by task

| If you're working on… | Read first |
|---|---|
| A backend endpoint or graph operation | [`backend/CLAUDE.md`](backend/CLAUDE.md) + [`backend/app/api/endpoints/dev.py`](backend/app/api/endpoints/dev.py) |
| A web-UI feature | [`pipgraph-web/CLAUDE.md`](pipgraph-web/CLAUDE.md) |
| An Obsidian plugin feature | [`pipgraph-obsidian/CLAUDE.md`](pipgraph-obsidian/CLAUDE.md) + `pipgraph-obsidian/.docs/plans/` |
| The CLI | [`pipgraph-cli/CLAUDE.md`](pipgraph-cli/CLAUDE.md) |
| Designing a *future* backend capability | [`backend/.docs/.todo/`](backend/.docs/.todo) — extend an existing note rather than forking it |

## Quick start

### Backend
```bash
cd backend/
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env   # fill NEO4J_*, CLOUDRU_* (or OPENROUTER_*) keys

uvicorn app.api.main:app --reload
# API: http://localhost:8001   Docs: http://localhost:8001/docs
```
Or, from the repo root: `./run-backend.sh` (and `./stop-backend.sh` to kill it).

Startup actively verifies Neo4j and the LLM provider — the server refuses to come up if either is unreachable.

### Web UI
```bash
cd pipgraph-web/
npm install
npm run dev   # http://localhost:3000
```
Or `./start-web-dev.sh` from the root. Optional: `NEXT_PUBLIC_API_URL=http://localhost:8001` in `.env.local`.

### Obsidian plugin
Build + deploy into a vault via `pipgraph-obsidian/deploy-to-vault.sh`. See its README/CLAUDE.md.

### CLI
`./run-cli.sh` from the root, or `pipgraph -w` from inside an activated `pipgraph-cli` venv.

## Backend API surface

All routes live under `/api/v1/dev`. The `dev` prefix is a deliberate signal that the contract is allowed to evolve — when you rename a path, fix every client in the same PR.

The endpoint table is maintained in **[`backend/CLAUDE.md`](backend/CLAUDE.md#the-live-contract-apiv1dev)** (and the live OpenAPI at `http://localhost:8001/docs`). Don't duplicate it here — keep one source of truth.

Response convention: `{success, …payload…, error}` — endpoints return HTTP 200 even on validation errors, so clients must check `success`.

## Data model (Neo4j)

```cypher
(:Episodic {uuid, name, content, created_at, valid_at, source, source_description, group_id})

(:Entity:Project)   ┐
(:Entity:Area)      │ {uuid, name, summary, name_embedding, attributes, created_at}
(:Entity:Resource)  │
(:Entity:Archive)   ┘

(:Episodic)-[:MENTIONS]->(:Entity)        // who creates: POST /dev/link-entity-episode (manual, idempotent MERGE)
                                          //              POST /dev/place-episode  (manual move+link; MERGE on the pattern, idempotent on the pair)
                                          //              POST /dev/process-note  (auto, via Graphiti build_episodic_edges)
                                          //              POST /dev/process-existing-episode (auto, only for NEW entities)
                                          // the only edge type allowed *from* an Episodic (Graphiti constraint)

(:Entity)-[:BELONGS_TO]->(:Entity)        // who creates: POST /dev/link-para-nodes (manual, idempotent MERGE)
                                          // PARA hierarchy: Project→Area, Resource→Area, Area→Archive

(:Entity)-[:RELATES_TO]->(:Entity)        // who creates: POST /dev/process-note (auto, via Graphiti extract_edges + resolve_extracted_edges)
                                          // LLM-extracted semantic relations between entities; never created manually
```

There is no live `:SUGGESTS` / `:IS_PART_OF` flow despite legacy code in `backend/app/crud/relationship_crud.py` — that module is dead (imported in `__init__.py` only, called by nothing). Treat the three edges above as the full set.

**Never create nodes or edges via raw Cypher.** Go through `PipGraphManager` (see [`backend/CLAUDE.md`](backend/CLAUDE.md)) so labels, embeddings, `created_at` and edge UUIDs stay consistent.

## Cross-cutting principles

1. **Backend is the single source of truth.** No client talks to Neo4j or an LLM directly. Ever.
2. **Layered backend.** API → `PipGraphManager` → CRUD → Neo4j. Endpoints stay thin; Cypher never appears in an endpoint.
3. **Non-destructive.** The body of a user's note is never modified. Metadata writes go to YAML frontmatter (client's job) or to the graph (backend's job).
4. **Two-plus consumers, one contract.** When changing `dev.py`, also update `pipgraph-web/src/lib/api.ts`, `pipgraph-obsidian/src/backend/PipGraphClient.ts`, and the plugin's `.docs/overview/api-surface.md` snapshot.
5. **Human-in-the-loop.** The system suggests; the user decides. Don't add silent auto-classification.
6. **Build only what's asked.** No speculative abstractions, no "while we're here" refactors.

## Configuration

Backend `.env` (full reference: [`backend/.docs/CONFIGURATION.md`](backend/.docs/CONFIGURATION.md)):
```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=...
LLM_PROVIDER=cloudru              # "cloudru" | "openrouter" — selects the active provider block
CLOUDRU_API_KEY=...               # or OPENROUTER_API_KEY, depending on provider
CLOUDRU_BASE_URL=https://.../v1
```

The LLM provider/keys/models are also editable at runtime from the Obsidian plugin via `PATCH /dev/llm-config`, which writes a gitignored overlay (`backend/config/llm_config.json`) applied on backend restart. `.env` stays the default. The extraction prompts' domain guidance is likewise tunable from the plugin via `PATCH /dev/prompts` (gitignored overlay `backend/config/prompt_overrides.json`) — but applied **live, without a restart**.

Web `.env.local`:
```bash
NEXT_PUBLIC_API_URL=http://localhost:8001
```

## Testing

**There is no automated test suite — everything is verified manually.** No pytest scaffold, no `pytest.ini`, no fixtures. If you reach for `pytest -m …` out of habit, stop: there is nothing to run.

How features are actually verified today:
- **Backend** — start `./run-backend.sh`, hit endpoints via `http://localhost:8001/docs` (Swagger UI) or `curl`, and inspect the result in Neo4j Browser (`http://localhost:7474`). Useful Cypher snippets live in [`backend/.docs/neo4j_verification_queries.md`](backend/.docs/neo4j_verification_queries.md). The server's `lifespan` startup check doubles as a smoke test — it refuses to come up if Neo4j or the LLM provider is unreachable.
- **Web** — `npm run lint && npm run build` in `pipgraph-web/`, then click through the feature in `npm run dev`.
- **Obsidian plugin** — deploy into a test vault via `pipgraph-obsidian/deploy-to-vault.sh` and exercise commands manually.

## Where to look next

- **Backend** → [`backend/CLAUDE.md`](backend/CLAUDE.md) (live API table, manager methods, layering rules)
- **Web client** → [`pipgraph-web/CLAUDE.md`](pipgraph-web/CLAUDE.md)
- **Obsidian plugin** → [`pipgraph-obsidian/CLAUDE.md`](pipgraph-obsidian/CLAUDE.md) + `.docs/plans/` (modular roadmap) and `.docs/overview/` (per-endpoint plugin coverage)
- **CLI** → [`pipgraph-cli/CLAUDE.md`](pipgraph-cli/CLAUDE.md)
- **Full architecture (Russian)** → [`README.md`](README.md)
