# CLAUDE.md - Backend

Quick reference guide for Claude Code when working with the PipGraph backend.

> **Detailed documentation**: See [docs/](docs/) directory for comprehensive guides.

## Quick Start

```bash
cd backend/
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
uvicorn app.api.main:app --reload
```

Server runs at `http://localhost:8000`

## Project Structure

```
app/
├── api/              # FastAPI endpoints, WebSocket handlers
├── services/         # Business logic, LLM orchestration
│   ├── pipgraph_manager.py   # 7-stage note processing wrapper over Graphiti
│   ├── cloudru_patched_client.py  # Cloud.ru/Qwen LLM client
│   └── note_processor.py     # Note processing service
├── crud/             # Database operations (Neo4j)
└── models/           # Pydantic data models
```

**Layered architecture**: API → Services → CRUD → Database

## Configuration

Uses `pydantic-settings` with `.env` file:

```bash
# Required variables
OPENROUTER_API_KEY=sk-or-v1-...
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
```

Import in code:
```python
from config.settings import settings
```

📖 Full guide: [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

## Key Patterns

### WebSocket Handler

```python
@router.websocket("/ws/notes/process")
async def process_note(websocket: WebSocket):
    await websocket.accept()
    data = await websocket.receive_json()
    payload = NotePayload(**data)  # Validate

    await websocket.send_json({"status": "processing"})
    result = await note_processor.process_and_store_note(payload)
    await websocket.send_json({"status": "done", "data": result.dict()})
```

### Service Layer - PipGraphManager

The `PipGraphManager` wraps Graphiti and exposes 7 processing stages with intervention points:

```python
from app.services.pipgraph_manager import PipGraphManager

async def process_and_store_note(note: NotePayload) -> GraphData:
    """Process note using PipGraphManager for step-by-step control."""
    manager = PipGraphManager(graphiti_instance)

    # Process note with full control over each stage
    result = await manager.process_note(
        name=note.file_path,
        content=note.content,
        reference_time=datetime.now(timezone.utc)
    )

    # Result contains entities and edges extracted
    logger.info(f"Extracted {result['entity_count']} entities, "
                f"{result['edge_count']} edges")

    return result
```

**7 Processing Stages** (from `docs/attend/pipgraph_manager_discussion.md`):
1. Input validation
2. Fact extraction (LLM)
3. Entity resolution
4. Relationship extraction
5. Duplicate detection
6. Graph updates (Neo4j)
7. Result formatting

### CRUD Layer

```python
async def save_graph_data(graph_data: GraphData) -> bool:
    async with driver.session() as session:
        for node in graph_data.nodes:
            await session.run("MERGE (n:Node {id: $id}) ...", ...)
    return True
```

## Testing

```bash
# Install test dependencies
uv pip install -r requirements-dev.txt

# Run tests by type
pytest -m unit           # Fast, no external dependencies
pytest -m integration    # Requires Neo4j, OpenRouter
pytest -m "not slow"     # Exclude expensive LLM calls

# Specific test with output
pytest tests/integration/test_openrouter.py::test_openrouter_llm_connection -sv
```

📖 Full guide: [docs/TESTING.md](docs/TESTING.md)

## API Endpoints

### WebSocket
- `ws://localhost:8000/api/v1/ws/notes/process` - Note processing

### REST
- `GET /` - Health check

### Planned
- `POST /api/v1/search` - Natural language search
- `GET /api/v1/suggestions/{note_id}` - Entity suggestions

## Common Tasks

### Add new endpoint

1. Create route in `app/api/endpoints/`
2. Define Pydantic models in `app/models/`
3. Implement logic in `app/services/`
4. Add tests in `tests/integration/`

### Add database operation

1. Define method in `app/crud/graph_crud.py`
2. Write Cypher query
3. Call from service layer
4. Test with `@pytest.mark.integration`

### Debug WebSocket

```bash
# Test with websocat
echo '{"file_path": "test.md", "content": "Test"}' | \
websocat ws://127.0.0.1:8000/api/v1/ws/notes/process
```

## Technology Stack

- **Framework**: FastAPI (async, WebSocket support)
- **Database**: Neo4j (graph database)
- **LLM Integration**:
  - Graphiti (entity extraction framework)
  - OpenRouter (main, small, embedding models)
  - CloudRuPatchedClient (Cloud.ru/Qwen compatibility)
- **Validation**: Pydantic + pydantic-settings
- **Testing**: pytest with markers (unit/integration/e2e)
- **Package Manager**: uv

## Important Notes

- **PipGraphManager Design**:
  - Copied `add_episode` logic from graphiti_core for controlled modifications
  - Enables gradual customization without modifying library code
  - Documents modification points for future enhancements
  - Based on architectural design from `docs/attend/pipgraph_manager_discussion.md`

- **Duplicate Note Detection** (High Priority TODO):
  - SHA-256 content hash verification planned
  - Scenario 1: Skip processing if content unchanged (cost optimization)
  - Scenario 2: Handle modified note re-processing (design needed)
  - Requires `find_episode_by_name()` implementation

- **CloudRuPatchedClient**:
  - Fixes JSON schema duplication in Cloud.ru/Qwen responses
  - Single-line modification: "return data only, not the schema"
  - Full compatibility with OpenAIGenericClient

- **WebSocket flow**:
  1. Client connects
  2. Server sends immediate "processing" acknowledgment
  3. Server processes via PipGraphManager (7 stages)
  4. Server sends extracted entities to client
  5. Optional: Multiple feedback rounds with client
  6. Server sends "done" with frontmatter update data
  7. Client updates note frontmatter

- **Layer responsibilities**:
  - API: Validation, transport
  - Services: Business logic (PipGraphManager orchestrates)
  - CRUD: Database only

## Documentation

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - Design decisions, patterns
- [CONFIGURATION.md](docs/CONFIGURATION.md) - Environment setup
- [TESTING.md](docs/TESTING.md) - Test strategy, fixtures
- [TODO.md](TODO.md) - Planned features
- [CHANGELOG.md](CHANGELOG.md) - Version history

## Root Documentation

- [Root CLAUDE.md](../CLAUDE.md) - Monorepo overview
- [Root README.md](../README.md) - Full architecture (Russian)

## Documentation Maintenance (for Claude Code)

### Automatic Documentation Updates

Claude should update documentation at these specific moments:

#### Update CHANGELOG.md when:

- ✅ New endpoint added to `app/api/endpoints/`
- ✅ New service created in `app/services/`
- ✅ New CRUD operation in `app/crud/`
- ✅ Integration added (LLM, database driver, external API)
- ✅ Bug fix that affects user behavior
- ✅ Dependency version updated (major/minor)
- ❌ **Skip**: Refactoring, renaming, typos, comment changes

**Format**: Add to `[Unreleased]` section under:
- `### Added` - New features
- `### Changed` - Changes in existing functionality
- `### Fixed` - Bug fixes

#### Update TODO.md when:

- ✅ Task from TODO completed → move to Completed ✓ section
- ✅ New technical debt identified during implementation
- ✅ Feature request discovered during work
- ✅ Research task needs to be tracked
- ❌ **Skip**: Trivial tasks, temporary experiments

**Ask user**: "Mark '[task name]' as completed in TODO?"

#### Update docs/ARCHITECTURE.md when:

- ✅ New layer added to architecture
- ✅ New design pattern introduced
- ✅ Technology choice changed (database, LLM provider)
- ✅ Significant architectural decision made
- ❌ **Skip**: Minor code organization changes

#### Update docs/CONFIGURATION.md when:

- ✅ New environment variable added to `config/settings.py`
- ✅ Configuration method changed
- ✅ New service requires credentials
- ✅ New deployment configuration needed

#### Update docs/TESTING.md when:

- ✅ New test fixture added to `conftest.py`
- ✅ New pytest marker introduced
- ✅ New testing pattern established
- ✅ Test infrastructure changed

### Update Protocol

**1. Detect significant change**

Examples of changes that trigger updates:

```python
# ✅ New file created: app/api/endpoints/search.py
# → Update CHANGELOG: "Added natural language search endpoint"

# ✅ New environment variable in config/settings.py:
# SEARCH_INDEX_NAME: str
# → Update CONFIGURATION.md

# ❌ Renamed variable in existing function
# → Skip documentation update
```

**2. Ask user for confirmation**

Before updating, ask explicitly:

```
"I've added a new search endpoint at POST /api/v1/search.
Should I update CHANGELOG.md with this feature? (y/n)"
```

**3. Batch updates at natural breakpoints**

Don't update after every file change. Instead, batch at:
- End of feature implementation
- Before git commit/PR
- User explicitly requests: "update docs"
- Session completion

Example prompt:
```
"During this session I've:
- Added search endpoint (POST /api/v1/search)
- Created SearchService in app/services/
- Added integration tests in tests/integration/test_search.py

Update documentation? This would affect:
- CHANGELOG.md (Added section)
- TODO.md (mark 'Natural language search' as completed)
(y/n)"
```

**4. Never update silently**

Always inform user:
```
"✓ Updated CHANGELOG.md: Added natural language search endpoint
✓ Updated TODO.md: Marked search task as completed"
```

### Examples

**Good trigger** ✅:
```
User: "Add a health check endpoint"
Agent: [creates app/api/endpoints/health.py with GET /health]
Agent: "Added health check endpoint. Update CHANGELOG? (y/n)"
User: "y"
Agent: [Updates CHANGELOG.md under ### Added]
```

**Bad trigger** ❌:
```
Agent: [Refactors process_note function to use helper methods]
Agent: [Does NOT update CHANGELOG - no user-visible changes]
```

**TODO update** ✅:
```
User: "The search feature is done"
Agent: [Reviews TODO.md, finds "Natural language search endpoint"]
Agent: "Move 'Natural language search endpoint' from High Priority to Completed? (y/n)"
User: "y"
Agent: "✓ Updated TODO.md: Task marked as completed"
```

### Quick Reference

**User commands**:
- `"update changelog"` - Review and update CHANGELOG.md
- `"update todo"` - Sync TODO.md with completed work
- `"update docs"` - Review all docs for accuracy
- `"mark task as done"` - Move TODO item to Completed

**When in doubt**:
- If change affects API contract → update CHANGELOG
- If change adds new pattern → consider docs/ update
- If trivial refactor → skip documentation
- **Always ask user before updating**
