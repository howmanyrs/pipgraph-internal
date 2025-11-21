# Cascade Mock Implementation

## Overview

Cascade функционал позволяет автоматически разрешать похожие suggestions когда пользователь принимает решение по одной заметке.

**Сценарий**: Пользователь подтверждает что заметка "Мемная битва" относится к Project. Система автоматически находит и разрешает похожие pending suggestions для заметок "Регистрация мемов" и "PvP битвы мемов".

## Architecture

### Data Flow

```
Frontend: POST /suggestion/{id}/decision {action: "confirm"}
                    │
                    ▼
Backend:  1. Process decision для заметки A
          2. Автоматически найти cascade candidates
          3. Применить cascade для высоко-релевантных (confidence > 0.85)
          4. Вернуть результат
                    │
                    ▼
Response: {
            "decision_applied": true,
            "cascade_applied": [
              {"note_path": "note_b.md", "auto_resolved": true},
              {"note_path": "note_c.md", "auto_resolved": true}
            ]
          }
```

### Source of Truth

| Компонент | Ответственность |
|-----------|-----------------|
| **LangGraph State** | Прогресс workflow (текущий node, interrupt status) |
| **Neo4j Graph** | Данные (suggestions, relationships) - **Source of Truth** |

### Cascade Logic

1. User confirms suggestion → creates `:IS_PART_OF` to container
2. Backend queries Neo4j for other `:SUGGESTS` to same container
3. For each with confidence > 0.85:
   - Delete `:SUGGESTS`
   - Create `:IS_PART_OF`
4. Return list of auto-resolved notes

### Key Principles

- **Automatic cascade** - no separate confirmation step
- **Threshold-based** - only auto-resolve if confidence > 0.85
- **Neo4j-centric** - cascade works directly with graph, not LangGraph state
- **Workflow awareness** - workflows read current state from Neo4j on resume

## Components

### New Files

```
backend/app/
├── services/
│   ├── cascade_service.py      # CascadeService class
│   └── mocks/
│       └── mock_cascade.py     # Deterministic mock for testing
└── crud/
    └── relationship_crud.py    # Extended with cascade queries
```

### Extended Files

- `backend/app/crud/relationship_crud.py` - new query methods
- `backend/app/services/pipgraph_manager.py` - cascade integration
- `backend/app/workflows/para_workflow.py` - cascade in process_decision_node

## API Changes

### Extended Response

`POST /suggestion/{id}/decision` response now includes:

```json
{
  "success": true,
  "decision_result": {
    "action": "confirm",
    "container_id": "uuid-..."
  },
  "cascade_applied": [
    {
      "note_path": "note_b.md",
      "suggestion_id": "uuid-...",
      "confidence": 0.92,
      "auto_resolved": true
    }
  ]
}
```

### New Endpoint

`GET /inbox/suggestions` - returns all pending suggestions across all notes:

```json
{
  "suggestions": [
    {
      "suggestion_id": "uuid-...",
      "note_path": "note_a.md",
      "container_id": "uuid-...",
      "container_name": "Meme Battle",
      "confidence": 0.8,
      "suggestion_type": "link"
    }
  ],
  "total": 5
}
```

## Mock Strategy

Mock cascade uses deterministic logic for testing:

```python
# mock_cascade.py
def find_cascade_candidates(container_id: str) -> list[dict]:
    """
    Returns fixed candidates based on container_id.
    For testing: always returns 2 candidates with confidence 0.9 and 0.7.
    Only 0.9 passes threshold for auto-resolve.
    """
```

This allows predictable tests without real embeddings/similarity search.

## Related Documents

- [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) - Step-by-step implementation checklist
- [MOCK_IMPLEMENTATION_CHECKLIST.md](../response_flow_plan_v02/MOCK_IMPLEMENTATION_CHECKLIST.md) - Previous iteration
