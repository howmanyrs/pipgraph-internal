# CLAUDE.md - PipGraph CLI

Quick reference guide for Claude Code when working with the PipGraph CLI terminal frontend.

> **For users**: See [README.md](README.md) for full documentation and [QUICKSTART.md](QUICKSTART.md) for getting started.

## Quick Start

```bash
cd pipgraph-cli/
uv venv && source .venv/bin/activate
uv pip install -e .

# Run CLI (make sure backend is running first)
pipgraph -w           # Workflow mode (recommended)
pipgraph              # Demo examples
pipgraph -i           # Interactive mode
pipgraph -f note.md   # Process file
```

## Project Structure

```
pipgraph-cli/
├── pipgraph_cli/
│   ├── __init__.py       # Package metadata, version
│   ├── main.py           # CLI entry point (argparse, async main)
│   ├── client.py         # WebSocket client for backend API
│   ├── ui.py             # Console UI (rich formatting)
│   └── examples.py       # Demo note examples
├── pyproject.toml        # uv config, entry points
├── requirements.txt      # Dependencies
├── README.md            # Full documentation
├── QUICKSTART.md        # Quick start guide
└── CLAUDE.md           # This file
```

## Architecture

**Layered design**: CLI → Client → Backend WebSocket/REST API

- **main.py**: Argument parsing, mode selection, orchestration
- **client.py**: WebSocket and REST API communication
- **ui.py**: Terminal formatting, user interaction
- **examples.py**: Demo data for testing

## Key Components

### 1. CLI Entry Point (main.py)

Entry point defined in `pyproject.toml`:

```toml
[project.scripts]
pipgraph = "pipgraph_cli.main:main"
```

Main function structure:

```python
def main():
    """Entry point called by pipgraph command."""
    asyncio.run(async_main())

async def async_main():
    """Parse args, check backend, run appropriate mode."""
    parser = argparse.ArgumentParser(...)
    args = parser.parse_args()

    # Check backend availability first
    if not await check_backend(args.backend_url):
        sys.exit(1)

    # Run mode based on args
    if args.workflow:
        await workflow_mode(backend_url)  # REST API mode
    elif args.interactive:
        await interactive_mode(backend_url)
    elif args.demo:
        await run_demo_examples(backend_url)
    elif args.file:
        await test_from_file(backend_url, args.file)
```

### 2. WebSocket Client (client.py)

Handles all backend communication:

```python
class PipGraphClient:
    def __init__(self, backend_url: str = "ws://localhost:8000"):
        self.ws_endpoint = f"{backend_url}/api/v1/ws/notes/process"

    async def process_note(
        self,
        note: NotePayload,
        on_status: Callable,  # Status updates
        on_error: Callable    # Error handling
    ) -> Optional[dict]:
        """Send note, receive status updates, return result."""
        async with websockets.connect(self.ws_endpoint) as ws:
            await ws.send(json.dumps(note.to_dict()))

            while True:
                response = json.loads(await ws.recv())

                if response["status"] == "processing":
                    on_status("processing", response["message"])
                elif response["status"] == "done":
                    return response["data"]
                elif response["status"] == "error":
                    on_error(response["message"])
                    return None
```

**Protocol** (matches backend API):
- **Send**: `{"file_path": "...", "content": "..."}`
- **Receive**: `{"status": "processing|done|error", "message": "...", "data": {...}}`

### 2b. REST API Client (client.py)

REST methods for workflow management:

```python
class PipGraphClient:
    def __init__(self, backend_url: str = "ws://localhost:8000"):
        self.http_base = backend_url.replace("ws://", "http://")

    async def start_workflow(self, file_path: str, content: str) -> dict:
        """POST /api/v1/workflow/start"""
        ...

    async def get_workflow_status(self, workflow_id: str) -> dict:
        """GET /api/v1/workflow/{id}/status"""
        ...

    async def get_suggestions(self, workflow_id: str) -> dict:
        """GET /api/v1/workflow/{id}/suggestions"""
        ...

    async def submit_decision(
        self,
        suggestion_id: str,
        action: str,
        modified_value: Optional[str] = None,
        custom_container_name: Optional[str] = None
    ) -> dict:
        """POST /api/v1/suggestion/{id}/decision"""
        ...

    async def get_inbox(self) -> dict:
        """GET /api/v1/inbox/suggestions"""
        ...
```

**Actions for submit_decision**:
- `confirm` - Accept suggestion
- `dismiss` - Reject suggestion
- `modify` - Change value (pass `modified_value`)
- `create_custom` - Create new container (pass `custom_container_name`)

### 3. Console UI (ui.py)

Singleton UI manager with rich support:

```python
ui = get_ui()  # Singleton instance

# Usage
ui.print_header("Processing Note")
ui.print_note_info(file_path, content)
ui.print_status("processing", "Extracting entities...")
ui.print_result(result_data)  # JSON with syntax highlighting
ui.print_error("Connection failed")
```

**Features**:
- Automatic fallback to plain text if rich not available
- Colored output, syntax highlighting
- Progress indicators, separators
- User input prompts

### 4. Demo Examples (examples.py)

Pre-built test data:

```python
def get_demo_examples() -> List[Dict[str, str]]:
    return [
        {"file_path": "...", "content": "..."},
        # 3 examples: person, project, meeting
    ]
```

## CLI Modes

### Workflow Mode (Recommended)

```bash
pipgraph --workflow
pipgraph -w
```

Interactive workflow with REST API:
1. Prompt for file path and content
2. Start workflow via POST /workflow/start
3. Check status via GET /workflow/{id}/status
4. If waiting_user, get suggestions via GET /workflow/{id}/suggestions
5. Display suggestions with confidence scores
6. Prompt for decision (confirm/dismiss/modify/create_custom)
7. Submit decision via POST /suggestion/{id}/decision
8. Display cascade results
9. Repeat until completed

### Demo Mode (Default)

```bash
pipgraph
pipgraph --demo
pipgraph -d
```

Runs 3 pre-built examples sequentially.

### Interactive Mode

```bash
pipgraph --interactive
pipgraph -i
```

Loop:
1. Prompt for file path (or command: `demo`, `quit`, `exit`)
2. Prompt for content (multi-line, Ctrl+D to finish)
3. Send to backend
4. Display results
5. Repeat

### File Mode

```bash
pipgraph --file path/to/note.md
pipgraph -f note.md
```

Read file, process once, exit.

## Configuration

### Backend URL

Default: `ws://localhost:8000`

Override:
```bash
pipgraph --backend-url ws://custom-host:8080
```

### Rich Formatting

Enabled by default if `rich` library available.

Disable for scripts:
```bash
pipgraph --no-rich
```

## Dependencies

- **websockets** (required) - WebSocket client
- **rich** (optional) - Terminal formatting
- **httpx** (optional) - HTTP client for future REST endpoints

Install:
```bash
uv pip install -e .  # Installs all from pyproject.toml
```

## Backend Integration

### WebSocket Endpoint (Demo/Interactive/File modes)

```
ws://localhost:8000/api/v1/ws/notes/process
```

### REST Endpoints (Workflow mode)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/workflow/start` | Start workflow |
| GET | `/api/v1/workflow/{id}/status` | Get status |
| GET | `/api/v1/workflow/{id}/suggestions` | Get suggestions |
| POST | `/api/v1/suggestion/{id}/decision` | Submit decision |
| GET | `/api/v1/inbox/suggestions` | Get all pending |

### WebSocket Protocol Flow

1. **Connect** to WebSocket
2. **Send** note payload: `{"file_path": "...", "content": "..."}`
3. **Receive** processing status: `{"status": "processing", "message": "..."}`
4. **Receive** result: `{"status": "done", "data": {...}}`
5. **Close** connection

### REST Protocol Flow

1. **POST** /workflow/start → get workflow_id
2. **GET** /workflow/{id}/status → check status
3. If `waiting_user`:
   - **GET** /workflow/{id}/suggestions → get suggestions
   - **POST** /suggestion/{id}/decision → submit decision
4. Repeat until `completed`

### Error Handling

- **ConnectionError**: Backend not running or wrong URL
- **TimeoutError**: Processing timeout (5 minutes)
- **ValidationError**: Invalid payload format
- **WebSocketException**: Connection issues

## Common Tasks

### Add New CLI Option

1. **Add argument** in `main.py`:
   ```python
   parser.add_argument('--new-option', type=str, help='...')
   ```

2. **Handle in async_main**:
   ```python
   if args.new_option:
       await handle_new_option(args.new_option)
   ```

### Add New Demo Example

Edit `examples.py`:
```python
def get_demo_examples() -> List[Dict[str, str]]:
    return [
        # existing examples...
        {
            "file_path": "notes/new_example.md",
            "content": "# New Example\n\nContent here"
        }
    ]
```

### Add New UI Element

In `ui.py`:
```python
def print_custom(self, message: str):
    if self.use_rich:
        self.console.print(f"[style]{message}[/style]")
    else:
        print(message)
```

### Change Default Backend URL

Edit `main.py`:
```python
parser.add_argument(
    '--backend-url',
    default='ws://new-default:8000',  # Change here
    help='...'
)
```

## Testing

### Manual Testing

```bash
# 1. Start backend
cd ../backend/
uvicorn app.api.main:app --reload

# 2. Test CLI
cd ../pipgraph-cli/
pipgraph  # Demo mode

# 3. Test file mode
echo "# Test\nContent" > test.md
pipgraph -f test.md

# 4. Test interactive mode
pipgraph -i
# Enter: notes/test.md
# Enter content, press Ctrl+D
```

### Connection Testing

```python
# In Python shell
from pipgraph_cli.client import test_connection
import asyncio

asyncio.run(test_connection("ws://localhost:8000"))
# Returns: True if backend available
```

### Debug Mode

Add verbose logging:
```python
# In main.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Troubleshooting

### Command not found: pipgraph

**Problem**: Entry point not installed

**Solution**:
```bash
cd pipgraph-cli/
uv pip install -e .  # Installs entry point
```

Verify:
```bash
which pipgraph
# Should show: .venv/bin/pipgraph
```

### Cannot connect to backend

**Problem**: Backend not running or wrong URL

**Solution**:
1. Check backend: `curl http://localhost:8000/`
2. Check WebSocket: `websocat ws://localhost:8000/api/v1/ws/notes/process`
3. Try explicit URL: `pipgraph --backend-url ws://localhost:8000`

### Rich not working

**Problem**: Rich library not installed or terminal not compatible

**Solution**:
```bash
# Install rich
pip install rich

# Or use plain text mode
pipgraph --no-rich
```

### Timeout errors

**Problem**: LLM processing takes too long (>5 min)

**Solution**:
- Check backend logs for errors
- Verify OpenRouter API key
- Verify Neo4j connection
- Increase timeout in `client.py`:
  ```python
  response_raw = await asyncio.wait_for(
      websocket.recv(),
      timeout=600  # Increase to 10 minutes
  )
  ```

## Development Workflow

### Making Changes

1. **Edit code** in `pipgraph_cli/`
2. **Test immediately** (no reinstall needed with `-e`)
   ```bash
   pipgraph --help  # Changes reflect immediately
   ```

### Adding Dependencies

1. **Add to pyproject.toml**:
   ```toml
   dependencies = [
       "websockets>=12.0",
       "new-package>=1.0.0",
   ]
   ```

2. **Install**:
   ```bash
   uv pip install -e .
   ```

### Code Style

- **Type hints**: Use throughout
- **Async**: Prefer async/await for I/O
- **Error handling**: Catch specific exceptions
- **UI**: Always provide fallback for non-rich mode

## Related Documentation

- **Backend API**: [../backend/CLAUDE.md](../backend/CLAUDE.md)
- **Backend WebSocket**: [../backend/app/api/endpoints/notes.py](../backend/app/api/endpoints/notes.py)
- **Root Architecture**: [../CLAUDE.md](../CLAUDE.md)

## Technology Stack

- **Python**: 3.12+ (async/await, type hints)
- **Package Manager**: uv
- **WebSocket**: websockets library
- **CLI**: argparse (stdlib)
- **UI**: rich (optional)
- **Entry Points**: pyproject.toml [project.scripts]

## Important Notes

- **Always check backend** availability before operations
- **Timeout**: Set to 5 minutes for LLM processing
- **Error messages**: User-friendly, suggest solutions
- **Interactive mode**: Graceful exit on Ctrl+C
- **File mode**: Validate file exists before processing
- **UI fallback**: Always work without rich library

## Future Enhancements

See [README.md](README.md) TODO section:
- Search command for graph queries
- Batch file processing
- Configuration file support (.pipgraph.yaml)
- Progress bar for long operations
- Export formats (JSON, Markdown, CSV)
