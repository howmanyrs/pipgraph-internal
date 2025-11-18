Готово. Вот чистовая версия документа `02_DATA_MODELS.md`.

Я структурировал его так, чтобы он служил прямым руководством для разработчиков при написании кода. Модели Pydantic снабжены описаниями и примерами, а также четко разделены по назначению.

---
--- START OF FILE 02_DATA_MODELS.md ---

# Модели данных

**Дата создания:** 2025-11-17
**Статус:** Спецификация для реализации
**Версия:** 1.0

---

## Введение

Этот документ описывает **полные схемы моделей данных** для системы многоуровневых подтверждений. Все модели представлены в формате, готовом для реализации в коде с использованием Pydantic, и сопровождаются примерами JSON-структур для API и хранения.

---

## 1. UserCheckStatus

**Назначение:** Представляет одно событие подтверждения пользователя. Хранится как отдельная нода `(:UserCheckStatus)` в Neo4j.

### 1.1 Pydantic Model

```python
from typing import Optional, List, Literal
from datetime import datetime
from pydantic import BaseModel, Field

class UserCheckStatus(BaseModel):
    """Модель для ноды UserCheckStatus в Neo4j."""

    # Идентификация
    id: str = Field(..., description="Уникальный ID проверки, например, check_abc123")

    # Основной статус
    status: Literal[
        "pending", "confirmed", "modified", "rejected", "skipped", "auto_confirmed"
    ]
    confirmation_level: Literal[
        "para_classification", "container_assignment", "entity", "attribute"
    ]

    # Метаданные
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Уверенность системы 0.0-1.0")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    user_action: Optional[Literal["confirm", "modify", "reject", "skip", "defer"]] = None

    # Изменения (только для status="modified")
    modified_fields: Optional[List[str]] = Field(None, description="Список измененных полей, например, ['name', 'role']")
    modifications: Optional[str] = Field(None, description="JSON-строка с массивом объектов FieldModification")

    # Дополнительная информация
    user_comment: Optional[str] = None
    system_suggestion: Optional[str] = Field(None, description="Изначальное предложение системы")
    auto_confirmed: bool = False

    # Skip/Defer
    skip_count: int = 0
    defer_until: Optional[datetime] = None
    defer_reason: Optional[str] = None
```

### 1.2 Примеры JSON

#### Подтверждено без изменений

```json
{
    "id": "check_001",
    "status": "confirmed",
    "confirmation_level": "entity",
    "confidence": 0.85,
    "timestamp": "2025-11-17T12:00:00Z",
    "user_action": "confirm"
}
```

#### Подтверждено с изменениями

```json
{
    "id": "check_002",
    "status": "modified",
    "confirmation_level": "entity",
    "confidence": 0.70,
    "timestamp": "2025-11-17T12:05:00Z",
    "user_action": "modify",
    "modified_fields": ["name", "role"],
    "modifications": "[{\"field_name\": \"name\", \"original_value\": \"John\", \"new_value\": \"John Smith\"}]",
    "user_comment": "Corrected name and title"
}
```

---

## 2. FieldModification

**Назначение:** Описывает изменение одного поля сущности. Хранится как элемент JSON-массива в поле `modifications` ноды `UserCheckStatus`.

### 2.1 Pydantic Model

```python
class FieldModification(BaseModel):
    """Описание изменения одного поля."""

    field_name: str
    original_value: Optional[str] = None
    new_value: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
```

### 2.2 Пример JSON

```json
{
    "field_name": "name",
    "original_value": "John",
    "new_value": "John Smith",
    "timestamp": "2025-11-17T12:05:00Z"
}
```

---

## 3. PARA Container Nodes

**Назначение:** Высокоуровневые узлы-агрегаторы для организации заметок по методу PARA.

### 3.1 Project

**Описание:** Конкретная цель с четким сроком выполнения.

```python
from datetime import date

class Project(BaseModel):
    id: str = Field(..., description="Уникальный ID проекта, например, proj_abc123")
    name: str
    status: Literal["active", "completed", "archived", "on_hold"] = "active"
    deadline: Optional[date] = None
    goal: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    team: Optional[List[str]] = Field(None, description="Список UUID участников (Person nodes)")
    budget: Optional[float] = None
```

**Пример JSON:**

```json
{
    "id": "proj_123",
    "name": "Q4 Marketing Campaign",
    "status": "active",
    "deadline": "2024-12-31",
    "goal": "Increase signups by 20%"
}
```

### 3.2 Area

**Описание:** Сфера ответственности без конечной даты.

```python
class Area(BaseModel):
    id: str = Field(..., description="Уникальный ID области, например, area_xyz456")
    name: str
    goal: Optional[str] = None
    review_frequency: Optional[Literal["weekly", "monthly", "quarterly"]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    active: bool = True
```

**Пример JSON:**

```json
{
    "id": "area_456",
    "name": "Team Management",
    "goal": "Maintain high team morale and productivity",
    "review_frequency": "monthly"
}
```

### 3.3 Resource

**Описание:** Тема или интерес для справки.

```python
class Resource(BaseModel):
    id: str = Field(..., description="Уникальный ID ресурса, например, res_def789")
    topic: str
    category: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    tags: Optional[List[str]] = None
```

**Пример JSON:**

```json
{
    "id": "res_789",
    "topic": "API Design Best Practices",
    "category": "Programming",
    "tags": ["api", "rest", "design"]
}
```

---

## 4. Расширения существующих моделей

### 4.1 Note

**Назначение:** Заметка из Obsidian с дополнительными кэшированными атрибутами для быстрой фильтрации.

**Ключевые поля в Neo4j:**

```cypher
(:Note {
    // === Базовые атрибуты ===
    path: string,
    created_at: datetime,
    updated_at: datetime,

    // === Кэшированные атрибуты для PARA ===
    para_type: string,      // "Project" | "Area" | "Resource" | null
    project_id: string,     // UUID связанного Project (если para_type="Project")
    area_id: string,        // и т.д.
    resource_id: string,

    // === Кэшированные статусы подтверждений ===
    _para_check_status: string,      // Статус для L1
    _container_check_status: string  // Статус для L2
})
```

**Важно:** Эти атрибуты — **кэш**. Источником истины является связь `[:IS_PART_OF]` с соответствующей нодой контейнера.

### 4.2 EntityNode

**Назначение:** Извлеченная из текста сущность. Дополнительные атрибуты используются для кэширования и приоритизации.

**Ключевые поля в Neo4j (внутри `attributes`):**

```cypher
(:EntityNode {
    uuid: string,
    name: string,
    labels: [string],
    attributes: {
        // ... существующие атрибуты ...

        // Кэшированные данные (опционально)
        _current_check_status: string,
        _check_priority: int,
        _confidence: float
    }
})
```

**Важно:** Как и в случае с `Note`, эти атрибуты являются кэшем. Источник истины — связь `[:HAS_CHECK]` с `UserCheckStatus`.

---

## 5. Специализированные модели для Workflow

Эти модели используются внутри LangGraph для обработки ответов пользователя и не хранятся в Neo4j напрямую.

### 5.1 PARAClassificationCheck (L1)

**Назначение:** Представление результата L1-подтверждения.

```python
class PARAClassificationCheck(BaseModel):
    """Результат L1-подтверждения типа заметки."""
    status: Literal["confirmed", "modified"]
    original_suggestion: Literal["Project", "Area", "Resource", "Archive"]
    user_choice: Literal["Project", "Area", "Resource", "Archive"]
    confidence: float

    @property
    def changed(self) -> bool:
        return self.original_suggestion != self.user_choice
```

### 5.2 ContainerAssignmentCheck (L2)

**Назначение:** Представление результата L2-подтверждения.

```python
class ContainerAssignmentCheck(BaseModel):
    """Результат L2-подтверждения привязки к контейнеру."""
    status: Literal["confirmed", "created"]
    action: Literal["create_new", "link_existing", "skip"]
    container_type: Literal["Project", "Area", "Resource"]
    container_id: str
    container_name: str
    created_new: bool = False
```

---

## Сводная таблица моделей

| Модель | Где хранится | Назначение |
| :--- | :--- | :--- |
| **UserCheckStatus** | Отдельная нода в Neo4j | Событие подтверждения пользователя |
| **FieldModification** | JSON-строка в `UserCheckStatus` | Описание изменения одного поля |
| **Project/Area/Resource** | Отдельные ноды в Neo4j | PARA контейнеры (источник истины) |
| **Note** (расширение) | Существующая нода `Note` | Заметка с кэшированными данными |
| **EntityNode** (расширение) | Существующая нода `EntityNode` | Сущность с кэшированными данными |
| **...Check** (L1/L2) | В коде (Pydantic) | Структуры для LangGraph workflow |

---

**Следующий документ:** [03_GRAPH_SCHEMA.md](./03_GRAPH_SCHEMA.md)