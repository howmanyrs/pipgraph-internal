# PipGraph CLI

Terminal frontend for PipGraph backend via WebSocket API.

## Features

- **Interactive Mode** - interactive note input via console
- **Demo Mode** - run pre-built examples for testing
- **File Mode** - process notes from files
- **WebSocket Communication** - async communication with backend
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

#### 1. Demo Mode (default)

Run 3 pre-built examples for testing:

```bash
pipgraph
# or explicitly
pipgraph --demo
```

#### 2. Interactive Mode

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

#### 3. File Mode

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

CLI communicates with backend via WebSocket:

### Endpoint

```
ws://localhost:8000/api/v1/ws/notes/process
```

### Request Format

```json
{
  "file_path": "notes/example.md",
  "content": "# Example Note\n\nSome content here"
}
```

### Response Formats

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

- [ ] Add search command for graph queries
- [ ] Implement batch file processing
- [ ] Add configuration via file (.pipgraph.yaml)
- [ ] Support progress bar for long-running operations
- [ ] Export results in various formats (JSON, Markdown)
