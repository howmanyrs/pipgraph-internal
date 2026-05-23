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
│   ├── tests/            ← unit / integration / e2e / api
│   ├── .docs/            ← gitignored working docs (CONFIGURATION.md, TESTING.md, .todo/, …)
│   ├── CLAUDE.md         ← backend direction & API table
│   └── README.md         ← Russian narrative
│
├── pipgraph-web/         ← Next.js 16 browser client (React 19, TanStack Query, shadcn/ui)
│   ├── src/lib/api.ts    ← backend API wrapper
│   └── CLAUDE.md
│
├── pipgraph-obsidian/    ← Obsidian plugin (TypeScript, pre-implementation, becoming primary client)
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
# API: http://localhost:8000   Docs: http://localhost:8000/docs
```
Or, from the repo root: `./run-backend.sh` (and `./stop-backend.sh` to kill it).

Startup actively verifies Neo4j and the LLM provider — the server refuses to come up if either is unreachable.

### Web UI
```bash
cd pipgraph-web/
npm install
npm run dev   # http://localhost:3000
```
Or `./start-web-dev.sh` from the root. Optional: `NEXT_PUBLIC_API_URL=http://localhost:8000` in `.env.local`.

### Obsidian plugin
Build + deploy into a vault via `pipgraph-obsidian/deploy-to-vault.sh`. See its README/CLAUDE.md.

### CLI
`./run-cli.sh` from the root, or `pipgraph -w` from inside an activated `pipgraph-cli` venv.

## Backend API surface

All routes live under `/api/v1/dev`. The `dev` prefix is a deliberate signal that the contract is allowed to evolve — when you rename a path, fix every client in the same PR.

| Method | Path | Purpose |
|---|---|---|
| POST | `/dev/process-note` | Create Episodic + full LLM extraction pipeline |
| POST | `/dev/episode` | Lightweight Episodic creation (no LLM) |
| GET | `/dev/episodic?note_path=…` | Get one Episodic by `name` |
| GET | `/dev/episodic/list` | List all Episodics |
| GET | `/dev/episodic/unlinked` | Episodics with no `MENTIONS` edge (triage inbox) |
| GET | `/dev/episodics/by-entity?entity_uuid=…` | Episodics that mention a given entity |
| POST | `/dev/process-existing-episode` | Re-run extraction on an already-linked Episodic |
| POST | `/dev/para-entity` | Create a PARA entity |
| GET | `/dev/para-entity/list` | List PARA entities (filterable by type and properties) |
| POST | `/dev/link-entity-episode` | `MENTIONS` edge (Episodic → Entity), idempotent |
| POST | `/dev/link-para-nodes` | `BELONGS_TO` edge (Entity → Entity), idempotent |
| POST | `/dev/make-suggestions` | Hybrid search ranking PARA entities for a note |
| GET | `/dev/para-tree` | Hierarchical PARA tree from `BELONGS_TO` |
| DELETE | `/dev/node/{node_uuid}` | Detach-delete an Episodic or Entity |

Authoritative source: [`backend/app/api/endpoints/dev.py`](backend/app/api/endpoints/dev.py) and live OpenAPI at `/docs`. Responses follow `{success, …payload…, error}` — clients must check `success` (endpoints return 200 even on validation errors).

## Data model (Neo4j)

```cypher
(:Episodic {uuid, name, content, created_at, valid_at, source, source_description, group_id})

(:Entity:Project)   ┐
(:Entity:Area)      │ {uuid, name, summary, name_embedding, attributes, created_at}
(:Entity:Resource)  │
(:Entity:Archive)   ┘

(:Episodic)-[:MENTIONS]->(:Entity)        // only edge type allowed from Episodic
(:Entity)-[:BELONGS_TO]->(:Entity)        // PARA hierarchy
(:Entity)-[:RELATES_TO]->(:Entity)        // LLM-extracted semantic relations
```

**Never create nodes via raw Cypher.** Go through `PipGraphManager` (see [`backend/CLAUDE.md`](backend/CLAUDE.md)) so labels, embeddings, and `created_at` stay consistent.

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
CLOUDRU_API_KEY=...               # or OPENROUTER_API_KEY, depending on provider
CLOUDRU_BASE_URL=https://.../v1
```

Web `.env.local`:
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Testing

```bash
# Backend
cd backend/
pytest -m unit            # fast, no external services
pytest -m integration     # requires Neo4j + LLM
pytest -m "not slow"      # skip LLM-heavy paths
```
Full conventions: [`backend/.docs/TESTING.md`](backend/.docs/TESTING.md).

```bash
# Web
cd pipgraph-web/
npm run lint
npm run build
```

## Where to look next

- **Backend** → [`backend/CLAUDE.md`](backend/CLAUDE.md) (live API table, manager methods, layering rules)
- **Web client** → [`pipgraph-web/CLAUDE.md`](pipgraph-web/CLAUDE.md)
- **Obsidian plugin** → [`pipgraph-obsidian/CLAUDE.md`](pipgraph-obsidian/CLAUDE.md) + `.docs/plans/` (modular roadmap) and `.docs/overview/` (per-endpoint plugin coverage)
- **CLI** → [`pipgraph-cli/CLAUDE.md`](pipgraph-cli/CLAUDE.md)
- **Full architecture (Russian)** → [`README.md`](README.md)
