# Data Structures - Минимальные модели для MVP

**Цель:** Определить упрощенные Pydantic модели и Neo4j схему для MVP.

---

## Принципы упрощения

1. **Только необходимые поля** - откладываем все "nice-to-have"
2. **Простые типы** - избегаем сложных nested структур
3. **No-Cache Policy** - никаких дублированных данных в свойствах

---

## Neo4j Graph Schema

### Node Types

#### 1. Project
**Описание:** Временный проект с конкретной целью.

**Properties:**
```python
{
    "id": str,          # UUID, primary key
    "name": str,        # Display name
    "status": str       # "active" | "completed" | "archived"
}
```

**Example:**
```json
{
    "id": "proj-550e8400-e29b-41d4-a716-446655440000",
    "name": "Website Redesign",
    "status": "active"
}
```

**Constraints:**
```cypher
CREATE CONSTRAINT project_id_unique IF NOT EXISTS
FOR (p:Project) REQUIRE p.id IS UNIQUE;
```

---

#### 2. Area
**Описание:** Долгосрочная область ответственности.

**Properties:**
```python
{
    "id": str,     # UUID, primary key
    "name": str    # Display name
}
```

**Example:**
```json
{
    "id": "area-e5d8a3f1-2c9b-4e67-8f1a-3d9c8e7b6a5f",
    "name": "Health & Fitness"
}
```

**Constraints:**
```cypher
CREATE CONSTRAINT area_id_unique IF NOT EXISTS
FOR (a:Area) REQUIRE a.id IS UNIQUE;
```

---

#### 3. Resource
**Описание:** Справочный материал, база знаний.

**Properties:**
```python
{
    "id": str,     # UUID, primary key
    "name": str    # Display name
}
```

**Example:**
```json
{
    "id": "res-7f9e2b8a-4d3c-1e5f-9a8b-2c7d6e5f4a3b",
    "name": "Design Patterns Library"
}
```

**Constraints:**
```cypher
CREATE CONSTRAINT resource_id_unique IF NOT EXISTS
FOR (r:Resource) REQUIRE r.id IS UNIQUE;
```

---

#### 4. Episodic
**Описание:** Файл заметки в Obsidian, сохраненный как эпизод средствами Graphiti.

**Properties:**
```python
{
    "path": str,            # Unique file path (e.g., "Notes/daily/2025-11-19.md")
    "created_at": datetime, # Timestamp создания
    "updated_at": datetime  # Timestamp последнего изменения
}
```

**Важно:** ❌ **НЕТ поля `project_id`** - контекст определяется через связь `[:IS_PART_OF]`

**Example:**
```json
{
    "path": "Notes/daily/2025-11-19.md",
    "created_at": "2025-11-19T10:30:00Z",
    "updated_at": "2025-11-19T15:45:00Z"
}
```

**Constraints:**
```cypher
CREATE CONSTRAINT episodic_path_unique IF NOT EXISTS
FOR (n:Episodic) REQUIRE n.path IS UNIQUE;
```

---

#### 5. Entity
**Описание:** Извлеченная сущность (Graphiti output).

**Properties:**
```python
{
    "uuid": str,           # UUID от Graphiti
    "name": str,           # Entity name (e.g., "User Authentication")
    "labels": list[str],   # ["Concept"] или ["Task", "Decision"]
    "summary": str         # Краткое описание сущности
}
```

**Важно:** ❌ **НЕТ поля `status`** - статус определяется через связь `[:HAS_CHECK]`

**Example:**
```json
{
    "uuid": "ent-a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "name": "Homepage Redesign",
    "labels": ["Concept", "Task"],
    "summary": "Complete redesign of the main landing page"
}
```

**Indexes:**
```cypher
CREATE INDEX entity_uuid_idx IF NOT EXISTS
FOR (e:Entity) ON (e.uuid);
```

---

#### 6. UserCheckStatus
**Описание:** История решений пользователя (для L1/L2 и L3).

**Properties (MVP - упрощенная версия):**
```python
{
    "id": str,          # UUID check
    "timestamp": datetime,
    "status": str,      # "pending" | "confirmed" | "rejected"
    "outcome": str,     # "confirmed" | "linked_to_alternative" | "created_custom" | "dismissed"
    "comment": str      # Optional user comment (nullable)
}
```

**Откладываем на потом:**
- `system_proposal_snapshot` - полный snapshot предложения системы
- `user_selection_snapshot` - полный snapshot выбора пользователя

**Example:**
```json
{
    "id": "check-9f8e7d6c-5b4a-3210-fedc-ba9876543210",
    "timestamp": "2025-11-19T11:00:00Z",
    "status": "confirmed",
    "outcome": "confirmed",
    "comment": null
}
```

**Indexes:**
```cypher
CREATE INDEX check_status_idx IF NOT EXISTS
FOR (c:UserCheckStatus) ON (c.id);
```

---

### Relationship Types

#### 1. [:IS_PART_OF]
**Описание:** Связывает заметку с PARA контейнером.

**From:** `Episodic`
**To:** `Project | Area | Resource`

**Properties:** (нет)

**Example:**
```cypher
(n:Episodic {path: "Notes/daily/2025-11-19.md"})-[:IS_PART_OF]->(p:Project {id: "proj-123"})
```

**Важность:** Это **единственный источник истины** для вопроса "К какому проекту относится заметка?"

---

#### 2. [:MENTIONS]
**Описание:** Связывает заметку с извлеченными сущностями.

**From:** `Episodic`
**To:** `Entity`

**Properties:** (нет)

**Example:**
```cypher
(n:Episodic {path: "Notes/daily/2025-11-19.md"})-[:MENTIONS]->(e:Entity {uuid: "ent-123"})
```

---

#### 3. [:HAS_CHECK]
**Описание:** Связывает заметку или сущность с решением пользователя.

**From:** `Episodic | Entity`
**To:** `UserCheckStatus`

**Properties:**
```python
{
    "is_current": bool  # True для последнего check, False для истории
}
```

**Example:**
```cypher
(n:Episodic {path: "Notes/daily/2025-11-19.md"})-[:HAS_CHECK {is_current: true}]->(c:UserCheckStatus {id: "check-123"})
```

**Важность:** Позволяет находить текущий статус через traversal:
```cypher
MATCH (n:Episodic {path: $path})-[:HAS_CHECK {is_current: true}]->(c:UserCheckStatus)
RETURN c.status
```

---

#### 4. [:NEXT] (опционально в MVP)
**Описание:** Связывает UserCheckStatus узлы в хронологическую цепочку.

**From:** `UserCheckStatus`
**To:** `UserCheckStatus`

**Properties:** (нет)

**Example:**
```cypher
(old:UserCheckStatus {id: "check-1"})-[:NEXT]->(new:UserCheckStatus {id: "check-2"})
```

**Статус:** **Can defer** - можно добавить после MVP для анализа истории.

---

## Pydantic Models (Backend API)

### L1/L2 Identification Models

#### PARACandidate
```python
from pydantic import BaseModel, Field

class PARACandidate(BaseModel):
    """Кандидат PARA контейнера (Project/Area/Resource)."""

    id: str = Field(..., description="UUID контейнера")
    name: str = Field(..., description="Display name")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0-1")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "proj-123",
                "name": "Website Redesign",
                "confidence": 0.87
            }
        }
```

---

#### PARAProposal
```python
class PARAProposal(BaseModel):
    """Предложение системы для L1/L2 идентификации."""

    para_type: str = Field(..., description="PARA type: Project | Area | Resource")
    primary_candidate: PARACandidate = Field(..., description="Лучший кандидат")
    alternatives: list[PARACandidate] = Field(default_factory=list, description="Альтернативы")
    reasoning: str = Field(..., description="Почему система предложила primary")

    class Config:
        json_schema_extra = {
            "example": {
                "para_type": "Project",
                "primary_candidate": {
                    "id": "proj-123",
                    "name": "Website Redesign",
                    "confidence": 0.87
                },
                "alternatives": [
                    {"id": "proj-456", "name": "Mobile App", "confidence": 0.65}
                ],
                "reasoning": "This note discusses design mockups and homepage layout, which aligns with the Website Redesign project."
            }
        }
```

---

#### UserDecisionPayload
```python
class UserDecisionPayload(BaseModel):
    """Решение пользователя из WebSocket."""

    action: str = Field(..., description="confirm | link_to_alternative | create_custom | dismiss")
    selected_container_id: str | None = Field(None, description="ID для link_to_alternative")
    custom_container_name: str | None = Field(None, description="Имя для create_custom")
    custom_container_type: str | None = Field(None, description="PARA type для create_custom")
    comment: str | None = Field(None, description="Optional user comment")

    class Config:
        json_schema_extra = {
            "example": {
                "action": "link_to_alternative",
                "selected_container_id": "proj-456",
                "comment": "Actually this belongs to Mobile App project"
            }
        }
```

---

### L3 Extraction Models

#### ExtractedCandidate
```python
class ExtractedCandidate(BaseModel):
    """Сущность, извлеченная Graphiti (до сохранения в граф)."""

    uuid: str = Field(..., description="UUID от Graphiti")
    name: str = Field(..., description="Entity name")
    labels: list[str] = Field(..., description="Entity types (whitelist)")
    summary: str = Field(..., description="Краткое описание")

    class Config:
        json_schema_extra = {
            "example": {
                "uuid": "ent-123",
                "name": "User Authentication System",
                "labels": ["Concept", "Task"],
                "summary": "Implement OAuth2-based user login system"
            }
        }
```

---

### Workflow State Model

#### NoteWorkflowState
```python
class NoteWorkflowState(BaseModel):
    """LangGraph state для обработки заметки."""

    # Input
    note_path: str = Field(..., description="Unique file path")
    note_content: str = Field(..., description="Full markdown content")

    # L1/L2 State
    system_proposal: PARAProposal | None = Field(None, description="Proposal от системы")
    user_decision: UserDecisionPayload | None = Field(None, description="Решение юзера")
    final_context: dict | None = Field(None, description="Финальный PARA контейнер")

    # L3 State
    extracted_entities: list[ExtractedCandidate] = Field(default_factory=list)
    confirmed_entity_uuids: list[str] = Field(default_factory=list)

    # Error handling
    error: str | None = Field(None, description="Error message if failed")

    class Config:
        arbitrary_types_allowed = True  # Для datetime и других типов
```

---

## Упрощения для MVP

### 1. UserCheckStatus - Minimal Snapshots
**Вместо:**
```python
system_proposal_snapshot: dict  # Full PARAProposal
user_selection_snapshot: dict   # Full UserDecisionPayload
```

**В MVP:**
```python
outcome: str  # Простая строка: "confirmed" | "linked_to_alternative" | ...
comment: str | None  # Optional текст от пользователя
```

**Почему:**
- Достаточно для отслеживания факта решения
- Не нужна сложная логика diff/comparison

---

### 2. Entity - No Status Field
**Вместо:**
```python
status: str  # "pending" | "confirmed" | "rejected"
```

**В MVP:**
- Статус определяется через traversal:
  ```cypher
  MATCH (e:Entity {uuid: $uuid})-[:HAS_CHECK {is_current: true}]->(c:UserCheckStatus)
  RETURN c.status
  ```

**Почему:**
- Соблюдаем No-Cache Policy
- Избегаем рассинхронизации

---

### 3. Episodic - No Cached Fields
**Вместо:**
```python
project_id: str  # Cached link to project
para_type: str   # Cached PARA type
```

**В MVP:**
- Контекст определяется через traversal:
  ```cypher
  MATCH (n:Episodic {path: $path})-[:IS_PART_OF]->(container)
  WHERE container:Project OR container:Area OR container:Resource
  RETURN container
  ```

**Почему:**
- Граф - единственный источник истины
- Нет синхронизации при изменении контейнера

---

### 4. Simplified Timestamps
**Вместо:**
```python
created_at: datetime
updated_at: datetime
last_processed_at: datetime
last_extraction_at: datetime
```

**В MVP:**
```python
created_at: datetime
updated_at: datetime
```

**Почему:**
- Базовая временная информация
- Дополнительные timestamps можно добавить позже

---

## Validation Rules

### PARA Type Validation
```python
from enum import Enum

class PARAType(str, Enum):
    PROJECT = "Project"
    AREA = "Area"
    RESOURCE = "Resource"

# Usage
class PARAProposal(BaseModel):
    para_type: PARAType  # Enforces enum values
```

---

### Entity Label Whitelist
```python
ALLOWED_ENTITY_LABELS = ["Concept", "Person", "Task", "Decision"]

class ExtractedCandidate(BaseModel):
    labels: list[str]

    @validator("labels")
    def validate_labels(cls, v):
        for label in v:
            if label not in ALLOWED_ENTITY_LABELS:
                raise ValueError(f"Label '{label}' not in whitelist: {ALLOWED_ENTITY_LABELS}")
        return v
```

---

### UserDecision Action Validation
```python
class UserAction(str, Enum):
    CONFIRM = "confirm"
    LINK_TO_ALTERNATIVE = "link_to_alternative"
    CREATE_CUSTOM = "create_custom"
    DISMISS = "dismiss"

class UserDecisionPayload(BaseModel):
    action: UserAction  # Enforces valid actions
```

---

## Example: Full Graph State

После обработки заметки `Notes/daily/2025-11-19.md`:

```cypher
// Nodes
(:Episodic {path: "Notes/daily/2025-11-19.md", created_at: ..., updated_at: ...})
(:Project {id: "proj-123", name: "Website Redesign", status: "active"})
(:Entity {uuid: "ent-1", name: "Homepage Layout", labels: ["Concept"], summary: "..."})
(:Entity {uuid: "ent-2", name: "Design Mockups", labels: ["Task"], summary: "..."})
(:UserCheckStatus {id: "check-1", status: "confirmed", outcome: "confirmed", timestamp: ...})
(:UserCheckStatus {id: "check-2", status: "confirmed", outcome: "confirmed", timestamp: ...})

// Relationships
(Episodic)-[:IS_PART_OF]->(Project)
(Episodic)-[:MENTIONS]->(Entity:ent-1)
(Episodic)-[:MENTIONS]->(Entity:ent-2)
(Episodic)-[:HAS_CHECK {is_current: true}]->(UserCheckStatus:check-1)
(Entity:ent-1)-[:HAS_CHECK {is_current: true}]->(UserCheckStatus:check-2)
```

**Queries:**

1. **Найти проект для заметки:**
   ```cypher
   MATCH (n:Episodic {path: "Notes/daily/2025-11-19.md"})-[:IS_PART_OF]->(p:Project)
   RETURN p.name
   // Result: "Website Redesign"
   ```

2. **Найти все сущности в заметке:**
   ```cypher
   MATCH (n:Episodic {path: "Notes/daily/2025-11-19.md"})-[:MENTIONS]->(e:Entity)
   RETURN e.name, e.labels
   ```

3. **Найти статус сущности:**
   ```cypher
   MATCH (e:Entity {uuid: "ent-1"})-[:HAS_CHECK {is_current: true}]->(c:UserCheckStatus)
   RETURN c.status
   // Result: "confirmed"
   ```

---

## Migration Strategy

### Initial Setup
```python
# app/db/migrations/001_initial_schema.py

async def create_initial_schema(neo4j_driver):
    """Создает constraints и индексы для MVP."""

    async with neo4j_driver.session() as session:
        # Constraints
        await session.run(
            "CREATE CONSTRAINT episodic_path_unique IF NOT EXISTS "
            "FOR (n:Episodic) REQUIRE n.path IS UNIQUE"
        )
        await session.run(
            "CREATE CONSTRAINT project_id_unique IF NOT EXISTS "
            "FOR (p:Project) REQUIRE p.id IS UNIQUE"
        )
        # ... (остальные constraints)

        # Indexes
        await session.run(
            "CREATE INDEX entity_uuid_idx IF NOT EXISTS "
            "FOR (e:Entity) ON (e.uuid)"
        )
        # ... (остальные indexes)

    print("✅ Initial schema created")
```

---

## Next Steps

После прочтения этого документа:
- **Используйте эти модели** при написании кода в Iteration 1-5
- **Не добавляйте поля**, которых нет в этом документе (избегаем scope creep)
- **Сверяйтесь с [01_MVP_SCOPE.md](./01_MVP_SCOPE.md)** если появляется желание добавить "одно маленькое поле"

**Помните:** Упрощение - это не компромисс, а стратегия для быстрого достижения работающего MVP.
