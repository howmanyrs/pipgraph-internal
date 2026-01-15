# PipGraph Backend — Conceptual Manifest

## Project Overview
PipGraph is an intelligent backend engine designed to bridge unstructured Markdown notes (Obsidian) with a structured Knowledge Graph (Neo4j). It acts as a "second brain" processor that structures, links, and classifies information while strictly adhering to a **Human-in-the-Loop** philosophy.

The system does not modify the body of user notes. Instead, it builds an external graph layer and syncs metadata back to the note's YAML frontmatter.

## Core Philosophy

1.  **Non-Destructive Processing**: The text content of notes is sacred. The system reads notes but only writes to a dedicated metadata section (YAML) or the external database.
2.  **Graph-First Structure**: Information is stored as nodes (Episodes, Entities, PARA Containers) and edges (Relationships), enabling complex semantic queries that flat file searches cannot handle.
3.  **Direct Processing**: The system provides direct REST API access to LLM-powered processing and hybrid search, without complex workflow orchestration.

## Business Logic & Methodology

### 1. The PARA Method
The system organizes knowledge based on the PARA methodology by Tiago Forte. Every note (Episode) is evaluated for context:
-   **Projects**: Short-term efforts with goals and deadlines.
-   **Areas**: Long-term responsibilities with standards to maintain.
-   **Resources**: Topics or themes of ongoing interest.
-   **Archives**: Inactive items from the above categories.
-   **Inbox**: The default holding area for unclassified content.

### 2. The Processing Pipeline
Data flows through a direct processing pipeline:
1.  **Ingestion**: A note is received as an "Episode" (an event in time).
2.  **Entity Extraction**: The system extracts entities (Tasks, Concepts, Persons, Technologies) from the text using LLM.
3.  **Graph Storage**: Extracted entities are stored in Neo4j with relationships to the Episode.
4.  **Hybrid Search**: When needed, the system can find relevant PARA entities using BM25 + vector similarity search.

## Key Features

### Natural Language Search
The system converts natural language questions (e.g., "What tasks did we discuss regarding the API migration last week?") into formal graph queries (Cypher), allowing users to interrogate their knowledge base without learning query languages.

### No-Cache Policy (Episodic Memory)
The "Episodic" nodes (the notes) do not store context permanently in their own properties. Context is derived dynamically by traversing relationships (`:IS_PART_OF`) in the graph. This ensures that if a Project is renamed or moved, the historical notes linked to it remain valid without needing bulk updates.

## Data Layer Architecture

### CRUD Operations via PipGraphManager

**All database operations** are performed through `PipGraphManager` (located in `app/services/graphiti/pipgraph_manager.py`). This is the **single source of truth** for Neo4j CRUD operations.

**Key Principles:**
- **Async-first**: All methods are asynchronous
- **Graphiti integration**: Returns Graphiti node objects (EpisodicNode, EntityNode)
- **UUID-based**: Uses UUIDs as primary identifiers
- **Type-safe**: Leverages Pydantic models from Graphiti

### PipGraphManager Methods

**Episodic Operations:**
```python
# Retrieve
episodic = await manager.get_episodic_by_name("path/to/note.md")
episodics = await manager.list_episodics(limit=100)

# Modify
success = await manager.update_episodic_timestamp(uuid, valid_at)
success = await manager.delete_episodic(uuid)

# Create (full processing pipeline)
result = await manager.process_note(name, content, ...)
# Or lightweight creation
episode = await manager.create_episode(name, content, ...)
```

**Entity Operations:**
```python
# Retrieve
entity = await manager.get_para_entity_by_uuid(uuid)
entity = await manager.get_para_entity_by_name("Project Alpha", para_type="Project")
entities = await manager.list_para_entities(limit=100, para_types=["project", "area"])

# Create
entity = await manager.create_para_entity(para_type="Project", name="Website Redesign", summary="...")
inbox = await manager.ensure_inbox_exists()

# Link
edge = await manager.link_entity_to_episode(episodic_uuid, entity_uuid)
```

**Legacy CRUD Classes (REMOVED):**
- ~~`EpisodicCRUD`~~ - Removed, use `PipGraphManager`
- ~~`PARAContainerCRUD`~~ - Removed, use `PipGraphManager`
- `RelationshipCRUD` - Core CRUD for relationship management
- `EntityCRUD` - Core CRUD for entity queries

### Schema Consistency

All nodes created by `PipGraphManager` use **Graphiti schema**:
- **Episodic**: `:Episodic {uuid, name, content, created_at, valid_at, ...}`
- **PARA Entities**: `:Entity:Project`, `:Entity:Area`, `:Entity:Resource`, `:Entity:Archive`
  - Properties: `uuid`, `name`, `summary`, `name_embedding`, `attributes`, `created_at`
- **Relationships**: `:MENTIONS` (Episodic → Entity), `:RELATES_TO` (Entity → Entity)

**Never create nodes manually** - always use PipGraphManager to ensure schema consistency.

## Documentation Structure
For technical implementation details, refer to the codebase:
-   **Architecture & Navigation**: Folder structure, layers, and key components.
-   **Coding Standards**: Testing, configuration, and patterns.