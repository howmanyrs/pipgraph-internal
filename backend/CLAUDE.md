# CLAUDE.md - Backend

This file provides guidance to Claude Code (claude.ai/code) when working with the PipGraph backend.

## Backend Architecture

The backend follows a strict layered architecture pattern:

```
app/
├── api/                    # API Layer - FastAPI endpoints, WebSocket handlers
│   ├── endpoints/         # Endpoint modules (notes.py)
│   └── main.py           # FastAPI app configuration
├── services/             # Service Layer - Business logic
│   └── note_processor.py # Core note processing logic
├── crud/                 # Data Access Layer - Database operations
│   └── graph_crud.py     # Graph database operations
└── models/               # Data Models - Pydantic schemas
    ├── note.py          # Note input models
    └── graph.py         # Graph data models
```

## Development Setup

### Configuration and Environment Variables

The project uses **pydantic-settings** for configuration management via environment variables and `.env` files. Configuration is defined in `config/settings.py`.

#### Required Environment Variables

```bash
# OpenAI API for LLM processing
OPENAI_API_KEY=your_openai_api_key_here

# Neo4j database connection
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
```

#### Configuration Methods

**Option 1: .env file (recommended for development)**
```bash
cd backend/
cat > .env << 'EOF'
OPENAI_API_KEY=your_openai_api_key_here
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
EOF
```

**Option 2: System environment variables**
```bash
export OPENAI_API_KEY="your_openai_api_key_here"
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your_neo4j_password"
```

**Option 3: Pass during startup**
```bash
OPENAI_API_KEY=your_key NEO4J_URI=bolt://localhost:7687 \
NEO4J_USER=neo4j NEO4J_PASSWORD=your_password \
uvicorn app.api.main:app --reload
```

#### Using Settings in Code

Import the ready-to-use settings instance:

```python
from config.settings import settings

# Usage in code
openai_key = settings.OPENAI_API_KEY
neo4j_uri = settings.NEO4J_URI
```

### Environment Creation with uv
```bash
cd backend/
uv venv                         # Create virtual environment
source .venv/bin/activate       # Activate (Linux/macOS)
uv pip install -r requirements.txt  # Install dependencies
```

### Required Dependencies
```
fastapi
uvicorn[standard]  # Includes WebSocket support
pydantic
pydantic-settings   # For configuration management
```

### Development Server
```bash
uvicorn app.api.main:app --reload  # Start with auto-reload
# Server available at: http://localhost:8000
# WebSocket endpoint: ws://localhost:8000/api/v1/ws/notes/process
```

## Code Structure Patterns

### Pydantic Models (`app/models/`)

**Note Input Model**:
```python
class NotePayload(BaseModel):
    file_path: str
    content: str
```

**Graph Data Models**:
```python
class Node(BaseModel):
    id: str
    label: str
    properties: Dict[str, Any]

class Relationship(BaseModel):
    source_id: str
    target_id: str
    type: str
    properties: Dict[str, Any] = Field(default_factory=dict)

class GraphData(BaseModel):
    nodes: List[Node]
    relationships: List[Relationship]
```

### WebSocket Handler Pattern (`app/api/endpoints/notes.py`)

Key WebSocket flow:
1. Accept connection: `await websocket.accept()`
2. Validate input with Pydantic: `NotePayload(**data)`
3. Send immediate acknowledgment: `{"status": "processing", "message": "..."}`
4. Process note through service layer
5. Send final result: `{"status": "done", "data": graph_data.dict()}`
6. Handle errors: `{"status": "error", "message": "..."}`

### Service Layer Pattern (`app/services/note_processor.py`)

Main processing function:
```python
def process_and_store_note(note: NotePayload) -> GraphData:
    # 1. LLM processing (extract entities)
    # 2. Call CRUD layer to save data
    # 3. Return processed graph data
```

### CRUD Layer Pattern (`app/crud/graph_crud.py`)

Database operations:
```python
def save_graph_data(graph_data: GraphData) -> bool:
    # Neo4j Cypher queries
    # Return success/failure status
```

## Testing


### WebSocket Testing with websocat
```bash
# Install websocat (if needed): brew install websocat

# Test note processing
echo '{"file_path": "test/note.md", "content": "Test content"}' | \
websocat ws://127.0.0.1:8000/api/v1/ws/notes/process
```

Expected responses:
1. Immediate: `{"status":"processing","message":"Note 'test/note.md' received..."}`
2. Final: `{"status":"done","data":{"nodes":[...],"relationships":[...]}}`

### API Health Check
```bash
curl http://localhost:8000/
# Expected: {"status": "PipGraph Backend is running"}
```

## Development Guidelines

### Layer Responsibilities
- **API Layer**: Request validation, WebSocket management, response formatting
- **Service Layer**: Business logic, LLM orchestration, data transformation
- **CRUD Layer**: Database queries, data persistence, Cypher operations

### Code Organization
- Use Pydantic models for all data validation and serialization
- Keep database-specific code (Cypher queries) in CRUD layer only
- Service layer should be database-agnostic
- Handle WebSocket connections with proper error handling and cleanup

### Future Integration Points
- LLM service integration in `app/services/note_processor.py`
- Neo4j connection and Cypher queries in `app/crud/graph_crud.py`
- Additional REST endpoints for search and suggestions
- Background task processing for long-running operations

## API Endpoints

### WebSocket
- `ws://localhost:8000/api/v1/ws/notes/process` - Note processing with async feedback

### REST (Current)
- `GET /` - Health check

### REST (Planned)
- `POST /api/v1/search` - Natural language search
- `GET /api/v1/suggestions/{note_id}` - Entity suggestions