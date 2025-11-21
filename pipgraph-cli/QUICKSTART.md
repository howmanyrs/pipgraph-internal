# PipGraph CLI - Quick Start

Quick start guide for working with PipGraph CLI.

## 1. Installation

```bash
cd pipgraph-cli/

# Create virtual environment with uv
uv venv
source .venv/bin/activate

# Install dependencies and package
uv pip install -e .
```

## 2. Start Backend

In a separate terminal:

```bash
cd backend/
source .venv/bin/activate
uvicorn app.api.main:app --reload
```

Backend will start at `http://localhost:8000`

## 3. Using CLI

### Workflow mode (recommended)

```bash
pipgraph -w
```

This is the most feature-rich mode:
1. Enter file path and content
2. Review suggestions with confidence scores
3. Make decisions (confirm/dismiss/modify)
4. See cascade auto-resolution results

Example:
```
Enter file path: notes/meeting.md
Enter note content:
# Meeting with John
Discussed project timeline.

Suggestion #1:
  Type: para_link
  Container: Project Alpha (Project)
  Confidence: 0.92

Enter action: confirm
Decision 'confirm' applied successfully!
Workflow completed successfully!
```

### Demo examples (easiest way to test)

```bash
pipgraph
```

This will run 3 pre-built examples:
1. Note about a person (John Doe)
2. Note about a project (PipGraph)
3. Note about a meeting (Daily Standup)

### Interactive mode

```bash
pipgraph -i
```

Then:
1. Enter path: `notes/test.md`
2. Enter content:
   ```
   # My Test Note
   This is a test note about something interesting.
   ```
3. Press `Ctrl+D` (Linux/Mac) or `Ctrl+Z` (Windows)

Or use commands:
- `demo` - run demo
- `quit` / `exit` - exit

### Process file

```bash
# Create test file
echo "# Test Note\nSome content" > test.md

# Process
pipgraph -f test.md
```

## 4. Check Results

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

## Troubleshooting

### Backend won't start

Check `.env` file in `backend/`:

```bash
OPENROUTER_API_KEY=sk-or-v1-...
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
```

### CLI cannot connect

```
✗ Error: Cannot connect to backend
```

**Solution**:
1. Make sure backend is running
2. Check port: `lsof -i :8000`
3. Try specifying URL explicitly: `pipgraph --backend-url ws://localhost:8000`

### Timeout

```
✗ Error: Timeout waiting for backend response
```

**Causes**:
- LLM API unavailable (check `OPENROUTER_API_KEY`)
- Neo4j unavailable (check `NEO4J_URI`)
- Slow internet (timeout is 5 minutes)

## Usage Examples

### 1. Quick test with workflow

```bash
# Terminal 1: Backend
cd backend/ && uvicorn app.api.main:app --reload

# Terminal 2: CLI workflow mode
cd pipgraph-cli/ && pipgraph -w

# Enter path and content, review suggestions, make decisions
```

### 2. Quick test with demo

```bash
# Terminal 1: Backend
cd backend/ && uvicorn app.api.main:app --reload

# Terminal 2: CLI demo
cd pipgraph-cli/ && pipgraph
```

### 3. Process real note

```bash
# If you have an Obsidian vault
pipgraph -f ~/Documents/ObsidianVault/Notes/meeting.md
```

### 4. Interactive work

```bash
pipgraph -i

# Example input:
notes/ideas/ai_research.md
# AI Research Ideas

- Neural networks for graph analysis
- LLM-based entity extraction
- Knowledge graph visualization
<Ctrl+D>
```

### 5. Without rich formatting

```bash
# For piping to file or scripts
pipgraph --no-rich > output.log
```

## Additional

### Help

```bash
pipgraph --help
```

### Version

```bash
pipgraph --version
```

### Custom backend URL

```bash
pipgraph --backend-url ws://192.168.1.100:8000
```

## Next Steps

1. Read [README.md](README.md) for full documentation
2. Study [backend/CLAUDE.md](../backend/CLAUDE.md) to understand API
3. Try processing your notes
4. Explore results in Neo4j Browser

Good luck! 🚀
