# CLAUDE.md

Guidance for Claude Code when working with the PipGraph monorepo.

## Project Overview

PipGraph is an Obsidian plugin with a Python backend that processes notes using LLM and stores extracted entities in a graph database.

**Architecture**: Frontend-backend separation with REST API communication.

## Monorepo Structure

```
pipgraph/
├── backend/              # Python FastAPI backend
│   ├── app/             # Source code (API/Services/CRUD)
│   ├── tests/           # Test suite (unit/integration/e2e)
│   ├── docs/            # Detailed documentation
│   ├── CLAUDE.md        # Backend quick reference
│   ├── README.md        # Backend developer guide
│   ├── TODO.md          # Task tracking
│   └── CHANGELOG.md     # Version history
├── obsidian-plugin/     # TypeScript Obsidian plugin
├── web-prototype/       # Web UI for development
└── README.md           # Full architecture (Russian)
```

## Quick Start

### Backend Development

```bash
cd backend/
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
uvicorn app.api.main:app --reload
```

📖 **Detailed guide**: [backend/CLAUDE.md](backend/CLAUDE.md)

## Technology Stack

- **Backend**: Python 3.12+, FastAPI, Neo4j, Graphiti, LangGraph
- **Frontend**: TypeScript, Svelte/React
- **Database**: Neo4j graph database
- **Package Manager**: `uv` (Python)
- **Communication**: REST API

## Backend Architecture

**Layered design**: API → Services/Workflows → CRUD → Database

- **API Layer**: REST endpoints, Pydantic validation
- **Workflow Layer**: LangGraph state machine with interrupt/resume
- **Service Layer**: Business logic, LLM orchestration
- **CRUD Layer**: Neo4j operations, Cypher queries


## Workflow System (PARA)

The backend implements a LangGraph-based workflow for PARA (Projects/Areas/Resources/Archive) classification:

### Key Components

- **Mock Services** (`app/services/mocks/`) - Deterministic mocks for testing without LLM
- **Proposal Manager** (`app/services/proposal_manager.py`) - Generates PARA suggestions
- **Cascade Service** (`app/services/cascade_service.py`) - Auto-resolves similar suggestions
- **LangGraph Workflow** (`app/workflows/para_workflow.py`) - State machine with interrupt/resume

### REST API Endpoints

```bash
# Workflow management
POST /api/v1/workflow/start          # Start new workflow
GET  /api/v1/workflow/{id}/status    # Get status
POST /api/v1/workflow/{id}/resume    # Resume with answer

# Suggestions
GET  /api/v1/workflow/{id}/suggestions  # Get pending suggestions
POST /api/v1/suggestion/{id}/decision   # Submit decision

# Inbox
GET  /api/v1/inbox/suggestions       # All pending suggestions
GET  /api/v1/inbox/count             # Count
```

### Cascade Feature

When user confirms a suggestion, the system automatically resolves similar suggestions:
- Threshold-based: confidence > 0.85 auto-resolves
- Uses Neo4j as source of truth for relationships
- Returns list of auto-resolved items in response

### Mock Implementation

For development/testing, mocks replace LLM calls:
- `mock_classifier.py` - L1 PARA type classification
- `mock_proposal_generator.py` - L2 proposal generation
- `mock_graphiti.py` - L3 entity extraction
- `mock_cascade.py` - Cascade candidate finding

Switch between mock/real via imports in `app/services/para/__init__.py`.

## Configuration

Backend uses `pydantic-settings` with `.env` file:

```bash
# backend/.env
OPENROUTER_API_KEY=sk-or-v1-...
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
```

See [backend/docs/CONFIGURATION.md](backend/docs/CONFIGURATION.md) for full guide.

## Testing

```bash
cd backend/
pytest -m unit           # Fast unit tests
pytest -m integration    # Requires Neo4j, OpenRouter
pytest -m "not slow"     # Exclude expensive LLM calls
```

See [backend/docs/TESTING.md](backend/docs/TESTING.md) for comprehensive guide.

## Documentation Structure

### Backend Documentation
- **[backend/CLAUDE.md](backend/CLAUDE.md)** - Quick reference for Claude Code
- **[backend/README.md](backend/README.md)** - Developer guide (Russian)
- **[backend/TODO.md](backend/TODO.md)** - Task tracking and roadmap
- **[backend/CHANGELOG.md](backend/CHANGELOG.md)** - Version history

### Backend Deep Dive (docs/)

- **[CONFIGURATION.md](backend/docs/CONFIGURATION.md)** - Environment setup
- **[TESTING.md](backend/docs/TESTING.md)** - Test strategy, fixtures

### Root Documentation
- **[README.md](README.md)** - Full architecture overview (Russian)

## Key Principles

- **REST API**: Stateless endpoints with interrupt/resume workflow
- **Type safety**: Pydantic models everywhere
- **Separation of concerns**: Strict layer boundaries
- **Test coverage**: Unit, integration, and e2e tests
- **Clear documentation**: CLAUDE.md for AI, README for humans

## Documentation Maintenance (for Claude Code)

### When to Update Documentation

**CHANGELOG.md** - Update when:
- ✅ New feature added (endpoint, service, integration)
- ✅ Significant bug fixed
- ✅ Architecture changed (new layer/pattern)
- ✅ Dependencies updated (major/minor versions)
- ✅ API contract changed (breaking change)
- ❌ **Skip**: refactoring without behavior change, typos, comments

**TODO.md** - Update when:
- ✅ Task completed → move to Completed section
- ✅ New technical debt discovered during work
- ✅ Feature request deferred for future
- ✅ Priorities changed based on learnings
- ❌ **Skip**: exploratory research, code reading

**docs/ files** - Update when:
- ✅ New environment variable added → CONFIGURATION.md
- ✅ New test fixture or pattern → TESTING.md
- ❌ **Skip**: minor code tweaks, small refactors

### Update Triggers

When to actually update documentation:

1. **User explicitly requests**:
   - "update changelog"
   - "update docs"
   - "mark task as done"

2. **Before PR/commit creation**:
   - Review all docs before git operations
   - Batch all session changes together

3. **Feature completion**:
   - When marking TODO item as done
   - When closing a significant work session

4. **Session end**:
   - Ask: "Update documentation with session changes?"
   - List what would be updated

### Update Strategy

**Batch updates**: Collect changes during session, update once at natural breakpoints.

**Always ask before updating**:
```
"I've made these changes:
- Added search endpoint
- Created SearchService
- Fixed Neo4j connection bug

Update CHANGELOG.md and TODO.md? (y/n)"
```

**Never update docs silently**: Always inform user what was updated and why.

**Format for updates**:
- CHANGELOG: Add to `[Unreleased]` section under Added/Changed/Fixed
- TODO: Move items between sections, add new items
- docs/: Update relevant sections only