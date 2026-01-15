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

### Start workflow mode

```bash
pipgraph
```

Steps:
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

### Process file directly

```bash
pipgraph -f path/to/note.md
```

### Without rich formatting

```bash
# For piping to file or scripts
pipgraph --no-rich > output.log
```

## 4. Check Results

Processing results are displayed in console.

Data is saved to Neo4j. Check via Neo4j Browser:
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
Cannot connect to backend at http://localhost:8000
```

**Solution**:
1. Make sure backend is running
2. Check port: `lsof -i :8000`
3. Try specifying URL explicitly: `pipgraph --backend-url http://localhost:8000`

## Usage Examples

### 1. Quick test

```bash
# Terminal 1: Backend
cd backend/ && uvicorn app.api.main:app --reload

# Terminal 2: CLI
cd pipgraph-cli/ && pipgraph
```

### 2. Process real note

```bash
# If you have an Obsidian vault
pipgraph -f ~/Documents/ObsidianVault/Notes/meeting.md
```

## Help

```bash
pipgraph --help
pipgraph --version
```

## Custom backend URL

```bash
pipgraph --backend-url http://192.168.1.100:8000
```

## Next Steps

1. Read [README.md](README.md) for full documentation
2. Study [backend/CLAUDE.md](../backend/CLAUDE.md) to understand API
3. Try processing your notes
4. Explore results in Neo4j Browser
