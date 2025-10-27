# Обогащение Связей: Расширенный PARA Edge Type Map

**Дата**: 2025-10-27
**Контекст**: [02_ARCHITECTURE_DECISION.md](./02_ARCHITECTURE_DECISION.md)

---

## Обзор

Этот документ определяет **полный набор типов связей (edge types)** между PARA-сущностями и базовыми entity types. Цель - создать семантически богатый граф, где каждая связь имеет четкий смысл.

---

## Принципы Дизайна Edge Types

### 1. Семантическая Специфичность

**Плохо**: Все связи = `RELATES_TO`
**Хорошо**: Конкретные типы (`ASSIGNED_TO`, `CONTRIBUTES_TO`, `USES`)

**Обоснование**: Specific edge types позволяют:
- Точнее отвечать на вопросы ("Кто работает над этим проектом?")
- Строить более осмысленные запросы
- Визуализировать граф с цветом по типу связи

---

### 2. Двунаправленность

Для каждой семантической связи должен быть reverse edge type.

**Пример**:
- `(Person) -[:WORKS_ON]-> (Project)`
- `(Project) -[:ASSIGNED_TO]-> (Person)`  # Reverse perspective

**Обоснование**: В Neo4j можно запрашивать в обе стороны, но явные типы помогают LLM понимать контекст.

---

### 3. PARA-Контекстность

Разные PARA типы требуют разных edge types.

**Project edges**:
- Фокус на исполнении: `ASSIGNED_TO`, `CONTAINS` (tasks), `USES` (resources)

**Area edges**:
- Фокус на управлении: `MANAGED_BY`, `SPAWNED` (projects), `DEFINES_STANDARDS_FOR`

**Resource edges**:
- Фокус на справке: `AUTHORED_BY`, `REFERENCES`, `USED_BY`

---

### 4. Расширяемость

Структура должна легко принимать новые типы без breaking changes.

**Подход**: Используем fallback `("Entity", "Entity")` для неизвестных комбинаций.

---

## Полный Edge Type Map

### Конфигурация (para_config.py)

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ========================================
# PARA Edge Type Models
# ========================================

class ContributesTo(BaseModel):
    """
    Relationship: (Project) -[:CONTRIBUTES_TO]-> (Area)

    Indicates that a project contributes to or advances goals within a specific area.
    When a project completes, learnings and outcomes flow back to the parent Area.

    LLM Extraction Criteria:
    - Project explicitly states it supports/improves an Area
    - Phrases like "this project contributes to X", "supports the goal of Y"
    - Clear alignment between project goal and area goal
    """
    impact_description: Optional[str] = Field(
        None,
        description="How this project contributes to the area. Extract from phrases like 'supports', 'advances', 'improves'."
    )
    completion_date: Optional[datetime] = Field(
        None,
        description="When the project completed its contribution to the area."
    )


class SpawnedFrom(BaseModel):
    """
    Relationship: (Project) -[:SPAWNED_FROM]-> (Area)

    Indicates that a project originated from an area of responsibility.
    Areas often generate projects to achieve specific goals within that domain.

    LLM Extraction Criteria:
    - Project mentions it was created to address Area need
    - Phrases like "spawned from X area", "created to improve Y"
    - Project goal aligns with Area responsibility
    """
    reason: Optional[str] = Field(
        None,
        description="Why this project was created from the area. Look for: 'needed', 'identified gap', 'opportunity'."
    )
    created_at: Optional[datetime] = Field(
        None,
        description="When the project was created from the area."
    )


class UsesResource(BaseModel):
    """
    Relationship: (Project|Area) -[:USES]-> (Resource)

    Indicates that a project or area utilizes a resource for reference or learning.
    Resources provide knowledge and context for active work.

    LLM Extraction Criteria:
    - Explicit references to guides, tutorials, documentation
    - Phrases like "using X as reference", "following Y guide", "based on Z tutorial"
    - Links or citations to resource notes
    """
    usage_type: Optional[str] = Field(
        None,
        description="How the resource is used. Examples: 'reference material', 'learning guide', 'best practices', 'inspiration'."
    )
    relevance: Optional[str] = Field(
        None,
        description="Why this resource is relevant. Extract specific connections mentioned."
    )


class AssignedTo(BaseModel):
    """
    Relationship: (Project|Area) -[:ASSIGNED_TO]-> (Person)

    Indicates that a person is assigned to work on a project or manage an area.

    LLM Extraction Criteria:
    - Explicit assignment statements: "assigned to John", "owner: Sarah"
    - Mentioned in task lists with names
    - DRI (Directly Responsible Individual) markers
    """
    role: Optional[str] = Field(
        None,
        description="The person's role in the project/area. E.g., 'Lead', 'Contributor', 'Reviewer', 'Owner'."
    )
    assigned_at: Optional[datetime] = Field(
        None,
        description="When the assignment was made."
    )


class LeadBy(BaseModel):
    """
    Relationship: (Project|Area) -[:LEAD_BY]-> (Person)

    Indicates that a person leads or is responsible for a project or area.
    Stronger than ASSIGNED_TO - implies ownership and decision-making authority.

    LLM Extraction Criteria:
    - Phrases like "led by", "project lead", "area owner", "managed by"
    - Title indicators: "PM:", "Tech Lead:", "Owner:"
    """
    start_date: Optional[datetime] = Field(
        None,
        description="When leadership started."
    )


class WorksOn(BaseModel):
    """
    Relationship: (Person) -[:WORKS_ON]-> (Project)

    Inverse of ASSIGNED_TO - person's perspective of project involvement.

    LLM Extraction Criteria:
    - Mentioned as contributor or team member
    - Active participation in project tasks
    """
    role: Optional[str] = Field(
        None,
        description="What the person does in the project."
    )


class ManagedBy(BaseModel):
    """
    Relationship: (Area) -[:MANAGED_BY]-> (Person)

    Indicates who manages or is responsible for an ongoing area.

    LLM Extraction Criteria:
    - Area explicitly states manager or owner
    - Responsibility assignment in area description
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

    LLM Extraction Criteria:
    - Task is listed within project/area note
    - Explicit task-project linkage: "Task for Project X"
    - Checkbox items in project notes
    """
    status: Optional[str] = Field(
        None,
        description="Task status if mentioned: 'todo', 'in_progress', 'done'."
    )


class Contains(BaseModel):
    """
    Relationship: (Project|Area) -[:CONTAINS]-> (Task|Decision)

    Indicates that a project or area contains tasks or decisions.

    LLM Extraction Criteria:
    - Task lists, checkboxes within project notes
    - Decision records explicitly documented
    """
    created_at: Optional[datetime] = Field(
        None,
        description="When task/decision was added."
    )


class PartnersWith(BaseModel):
    """
    Relationship: (Project) -[:PARTNERS_WITH]-> (Organization)

    Indicates organizational partnerships in projects.

    LLM Extraction Criteria:
    - Explicit partnership mentions
    - Collaboration statements with external organizations
    """
    partnership_type: Optional[str] = Field(
        None,
        description="Type of partnership: 'vendor', 'client', 'collaborator', 'sponsor'."
    )


class AuthoredBy(BaseModel):
    """
    Relationship: (Resource) -[:AUTHORED_BY]-> (Person|Organization)

    Indicates who created or maintains a resource.

    LLM Extraction Criteria:
    - Author attribution in resource notes
    - "Written by", "Created by", "Maintained by"
    """
    date: Optional[datetime] = Field(
        None,
        description="When resource was authored."
    )


class References(BaseModel):
    """
    Relationship: (Resource|Project|Area) -[:REFERENCES]-> (Source)

    Indicates external sources cited or referenced.

    LLM Extraction Criteria:
    - URLs, book citations, paper references
    - Bibliography sections
    """
    reference_type: Optional[str] = Field(
        None,
        description="Type of reference: 'url', 'book', 'paper', 'video', 'documentation'."
    )


# ========================================
# Edge Types Dictionary
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

    # Generic fallback edges (from original PARA_EDGE_TYPES)
    "MENTIONS": BaseModel,  # No attributes, just existence
    "RELATES_TO": BaseModel,
}


# ========================================
# Extended Edge Type Map
# ========================================

PARA_EDGE_TYPE_MAP_EXTENDED: dict[tuple[str, str], list[str]] = {
    # ====== PARA ↔ PARA Relationships ======
    ("Project", "Area"): ["ContributesTo", "SpawnedFrom"],
    ("Project", "Resource"): ["UsesResource"],
    ("Project", "Project"): ["RELATES_TO", "DependsOn"],  # Inter-project dependencies

    ("Area", "Resource"): ["UsesResource"],
    ("Area", "Project"): ["SpawnedFrom"],  # Reverse: Area spawned this project
    ("Area", "Area"): ["RELATES_TO"],  # Related areas

    ("Resource", "Resource"): ["RELATES_TO"],  # Related resources

    ("Archive", "Project"): ["RELATES_TO"],  # Archived project relates to active
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

    # Archive → Entity (less specific, mostly historical)
    ("Archive", "Person"): ["MENTIONS"],
    ("Archive", "Organization"): ["MENTIONS"],

    # ====== Entity → PARA Relationships (Reverse Direction) ======

    # Person → PARA
    ("Person", "Project"): ["WorksOn", "LeadBy"],  # Reverse perspective
    ("Person", "Area"): ["ResponsibleFor", "ManagedBy"],  # Reverse perspective
    ("Person", "Resource"): ["AuthoredBy"],  # Reverse perspective

    # Task → PARA
    ("Task", "Project"): ["BelongsTo"],
    ("Task", "Area"): ["BelongsTo"],

    # Organization → PARA
    ("Organization", "Project"): ["PartnersWith"],  # Can be bidirectional
    ("Organization", "Resource"): ["AuthoredBy"],

    # Source → PARA
    ("Source", "Resource"): ["REFERENCED_BY"],  # Reverse of References

    # Decision → PARA
    ("Decision", "Project"): ["DOCUMENTED_IN"],
    ("Decision", "Area"): ["DOCUMENTED_IN"],

    # Idea → PARA
    ("Idea", "Project"): ["INSPIRED"],  # Idea inspired this project
    ("Idea", "Resource"): ["DOCUMENTED_IN"],

    # ====== Entity ↔ Entity Relationships (Non-PARA) ======

    ("Person", "Person"): ["MENTIONS", "COLLABORATES_WITH"],
    ("Person", "Organization"): ["WORKS_AT", "MENTIONS"],
    ("Person", "Task"): ["ASSIGNED_TO", "MENTIONS"],

    ("Task", "Task"): ["DEPENDS_ON", "RELATES_TO"],
    ("Task", "Decision"): ["IMPLEMENTS"],

    ("Organization", "Organization"): ["PARTNERS_WITH", "MENTIONS"],

    ("Decision", "Decision"): ["SUPERSEDES", "RELATES_TO"],

    ("Source", "Source"): ["CITES", "RELATES_TO"],

    # ====== Fallback for Unknown Combinations ======
    ("Entity", "Entity"): ["RELATES_TO", "MENTIONS"],
}
```

---

## Визуализация Связей

### PARA → Entity Edge Types (Outgoing)

```
┌─────────┐
│ Project │
└─────────┘
    ↓ AssignedTo, LeadBy
    → (Person)

    ↓ PartnersWith
    → (Organization)

    ↓ Contains
    → (Task, Decision, Idea)

    ↓ References
    → (Source)

    ↓ ContributesTo, SpawnedFrom
    → (Area)

    ↓ UsesResource
    → (Resource)


┌──────┐
│ Area │
└──────┘
    ↓ ManagedBy
    → (Person)

    ↓ Contains
    → (Task, Decision)

    ↓ UsesResource
    → (Resource)

    ↓ SpawnedFrom
    → (Project)


┌──────────┐
│ Resource │
└──────────┘
    ↓ AuthoredBy
    → (Person, Organization)

    ↓ References
    → (Source)

    ↓ Contains
    → (Idea)
```

---

### Entity → PARA Edge Types (Incoming)

```
(Person)
    ↓ WorksOn, LeadBy
    → Project

    ↓ ResponsibleFor, ManagedBy
    → Area

    ↓ AuthoredBy
    → Resource


(Task)
    ↓ BelongsTo
    → Project, Area


(Source)
    ↓ REFERENCED_BY
    → Resource
```

---

## Промпты для LLM (Edge Extraction Context)

### Кастомные инструкции на основе PARA типа

Эти инструкции передаются в `extract_edges` через `custom_prompt` (или hack через previous_episodes).

#### Для Project Notes

```
SPECIAL INSTRUCTIONS FOR PROJECT NOTE EDGE EXTRACTION:

This note is classified as a PROJECT. When extracting relationships, prioritize the following edge types:

1. **Person Relationships**:
   - Look for assignment statements: "assigned to", "owned by", "lead by"
   - Extract AssignedTo or LeadBy edges for people working on the project
   - Extract MENTIONS for people mentioned but not explicitly assigned

2. **Task Relationships**:
   - Look for task lists, checkboxes, action items
   - Extract Contains edges from project to tasks
   - Note task status if mentioned (todo/in_progress/done)

3. **Area Relationships**:
   - Look for statements like "this project contributes to X area"
   - Extract ContributesTo if project advances an area goal
   - Extract SpawnedFrom if project originated from an area

4. **Resource Usage**:
   - Look for references to guides, tutorials, documentation
   - Extract UsesResource for learning materials or reference docs

5. **Organization Partnerships**:
   - Look for external collaborators, vendors, clients
   - Extract PartnersWith for organizational relationships

6. **Decision and Idea Containment**:
   - Look for decision records ("Decided:", "Resolution:")
   - Look for key ideas or insights
   - Extract Contains edges

Prioritize typed edges (AssignedTo, Contains, etc.) over generic MENTIONS or RELATES_TO.
```

#### Для Area Notes

```
SPECIAL INSTRUCTIONS FOR AREA NOTE EDGE EXTRACTION:

This note is classified as an AREA. When extracting relationships, prioritize the following edge types:

1. **Ownership**:
   - Look for who manages or is responsible for this area
   - Extract ManagedBy edges to people

2. **Project Relationships**:
   - Look for projects that spawned from this area
   - Extract SpawnedFrom (from project to area)
   - Look for projects that contribute to this area's goals

3. **Resource Usage**:
   - Look for standard operating procedures, guidelines, reference materials
   - Extract UsesResource for knowledge base docs

4. **Ongoing Tasks**:
   - Look for recurring tasks or responsibilities
   - Extract Contains edges to tasks

5. **Standards and Best Practices**:
   - Look for documented decisions that define how this area operates
   - Extract Contains edges to decision records

Prioritize typed edges over generic relationships.
```

#### Для Resource Notes

```
SPECIAL INSTRUCTIONS FOR RESOURCE NOTE EDGE EXTRACTION:

This note is classified as a RESOURCE. When extracting relationships, prioritize the following edge types:

1. **Authorship**:
   - Look for who created or maintains this resource
   - Extract AuthoredBy edges to people or organizations

2. **External Sources**:
   - Look for citations, URLs, book references
   - Extract References edges to external sources

3. **Related Ideas**:
   - Look for key concepts or insights documented
   - Extract Contains edges to ideas

4. **Usage Relationships** (Incoming):
   - This resource might be USED_BY projects or areas
   - Look for mentions of application context

Prioritize structured attribution (AuthoredBy, References) over generic mentions.
```

---

## Имплементация: Генерация Кастомных Промптов

### Модуль para_edge_prompts.py

```python
"""
PARA-specific edge extraction prompt builders.

Generates custom instructions for LLM based on PARA type classification.
"""

from typing import Optional


def build_para_edge_instructions(para_type: Optional[str]) -> str:
    """
    Build custom prompt instructions for edge extraction based on PARA type.

    Args:
        para_type: "Project" | "Area" | "Resource" | "Archive" | None

    Returns:
        Custom instruction string to prepend/append to extract_edges prompt
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
    return """
SPECIAL INSTRUCTIONS FOR PROJECT NOTE EDGE EXTRACTION:

This note is a PROJECT (time-bound initiative with specific goal).

**Prioritize these relationship types**:

1. **Person Assignment** (AssignedTo, LeadBy):
   - "assigned to John", "owned by Sarah", "PM: Alex"
   - Use LeadBy for leaders/owners, AssignedTo for contributors

2. **Task Containment** (Contains):
   - Checkbox items, action items, milestones
   - Link tasks to this project

3. **Area Connection** (ContributesTo, SpawnedFrom):
   - "supports X area", "spawned from Y domain"
   - Link to parent areas

4. **Resource Usage** (UsesResource):
   - References to guides, documentation, best practices
   - "using X as reference", "following Y guide"

5. **Organization Partners** (PartnersWith):
   - External vendors, clients, collaborators

6. **Decisions and Ideas** (Contains):
   - "Decided:", key decisions made
   - Important insights or ideas

**Avoid generic MENTIONS/RELATES_TO when specific types apply.**
"""


def _area_edge_instructions() -> str:
    return """
SPECIAL INSTRUCTIONS FOR AREA NOTE EDGE EXTRACTION:

This note is an AREA (ongoing responsibility without endpoint).

**Prioritize these relationship types**:

1. **Ownership** (ManagedBy):
   - "managed by", "area owner:", "responsible:"
   - Link to the person managing this area

2. **Project Spawning** (SpawnedFrom - reverse):
   - Projects that originated from this area
   - "created project X to address Y"

3. **Resource Standards** (UsesResource):
   - SOPs, guidelines, knowledge base docs
   - "following X guidelines", "based on Y standards"

4. **Ongoing Tasks** (Contains):
   - Recurring tasks, regular duties
   - Checkboxes representing continuous work

5. **Decision Documentation** (Contains):
   - Standards and best practices documented
   - How things should be done in this area

**Avoid generic relationships when typed edges apply.**
"""


def _resource_edge_instructions() -> str:
    return """
SPECIAL INSTRUCTIONS FOR RESOURCE NOTE EDGE EXTRACTION:

This note is a RESOURCE (reference material, no action required).

**Prioritize these relationship types**:

1. **Authorship** (AuthoredBy):
   - "written by", "created by", "maintained by"
   - Link to authors (people or organizations)

2. **External References** (References):
   - URLs, book citations, paper references
   - "source:", "based on:", links

3. **Idea Documentation** (Contains):
   - Key concepts explained in this resource
   - Important insights or principles

4. **Related Resources** (RELATES_TO):
   - Links to other learning materials
   - "see also:", "related topics:"

**Focus on attribution and citation relationships.**
"""


def _archive_edge_instructions() -> str:
    return """
SPECIAL INSTRUCTIONS FOR ARCHIVE NOTE EDGE EXTRACTION:

This note is ARCHIVED (completed/inactive).

**Focus on**:

1. **Historical Context** (RELATES_TO):
   - What this archived item relates to
   - Learnings that apply to current projects/areas

2. **Outcome Documentation**:
   - Final results, lessons learned
   - People involved in completion

**Most edges will be generic (MENTIONS, RELATES_TO) since this is historical.**
"""


# ========================================
# Integration Point
# ========================================

def inject_para_context_into_episode(
    para_type: Optional[str],
    original_episode_content: str,
) -> str:
    """
    Inject PARA edge extraction instructions into episode content.

    This is a HACK to work around extract_edges not accepting custom_prompt parameter.
    We prepend the instructions to episode content so LLM sees them.

    Args:
        para_type: PARA classification of note
        original_episode_content: Original note content

    Returns:
        Modified content with PARA instructions prepended
    """

    instructions = build_para_edge_instructions(para_type)

    if not instructions:
        return original_episode_content

    # Prepend instructions with clear delimiters
    return f"""
{instructions}

===== END OF EDGE EXTRACTION INSTRUCTIONS =====
===== BEGIN NOTE CONTENT =====

{original_episode_content}
"""
```

---

## Интеграция в pipgraph_manager.py

### Модификация extract_edges вызова

```python
# В process_note(), после классификации и создания эпизода

# ЭТАП: Внедрение PARA контекста для extract_edges
if para_type:
    # Вариант A (HACK): Модифицировать episode content
    from app.services.para_edge_prompts import inject_para_context_into_episode

    episode_with_context = EpisodicNode(
        **episode.model_dump(exclude={"content"}),
        content=inject_para_context_into_episode(para_type, episode.content)
    )
else:
    episode_with_context = episode

# ЭТАП 3: ИЗВЛЕЧЕНИЕ СВЯЗЕЙ (с PARA контекстом)
extracted_edges = await extract_edges(
    self.clients,
    episode_with_context,  # ← Episode with PARA instructions
    extracted_nodes,
    previous_episodes,
    PARA_EDGE_TYPE_MAP_EXTENDED,  # ← Extended map
    group_id,
    PARA_EDGE_TYPES_EXTENDED,  # ← Extended types
)
```

**Note**: Это hack. В production версии желательно использовать wrapper функцию или vendor graphiti.

---

## Примеры Извлечения Связей

### Пример 1: Project Note с Assignments

**Input Note** (после классификации как Project):
```
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
    # ... more Contains edges for other tasks
    EntityEdge(
        name="UsesResource",
        source="Project:Q4_Product_Launch",
        target="Resource:API_Best_Practices",
        attributes={"usage_type": "reference material"}
    ),
]
```

---

### Пример 2: Area Note с Management

**Input Note** (после классификации как Area):
```
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
        name="SpawnedFrom",  # Reverse: project spawned from area
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
    # ... more Contains edges for other tasks
]
```

---

## Тестирование Edge Enrichment

### Unit Tests

```python
# tests/unit/test_para_edge_enrichment.py

import pytest
from app.services.para_edge_prompts import build_para_edge_instructions


def test_project_edge_instructions():
    """Test that project instructions mention AssignedTo, Contains, etc."""
    instructions = build_para_edge_instructions("Project")

    assert "AssignedTo" in instructions
    assert "LeadBy" in instructions
    assert "Contains" in instructions
    assert "ContributesTo" in instructions
    assert "UsesResource" in instructions


def test_area_edge_instructions():
    """Test that area instructions mention ManagedBy, SpawnedFrom, etc."""
    instructions = build_para_edge_instructions("Area")

    assert "ManagedBy" in instructions
    assert "SpawnedFrom" in instructions
    assert "UsesResource" in instructions
    assert "Contains" in instructions


def test_resource_edge_instructions():
    """Test that resource instructions mention AuthoredBy, References."""
    instructions = build_para_edge_instructions("Resource")

    assert "AuthoredBy" in instructions
    assert "References" in instructions
    assert "Contains" in instructions


def test_none_type_returns_empty():
    """Test that unclassified notes get no special instructions."""
    instructions = build_para_edge_instructions(None)
    assert instructions == ""
```

---

### Integration Tests

```python
# tests/integration/test_para_edge_extraction.py

import pytest
from app.services.pipgraph_manager import PipGraphManager


@pytest.mark.integration
async def test_project_edges_extracted_correctly(manager: PipGraphManager):
    """Test that project notes generate AssignedTo, Contains edges."""

    note_body = """
    # Q4 Campaign

    **PM**: Sarah Johnson
    **Deadline**: 2024-12-31

    ## Tasks
    - [ ] Design marketing materials (John Doe)
    """

    result = await manager.process_note(
        name="Q4 Campaign",
        episode_body=note_body,
        source_description="Test",
        reference_time=datetime.now(timezone.utc),
    )

    # Verify edges
    edge_names = [edge.name for edge in result.edges]

    assert "LeadBy" in edge_names or "AssignedTo" in edge_names
    assert "Contains" in edge_names

    # Verify LeadBy edge points to Sarah Johnson
    lead_edges = [e for e in result.edges if e.name == "LeadBy"]
    assert any("Sarah" in str(e.target_node_uuid) for e in lead_edges)
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

---

## Связанные Документы

- **Назад**: [03_CLASSIFICATION_FLOW.md](./03_CLASSIFICATION_FLOW.md)
- **Далее**: [05_IMPLEMENTATION_PLAN.md](./05_IMPLEMENTATION_PLAN.md) - Пошаговый план кода
- **Конфигурация**: `backend/config/para_config.py` - Место имплементации

---

## Checklist для Имплементации

- [ ] Создать Pydantic модели для всех новых edge types
- [ ] Обновить `PARA_EDGE_TYPES_EXTENDED` dict
- [ ] Создать `PARA_EDGE_TYPE_MAP_EXTENDED` с полным набором комбинаций
- [ ] Реализовать `para_edge_prompts.py` модуль
- [ ] Реализовать `build_para_edge_instructions()` для каждого PARA типа
- [ ] Интегрировать hack `inject_para_context_into_episode()` в `pipgraph_manager.py`
- [ ] Написать unit tests для prompt generation
- [ ] Написать integration tests для edge extraction
- [ ] Измерить edge type distribution до/после
- [ ] Документировать новые edge types в docstrings
