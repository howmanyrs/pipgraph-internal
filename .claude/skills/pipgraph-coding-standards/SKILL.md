---
name: pipgraph-coding-standards
description: Definitive guidelines for code style, Pydantic usage, async patterns, configuration management, and testing strategies. Use this skill to ensure code consistency, proper error handling, and correct test categorization (Unit vs Integration vs Slow).
---

# Coding Standards & Testing

## Purpose
Follow these guidelines to maintain code quality, consistency, and reliability across the PipGraph backend.

**Note:** All file paths in this skill are relative to the `backend/` directory (e.g., `app/services/` refers to `backend/app/services/`).

## 1. Coding Style & Patterns

### Imports
**Rule**: Prefer module-level imports for internal components (`services`, `workflows`, `crud`) to avoid circular dependencies and make the origin clear.
*   ✅ **Good**: `from app.services import para` → `para.classify_note_para()`
*   ✅ **Good**: `from app.crud import relationship_crud` → `relationship_crud.RelationshipCRUD()`
*   ❌ **Avoid**: `from app.services.para import classify_note_para` (Context is lost)

### Async/Await
**Rule**: The entire pipeline is asynchronous.
*   FastAPI endpoints: `async def`
*   Neo4j drivers: `async with driver.session()`
*   LangGraph nodes: `async def node_name(state)`

### Pydantic Models
**Rule**: Use Pydantic for all data boundaries (API inputs/outputs, Graphiti schemas).
*   **Config**: Use `model_config` dict instead of nested `class Config`.
*   **Fields**: Always include `description="..."` for fields used by LLMs (Graphiti/OpenAI).

### Working with Graphiti Nodes
**Rule**: Always use PipGraph wrapper classes, never import from `graphiti_core.nodes` directly.
*   ✅ **Good**: `from app.models.nodes import PipGraphEpisodicNode`
*   ❌ **Avoid**: `from graphiti_core.nodes import EpisodicNode` (in Service/API layers)
*   **Pattern**: API schemas → Service maps → PipGraph wrappers → Graphiti save()
*   **Example**:
    ```python
    # API: Simple schema
    class CreateEpisodeRequest(BaseModel):
        name: str
        content: str

    # Service: Map to wrapper
    episode = PipGraphEpisodicNode(
        name=request.name,
        content=request.content,
        obsidian_path=...,  # PipGraph-specific field
    )
    await episode.save(driver)  # Uses Graphiti's save()
    ```

### Logging
**Rule**: Use structured logging. Never use `print()`.
```python
import logging
logger = logging.getLogger(__name__)

# Usage
logger.info(f"[function_name] Action details: {variable}")
```

## 2. Configuration (`config/settings.py`)

We use `pydantic-settings` to manage environment variables.
*   **Access**: `from config.settings import settings`
*   **Key Variables**:
    *   `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`
    *   `OPENROUTER_API_KEY` (or `CLOUDRU_API_KEY`)
    *   `LOG_LEVEL` (Default: INFO)

## 3. Testing Strategy

Run tests using `pytest` from the `backend/` root.

### Test Categories (Markers)
1.  **Unit Tests** (`@pytest.mark.unit`)
    *   **Location**: `tests/unit/`
    *   **Scope**: Logic isolation, Pydantic validation, State transitions.
    *   **Speed**: Fast (<1s). **No DB**, **No LLM**.

2.  **Integration Tests** (`@pytest.mark.integration`)
    *   **Location**: `tests/integration/`
    *   **Scope**: Real Neo4j queries, Real Workflow execution.
    *   **Speed**: Slower. Requires running Neo4j container.

3.  **Slow/LLM Tests** (`@pytest.mark.slow`)
    *   **Scope**: Real calls to OpenRouter/Cloud.ru.
    *   **Usage**: Run manually only when validating prompt changes.

### Running Tests
```bash
# Run fast tests only (CI/CD standard)
pytest -m "not slow and not integration"

# Run integration tests (Requires Neo4j)
pytest -m integration

# Run everything including LLM calls (Costly!)
pytest --run-slow
```

## 4. Special Project Mechanisms

### Graphiti Node Wrappers
**Why**: Protects from Graphiti API changes and adds PipGraph-specific fields.
**Files**: `app/models/nodes.py` — `PipGraphEpisodicNode`, `PipGraphEntityNode`.
**Usage**: Service layer creates wrappers, calls `.save()`. CRUD layer never touches Graphiti directly.

### Mock-First Switching
To avoid LLM costs during development, we switch between Real and Mock implementations in `app/services/para/__init__.py`.
*   **Mechanism**: Comment/Uncomment imports.
*   **Instruction**: When developing logic flow, ensure Mocks are active. When testing prompts, switch to Real.

### Cloud.ru / Qwen Patch
**File**: `app/services/graphiti/patched_client.py`
**Why**: Qwen models often return the JSON schema *inside* the response body, breaking Pydantic validation.
**Fix**: `CloudRuPatchedClient` injects a specific prompt instruction ("return data only, not the schema") to force correct JSON output.
**Usage**: Automatically used by `get_graphiti()` in `setup_graphiti.py`.

### Neo4j Schema Management
**File**: `app/db/schema.py`
**Usage**: Run this script directly (`python -m app.db.schema`) to apply constraints and indexes (e.g., `suggestion_id` index, unique constraints). The app also attempts to apply these on startup.
