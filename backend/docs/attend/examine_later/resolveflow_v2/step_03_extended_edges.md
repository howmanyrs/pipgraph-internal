# Этап 3: Расширение Edge Types для PARA

**Цель**: Создать полный набор типизированных связей (edge types) между PARA-сущностями и базовыми entity types.

**Время**: 1-2 дня
**Контекст**: [04_EDGE_ENRICHMENT.md](../resolveflow/04_EDGE_ENRICHMENT.md), [step_02_episodic_integration.md](./step_02_episodic_integration.md)

---

## Принятые Решения

### 1. Семантическая специфичность

Приоритет конкретных типов связей (`ASSIGNED_TO`, `CONTRIBUTES_TO`) над общими (`RELATES_TO`, `MENTIONS`).

### 2. Двунаправленность связей

Для каждой семантической связи создаем reverse edge type:
- `(Person) -[:WORKS_ON]-> (Project)`
- `(Project) -[:ASSIGNED_TO]-> (Person)` (обратная перспектива)

### 3. PARA-контекстные связи

Разные PARA типы используют разные edge types в зависимости от семантики.

---

## Шаги Реализации

### Шаг 3.1: Создать Pydantic модели для новых edge types

**Файл**: `backend/config/para_config.py`

**Добавить в начало файла** (после существующих импортов):

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
```

**Добавить модели edge types** (после существующих PARA entity models):

```python
# ========================================
# PARA Edge Type Models
# ========================================

class ContributesTo(BaseModel):
    """
    Relationship: (Project) -[:CONTRIBUTES_TO]-> (Area)

    Indicates that a project contributes to or advances goals within a specific area.
    """
    impact_description: Optional[str] = Field(
        None,
        description="How this project contributes to the area."
    )
    completion_date: Optional[datetime] = Field(
        None,
        description="When the project completed its contribution."
    )


class SpawnedFrom(BaseModel):
    """
    Relationship: (Project) -[:SPAWNED_FROM]-> (Area)

    Indicates that a project originated from an area of responsibility.
    """
    reason: Optional[str] = Field(
        None,
        description="Why this project was created from the area."
    )
    created_at: Optional[datetime] = Field(
        None,
        description="When the project was created."
    )


class UsesResource(BaseModel):
    """
    Relationship: (Project|Area) -[:USES]-> (Resource)

    Indicates that a project or area utilizes a resource for reference.
    """
    usage_type: Optional[str] = Field(
        None,
        description="How the resource is used. E.g., 'reference material', 'learning guide'."
    )
    relevance: Optional[str] = Field(
        None,
        description="Why this resource is relevant."
    )


class AssignedTo(BaseModel):
    """
    Relationship: (Project|Area) -[:ASSIGNED_TO]-> (Person)

    Indicates that a person is assigned to work on a project or manage an area.
    """
    role: Optional[str] = Field(
        None,
        description="The person's role. E.g., 'Lead', 'Contributor', 'Reviewer'."
    )
    assigned_at: Optional[datetime] = Field(
        None,
        description="When the assignment was made."
    )


class LeadBy(BaseModel):
    """
    Relationship: (Project|Area) -[:LEAD_BY]-> (Person)

    Indicates that a person leads or is responsible for a project or area.
    Stronger than ASSIGNED_TO - implies ownership.
    """
    start_date: Optional[datetime] = Field(
        None,
        description="When leadership started."
    )


class WorksOn(BaseModel):
    """
    Relationship: (Person) -[:WORKS_ON]-> (Project)

    Inverse of ASSIGNED_TO - person's perspective of project involvement.
    """
    role: Optional[str] = Field(
        None,
        description="What the person does in the project."
    )


class ManagedBy(BaseModel):
    """
    Relationship: (Area) -[:MANAGED_BY]-> (Person)

    Indicates who manages or is responsible for an ongoing area.
    """
    start_date: Optional[datetime] = Field(
        None,
        description="When management started."
    )


class ResponsibleFor(BaseModel):
    """
    Relationship: (Person) -[:RESPONSIBLE_FOR]-> (Area)

    Inverse of MANAGED_BY - person's perspective of area ownership.
    """
    pass


class BelongsTo(BaseModel):
    """
    Relationship: (Task) -[:BELONGS_TO]-> (Project|Area)

    Indicates that a task is part of a project or area.
    """
    status: Optional[str] = Field(
        None,
        description="Task status: 'todo', 'in_progress', 'done'."
    )


class Contains(BaseModel):
    """
    Relationship: (Project|Area) -[:CONTAINS]-> (Task|Decision)

    Indicates that a project or area contains tasks or decisions.
    """
    created_at: Optional[datetime] = Field(
        None,
        description="When task/decision was added."
    )


class PartnersWith(BaseModel):
    """
    Relationship: (Project) -[:PARTNERS_WITH]-> (Organization)

    Indicates organizational partnerships in projects.
    """
    partnership_type: Optional[str] = Field(
        None,
        description="Type: 'vendor', 'client', 'collaborator', 'sponsor'."
    )


class AuthoredBy(BaseModel):
    """
    Relationship: (Resource) -[:AUTHORED_BY]-> (Person|Organization)

    Indicates who created or maintains a resource.
    """
    date: Optional[datetime] = Field(
        None,
        description="When resource was authored."
    )


class References(BaseModel):
    """
    Relationship: (Resource|Project|Area) -[:REFERENCES]-> (Source)

    Indicates external sources cited or referenced.
    """
    reference_type: Optional[str] = Field(
        None,
        description="Type: 'url', 'book', 'paper', 'video', 'documentation'."
    )


class ReferencedBy(BaseModel):
    """
    Relationship: (Source) -[:REFERENCED_BY]-> (Resource)

    Inverse of REFERENCES.
    """
    pass


class DocumentedIn(BaseModel):
    """
    Relationship: (Decision|Idea) -[:DOCUMENTED_IN]-> (Project|Area|Resource)

    Indicates where a decision or idea is documented.
    """
    pass


class Inspired(BaseModel):
    """
    Relationship: (Idea) -[:INSPIRED]-> (Project)

    Indicates that an idea inspired a project.
    """
    pass
```

---

### Шаг 3.2: Создать PARA_EDGE_TYPES_EXTENDED

**Добавить в para_config.py**:

```python
# ========================================
# Extended Edge Types Dictionary
# ========================================

PARA_EDGE_TYPES_EXTENDED: dict[str, type[BaseModel]] = {
    # PARA-specific edges
    "ContributesTo": ContributesTo,
    "SpawnedFrom": SpawnedFrom,
    "UsesResource": UsesResource,

    # Assignment and ownership edges
    "AssignedTo": AssignedTo,
    "LeadBy": LeadBy,
    "WorksOn": WorksOn,
    "ManagedBy": ManagedBy,
    "ResponsibleFor": ResponsibleFor,

    # Task and decision edges
    "BelongsTo": BelongsTo,
    "Contains": Contains,

    # Organization edges
    "PartnersWith": PartnersWith,

    # Authorship and reference edges
    "AuthoredBy": AuthoredBy,
    "References": References,
    "ReferencedBy": ReferencedBy,
    "DocumentedIn": DocumentedIn,
    "Inspired": Inspired,

    # Generic fallback edges (from original PARA_EDGE_TYPES)
    "MENTIONS": BaseModel,  # No attributes
    "RELATES_TO": BaseModel,
    "DependsOn": BaseModel,
    "COLLABORATES_WITH": BaseModel,
    "WORKS_AT": BaseModel,
    "SUPERSEDES": BaseModel,
    "CITES": BaseModel,
    "IMPLEMENTS": BaseModel,
}
```

---

### Шаг 3.3: Создать PARA_EDGE_TYPE_MAP_EXTENDED

**Добавить в para_config.py**:

```python
# ========================================
# Extended Edge Type Map
# ========================================

PARA_EDGE_TYPE_MAP_EXTENDED: dict[tuple[str, str], list[str]] = {
    # ====== PARA ↔ PARA Relationships ======
    ("Project", "Area"): ["ContributesTo", "SpawnedFrom"],
    ("Project", "Resource"): ["UsesResource"],
    ("Project", "Project"): ["RELATES_TO", "DependsOn"],

    ("Area", "Resource"): ["UsesResource"],
    ("Area", "Project"): ["SpawnedFrom"],  # Reverse: Area spawned project
    ("Area", "Area"): ["RELATES_TO"],

    ("Resource", "Resource"): ["RELATES_TO"],

    ("Archive", "Project"): ["RELATES_TO"],
    ("Archive", "Area"): ["RELATES_TO"],
    ("Archive", "Resource"): ["RELATES_TO"],

    # ====== PARA → Entity Relationships ======

    # Project → Entity
    ("Project", "Person"): ["MENTIONS", "AssignedTo", "LeadBy"],
    ("Project", "Organization"): ["MENTIONS", "PartnersWith"],
    ("Project", "Task"): ["Contains"],
    ("Project", "Decision"): ["Contains"],
    ("Project", "Source"): ["References"],
    ("Project", "Idea"): ["Contains", "RELATES_TO"],

    # Area → Entity
    ("Area", "Person"): ["MENTIONS", "ManagedBy"],
    ("Area", "Organization"): ["MENTIONS", "PartnersWith"],
    ("Area", "Task"): ["Contains"],
    ("Area", "Decision"): ["Contains"],
    ("Area", "Source"): ["References"],

    # Resource → Entity
    ("Resource", "Person"): ["MENTIONS", "AuthoredBy"],
    ("Resource", "Organization"): ["MENTIONS", "AuthoredBy"],
    ("Resource", "Source"): ["References"],
    ("Resource", "Idea"): ["Contains"],

    # Archive → Entity
    ("Archive", "Person"): ["MENTIONS"],
    ("Archive", "Organization"): ["MENTIONS"],

    # ====== Entity → PARA Relationships (Reverse) ======

    # Person → PARA
    ("Person", "Project"): ["WorksOn", "LeadBy"],
    ("Person", "Area"): ["ResponsibleFor", "ManagedBy"],
    ("Person", "Resource"): ["AuthoredBy"],

    # Task → PARA
    ("Task", "Project"): ["BelongsTo"],
    ("Task", "Area"): ["BelongsTo"],

    # Organization → PARA
    ("Organization", "Project"): ["PartnersWith"],
    ("Organization", "Resource"): ["AuthoredBy"],

    # Source → PARA
    ("Source", "Resource"): ["ReferencedBy"],

    # Decision → PARA
    ("Decision", "Project"): ["DocumentedIn"],
    ("Decision", "Area"): ["DocumentedIn"],

    # Idea → PARA
    ("Idea", "Project"): ["Inspired"],
    ("Idea", "Resource"): ["DocumentedIn"],

    # ====== Entity ↔ Entity Relationships (Non-PARA) ======

    ("Person", "Person"): ["MENTIONS", "COLLABORATES_WITH"],
    ("Person", "Organization"): ["WORKS_AT", "MENTIONS"],
    ("Person", "Task"): ["AssignedTo", "MENTIONS"],

    ("Task", "Task"): ["DependsOn", "RELATES_TO"],
    ("Task", "Decision"): ["IMPLEMENTS"],

    ("Organization", "Organization"): ["PartnersWith", "MENTIONS"],

    ("Decision", "Decision"): ["SUPERSEDES", "RELATES_TO"],

    ("Source", "Source"): ["CITES", "RELATES_TO"],

    # ====== Fallback for Unknown Combinations ======
    ("Entity", "Entity"): ["RELATES_TO", "MENTIONS"],
}
```

---

### Шаг 3.4: Создать функцию для выбора правильного edge type map

**Добавить в para_config.py**:

```python
def get_para_edge_types(extended: bool = True) -> dict[str, type[BaseModel]]:
    """
    Get PARA edge types dictionary.

    Args:
        extended: If True, return extended version with all PARA↔Entity types.
                 If False, return basic PARA-only types.

    Returns:
        Dictionary mapping edge type name to Pydantic model
    """
    if extended:
        return PARA_EDGE_TYPES_EXTENDED
    else:
        return PARA_EDGE_TYPES  # Original version


def get_para_edge_type_map(extended: bool = True) -> dict[tuple[str, str], list[str]]:
    """
    Get PARA edge type map.

    Args:
        extended: If True, return extended version with all PARA↔Entity mappings.
                 If False, return basic PARA-only map.

    Returns:
        Dictionary mapping (source_type, target_type) to list of edge type names
    """
    if extended:
        return PARA_EDGE_TYPE_MAP_EXTENDED
    else:
        return PARA_EDGE_TYPE_MAP  # Original version
```

---

### Шаг 3.5: Обновить импорт в pipgraph_manager.py

**Файл**: `backend/app/services/pipgraph_manager.py`

**Найти** (примерно где используются PARA_EDGE_TYPES):

**БЫЛО**:
```python
from config.para_config import PARA_EDGE_TYPES, PARA_EDGE_TYPE_MAP
```

**СТАЛО**:
```python
from config.para_config import (
    get_para_edge_types,
    get_para_edge_type_map,
)
```

---

### Шаг 3.6: Использовать расширенные версии в process_note()

**Файл**: `backend/app/services/pipgraph_manager.py`

**Найти** в методе `process_note()`:

**БЫЛО**:
```python
if use_para_entities:
    if edge_types is None:
        edge_types = PARA_EDGE_TYPES
        logger.info("Using PARA edge types")

    if edge_type_map is None:
        edge_type_map = PARA_EDGE_TYPE_MAP
        logger.info("Using PARA edge type map")
```

**СТАЛО**:
```python
if use_para_entities:
    # Используем расширенные версии при ранней классификации
    use_extended = enable_early_para_classification

    if edge_types is None:
        edge_types = get_para_edge_types(extended=use_extended)
        logger.info(f"Using {'extended' if use_extended else 'basic'} PARA edge types")

    if edge_type_map is None:
        edge_type_map = get_para_edge_type_map(extended=use_extended)
        logger.info(f"Using {'extended' if use_extended else 'basic'} PARA edge type map")
```

---

## Визуализация Связей

После реализации, граф будет содержать семантически богатые связи:

### Для Project Notes:
```
(Project:Q4_Campaign)
    -[:LeadBy {role: "PM"}]-> (Person:Sarah_Johnson)
    -[:AssignedTo {role: "Engineer"}]-> (Person:John_Doe)
    -[:Contains]-> (Task:Design_UI)
    -[:ContributesTo {impact: "Increases revenue"}]-> (Area:Revenue_Growth)
    -[:UsesResource {usage_type: "reference"}]-> (Resource:API_Best_Practices)
```

### Для Area Notes:
```
(Area:Team_Management)
    -[:ManagedBy]-> (Person:Sarah_Johnson)
    -[:SpawnedFrom]-> (Project:Team_Building_Initiative)
    -[:Contains]-> (Task:Weekly_1on1s)
    -[:UsesResource]-> (Resource:Management_Playbook)
```

### Для Resource Notes:
```
(Resource:Python_Async_Guide)
    -[:AuthoredBy {date: "2024-01-15"}]-> (Person:John_Doe)
    -[:References {type: "documentation"}]-> (Source:Python_Docs)
    -[:Contains]-> (Idea:Async_Best_Practice)
```

---

## Проверка Реализации

После реализации должно работать:

1. ✅ Все новые Pydantic модели edge types созданы
2. ✅ `PARA_EDGE_TYPES_EXTENDED` содержит все типы связей
3. ✅ `PARA_EDGE_TYPE_MAP_EXTENDED` покрывает все комбинации PARA↔Entity
4. ✅ Функции `get_para_edge_types()` и `get_para_edge_type_map()` возвращают правильные версии
5. ✅ `pipgraph_manager.py` использует расширенные версии при `enable_early_para_classification=True`
6. ✅ Fallback `("Entity", "Entity")` доступен для неизвестных комбинаций

---

## Пример Использования

```python
# В pipgraph_manager.py, при вызове extract_edges:

extracted_edges = await extract_edges(
    self.clients,
    episode,
    extracted_nodes,
    previous_episodes,
    edge_type_map=get_para_edge_type_map(extended=True),  # ← Расширенная версия
    group_id=group_id,
    edge_types=get_para_edge_types(extended=True),  # ← Расширенная версия
)
```

---

## Следующий Этап

См. [step_04_edge_context_injection.md](./step_04_edge_context_injection.md) для внедрения PARA-контекста в процесс извлечения связей.
