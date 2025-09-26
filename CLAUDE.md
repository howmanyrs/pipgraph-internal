# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PipGraph is an Obsidian plugin with a Python backend that processes notes using LLM and stores extracted entities in a graph database. The project follows a frontend-backend separation architecture with WebSocket-based async communication.

## Architecture

- **Frontend**: Obsidian plugin (TypeScript) + web prototype for UI development
- **Backend**: Python FastAPI server with layered architecture (API/Services/CRUD)
- **Database**: Neo4j graph database for storing extracted entities and relationships
- **Communication**: WebSocket for async note processing, REST API for quick operations
- **Structure**: Monorepo with clear separation of concerns

## Technology Stack

- **Backend**: Python 3.12+, FastAPI, uvicorn, Pydantic
- **Dependency Management**: `uv` for Python virtual environments and packages
- **Frontend**: TypeScript, Svelte/React (for web prototype)
- **Database**: Neo4j (recommended for development)
- **Communication**: WebSockets for async operations, REST for sync operations

## Development Commands

### Backend Setup and Run
```bash
cd backend/
uv venv                          # Create virtual environment
source .venv/bin/activate        # Activate environment (Linux/macOS)
# .\.venv\Scripts\activate       # Activate environment (Windows)
uv pip install -r requirements.txt  # Install dependencies
uvicorn app.api.main:app --reload   # Start development server (localhost:8000)
```

### Testing WebSocket API
```bash
# Test note processing via WebSocket
echo '{"file_path": "test/note.md", "content": "Test content here"}' | \
websocat ws://127.0.0.1:8000/api/v1/ws/notes/process
```

## Project Structure

```
pipgraph/
├── backend/                 # Python FastAPI backend
│   ├── app/
│   │   ├── api/            # FastAPI endpoints and WebSocket handlers
│   │   ├── services/       # Business logic layer
│   │   ├── crud/           # Database access layer
│   │   └── models/         # Pydantic data models
│   └── requirements.txt
├── obsidian-plugin/        # TypeScript Obsidian plugin
├── web-prototype/          # Web UI for development/testing
└── README.md              # Detailed architecture (in Russian)
```

## Key Development Patterns

### WebSocket Note Processing Flow
1. Client establishes WebSocket connection to `/api/v1/ws/notes/process`
2. Client sends note data: `{"file_path": "...", "content": "..."}`
3. Server immediately responds: `{"status": "processing", "message": "..."}`
4. Server processes note (LLM extraction, database storage)
5. Server sends final result: `{"status": "done", "data": {...}}`

### Backend Layered Architecture
- **API Layer** (`app/api/`): WebSocket/HTTP request handling, data validation
- **Service Layer** (`app/services/`): Business logic, LLM integration orchestration
- **CRUD Layer** (`app/crud/`): Database operations, Cypher queries

## Environment Setup Requirements

1. Python 3.12+ installed
2. Node.js 18+ (for frontend components)
3. `uv` package manager: `pip install uv`
4. Neo4j database (local installation recommended)
5. WebSocket testing tool: `websocat` (optional but recommended)

## API Endpoints

- **WebSocket**: `ws://localhost:8000/api/v1/ws/notes/process` - Async note processing
- **REST**: `GET /` - Health check
- Future: `POST /search` - Natural language search, `GET /suggestions/{note_id}` - Entity suggestions

## Development Notes

- Use `uv` for all Python dependency management instead of pip
- Backend designed for independent development with mock/stub implementations
- Web prototype allows UI development without Obsidian integration
- All async operations use WebSocket with immediate acknowledgment pattern
- Project documentation is primarily in Russian but code should use English