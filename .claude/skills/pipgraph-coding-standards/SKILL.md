---
name: pipgraph-coding-standards
description: Definitive guidelines for code style, Pydantic usage, async patterns, configuration management, and PipGraphManager usage. Use this skill to ensure code consistency, proper error handling, and adherence to architectural principles.
---

# Coding Standards & Best Practices

## Purpose
Follow these guidelines to maintain code quality, consistency, and reliability across the PipGraph backend.

**Note:** All file paths in this skill are relative to the `backend/` directory (e.g., `app/services/` refers to `backend/app/services/`).

## 1. Coding Style & Patterns

### Imports
**Rule**: Prefer module-level imports for internal components (`services`, `crud`) to avoid circular dependencies and make the origin clear.
*   ✅ **Good**: `from app.services.graphiti import pipgraph_manager`
*   ✅ **Good**: `from app.crud import relationship_crud`
*   ❌ **Avoid**: `from app.crud.relationship_crud import RelationshipCRUD` (for commonly used modules)

**Import Order**:
1. Standard library imports
2. Third-party imports (FastAPI, Pydantic, Neo4j, etc.)
3. Local application imports (`from app...`)

### Async/Await
**Rule**: The entire pipeline is asynchronous.
*   FastAPI endpoints: `async def`
*   Neo4j operations: All CRUD methods are `async`
*   PipGraphManager methods: All `async def`
*   LLM calls (Graphiti): Asynchronous

**Example**:
```python
@router.post("/process-note")
async def process_note(request: ProcessNoteRequest):
    manager = PipGraphManager()
    result = await manager.process_note(
        name=request.name,
        content=request.episode_body
    )
    return result
```

### Pydantic Models
**Rule**: Use Pydantic for all data boundaries (API inputs/outputs, domain models).
*   **Config**: Use `model_config` dict instead of nested `class Config`.
*   **Fields**: Always include `description="..."` for fields used by LLMs (Graphiti/OpenRouter).
*   **Validation**: Use Field validators where appropriate.

**Example**:
```python
from pydantic import BaseModel, Field

class CreateEpisodeRequest(BaseModel):
    name: str = Field(..., description="Note filename (e.g., 'daily/2024-01-15.md')")
    content: str = Field(..., description="Note body content")

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "daily/2024-01-15.md",
                "content": "Today I worked on the API..."
            }
        }
    }
```

### Working with Graphiti Nodes
**Rule**: Always use PipGraph wrapper classes, never import from `graphiti_core.nodes` directly in API/Service layers.
*   ✅ **Good**: `from app.models.nodes import PipGraphEpisodicNode`
*   ❌ **Avoid**: `from graphiti_core.nodes import EpisodicNode` (in Service/API layers)
*   **Pattern**: API schemas → PipGraphManager → Graphiti operations → PipGraph wrappers

**Example**:
```python
# API: Simple request schema
class CreateEpisodeRequest(BaseModel):
    name: str
    content: str

# Service (PipGraphManager): Handle Graphiti operations
async def create_episode(self, name: str, content: str):
    # PipGraphManager internally works with Graphiti
    episode = await self.graphiti.add_episode(
        name=name,
        episode_body=content,
        source_description="User-created note"
    )
    # Returns Graphiti EpisodicNode
    return episode
```

### Logging
**Rule**: Use structured logging. Never use `print()`.
```python
import logging
logger = logging.getLogger(__name__)

# Usage
logger.info(f"Processing note: {note_name}")
logger.error(f"Failed to create entity: {error}", exc_info=True)
logger.debug(f"Query result: {result}")
```

**Log Levels**:
- `DEBUG`: Detailed information for debugging
- `INFO`: General informational messages
- `WARNING`: Warning messages for recoverable issues
- `ERROR`: Error messages for failures
- `CRITICAL`: Critical errors that may cause system failure

## 2. PipGraphManager Usage (CRITICAL)

**Rule**: ALL database operations MUST go through `PipGraphManager`. Never use CRUD classes directly in API or business logic.

### Why PipGraphManager?
- **Single Source of Truth**: Centralized database access
- **Consistency**: Ensures Graphiti schema compliance
- **Type Safety**: Returns typed Graphiti objects
- **Async-First**: All methods are asynchronous
- **Testing**: Easier to mock and test

### Common Operations

**Create Episode**:
```python
from app.services.graphiti.pipgraph_manager import PipGraphManager

manager = PipGraphManager()
episode = await manager.create_episode(
    name="path/to/note.md",
    episode_body="Note content",
    source_description="User note"
)
```

**Get Episodic**:
```python
# By name
episodic = await manager.get_episodic_by_name("path/to/note.md")

# By UUID
episodic = await manager.get_episodic_by_uuid(uuid_obj)

# List all
episodics = await manager.list_episodics(limit=100)
```

**Create PARA Entity**:
```python
entity = await manager.create_para_entity(
    para_type="Project",
    name="Website Redesign",
    summary="Redesign company website with modern UI"
)
```

**Link Entity to Episode**:
```python
edge = await manager.link_entity_to_episode(
    episodic_uuid=episode_uuid,
    entity_uuid=entity_uuid
)
```

### When to Use CRUD Classes Directly
**Never in API/Service layers.** CRUD classes are internal implementation details used by PipGraphManager.

Only use CRUD directly if:
1. You're implementing a new PipGraphManager method
2. You're writing low-level database utilities

## 3. Configuration (`config/settings.py`)

We use `pydantic-settings` to manage environment variables.

**Access**:
```python
from config.settings import settings

neo4j_uri = settings.NEO4J_URI
api_key = settings.OPENROUTER_API_KEY
```

**Key Variables**:
*   `NEO4J_URI` - Neo4j connection string (bolt://localhost:7687)
*   `NEO4J_USER` - Neo4j username
*   `NEO4J_PASSWORD` - Neo4j password
*   `OPENROUTER_API_KEY` - OpenRouter API key for LLM
*   `LOG_LEVEL` - Logging level (default: INFO)
*   `GRAPHITI_LLM_MODEL` - LLM model name (default: qwen/qwen-2.5-72b-instruct)

**Best Practices**:
- Never hardcode sensitive values
- Use `.env` file for local development
- Document all new environment variables in `.env.example`

## 4. Error Handling

### FastAPI Endpoints
Use HTTPException for API errors:
```python
from fastapi import HTTPException

@router.get("/episodic")
async def get_episodic(name: str):
    manager = PipGraphManager()
    episodic = await manager.get_episodic_by_name(name)

    if not episodic:
        raise HTTPException(
            status_code=404,
            detail=f"Episodic not found: {name}"
        )

    return episodic
```

### Service Layer
Raise descriptive exceptions:
```python
class EntityNotFoundError(Exception):
    """Raised when entity is not found in database"""
    pass

# Usage
if not entity:
    raise EntityNotFoundError(f"Entity with UUID {uuid} not found")
```

### CRUD Layer
Let database exceptions propagate or wrap them:
```python
try:
    result = await session.run(query, parameters)
except Exception as e:
    logger.error(f"Query failed: {query}", exc_info=True)
    raise
```

## 5. Special Project Mechanisms

### Graphiti Node Wrappers
**Why**: Protects from Graphiti API changes and adds PipGraph-specific fields.
**Files**: `app/models/nodes.py` — `PipGraphEpisodicNode`, `PipGraphEntityNode`.
**Usage**: PipGraphManager internally handles wrapper conversions. API layer works with simple schemas.

### Mock-First Switching
To avoid LLM costs during development, we can switch between Real and Mock implementations in `app/services/para/__init__.py`.
*   **Mechanism**: Comment/Uncomment imports.
*   **Instruction**: When developing logic flow, ensure Mocks are active. When testing prompts, switch to Real.

**Example** (`app/services/para/__init__.py`):
```python
# Real implementation (default)
from .real_service import classify_note_para, generate_para_suggestions

# Mock implementation (for testing)
# from .mock_service import classify_note_para, generate_para_suggestions
```

### Cloud.ru / Qwen Patch
**File**: `app/services/graphiti/cloudru_patched_client.py`
**Why**: Qwen models sometimes return JSON schema inside the response body, breaking Pydantic validation.
**Fix**: `CloudRuPatchedClient` injects specific prompt instructions to force correct JSON output.
**Usage**: Automatically used by PipGraphManager when initializing Graphiti client.

### Neo4j Schema Management
**File**: `app/db/schema.py`
**Usage**: Run this script directly to apply constraints and indexes:
```bash
cd backend/
python -m app.db.schema
```

**What it does**:
- Creates unique constraints on UUIDs
- Creates indexes for common queries
- Ensures schema consistency

## 6. Code Organization Principles

### Separation of Concerns
1. **API Layer** (`app/api/`): Request validation, response formatting
2. **Service Layer** (`app/services/`): Business logic, LLM interactions
3. **CRUD Layer** (`app/crud/`): Database queries
4. **Models** (`app/models/`): Data structures

### Single Responsibility
Each module/class should have ONE clear purpose:
- ✅ `PipGraphManager`: Database operations coordinator
- ✅ `RelationshipCRUD`: Relationship-specific queries
- ✅ `dev.py`: Development endpoints

### DRY (Don't Repeat Yourself)
- Extract common logic to utility functions
- Use PipGraphManager methods instead of duplicating queries
- Share schemas between endpoints when appropriate

### KISS (Keep It Simple, Stupid)
- Avoid over-engineering
- Use direct REST calls, not complex orchestration
- Prefer simple solutions over clever ones

## 7. Common Patterns & Anti-Patterns

### ✅ Good Patterns

**1. Using PipGraphManager in Endpoints**:
```python
@router.post("/create-episode")
async def create_episode(request: CreateEpisodeRequest):
    manager = PipGraphManager()
    episode = await manager.create_episode(
        name=request.name,
        episode_body=request.content
    )
    return {"uuid": str(episode.uuid), "name": episode.name}
```

**2. Proper Async Operations**:
```python
async def process_multiple_notes(notes: list[str]):
    manager = PipGraphManager()
    results = []
    for note in notes:
        result = await manager.process_note(name=note, content="...")
        results.append(result)
    return results
```

**3. Type Hints**:
```python
from uuid import UUID
from graphiti_core.nodes import EpisodicNode

async def get_episode(uuid: UUID) -> EpisodicNode | None:
    manager = PipGraphManager()
    return await manager.get_episodic_by_uuid(uuid)
```

### ❌ Anti-Patterns

**1. Direct CRUD Usage in API**:
```python
# BAD: Don't do this
@router.get("/episodic")
async def get_episodic(name: str):
    crud = EpisodicCRUD()  # ❌ Wrong!
    return await crud.get_by_name(name)

# GOOD: Use PipGraphManager
@router.get("/episodic")
async def get_episodic(name: str):
    manager = PipGraphManager()  # ✅ Correct
    return await manager.get_episodic_by_name(name)
```

**2. Synchronous Operations**:
```python
# BAD
def process_note(name: str):  # ❌ Missing async
    manager = PipGraphManager()
    return manager.create_episode(...)  # ❌ Missing await

# GOOD
async def process_note(name: str):  # ✅
    manager = PipGraphManager()
    return await manager.create_episode(...)  # ✅
```

**3. Mixing Business Logic in API**:
```python
# BAD
@router.post("/process")
async def process(request: Request):
    # ❌ Business logic in API layer
    if request.content.startswith("TODO:"):
        para_type = "Project"
    else:
        para_type = "Resource"
    ...

# GOOD
@router.post("/process")
async def process(request: Request):
    manager = PipGraphManager()
    # ✅ Business logic in service layer
    return await manager.process_note(...)
```

## 8. Documentation Standards

### Docstrings
Use Google-style docstrings for functions and classes:

```python
async def create_para_entity(
    self,
    para_type: str,
    name: str,
    summary: str
) -> EntityNode:
    """Create a new PARA entity (Project/Area/Resource/Archive).

    Args:
        para_type: Type of PARA entity (Project, Area, Resource, Archive)
        name: Entity name
        summary: Brief description of the entity

    Returns:
        EntityNode: Created entity node

    Raises:
        ValueError: If para_type is invalid
    """
    ...
```

### Comments
- Use comments for "why", not "what"
- ✅ Good: `# Qwen models need explicit instruction to avoid schema in output`
- ❌ Bad: `# Create entity`

### README and CLAUDE.md
- Keep documentation up to date
- Update CLAUDE.md when architecture changes
- Document all environment variables in .env.example

## 9. Performance Considerations

### Database Queries
- Use `LIMIT` on all list operations
- Avoid N+1 queries (use batch operations when possible)
- Use indexes for frequently queried fields

### Caching
Currently, caching is minimal. Future considerations:
- Cache frequently accessed PARA entities
- Cache BM25 search results
- Use Redis for distributed caching

### Async Operations
- Use `asyncio.gather()` for parallel operations when appropriate
- Don't block the event loop with synchronous I/O

## 10. Security Best Practices

### Environment Variables
- Never commit `.env` files
- Use `.env.example` as template
- Rotate API keys regularly

### Input Validation
- Always validate user input with Pydantic
- Sanitize file paths (prevent directory traversal)
- Validate UUIDs before database queries

### Database Security
- Use parameterized queries (Neo4j driver handles this)
- Never construct Cypher queries with string concatenation
- Limit database user permissions

## Summary Checklist

Before committing code, verify:
- [ ] All database operations go through PipGraphManager
- [ ] All functions are `async def` where appropriate
- [ ] Pydantic models used for all data boundaries
- [ ] Proper logging (no `print()` statements)
- [ ] Type hints on all function signatures
- [ ] Error handling with appropriate exceptions
- [ ] Documentation (docstrings) for public functions
- [ ] Environment variables in .env.example
- [ ] No hardcoded credentials or sensitive data
- [ ] Code follows layer separation (API → Services → CRUD)
