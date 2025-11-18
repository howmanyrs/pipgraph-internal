# Модели данных

**Дата создания:** 2025-11-17
**Статус:** Спецификация для реализации
**Версия:** 1.0

---

## Введение

Этот документ описывает **полные схемы моделей данных** для системы многоуровневых подтверждений. Все модели представлены в формате, готовом для реализации в коде.

---

## 1. UserCheckStatus Node

### Описание

Нода в Neo4j, представляющая одно событие подтверждения пользователя. Каждая нода — это snapshot состояния на момент действия пользователя.

### Схема Neo4j

```cypher
(:UserCheckStatus {
    // === Идентификация ===
    id: string,                          // Уникальный ID проверки, например "check_abc123"

    // === Основной статус ===
    status: string,                      // "pending" | "confirmed" | "modified" | "rejected" | "skipped" | "auto_confirmed"
    confirmation_level: string,          // "para_classification" | "container_assignment" | "entity" | "attribute"

    // === Метаданные ===
    confidence: float,                   // Уверенность системы: 0.0-1.0
    timestamp: datetime,                 // Время создания проверки
    user_action: string,                 // "confirm" | "modify" | "reject" | "skip" | "defer" | null

    // === Изменения (только для status="modified") ===
    modified_fields: [string],           // Список измененных полей, например ["name", "role"]
    modifications: string,               // JSON-массив FieldModification объектов

    // === Дополнительная информация ===
    user_comment: string,                // Опциональный комментарий пользователя
    system_suggestion: string,           // Изначальное предложение системы
    auto_confirmed: boolean,             // true если подтверждено автоматически

    // === Skip/Defer (опционально) ===
    skip_count: int,                     // Сколько раз пропускали
    defer_until: datetime,               // Когда спросить снова (для defer)
    defer_reason: string                 // Причина отсрочки
})
```

### Pydantic Model (Python)

```python
from typing import Optional, List, Literal
from datetime import datetime
from pydantic import BaseModel, Field

class UserCheckStatus(BaseModel):
    """Базовая модель для UserCheckStatus node"""

    # Идентификация
    id: str = Field(..., description="Уникальный ID проверки")

    # Основной статус
    status: Literal[
        "pending",
        "confirmed",
        "modified",
        "rejected",
        "skipped",
        "auto_confirmed"
    ]
    confirmation_level: Literal[
        "para_classification",
        "container_assignment",
        "entity",
        "attribute"
    ]

    # Метаданные
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    user_action: Optional[Literal["confirm", "modify", "reject", "skip", "defer"]] = None

    # Изменения
    modified_fields: Optional[List[str]] = None
    modifications: Optional[str] = None  # JSON string

    # Дополнительная информация
    user_comment: Optional[str] = None
    system_suggestion: Optional[str] = None
    auto_confirmed: bool = False

    # Skip/Defer
    skip_count: int = 0
    defer_until: Optional[datetime] = None
    defer_reason: Optional[str] = None
```

### Примеры

#### Пример 1: Подтверждено без изменений

```json
{
    "id": "check_001",
    "status": "confirmed",
    "confirmation_level": "entity",
    "confidence": 0.85,
    "timestamp": "2025-11-17T12:00:00Z",
    "user_action": "confirm",
    "system_suggestion": "Person: John Smith",
    "auto_confirmed": false,
    "skip_count": 0
}
```

#### Пример 2: Подтверждено с изменениями

```json
{
    "id": "check_002",
    "status": "modified",
    "confirmation_level": "entity",
    "confidence": 0.70,
    "timestamp": "2025-11-17T12:05:00Z",
    "user_action": "modify",
    "modified_fields": ["name", "role"],
    "modifications": "[{\"field_name\": \"name\", \"original_value\": \"John\", \"new_value\": \"John Smith\", \"timestamp\": \"2025-11-17T12:05:00Z\"}, {\"field_name\": \"role\", \"original_value\": \"Developer\", \"new_value\": \"CEO\", \"timestamp\": \"2025-11-17T12:05:30Z\"}]",
    "user_comment": "Corrected name and title",
    "system_suggestion": "Person: John",
    "auto_confirmed": false,
    "skip_count": 0
}
```

#### Пример 3: Пропущено

```json
{
    "id": "check_003",
    "status": "skipped",
    "confirmation_level": "entity",
    "confidence": 0.50,
    "timestamp": "2025-11-17T12:10:00Z",
    "user_action": "skip",
    "user_comment": "Will verify contact details later",
    "skip_count": 1
}
```

#### Пример 4: Автоподтверждено

```json
{
    "id": "check_004",
    "status": "auto_confirmed",
    "confirmation_level": "entity",
    "confidence": 0.96,
    "timestamp": "2025-11-17T12:00:00Z",
    "user_action": null,
    "system_suggestion": "Source: https://example.com",
    "auto_confirmed": true,
    "skip_count": 0
}
```

#### Пример 5: PARA Classification

```json
{
    "id": "check_005",
    "status": "modified",
    "confirmation_level": "para_classification",
    "confidence": 0.70,
    "timestamp": "2025-11-17T12:00:00Z",
    "user_action": "modify",
    "modified_fields": ["para_type"],
    "modifications": "[{\"field_name\": \"para_type\", \"original_value\": \"Project\", \"new_value\": \"Area\", \"timestamp\": \"2025-11-17T12:00:00Z\"}]",
    "user_comment": "This is ongoing responsibility, not a project",
    "system_suggestion": "Project"
}
```

---

## 2. FieldModification Structure

### Описание

Структура, описывающая изменение одного поля сущности. Хранится как JSON-массив в поле `modifications` ноды `UserCheckStatus`.

### Pydantic Model

```python
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class FieldModification(BaseModel):
    """Описание изменения одного поля"""

    field_name: str
    original_value: Optional[str] = None
    new_value: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
```

### Примеры

#### Изменение имени

```json
{
    "field_name": "name",
    "original_value": "John",
    "new_value": "John Smith",
    "timestamp": "2025-11-17T12:05:00Z"
}
```

#### Изменение типа сущности

```json
{
    "field_name": "type",
    "original_value": "Person",
    "new_value": "Organization",
    "timestamp": "2025-11-17T12:05:30Z"
}
```

#### Добавление нового поля

```json
{
    "field_name": "email",
    "original_value": null,
    "new_value": "john.smith@example.com",
    "timestamp": "2025-11-17T12:06:00Z"
}
```

---

## 3. PARA Container Nodes

### Описание

Высокоуровневые узлы-агрегаторы для организации заметок по методу PARA (Project, Area, Resource).

### 3.1 Project Node

**Описание:** Конкретная цель с четким сроком выполнения.

**Схема Neo4j:**
```cypher
(:Project {
    id: string,                // Уникальный ID проекта
    name: string,              // Название проекта
    status: string,            // "active" | "completed" | "archived" | "on_hold"
    deadline: date,            // Дедлайн проекта
    goal: string,              // Описание цели проекта
    created_at: datetime,      // Дата создания
    completed_at: datetime,    // Дата завершения (если status="completed")
    team: [string],            // Список участников (UUID Person nodes)
    budget: float              // Бюджет (опционально)
})
```

**Pydantic Model:**
```python
from datetime import date, datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field

class Project(BaseModel):
    id: str = Field(..., description="Уникальный ID проекта")
    name: str
    status: Literal["active", "completed", "archived", "on_hold"] = "active"
    deadline: Optional[date] = None
    goal: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    team: Optional[List[str]] = None
    budget: Optional[float] = None
```

**Пример:**
```json
{
    "id": "proj_123",
    "name": "Q4 Marketing Campaign",
    "status": "active",
    "deadline": "2024-12-31",
    "goal": "Increase signups by 20%",
    "created_at": "2024-10-01T00:00:00Z",
    "team": ["person_uuid_1", "person_uuid_2"]
}
```

### 3.2 Area Node

**Описание:** Сфера ответственности без конечной даты.

**Схема Neo4j:**
```cypher
(:Area {
    id: string,                // Уникальный ID области
    name: string,              // Название области
    goal: string,              // Описание цели области
    review_frequency: string,  // "weekly" | "monthly" | "quarterly"
    created_at: datetime,      // Дата создания
    active: boolean            // true если активна
})
```

**Pydantic Model:**
```python
class Area(BaseModel):
    id: str
    name: str
    goal: Optional[str] = None
    review_frequency: Optional[Literal["weekly", "monthly", "quarterly"]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    active: bool = True
```

**Пример:**
```json
{
    "id": "area_456",
    "name": "Team Management",
    "goal": "Maintain high team morale and productivity",
    "review_frequency": "monthly",
    "created_at": "2024-01-01T00:00:00Z",
    "active": true
}
```

### 3.3 Resource Node

**Описание:** Тема или интерес для справки.

**Схема Neo4j:**
```cypher
(:Resource {
    id: string,           // Уникальный ID ресурса
    topic: string,        // Тема ресурса
    category: string,     // Категория (например, "Programming", "Business")
    created_at: datetime, // Дата создания
    tags: [string]        // Теги для поиска
})
```

**Pydantic Model:**
```python
class Resource(BaseModel):
    id: str
    topic: str
    category: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    tags: Optional[List[str]] = None
```

**Пример:**
```json
{
    "id": "res_789",
    "topic": "API Design Best Practices",
    "category": "Programming",
    "created_at": "2024-06-01T00:00:00Z",
    "tags": ["api", "rest", "design"]
}
```

---

## 4. Enhanced EntityNode

### Описание

Расширение существующего `EntityNode` для поддержки user_check workflow. Добавляются вспомогательные атрибуты, но основная логика проверки хранится в отдельных `UserCheckStatus` нодах.

### Дополнительные атрибуты (опционально)

```python
# Эти атрибуты НЕ обязательны, но могут быть полезны для кеширования
entity.attributes = {
    # ... существующие атрибуты ...

    # Кешированный текущий статус (для быстрого доступа без JOIN)
    '_current_check_status': 'confirmed',      # Опционально
    '_current_check_timestamp': '2025-11-17T12:00:00Z',  # Опционально

    # Приоритет для clarifications
    '_check_priority': 2,                      # 1-5, где 1 - highest
    '_confidence': 0.85                        # Уверенность системы при извлечении
}
```

**Важно:** Эти атрибуты — кеш. **Источник истины** — это связь с `UserCheckStatus` нодой.

### Связи

```cypher
// Текущий статус
(entity:EntityNode)-[:HAS_CHECK {is_current: true}]->(current_check:UserCheckStatus)

// Полная история (опционально)
(entity)-[:HAS_CHECK {is_current: false}]->(old_checks:UserCheckStatus)
```

---

## 5. Note Node (расширение)

### Описание

Заметка из Obsidian с дополнительными атрибутами для PARA классификации.

### Схема Neo4j

```cypher
(:Note {
    // === Базовые атрибуты ===
    path: string,                    // Путь к файлу, например "meetings/sync.md"
    created_at: datetime,            // Дата создания файла
    updated_at: datetime,            // Дата последнего изменения

    // === PARA Classification (кешированные) ===
    para_type: string,               // "Project" | "Area" | "Resource" | "Archive" | null
    project_id: string,              // UUID связанного Project (если para_type="Project")
    area_id: string,                 // UUID связанной Area (если para_type="Area")
    resource_id: string,             // UUID связанного Resource (если para_type="Resource")

    // === User Check Status (кешированный) ===
    _para_check_status: string,      // "pending" | "confirmed" | "modified" и т.д.
    _container_check_status: string  // Статус для L2 (container assignment)
})
```

**Важно:** Атрибуты `para_type`, `project_id` и т.д. — это **кеш** для быстрых фильтров. **Источник истины** — связь `IS_PART_OF` с PARA container node.

### Связи

```cypher
// Связь с PARA container (источник истины)
(n:Note)-[:IS_PART_OF]->(p:Project)
(n:Note)-[:IS_PART_OF]->(a:Area)
(n:Note)-[:IS_PART_OF]->(r:Resource)

// User check для PARA classification
(n:Note)-[:HAS_CHECK {is_current: true}]->(check_l1:UserCheckStatus {confirmation_level: "para_classification"})

// User check для container assignment
(n:Note)-[:HAS_CHECK {is_current: true}]->(check_l2:UserCheckStatus {confirmation_level: "container_assignment"})
```

---

## 6. Специализированные модели для уровней

### 6.1 PARA Classification Check

**Использование:** Уровень L1 (определение типа заметки)

**Pydantic Model:**
```python
class PARAClassificationCheck(BaseModel):
    """User check для PARA классификации заметки"""

    status: Literal["pending", "confirmed", "modified"]

    original_suggestion: Literal["Project", "Area", "Resource", "Archive"]
    user_choice: Literal["Project", "Area", "Resource", "Archive"]

    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    reasoning: Optional[str] = None
    changed: bool = Field(default=False)

    def model_post_init(self, __context):
        """Auto-calculate changed flag"""
        self.changed = self.original_suggestion != self.user_choice
        if self.changed:
            self.status = "modified"
```

**Пример:**
```json
{
    "status": "modified",
    "original_suggestion": "Project",
    "user_choice": "Area",
    "confidence": 0.70,
    "timestamp": "2025-11-17T12:00:00Z",
    "reasoning": "This is ongoing responsibility, not a time-bound project",
    "changed": true
}
```

### 6.2 Container Assignment Check

**Использование:** Уровень L2 (привязка к проекту/области/ресурсу)

**Pydantic Model:**
```python
class ContainerAssignmentCheck(BaseModel):
    """User check для привязки к проекту/области"""

    status: Literal["pending", "confirmed", "created"]

    action: Literal["create_new", "link_existing", "skip"]

    container_type: Literal["Project", "Area", "Resource"]
    container_id: str  # UUID созданного/выбранного контейнера
    container_name: str

    # Если create_new
    created_new: bool = False
    container_metadata: Optional[dict] = None  # deadline, goal и т.д.

    timestamp: datetime = Field(default_factory=datetime.utcnow)
```

**Пример (создание нового проекта):**
```json
{
    "status": "created",
    "action": "create_new",
    "container_type": "Project",
    "container_id": "proj_new_123",
    "container_name": "Q4 Marketing Campaign 2024",
    "created_new": true,
    "container_metadata": {
        "deadline": "2024-12-31",
        "goal": "Increase signups by 20%"
    },
    "timestamp": "2025-11-17T12:02:00Z"
}
```

**Пример (выбор существующего):**
```json
{
    "status": "confirmed",
    "action": "link_existing",
    "container_type": "Project",
    "container_id": "proj_existing_456",
    "container_name": "Marketing Strategy 2024",
    "created_new": false,
    "timestamp": "2025-11-17T12:02:00Z"
}
```

---

## 7. Приоритизация сущностей

### Entity Priority Weights

```python
ENTITY_PRIORITY = {
    'Project': 1,      # Высший приоритет - PARA структура
    'Area': 1,
    'Resource': 1,
    'Person': 2,       # Важные сущности
    'Organization': 2,
    'Decision': 3,     # Средний приоритет
    'Task': 3,
    'Idea': 4,         # Низкий приоритет - можно пропустить
    'Source': 4,
    'Question': 5      # Самый низкий приоритет
}
```

### Auto-confirm Logic

```python
def should_auto_confirm(entity_type: str, confidence: float) -> bool:
    """Определяет, нужно ли автоматически подтвердить сущность"""

    priority = ENTITY_PRIORITY.get(entity_type, 5)

    # Очень высокая уверенность + низкий приоритет
    if confidence > 0.95 and priority >= 4:
        return True

    # Высокая уверенность + средний приоритет
    if confidence > 0.90 and priority >= 3:
        return True

    return False
```

---

## Сводная таблица моделей

| Модель | Где хранится | Назначение | Связи |
|--------|--------------|------------|-------|
| **UserCheckStatus** | Отдельная нода | Событие подтверждения пользователя | `[:HAS_CHECK]`, `[:NEXT]` |
| **FieldModification** | JSON в UserCheckStatus | Изменение поля сущности | — |
| **Project/Area/Resource** | Отдельные ноды | PARA контейнеры | `[:IS_PART_OF]` |
| **EntityNode** | Существующая нода | Извлеченная сущность | `[:HAS_CHECK]` |
| **Note** | Существующая нода | Заметка из Obsidian | `[:IS_PART_OF]`, `[:HAS_CHECK]` |
| **PARAClassificationCheck** | Pydantic (в коде) | Для L1 workflow | — |
| **ContainerAssignmentCheck** | Pydantic (в коде) | Для L2 workflow | — |

---

**Следующий документ:** [03_GRAPH_SCHEMA.md](./03_GRAPH_SCHEMA.md)
