# Response Flow MVP - Progress Checklist

**Дата начала:** _____
**Дата завершения:** _____
**Текущая итерация:** Iteration 1

---

## Общий прогресс

- [ ] **Iteration 1:** Database Setup & Foundation (1-2 дня)
- [ ] **Iteration 2:** L1/L2 PARA Identification (2-3 дня)
- [ ] **Iteration 3:** User Interaction Flow (2 дня)
- [ ] **Iteration 4:** L3 Context-Aware Extraction (2-3 дня)
- [ ] **Iteration 5:** Integration & End-to-End Testing (1-2 дня)

**Итого:** 0/5 итераций завершено

---

## Iteration 1: Database Setup & Foundation

**Цель:** Развернуть Neo4j схему, создать базовые CRUD операции.
**Статус:** 🔴 Not Started
**Длительность:** 1-2 дня

### 1.1 Neo4j Schema Definition
**Файл:** `app/services/graph_schema.py`

- [ ] Создать constraints для уникальности:
  - [ ] `Episodic.path` (UNIQUE)
  - [ ] `Project.id` (UNIQUE)
  - [ ] `Area.id` (UNIQUE)
  - [ ] `Resource.id` (UNIQUE)
- [ ] Создать индексы для производительности:
  - [ ] `Entity.uuid` (INDEX)
  - [ ] `UserCheckStatus.id` (INDEX)
- [ ] Запустить миграцию на пустой Neo4j
- [ ] Проверить наличие constraints через `SHOW CONSTRAINTS`

### 1.2 PARA Container CRUD
**Файл:** `app/crud/para_crud.py`

- [ ] Создать класс `PARAContainerCRUD`
- [ ] Реализовать методы:
  - [ ] `create_project(project_id, name, status)`
  - [ ] `create_area(area_id, name)`
  - [ ] `create_resource(resource_id, name)`
  - [ ] `get_project(project_id)`
  - [ ] `get_area(area_id)`
  - [ ] `get_resource(resource_id)`
  - [ ] `list_projects(status=None)`
  - [ ] `list_areas()`
  - [ ] `list_resources()`
- [ ] Написать unit тесты:
  - [ ] `test_create_project()`
  - [ ] `test_list_projects_by_status()`
  - [ ] `test_get_nonexistent_project()`

### 1.3 Episodic CRUD
**Файл:** `app/crud/episodic_crud.py`

- [ ] Создать класс `EpisodicCRUD`
- [ ] Реализовать методы:
  - [ ] `create_episodic(path, created_at, updated_at)`
  - [ ] `get_episodic(path)`
  - [ ] `update_episodic_timestamp(path, updated_at)`
- [ ] Убедиться: НЕТ поля `project_id` в узле `Episodic`
- [ ] Написать unit тесты:
  - [ ] `test_create_episodic()`
  - [ ] `test_get_episodic_by_path()`
  - [ ] `test_update_episodic_timestamp()`

### 1.4 Relationship CRUD
**Файл:** `app/crud/relationship_crud.py`

- [ ] Создать класс `RelationshipCRUD`
- [ ] Реализовать методы:
  - [ ] `link_episodic_to_container(episodic_path, container_id, container_type)`
  - [ ] `get_episodic_para_context(episodic_path)` → `{"id": "...", "name": "...", "type": "..."}`
- [ ] Написать unit тесты:
  - [ ] `test_link_episodic_to_project()`
  - [ ] `test_get_episodic_para_context()`
  - [ ] `test_get_context_for_unlinked_episodic()` → None

### Definition of Done (Iteration 1)

- [ ] ✅ Neo4j schema создана (constraints, indexes)
- [ ] ✅ CRUD операции работают для PARA контейнеров и Episodic узлов
- [ ] ✅ Связь `:IS_PART_OF` создается и читается через граф
- [ ] ✅ Unit тесты проходят для всех CRUD методов
- [ ] ✅ Integration тест: `Project → Episodic → link → get_para_context → verify`

---

## Iteration 2: L1/L2 PARA Identification

**Цель:** Реализовать Top-Down идентификацию контекста для заметки.
**Статус:** 🔴 Not Started
**Длительность:** 2-3 дня

### 2.1 PARA Type Classification
**Файл:** `app/services/pipgraph_manager.py`

- [ ] Реализовать метод `classify_note_para(note_content)`:
  - [ ] Интеграция с OpenRouter API
  - [ ] Промпт для классификации: Project/Area/Resource
  - [ ] Structured output (JSON): `{"para_type": "...", "reasoning": "..."}`
  - [ ] Модель: `anthropic/claude-3.5-sonnet`
- [ ] Написать тесты:
  - [ ] `test_classify_note_para_project()` (mock LLM)
  - [ ] `test_classify_note_para_area()`

### 2.2 Similarity Search
**Файл:** `app/services/pipgraph_manager.py`

- [ ] Реализовать метод `find_similar_containers(note_content, para_type, top_k=3)`:
  - [ ] Получить embedding для note_content
  - [ ] Получить все контейнеры типа `para_type` из Neo4j
  - [ ] Вычислить cosine similarity для каждого
  - [ ] Вернуть top-K
- [ ] Настроить embeddings:
  - [ ] Модель: `text-embedding-3-small` или аналог через OpenRouter
  - [ ] Хранение в памяти (в MVP нет кэша в Neo4j)
- [ ] Написать тест:
  - [ ] `test_find_similar_containers()` (mock embeddings)

### 2.3 Proposal Generation
**Файл:** `app/services/pipgraph_manager.py`

- [ ] Создать Pydantic модели:
  - [ ] `PARACandidate(id, name, confidence)`
  - [ ] `PARAProposal(para_type, primary_candidate, alternatives, reasoning)`
- [ ] Реализовать метод `generate_para_proposal(note_content)`:
  - [ ] Classify PARA type
  - [ ] Find similar containers
  - [ ] LLM decision: выбор лучшего контейнера
  - [ ] Return structured proposal
- [ ] Написать тесты:
  - [ ] `test_generate_para_proposal()` (mock LLM)
  - [ ] `test_proposal_has_alternatives()`

### 2.4 Simple Linking (без User Interaction)
**Файл:** `app/services/pipgraph_manager.py`

- [ ] Реализовать метод `auto_link_episodic(episodic_path, container_id, container_type)`:
  - [ ] Вызвать `relationship_crud.link_episodic_to_container()`
  - [ ] Логировать решение
  - [ ] Использовать только если confidence > 95%
- [ ] Написать тест:
  - [ ] `test_auto_link_episodic()`

### Definition of Done (Iteration 2)

- [ ] ✅ PARA type классификация работает (LLM возвращает Project/Area/Resource)
- [ ] ✅ Similarity search находит топ-3 похожих контейнеров
- [ ] ✅ Proposal generation создает структурированное предложение
- [ ] ✅ Auto-link работает для high-confidence случаев
- [ ] ✅ Integration тест: `episodic → classify → find_similar → generate_proposal → auto_link` (mock LLM)

---

## Iteration 3: User Interaction Flow

**Цель:** Добавить прерывания workflow и обработку решений пользователя.
**Статус:** 🔴 Not Started
**Длительность:** 2 дня

### 3.1 UserCheckStatus CRUD
**Файл:** `app/crud/user_check_crud.py`

- [ ] Создать класс `UserCheckCRUD`
- [ ] Реализовать методы:
  - [ ] `create_check(check_id, timestamp, status, outcome, comment)`
  - [ ] `link_check_to_episodic(check_id, episodic_path, is_current=True)`
  - [ ] `get_current_check_for_episodic(episodic_path)`
- [ ] Написать тесты:
  - [ ] `test_create_check()`
  - [ ] `test_get_current_check_for_episodic()`

### 3.2 Decision Processing
**Файл:** `app/services/pipgraph_manager.py`

- [ ] Создать Pydantic модель `UserDecisionPayload`:
  - [ ] `action: str` (confirm/link_to_alternative/create_custom/dismiss)
  - [ ] `selected_container_id: Optional[str]`
  - [ ] `custom_container_name: Optional[str]`
  - [ ] `comment: Optional[str]`
- [ ] Реализовать метод `process_linking_decision(episodic_path, user_decision)`:
  - [ ] Create UserCheckStatus node
  - [ ] Link check to episodic with `[:HAS_CHECK]`
  - [ ] Execute action (link or create+link)
  - [ ] Return workflow control
- [ ] Написать тесты:
  - [ ] `test_process_decision_confirm()`
  - [ ] `test_process_decision_alternative()`
  - [ ] `test_process_decision_create_custom()`

### 3.3 LangGraph Interrupt Node
**Файл:** `app/workflows/note_workflow.py`

- [ ] Создать узел `wait_for_user_context_decision(state)`:
  - [ ] Save proposal to state
  - [ ] Create pending check
  - [ ] Return state (LangGraph handles interrupt)
- [ ] Настроить LangGraph config:
  - [ ] `workflow.add_node("wait_for_context_decision", ...)`
  - [ ] `workflow.add_edge("identify_context_node", "wait_for_context_decision")`
  - [ ] Conditional edge: check if decision received
- [ ] Написать тесты:
  - [ ] `test_interrupt_creates_pending_check()`
  - [ ] `test_resume_after_decision()` (mock resume)

### 3.4 JSON Payload Format
**Файл:** `app/api/schemas/notification_schema.py`

- [ ] Создать Pydantic схемы:
  - [ ] `ContextProposalNotification(notification_type, episodic_path, proposal, actions)`
  - [ ] `ActionButton(id, label, style)`
- [ ] Написать тесты:
  - [ ] `test_notification_schema_valid()`
  - [ ] `test_actions_have_labels()`

### Definition of Done (Iteration 3)

- [ ] ✅ UserCheckStatus узлы создаются при interrupt
- [ ] ✅ User decision обрабатывается (confirm/alternative/create_custom)
- [ ] ✅ LangGraph interrupt/resume работает (mock workflow test)
- [ ] ✅ JSON payload соответствует схеме для фронтенда
- [ ] ✅ Integration тест: `interrupt → save check → resume with decision → verify link`

---

## Iteration 4: L3 Context-Aware Extraction

**Цель:** Извлекать сущности с учетом контекста проекта через Graphiti.
**Статус:** 🔴 Not Started
**Длительность:** 2-3 дня

### 4.1 Context Injection
**Файл:** `app/services/pipgraph_manager.py`

- [ ] Реализовать метод `extract_entities_with_context(episodic_path, episodic_content)`:
  - [ ] Get PARA context for episodic (via `relationship_crud`)
  - [ ] Build context prompt: `"Context: This note belongs to Project '...'"
  - [ ] Call Graphiti with context-injected prompt
  - [ ] Return extracted entities
- [ ] Настроить Graphiti SDK:
  - [ ] Инициализация: `Graphiti(uri=NEO4J_URI, ...)`
  - [ ] Метод: `graphiti.add_episode(content, context=...)`
- [ ] Написать тесты:
  - [ ] `test_extract_with_context()` (mock Graphiti)
  - [ ] `test_extract_without_para_context()` (пустой контекст)

### 4.2 Schema Whitelist Configuration
**Файл:** `app/config/graphiti_config.py`

- [ ] Создать конфигурацию:
  - [ ] `ALLOWED_ENTITY_LABELS = ["Concept", "Person", "Task", "Decision"]`
  - [ ] `GRAPHITI_EXTRACTION_PROMPT` с инструкциями
- [ ] Настроить Graphiti client:
  - [ ] `graphiti_client.set_allowed_labels(ALLOWED_ENTITY_LABELS)`
- [ ] Написать тест:
  - [ ] `test_whitelist_filters_generic_entities()` (даты не извлекаются)

### 4.3 Entity Saving
**Файл:** `app/crud/entity_crud.py`

- [ ] Создать класс `EntityCRUD`
- [ ] Реализовать методы:
  - [ ] `save_entity(uuid, name, labels, summary)`
  - [ ] `link_entity_to_episodic(entity_uuid, episodic_path)`
  - [ ] `batch_save_entities(entities, episodic_path)`
- [ ] Убедиться: НЕТ поля `status` в узле `Entity`
- [ ] Написать тесты:
  - [ ] `test_save_entity()`
  - [ ] `test_batch_save_entities()`

### 4.4 Entity Confirmation Flow
**Файл:** `app/services/pipgraph_manager.py`

- [ ] Реализовать метод `confirm_entities(episodic_path, entity_uuids)`:
  - [ ] Create UserCheckStatus for each entity
  - [ ] Link check to entity with `[:HAS_CHECK]`
- [ ] Написать тест:
  - [ ] `test_confirm_entities()`

### Definition of Done (Iteration 4)

- [ ] ✅ Context injection работает (Graphiti получает project name в промпте)
- [ ] ✅ Schema whitelist фильтрует лишние типы сущностей
- [ ] ✅ Entity nodes сохраняются в граф с правильными labels
- [ ] ✅ Связь `:MENTIONS` создается между Episodic и Entity
- [ ] ✅ Entity confirmation создает `[:HAS_CHECK]` связи
- [ ] ✅ Integration тест: `extract → save entities → confirm → verify graph structure`

---

## Iteration 5: Integration & End-to-End Testing

**Цель:** Связать все части, протестировать полный цикл, зафиксировать баги.
**Статус:** 🔴 Not Started
**Длительность:** 1-2 дня

### 5.1 Complete Workflow Assembly
**Файл:** `app/workflows/note_workflow.py`

- [ ] Создать LangGraph граф:
  - [ ] Добавить узлы:
    - [ ] `identify_context`
    - [ ] `wait_context_decision`
    - [ ] `commit_link`
    - [ ] `extract_content`
    - [ ] `confirm_entities`
  - [ ] Настроить edges:
    - [ ] `identify_context → wait_context_decision`
    - [ ] `wait_context_decision → commit_link`
    - [ ] `commit_link → extract_content`
    - [ ] `extract_content → confirm_entities`
    - [ ] `confirm_entities → END`
  - [ ] Скомпилировать workflow
- [ ] Написать тест:
  - [ ] `test_workflow_graph_structure()`

### 5.2 E2E Test Scenario
**Файл:** `tests/e2e/test_episodic_processing_flow.py`

- [ ] Создать полный E2E тест `test_full_episodic_processing_cycle()`:
  - [ ] Setup: Create test Project in Neo4j
  - [ ] Submit episodic for processing
  - [ ] Verify L1/L2: Workflow interrupts with proposal
  - [ ] Mock user decision: "confirm"
  - [ ] Verify Link: Episodic has `[:IS_PART_OF]` → Project
  - [ ] Verify Extraction: Entities extracted with context
  - [ ] Verify Graph state:
    - [ ] Entities have `[:MENTIONS]` ← Episodic
    - [ ] Entities have `[:HAS_CHECK]` → UserCheckStatus

### 5.3 Error Handling
**Файл:** `app/workflows/note_workflow.py`

- [ ] Добавить try/except в узлы:
  - [ ] `identify_context_node` - обработка LLM failures
  - [ ] `extract_content_node` - обработка Graphiti errors
  - [ ] Создать fallback logic для ошибок
- [ ] Написать тест:
  - [ ] `test_error_handling_llm_failure()` (mock LLM exception)

### 5.4 Logging & Observability
**Файл:** `app/utils/workflow_logger.py`

- [ ] Настроить логирование:
  - [ ] Создать `logger = logging.getLogger("pipgraph.workflow")`
  - [ ] Функция `log_workflow_step(step_name, state)`
- [ ] Добавить логи в узлы:
  - [ ] `identify_context_node`
  - [ ] `extract_content_node`
  - [ ] `confirm_entities_node`
- [ ] Написать тест:
  - [ ] `test_workflow_logs_steps()` (caplog fixture)

### 5.5 Documentation & Examples
**Файл:** `backend/docs/WORKFLOW_EXAMPLES.md`

- [ ] Создать примеры использования:
  - [ ] Example 1: Basic episodic processing
  - [ ] Example 2: Resume after interrupt
  - [ ] Example 3: Error handling

### Definition of Done (Iteration 5)

- [ ] ✅ LangGraph workflow собран и скомпилирован
- [ ] ✅ E2E тест проходит для happy path
- [ ] ✅ Error handling работает для LLM failures
- [ ] ✅ Логирование настроено для всех узлов
- [ ] ✅ Документация примеров создана
- [ ] ✅ No-Cache проверка: Cypher запросы подтверждают отсутствие cached полей

### Final Verification (Cypher Queries)

- [ ] Проверить: Episodic не имеет `project_id`:
  ```cypher
  MATCH (n:Episodic)
  RETURN keys(n)  // Должно быть: ["path", "created_at", "updated_at"]
  ```
- [ ] Проверить: Entity не имеет `status`:
  ```cypher
  MATCH (e:Entity)
  RETURN keys(e)  // Должно быть: ["uuid", "name", "labels", "summary"]
  ```
- [ ] Проверить: все связи на месте:
  ```cypher
  MATCH (n:Episodic)-[:IS_PART_OF]->(p:Project)
  MATCH (n)-[:MENTIONS]->(e:Entity)
  MATCH (e)-[:HAS_CHECK]->(c:UserCheckStatus)
  RETURN count(*)
  ```

---

## Критерии успеха MVP

- [ ] ✅ Работает базовый цикл: `Episodic → L1/L2 → User Confirmation → Link to PARA → L3 → Save Entities`
- [ ] ✅ Нет тупиков: каждое прерывание дает пользователю конструктивные опции
- [ ] ✅ Чистый граф:
  - [ ] Нет дублированных данных в свойствах узлов
  - [ ] Вся информация в связях (`:IS_PART_OF`, `:HAS_CHECK`)
- [ ] ✅ Контекст работает:
  - [ ] Graphiti получает имя проекта в промпте
  - [ ] Извлечение меняется в зависимости от контекста

---

## Полезные команды

### Запуск тестов
```bash
# Unit тесты (iteration 1, 2)
pytest -m unit

# Integration тесты (iteration 3, 4)
pytest -m integration

# E2E тесты (iteration 5)
pytest tests/e2e/

# Все тесты кроме медленных
pytest -m "not slow"
```

### Neo4j проверки
```bash
# Показать constraints
SHOW CONSTRAINTS

# Показать индексы
SHOW INDEXES

# Очистить БД (dev only!)
MATCH (n) DETACH DELETE n
```

---

## Заметки и блокеры

**Iteration 1:**
-

**Iteration 2:**
-

**Iteration 3:**
-

**Iteration 4:**
-

**Iteration 5:**
-

---

## Ссылки на документацию

- [README.md](./README.md) - Обзор плана
- [01_MVP_SCOPE.md](./01_MVP_SCOPE.md) - Границы MVP
- [02_IMPLEMENTATION_STEPS.md](./02_IMPLEMENTATION_STEPS.md) - Детальные шаги
- [03_DATA_STRUCTURES.md](./03_DATA_STRUCTURES.md) - Модели данных
- [04_WORKFLOW_STATES.md](./04_WORKFLOW_STATES.md) - LangGraph граф
- [05_TESTING_STRATEGY.md](./05_TESTING_STRATEGY.md) - Стратегия тестирования
