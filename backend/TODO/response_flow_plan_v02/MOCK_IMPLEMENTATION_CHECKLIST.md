# Mock Implementation Checklist

**Дата создания:** 2025-11-19
**Версия:** 1.0
**Статус:** Ready for Development
**Подход:** Mock-First Development

---

## Обоснование Mock-подхода

### Почему Mock-First?

✅ **Быстрая итерация**
- Нет задержек на LLM API (экономия времени и денег)
- Мгновенная проверка результатов в Neo4j Browser
- Детерминированные данные → легче отладка

✅ **Фокус на архитектуре**
- Проверяем схему данных (:SUGGESTS с suggestion_id, множественные ребра)
- Отлаживаем CRUD операции
- Видим реальную структуру графа

✅ **Постепенная миграция**
- Начинаем с моков
- Постепенно заменяем компоненты на реальные LLM вызовы
- Сначала L1, потом L2, потом L3

---

## Mock Data Strategy

### Что возвращают mock-методы?

| Mock Module | Возвращаемые данные | Цель |
|-------------|-------------------|------|
| `mock_classifier.py` | `{"para_type": "Project", "confidence": 0.85}` | Проверить L1 логику |
| `mock_proposal_generator.py` | `PARAProposal` с 2 candidates:<br/>1. Link (conf: 0.8)<br/>2. Property update "name" (conf: 0.75) | Проверить множественные :SUGGESTS |
| `mock_graphiti.py` | Список из 2-3 `Entity` объектов | Проверить :MENTIONS связи |

### Принципы mock-данных

1. **Простота**: Минимум полей, только необходимые атрибуты
2. **Детерминизм**: Всегда одни и те же данные для одинаковых входов
3. **Реалистичность**: Структура соответствует реальным Pydantic моделям
4. **Отладка**: Понятные названия (`"Mock Project Alpha"`, `suggestion-uuid-link-001`)

---

## ITERATION 1: Neo4j Schema & CRUD Foundation

**Цель:** Развернуть Neo4j схему, создать базовые CRUD операции для узлов и связей с поддержкой детализированных предложений.

**Длительность:** 1-2 дня

### Задачи

#### 1.1 Neo4j Schema Setup
**Файл:** `app/db/schema.py` или migration script

- [x] Создать constraint для `Episode.name` (UNIQUE)
- [x] Создать constraint для `Project.id` (UNIQUE)
- [x] Создать constraint для `Area.id` (UNIQUE)
- [x] Создать constraint для `Resource.id` (UNIQUE)
- [x] Создать index для `Entity.uuid`
- [x] **ВАЖНО:** Создать index для `SUGGESTS.suggestion_id`
- [x] Выполнить все Cypher команды на локальном Neo4j (Neo4j Browser или скрипт)
- [x] 🔍 Проверить через `SHOW CONSTRAINTS` и `SHOW INDEXES`

**Cypher для проверки:**
```cypher
SHOW CONSTRAINTS;
SHOW INDEXES;
```

---

#### 1.2 PARA Container CRUD
**Файл:** `app/crud/para_crud.py`

- [x] Создать класс `PARAContainerCRUD`
- [x] Реализовать `create_project(project_id, name, status)`
- [x] Реализовать `create_area(area_id, name)`
- [x] Реализовать `create_resource(resource_id, name)`
- [x] Реализовать `get_project(project_id)`
- [x] Реализовать `list_projects(status=None)`
- [x] Реализовать `ensure_inbox_exists()` (дефолтная Area "Inbox")
- [ ] 🔍 Создать Project вручную, проверить в Neo4j Browser

**Cypher для проверки:**
```cypher
// Проверить созданный проект
MATCH (p:Project {id: "test-proj-1"}) RETURN p;

// Проверить Inbox
MATCH (a:Area {name: "Inbox"}) RETURN a;
```

---

#### 1.3 Episodic CRUD
**Файл:** `app/crud/episodic_crud.py`

- [x] Создать класс `EpisodicCRUD`
- [x] Реализовать `create_episodic(path, created_at, updated_at)`
- [x] Реализовать `get_episodic(path)`
- [x] Реализовать `update_episodic_timestamp(path, updated_at)`
- [x] **ВАЖНО:** Убедиться, что в Episode узле НЕТ поля `project_id`
- [ ] 🔍 Создать Episode, проверить структуру узла

**Cypher для проверки:**
```cypher
// Проверить Episode без project_id
MATCH (e:Episode {name: "Notes/test.md"}) RETURN properties(e);
```

---

#### 1.4 Relationship CRUD (Ключевая часть!)
**Файл:** `app/crud/relationship_crud.py`

- [x] Создать класс `RelationshipCRUD`
- [x] Реализовать `create_suggestion(...)` с параметрами:
  - `episodic_path`
  - `container_id`
  - `suggestion_id` (UUID)
  - `confidence`
  - `reasoning`
  - `suggestion_type` ("link" | "property_update")
  - `target_field` (опционально)
  - `suggested_value` (опционально)
- [x] Реализовать `get_suggestions(episodic_path)` → список всех :SUGGESTS
- [x] Реализовать `get_suggestion_by_id(suggestion_id)` → конкретное ребро
- [x] Реализовать `remove_suggestion(suggestion_id)` → удаление по UUID
- [x] Реализовать `create_link(episodic_path, container_id)` → :IS_PART_OF
- [x] Реализовать `get_episodic_para_context(episodic_path)` → контекст из :IS_PART_OF
- [ ] 🔍 Создать 2 разных :SUGGESTS между Episode и Project
- [ ] 🔍 Проверить, что оба ребра существуют с разными suggestion_id

**Cypher для проверки:**
```cypher
// Проверить множественные :SUGGESTS
MATCH (e:Episode {name: "Notes/test.md"})-[r:SUGGESTS]->(p:Project)
RETURN r.suggestion_id, r.suggestion_type, r.target_field
ORDER BY r.suggestion_id;

// Должно вернуть 2 ребра: одно "link", другое "property_update"
```

---

### Definition of Done (Iteration 1)

- [x] ✅ Neo4j schema создана (constraints, indexes)
- [x] ✅ CRUD операции работают для PARA контейнеров и Episode
- [x] ✅ Связи :SUGGESTS поддерживают множественность
- [x] ✅ Можно создать/удалить конкретное ребро по suggestion_id
- [x] ✅ get_episodic_para_context возвращает только :IS_PART_OF (игнорирует :SUGGESTS)

---

## ITERATION 2: Mock L1/L2 PARA Identification

**Цель:** Реализовать Top-Down идентификацию контекста с созданием детализированных предложений. **Все LLM вызовы заменены моками.**

**Длительность:** 1-2 дня

### Задачи

#### 2.1 Mock Infrastructure Setup
**Файлы:**
- `app/services/mocks/__init__.py`
- `app/config.py` (добавить USE_MOCKS)

- [ ] Создать директорию `app/services/mocks/`
- [ ] Создать `__init__.py` в mocks
- [ ] Добавить в `app/config.py`:
  ```python
  class Settings(BaseSettings):
      USE_MOCKS: bool = Field(default=True)
      # ... остальные настройки
  ```
- [ ] 🔍 Проверить импорт: `from app.services.mocks import mock_classifier`

---

#### 2.2 Mock Classifier (L1)
**Файл:** `app/services/mocks/mock_classifier.py`

- [ ] Создать функцию `classify_note_para(note_content: str) -> str`
- [ ] Всегда возвращает `"Project"` (или выбор на основе ключевых слов в content)
- [ ] **Простая реализация:**
  ```python
  def classify_note_para(note_content: str) -> str:
      """Mock L1: всегда возвращает 'Project'."""
      return "Project"
  ```
- [ ] 🔍 Вызвать функцию, проверить результат

---

#### 2.3 Mock Proposal Generator (L2)
**Файл:** `app/services/mocks/mock_proposal_generator.py`

- [ ] Создать функцию `generate_para_proposal(note_content: str) -> PARAProposal`
- [ ] Возвращает `PARAProposal` с:
  - `primary_candidate`: Link предложение (confidence: 0.8)
  - `alternatives[0]`: Property update "name" (confidence: 0.75)
- [ ] **Простая реализация:**
  ```python
  from app.models.proposal import PARAProposal, PARACandidate

  def generate_para_proposal(note_content: str) -> PARAProposal:
      """Mock L2: возвращает предложение с Link + Rename."""
      return PARAProposal(
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
- [ ] 🔍 Вызвать функцию, проверить структуру PARAProposal

---

#### 2.4 Apply Proposal to Graph
**Файл:** `app/services/pipgraph_manager.py`

- [ ] Создать класс `PipGraphManager`
- [ ] Реализовать `apply_proposal_to_graph(episodic_path, proposal)`
- [ ] Логика:
  - Iterates through `primary_candidate` + `alternatives`
  - Для каждого candidate:
    - Генерирует UUID для `suggestion_id`
    - Если `confidence > 0.95` И `type == "link"` → создает :IS_PART_OF
    - Иначе → создает :SUGGESTS со всеми атрибутами
- [ ] Использовать `relationship_crud.create_suggestion()` и `create_link()`
- [ ] 🔍 Применить proposal, проверить в Neo4j Browser 2 ребра :SUGGESTS

**Cypher для проверки:**
```cypher
// Проверить предложения после apply_proposal
MATCH (e:Episode {name: "Notes/test.md"})-[r:SUGGESTS]->(p)
RETURN r.suggestion_id, r.suggestion_type, r.confidence, r.target_field, r.suggested_value;
```

---

#### 2.5 Integration with Config
**Файл:** `app/services/pipgraph_manager.py`

- [ ] Добавить conditional import:
  ```python
  from app.config import settings

  if settings.USE_MOCKS:
      from app.services.mocks.mock_classifier import classify_note_para
      from app.services.mocks.mock_proposal_generator import generate_para_proposal
  else:
      from app.services.llm.real_classifier import classify_note_para
      from app.services.llm.real_proposal_generator import generate_para_proposal
  ```
- [ ] 🔍 Переключить USE_MOCKS=True/False, проверить импорт

---

### Definition of Done (Iteration 2)

- [ ] ✅ Mock инфраструктура создана (директория, config переключатель)
- [ ] ✅ Mock classifier возвращает "Project"
- [ ] ✅ Mock proposal generator возвращает 2 candidates (link + rename)
- [ ] ✅ apply_proposal_to_graph создает правильные :SUGGESTS в Neo4j
- [ ] ✅ В Neo4j существует 2 ребра с разными suggestion_id

---

## ITERATION 3: Mock User Decisions & LangGraph Structure

**Цель:** Обработка решений пользователя на уровне конкретных связей (suggestions). Создание LangGraph workflow структуры (без полного запуска).

**Длительность:** 1-2 дня

### Задачи

#### 3.1 Decision Processing Logic
**Файл:** `app/services/pipgraph_manager.py`

- [ ] Реализовать `process_user_decision(episodic_path, user_decision: UserDecisionPayload)`
- [ ] Обработка `action="confirm"`:
  - [ ] Получить suggestion по `user_decision.suggestion_id`
  - [ ] Если `type == "link"`:
    - [ ] Delete :SUGGESTS
    - [ ] Create :IS_PART_OF
  - [ ] Если `type == "property_update"`:
    - [ ] Update свойство целевого узла (например, `SET p.name = r.suggested_value`)
    - [ ] Delete :SUGGESTS
- [ ] Обработка `action="dismiss"`:
  - [ ] Delete конкретное :SUGGESTS по suggestion_id
  - [ ] Если это было последнее link-предложение → Create :IS_PART_OF к Inbox
- [ ] Обработка `action="link_to_alternative"`:
  - [ ] Delete все :SUGGESTS
  - [ ] Create :IS_PART_OF к `user_decision.selected_container_id`
- [ ] Обработка `action="create_custom"`:
  - [ ] Create новый Project/Area
  - [ ] Delete все :SUGGESTS
  - [ ] Create :IS_PART_OF
- [ ] 🔍 Проверить каждый action в Neo4j Browser

**Cypher для проверки (confirm link):**
```cypher
// До: должно быть :SUGGESTS
MATCH (e:Episode {name: "Notes/test.md"})-[r:SUGGESTS {suggestion_id: "uuid-123"}]->(p)
RETURN r;

// После confirm: должно быть :IS_PART_OF
MATCH (e:Episode {name: "Notes/test.md"})-[r:IS_PART_OF]->(p)
RETURN r;
```

---

#### 3.2 LangGraph Nodes Structure
**Файл:** `app/workflows/note_workflow.py`

- [ ] Создать файл `app/workflows/state.py` с `NoteWorkflowState`
- [ ] Реализовать node: `identify_context_node(state)` (вызывает mock proposal generator)
- [ ] Реализовать node: `apply_proposal_node(state)` (вызывает apply_proposal_to_graph)
- [ ] Реализовать node: `wait_for_decision_node(state)` (Interrupt point, пока пустой)
- [ ] Реализовать node: `process_decision_node(state)` (вызывает process_user_decision)
- [ ] **Пока НЕ собираем граф**, только создаем функции
- [ ] 🔍 Проверить, что функции импортируются

---

#### 3.3 Conditional Logic
**Файл:** `app/workflows/conditions.py`

- [ ] Реализовать `check_suggestion_status(state) -> str`
- [ ] Логика:
  ```python
  suggestions = await relationship_crud.get_suggestions(state.note_path)
  if suggestions:
      return "wait_for_decision_node"

  context = await relationship_crud.get_episodic_para_context(state.note_path)
  if context:
      return "extract_content_node"

  raise ValueError("Invalid graph state")
  ```
- [ ] 🔍 Mock state, вызвать функцию, проверить возврат правильного next_node

---

### Definition of Done (Iteration 3)

- [ ] ✅ process_user_decision обрабатывает все actions
- [ ] ✅ Confirm link: :SUGGESTS трансформируется в :IS_PART_OF
- [ ] ✅ Confirm update: свойство Project обновляется, ребро удаляется
- [ ] ✅ Dismiss: конкретное ребро удаляется (по suggestion_id)
- [ ] ✅ LangGraph nodes структура создана (функции готовы)
- [ ] ✅ check_suggestion_status возвращает правильный next_node

---

## ITERATION 4: Mock L3 Context-Aware Extraction

**Цель:** Извлекать сущности с учетом контекста проекта. **Graphiti заменен моком.**

**Длительность:** 1-2 дня

### Задачи

#### 4.1 Mock Graphiti
**Файл:** `app/services/mocks/mock_graphiti.py`

- [ ] Создать функцию `extract_entities(episodic_content: str, context: dict) -> list[ExtractedCandidate]`
- [ ] Возвращает список из 2-3 Entity
- [ ] **Простая реализация:**
  ```python
  from app.models.entity import ExtractedCandidate

  def extract_entities(episodic_content: str, context: dict) -> list[ExtractedCandidate]:
      """Mock L3: возвращает фиксированный набор сущностей."""
      return [
          ExtractedCandidate(
              uuid="mock-entity-001",
              name="Mock Concept: User Authentication",
              labels=["Concept"],
              summary="Authentication system mentioned in note"
          ),
          ExtractedCandidate(
              uuid="mock-entity-002",
              name="Mock Task: Implement Login",
              labels=["Task"],
              summary="Task to implement login feature"
          )
      ]
  ```
- [ ] 🔍 Вызвать функцию, проверить структуру

**📌 Заметка о Entity labels:**
Когда Graphiti извлекает entities с указанными типами (через параметр `entity_types`), узлы создаются с composite labels: `:Entity:Concept`, `:Entity:Task` и т.д.

**Важно:** PARA узлы (`:Project`, `:Area`, `:Resource`) - это **отдельные узлы**, НЕ Entity! Не путайте:
- **PARA контейнеры:** `:Project`, `:Area`, `:Resource` (для организации заметок)
- **Extracted entities:** `:Entity:Concept`, `:Entity:Task` (извлеченные сущности из контента)

В mock реализации можно использовать простые Entity без типов (просто `:Entity`).

---

#### 4.2 Context Retrieval & Extraction
**Файл:** `app/services/pipgraph_manager.py`

- [ ] Реализовать `extract_entities_with_context(episodic_path, episodic_content)`
- [ ] Логика:
  1. Получить контекст: `context = relationship_crud.get_episodic_para_context(episodic_path)`
  2. Если нет контекста → raise Error
  3. Вызвать mock Graphiti: `entities = mock_graphiti.extract_entities(content, context)`
  4. Вернуть список entities
- [ ] **ВАЖНО:** Проверить, что context.name попадает в вызов (для будущего промпта)
- [ ] 🔍 Проверить, что функция читает контекст из графа

---

#### 4.3 Entity CRUD
**Файл:** `app/crud/entity_crud.py`

- [ ] Создать класс `EntityCRUD`
- [ ] Реализовать `save_entity_node(entity: ExtractedCandidate)`
- [ ] Реализовать `link_entity_to_episodic(episodic_path, entity_uuid, status="confirmed")`
- [ ] Реализовать `batch_save_entities(entities: list, episodic_path)`
- [ ] 🔍 Сохранить entities, проверить в Neo4j Browser

**Cypher для проверки:**
```cypher
// Проверить созданные Entity
MATCH (e:Entity) RETURN e.uuid, e.name LIMIT 5;

// Проверить Neo4j labels (могут быть composite если использовали entity_types)
MATCH (e:Entity) RETURN e.uuid, e.name, labels(e) LIMIT 3;
// Для mock данных будет просто ["Entity"]
// Для реального Graphiti с entity_types может быть ["Entity", "Concept"]

// Проверить связи :MENTIONS
MATCH (ep:Episodic {name: "Notes/test.md"})-[r:MENTIONS]->(e:Entity)
RETURN e.name, r.status;
```

---

#### 4.4 LangGraph Extraction Nodes
**Файл:** `app/workflows/note_workflow.py`

- [ ] Реализовать node: `extract_content_node(state)` (вызывает extract_entities_with_context)
- [ ] Реализовать node: `save_entities_node(state)` (вызывает entity_crud.batch_save_entities)
- [ ] 🔍 Проверить, что nodes импортируются

---

### Definition of Done (Iteration 4)

- [ ] ✅ Mock Graphiti возвращает список Entity
- [ ] ✅ extract_entities_with_context читает контекст из :IS_PART_OF
- [ ] ✅ Entity nodes сохраняются в Neo4j
- [ ] ✅ Связи :MENTIONS создаются с атрибутом status="confirmed"
- [ ] ✅ LangGraph extraction nodes готовы

---

## ITERATION 5: Integration & Manual Testing

**Цель:** Связать все части, собрать LangGraph workflow, создать скрипт для ручного тестирования полного цикла.

**Длительность:** 1-2 дня

### Задачи

#### 5.1 Complete LangGraph Workflow Assembly
**Файл:** `app/workflows/note_workflow.py`

- [ ] Собрать StateGraph:
  ```python
  from langgraph.graph import StateGraph, END

  workflow = StateGraph(NoteWorkflowState)
  workflow.add_node("identify_context", identify_context_node)
  workflow.add_node("apply_proposal", apply_proposal_node)
  workflow.add_node("wait_for_decision", wait_for_decision_node)
  workflow.add_node("process_decision", process_decision_node)
  workflow.add_node("extract_content", extract_content_node)
  workflow.add_node("save_entities", save_entities_node)
  ```
- [ ] Добавить edges:
  - [ ] Entry point: "identify_context"
  - [ ] "identify_context" → "apply_proposal"
  - [ ] "apply_proposal" → conditional (check_suggestion_status)
  - [ ] "wait_for_decision" → "process_decision"
  - [ ] "process_decision" → conditional (check_suggestion_status)
  - [ ] "extract_content" → "save_entities"
  - [ ] "save_entities" → END
- [ ] Скомпилировать: `compiled_workflow = workflow.compile()`
- [ ] 🔍 Проверить, что workflow компилируется без ошибок

---

#### 5.2 Manual Test Script
**Файл:** `scripts/test_mock_flow.py`

- [ ] Создать скрипт для ручного тестирования
- [ ] Структура скрипта:
  ```python
  # 1. Setup: создать Project "Mock Alpha" в Neo4j
  # 2. Step 1: запустить workflow с note_path и note_content
  # 3. Проверить: должен остановиться (interrupt)
  # 4. Вывести: список suggestions из графа
  # 5. Step 2: отправить decision "confirm" для link suggestion
  # 6. Проверить: :IS_PART_OF создан
  # 7. Step 3: отправить decision "confirm" для rename suggestion
  # 8. Проверить: Project переименован
  # 9. Step 4: workflow продолжается, извлекает entities
  # 10. Финал: проверить :MENTIONS в Neo4j
  ```
- [ ] 🔍 Запустить скрипт, проверить каждый шаг в Neo4j Browser

---

#### 5.3 Neo4j Verification Queries
**Файл:** `docs/neo4j_verification_queries.md`

- [ ] Создать документ с готовыми Cypher запросами для проверки:
  - [ ] Проверка структуры Episode (нет project_id)
  - [ ] Проверка множественных :SUGGESTS
  - [ ] Проверка трансформации :SUGGESTS → :IS_PART_OF
  - [ ] Проверка обновления свойств Project
  - [ ] Проверка :MENTIONS связей
  - [ ] Проверка чистоты графа (нет висячих узлов)

---

#### 5.4 Mock Documentation
**Файл:** `app/services/mocks/README.md`

- [ ] Создать документацию для mock-структуры:
  - [ ] Описание каждого мока
  - [ ] Какие данные возвращает
  - [ ] Как переключить на реальные LLM
  - [ ] План миграции (по компонентам)

---

### Definition of Done (Iteration 5)

- [ ] ✅ LangGraph workflow собран и компилируется
- [ ] ✅ Manual test script работает
- [ ] ✅ Полный цикл проверен вручную в Neo4j Browser
- [ ] ✅ Граф остается чистым после завершения
- [ ] ✅ Документация для моков создана

---

## Appendix A: Neo4j Verification Queries

### Проверка Episode (No-Cache Policy)
```cypher
// Episode должен быть БЕЗ поля project_id
MATCH (e:Episode {name: "Notes/test.md"})
RETURN properties(e);
// Ожидаем: name, content, created_at, valid_at, uuid, source
// НЕ должно быть: project_id
```

### Проверка множественных :SUGGESTS
```cypher
// Должно быть 2 ребра между Episode и Project
MATCH (e:Episode {name: "Notes/test.md"})-[r:SUGGESTS]->(p:Project)
RETURN r.suggestion_id, r.suggestion_type, r.confidence, r.target_field
ORDER BY r.suggestion_type;
// Ожидаем:
// 1. suggestion_type="link"
// 2. suggestion_type="property_update", target_field="name"
```

### Проверка трансформации :SUGGESTS → :IS_PART_OF
```cypher
// После confirm link
// :SUGGESTS с type="link" должно исчезнуть
MATCH (e:Episode {name: "Notes/test.md"})-[r:SUGGESTS {suggestion_type: "link"}]->(p:Project)
RETURN count(r) as link_suggestions;
// Ожидаем: 0

// :IS_PART_OF должно появиться
MATCH (e:Episode {name: "Notes/test.md"})-[r:IS_PART_OF]->(p:Project)
RETURN p.name;
// Ожидаем: "Mock Project Alpha"
```

### Проверка обновления свойств Project
```cypher
// После confirm property_update
MATCH (p:Project {id: "mock-project-alpha"})
RETURN p.name;
// Ожидаем: "Mock Project Alpha v2"

// :SUGGESTS с type="property_update" должно исчезнуть
MATCH (e:Episode)-[r:SUGGESTS {suggestion_type: "property_update"}]->(p:Project)
RETURN count(r) as update_suggestions;
// Ожидаем: 0
```

### Проверка :MENTIONS связей
```cypher
// Entities должны быть связаны с Episode
MATCH (e:Episode {name: "Notes/test.md"})-[r:MENTIONS]->(ent:Entity)
RETURN ent.name, ent.labels, r.status;
// Ожидаем: 2-3 Entity с status="confirmed"
```

### Проверка чистоты графа
```cypher
// Не должно быть Episode без контекста
MATCH (e:Episode)
WHERE NOT EXISTS((e)-[:IS_PART_OF]->())
RETURN e.name;
// Ожидаем: пустой результат (или только те, что в процессе обработки)

// Не должно быть старых :SUGGESTS после завершения
MATCH (e:Episode {name: "Notes/test.md"})-[r:SUGGESTS]->()
RETURN count(r) as remaining_suggestions;
// Ожидаем: 0 (после полного прохождения workflow)
```

---

## Appendix B: Migration Plan (Mock → Real LLM)

### Этап 1: L1 Classifier (Первый переход)
**Когда:** После успешной проверки архитектуры на моках

- [ ] Реализовать `app/services/llm/real_classifier.py`
- [ ] Использовать OpenRouter API для классификации PARA type
- [ ] Переключить `USE_MOCKS=False` только для классификатора
- [ ] Проверить, что остальные моки работают

### Этап 2: L2 Proposal Generator
**Когда:** После стабилизации L1

- [ ] Реализовать `app/services/llm/real_proposal_generator.py`
- [ ] Embeddings для поиска похожих контейнеров
- [ ] LLM для генерации PARAProposal (с множественными suggestions)
- [ ] Переключить L2 на реальный LLM

### Этап 3: L3 Graphiti Extraction
**Когда:** После стабилизации L1+L2

- [ ] Интегрировать Graphiti SDK
- [ ] Реализовать context injection в промпт
- [ ] Переключить L3 на реальный Graphiti
- [ ] Удалить все моки (или оставить для тестов)

### Конфигурация для поэтапной миграции
```python
# app/config.py
class Settings(BaseSettings):
    USE_MOCK_CLASSIFIER: bool = Field(default=False)
    USE_MOCK_PROPOSAL: bool = Field(default=False)
    USE_MOCK_GRAPHITI: bool = Field(default=False)
```

---

## Критерии успеха Mock MVP

### Функциональные критерии
- [ ] ✅ **Happy Path (Simple Link):**
  - Mock AI создает :SUGGESTS (link)
  - User confirms
  - Transform to :IS_PART_OF
  - Mock L3 Extraction

- [ ] ✅ **Complex Path (Link + Update):**
  - Mock AI создает 2 ребра :SUGGESTS
  - User confirms Link
  - User confirms Update (Project renamed)
  - Mock L3 Extraction (использует новое имя)

- [ ] ✅ **Alternative/Custom Path:**
  - User selects alternative
  - Old suggestions deleted
  - New context created

- [ ] ✅ **No-Cache проверка:**
  - В Episode узле нет поля project_id
  - Вся информация через traversal связей

### Технические критерии
- [ ] ✅ Все CRUD операции работают
- [ ] ✅ Множественные :SUGGESTS корректно создаются и удаляются
- [ ] ✅ LangGraph workflow компилируется
- [ ] ✅ Manual test script проходит полный цикл
- [ ] ✅ Граф остается чистым (нет висячих узлов, suggestions)

---

**Готово к старту! Начните с Iteration 1, Task 1.1** 🚀
