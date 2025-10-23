# План решения Issue #567: Custom Entity Labels в Graphiti

> **Проблема**: Graphiti не сохраняет custom entity types как Neo4j labels
> **GitHub Issue**: [#567](https://github.com/getzep/graphiti/issues/567)
> **Статус**: Open (на момент 2025-10-21)
> **Приоритет**: High (блокирует фильтрацию и label-aware entity resolution)

## Содержание

1. [Резюме проблемы](#резюме-проблемы)
2. [Стратегии решения](#стратегии-решения)
3. [Рекомендуемый подход](#рекомендуемый-подход)
4. [Implementation Roadmap](#implementation-roadmap)
5. [Код-примеры](#код-примеры)
6. [Тесты](#тесты)
7. [План миграции](#план-миграции)

---

## Резюме проблемы

### Текущее поведение

**Что происходит**:
```python
# PipGraph создает episode
entity = EntityNode(name="Python", labels=[])  # ← labels пустой!
await entity.save(driver)

# В Neo4j
MATCH (n {name: "Python"}) RETURN labels(n)
→ ["Entity"]  # ❌ Только базовый label!
```

**Почему происходит**:
1. LLM prompt в `extract_nodes` не требует заполнения `labels` field
2. Даже если `entity_types` настроены, type информация не попадает в `labels`
3. В `EntityNode.save()` строка 471: `labels = ':'.join(self.labels + ['Entity'])` → только `":Entity"`

### Желаемое поведение

```python
# После извлечения
entity = EntityNode(name="Python", labels=["Technology", "Programming Language"])

# В Neo4j
MATCH (n {name: "Python"}) RETURN labels(n)
→ ["Entity", "Technology", "Programming Language"]  # ✅

# Также сохраняется как property
MATCH (n {name: "Python"}) RETURN n.labels
→ ["Technology", "Programming Language"]  # ✅
```

### Влияние на PipGraph

- ❌ **Невозможна фильтрация по категориям**: `MATCH (n:Technology)` не работает
- ❌ **Label-aware entity resolution не работает**: нет данных для различения омонимов
- ❌ **Нет визуальной группировки** в Neo4j Browser по категориям
- ❌ **Теряется семантическая информация** из LLM извлечения

**См. детали**: [GRAPHITI_LABELS_EXPLAINED.md](GRAPHITI_LABELS_EXPLAINED.md)

---

## Стратегии решения

### Стратегия A: Post-processing Hook (Быстрое решение)

**Идея**: Добавить hook в `PipGraphManager` после `extract_nodes`, который инферирует labels из LLM response.

**Преимущества**:
- ✅ Не требует изменений в Graphiti Core
- ✅ Можно реализовать за 1-2 дня
- ✅ Полный контроль над логикой
- ✅ Работает с текущей версией Graphiti

**Недостатки**:
- ⚠️ Зависит от парсинга LLM response (может быть хрупким)
- ⚠️ Дублирование логики категоризации
- ⚠️ Не решает проблему для других пользователей Graphiti

**Подходит для**: Немедленного workaround в PipGraph.

---

### Стратегия B: Custom EntityNode Subclasses (Среднесрочное)

**Идея**: Создать custom entity types, которые автоматически добавляют labels при инициализации.

**Преимущества**:
- ✅ Явная типизация entities
- ✅ Автоматическое добавление labels
- ✅ Расширяемость (можно добавлять custom properties)
- ✅ Совместимо с Graphiti `entity_types` parameter

**Недостатки**:
- ⚠️ Требует определения всех entity types заранее
- ⚠️ LLM должен корректно классифицировать entities
- ⚠️ Не работает для динамических/неожиданных категорий

**Подходит для**: Структурированных domain models с заранее известными типами.

---

### Стратегия C: Patch Graphiti `extract_nodes` Prompt (Upstream Fix)

**Идея**: Модифицировать LLM prompt в Graphiti Core, чтобы требовать заполнения `labels` field.

**Преимущества**:
- ✅ Правильное решение "в корне"
- ✅ Помогает всем пользователям Graphiti
- ✅ Использует полную мощь LLM для категоризации
- ✅ Не требует предопределенной схемы

**Недостатки**:
- ⚠️ Требует PR в Graphiti Core
- ⚠️ Неизвестный timeline (может быть долго)
- ⚠️ Зависит от review/merge maintainers
- ⚠️ Может увеличить стоимость LLM calls (больше tokens)

**Подходит для**: Долгосрочного решения, помощи community.

---

## Рекомендуемый подход

### Комбинированная стратегия (A → B → C)

**Phase 1: Immediate Workaround (1-3 дня)**
- Стратегия A: Post-processing hook в `PipGraphManager`
- Использовать `attributes` для хранения категорий
- Обеспечить фильтрацию через `n.category`

**Phase 2: Structured Implementation (1-2 недели)**
- Стратегия B: Определить базовые entity types для PipGraph domain
- Создать custom `EntityNode` subclasses
- Добавить automatic label assignment

**Phase 3: Upstream Contribution (параллельно)**
- Стратегия C: Создать issue/PR в Graphiti
- Предложить patch для `extract_nodes` prompt
- Мониторить обсуждение и адаптировать

**Почему такой порядок**:
1. Phase 1 дает **немедленное решение** → пользователи могут фильтровать entities
2. Phase 2 обеспечивает **структурированность** → код становится maintainable
3. Phase 3 помогает **community** → в долгосрочной перспективе убираем workarounds

---

## Implementation Roadmap

### Phase 1: Post-processing Hook (Immediate)

**Срок**: 1-3 дня
**Файлы**:
- `backend/app/services/pipgraph_manager.py`
- `backend/app/services/entity_category_inference.py` (новый)
- `backend/tests/services/test_entity_category_inference.py` (новый)

**Задачи**:

1. **Создать `EntityCategoryInference` service**
   ```python
   # app/services/entity_category_inference.py
   class EntityCategoryInference:
       """Инферирует категории entities из summary/name."""

       def infer_category(self, entity: EntityNode) -> str | None:
           """Определяет категорию на основе keywords, patterns, LLM summary."""
           pass
   ```

2. **Добавить hook в `PipGraphManager.process_note()`**
   ```python
   # После строки 228 (extract_nodes)
   extracted_nodes = await extract_nodes(...)

   # НОВЫЙ КОД: Обогащение labels
   category_inferencer = EntityCategoryInference()
   for node in extracted_nodes:
       category = category_inferencer.infer_category(node)
       if category:
           node.attributes["category"] = category  # Workaround через attributes
           node.labels = [category]  # Попытка заполнить labels (может не работать)
   ```

3. **Реализовать keyword-based inference**
   ```python
   CATEGORY_KEYWORDS = {
       "Technology": ["software", "programming", "framework", "library", "tool"],
       "Person": ["человек", "разработчик", "developer", "engineer", "manager"],
       "Organization": ["компания", "company", "organization", "startup", "corp"],
       "Concept": ["идея", "методология", "принцип", "pattern", "approach"],
   }
   ```

4. **Добавить Cypher запросы для фильтрации**
   ```python
   # app/crud/entity_crud.py (новый)
   async def get_entities_by_category(driver, category: str):
       query = """
       MATCH (n:Entity)
       WHERE n.category = $category
       RETURN n
       """
       return await driver.execute_query(query, category=category)
   ```

5. **Тесты**
   - Unit тесты для `EntityCategoryInference`
   - Integration тесты для сохранения в Neo4j
   - E2E тест: извлечь entities → проверить `n.category`

**Критерии успеха**:
- ✅ Cypher `MATCH (n:Entity) WHERE n.category = "Technology"` работает
- ✅ Минимум 70% entities получают категорию
- ✅ Тесты проходят

---

### Phase 2: Custom EntityNode Subclasses (1-2 недели)

**Срок**: 1-2 недели
**Файлы**:
- `backend/app/models/entities/` (новая папка)
  - `base.py`
  - `person.py`
  - `technology.py`
  - `organization.py`
  - `concept.py`
- `backend/app/services/pipgraph_manager.py` (модификация)

**Задачи**:

1. **Определить domain-specific entity types**
   ```python
   # app/models/entities/person.py
   from graphiti_core.nodes import EntityNode

   class PersonEntity(EntityNode):
       """Person entity with auto-labels."""

       def __init__(self, **kwargs):
           super().__init__(**kwargs)
           # Автоматически добавляем label
           if "Person" not in self.labels:
               self.labels = self.labels + ["Person"]

       # Custom properties
       role: str | None = None
       affiliation: str | None = None
   ```

2. **Создать entity_types map**
   ```python
   # app/models/entities/__init__.py
   from .person import PersonEntity
   from .technology import TechnologyEntity
   from .organization import OrganizationEntity
   from .concept import ConceptEntity

   PIPGRAPH_ENTITY_TYPES = {
       "Person": PersonEntity,
       "Technology": TechnologyEntity,
       "Organization": OrganizationEntity,
       "Concept": ConceptEntity,
   }
   ```

3. **Использовать в `PipGraphManager`**
   ```python
   # В process_note()
   from app.models.entities import PIPGRAPH_ENTITY_TYPES

   extracted_nodes = await extract_nodes(
       self.clients,
       episode,
       previous_episodes,
       entity_types=PIPGRAPH_ENTITY_TYPES,  # ← Используем custom types!
       excluded_entity_types=excluded_entity_types
   )
   ```

4. **Тесты**
   - Unit тесты для каждого entity type
   - Проверить auto-labels assignment
   - Проверить custom properties

**Критерии успеха**:
- ✅ Entities создаются с правильными subclasses
- ✅ Labels автоматически добавляются
- ✅ Custom properties сохраняются

---

### Phase 3: Upstream Graphiti Contribution (параллельно)

**Срок**: Зависит от Graphiti maintainers
**Репозиторий**: https://github.com/getzep/graphiti

**Задачи**:

1. **Изучить Graphiti codebase**
   - Найти `extract_nodes` prompt
   - Понять структуру LLM response parsing
   - Проверить, где можно добавить `labels` field

2. **Модифицировать prompt**
   ```python
   # graphiti_core/prompts/extract_nodes.py (гипотетически)
   EXTRACT_NODES_PROMPT = """
   Extract entities from the episode.

   For each entity, provide:
   - name: Entity name
   - summary: Brief description
   - labels: List of category labels (e.g., ["Technology", "Programming Language"])
     - Assign broad categories like "Person", "Organization", "Technology", "Concept"
     - Add specific subcategories if applicable

   Example:
   {
     "name": "Python",
     "summary": "A programming language",
     "labels": ["Technology", "Programming Language"]
   }
   """
   ```

3. **Обновить parsing logic**
   - Парсить `labels` из LLM response
   - Присваивать `EntityNode.labels`

4. **Создать PR**
   - Fork Graphiti
   - Создать feature branch
   - Написать тесты
   - Создать PR с описанием проблемы и решения

5. **Участвовать в review**
   - Отвечать на комментарии maintainers
   - Адаптировать код по feedback

**Критерии успеха**:
- ✅ PR создан и отправлен
- ✅ Тесты проходят в CI
- ⏳ PR merged (зависит от maintainers)

---

## Код-примеры

### 1. Post-processing Hook

```python
# backend/app/services/entity_category_inference.py

import re
from typing import Dict, List
from graphiti_core.nodes import EntityNode


class EntityCategoryInference:
    """
    Инферирует категории entities на основе keywords и patterns.

    Используется как workaround для Issue #567 до upstream fix.
    """

    CATEGORY_KEYWORDS: Dict[str, List[str]] = {
        "Technology": [
            "software", "программа", "framework", "библиотека", "library",
            "язык программирования", "programming language", "tool", "инструмент",
            "api", "database", "база данных", "платформа", "platform"
        ],
        "Person": [
            "человек", "разработчик", "developer", "engineer", "инженер",
            "manager", "менеджер", "designer", "дизайнер", "researcher"
        ],
        "Organization": [
            "компания", "company", "organization", "организация", "startup",
            "стартап", "corp", "inc", "ltd", "университет", "university"
        ],
        "Concept": [
            "идея", "idea", "методология", "methodology", "принцип", "principle",
            "pattern", "паттерн", "подход", "approach", "концепция", "concept"
        ],
        "Place": [
            "город", "city", "страна", "country", "офис", "office",
            "локация", "location", "адрес", "address"
        ]
    }

    def infer_category(self, entity: EntityNode) -> str | None:
        """
        Определяет категорию entity на основе name и summary.

        Args:
            entity: EntityNode для категоризации

        Returns:
            Название категории или None, если не удалось определить
        """
        # Объединяем name и summary для анализа
        text = f"{entity.name} {entity.summary or ''}".lower()

        # Подсчитываем scores для каждой категории
        scores = {}
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword.lower() in text)
            if score > 0:
                scores[category] = score

        # Возвращаем категорию с максимальным score
        if scores:
            return max(scores, key=scores.get)

        return None

    def infer_multiple_categories(self, entity: EntityNode, threshold: int = 1) -> List[str]:
        """
        Определяет несколько категорий для entity.

        Args:
            entity: EntityNode для категоризации
            threshold: Минимальный score для включения категории

        Returns:
            Список категорий
        """
        text = f"{entity.name} {entity.summary or ''}".lower()

        categories = []
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword.lower() in text)
            if score >= threshold:
                categories.append(category)

        return categories


# backend/app/services/pipgraph_manager.py

# Добавить import
from app.services.entity_category_inference import EntityCategoryInference

# В методе process_note(), после строки 228:

# ЭТАП 1: ИЗВЛЕЧЕНИЕ СЫРЫХ СУЩНОСТЕЙ
extracted_nodes = await extract_nodes(
    self.clients, episode, previous_episodes, entity_types, excluded_entity_types
)

# ========== НОВЫЙ КОД: WORKAROUND ДЛЯ ISSUE #567 ==========
# Обогащаем entities категориями через inference
category_inferencer = EntityCategoryInference()
for node in extracted_nodes:
    # Инферируем категорию
    category = category_inferencer.infer_category(node)

    if category:
        # Сохраняем в attributes (надежный workaround)
        if node.attributes is None:
            node.attributes = {}
        node.attributes["category"] = category

        # Пытаемся заполнить labels (может не сохраниться из-за Issue #567)
        if not node.labels:
            node.labels = [category]

    logger.debug(
        f"Entity '{node.name}' categorized as: {category or 'Unknown'}",
        extra={"entity_uuid": node.uuid, "category": category}
    )
# ========== КОНЕЦ WORKAROUND ==========

# TODO: ТОЧКА ИНТЕРВЕНЦИИ 1 (optional)
# Здесь можно показать пользователю список найденных сущностей
# и дать возможность подтвердить/отклонить их
```

**Тесты**:

```python
# backend/tests/services/test_entity_category_inference.py

import pytest
from graphiti_core.nodes import EntityNode
from app.services.entity_category_inference import EntityCategoryInference


class TestEntityCategoryInference:
    """Тесты для категоризации entities."""

    def setup_method(self):
        self.inferencer = EntityCategoryInference()

    def test_infer_technology_category(self):
        """Должен корректно определить Technology."""
        entity = EntityNode(
            name="Python",
            summary="A popular programming language for data science"
        )

        category = self.inferencer.infer_category(entity)
        assert category == "Technology"

    def test_infer_person_category(self):
        """Должен корректно определить Person."""
        entity = EntityNode(
            name="Антон Новиков",
            summary="Senior разработчик в TechCorp"
        )

        category = self.inferencer.infer_category(entity)
        assert category == "Person"

    def test_infer_organization_category(self):
        """Должен корректно определить Organization."""
        entity = EntityNode(
            name="TechCorp",
            summary="Крупная IT компания, занимающаяся AI"
        )

        category = self.inferencer.infer_category(entity)
        assert category == "Organization"

    def test_infer_no_category(self):
        """Должен вернуть None для неопределенных entities."""
        entity = EntityNode(
            name="Загадка",
            summary="Непонятно что это"
        )

        category = self.inferencer.infer_category(entity)
        assert category is None

    def test_infer_multiple_categories(self):
        """Должен определить несколько категорий."""
        entity = EntityNode(
            name="Стэнфордский университет",
            summary="Образовательная организация в области computer science"
        )

        categories = self.inferencer.infer_multiple_categories(entity)
        assert "Organization" in categories
        # Может также содержать "Technology" из-за "computer science"
```

---

### 2. Custom EntityNode Subclasses

```python
# backend/app/models/entities/base.py

from graphiti_core.nodes import EntityNode


class PipGraphEntity(EntityNode):
    """
    Base class для всех custom entities в PipGraph.

    Автоматически добавляет labels на основе class name.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Автоматически добавляем label из class name
        class_label = self.__class__.__name__.replace("Entity", "")
        if class_label != "PipGraph" and class_label not in self.labels:
            self.labels = self.labels + [class_label]


# backend/app/models/entities/person.py

from pydantic import Field
from app.models.entities.base import PipGraphEntity


class PersonEntity(PipGraphEntity):
    """
    Entity representing a person (developer, manager, researcher, etc.).

    Auto-adds "Person" label to Neo4j.
    """

    # Custom properties
    role: str | None = Field(
        default=None,
        description="Role or occupation of the person"
    )
    affiliation: str | None = Field(
        default=None,
        description="Organization or company the person is affiliated with"
    )


# backend/app/models/entities/technology.py

from pydantic import Field
from app.models.entities.base import PipGraphEntity


class TechnologyEntity(PipGraphEntity):
    """
    Entity representing technology (software, framework, library, tool).

    Auto-adds "Technology" label to Neo4j.
    """

    # Custom properties
    tech_type: str | None = Field(
        default=None,
        description="Type of technology (e.g., 'Programming Language', 'Framework', 'Database')"
    )
    version: str | None = Field(
        default=None,
        description="Version of the technology if applicable"
    )


# backend/app/models/entities/organization.py

from pydantic import Field
from app.models.entities.base import PipGraphEntity


class OrganizationEntity(PipGraphEntity):
    """
    Entity representing an organization (company, startup, university).

    Auto-adds "Organization" label to Neo4j.
    """

    # Custom properties
    org_type: str | None = Field(
        default=None,
        description="Type of organization (e.g., 'Company', 'Startup', 'University')"
    )
    industry: str | None = Field(
        default=None,
        description="Industry or sector"
    )


# backend/app/models/entities/__init__.py

from .person import PersonEntity
from .technology import TechnologyEntity
from .organization import OrganizationEntity

# Entity types map для Graphiti
PIPGRAPH_ENTITY_TYPES = {
    "Person": PersonEntity,
    "Technology": TechnologyEntity,
    "Organization": OrganizationEntity,
}

__all__ = [
    "PersonEntity",
    "TechnologyEntity",
    "OrganizationEntity",
    "PIPGRAPH_ENTITY_TYPES",
]
```

**Использование в PipGraphManager**:

```python
# backend/app/services/pipgraph_manager.py

from app.models.entities import PIPGRAPH_ENTITY_TYPES

# В process_note()
extracted_nodes = await extract_nodes(
    self.clients,
    episode,
    previous_episodes,
    entity_types=PIPGRAPH_ENTITY_TYPES,  # ← Используем custom types
    excluded_entity_types=excluded_entity_types
)
```

**Тесты**:

```python
# backend/tests/models/entities/test_custom_entities.py

import pytest
from app.models.entities import PersonEntity, TechnologyEntity, OrganizationEntity


class TestCustomEntities:
    """Тесты для custom entity types."""

    def test_person_entity_auto_label(self):
        """PersonEntity должен автоматически добавлять label 'Person'."""
        person = PersonEntity(
            name="Антон Новиков",
            summary="Senior Developer"
        )

        assert "Person" in person.labels

    def test_person_entity_custom_properties(self):
        """PersonEntity должен поддерживать custom properties."""
        person = PersonEntity(
            name="Антон Новиков",
            summary="Developer",
            role="Senior Backend Engineer",
            affiliation="TechCorp"
        )

        assert person.role == "Senior Backend Engineer"
        assert person.affiliation == "TechCorp"

    def test_technology_entity_auto_label(self):
        """TechnologyEntity должен автоматически добавлять label 'Technology'."""
        tech = TechnologyEntity(
            name="Python",
            summary="Programming language"
        )

        assert "Technology" in tech.labels

    def test_organization_entity_auto_label(self):
        """OrganizationEntity должен автоматически добавлять label 'Organization'."""
        org = OrganizationEntity(
            name="TechCorp",
            summary="IT company"
        )

        assert "Organization" in org.labels
```

---

### 3. Upstream Graphiti Prompt Patch (Пример PR)

```python
# graphiti_core/prompts/extract_nodes.py (гипотетический patch)

# БЫЛО:
EXTRACT_NODES_SYSTEM_PROMPT = """
Extract entities from the given episode.

For each entity provide:
- name: The name of the entity
- summary: A brief description of the entity

Return a JSON array of entities.
"""

# СТАЛО:
EXTRACT_NODES_SYSTEM_PROMPT = """
Extract entities from the given episode.

For each entity provide:
- name: The name of the entity
- summary: A brief description of the entity
- labels: A list of category labels for the entity (required)
  * Assign broad categories like "Person", "Organization", "Technology", "Concept", "Event", "Place"
  * Add specific subcategories if applicable (e.g., ["Technology", "Programming Language"])
  * Use at least one label per entity
  * Labels should be general categories, not specific to this instance

Examples:
- Entity "Python" → labels: ["Technology", "Programming Language"]
- Entity "John Doe" → labels: ["Person"]
- Entity "TechCorp" → labels: ["Organization", "Company"]
- Entity "Machine Learning" → labels: ["Concept", "Technology"]

Return a JSON array of entities.
"""

# graphiti_core/utils/maintenance/node_operations.py

# В функции extract_nodes, при парсинге LLM response:

# БЫЛО:
entity_node = EntityNode(
    name=entity_data["name"],
    summary=entity_data.get("summary", ""),
    group_id=episode.group_id,
)

# СТАЛО:
entity_node = EntityNode(
    name=entity_data["name"],
    summary=entity_data.get("summary", ""),
    labels=entity_data.get("labels", []),  # ← НОВОЕ: Парсим labels из LLM response
    group_id=episode.group_id,
)
```

**PR Description** (пример):

```markdown
## Fix #567: Add labels field to extract_nodes LLM prompt

### Problem
Currently, Graphiti does not populate the `labels` field when extracting entities via LLM. This causes:
- All Entity nodes in Neo4j to have only the base `:Entity` label
- No ability to filter by entity categories
- Loss of semantic information from LLM extraction

See Issue #567 for detailed analysis.

### Solution
1. Update `EXTRACT_NODES_SYSTEM_PROMPT` to require `labels` field in LLM response
2. Parse `labels` from LLM response and assign to `EntityNode.labels`
3. Existing `EntityNode.save()` logic already handles converting `labels` to Neo4j labels

### Example

**Before**:
```python
entity = EntityNode(name="Python", labels=[])  # Empty!
# Neo4j: labels(n) → ["Entity"]
```

**After**:
```python
entity = EntityNode(name="Python", labels=["Technology", "Programming Language"])
# Neo4j: labels(n) → ["Entity", "Technology", "Programming Language"]
```

### Testing
- Added unit tests for LLM response parsing
- Added integration test verifying Neo4j labels are set correctly
- Tested with OpenAI GPT-4 and Anthropic Claude models

### Breaking Changes
None - this is backwards compatible. If LLM doesn't return `labels`, defaults to empty list.
```

---

## Тесты

### Integration Test: Labels Persistence

```python
# backend/tests/integration/test_issue_567_labels.py

import pytest
from datetime import datetime, timezone
from graphiti_core.nodes import EntityNode
from app.services.pipgraph_manager import PipGraphManager


@pytest.mark.integration
@pytest.mark.asyncio
async def test_entity_labels_saved_to_neo4j(pipgraph_manager: PipGraphManager, neo4j_driver):
    """
    Integration test для Issue #567: проверяем, что labels сохраняются в Neo4j.

    Этот тест проверяет WORKAROUND через attributes.category до upstream fix.
    """
    # Process note с сущностью
    result = await pipgraph_manager.process_note(
        name="test_note.md",
        episode_body="Python is a popular programming language used for data science.",
        source="test",
        source_description="Integration test",
        reference_time=datetime.now(timezone.utc)
    )

    # Проверяем, что entities были извлечены
    assert len(result.nodes) > 0

    # Ищем entity "Python"
    python_entity = next((n for n in result.nodes if "Python" in n.name), None)
    assert python_entity is not None, "Entity 'Python' should be extracted"

    # Проверяем Neo4j
    query = """
    MATCH (n:Entity {uuid: $uuid})
    RETURN
        labels(n) AS neo4j_labels,
        n.category AS category,
        n.labels AS labels_field
    """

    result = await neo4j_driver.execute_query(
        query,
        uuid=python_entity.uuid
    )

    record = result.records[0]

    # После WORKAROUND (Phase 1):
    # - neo4j_labels может быть только ["Entity"] (Issue #567 не исправлен)
    # - но category должна быть "Technology"
    assert record["category"] == "Technology", "Category should be inferred and saved"

    # После UPSTREAM FIX (Phase 3):
    # - neo4j_labels должны включать "Technology"
    # - labels_field должно быть ["Technology"] или подобное
    # Раскомментировать после merge upstream fix:
    # assert "Technology" in record["neo4j_labels"], "Neo4j labels should include Technology"
    # assert record["labels_field"] is not None, "labels field should be persisted"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_filter_entities_by_category(pipgraph_manager: PipGraphManager, neo4j_driver):
    """
    Проверяем фильтрацию по категориям через n.category.
    """
    # Process несколько заметок
    await pipgraph_manager.process_note(
        name="tech_note.md",
        episode_body="Python and JavaScript are programming languages.",
        source="test",
        source_description="Test",
        reference_time=datetime.now(timezone.utc)
    )

    await pipgraph_manager.process_note(
        name="people_note.md",
        episode_body="Антон Новиков is a senior developer at TechCorp.",
        source="test",
        source_description="Test",
        reference_time=datetime.now(timezone.utc)
    )

    # Фильтруем по категории "Technology"
    query = """
    MATCH (n:Entity)
    WHERE n.category = 'Technology'
    RETURN n.name AS name
    """

    result = await neo4j_driver.execute_query(query)
    tech_names = [record["name"] for record in result.records]

    # Должны найти Python и/или JavaScript
    assert any("Python" in name or "JavaScript" in name for name in tech_names)

    # Фильтруем по категории "Person"
    query = """
    MATCH (n:Entity)
    WHERE n.category = 'Person'
    RETURN n.name AS name
    """

    result = await neo4j_driver.execute_query(query)
    person_names = [record["name"] for record in result.records]

    # Должны найти Антона
    assert any("Антон" in name or "Novikov" in name for name in person_names)
```

### Unit Test: Category Inference

```python
# backend/tests/services/test_entity_category_inference.py
# (См. выше в разделе "Код-примеры")
```

### E2E Test: Full Pipeline

```python
# backend/tests/e2e/test_note_processing_with_labels.py

import pytest
from datetime import datetime, timezone


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_pipeline_entity_categorization(
    test_client,
    neo4j_driver,
    cleanup_neo4j
):
    """
    E2E тест: отправляем заметку через API, проверяем категоризацию в Neo4j.
    """
    # Отправляем заметку через WebSocket API
    note_content = """
    # Tech Discussion

    Today I discussed Python and FastAPI with John Doe from TechCorp.
    We explored how to integrate Neo4j with our backend system.
    """

    # Здесь использовать WebSocket client для отправки заметки
    # (реализация зависит от вашего API)

    # После обработки проверяем Neo4j
    query = """
    MATCH (n:Entity)
    WHERE n.name CONTAINS 'Python' OR n.name CONTAINS 'FastAPI'
    RETURN n.name, n.category
    """

    result = await neo4j_driver.execute_query(query)

    # Проверяем, что технологии категоризированы
    for record in result.records:
        assert record["category"] == "Technology"
```

---

## План миграции

### Миграция существующих данных (после upstream fix)

**Проблема**: Существующие Entity nodes в Neo4j имеют только `:Entity` label и не имеют `category` attribute.

**Решение**: Cypher скрипт для backfill категорий.

#### Вариант 1: Re-processing Notes

```python
# backend/scripts/migrate_add_labels.py

"""
Скрипт для пересоздания графа с правильными labels.

WARNING: Это удалит все существующие данные!
"""

import asyncio
from app.core.config import settings
from app.services.pipgraph_manager import PipGraphManager
from graphiti_core import Graphiti
from neo4j import GraphDatabase


async def migrate_reprocess_all_notes():
    """
    Стратегия: удалить граф, пересоздать из исходных заметок.

    Требования:
    - Исходные заметки доступны (Obsidian vault)
    - Готовность к длительной обработке (LLM calls)
    """
    print("WARNING: This will delete all existing graph data!")
    confirm = input("Type 'YES' to continue: ")

    if confirm != "YES":
        print("Migration cancelled.")
        return

    # 1. Очистить Neo4j
    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )

    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
        print("Neo4j cleared.")

    # 2. Пересоздать граф
    graphiti = Graphiti(...)
    manager = PipGraphManager(graphiti)

    # 3. Обработать все заметки заново
    notes = get_all_notes_from_vault()  # Реализовать

    for i, note in enumerate(notes):
        print(f"Processing {i+1}/{len(notes)}: {note.name}")
        await manager.process_note(
            name=note.name,
            episode_body=note.content,
            source="obsidian",
            source_description=note.path,
            reference_time=note.modified_time
        )

    print("Migration complete!")


if __name__ == "__main__":
    asyncio.run(migrate_reprocess_all_notes())
```

#### Вариант 2: In-place Category Inference

```cypher
-- backend/scripts/migrate_add_labels.cypher

-- Скрипт для добавления category к существующим entities без пересоздания.

-- 1. Найти все entities без category
MATCH (n:Entity)
WHERE n.category IS NULL
WITH n
LIMIT 1000  -- Batch processing

-- 2. Инферировать category из summary
SET n.category =
    CASE
        WHEN n.summary CONTAINS 'programming' OR n.summary CONTAINS 'software'
             OR n.summary CONTAINS 'framework' OR n.summary CONTAINS 'library'
             THEN 'Technology'

        WHEN n.summary CONTAINS 'developer' OR n.summary CONTAINS 'engineer'
             OR n.summary CONTAINS 'manager' OR n.summary CONTAINS 'person'
             THEN 'Person'

        WHEN n.summary CONTAINS 'company' OR n.summary CONTAINS 'organization'
             OR n.summary CONTAINS 'startup' OR n.summary CONTAINS 'corp'
             THEN 'Organization'

        WHEN n.summary CONTAINS 'concept' OR n.summary CONTAINS 'idea'
             OR n.summary CONTAINS 'methodology' OR n.summary CONTAINS 'principle'
             THEN 'Concept'

        ELSE 'Unknown'
    END

RETURN count(n) AS updated_count;

-- Запустить несколько раз, пока updated_count > 0
```

**Python wrapper для Cypher migration**:

```python
# backend/scripts/migrate_add_labels_in_place.py

import asyncio
from neo4j import GraphDatabase
from app.core.config import settings


async def migrate_add_categories_in_place():
    """
    Добавляет category к существующим entities на основе keyword inference.

    Менее точно, чем LLM re-processing, но быстрее и безопаснее.
    """
    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )

    with open("backend/scripts/migrate_add_labels.cypher", "r") as f:
        cypher_query = f.read()

    total_updated = 0

    with driver.session() as session:
        while True:
            result = session.run(cypher_query)
            updated_count = result.single()["updated_count"]

            total_updated += updated_count
            print(f"Batch updated: {updated_count} entities")

            if updated_count == 0:
                break

    print(f"Migration complete! Total updated: {total_updated} entities")


if __name__ == "__main__":
    asyncio.run(migrate_add_categories_in_place())
```

#### Вариант 3: Manual Review UI

**Идея**: Создать простой UI для ручного review и категоризации entities.

```python
# backend/app/api/routes/admin.py (новый endpoint)

from fastapi import APIRouter
from app.services.entity_crud import get_uncategorized_entities, update_entity_category

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/uncategorized-entities")
async def get_uncategorized():
    """Получить список entities без категории."""
    entities = await get_uncategorized_entities(limit=50)
    return {"entities": entities}


@router.post("/entities/{uuid}/category")
async def set_entity_category(uuid: str, category: str):
    """Установить категорию для entity вручную."""
    await update_entity_category(uuid, category)
    return {"status": "ok", "uuid": uuid, "category": category}
```

**Простой UI** (React/HTML):
```jsx
// frontend/admin/EntityReview.jsx

function EntityReview() {
  const [entities, setEntities] = useState([]);

  useEffect(() => {
    fetch('/api/v1/admin/uncategorized-entities')
      .then(r => r.json())
      .then(data => setEntities(data.entities));
  }, []);

  const setCategory = (uuid, category) => {
    fetch(`/api/v1/admin/entities/${uuid}/category`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({category})
    });
  };

  return (
    <div>
      <h1>Review Uncategorized Entities</h1>
      {entities.map(e => (
        <div key={e.uuid}>
          <h3>{e.name}</h3>
          <p>{e.summary}</p>
          <select onChange={(ev) => setCategory(e.uuid, ev.target.value)}>
            <option>Select category...</option>
            <option value="Technology">Technology</option>
            <option value="Person">Person</option>
            <option value="Organization">Organization</option>
            <option value="Concept">Concept</option>
          </select>
        </div>
      ))}
    </div>
  );
}
```

---

## Сравнение стратегий миграции

| Стратегия | Точность | Скорость | Стоимость (LLM) | Риск потери данных |
|-----------|----------|----------|-----------------|-------------------|
| **Вариант 1: Re-processing** | ⭐⭐⭐⭐⭐ | ⭐ | 💰💰💰 | ⚠️ Высокий |
| **Вариант 2: In-place Cypher** | ⭐⭐ | ⭐⭐⭐⭐⭐ | 💰 (бесплатно) | ⚠️ Низкий |
| **Вариант 3: Manual Review** | ⭐⭐⭐⭐ | ⭐⭐ | 💰 (бесплатно) | ⚠️ Низкий |

**Рекомендация**:
1. Начать с **Вариант 2** (Cypher in-place) для быстрого улучшения
2. Использовать **Вариант 3** (Manual UI) для critical entities
3. Рассмотреть **Вариант 1** (Re-processing) только для маленьких графов (<1000 nodes)

---

## Timeline и Dependencies

### Phase 1: Immediate Workaround

**Срок**: 1-3 дня
**Dependencies**: Нет
**Deliverables**:
- ✅ `EntityCategoryInference` service
- ✅ Post-processing hook в `PipGraphManager`
- ✅ Unit + integration тесты
- ✅ Cypher запросы для фильтрации по `category`

**Success Metrics**:
- 70%+ entities получают категорию
- Cypher `WHERE n.category = "Technology"` работает
- Тесты проходят

---

### Phase 2: Custom Entity Types

**Срок**: 1-2 недели
**Dependencies**: Phase 1 (опционально, можно параллельно)
**Deliverables**:
- ✅ `app/models/entities/` с custom entity types
- ✅ `PIPGRAPH_ENTITY_TYPES` map
- ✅ Интеграция с `PipGraphManager`
- ✅ Unit тесты для каждого entity type

**Success Metrics**:
- Custom entities создаются с правильными labels
- Auto-labeling работает
- Custom properties сохраняются

---

### Phase 3: Upstream Contribution

**Срок**: Зависит от Graphiti maintainers (1-3 месяца?)
**Dependencies**: Нет (параллельно Phase 1-2)
**Deliverables**:
- ✅ Fork Graphiti repo
- ✅ Feature branch с patch
- ✅ Тесты для upstream PR
- ✅ PR создан и submitted
- ⏳ PR reviewed и merged (зависит от maintainers)

**Success Metrics**:
- PR создан
- CI проходит
- Maintainers начали review

---

## Заключение

### Ключевые выводы

1. **Issue #567 реален и блокирует функциональность**:
   - Невозможна фильтрация по категориям
   - Label-aware entity resolution не работает
   - Теряется семантическая информация

2. **Комбинированный подход оптимален**:
   - Phase 1: Немедленный workaround через `attributes`
   - Phase 2: Структурированные custom entity types
   - Phase 3: Upstream fix для всего community

3. **Workaround через `attributes.category` работает**:
   - Надежно (не зависит от Graphiti bugs)
   - Позволяет фильтрацию в Cypher
   - Легко мигрировать на labels после upstream fix

4. **Custom entity types улучшают maintainability**:
   - Явная типизация
   - Auto-labeling
   - Расширяемость (custom properties)

5. **Upstream contribution помогает community**:
   - Долгосрочное решение
   - Убирает необходимость workarounds
   - Помогает другим пользователям Graphiti

### Следующие шаги

**Немедленно**:
1. ✅ Создать Issue в PipGraph repo для трекинга
2. ✅ Начать Phase 1: Post-processing hook
3. ✅ Написать unit тесты для `EntityCategoryInference`

**Через 1-2 недели**:
1. ⏳ Завершить Phase 1, задеплоить workaround
2. ⏳ Начать Phase 2: Custom entity types
3. ⏳ Создать fork Graphiti для Phase 3

**Долгосрочно**:
1. ⏳ Мониторить Graphiti releases
2. ⏳ Участвовать в upstream PR review
3. ⏳ Мигрировать на labels после merge

---

## Связанные документы

- [GRAPHITI_LABELS_EXPLAINED.md](GRAPHITI_LABELS_EXPLAINED.md) - Детальное объяснение проблемы
- [GRAPHITI_HOMONYMS_EDGE_CASE.md](GRAPHITI_HOMONYMS_EDGE_CASE.md) - Label-aware entity resolution
- [GRAPHITI_EMBEDDING_DESIGN_RATIONALE.md](GRAPHITI_EMBEDDING_DESIGN_RATIONALE.md) - Использование labels в примерах
- [GitHub Issue #567](https://github.com/getzep/graphiti/issues/567) - Upstream issue

---

**Автор**: Claude (Anthropic)
**Дата**: 2025-10-21
**Версия**: 1.0
**Статус**: Implementation plan - Ready for execution
