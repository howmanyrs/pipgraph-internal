# Graphiti Communities FAQ - Часто задаваемые вопросы

> **Дата создания**: 2025-10-22
> **Версия Graphiti**: 0.3.x
> **Контекст**: Ответы на вопросы о построении communities, labels и entity_types

---

## Вопрос 1: Нужны ли Labels у сущностей для построения communities?

### Короткий ответ

**❌ НЕТ, дополнительные labels НЕ нужны для построения communities!**

Communities строятся **только на основе топологии графа** (связей `RELATES_TO`), а не на основе семантики labels.

---

### Доказательство из кода

#### Функция `get_community_clusters()`

**Файл**: `graphiti_core/utils/maintenance/community_operations.py:29-83`

**Cypher-запрос для поиска кластеров**:
```cypher
MATCH (n:Entity {group_id: $group_id, uuid: $uuid})
      -[e:RELATES_TO]-
      (m:Entity {group_id: $group_id})
WITH count(e) AS count, m.uuid AS uuid
RETURN uuid, count
```

**Критерии кластеризации:**
- ✅ Наличие базового label `:Entity` (есть у всех EntityNode)
- ✅ Совпадение `group_id` (для изоляции графов разных пользователей)
- ✅ Наличие связей `RELATES_TO` между узлами
- ❌ **НЕ используются** дополнительные labels (`:Person`, `:Project`, `:Tool`, etc.)

---

#### Алгоритм Label Propagation

**Файл**: `graphiti_core/utils/maintenance/community_operations.py:86-131`

**Критическая часть**:
```python
def label_propagation(projection: dict[str, list[Neighbor]]) -> list[list[str]]:
    # projection = {uuid: [Neighbor(node_uuid, edge_count), ...]}

    community_map = {uuid: i for i, uuid in enumerate(projection.keys())}

    while True:
        for uuid, neighbors in projection.items():
            # Подсчитываем вес каждого community-кандидата
            community_candidates: dict[int, int] = defaultdict(int)
            for neighbor in neighbors:
                # ← Используется только edge_count, НЕ labels!
                community_candidates[community_map[neighbor.node_uuid]] += neighbor.edge_count

            # Выбираем community с максимальным весом
            # ...
```

**Алгоритм работает на:**
- ✅ Топология графа (какие узлы связаны)
- ✅ Вес связей (количество рёбер `edge_count`)
- ❌ **НЕ использует** neo4j labels узлов

---

### Пример

**Граф с разными labels:**

```cypher
(:Entity:Person {name: "Alice", group_id: "default"})-[:RELATES_TO]->(:Entity:Project {name: "ProjectX"})
(:Entity:Person {name: "Bob", group_id: "default"})-[:RELATES_TO]->(:Entity:Project {name: "ProjectX"})
(:Entity:Tool {name: "FastAPI", group_id: "default"})-[:RELATES_TO]->(:Entity:Project {name: "ProjectX"})
```

**Результат `build_communities()`:**

Все три узла будут в **одном community**, потому что они связаны через ProjectX, независимо от того, что у них разные labels (Person, Project, Tool).

---

### Вывод

**Communities зависят ТОЛЬКО от:**
1. Структуры графа (кто с кем связан через `RELATES_TO`)
2. `group_id` (для изоляции графов)

**Communities НЕ зависят от:**
1. Дополнительных labels (Person, Project, etc.)
2. Атрибутов узлов (name, summary, attributes)
3. Типов связей (все `RELATES_TO` равнозначны)

---

## Вопрос 2: Нужно ли указывать entity_types заранее?

### Короткий ответ

**⚠️ Зависит от вашей задачи:**
- **Без entity_types**: Все сущности будут иметь label `:Entity` (работает для communities)
- **С entity_types**: Сущности получат дополнительные labels (`:Person`, `:Project`) для лучшей структуризации

---

### Вариант A: БЕЗ entity_types (по умолчанию)

**Код**:
```python
result = await pipgraph.process_note(
    name="note.md",
    episode_body="Vladimir Ivanov discussed FastAPI and Obsidian",
    source_description="Obsidian note",
    reference_time=datetime.now(timezone.utc),
    # entity_types=None  ← НЕ указываем
)
```

**Что происходит:**

1. **Извлечение сущностей** (`extract_nodes.py:163-191`):
```python
# Промпт для LLM (extract_text):
"""
<ENTITY TYPES>
[
  {
    "entity_type_id": 0,
    "entity_type_name": "Entity",
    "entity_type_description": "Default entity classification."
  }
]
</ENTITY TYPES>

<TEXT>
Vladimir Ivanov discussed FastAPI and Obsidian
</TEXT>

Extract entities from the TEXT...
"""
```

2. **Создание узлов** (`node_operations.py:152-181`):
```python
for extracted_entity in filtered_extracted_entities:
    entity_type_name = 'Entity'  # ← Всегда Entity по умолчанию

    labels: list[str] = list({'Entity', str(entity_type_name)})
    # labels = ['Entity']  ← Только один label

    new_node = EntityNode(
        name=extracted_entity.name,
        group_id=episode.group_id,
        labels=labels,  # ['Entity']
        summary='',
        created_at=utc_now(),
    )
```

3. **Результат в Neo4j**:
```cypher
(:Entity {name: "Vladimir Ivanov", summary: "..."})
(:Entity {name: "FastAPI", summary: "..."})
(:Entity {name: "Obsidian", summary: "..."})
```

**Плюсы:**
- ✅ Работает из коробки (без настройки)
- ✅ Communities строятся корректно
- ✅ Меньше кода и конфигурации

**Минусы:**
- ❌ Нет семантической типизации (все просто Entity)
- ❌ Сложнее фильтровать в Neo4j: `MATCH (n:Entity WHERE n.name CONTAINS 'Project')`
- ❌ Нет структурированных атрибутов

---

### Вариант B: С entity_types (рекомендуется)

**Определение типов**:
```python
from pydantic import BaseModel, Field

class Person(BaseModel):
    """A person mentioned in the note"""
    full_name: str = Field(description="Full name of the person")
    role: str | None = Field(default=None, description="Role or occupation")

class Project(BaseModel):
    """A software project or library"""
    name: str = Field(description="Project name")
    tech_stack: str | None = Field(default=None, description="Technologies used")

class Tool(BaseModel):
    """A software tool or framework"""
    name: str = Field(description="Tool name")
```

**Код**:
```python
result = await pipgraph.process_note(
    name="note.md",
    episode_body="Vladimir Ivanov discussed FastAPI and Obsidian",
    source_description="Obsidian note",
    reference_time=datetime.now(timezone.utc),
    entity_types={
        "Person": Person,
        "Project": Project,
        "Tool": Tool,
    }
)
```

**Что происходит:**

1. **Извлечение с классификацией** (`extract_nodes.py:163-191`):
```python
# Промпт для LLM:
"""
<ENTITY TYPES>
[
  {"entity_type_id": 0, "entity_type_name": "Entity", "entity_type_description": "Default..."},
  {"entity_type_id": 1, "entity_type_name": "Person", "entity_type_description": "A person mentioned in the note"},
  {"entity_type_id": 2, "entity_type_name": "Project", "entity_type_description": "A software project..."},
  {"entity_type_id": 3, "entity_type_name": "Tool", "entity_type_description": "A software tool..."}
]
</ENTITY TYPES>

Extract entities and classify them by entity_type_id...
"""
```

2. **Создание узлов с типами** (`node_operations.py:152-181`):
```python
for extracted_entity in filtered_extracted_entities:
    type_id = extracted_entity.entity_type_id  # LLM выбрал 1 (Person)
    entity_type_name = entity_types_context[type_id]['entity_type_name']  # "Person"

    labels: list[str] = list({'Entity', str(entity_type_name)})
    # labels = ['Entity', 'Person']  ← Два labels!

    new_node = EntityNode(
        name=extracted_entity.name,
        group_id=episode.group_id,
        labels=labels,  # ['Entity', 'Person']
        summary='',
        created_at=utc_now(),
    )
```

3. **Извлечение атрибутов** (`extract_attributes_from_nodes()`):
```python
# LLM извлекает структурированные данные согласно Pydantic модели
# Person.full_name = "Vladimir Ivanov"
# Person.role = "Developer"
```

4. **Результат в Neo4j**:
```cypher
(:Entity:Person {
  name: "Vladimir Ivanov",
  summary: "...",
  attributes: {full_name: "Vladimir Ivanov", role: "Developer"}
})

(:Entity:Tool {
  name: "FastAPI",
  summary: "...",
  attributes: {name: "FastAPI"}
})

(:Entity:Tool {
  name: "Obsidian",
  summary: "...",
  attributes: {name: "Obsidian"}
})
```

**Плюсы:**
- ✅ Семантическая типизация (можно различать людей, проекты, инструменты)
- ✅ Удобная фильтрация в Neo4j: `MATCH (p:Person)` вместо `MATCH (n:Entity WHERE ...)`
- ✅ Структурированные атрибуты (full_name, role, tech_stack)
- ✅ Лучше для аналитики и поиска
- ✅ Communities всё равно работают корректно!

**Минусы:**
- ⚠️ Требует определения Pydantic моделей заранее
- ⚠️ Больше LLM-токенов (промпт длиннее)

---

### Рекомендации для PipGraph

**Создайте файл** `backend/app/models/entity_types.py`:

```python
from pydantic import BaseModel, Field

class Person(BaseModel):
    """A person mentioned in notes"""
    pass

class Note(BaseModel):
    """Another Obsidian note referenced (like [[Note Name]])"""
    pass

class Concept(BaseModel):
    """An abstract concept or idea"""
    pass

class Project(BaseModel):
    """A project or initiative"""
    pass

class Tool(BaseModel):
    """A software tool, library, or framework"""
    pass

OBSIDIAN_ENTITY_TYPES = {
    "Person": Person,
    "Note": Note,
    "Concept": Concept,
    "Project": Project,
    "Tool": Tool,
}
```

**Используйте в** `backend/app/services/note_processor.py`:

```python
from app.models.entity_types import OBSIDIAN_ENTITY_TYPES

result = await pipgraph.process_note(
    name=note.file_path,
    episode_body=note.content,
    source=EpisodeType.text,
    source_description=f"Obsidian note from {note.file_path}",
    reference_time=datetime.now(timezone.utc),
    entity_types=OBSIDIAN_ENTITY_TYPES,  # ← Добавить типы
)
```

---

## Вопрос 3: Создаст ли Graphiti мета-теги автоматически из контента?

### Короткий ответ

**❌ НЕТ, Graphiti НЕ создаёт entity_types автоматически!**

Entity types — это **заранее определённая схема** (как Pydantic модели). LLM **классифицирует** сущности по **предоставленным типам**, но НЕ придумывает новые типы.

---

### Механизм работы классификации

**Графити использует подход "closed-world classification":**

```
Шаг 1: Вы определяете схему
entity_types = {"Person": Person, "Project": Project, "Tool": Tool}

Шаг 2: LLM получает промпт со списком типов
<ENTITY TYPES>
[
  {"entity_type_id": 0, "entity_type_name": "Entity"},      ← Fallback
  {"entity_type_id": 1, "entity_type_name": "Person"},
  {"entity_type_id": 2, "entity_type_name": "Project"},
  {"entity_type_id": 3, "entity_type_name": "Tool"}
]
</ENTITY TYPES>

Шаг 3: LLM извлекает сущности и выбирает тип из списка
{
  "extracted_entities": [
    {"name": "Vladimir Ivanov", "entity_type_id": 1},  ← Person
    {"name": "FastAPI", "entity_type_id": 3},          ← Tool
    {"name": "meeting", "entity_type_id": 0}           ← Entity (не подошёл ни один тип)
  ]
}

Шаг 4: Graphiti создаёт узлы с labels
(:Entity:Person {name: "Vladimir Ivanov"})
(:Entity:Tool {name: "FastAPI"})
(:Entity {name: "meeting"})  ← Fallback на базовый Entity
```

---

### Что происходит без entity_types

**Без entity_types** LLM видит **только один тип**:

```python
entity_types_context = [
    {
        'entity_type_id': 0,
        'entity_type_name': 'Entity',
        'entity_type_description': 'Default entity classification.'
    }
]
```

**Результат**: все сущности получают `entity_type_id = 0` → label `:Entity`

---

### Промпт для extract_nodes

**Файл**: `graphiti_core/prompts/extract_nodes.py:163-191`

```python
def extract_text(context: dict[str, Any]) -> list[Message]:
    user_prompt = f"""
<ENTITY TYPES>
{context['entity_types']}  # ← Список предоставленных типов
</ENTITY TYPES>

<TEXT>
{context['episode_content']}
</TEXT>

Given the above text, extract entities from the TEXT...
For each entity extracted, also determine its entity type based on the
provided ENTITY TYPES and their descriptions.
Indicate the classified entity type by providing its entity_type_id.

Guidelines:
1. Extract significant entities, concepts, or actors mentioned in the conversation.
2. Avoid creating nodes for relationships or actions.
3. Be as explicit as possible in your node names, using full names.
"""
```

**Ключевой момент**:
> "determine its entity type **based on the provided ENTITY TYPES**"

LLM **НЕ имеет** инструкции создавать новые типы — только выбирать из предоставленных!

---

### Пример: Что если LLM встречает неизвестный тип?

**Промпт** (classify_nodes.py:218-243):

```python
"""
<ENTITY TYPES>
[
  {"entity_type_id": 0, "entity_type_name": "Entity"},
  {"entity_type_id": 1, "entity_type_name": "Person"}
]
</ENTITY TYPES>

<EXTRACTED ENTITIES>
["Vladimir Ivanov", "FastAPI", "2025-10-22"]
</EXTRACTED ENTITIES>

Guidelines:
1. Each entity must have exactly one type
2. Only use the provided ENTITY TYPES as types
3. If none of the provided entity types accurately classify an extracted node,
   the type should be set to None  # ← Fallback на Entity
"""
```

**Результат**:
```json
{
  "entity_classifications": [
    {"uuid": "...", "name": "Vladimir Ivanov", "entity_type": "Person"},
    {"uuid": "...", "name": "FastAPI", "entity_type": null},  // ← Fallback
    {"uuid": "...", "name": "2025-10-22", "entity_type": null}
  ]
}
```

**В коде** (`node_operations.py:160-168`):

```python
if entity_type_name is None:
    entity_type_name = 'Entity'  # ← Fallback на базовый тип

labels: list[str] = list({'Entity', str(entity_type_name)})
# FastAPI → labels = ['Entity']
# Vladimir Ivanov → labels = ['Entity', 'Person']
```

---

### Если нужны динамические типы

Если вы хотите, чтобы система **сама определяла типы** (например, "Organization", "Location", "Event"), вам нужно:

**Вариант 1: Широкий набор типов заранее**

```python
UNIVERSAL_ENTITY_TYPES = {
    "Person": Person,
    "Organization": Organization,
    "Location": Location,
    "Event": Event,
    "Concept": Concept,
    "Tool": Tool,
    "Document": Document,
    "Product": Product,
    # ... до 20-30 типов
}
```

**Вариант 2: Двухэтапная обработка (custom logic)**

```python
# Этап 1: Обработать без типов
result = await pipgraph.process_note(..., entity_types=None)

# Этап 2: Проанализировать сущности и определить типы
discovered_types = await analyze_entities_and_suggest_types(result.nodes)

# Этап 3: Переклассифицировать сущности
await reclassify_entities(result.nodes, discovered_types)
```

Но это **не встроенная функция Graphiti** — вам придётся реализовать самостоятельно.

---

## Сравнительная таблица подходов

| Критерий | Без entity_types | С entity_types |
|----------|-----------------|----------------|
| **Labels в Neo4j** | `:Entity` | `:Entity:Person`, `:Entity:Project` |
| **Communities** | ✅ Работают | ✅ Работают |
| **Фильтрация в Neo4j** | `MATCH (n:Entity WHERE ...)` | `MATCH (p:Person)` |
| **Структурированные атрибуты** | ❌ Нет | ✅ Да (из Pydantic models) |
| **Аналитика** | Сложнее | Проще |
| **Настройка** | Не требуется | Определить Pydantic модели |
| **LLM токены** | Меньше | Больше (промпт длиннее) |
| **Семантика** | Нет типизации | Чёткая типизация |

---

## Итоговые рекомендации для PipGraph

### 1. Communities будут работать в любом случае

Не важно, используете ли вы entity_types или нет — communities строятся на основе топологии графа (связей `RELATES_TO`), а не на основе labels.

### 2. Рекомендуется использовать entity_types

Для Obsidian-based knowledge graph имеет смысл определить базовые типы:

```python
OBSIDIAN_ENTITY_TYPES = {
    "Person": Person,
    "Note": Note,        # Для [[Note Name]] ссылок
    "Concept": Concept,
    "Project": Project,
    "Tool": Tool,
}
```

**Преимущества:**
- Лучшая структуризация данных
- Удобная фильтрация и поиск
- Возможность добавить custom атрибуты в будущем

### 3. Graphiti не создаёт типы автоматически

Если вы хотите динамическую классификацию, вам нужно:
- Либо определить широкий набор типов заранее
- Либо реализовать custom логику для анализа и переклассификации

---

## Ссылки на исходники

- **Community operations**: `graphiti_core/utils/maintenance/community_operations.py`
- **Node extraction**: `graphiti_core/utils/maintenance/node_operations.py`
- **Extract prompts**: `graphiti_core/prompts/extract_nodes.py`
- **Label propagation**: `community_operations.py:86-131`

---

## Дата документа

Создано: 2025-10-22
Версия Graphiti: 0.3.x
Актуально для: PipGraph backend
