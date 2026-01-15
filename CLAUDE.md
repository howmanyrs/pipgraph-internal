# CLAUDE.md

Quick reference for Claude Code when working with the PipGraph monorepo.

## Project Overview

PipGraph is an intelligent knowledge graph system that transforms unstructured Markdown notes (Obsidian) into a structured graph database (Neo4j) using LLM. It implements the PARA methodology (Projects, Areas, Resources, Archives).

**Key Features:**
- Non-destructive note processing (only YAML frontmatter modified)
- LLM-powered entity extraction
- REST API for all operations
- Human-in-the-loop workflow

## Monorepo Structure

```
pipgraph/
├── backend/              # Python FastAPI backend (main component)
│   ├── app/             # Source code
│   │   ├── api/         # REST endpoints (API layer)
│   │   ├── services/    # Business logic (Service layer)
│   │   └── crud/        # Neo4j operations (Data layer)
│   ├── tests/           # Unit/Integration/E2E tests
│   ├── docs/            # Detailed documentation
│   ├── CLAUDE.md        # Backend quick reference
│   └── README.md        # Backend developer guide
│
├── pipgraph-web/        # Next.js web interface (NEW)
│   ├── src/             # React components, pages, hooks
│   │   ├── app/         # Next.js App Router
│   │   ├── components/  # React components (shadcn/ui)
│   │   ├── lib/         # Utilities
│   │   └── hooks/       # Custom React hooks
│   ├── CLAUDE.md        # Web UI quick reference
│   └── package.json     # npm dependencies
│
├── obsidian-plugin/     # TypeScript Obsidian plugin (in dev)
├── CLAUDE.md            # This file
└── README.md            # Full architecture (Russian)
```

## Technology Stack

### Backend
- **Python 3.12+**, FastAPI, Uvicorn
- **Neo4j** graph database
- **Graphiti** for LLM integration
- **uv** for package management
- **pytest** for testing

### Frontend (pipgraph-web)
- **Next.js 16.1.1** (App Router, React 19, TypeScript)
- **Tailwind CSS v4** + **shadcn/ui** (New York style)
- **TanStack Query v5** (server state management)
- **React Hook Form + Zod** (form validation)
- **react-markdown** (content rendering)

### Frontend (obsidian-plugin)
- TypeScript, Svelte (in development)

## Quick Start

### Backend Development

```bash
cd backend/
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# Configure .env file
cp .env.example .env
# Edit: OPENROUTER_API_KEY, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

uvicorn app.api.main:app --reload
# Server: http://localhost:8000
# Docs: http://localhost:8000/docs
```

📖 **Detailed guide**: [backend/CLAUDE.md](backend/CLAUDE.md)

### Web UI Development

```bash
cd pipgraph-web/
npm install

# Optional: configure .env.local
# NEXT_PUBLIC_API_URL=http://localhost:8000

npm run dev
# Web UI: http://localhost:3000
```

📖 **Detailed guide**: [pipgraph-web/CLAUDE.md](pipgraph-web/CLAUDE.md)

## Backend Architecture

**Layered design**: API → Services → CRUD → Database

```
API Layer (app/api/)
  ↓ Pydantic validation
Service Layer (app/services/)
  ↓ PipGraphManager (single source of truth)
CRUD Layer (app/crud/)
  ↓ Cypher queries
Neo4j Database
```

### Key Backend Endpoints

All functionality via `/api/v1/dev`:

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/dev/process-note` | Full LLM pipeline |
| GET | `/dev/episodic` | Get episodic by UUID/name |
| GET | `/dev/episodics` | List all episodics |
| POST | `/dev/create-episode` | Lightweight episodic |
| POST | `/dev/para-entity` | Create PARA entity |
| GET | `/dev/para-entities` | List PARA entities |
| POST | `/dev/link-entity-episode` | Link entity to episode |
| POST | `/dev/make-suggestions` | Hybrid search |

**Full list**: `backend/app/api/endpoints/dev.py`

## Frontend Architecture (pipgraph-web)

**Client-Server Pattern**: React components → TanStack Query → Backend REST API

### Key Patterns

**TanStack Query** for all API calls:
```typescript
// Always use useQuery/useMutation
const { data, isLoading } = useQuery({
  queryKey: ['episodics'],
  queryFn: async () => {
    const res = await fetch(`${API_BASE}/api/v1/dev/episodics`);
    return res.json();
  },
});
```

**shadcn/ui via MCP Server**:
- Use MCP tools to fetch component source: `mcp__shadcn-ui-mcp__get_component`
- Save to `src/components/ui/{component-name}.tsx`
- Import and use: `import { Button } from '@/components/ui/button'`

**Zod + React Hook Form** for validation:
```typescript
const schema = z.object({
  name: z.string().min(1),
  content: z.string(),
});
type FormData = z.infer<typeof schema>;
```

## Configuration

### Backend (.env)
```bash
OPENROUTER_API_KEY=sk-or-v1-...
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
```

See [backend/docs/CONFIGURATION.md](backend/docs/CONFIGURATION.md)

### Frontend (.env.local)
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Testing

### Backend
```bash
cd backend/
pytest -m unit           # Fast unit tests
pytest -m integration    # Requires Neo4j, OpenRouter
pytest -m "not slow"     # Exclude LLM calls
```

See [backend/docs/TESTING.md](backend/docs/TESTING.md)

### Frontend
```bash
cd pipgraph-web/
npm run lint             # ESLint check
npm run build            # Production build test
```

## Documentation Structure

### Component-Specific Docs
- **[backend/CLAUDE.md](backend/CLAUDE.md)** — Backend quick reference (Python, FastAPI, Neo4j)
- **[pipgraph-web/CLAUDE.md](pipgraph-web/CLAUDE.md)** — Web UI quick reference (Next.js, TanStack Query, shadcn/ui)

### Backend Deep Dive (backend/docs/)
- **[CONFIGURATION.md](backend/docs/CONFIGURATION.md)** — Environment setup, .env variables
- **[TESTING.md](backend/docs/TESTING.md)** — Test strategy, fixtures, markers

### Root Documentation
- **[README.md](README.md)** — Full architecture overview (Russian, comprehensive)
- **[CLAUDE.md](CLAUDE.md)** — This file (quick reference for AI)

## Key Principles

1. **Separation of Concerns**: Backend (Python) handles all logic, frontends (Web/Obsidian) are thin clients
2. **REST API First**: All features exposed via stateless HTTP endpoints
3. **Type Safety**: Pydantic (backend) + Zod (frontend) for validation
4. **Single Source of Truth**: PipGraphManager for all database operations
5. **Human-in-the-Loop**: System suggests, user decides
6. **Minimize Over-Engineering**: Build only what's requested, no extra features

## Development Workflow

### When Working on Backend
1. Read [backend/CLAUDE.md](backend/CLAUDE.md) for detailed guidance
2. Use PipGraphManager for all database operations
3. Follow layered architecture: API → Services → CRUD
4. Write tests: `pytest -m unit` before committing

### When Working on Web UI
1. Read [pipgraph-web/CLAUDE.md](pipgraph-web/CLAUDE.md) for detailed guidance
2. Use TanStack Query for all API calls
3. Use shadcn/ui MCP tools for components
4. Always use Zod for form validation
5. Keep it simple: avoid over-engineering

### When Working on Integration
1. Ensure backend is running: `cd backend && uvicorn app.api.main:app --reload`
2. Ensure Neo4j is running: check `bolt://localhost:7687`
3. Check API docs: http://localhost:8000/docs
4. Test endpoints with curl/Postman before UI integration

## Data Model (Neo4j)

**Episodic** (note):
```cypher
(:Episodic {uuid, name, content, created_at, valid_at})
```

**PARA Entity**:
```cypher
(:Entity:Project|:Area|:Resource|:Archive {
  uuid, name, summary, name_embedding, attributes, created_at
})
```

**Relationships**:
- `(:Episodic)-[:MENTIONS]->(:Entity)` — episode mentions entity
- `(:Entity)-[:RELATES_TO]->(:Entity)` — entity-to-entity relation

## Common Tasks

### Add New Backend Endpoint
1. Create Pydantic schema in `app/api/schemas/`
2. Add endpoint in `app/api/endpoints/`
3. Implement logic in `app/services/`
4. Write tests in `tests/`

### Add New Web UI Component
1. Fetch shadcn component via MCP: `mcp__shadcn-ui-mcp__get_component`
2. Save to `src/components/ui/{name}.tsx`
3. Create feature component in `src/components/`
4. Integrate with TanStack Query for API calls

### Process a Note
```bash
# Backend must be running
curl -X POST http://localhost:8000/api/v1/dev/process-note \
  -H "Content-Type: application/json" \
  -d '{"name": "test.md", "episode_body": "My note content"}'
```

## Current Status

### ✅ Ready
- Backend REST API (`/api/v1/dev`)
- PipGraphManager (database operations)
- Entity extraction (LLM)
- Hybrid search (BM25 + vector)
- pipgraph-web basic structure

### 🚧 In Development
- pipgraph-web UI components
- Obsidian plugin integration

### 📋 Planned
- Real-time sync with Obsidian
- Graph visualizations
- Multi-user support

---

**For more details:**
- Backend specifics → [backend/CLAUDE.md](backend/CLAUDE.md)
- Web UI specifics → [pipgraph-web/CLAUDE.md](pipgraph-web/CLAUDE.md)
- Full architecture → [README.md](README.md)
