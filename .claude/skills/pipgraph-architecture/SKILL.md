---
name: pipgraph-architecture
description: A comprehensive guide to the PipGraph backend structure, layer responsibilities (API, Services, CRUD), and data flow. Use this skill when locating files, adding new components, tracing the execution pipeline, or debugging architecture violations.
---

# Architecture & Navigation

## Purpose
This skill defines the structural blueprint of the PipGraph backend. It enforces a strict layered architecture: **API → Services → CRUD → Database**. Use this map to determine where code belongs and how components interact.

**Note:** All file paths in this skill are relative to the `backend/` directory (e.g., `app/api/` refers to `backend/app/api/`).

## Directory Structure Map

```text
app/
├── api/                  # 1. Interface Layer
│   ├── endpoints/        # REST Controllers (FastAPI)
│   │   └── dev.py        # Main development endpoints
│   ├── schemas/          # DTOs (Request/Response models)
│   └── main.py           # FastAPI app initialization
├── services/             # 2. Business Logic Layer
│   ├── graphiti/         # Graphiti SDK Wrapper & PipGraphManager
│   │   ├── pipgraph_manager.py  # SINGLE SOURCE OF TRUTH for DB ops
│   │   └── cloudru_patched_client.py  # Qwen-specific patches
│   └── para/             # Context Identification (Mock/Real Switch)
├── crud/                 # 3. Data Access Layer (Neo4j)
│   ├── relationship_crud.py # Relationship management
│   ├── entity_crud.py    # Entity queries
│   └── base.py           # Base CRUD utilities
├── models/               # Domain Models (Pydantic)
│   ├── nodes.py          # Graphiti wrapper classes
│   ├── entity.py         # Extracted entities
│   ├── para_entities.py  # PARA definitions
│   └── proposal.py       # Suggestion structures
└── db/                   # Infrastructure
    ├── schema.py         # Neo4j constraints & indexes
    └── connection.py     # Neo4j driver setup
```

## Layer Responsibilities (Rules of Engagement)

When implementing or modifying features, you must adhere to these strict layer boundaries:

### 1. API Layer (`app/api/`)
*   **Role**: Entry point, input validation, output formatting.
*   **Rule**: **NO business logic.** This layer only calls `services` (primarily `PipGraphManager`) and maps results to Pydantic schemas.
*   **Key Files**:
    *   `endpoints/dev.py`: All development endpoints (`/api/v1/dev/*`)
    *   `schemas/`: Request/response models

**Current Endpoints** (`/api/v1/dev`):
- `POST /process-note` - Full LLM pipeline
- `GET /episodic` - Get episodic by UUID/name
- `GET /episodics` - List all episodics
- `POST /create-episode` - Lightweight episodic creation
- `POST /para-entity` - Create PARA entity
- `GET /para-entities` - List PARA entities
- `POST /link-entity-episode` - Link entity to episode
- `POST /make-suggestions` - Hybrid search (BM25 + vector)

### 2. Service Layer (`app/services/`)
*   **Role**: The "Brain". Handles complex calculations, LLM interactions, and business logic.
*   **Rule**: Coordinates between LLMs (Graphiti/OpenRouter) and CRUD. **All database operations MUST go through PipGraphManager.**
*   **Key Components**:
    *   **`PipGraphManager`** (in `services/graphiti/pipgraph_manager.py`): **SINGLE SOURCE OF TRUTH** for all Neo4j CRUD operations. This is the ONLY way to interact with the database.
    *   `para/`: Context identification services (Mock/Real implementations)

**PipGraphManager is Critical:**
- All database reads/writes go through it
- Returns Graphiti node objects (EpisodicNode, EntityNode)
- UUID-based operations
- Async-first design
- Type-safe with Pydantic models

### 3. CRUD Layer (`app/crud/`)
*   **Role**: The "Hands". Direct interaction with Neo4j.
*   **Rule**: **Pure Cypher queries only.** No LLM calls. All operations must be atomic.
*   **Key Classes**:
    *   `RelationshipCRUD`: Manages relationships (`:MENTIONS`, `:RELATES_TO`)
    *   `EntityCRUD`: Entity queries and searches
    *   **REMOVED**: `EpisodicCRUD`, `PARAContainerCRUD` (use PipGraphManager instead)

**Important**: Direct CRUD usage is discouraged. Always prefer PipGraphManager for database operations.

### 4. Models Layer (`app/models/`)
*   **Role**: Schema definitions and data wrappers.
*   **Rule**: **Use PipGraph wrappers, not raw Graphiti nodes.** API schemas stay separate from Graphiti schemas.
*   **Key Files**:
    *   `nodes.py`: `PipGraphEpisodicNode`, `PipGraphEntityNode` — extend graphiti_core with PipGraph fields
    *   `para_entities.py`: PARA container definitions (Project, Area, Resource, Archive)
*   **Pattern**: API schemas → Service (maps to) → Graphiti wrappers

## Critical Data Flow: The Note Processing Pipeline

### Direct Processing (No Workflows)
The system uses a **direct processing** model, not complex workflow orchestration:

1.  **Entry**: Request hits `api/endpoints/dev.py` endpoint
2.  **Validation**: FastAPI + Pydantic validate request
3.  **Processing**: Endpoint calls `PipGraphManager` method
4.  **LLM Interaction**: PipGraphManager uses Graphiti for entity extraction
5.  **Database**: PipGraphManager executes CRUD operations
6.  **Response**: Results returned as Pydantic models

### Example: Process Note Flow
```
POST /api/v1/dev/process-note
  ↓
dev.py endpoint validates request
  ↓
Calls: await manager.process_note(name, content, ...)
  ↓
PipGraphManager:
  1. Create/update Episodic node
  2. Extract entities via Graphiti LLM
  3. Create Entity nodes
  4. Create :MENTIONS relationships
  ↓
Return ProcessingResult to API
```

### Example: Hybrid Search Flow
```
POST /api/v1/dev/make-suggestions
  ↓
dev.py endpoint validates request
  ↓
Calls: await manager.make_suggestions(episode_name, query, ...)
  ↓
PipGraphManager:
  1. BM25 keyword search
  2. Vector similarity search
  3. Combine and rank results
  ↓
Return list of PARA entities
```

## Schema Consistency (Graphiti Model)

All nodes created by `PipGraphManager` use **Graphiti schema**:

### Episodic Nodes
```cypher
(:Episodic {
  uuid: String,
  name: String,
  content: String,
  created_at: DateTime,
  valid_at: DateTime
})
```

### PARA Entity Nodes
```cypher
(:Entity:Project|:Area|:Resource|:Archive {
  uuid: String,
  name: String,
  summary: String,
  name_embedding: Vector,
  attributes: Map,
  created_at: DateTime
})
```

### Relationships
- `(:Episodic)-[:MENTIONS]->(:Entity)` — Episode mentions entity
- `(:Entity)-[:RELATES_TO]->(:Entity)` — Entity-to-entity relation

**Critical Rule**: Never create nodes manually with Cypher. Always use PipGraphManager methods to ensure schema consistency.

## Integration Points

### Graphiti SDK
*   **Location**: `app/services/graphiti/`
*   **Purpose**: LLM-powered entity extraction and graph operations
*   **Custom Client**: `CloudRuPatchedClient` handles Qwen-specific JSON schema issues
*   **Wrapper**: `PipGraphManager` wraps Graphiti operations with PipGraph-specific logic

### Mock Services
*   **Location**: `app/services/mocks/`
*   **Purpose**: Deterministic implementations for testing
*   **Switching**: Handled in `app/services/para/__init__.py`
*   **Use Case**: Unit tests that don't require real LLM calls

### Neo4j Database
*   **Connection**: Managed via `app/db/connection.py`
*   **Config**: Environment variables (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
*   **Access**: Always through PipGraphManager, never direct driver usage in business logic

## Key Architectural Principles

1. **Single Source of Truth**: PipGraphManager is the ONLY interface for database operations
2. **Layered Architecture**: API → Services → CRUD → Database (strict separation)
3. **Non-Destructive Processing**: Never modify note body content, only YAML frontmatter
4. **Async-First**: All I/O operations are asynchronous
5. **Type Safety**: Pydantic models everywhere (API, Services, CRUD)
6. **Direct Processing**: No complex workflow orchestration, direct REST API calls

## Common Patterns

### Adding a New Endpoint
1. Create Pydantic schema in `app/api/schemas/`
2. Add endpoint in `app/api/endpoints/dev.py`
3. Call `PipGraphManager` method (create if needed)
4. Map result to response schema

### Adding PipGraphManager Method
1. Define method in `app/services/graphiti/pipgraph_manager.py`
2. Use existing CRUD classes if needed
3. Return Graphiti objects (EpisodicNode, EntityNode)
4. Keep async-first, UUID-based

### Database Query
1. Never write raw Cypher in API/Services
2. Add method to appropriate CRUD class (`app/crud/`)
3. Call CRUD method from PipGraphManager
4. PipGraphManager exposes high-level interface to API

## File Location Quick Reference

**Need to find where to...**

| Task | Location | Example File |
|------|----------|--------------|
| Add REST endpoint | `app/api/endpoints/` | `dev.py` |
| Define request/response schema | `app/api/schemas/` | Various |
| Implement business logic | `app/services/graphiti/` | `pipgraph_manager.py` |
| Write database query | `app/crud/` | `entity_crud.py` |
| Define domain model | `app/models/` | `para_entities.py` |
| Configure database | `app/db/` | `connection.py` |

## Troubleshooting Architecture Issues

**Symptom**: Business logic in API layer
- **Solution**: Move to PipGraphManager method in `app/services/graphiti/`

**Symptom**: Direct Neo4j driver usage in services
- **Solution**: Add method to CRUD class, call from PipGraphManager

**Symptom**: Inconsistent node schema
- **Solution**: Always use PipGraphManager methods, never raw Cypher for node creation

**Symptom**: Synchronous I/O operations
- **Solution**: Use `async`/`await` for all database and LLM calls

**Symptom**: Can't find where to add feature
- **Solution**: Follow API → Services → CRUD flow, refer to File Location Quick Reference
