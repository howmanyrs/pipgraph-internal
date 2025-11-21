# API Update for Mock Workflow

## Overview

Обновление REST API для работы с mock реализациями workflow. Цель - сделать API функциональным для тестирования через pipgraph-cli до интеграции реальных LLM.

## Current State

### Existing Endpoints

```
POST /api/v1/notes/workflow/start      - запуск workflow
POST /api/v1/notes/workflow/resume     - resume с ответом
GET  /api/v1/notes/workflow/status/{id} - статус
```

### Problems

1. **Неоптимальные пути**: `/notes/workflow/*` вместо `/workflow/*`
2. **thread_id с двоеточиями**: `note:path/file.md` - проблемы с URL encoding
3. **Нет suggestions API**: вопросы встроены в workflow state
4. **Нет inbox endpoint**: нельзя получить все pending suggestions
5. **Schemas inline**: не вынесены в отдельные файлы

## Target State

### New API Structure

```
# Workflow management
POST /api/v1/workflow/start                    → WorkflowCreateResponse
GET  /api/v1/workflow/{workflow_id}/status     → WorkflowStatusResponse
POST /api/v1/workflow/{workflow_id}/resume     → WorkflowResumeResponse

# Suggestions
GET  /api/v1/workflow/{workflow_id}/suggestions → SuggestionsResponse
POST /api/v1/suggestion/{suggestion_id}/decision → DecisionResponse

# Inbox
GET  /api/v1/inbox/suggestions                 → InboxResponse
GET  /api/v1/inbox/count                       → {count: int}
```

### ID Schema Change

**Before**: `thread_id = "note:meetings/sync.md"`
**After**: `workflow_id = "wf_a1b2c3d4"` (UUID-based, URL-safe)

## File Structure

### New Files

```
backend/app/api/
├── endpoints/
│   ├── notes.py           # Keep old WebSocket (deprecated)
│   ├── workflow.py        # NEW: Workflow REST API
│   └── suggestions.py     # NEW: Suggestions/Inbox API
└── schemas/
    ├── __init__.py
    ├── workflow.py        # Workflow request/response
    └── suggestions.py     # Suggestion/Inbox models
```

### Updated Files

- `backend/app/api/main.py` - register new routers
- `backend/app/workflows/para_workflow.py` - new ID generation

## Request/Response Examples

### Start Workflow

```bash
curl -X POST http://localhost:8000/api/v1/workflow/start \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "projects/meme-battle.md",
    "content": "# Meme Battle\n\nGame where users battle with memes..."
  }'
```

Response:
```json
{
  "workflow_id": "wf_a1b2c3d4",
  "status": "waiting_user",
  "file_path": "projects/meme-battle.md"
}
```

### Get Suggestions

```bash
curl http://localhost:8000/api/v1/workflow/wf_a1b2c3d4/suggestions
```

Response:
```json
{
  "workflow_id": "wf_a1b2c3d4",
  "suggestions": [
    {
      "suggestion_id": "sug_x1y2z3",
      "suggestion_type": "para_link",
      "container_type": "Project",
      "container_name": "Mock Project Alpha",
      "confidence": 0.80,
      "alternatives": [
        {"type": "property_update", "field": "name", "confidence": 0.75}
      ]
    }
  ]
}
```

### Submit Decision

```bash
curl -X POST http://localhost:8000/api/v1/suggestion/sug_x1y2z3/decision \
  -H "Content-Type: application/json" \
  -d '{
    "action": "confirm"
  }'
```

Response:
```json
{
  "success": true,
  "workflow_id": "wf_a1b2c3d4",
  "suggestion_id": "sug_x1y2z3",
  "action": "confirm",
  "cascade_applied": [
    {
      "note_path": "ideas/meme-registry.md",
      "suggestion_id": "sug_p1q2r3",
      "auto_resolved": true
    }
  ]
}
```

### Get Inbox

```bash
curl http://localhost:8000/api/v1/inbox/suggestions
```

Response:
```json
{
  "suggestions": [
    {
      "suggestion_id": "sug_x1y2z3",
      "workflow_id": "wf_a1b2c3d4",
      "note_path": "projects/meme-battle.md",
      "suggestion_type": "para_link",
      "container_name": "Mock Project Alpha",
      "confidence": 0.80,
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total_count": 1
}
```

## WebSocket Compatibility

REST API работает параллельно с WebSocket `/ws/workflow`. Оба используют:
- Одинаковые workflow_id
- Одинаковое состояние в Neo4j
- Одинаковые LangGraph workflows

CLI может использовать REST для простоты, Obsidian plugin - WebSocket для real-time.

## Related Documents

- [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) - Step-by-step implementation
- [cascade_mocks_update/](../cascade_mocks_update/) - Cascade functionality (depends on this)
- [response_flow_plan_v02/](../response_flow_plan_v02/) - Previous mock implementation
