# Этап 4: Внедрение PARA Контекста в Extract Edges

**Цель**: Передать информацию о PARA-типе заметки в процесс извлечения связей, чтобы LLM создавала семантически правильные edge types.

**Время**: 1 день

---

## Обзор

После классификации заметки (Этап 3), мы знаем её PARA-тип (Project/Area/Resource/Archive). На этом этапе мы используем эту информацию для обогащения извлечения связей:

1. Создаём специфичные для каждого PARA-типа инструкции для LLM
2. Внедряем эти инструкции в процесс `extract_edges`
3. LLM создаёт более точные typed edges вместо generic `MENTIONS`/`RELATES_TO`

**Принятое решение**: Используем локальную копию `extract_edges` из graphiti с поддержкой `custom_prompt` параметра.

---

## Принципы Дизайна Edge Types

### 1. Семантическая Специфичность

**Плохо**: Все связи = `RELATES_TO`
**Хорошо**: Конкретные типы (`AssignedTo`, `ContributesTo`, `UsesResource`)

**Обоснование**: Specific edge types позволяют:
- Точнее отвечать на вопросы ("Кто работает над этим проектом?")
- Строить более осмысленные запросы
- Визуализировать граф с цветом по типу связи

### 2. PARA-Контекстность

Разные PARA типы требуют разных edge types:

- **Project edges**: Фокус на исполнении (`AssignedTo`, `Contains` tasks, `UsesResource`)
- **Area edges**: Фокус на управлении (`ManagedBy`, `SpawnedFrom` projects)
- **Resource edges**: Фокус на справке (`AuthoredBy`, `References`)

---

## Шаг 4.1: Создать модуль para_edge_prompts.py

**Файл**: `backend/app/services/para_edge_prompts.py` (NEW)

Этот модуль генерирует кастомные инструкции для LLM на основе PARA-типа заметки.

```python
"""
PARA-specific edge extraction prompt builders.

Generates custom instructions for LLM based on PARA type classification.
These instructions guide the LLM to prioritize semantically appropriate
edge types when extracting relationships from notes.
"""

from typing import Optional


def build_para_edge_instructions(para_type: Optional[str]) -> str:
    """
    Build custom prompt instructions for edge extraction based on PARA type.

    Args:
        para_type: "Project" | "Area" | "Resource" | "Archive" | None

    Returns:
        Custom instruction string to prepend to extract_edges prompt.
        Empty string if para_type is None.
    """

    if para_type == "Project":
        return _project_edge_instructions()
    elif para_type == "Area":
        return _area_edge_instructions()
    elif para_type == "Resource":
        return _resource_edge_instructions()
    elif para_type == "Archive":
        return _archive_edge_instructions()
    else:
        return ""  # No special instructions for unclassified notes


def _project_edge_instructions() -> str:
    """Instructions for extracting edges from Project notes."""
    return """
PARA CLASSIFICATION CONTEXT: This note is a PROJECT (time-bound initiative with specific goal).

When extracting relationships, PRIORITIZE these edge types:

1. **Person Assignment** (AssignedTo, LeadBy):
   - Look for: "assigned to John", "owned by Sarah", "PM: Alex", "lead: Maria"
   - Use LeadBy for leaders/owners/project managers
   - Use AssignedTo for contributors/team members

2. **Task Containment** (Contains):
   - Look for: checkbox items, action items, milestones, todos
   - Create Contains edges from this project to tasks mentioned

3. **Area Connection** (ContributesTo, SpawnedFrom):
   - Look for: "supports X area", "contributes to Y", "spawned from Z domain"
   - ContributesTo when project advances an area's goal
   - SpawnedFrom when project originated from an area

4. **Resource Usage** (UsesResource):
   - Look for: references to guides, documentation, best practices, tutorials
   - Phrases like "using X as reference", "following Y guide", "based on Z"

5. **Organization Partners** (PartnersWith):
   - Look for: external vendors, clients, collaborators, sponsors

6. **Decisions and Ideas** (Contains):
   - Look for: "Decided:", "Resolution:", key decisions, important insights

**AVOID generic MENTIONS/RELATES_TO when specific typed edges apply.**
"""


def _area_edge_instructions() -> str:
    """Instructions for extracting edges from Area notes."""
    return """
PARA CLASSIFICATION CONTEXT: This note is an AREA (ongoing responsibility without endpoint).

When extracting relationships, PRIORITIZE these edge types:

1. **Ownership** (ManagedBy):
   - Look for: "managed by", "area owner:", "responsible:", "DRI:"
   - Link to the person managing this area

2. **Project Spawning** (SpawnedFrom - reverse direction):
   - Look for: projects that originated from this area
   - Phrases like "created project X to address Y", "spawned initiative Z"

3. **Resource Standards** (UsesResource):
   - Look for: SOPs, guidelines, knowledge base docs, playbooks
   - Phrases like "following X guidelines", "based on Y standards"

4. **Ongoing Tasks** (Contains):
   - Look for: recurring tasks, regular duties, continuous responsibilities
   - Checkboxes representing ongoing work (not one-time tasks)

5. **Decision Documentation** (Contains):
   - Look for: standards and best practices documented
   - How things should be done in this area

**AVOID generic relationships when typed edges apply.**
"""


def _resource_edge_instructions() -> str:
    """Instructions for extracting edges from Resource notes."""
    return """
PARA CLASSIFICATION CONTEXT: This note is a RESOURCE (reference material, no action required).

When extracting relationships, PRIORITIZE these edge types:

1. **Authorship** (AuthoredBy):
   - Look for: "written by", "created by", "maintained by", "author:"
   - Link to authors (people or organizations)

2. **External References** (References):
   - Look for: URLs, book citations, paper references, video links
   - Phrases like "source:", "based on:", "see:", hyperlinks

3. **Idea Documentation** (Contains):
   - Look for: key concepts explained in this resource
   - Important insights, principles, frameworks documented

4. **Related Resources** (RELATES_TO):
   - Look for: links to other learning materials
   - Phrases like "see also:", "related topics:", "similar to:"

**FOCUS on attribution (AuthoredBy) and citation (References) relationships.**
"""


def _archive_edge_instructions() -> str:
    """Instructions for extracting edges from Archive notes."""
    return """
PARA CLASSIFICATION CONTEXT: This note is ARCHIVED (completed/inactive).

When extracting relationships, focus on:

1. **Historical Context** (RELATES_TO):
   - What this archived item relates to
   - Learnings that apply to current projects/areas

2. **Outcome Documentation**:
   - Final results, lessons learned
   - People involved in completion (MENTIONS)

**Most edges will be generic (MENTIONS, RELATES_TO) since this is historical content.**
"""
```

---

## Шаг 4.2: Создать локальную версию extract_edges

**Файл**: `backend/app/services/local_extract_edges.py` (NEW)

Это wrapper-функция, которая использует оригинальную `extract_edges` из graphiti, но модифицирует `episode.content` для внедрения кастомных инструкций.

```python
"""
Local wrapper for graphiti's extract_edges function with custom_prompt support.

This wrapper modifies episode content to inject PARA-specific edge extraction
context, avoiding the need to modify graphiti's internal API.
"""

from typing import Any
from graphiti_core.nodes import EpisodicNode, EntityNode
from graphiti_core.edges import EntityEdge, extract_edges
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)


async def extract_edges_with_context(
    clients: Any,  # GraphitiClients
    episode: EpisodicNode,
    nodes: list[EntityNode],
    previous_episodes: list[EpisodicNode],
    edge_type_map: dict[tuple[str, str], list[str]],
    group_id: str,
    edge_types: dict[str, type[BaseModel]],
    custom_prompt: str = "",  # ← NEW parameter
) -> list[EntityEdge]:
    """
    Extract edges between entities with optional custom prompt context.

    This is a wrapper around graphiti's extract_edges that accepts
    a custom_prompt parameter for PARA-specific instructions.

    Args:
        clients: GraphitiClients instance
        episode: The episode node containing the note content
        nodes: List of extracted entity nodes
        previous_episodes: List of previous episodes for context
        edge_type_map: Mapping of (source_type, target_type) to edge types
        group_id: Group ID for the episode
        edge_types: Dictionary of edge type models
        custom_prompt: Optional custom instructions for LLM (e.g., PARA context)

    Returns:
        List of extracted EntityEdge objects
    """

    # If custom_prompt is provided, inject it into episode content
    if custom_prompt:
        logger.debug("Injecting custom PARA prompt into episode content")

        # Create a modified episode with custom prompt prepended
        modified_episode = EpisodicNode(
            **episode.model_dump(exclude={"content"}),
            content=f"{custom_prompt}\n\n===== NOTE CONTENT =====\n\n{episode.content}"
        )

        # Call graphiti's extract_edges with modified episode
        return await extract_edges(
            clients,
            modified_episode,  # ← Modified with custom prompt
            nodes,
            previous_episodes,
            edge_type_map,
            group_id,
            edge_types,
        )
    else:
        # No custom prompt, use original function
        return await extract_edges(
            clients,
            episode,
            nodes,
            previous_episodes,
            edge_type_map,
            group_id,
            edge_types,
        )
```

**Примечание**: Это wrapper, который использует оригинальную функцию из graphiti, но модифицирует `episode.content` для внедрения кастомных инструкций. Это более чистое решение, чем полное копирование функции.

---

## Шаг 4.3: Интегрировать в pipgraph_manager.py

**Файл**: `backend/app/services/pipgraph_manager.py`

### Добавить импорты

В начало файла добавить:

```python
from app.services.local_extract_edges import extract_edges_with_context
from app.services.para_edge_prompts import build_para_edge_instructions
```

### Модифицировать вызов extract_edges

Найти вызов `extract_edges` (примерно строки 280-290) и заменить:

**БЫЛО**:
```python
from graphiti_core.edges import extract_edges

# ...

extracted_edges = await extract_edges(
    self.clients,
    episode,
    extracted_nodes,
    previous_episodes,
    edge_type_map,
    group_id,
    edge_types,
)
```

**СТАЛО**:
```python
# Build PARA-specific context if note is classified
para_context = ""
if para_type:
    para_context = build_para_edge_instructions(para_type)
    logger.debug(f"Using PARA context for edge extraction: {para_type}")

# Extract edges with PARA context
extracted_edges = await extract_edges_with_context(
    self.clients,
    episode,
    extracted_nodes,
    previous_episodes,
    edge_type_map,
    group_id,
    edge_types,
    custom_prompt=para_context,  # ← NEW parameter
)
```

**Где взять `para_type`**: Эта переменная должна быть получена из Этапа 3 (классификация), который выполняется перед извлечением связей в методе `process_note()`.

---

## Пример Работы

### Для Project Note

**Input**:
```
Note: "Q4 Campaign"
Classification: Project
Content: "Launch product by Dec 31. PM: Sarah Johnson. Tasks: - Design UI (John)"
```

**PARA Context** (автоматически добавляется):
```
PARA CLASSIFICATION CONTEXT: This note is a PROJECT...

PRIORITIZE these edge types:
1. Person Assignment (AssignedTo, LeadBy)
2. Task Containment (Contains)
...
```

**Результат** (extracted edges):
```python
[
    EntityEdge(name="LeadBy", source="Project:Q4_Campaign", target="Person:Sarah_Johnson"),
    EntityEdge(name="AssignedTo", source="Project:Q4_Campaign", target="Person:John"),
    EntityEdge(name="Contains", source="Project:Q4_Campaign", target="Task:Design_UI"),
]
```

Вместо общих:
```python
[
    EntityEdge(name="MENTIONS", source="...", target="..."),
    EntityEdge(name="RELATES_TO", source="...", target="..."),
]
```

---

## Проверка Реализации

После реализации должно работать:

1. ✅ Модуль `para_edge_prompts.py` создан с инструкциями для каждого PARA типа
2. ✅ Модуль `local_extract_edges.py` создан с wrapper для extract_edges
3. ✅ Параметр `custom_prompt` добавлен и используется
4. ✅ PARA контекст автоматически внедряется при `para_type != None`
5. ✅ LLM получает специфичные инструкции для Project/Area/Resource/Archive
6. ✅ Извлеченные edges имеют семантически правильные типы

---

## Мониторинг Эффективности

После внедрения, следует отслеживать:

**Edge Type Distribution**:
```python
# В логах после extract_edges
edge_type_counts = {}
for edge in extracted_edges:
    edge_type_counts[edge.name] = edge_type_counts.get(edge.name, 0) + 1

logger.info(f"Edge types extracted: {edge_type_counts}")
# Example output: {"LeadBy": 1, "AssignedTo": 2, "Contains": 3, "MENTIONS": 1}
```

**Target**: ≥60% typed edges (не `RELATES_TO`/`MENTIONS`)

---

## Связь с Другими Этапами

**Входные данные**:
- `para_type` (str | None) - из Этапа 3 (классификация заметки)
- `episode` (EpisodicNode) - эпизод с классифицированной заметкой
- `extracted_nodes` - сущности, извлечённые из заметки

**Выходные данные**:
- `extracted_edges` - список связей с правильными typed edges

**Следующий этап**: См. [step_05_documentation.md](step_05_documentation.md) для обновления документации.

---

## Примеры Извлечения Связей

### Пример 1: Project Note с Assignments

**Input Note** (после классификации как Project):
```markdown
# Q4 Product Launch

**PM**: Sarah Johnson
**Engineers**: John Doe, Alex Smith
**Deadline**: 2024-12-31

## Tasks
- [ ] Complete API design (assigned to John)
- [ ] Frontend implementation (assigned to Alex)
- [ ] QA testing (assigned to Sarah)

## References
Using our API Design Guidelines (see Resource note: API Best Practices)
```

**Expected Edges**:
```python
[
    EntityEdge(
        name="LeadBy",
        source="Project:Q4_Product_Launch",
        target="Person:Sarah_Johnson",
        attributes={"role": "PM"}
    ),
    EntityEdge(
        name="AssignedTo",
        source="Project:Q4_Product_Launch",
        target="Person:John_Doe",
        attributes={"role": "Engineer"}
    ),
    EntityEdge(
        name="AssignedTo",
        source="Project:Q4_Product_Launch",
        target="Person:Alex_Smith",
        attributes={"role": "Engineer"}
    ),
    EntityEdge(
        name="Contains",
        source="Project:Q4_Product_Launch",
        target="Task:Complete_API_design",
        attributes={}
    ),
    EntityEdge(
        name="UsesResource",
        source="Project:Q4_Product_Launch",
        target="Resource:API_Best_Practices",
        attributes={"usage_type": "reference material"}
    ),
]
```

### Пример 2: Area Note с Management

**Input Note** (после классификации как Area):
```markdown
# Engineering Team Management

**Area Owner**: Sarah Johnson
**Review**: Weekly 1-on-1s every Monday

## Ongoing Responsibilities
- Conduct 1-on-1s with all team members
- Remove blockers
- Foster team culture

## Related Projects
- Q4 Product Launch (spawned from this area)
- Code Quality Improvement Initiative

## Standards
Using our Team Management Playbook (see Resource: Management Best Practices)
```

**Expected Edges**:
```python
[
    EntityEdge(
        name="ManagedBy",
        source="Area:Engineering_Team_Management",
        target="Person:Sarah_Johnson",
        attributes={}
    ),
    EntityEdge(
        name="SpawnedFrom",
        source="Project:Q4_Product_Launch",
        target="Area:Engineering_Team_Management",
        attributes={"reason": "Spawned from team area"}
    ),
    EntityEdge(
        name="UsesResource",
        source="Area:Engineering_Team_Management",
        target="Resource:Management_Best_Practices",
        attributes={"usage_type": "standard operating procedure"}
    ),
    EntityEdge(
        name="Contains",
        source="Area:Engineering_Team_Management",
        target="Task:Conduct_1on1s",
        attributes={}
    ),
]
```

---

## Метрики Успеха

После имплементации измеряем:

1. **Edge Type Distribution**:
   - До: 80% `RELATES_TO`, 15% `MENTIONS`, 5% other
   - После: 40% typed PARA edges, 30% `RELATES_TO`, 30% other

2. **Semantic Richness Score**:
   - Доля связей с специфичным типом (не `RELATES_TO`/`MENTIONS`)
   - Target: ≥ 60%

3. **Query Expressiveness**:
   - Можем ответить на вопросы типа "Who works on Project X?" → LeadBy/AssignedTo
   - Можем найти "All tasks in Project Y" → Contains
   - Можем найти "Resources used by Area Z" → UsesResource
