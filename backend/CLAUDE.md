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
├── api/              # FastAPI REST endpoints
│   └── endpoints/    # workflow.py, suggestions.py
├── services/         # Business logic, LLM orchestration
│   ├── pipgraph_manager.py     # Note processing with Graphiti
│   ├── proposal_manager.py     # Apply PARA proposals to Neo4j
│   ├── cascade_service.py      # Auto-resolve similar suggestions
│   └── mocks/                  # Mock services for testing
├── workflows/        # LangGraph PARA workflow
│   ├── para_workflow.py        # State machine (6 nodes)
│   ├── langgraph_service.py    # Graph assembly & execution
│   ├── state.py                # PARAWorkflowState
│   └── conditions.py           # Transition conditions
├── crud/             # Database operations (Neo4j)
│   ├── relationship_crud.py    # Suggestions, links
│   ├── entity_crud.py          # Entities
│   └── para_crud.py            # PARA containers
└── models/           # Pydantic data models
```

**Layered architecture**: API → Services/Workflows → CRUD → Database

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

### REST API Endpoints

```python
# app/api/endpoints/workflow.py
@router.post("/workflow/start")
async def start_workflow(request: WorkflowCreateRequest):
    result = await langgraph_service.start_workflow(
        request.file_path, request.content
    )
    return WorkflowStatusResponse(**result)

@router.post("/workflow/{workflow_id}/resume")
async def resume_workflow(workflow_id: str, request: WorkflowResumeRequest):
    result = await langgraph_service.resume_workflow(workflow_id, request.answer)
    return WorkflowResumeResponse(**result)
```

### LangGraph Workflow

```python
from app.workflows.langgraph_service import start_workflow, resume_workflow

# Start new PARA classification workflow
result = await start_workflow(file_path="note.md", content="...")
# Returns: {workflow_id, status, pending_question}

# Resume with user decision
result = await resume_workflow(workflow_id, answer={"action": "confirm"})
# Returns: {status, cascade_applied, next_question}
```

**6 Workflow Nodes**:
1. `identify_context` - L1 PARA classification, L2 proposal generation
2. `apply_proposal` - Create :SUGGESTS relationships in Neo4j
3. `wait_for_decision` - INTERRUPT for user input
4. `process_decision` - Handle user action, cascade resolution
5. `extract_content` - L3 entity extraction (PipGraphManager)
6. `save_entities` - Save to Neo4j

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

### Workflow Management
- `POST /api/v1/workflow/start` - Start new PARA workflow
- `GET /api/v1/workflow/{id}/status` - Get workflow status
- `POST /api/v1/workflow/{id}/resume` - Resume with user answer

### Suggestions
- `GET /api/v1/workflow/{id}/suggestions` - Get pending suggestions
- `POST /api/v1/suggestion/{id}/decision` - Submit decision

### Inbox
- `GET /api/v1/inbox/suggestions` - All pending suggestions
- `GET /api/v1/inbox/count` - Count of pending

### Health
- `GET /` - Health check

## Common Tasks

### Add new endpoint

1. Create route in `app/api/endpoints/`
2. Define Pydantic models in `app/models/`
3. Implement logic in `app/services/`
4. Add tests in `tests/integration/`

### Add database operation

1. Define method in appropriate CRUD file (`relationship_crud.py`, `entity_crud.py`, etc.)
2. Write Cypher query
3. Call from service layer
4. Test with `@pytest.mark.integration`

### Debug REST API

```bash
# Test workflow start
curl -X POST http://127.0.0.1:8000/api/v1/workflow/start \
  -H "Content-Type: application/json" \
  -d '{"file_path": "test.md", "content": "Test"}'

# Get workflow status
curl http://127.0.0.1:8000/api/v1/workflow/{workflow_id}/status
```

## Technology Stack

- **Framework**: FastAPI (async REST API)
- **Workflow**: LangGraph (state machine with interrupt/resume)
- **Database**: Neo4j (graph database)
- **LLM Integration**:
  - Graphiti (entity extraction framework)
  - OpenRouter (main, small, embedding models)
- **Validation**: Pydantic + pydantic-settings
- **Testing**: pytest with markers (unit/integration/e2e)
- **Package Manager**: uv

## Important Notes

- **LangGraph PARA Workflow**:
  - State machine with interrupt/resume support
  - 6 nodes: identify_context → apply_proposal → wait_for_decision → process_decision → extract_content → save_entities
  - Cascade auto-resolution for similar suggestions
  - Mock services in `mocks/` for testing without LLM

- **Cascade Service**:
  - Threshold-based: confidence > 0.85 auto-resolves
  - Uses Neo4j as source of truth
  - Returns list of auto-resolved items in response

- **REST API Flow**:
  1. Client POSTs to `/workflow/start`
  2. Server returns `workflow_id` and `pending_question`
  3. Client POSTs decision to `/workflow/{id}/resume`
  4. Server processes, may return more questions or complete
  5. Client can query `/inbox/suggestions` for all pending items

- **Layer responsibilities**:
  - API: Validation, transport (REST)
  - Workflows: LangGraph state machine orchestration
  - Services: Business logic (PipGraphManager, CascadeService)
  - CRUD: Database only (Neo4j)

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
