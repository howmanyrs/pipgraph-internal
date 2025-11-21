# PipGraph CLI

Terminal frontend for PipGraph backend via WebSocket and REST API.

## Features

- **Workflow Mode** - interactive processing with clarification questions (REST API)
- **Interactive Mode** - interactive note input via console
- **Demo Mode** - run pre-built examples for testing
- **File Mode** - process notes from files
- **WebSocket Communication** - async communication with backend
- **REST API Support** - workflow management and suggestions
- **Rich UI** - beautiful colored output with formatting (optional)

## Installation

### Using uv (recommended)

```bash
cd pipgraph-cli/
uv venv
source .venv/bin/activate  # Linux/macOS
# or .venv\Scripts\activate  # Windows

uv pip install -e .
```

### Using pip

```bash
cd pipgraph-cli/
pip install -r requirements.txt
pip install -e .
```

## Usage

### Start backend

Before using CLI, make sure backend is running:

```bash
cd backend/
uvicorn app.api.main:app --reload
```

Backend will be available at `http://localhost:8000`

### CLI Modes

#### 1. Workflow Mode (recommended)

Interactive workflow with clarification questions via REST API:

```bash
pipgraph --workflow
# or short form
pipgraph -w
```

Features:
- Start workflow and receive suggestions
- Review suggestions with confidence scores
- Make decisions: confirm, dismiss, modify, create_custom
- See cascade auto-resolution results

Example session:

```
Enter file path (or 'quit'): notes/meeting.md
Enter note content (end with empty line):
# Meeting with John Smith
Discussed PipGraph project timeline.

Starting workflow...
Workflow started: wf_a1b2c3d4
Status: waiting_user

Suggestion #1:
  Type: para_link
  Container: PipGraph Project (Project)
  Confidence: 0.92

Available actions:
  confirm - Accept this suggestion
  dismiss - Reject this suggestion
  modify - Change the suggested value
  create_custom - Create a new container

Enter action: confirm
Decision 'confirm' applied successfully!

Cascade auto-resolved 2 similar suggestion(s):
  - meetings/other.md (confidence: 0.88)
  - notes/planning.md (confidence: 0.85)

Workflow completed successfully!
Episode UUID: ep_xyz789
```

#### 2. Demo Mode (default)

Run 3 pre-built examples for testing:

```bash
pipgraph
# or explicitly
pipgraph --demo
```

#### 3. Interactive Mode

Interactive note input via console:

```bash
pipgraph --interactive
# or short form
pipgraph -i
```

Available commands in interactive mode:
- `demo` - run demo examples
- `quit` / `exit` / `q` - exit
- Or enter file path and note content

Example session:

```
Enter file path (or command): notes/test.md
Enter note content (press Ctrl+D or Ctrl+Z when done):
# Test Note
This is a test note with some content.
<Ctrl+D>
```

#### 4. File Mode

Process note from file:

```bash
pipgraph --file path/to/note.md
# or short form
pipgraph -f note.md
```

### Additional Options

#### Specify backend URL

```bash
pipgraph --backend-url ws://localhost:8080
```

#### Disable rich formatting

Use plain text output (useful for scripts):

```bash
pipgraph --no-rich
```

#### Version

```bash
pipgraph --version
```

#### Help

```bash
pipgraph --help
```

## Usage Examples

### Quick test with demo

```bash
# Start backend
cd backend/
uvicorn app.api.main:app --reload

# In another terminal
cd pipgraph-cli/
pipgraph
```

### Process file

```bash
pipgraph -f ../obsidian-vault/notes/meeting.md
```

### Interactive work

```bash
pipgraph -i

# Enter:
notes/test.md
# Test Note
Some content here
<Ctrl+D>

# Or run demo:
demo
```

## Check Results

Processing results are displayed in console as JSON:

```json
{
  "nodes": [...],
  "relationships": [...]
}
```

Data is also saved to Neo4j. Check via Neo4j Browser:
- Open `http://localhost:7474`
- Run query: `MATCH (n) RETURN n LIMIT 25`

## Project Structure

```
pipgraph-cli/
├── pipgraph_cli/
│   ├── __init__.py       # Package metadata
│   ├── main.py           # CLI entry point
│   ├── client.py         # WebSocket client
│   ├── ui.py             # Console UI
│   └── examples.py       # Demo examples
├── pyproject.toml        # uv configuration
├── requirements.txt      # Dependencies
└── README.md            # Documentation
```

## Dependencies

- **websockets** - WebSocket client for async communication
- **rich** - Beautiful console output (optional)
- **httpx** - HTTP client for additional requests

## Development

### Install in development mode

```bash
cd pipgraph-cli/
uv pip install -e .
```

### Run tests

```bash
pytest
```

## API Protocol

CLI communicates with backend via WebSocket and REST API.

### WebSocket API (Demo/Interactive/File modes)

#### Endpoint

```
ws://localhost:8000/api/v1/ws/notes/process
```

#### Request Format

```json
{
  "file_path": "notes/example.md",
  "content": "# Example Note\n\nSome content here"
}
```

#### Response Formats

**Processing (intermediate status)**:
```json
{
  "status": "processing",
  "message": "Note 'notes/example.md' received, starting processing..."
}
```

**Done (successful completion)**:
```json
{
  "status": "done",
  "data": {
    "nodes": [...],
    "relationships": [...]
  }
}
```

**Error**:
```json
{
  "status": "error",
  "message": "Error description"
}
```

### REST API (Workflow mode)

#### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/workflow/start` | Start new workflow |
| GET | `/api/v1/workflow/{id}/status` | Get workflow status |
| POST | `/api/v1/workflow/{id}/resume` | Resume with answer |
| GET | `/api/v1/workflow/{id}/suggestions` | Get suggestions |
| POST | `/api/v1/suggestion/{id}/decision` | Submit decision |
| GET | `/api/v1/inbox/suggestions` | Get all pending |

#### Start Workflow

```bash
curl -X POST http://localhost:8000/api/v1/workflow/start \
  -H "Content-Type: application/json" \
  -d '{"file_path": "notes/test.md", "content": "# Test"}'
```

Response:
```json
{
  "workflow_id": "wf_a1b2c3d4",
  "status": "waiting_user",
  "file_path": "notes/test.md"
}
```

#### Get Suggestions

```bash
curl http://localhost:8000/api/v1/workflow/wf_a1b2c3d4/suggestions
```

Response:
```json
{
  "workflow_id": "wf_a1b2c3d4",
  "suggestions": [
    {
      "suggestion_id": "q_123",
      "suggestion_type": "para_link",
      "container_type": "Project",
      "container_name": "Project Alpha",
      "confidence": 0.92,
      "alternatives": []
    }
  ]
}
```

#### Submit Decision

```bash
curl -X POST http://localhost:8000/api/v1/suggestion/q_123/decision \
  -H "Content-Type: application/json" \
  -d '{"action": "confirm"}'
```

Response:
```json
{
  "success": true,
  "workflow_id": "wf_a1b2c3d4",
  "suggestion_id": "q_123",
  "action": "confirm",
  "cascade_applied": [
    {"suggestion_id": "q_456", "note_path": "other.md", "confidence": 0.88}
  ]
}
```

## Troubleshooting

### Cannot connect to backend

Error:
```
✗ Error: Cannot connect to backend at ws://localhost:8000/api/v1/ws/notes/process
```

Solution:
1. Check that backend is running: `uvicorn app.api.main:app --reload`
2. Make sure port 8000 is not occupied
3. Check firewall/antivirus

### Timeout waiting for response

Error:
```
✗ Error: Timeout waiting for backend response (5 min)
```

Solution:
1. Check backend logs for errors
2. Make sure environment variables are configured:
   - `OPENROUTER_API_KEY`
   - `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`
3. Check Neo4j connection

### Rich library not available

CLI automatically falls back to plain text output if `rich` is not installed.

To install:
```bash
pip install rich
```

## Relation to Backend

PipGraph CLI is a terminal client for [PipGraph Backend](../backend/README.md).

Backend provides:
- WebSocket API for note processing
- LLM integration (via Graphiti + OpenRouter)
- Graph storage in Neo4j

See [backend/CLAUDE.md](../backend/CLAUDE.md) for details.

## License

MIT

## TODO

- [x] Workflow mode with clarification questions (REST API)
- [x] Cascade auto-resolution display
- [ ] Add search command for graph queries
- [ ] Implement batch file processing
- [ ] Add configuration via file (.pipgraph.yaml)
- [ ] Support progress bar for long-running operations
- [ ] Export results in various formats (JSON, Markdown)
