---
name: pipgraph-architecture
description: A comprehensive guide to the PipGraph backend structure, layer responsibilities (API, Workflows, Services, CRUD), and data flow. Use this skill when locating files, adding new components, tracing the execution pipeline, or debugging architecture violations.
---

# Architecture & Navigation

## Purpose
This skill defines the structural blueprint of the PipGraph backend. It enforces a strict layered architecture: **API → Workflows → Services → CRUD → Database**. Use this map to determine where code belongs and how components interact.

## Directory Structure Map

```text
app/
├── api/                  # 1. Interface Layer
│   ├── endpoints/        # REST Controllers (FastAPI)
│   └── schemas/          # DTOs (Request/Response models)
├── workflows/            # 2. Orchestration Layer (LangGraph)
│   ├── para_workflow.py  # Node definitions (Business steps)
│   ├── state.py          # State TypedDict & Serialization
│   └── conditions.py     # Conditional routing logic
├── services/             # 3. Business Logic Layer
│   ├── graphiti/         # Graphiti SDK Wrapper & Logic
│   ├── para/             # Context Identification (Mock/Real Switch)
│   ├── cascade_service.py # Auto-resolution logic
│   └── proposal_manager.py # Graph update coordinator
├── crud/                 # 4. Data Access Layer (Neo4j)
│   ├── relationship_crud.py # :SUGGESTS & :IS_PART_OF logic
│   ├── entity_crud.py    # Entity & :MENTIONS logic
│   └── para_crud.py      # Container management
├── models/               # Domain Models (Pydantic)
│   ├── entity.py         # Extracted entities
│   ├── para_entities.py  # Project/Area/Resource definitions
│   └── proposal.py       # Suggestion structures
└── db/                   # Infrastructure
    └── schema.py         # Neo4j constraints & indexes
```

## Layer Responsibilities (Rules of Engagement)

When implementing or modifying features, you must adhere to these strict layer boundaries:

### 1. API Layer (`app/api/`)
*   **Role**: Entry point, input validation, output formatting.
*   **Rule**: **NO business logic.** This layer only calls `workflows` or `services` and maps results to Pydantic schemas.
*   **Key Files**:
    *   `endpoints/workflow.py`: Handles start/resume operations.
    *   `endpoints/suggestions.py`: Manages the Inbox/Suggestion retrieval.

### 2. Workflow Layer (`app/workflows/`)
*   **Role**: State management, process orchestration, and handling Human-in-the-Loop (HITL) interrupts.
*   **Rule**: **NO direct DB access.** It delegates work to `services`. It manages the *sequence* of operations, not the implementation details.
*   **Key Files**:
    *   `langgraph_service.py`: Graph assembly and compilation.
    *   `para_workflow.py`: Individual node logic.

### 3. Service Layer (`app/services/`)
*   **Role**: The "Brain". Handles complex calculations, LLM interactions, and glue logic.
*   **Rule**: Coordinates between LLMs (Graphiti/OpenRouter) and CRUD.
*   **Key Components**:
    *   `PipGraphManager`: Wrapper around Graphiti core logic (extraction).
    *   `ProposalManager`: Converts AI proposals into Graph actions (Link vs Suggestion).
    *   `CascadeService`: Finds and applies similar decisions to other notes.
    *   `mock/*`: Deterministic implementations for testing.

### 4. CRUD Layer (`app/crud/`)
*   **Role**: The "Hands". Direct interaction with Neo4j.
*   **Rule**: **Pure Cypher queries only.** No LLM calls. All operations must be atomic.
*   **Key Classes**:
    *   `RelationshipCRUD`: Manages the critical `:SUGGESTS` (pending) and `:IS_PART_OF` (confirmed) edges.
    *   `EpisodicCRUD`: Manages Note nodes (adhering to the No-Cache Policy).

## Critical Data Flow: The Note Processing Pipeline

1.  **Start**: Request hits `api/endpoints/workflow.py` → calls `workflows/langgraph_service.start_workflow`.
2.  **L1/L2 Analysis**: `para_workflow.identify_context_node` calls `services.para.classify/generate`.
3.  **Graph Update**: `apply_proposal_node` calls `services.proposal_manager` → `crud.relationship_crud`.
4.  **Interrupt**: `wait_for_decision_node` checks database state and pauses execution if suggestions exist.
5.  **Resume**: User decision hits `api/.../resume` → calls `workflows...resume_workflow`.
6.  **Resolution**: `process_decision_node` calls `pipgraph_manager.process_user_decision`.
7.  **L3 Extraction**: `extract_content_node` calls `pipgraph_manager.extract_entities`.

## Integration Points

*   **Graphiti**: Located in `app/services/graphiti/`. Uses `CloudRuPatchedClient` to handle Qwen-specific JSON schema issues.
*   **Mocks**: Located in `app/services/mocks/`. Switching logic is handled in `app/services/para/__init__.py`.
*   **Neo4j**: Connection is managed via `app/crud/` classes using `config.settings`.
