# Backend Architecture

Detailed architectural documentation for the PipGraph backend, explaining design decisions, patterns, and implementation details.

## Table of Contents

- [Overview](#overview)
- [Architectural Principles](#architectural-principles)
- [Layered Architecture](#layered-architecture)
- [Data Flow](#data-flow)
- [Technology Choices](#technology-choices)
- [Design Patterns](#design-patterns)
- [Future Considerations](#future-considerations)

## Overview

The PipGraph backend is built on **FastAPI** with a strict **layered architecture** pattern. It processes notes using LLM-based entity extraction and stores results in a Neo4j graph database.

### Key Characteristics

- **Asynchronous by default**: Uses async/await for I/O operations
- **Type-safe**: Leverages Python type hints and Pydantic models
- **Testable**: Clear separation of concerns enables isolated testing
- **Scalable**: Layered design allows horizontal scaling
- **Maintainable**: Each layer has a single responsibility

## Architectural Principles

### 1. Separation of Concerns

Each layer has a specific responsibility and doesn't leak into others:

```
API Layer        → Request/Response handling, validation
Service Layer    → Business logic, orchestration
CRUD Layer       → Database operations
Models Layer     → Data structures, validation
```

### 2. Dependency Inversion

Upper layers depend on abstractions, not concrete implementations:

```python
# Service layer doesn't know about Neo4j specifics
def process_note(note: NotePayload) -> GraphData:
    # Business logic here
    graph_crud.save_graph_data(data)  # Abstract operation
```

### 3. Single Responsibility

Each module/function has one reason to change:

- `note_processor.py` - Note processing logic only
- `graph_crud.py` - Database operations only
- `notes.py` (endpoints) - HTTP/WebSocket handling only

### 4. Fail Fast

Validate early using Pydantic models:

```python
# Invalid data caught at API boundary
payload = NotePayload(**data)  # Raises ValidationError if invalid
```

### 5. Explicit is Better Than Implicit

- No magic: clear function signatures
- Type hints everywhere
- Explicit error handling

## Layered Architecture

```
┌─────────────────────────────────────────────────┐
│              Client (Obsidian/Web)              │
└───────────────────┬─────────────────────────────┘
                    │ WebSocket / REST
┌───────────────────▼─────────────────────────────┐
│            API Layer (app/api/)                 │
│  - FastAPI endpoints                            │
│  - WebSocket handlers                           │
│  - Request validation (Pydantic)                │
│  - Response serialization                       │
└───────────────────┬─────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────┐
│         Service Layer (app/services/)           │
│  - Business logic                               │
│  - LLM orchestration                            │
│  - Data transformation                          │
│  - Error handling                               │
└──────────────┬───────────────┬──────────────────┘
               │               │
       ┌───────▼────────┐ ┌───▼──────────────┐
       │  LLM Services  │ │   CRUD Layer     │
       │   (Graphiti)   │ │ (app/crud/)      │
       └────────────────┘ │  - Graph queries │
                          │  - Cypher ops    │
                          └────────┬─────────┘
                                   │
                          ┌────────▼─────────┐
                          │  Neo4j Database  │
                          └──────────────────┘
```

### Layer Details

#### API Layer (`app/api/`)

**Purpose**: Handle HTTP/WebSocket communication

**Responsibilities**:
- Accept incoming connections
- Validate request data with Pydantic
- Call service layer methods
- Format responses
- Handle transport errors

**Example**:
```python
@router.websocket("/ws/notes/process")
async def process_note_websocket(websocket: WebSocket):
    await websocket.accept()
    data = await websocket.receive_json()

    payload = NotePayload(**data)  # Validation

    # Send acknowledgment
    await websocket.send_json({"status": "processing"})

    # Call service layer
    result = await note_processor.process_and_store_note(payload)

    # Send result
    await websocket.send_json({"status": "done", "data": result.dict()})
```

**Key Files**:
- `main.py` - FastAPI app configuration
- `endpoints/notes.py` - Note processing endpoints

#### Service Layer (`app/services/`)

**Purpose**: Implement business logic

**Responsibilities**:
- Orchestrate operations across multiple subsystems
- Transform data between layers
- Implement business rules
- Handle domain errors

**Example**:
```python
async def process_and_store_note(note: NotePayload) -> GraphData:
    # 1. Extract entities and store in Neo4j (Graphiti handles both)
    graphiti = await get_graphiti()
    await graphiti.add_episode(
        name=note.file_path,
        episode_body=note.content,
        source=EpisodeType.text,
        source_description=f"Obsidian note from {note.file_path}",
        reference_time=datetime.now(timezone.utc)
    )
    # Note: Graphiti automatically extracts entities and writes to Neo4j

    # 2. Prepare response for Obsidian feedback cycle
    # TODO: Query Graphiti for extracted entities
    # TODO: Format for frontmatter update
    graph_data = prepare_feedback_data(note.file_path)

    return graph_data
```

**Key Files**:
- `note_processor.py` - Main note processing logic
- `llm_graphiti_client.py` - Graphiti LLM client management

#### CRUD Layer (`app/crud/`)

**Purpose**: Abstract database operations

**Responsibilities**:
- Execute database queries
- Map domain models to DB format
- Handle connection management
- Implement query optimization

**Example**:
```python
async def save_graph_data(graph_data: GraphData) -> bool:
    driver = get_neo4j_driver()

    async with driver.session() as session:
        # Create nodes
        for node in graph_data.nodes:
            await session.run(
                "MERGE (n:Node {id: $id}) SET n += $props",
                id=node.id,
                props=node.properties
            )

        # Create relationships
        for rel in graph_data.relationships:
            await session.run(
                """
                MATCH (a {id: $source}), (b {id: $target})
                MERGE (a)-[r:$type]->(b)
                SET r += $props
                """,
                source=rel.source_id,
                target=rel.target_id,
                type=rel.type,
                props=rel.properties
            )

    return True
```

**Key Files**:
- `graph_crud.py` - Graph database operations

#### Models Layer (`app/models/`)

**Purpose**: Define data structures

**Responsibilities**:
- Data validation
- Serialization/deserialization
- Type safety
- API contracts

**Example**:
```python
class NotePayload(BaseModel):
    file_path: str
    content: str

    @validator('file_path')
    def validate_path(cls, v):
        if not v.endswith('.md'):
            raise ValueError('Must be a markdown file')
        return v

class GraphData(BaseModel):
    nodes: List[Node]
    relationships: List[Relationship]
```

**Key Files**:
- `note.py` - Note-related models
- `graph.py` - Graph data models

## Data Flow

### Note Processing Flow

```
1. Client sends WebSocket message
   ↓
2. API Layer validates with NotePayload
   ↓
3. API sends "processing" acknowledgment
   ↓
4. Service Layer receives NotePayload
   ↓
5. Service calls Graphiti for entity extraction
   ↓
6. Graphiti extracts entities and stores directly in Neo4j
   (add_episode() handles both extraction and DB writes)
   ↓
7. Service prepares extracted entities for client
   ↓
8. API initiates feedback cycle with Obsidian
   ↓
9. Multiple feedback rounds (optional):
   - Client may request clarification
   - User may provide additional context
   - System refines entities based on feedback
   ↓
10. Final entities prepared for frontmatter
   ↓
11. API sends "done" with entities and relationships
   ↓
12. Client updates note frontmatter with verified data
```

### Error Handling Flow

```
Error occurs at any layer
   ↓
Layer catches exception
   ↓
Layer logs error with context
   ↓
Layer transforms to domain error
   ↓
Error propagates up to API layer
   ↓
API sends error response to client
```

## Technology Choices

### Why FastAPI?

**Pros**:
- Native async/await support
- Built-in WebSocket support
- Automatic OpenAPI documentation
- Pydantic integration
- Fast performance

**Alternatives considered**:
- Flask: Lacks native async
- Django: Too heavyweight for our needs
- Starlette: Too low-level

### Why Neo4j?

**Pros**:
- Native graph database
- Powerful query language (Cypher)
- Good Python driver
- Excellent visualization tools
- Community support

**Alternatives considered**:
- MemGraph: Less mature ecosystem
- ArangoDB: Multi-model, but we only need graphs
- PostgreSQL + AGE: Requires more setup

### Why Graphiti?

**Pros**:
- Purpose-built for temporal knowledge graphs
- Handles entity extraction
- Temporal relationship tracking
- OpenAI/Anthropic integration

**Alternatives considered**:
- Direct OpenAI API: More manual work
- LangChain: Too general-purpose
- Custom LLM pipeline: Reinventing the wheel

### Why Pydantic?

**Pros**:
- Runtime type validation
- FastAPI integration
- Clear error messages
- Serialization/deserialization
- Modern Python patterns

**Alternatives considered**:
- Marshmallow: Older, less integrated
- Dataclasses: No validation
- Manual validation: Error-prone

## Design Patterns

### Repository Pattern (CRUD Layer)

Abstracts data access logic:

```python
# Abstract interface (implicit in Python)
class GraphRepository:
    def save_graph_data(self, data: GraphData) -> bool: ...
    def get_node(self, node_id: str) -> Optional[Node]: ...

# Concrete implementation
class Neo4jGraphRepository(GraphRepository):
    def save_graph_data(self, data: GraphData) -> bool:
        # Neo4j-specific implementation
```

### Service Layer Pattern

Orchestrates business operations:

```python
class NoteProcessingService:
    def __init__(self, llm_client, graph_repo):
        self.llm_client = llm_client
        self.graph_repo = graph_repo

    async def process_note(self, note: NotePayload) -> GraphData:
        # Business logic orchestration
```

### Dependency Injection

Configuration-based dependencies:

```python
# Injected via settings
def get_neo4j_driver():
    return GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )

# Used in CRUD layer
driver = get_neo4j_driver()
```

### Async Context Managers

Resource management:

```python
async with driver.session() as session:
    # Session automatically closed
    result = await session.run(query)
```

## WebSocket Architecture

### Connection Lifecycle

```
1. Client establishes connection
   ws://localhost:8000/api/v1/ws/notes/process

2. Server accepts connection
   await websocket.accept()

3. Client sends message
   {"file_path": "...", "content": "..."}

4. Server validates and acknowledges
   {"status": "processing", "message": "..."}

5. Server processes (may take seconds)
   [Graphiti: LLM extraction + direct Neo4j storage]

6. Server sends extracted entities
   {"status": "entities_extracted", "entities": [...], "relationships": [...]}

7. Optional: Multiple feedback rounds
   - Client may send clarifications
   - Server refines and sends updates

8. Server sends final result with frontmatter
   {"status": "done", "frontmatter_update": {...}}

9. Client updates note frontmatter

10. Connection closes
    await websocket.close()
```

### Why WebSocket for Note Processing?

**Advantages**:
- Bidirectional communication
- Immediate acknowledgment
- Progress updates possible
- Lower overhead than polling

**Alternative (not chosen)**:
- REST + polling: More HTTP requests
- REST + webhooks: Requires callback URL
- Server-Sent Events: One-way only

## Obsidian Feedback Cycle

### Overview

After Graphiti processes a note and extracts entities, the system initiates a feedback cycle with the Obsidian client. This bidirectional communication allows for entity verification, user clarification, and ultimately updating the note's frontmatter with validated graph data.

### Feedback Cycle Flow

```
1. Note processed by Graphiti
   ↓
2. Entities extracted and stored in Neo4j
   ↓
3. Backend sends extracted entities to client
   {"status": "entities_extracted", "entities": [...], "relationships": [...]}
   ↓
4. Optional: Client requests clarification
   {"action": "clarify", "question": "Is 'Apple' a company or fruit?"}
   ↓
5. Optional: Backend refines with additional context
   - Re-query LLM with user input
   - Update graph with refined data
   ↓
6. Multiple rounds possible (steps 3-5 repeat as needed)
   ↓
7. Backend sends final validated entities
   {"status": "done", "frontmatter_update": {...}}
   ↓
8. Client updates note frontmatter
   - Add/update entities list
   - Add/update relationships
   - Mark as processed
```

### Frontmatter Update Structure

The final message includes structured data for updating the note's YAML frontmatter:

```yaml
---
# Original frontmatter preserved
title: "My Note"
date: 2025-01-15

# PipGraph additions
pipgraph:
  processed: true
  processed_at: "2025-01-15T10:30:00Z"
  entities:
    - name: "Neural Networks"
      type: "Concept"
      uuid: "abc-123"
    - name: "Machine Learning"
      type: "Field"
      uuid: "def-456"
  relationships:
    - source: "Neural Networks"
      target: "Machine Learning"
      type: "PART_OF"
---
```

### Feedback Scenarios

#### 1. Simple Case (No Feedback Needed)
```
Client → Note content
Backend → Processing...
Backend → Entities extracted (high confidence)
Backend → Done + frontmatter data
Client → Update frontmatter
```

#### 2. Clarification Required
```
Client → Note content
Backend → Processing...
Backend → Entities extracted (low confidence for some)
Backend → Request clarification: "Is 'Python' the language or snake?"
Client → User responds: "Programming language"
Backend → Re-process with context
Backend → Done + refined frontmatter data
Client → Update frontmatter
```

#### 3. User-Initiated Refinement
```
Client → Note content
Backend → Processing...
Backend → Entities extracted
Backend → Proposed frontmatter
Client → User reviews, requests changes: "Add tag: #research"
Backend → Update graph with user input
Backend → Done + updated frontmatter
Client → Update frontmatter
```

### Implementation Considerations

**Current Status**:
- ✅ Graphiti integration for entity extraction
- ✅ Direct Neo4j storage via `add_episode()`
- ⏳ Feedback cycle messaging protocol (planned)
- ⏳ Frontmatter formatting logic (planned)
- ⏳ Multi-round clarification handling (planned)

**Future Enhancements**:
- Confidence scores for entities
- Conflict resolution when entities differ from existing frontmatter
- Batch processing with feedback aggregation
- Learning from user corrections to improve future extractions

### WebSocket Message Protocol

**Entity Extraction Complete**:
```json
{
  "status": "entities_extracted",
  "confidence": 0.85,
  "entities": [
    {"name": "...", "type": "...", "uuid": "...", "confidence": 0.9}
  ],
  "relationships": [
    {"source": "...", "target": "...", "type": "...", "confidence": 0.8}
  ],
  "requires_clarification": false
}
```

**Clarification Request**:
```json
{
  "status": "clarification_needed",
  "questions": [
    {
      "entity": "Apple",
      "question": "Is this a company, fruit, or something else?",
      "options": ["Company", "Fruit", "Other"]
    }
  ]
}
```

**Final Update**:
```json
{
  "status": "done",
  "frontmatter_update": {
    "pipgraph": {
      "processed": true,
      "processed_at": "2025-01-15T10:30:00Z",
      "entities": [...],
      "relationships": [...]
    }
  }
}
```

## Future Considerations

### Scalability

**Horizontal Scaling**:
```
                    Load Balancer
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
    Backend 1        Backend 2        Backend 3
        │                │                │
        └────────────────┼────────────────┘
                         ▼
                    Neo4j Cluster
```

**Challenges**:
- WebSocket sticky sessions
- Shared state management
- Database connection pooling

### Caching

**Strategy**:
```
Request → Cache Check → Cache Hit? → Return
                    │
                    └→ Cache Miss → Process → Store in Cache → Return
```

**What to cache**:
- LLM responses (expensive)
- Frequently accessed graph queries
- User session data

### Background Jobs

**Current**: Synchronous processing in WebSocket

**Future**: Asynchronous job queue
```
WebSocket → Enqueue Job → Return Job ID
                │
                ▼
          Worker picks up job
                │
                ▼
          Process & store result
                │
                ▼
          Notify client (WebSocket or webhook)
```

**Technologies**:
- Celery + Redis
- RQ (Redis Queue)
- AWS SQS + Lambda

### Multi-tenancy

**Approach**: Database per tenant
```
User → Auth → Tenant ID → Neo4j DB selection
```

**Considerations**:
- Connection pool per tenant
- Data isolation
- Backup strategies

## Related Documentation

- [Configuration Guide](CONFIGURATION.md) - Environment setup
- [Testing Guide](TESTING.md) - Testing strategy
- [Backend README](../README.md) - Getting started
- [TODO](../TODO.md) - Planned improvements
