# Implementation Steps - Пошаговый план разработки

**Стратегия:** 5 итераций, каждая добавляет работающий слой функциональности.

---

## Iteration 1: Database Setup & Foundation
**Длительность:** 1-2 дня
**Цель:** Развернуть Neo4j схему, создать базовые CRUD операции для узлов и связей с поддержкой детализированных предложений (suggestions).

### Задачи

#### 1.1 Neo4j Schema Definition
**Файл:** `app/services/graph_schema.py` (или отдельный migration script)

**Что делаем:**
- Создаем constraints и индексы:
  ```cypher
  // Unique constraints
  CREATE CONSTRAINT episodic_path_unique IF NOT EXISTS
  FOR (n:Episodic) REQUIRE n.name IS UNIQUE;

  CREATE CONSTRAINT project_id_unique IF NOT EXISTS
  FOR (p:Project) REQUIRE p.id IS UNIQUE;

  CREATE CONSTRAINT area_id_unique IF NOT EXISTS
  FOR (a:Area) REQUIRE a.id IS UNIQUE;

  CREATE CONSTRAINT resource_id_unique IF NOT EXISTS
  FOR (r:Resource) REQUIRE r.id IS UNIQUE;

  // Indexes for performance
  CREATE INDEX entity_uuid_idx IF NOT EXISTS
  FOR (e:Entity) ON (e.uuid);

  // Index for searching specific suggestions
  CREATE INDEX suggestion_id_idx IF NOT EXISTS
  FOR ()-[r:SUGGESTS]-() ON (r.suggestion_id);
  ```

**Тест:**
- Запустить миграцию на пустой Neo4j.
- Проверить наличие constraints через `SHOW CONSTRAINTS`.

---

#### 1.2 PARA Container CRUD
**Файл:** `app/crud/para_crud.py`

**Методы:**
```python
class PARAContainerCRUD:
    def create_project(self, project_id: str, name: str, status: str = "active") -> dict
    def create_area(self, area_id: str, name: str) -> dict
    def create_resource(self, resource_id: str, name: str) -> dict

    def get_project(self, project_id: str) -> Optional[dict]
    def get_area(self, area_id: str) -> Optional[dict]
    def get_resource(self, resource_id: str) -> Optional[dict]

    def list_projects(self, status: Optional[str] = None) -> list[dict]
    def list_areas(self) -> list[dict]
    def list_resources(self) -> list[dict]

    def ensure_inbox_exists(self) -> dict
    # Создает дефолтную Area "Inbox" если её нет
```

**Cypher examples:**
```cypher
// Create Project
CREATE (p:Project {id: $id, name: $name, status: $status})
RETURN p

// Ensure Inbox
MERGE (a:Area {name: "Inbox"})
ON CREATE SET a.id = $generated_id
RETURN a
```

**Тесты:**
- `test_create_project()` - создает проект, проверяет свойства.
- `test_ensure_inbox()` - создает Inbox, повторный вызов не дублирует.

---

#### 1.3 Episodic CRUD
**Файл:** `app/crud/episodic_crud.py`

**Методы:**
```python
class EpisodicCRUD:
    def create_episodic(self, path: str, created_at: datetime, updated_at: datetime) -> dict
    def get_episodic(self, path: str) -> Optional[dict]
    def update_episodic_timestamp(self, path: str, updated_at: datetime) -> dict
```

**Важно:**
- В узле `Episodic` НЕТ поля `project_id`.
- Только: `name` (path), `created_at`, `valid_at`.

**Тесты:**
- `test_create_episodic()` - создает episodic с timestamps.
- `test_get_episodic_by_path()` - поиск по unique name.

---

#### 1.4 Relationship CRUD
**Файл:** `app/crud/relationship_crud.py`

**Методы:**
```python
class RelationshipCRUD:
    # Управление связью :SUGGESTS (Гипотеза)
    def create_suggestion(
        self,
        episodic_path: str,
        container_id: str,
        suggestion_id: str,
        confidence: float,
        reasoning: str,
        suggestion_type: str = "link",
        target_field: Optional[str] = None,
        suggested_value: Optional[str] = None
    ) -> None

    def get_suggestions(self, episodic_path: str) -> list[dict]
    # Возвращает список всех активных предложений для заметки
    # Returns: [{"suggestion_id": "...", "type": "link", "confidence": 0.9, ...}, ...]

    def get_suggestion_by_id(self, suggestion_id: str) -> Optional[dict]
    # Поиск конкретного ребра по UUID

    def remove_suggestion(self, suggestion_id: str) -> None
    # Удаляет конкретное ребро по ID

    # Управление связью :IS_PART_OF (Факт)
    def create_link(
        self,
        episodic_path: str,
        container_id: str
    ) -> None

    def get_episodic_para_context(self, episodic_path: str) -> Optional[dict]
    # Ищет только по связи :IS_PART_OF
    # Returns: {"id": "proj-123", "name": "Website Redesign", "type": "Project"}
```

**Cypher examples:**
```cypher
// Create Suggestion (Multiple edges allowed)
MATCH (n:Episodic {name: $episodic_path})
MATCH (c {id: $container_id}) WHERE c:Project OR c:Area OR c:Resource
MERGE (n)-[r:SUGGESTS {suggestion_id: $suggestion_id}]->(c)
SET r.confidence = $confidence, 
    r.reasoning = $reasoning,
    r.suggestion_type = $suggestion_type,
    r.target_field = $target_field,
    r.suggested_value = $suggested_value

// Transform Link Suggestion to Fact (Transaction)
MATCH (n:Episodic)-[r:SUGGESTS {suggestion_id: $suggestion_id}]->(c)
DELETE r
MERGE (n)-[:IS_PART_OF {created_at: datetime()}]->(c)

// Apply Property Update Suggestion
MATCH (n:Episodic)-[r:SUGGESTS {suggestion_id: $suggestion_id}]->(c)
SET c[r.target_field] = r.suggested_value
DELETE r
```

**Тесты:**
- `test_create_suggestion()` - создает связь `:SUGGESTS` с дополнительными атрибутами.
- `test_create_multiple_suggestions()` - проверяет создание двух разных ребер (link + update) между одними и теми же узлами.
- `test_create_link()` - создает связь `:IS_PART_OF`.
- `test_get_context_ignores_suggestion()` - `get_episodic_para_context` не должен возвращать то, что только предложено.

---

### Definition of Done (Iteration 1)

✅ **Neo4j schema создана** (constraints, indexes).
✅ **CRUD операции работают** для PARA контейнеров и Episodic узлов.
✅ **Связи `:SUGGESTS` поддерживают множественность** и атрибуты детализации (`suggestion_id`, `type`).
✅ **Unit тесты проходят** для всех CRUD методов.
✅ **Integration тест:** создать Project → создать Episodic → создать несколько suggestion (link, rename) → проверить наличие двух ребер → удалить одно по ID.

---

## Iteration 2: L1/L2 PARA Identification
**Длительность:** 2-3 дня
**Цель:** Реализовать Top-Down идентификацию контекста с созданием детализированных предложений.

### Задачи

#### 2.1 PARA Type Classification & Search
**Файл:** `app/services/pipgraph_manager.py`

**Методы:**
```python
async def classify_note_para(self, note_content: str) -> str:
    """Returns: "Project" | "Area" | "Resource" via LLM."""
    pass

async def find_similar_containers(
    self,
    note_content: str,
    para_type: str,
    top_k: int = 3
) -> list[dict]:
    """Returns top-K similar containers by embedding similarity."""
    pass
```

**Тест:**
- `test_classify_note_para()` - mock LLM response.
- `test_find_similar_containers()` - mock embeddings.

---

#### 2.2 Proposal Generation
**Файл:** `app/services/pipgraph_manager.py`

**Метод:**
```python
async def generate_para_proposal(
    self,
    note_content: str
) -> PARAProposal:
    """
    Создает предложение.
    Может возвращать список кандидатов, включая предложения по обновлению свойств.
    Returns: PARAProposal.
    """
    pass
```

**Тест:**
- `test_generate_para_proposal()` - проверяем структуру ответа, наличие `suggestion_type`.

---

#### 2.3 Suggestion Creation Logic
**Файл:** `app/services/pipgraph_manager.py`

**Метод:**
```python
async def apply_proposal_to_graph(
    self,
    episodic_path: str,
    proposal: PARAProposal
) -> None:
    """
    Применяет предложение к графу.
    
    Iterates through proposal.primary_candidate and alternatives:
    1. Generates unique UUID for each candidate.
    2. Logic:
       - Если confidence > 0.95 AND type == 'link':
         Вызвать relationship_crud.create_link() (Сразу :IS_PART_OF).
       - Иначе:
         Вызвать relationship_crud.create_suggestion() со всеми атрибутами (type, target_field, value).
    """
    pass
```

**Тест:**
- `test_apply_proposal_high_confidence_link()` - создает `:IS_PART_OF`.
- `test_apply_proposal_property_update()` - всегда создает `:SUGGESTS` (даже при высокой уверенности, так как изменение данных требует подтверждения).

---

### Definition of Done (Iteration 2)

✅ **PARA type классификация работает**.
✅ **Similarity search находит** контейнеры.
✅ **Proposal generation создает** структурированное предложение с типами действий.
✅ **Graph logic работает:** создаются правильные типы связей, `suggestion_id` генерируется и сохраняется.
✅ **Integration тест:** episodic → classify → proposal → check graph state (SUGGESTS edges with correct attributes).

---

## Iteration 3: User Interaction Flow
**Длительность:** 2 дня
**Цель:** Обработка решений пользователя на уровне конкретных связей (suggestions).

### Задачи

#### 3.1 Decision Processing Logic
**Файл:** `app/services/pipgraph_manager.py`

**Метод:**
```python
async def process_user_decision(
    self,
    episodic_path: str,
    user_decision: UserDecisionPayload
) -> None:
    """
    Обрабатывает решение пользователя.
    
    Args:
        user_decision: содержит action и опционально suggestion_id.

    Actions:
    - "confirm":
        Требует user_decision.suggestion_id.
        1. Получить тип suggestion из графа по ID.
        2. Если type == 'link': Transform :SUGGESTS -> :IS_PART_OF.
        3. Если type == 'property_update': Apply update to Target Node, Delete :SUGGESTS.
        4. Удалить остальные конфликтующие suggestions (если применимо).

    - "link_to_alternative":
        1. Удалить все текущие :SUGGESTS для этой заметки.
        2. Создать :IS_PART_OF к user_decision.selected_container_id.

    - "create_custom":
        1. Удалить все текущие :SUGGESTS.
        2. Создать новый Node (Project/Area).
        3. Создать :IS_PART_OF.

    - "dismiss":
        Если указан suggestion_id -> удалить только это ребро.
        Если suggestion_id не указан (или это единственное link-предложение) -> Fallback to Inbox.
    """
    pass
```

**Важно:** Все операции должны быть атомарными.

**Тест:**
- `test_process_confirm_link()` - трансформация связи по ID.
- `test_process_confirm_update()` - обновление поля проекта и удаление ребра.
- `test_process_dismiss_specific()` - удаление конкретного предложения.

---

#### 3.2 LangGraph Interrupt Node
**Файл:** `app/workflows/note_workflow.py`

**Узел:**
```python
def check_suggestion_status(state: NoteWorkflowState) -> str:
    """
    Проверяет статус графа.
    Logic:
    1. Есть ли связь :IS_PART_OF? -> Proceed ("extract_content_node").
    2. Есть ли связи :SUGGESTS? -> Interrupt ("wait_for_decision_node").
    """
    pass
```

**Логика:** Workflow останавливается, если в графе есть **любые** необработанные предложения (`:SUGGESTS`), которые блокируют определение контекста или требуют внимания.

**Тест:**
- `test_interrupt_if_suggestion_exists()`
- `test_proceed_if_linked()`

---

### Definition of Done (Iteration 3)

✅ **Decision processing корректно обрабатывает `suggestion_id`**.
✅ **Подтверждение update_property меняет данные узла**.
✅ **Episodic всегда имеет связь** (или Inbox) в конце процесса связывания.
✅ **Integration тест:** create link suggestion + update suggestion → confirm link → verify IS_PART_OF exists & update suggestion remains → confirm update → verify project renamed.

---

## Iteration 4: L3 Context-Aware Extraction
**Длительность:** 2-3 дня
**Цель:** Извлекать сущности с учетом контекста проекта (связь `:IS_PART_OF`).

### Задачи

#### 4.1 Context Retrieval
**Файл:** `app/services/pipgraph_manager.py`

**Метод:**
```python
async def extract_entities_with_context(
    self,
    episodic_path: str,
    episodic_content: str
) -> list[ExtractedCandidate]:
    """
    1. Получить контекст: MATCH (n {name: $path})-[:IS_PART_OF]->(c) RETURN c.name, labels(c).
    2. Сформировать промпт: "Context: Project 'Website Redesign'..."
    3. Вызвать Graphiti.
    """
    pass
```

**Тест:**
- `test_extract_uses_graph_context()` - проверяем, что имя проекта попало в промпт.

---

#### 4.2 Entity Saving (with Relationships)
**Файл:** `app/crud/entity_crud.py`

**Методы:**
```python
class EntityCRUD:
    def save_entity_node(self, entity: ExtractedCandidate) -> None

    def link_entity_to_episodic(
        self,
        episodic_path: str,
        entity_uuid: str,
        status: str = "confirmed"
    ) -> None
    # Создает связь: (n)-[:MENTIONS {status: $status}]->(e)
```

**Cypher examples:**
```cypher
MATCH (n:Episodic {name: $path})
MATCH (e:Entity {uuid: $uuid})
MERGE (n)-[r:MENTIONS]->(e)
SET r.status = $status
```

**Тест:**
- `test_save_entity_and_link()` - проверяем создание узла и связи с атрибутом.

---

### Definition of Done (Iteration 4)

✅ **Context injection работает:** Graphiti получает имя контейнера из графа.
✅ **Entity nodes сохраняются**.
✅ **Связи `:MENTIONS` создаются** с атрибутом `status="confirmed"`.
✅ **Integration тест:** link episodic to project → extract → verify entities linked to episodic.

---

## Iteration 5: Integration & End-to-End Testing
**Длительность:** 1-2 дня
**Цель:** Связать все части, протестировать полный цикл.

### Задачи

#### 5.1 Complete Workflow Assembly
**Файл:** `app/workflows/note_workflow.py`

**Граф:**
1. `identify_context` (L1/L2)
2. `apply_proposal`
3. `check_suggestion_status` (Conditional Interrupt)
4. `process_decision`
5. `extract_content` (L3)
6. `save_entities` (L3)

**Тест:**
- `test_workflow_structure()`

---

#### 5.2 E2E Test Scenario
**Файл:** `tests/e2e/test_episodic_processing_flow.py`

**Сценарий:**
1. **Setup:** Создать `Project "Alpha"`.
2. **Step 1:** Обработать заметку. Mock LLM возвращает уверенность 0.6 и предложение переименовать в "Alpha v2".
3. **Verify:** В графе появились две связи `:SUGGESTS`: одна типа "link", другая "property_update".
4. **Step 2:** Отправить User Decision "Confirm" для "link".
5. **Verify:** Связь "link" стала `:IS_PART_OF`. Связь "property_update" осталась. Workflow снова (или продолжает) в состоянии ожидания (опционально, зависит от логики прерывания, для MVP можно требовать подтверждения линка для прохода дальше).
6. **Step 3:** Resume workflow / Logic check.
7. **Verify:** Извлечены сущности, созданы связи `:MENTIONS`.

---

### Definition of Done (Iteration 5)

✅ **LangGraph workflow собран**.
✅ **E2E тест проходит** (полный цикл с прерыванием).
✅ **Граф остается чистым** (нет лишних связей после завершения).
✅ **No-Cache Policy соблюдена**.

---

## Rollout Plan

### Week 1
- **Day 1-2:** Iteration 1 (DB & CRUD w/ Detailed Suggestions).
- **Day 3-4:** Iteration 2 (L1/L2 Logic).
- **Day 5:** Iteration 3 (Decision Processing).

### Week 2
- **Day 6-7:** Iteration 4 (L3 Extraction).
- **Day 8:** Iteration 5 (Integration).
- **Day 9:** Bug fixing & Doc update.

---

## Next Steps

После прочтения этого документа:
- **Начните с Iteration 1, Task 1.1** (Neo4j Schema).
- **Используйте [03_DATA_STRUCTURES.md](./03_DATA_STRUCTURES.md)** для моделей.
- **Пишите тесты параллельно** с кодом.

**Удачи! 🚀**