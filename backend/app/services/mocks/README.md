# Mock Services

**Дата создания:** 2025-11-21
**Версия:** 1.0
**Статус:** Active - Ready for Migration

---

## Обзор

Этот пакет содержит mock-реализации LLM сервисов для Mock-First Development подхода. Моки позволяют быстро проверить архитектуру системы без реальных API вызовов.

### Преимущества Mock-подхода

✅ **Быстрая итерация**
- Нет задержек на LLM API (экономия времени и денег)
- Мгновенная проверка результатов в Neo4j Browser
- Детерминированные данные → легче отладка

✅ **Фокус на архитектуре**
- Проверяем схему данных (`:SUGGESTS` с `suggestion_id`, множественные ребра)
- Отлаживаем CRUD операции
- Видим реальную структуру графа

✅ **Постепенная миграция**
- Начинаем с моков
- Постепенно заменяем компоненты на реальные LLM вызовы
- Сначала L1, потом L2, потом L3

---

## Mock Modules

### 1. mock_classifier.py (L1)

**Функция:** `classify_note_para(note_content: str) -> str`

**Описание:** Классификация заметки по типу PARA (Project, Area, Resource).

**Возвращаемые данные:**
```python
"Project"  # Всегда возвращает "Project"
```

**Использование:**
```python
from app.services.mocks.mock_classifier import classify_note_para

para_type = classify_note_para("Note content here")
# Returns: "Project"
```

**Логика:**
- Простая реализация: всегда возвращает "Project"
- Можно расширить для keyword-based классификации

---

### 2. mock_proposal_generator.py (L2)

**Функция:** `generate_para_proposal(note_content: str) -> PARAProposal`

**Описание:** Генерация предложений по привязке заметки к контейнеру PARA.

**Возвращаемые данные:**
```python
PARAProposal(
    primary_candidate=PARACandidate(
        container_id="mock-project-alpha",
        container_name="Mock Project Alpha",
        confidence=0.80,
        reasoning="Mock: content matches project context",
        suggestion_type="link"
    ),
    alternatives=[
        PARACandidate(
            container_id="mock-project-alpha",
            container_name="Mock Project Alpha v2",
            confidence=0.75,
            reasoning="Mock: note suggests project renaming",
            suggestion_type="property_update",
            target_field="name",
            suggested_value="Mock Project Alpha v2"
        )
    ]
)
```

**Использование:**
```python
from app.services.mocks.mock_proposal_generator import generate_para_proposal

proposal = generate_para_proposal("Note content")
print(proposal.primary_candidate.container_name)  # "Mock Project Alpha"
print(len(proposal.alternatives))  # 1
```

**Важно:** Перед тестированием создайте Project с `id="mock-project-alpha"` в Neo4j!

---

### 3. mock_graphiti.py (L3)

**Функция:** `extract_entities(episodic_content: str, context: dict) -> list[ExtractedCandidate]`

**Описание:** Извлечение сущностей из контента заметки с учетом контекста.

**Возвращаемые данные:**
```python
[
    ExtractedCandidate(
        uuid="mock-entity-001",
        name="Mock Concept: User Authentication",
        labels=["Entity", "Concept"],
        summary=f"Authentication system mentioned in note (context: {context['name']})"
    ),
    ExtractedCandidate(
        uuid="mock-entity-002",
        name="Mock Task: Implement Login",
        labels=["Entity", "Task"],
        summary=f"Task to implement login feature (context: {context['name']})"
    )
]
```

**Использование:**
```python
from app.services.mocks.mock_graphiti import extract_entities

context = {
    "id": "project-123",
    "name": "My Project",
    "label": "Project"
}
entities = extract_entities("Note content", context)
print(len(entities))  # 2
```

**Особенность:** Имя контейнера включается в `summary` для проверки передачи контекста.

---

## Архитектура импортов

### Текущее состояние (Mock)

```python
# app/services/para/__init__.py
from app.services.mocks.mock_classifier import classify_note_para
from app.services.mocks.mock_proposal_generator import generate_para_proposal

# app/services/graphiti/__init__.py (если создан)
from app.services.mocks.mock_graphiti import extract_entities
```

### После миграции (Real LLM)

```python
# app/services/para/__init__.py
from app.services.llm.real_classifier import classify_note_para
from app.services.llm.real_proposal_generator import generate_para_proposal

# app/services/graphiti/__init__.py
from app.services.graphiti.real_graphiti import extract_entities
```

---

## План миграции

### Этап 1: L1 Classifier

**Когда:** После успешной проверки архитектуры на моках

1. Создать `app/services/llm/real_classifier.py`
2. Реализовать LLM вызов через OpenRouter API
3. Изменить импорт в `app/services/para/__init__.py`:
   ```python
   from app.services.llm.real_classifier import classify_note_para
   ```
4. Проверить что остальные моки работают

### Этап 2: L2 Proposal Generator

**Когда:** После стабилизации L1

1. Создать `app/services/llm/real_proposal_generator.py`
2. Реализовать:
   - Embeddings для поиска похожих контейнеров
   - LLM для генерации PARAProposal
3. Изменить импорт в `app/services/para/__init__.py`:
   ```python
   from app.services.llm.real_proposal_generator import generate_para_proposal
   ```

### Этап 3: L3 Graphiti Extraction

**Когда:** После стабилизации L1+L2

1. Интегрировать Graphiti SDK
2. Реализовать context injection в промпт
3. Изменить импорт:
   ```python
   from app.services.graphiti.real_graphiti import extract_entities
   ```
4. Опционально: удалить моки или оставить для тестов

---

## Проверка работы моков

### 1. Unit тест

```python
from app.services.mocks import (
    classify_note_para,
    generate_para_proposal,
    extract_entities
)

# L1
para_type = classify_note_para("Test note")
assert para_type == "Project"

# L2
proposal = generate_para_proposal("Test note")
assert proposal.primary_candidate.confidence == 0.80

# L3
entities = extract_entities("Content", {"name": "Test"})
assert len(entities) == 2
```

### 2. Integration тест

Запустите тестовый скрипт:
```bash
cd backend
python scripts/test_iteration5_workflow.py
```

### 3. Neo4j Browser проверка

После запуска workflow проверьте:
```cypher
// Проверить :SUGGESTS
MATCH (e:Episodic)-[r:SUGGESTS]->(p:Project)
RETURN r.suggestion_id, r.suggestion_type, r.confidence;

// Проверить Entity
MATCH (e:Entity)
WHERE e.uuid STARTS WITH "mock-entity-"
RETURN e.name, e.summary;
```

---

## Troubleshooting

### Mock project not found

**Проблема:** `ProposalManager` не может создать `:SUGGESTS` к `mock-project-alpha`

**Решение:** Создайте проект перед тестированием:
```python
from app.crud.para_crud import PARAContainerCRUD
crud = PARAContainerCRUD()
crud.create_project("mock-project-alpha", "Mock Project Alpha", "active")
```

### Context not in entity summary

**Проблема:** Entity summaries не содержат имя контейнера

**Проверка:** Убедитесь что `:IS_PART_OF` существует перед извлечением:
```cypher
MATCH (e:Episodic {name: "Notes/test.md"})-[:IS_PART_OF]->(p)
RETURN p.name;
```

### Import errors

**Проблема:** `ImportError: cannot import name 'classify_note_para'`

**Проверка:** Убедитесь что все `__init__.py` правильно настроены:
- `app/services/mocks/__init__.py`
- `app/services/para/__init__.py`

---

## Структура директории

```
app/services/
├── mocks/
│   ├── __init__.py              # Экспорт всех mock функций
│   ├── README.md                # Эта документация
│   ├── mock_classifier.py       # L1: PARA classification
│   ├── mock_proposal_generator.py  # L2: Proposal generation
│   └── mock_graphiti.py         # L3: Entity extraction
├── para/
│   └── __init__.py              # Переключатель mock/real для L1+L2
├── llm/
│   ├── real_classifier.py       # (будущее) Real L1
│   └── real_proposal_generator.py  # (будущее) Real L2
└── graphiti/
    └── real_graphiti.py         # (будущее) Real L3
```

---

## Принципы mock-данных

1. **Простота:** Минимум полей, только необходимые атрибуты
2. **Детерминизм:** Всегда одни и те же данные для одинаковых входов
3. **Реалистичность:** Структура соответствует реальным Pydantic моделям
4. **Отладка:** Понятные названия (`"Mock Project Alpha"`, `"mock-entity-001"`)

---

## Связанная документация

- [MOCK_IMPLEMENTATION_CHECKLIST.md](../../../TODO/response_flow_plan_v02/MOCK_IMPLEMENTATION_CHECKLIST.md) - Полный checklist разработки
- [neo4j_verification_queries.md](../../../docs/neo4j_verification_queries.md) - Cypher запросы для проверки
- [03_DATA_STRUCTURES.md](../../../TODO/response_flow_plan_v02/03_DATA_STRUCTURES.md) - Схема данных

---

**Готово к миграции на реальные LLM!** 🚀
