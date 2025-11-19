# Implementation Steps - Пошаговый план разработки

**Стратегия:** 5 итераций, каждая добавляет работающий слой функциональности.

---

## Iteration 1: Database Setup & Foundation
**Длительность:** 1-2 дня
**Цель:** Развернуть Neo4j схему, создать базовые CRUD операции.

### Задачи

#### 1.1 Neo4j Schema Definition
**Файл:** `app/services/graph_schema.py` (или отдельный migration script)

**Что делаем:**
- Создаем constraints и индексы:
  ```cypher
  // Unique constraints
  CREATE CONSTRAINT episodic_path_unique IF NOT EXISTS
  FOR (n:Episodic) REQUIRE n.path IS UNIQUE;

  CREATE CONSTRAINT project_id_unique IF NOT EXISTS
  FOR (p:Project) REQUIRE p.id IS UNIQUE;

  CREATE CONSTRAINT area_id_unique IF NOT EXISTS
  FOR (a:Area) REQUIRE a.id IS UNIQUE;

  CREATE CONSTRAINT resource_id_unique IF NOT EXISTS
  FOR (r:Resource) REQUIRE r.id IS UNIQUE;

  // Indexes for performance
  CREATE INDEX entity_uuid_idx IF NOT EXISTS
  FOR (e:Entity) ON (e.uuid);

  CREATE INDEX check_status_idx IF NOT EXISTS
  FOR (c:UserCheckStatus) ON (c.id);
  ```

**Тест:**
- Запустить миграцию на пустой Neo4j
- Проверить наличие constraints через `SHOW CONSTRAINTS`

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
```

**Cypher examples:**
```cypher
// Create Project
CREATE (p:Project {id: $id, name: $name, status: $status})
RETURN p

// List all active Projects
MATCH (p:Project {status: 'active'})
RETURN p
```

**Тесты:**
- `test_create_project()` - создает проект, проверяет свойства
- `test_list_projects_by_status()` - фильтрация по статусу
- `test_get_nonexistent_project()` - возвращает None

---

#### 1.3 Episodic CRUD
**Файл:** `app/crud/episodic_crud.py`

**Методы:**
```python
class EpisodicCRUD:
    def create_episodic(self, path: str, created_at: datetime, updated_at: datetime) -> dict
    def get_episodic(self, path: str) -> Optional[dict]
    def update_episodic_timestamp(self, path: str, updated_at: datetime) -> dict

    # NO method like `update_episodic_project_id()` - we use relationships!
```

**Важно:**
- В узле `Episodic` НЕТ поля `project_id`
- Только: `path`, `created_at`, `updated_at`

**Тесты:**
- `test_create_episodic()` - создает episodic с timestamps
- `test_get_episodic_by_path()` - поиск по unique path
- `test_update_episodic_timestamp()` - обновление метаданных

---

#### 1.4 Relationship CRUD
**Файл:** `app/crud/relationship_crud.py`

**Методы:**
```python
class RelationshipCRUD:
    def link_episodic_to_container(
        self,
        episodic_path: str,
        container_id: str,
        container_type: str  # "Project" | "Area" | "Resource"
    ) -> dict

    def get_episodic_para_context(self, episodic_path: str) -> Optional[dict]
    # Returns: {"id": "proj-123", "name": "Website Redesign", "type": "Project"}
```

**Cypher examples:**
```cypher
// Link Episodic to Project
MATCH (n:Episodic {path: $episodic_path})
MATCH (p:Project {id: $container_id})
MERGE (n)-[:IS_PART_OF]->(p)
RETURN n, p

// Get PARA context for Episodic
MATCH (n:Episodic {path: $episodic_path})-[:IS_PART_OF]->(container)
WHERE container:Project OR container:Area OR container:Resource
RETURN container
```

**Тесты:**
- `test_link_episodic_to_project()` - создает связь `:IS_PART_OF`
- `test_get_episodic_para_context()` - возвращает проект для episodic
- `test_get_context_for_unlinked_episodic()` - возвращает None

---

### Definition of Done (Iteration 1)

✅ **Neo4j schema создана** (constraints, indexes)
✅ **CRUD операции работают** для PARA контейнеров и Episodic узлов
✅ **Связь `:IS_PART_OF` создается** и читается через граф
✅ **Unit тесты проходят** для всех CRUD методов
✅ **Integration тест:** создать Project → создать Episodic → link → get_para_context → проверить результат

---

## Iteration 2: L1/L2 PARA Identification
**Длительность:** 2-3 дня
**Цель:** Реализовать Top-Down идентификацию контекста для заметки.

### Задачи

#### 2.1 PARA Type Classification
**Файл:** `app/services/pipgraph_manager.py`

**Метод:**
```python
async def classify_note_para(self, note_content: str) -> str:
    """
    Определяет PARA тип заметки через LLM.

    Returns: "Project" | "Area" | "Resource"
    """
    # Промпт: "Is this note about a Project (time-bound goal),
    # Area (ongoing responsibility), or Resource (reference material)?"
    pass
```

**LLM Integration:**
- Используем OpenRouter API
- Модель: `anthropic/claude-3.5-sonnet`
- Structured output (JSON): `{"para_type": "Project", "reasoning": "..."}`

**Тест:**
- `test_classify_note_para_project()` - mock LLM response
- `test_classify_note_para_area()` - разные типы заметок

---

#### 2.2 Similarity Search
**Файл:** `app/services/pipgraph_manager.py`

**Метод:**
```python
async def find_similar_containers(
    self,
    note_content: str,
    para_type: str,
    top_k: int = 3
) -> list[dict]:
    """
    Ищет топ-K похожих контейнеров по embeddings.

    Returns: [
        {"id": "proj-123", "name": "Website Redesign", "similarity": 0.87},
        {"id": "proj-456", "name": "Mobile App", "similarity": 0.72},
        ...
    ]
    """
    # 1. Получить embedding для note_content
    # 2. Получить все контейнеры типа para_type из Neo4j
    # 3. Для каждого: вычислить cosine similarity
    # 4. Вернуть топ-K
    pass
```

**Embeddings:**
- Модель: `text-embedding-3-small` (OpenAI) или аналог через OpenRouter
- Храним embeddings в памяти (в MVP нет кэша в Neo4j)

**Тест:**
- `test_find_similar_containers()` - mock embeddings, проверяем сортировку по similarity

---

#### 2.3 Proposal Generation
**Файл:** `app/services/pipgraph_manager.py`

**Метод:**
```python
async def generate_para_proposal(
    self,
    note_content: str
) -> PARAProposal:
    """
    Создает предложение для L1/L2 идентификации.

    Returns: PARAProposal with:
    - para_type: "Project"
    - primary_candidate: {"id": "proj-123", "name": "...", "confidence": 0.87}
    - alternatives: [...]
    - reasoning: "This note discusses design mockups..."
    """
    # 1. Classify PARA type
    # 2. Find similar containers
    # 3. LLM decision: "Which container is best for this note?"
    # 4. Return structured proposal
    pass
```

**Pydantic Model:**
```python
class PARACandidate(BaseModel):
    id: str
    name: str
    confidence: float

class PARAProposal(BaseModel):
    para_type: str  # "Project" | "Area" | "Resource"
    primary_candidate: PARACandidate
    alternatives: list[PARACandidate]
    reasoning: str
```

**Тест:**
- `test_generate_para_proposal()` - mock LLM, проверяем structure
- `test_proposal_has_alternatives()` - минимум 1 alternative

---

#### 2.4 Simple Linking (без User Interaction)
**Файл:** `app/services/pipgraph_manager.py`

**Метод:**
```python
async def auto_link_episodic(
    self,
    episodic_path: str,
    container_id: str,
    container_type: str
) -> None:
    """
    Автоматически привязывает episodic к контейнеру.
    (Используется только если confidence > 95%)
    """
    # 1. Вызвать relationship_crud.link_episodic_to_container()
    # 2. Логировать решение
    pass
```

**Тест:**
- `test_auto_link_episodic()` - проверяем создание связи в графе

---

### Definition of Done (Iteration 2)

✅ **PARA type классификация работает** (LLM возвращает Project/Area/Resource)
✅ **Similarity search находит** топ-3 похожих контейнеров
✅ **Proposal generation создает** структурированное предложение
✅ **Auto-link работает** для high-confidence случаев
✅ **Integration тест:** episodic → classify → find_similar → generate_proposal → auto_link (mock LLM)

---

## Iteration 3: User Interaction Flow
**Длительность:** 2 дня
**Цель:** Добавить прерывания workflow и обработку решений пользователя.

### Задачи

#### 3.1 UserCheckStatus CRUD
**Файл:** `app/crud/user_check_crud.py`

**Методы:**
```python
class UserCheckCRUD:
    def create_check(
        self,
        check_id: str,
        timestamp: datetime,
        status: str,  # "pending" | "confirmed" | "rejected"
        outcome: str,  # "confirmed" | "linked_to_alternative" | "created_custom"
        comment: Optional[str] = None
    ) -> dict

    def link_check_to_episodic(self, check_id: str, episodic_path: str, is_current: bool = True) -> None

    def get_current_check_for_episodic(self, episodic_path: str) -> Optional[dict]
```

**Cypher examples:**
```cypher
// Create UserCheckStatus node
CREATE (c:UserCheckStatus {
    id: $check_id,
    timestamp: $timestamp,
    status: $status,
    outcome: $outcome,
    comment: $comment
})
RETURN c

// Link to Episodic with is_current flag
MATCH (n:Episodic {path: $episodic_path})
MATCH (c:UserCheckStatus {id: $check_id})
MERGE (n)-[:HAS_CHECK {is_current: $is_current}]->(c)
```

**Тест:**
- `test_create_check()` - создаем узел UserCheckStatus
- `test_get_current_check_for_episodic()` - возвращает последний check

---

#### 3.2 Decision Processing
**Файл:** `app/services/pipgraph_manager.py`

**Метод:**
```python
async def process_linking_decision(
    self,
    episodic_path: str,
    user_decision: UserDecisionPayload
) -> None:
    """
    Обрабатывает решение пользователя из WebSocket.

    user_decision.action:
    - "confirm" → link to primary_candidate
    - "link_to_alternative" → link to user_decision.selected_container_id
    - "create_custom" → create new container + link
    - "dismiss" → do nothing (skip L3)
    """
    # 1. Create UserCheckStatus node
    # 2. Link check to episodic with [:HAS_CHECK]
    # 3. Execute action (link or create+link)
    # 4. Return workflow control
    pass
```

**Pydantic Model:**
```python
class UserDecisionPayload(BaseModel):
    action: str  # "confirm" | "link_to_alternative" | "create_custom" | "dismiss"
    selected_container_id: Optional[str] = None  # for "link_to_alternative"
    custom_container_name: Optional[str] = None  # for "create_custom"
    comment: Optional[str] = None
```

**Тест:**
- `test_process_decision_confirm()` - проверяем link to primary
- `test_process_decision_alternative()` - проверяем link to selected
- `test_process_decision_create_custom()` - проверяем создание нового контейнера

---

#### 3.3 LangGraph Interrupt Node
**Файл:** `app/workflows/note_workflow.py`

**Узел:**
```python
def wait_for_user_context_decision(state: NoteWorkflowState) -> NoteWorkflowState:
    """
    LangGraph node that interrupts workflow and waits for user input.

    - Creates UserCheckStatus with status="pending"
    - Raises interrupt
    - Returns control to user
    """
    # 1. Save proposal to state
    # 2. Create pending check
    # 3. Return state (LangGraph handles interrupt)
    return state
```

**LangGraph Config:**
```python
workflow.add_node("wait_for_context_decision", wait_for_user_context_decision)
workflow.add_edge("identify_context_node", "wait_for_context_decision")

# Conditional edge after interrupt
workflow.add_conditional_edges(
    "wait_for_context_decision",
    should_proceed_to_extraction,  # Check if decision received
    {
        True: "extract_content_node",
        False: END
    }
)
```

**Тест:**
- `test_interrupt_creates_pending_check()` - проверяем создание check
- `test_resume_after_decision()` - mock resume с user_decision

---

#### 3.4 JSON Payload Format
**Файл:** `app/api/schemas/notification_schema.py`

**Response для фронтенда:**
```python
class ContextProposalNotification(BaseModel):
    notification_type: str = "para_context_proposal"
    episodic_path: str
    proposal: PARAProposal
    actions: list[ActionButton]

class ActionButton(BaseModel):
    id: str  # "confirm" | "choose_alternative" | "create_custom"
    label: str  # "Confirm" | "Choose Alternative" | "Create New Project"
    style: str  # "primary" | "secondary"
```

**Example JSON:**
```json
{
  "notification_type": "para_context_proposal",
  "episodic_path": "Notes/daily/2025-11-19.md",
  "proposal": {
    "para_type": "Project",
    "primary_candidate": {
      "id": "proj-123",
      "name": "Website Redesign",
      "confidence": 0.87
    },
    "alternatives": [
      {"id": "proj-456", "name": "Mobile App", "confidence": 0.65}
    ],
    "reasoning": "This note discusses design mockups..."
  },
  "actions": [
    {"id": "confirm", "label": "Link to 'Website Redesign'", "style": "primary"},
    {"id": "choose_alternative", "label": "Choose Alternative", "style": "secondary"},
    {"id": "create_custom", "label": "Create New Project", "style": "secondary"}
  ]
}
```

**Тест:**
- `test_notification_schema_valid()` - проверяем Pydantic validation
- `test_actions_have_labels()` - все кнопки имеют labels

---

### Definition of Done (Iteration 3)

✅ **UserCheckStatus узлы создаются** при interrupt
✅ **User decision обрабатывается** (confirm/alternative/create_custom)
✅ **LangGraph interrupt/resume работает** (mock workflow test)
✅ **JSON payload соответствует схеме** для фронтенда
✅ **Integration тест:** interrupt → save check → resume with decision → verify link

---

## Iteration 4: L3 Context-Aware Extraction
**Длительность:** 2-3 дня
**Цель:** Извлекать сущности с учетом контекста проекта через Graphiti.

### Задачи

#### 4.1 Context Injection
**Файл:** `app/services/pipgraph_manager.py`

**Метод:**
```python
async def extract_entities_with_context(
    self,
    episodic_path: str,
    episodic_content: str
) -> list[ExtractedCandidate]:
    """
    Извлекает сущности с инъекцией контекста проекта.

    Steps:
    1. Get PARA context for episodic (via relationship_crud)
    2. Build context prompt: "Context: This note belongs to Project 'Website Redesign'"
    3. Call Graphiti with context-injected prompt
    4. Return extracted entities
    """
    # 1. para_context = relationship_crud.get_episodic_para_context(episodic_path)
    # 2. context_text = f"Context: Project '{para_context['name']}'"
    # 3. graphiti_result = await graphiti.extract(episodic_content, context=context_text)
    # 4. Return entities
    pass
```

**Graphiti Integration:**
- Используем Graphiti SDK
- Инициализация: `Graphiti(uri=NEO4J_URI, user=..., password=...)`
- Метод: `graphiti.add_episode(content, context=...)`

**Тест:**
- `test_extract_with_context()` - mock Graphiti, проверяем context в промпте
- `test_extract_without_para_context()` - если нет контекста, используем пустой

---

#### 4.2 Schema Whitelist Configuration
**Файл:** `app/config/graphiti_config.py`

**Конфигурация:**
```python
ALLOWED_ENTITY_LABELS = [
    "Concept",
    "Person",
    "Task",
    "Decision"
]

GRAPHITI_EXTRACTION_PROMPT = """
Extract entities from this note.

ALLOWED TYPES ONLY:
- Concept: abstract ideas, methodologies
- Person: people mentioned by name
- Task: actionable items
- Decision: choices made or to be made

IGNORE:
- Dates, times
- File formats, tools
- Generic nouns (without context)

Context: {context}

Note content:
{content}
"""
```

**Graphiti Setup:**
```python
from graphiti import Graphiti

graphiti_client = Graphiti(
    uri=settings.NEO4J_URI,
    user=settings.NEO4J_USER,
    password=settings.NEO4J_PASSWORD
)

# Configure schema
graphiti_client.set_allowed_labels(ALLOWED_ENTITY_LABELS)
```

**Тест:**
- `test_whitelist_filters_generic_entities()` - проверяем, что даты не извлекаются

---

#### 4.3 Entity Saving
**Файл:** `app/crud/entity_crud.py`

**Методы:**
```python
class EntityCRUD:
    def save_entity(
        self,
        uuid: str,
        name: str,
        labels: list[str],
        summary: str
    ) -> dict

    def link_entity_to_episodic(
        self,
        entity_uuid: str,
        episodic_path: str
    ) -> None

    def batch_save_entities(
        self,
        entities: list[ExtractedCandidate],
        episodic_path: str
    ) -> None
```

**Cypher examples:**
```cypher
// Save Entity
CREATE (e:Entity {
    uuid: $uuid,
    name: $name,
    labels: $labels,  // ["Concept", "Task"]
    summary: $summary
})
RETURN e

// Link to Episodic
MATCH (e:Entity {uuid: $uuid})
MATCH (n:Episodic {path: $episodic_path})
MERGE (n)-[:MENTIONS]->(e)
```

**Важно:**
- В `Entity` НЕТ поля `status`
- Статус извлекается через `[:HAS_CHECK]` связь

**Тест:**
- `test_save_entity()` - создаем Entity в графе
- `test_batch_save_entities()` - множественное сохранение

---

#### 4.4 Entity Confirmation Flow
**Файл:** `app/services/pipgraph_manager.py`

**Метод:**
```python
async def confirm_entities(
    self,
    episodic_path: str,
    entity_uuids: list[str]
) -> None:
    """
    Подтверждает извлеченные сущности.

    - Creates UserCheckStatus for each entity
    - Links check to entity with [:HAS_CHECK]
    """
    for uuid in entity_uuids:
        check = user_check_crud.create_check(
            check_id=f"check-{uuid}",
            status="confirmed",
            outcome="confirmed"
        )
        # Link check to entity
        # MATCH (e:Entity {uuid: $uuid})
        # MATCH (c:UserCheckStatus {id: $check_id})
        # MERGE (e)-[:HAS_CHECK {is_current: true}]->(c)
    pass
```

**Тест:**
- `test_confirm_entities()` - проверяем создание [:HAS_CHECK] связей

---

### Definition of Done (Iteration 4)

✅ **Context injection работает** (Graphiti получает project name в промпте)
✅ **Schema whitelist фильтрует** лишние типы сущностей
✅ **Entity nodes сохраняются** в граф с правильными labels
✅ **Связь `:MENTIONS` создается** между Episodic и Entity
✅ **Entity confirmation создает** [:HAS_CHECK] связи
✅ **Integration тест:** extract → save entities → confirm → verify graph structure

---

## Iteration 5: Integration & End-to-End Testing
**Длительность:** 1-2 дня
**Цель:** Связать все части, протестировать полный цикл, зафиксировать багиs.

### Задачи

#### 5.1 Complete Workflow Assembly
**Файл:** `app/workflows/note_workflow.py`

**LangGraph Граф:**
```python
from langgraph.graph import StateGraph, END

workflow = StateGraph(NoteWorkflowState)

# Nodes
workflow.add_node("identify_context", identify_context_node)
workflow.add_node("wait_context_decision", wait_for_user_context_decision)
workflow.add_node("commit_link", commit_link_node)
workflow.add_node("extract_content", extract_content_node)
workflow.add_node("confirm_entities", confirm_entities_node)

# Edges
workflow.set_entry_point("identify_context")
workflow.add_edge("identify_context", "wait_context_decision")
workflow.add_edge("wait_context_decision", "commit_link")
workflow.add_edge("commit_link", "extract_content")
workflow.add_edge("extract_content", "confirm_entities")
workflow.add_edge("confirm_entities", END)

compiled_workflow = workflow.compile()
```

**Тест:**
- `test_workflow_graph_structure()` - проверяем наличие всех узлов

---

#### 5.2 E2E Test Scenario
**Файл:** `tests/e2e/test_episodic_processing_flow.py`

**Сценарий:**
```python
@pytest.mark.integration
async def test_full_episodic_processing_cycle():
    """
    E2E тест: Episodic → L1/L2 → User Confirm → L3 → Entities Saved

    Steps:
    1. Create test Project in Neo4j
    2. Submit episodic for processing
    3. Workflow identifies context → interrupts
    4. Mock user decision: "confirm"
    5. Workflow resumes → links episodic to project
    6. Workflow extracts entities with context
    7. Verify graph state:
       - Episodic has [:IS_PART_OF] → Project
       - Entities have [:MENTIONS] ← Episodic
       - Entities have [:HAS_CHECK] → UserCheckStatus
    """
    # Setup
    project = para_crud.create_project(...)
    episodic_content = "Design mockups for homepage..."

    # Execute workflow
    state = await compiled_workflow.ainvoke({
        "episodic_path": "test.md",
        "episodic_content": episodic_content
    })

    # Verify L1/L2
    assert state["system_proposal"] is not None

    # Mock user decision
    user_decision = UserDecisionPayload(action="confirm")
    state = await compiled_workflow.ainvoke({
        ...state,
        "user_decision": user_decision
    })

    # Verify Link
    para_context = relationship_crud.get_episodic_para_context("test.md")
    assert para_context["id"] == project["id"]

    # Verify Extraction
    assert len(state["extracted_entities"]) > 0

    # Verify Graph
    entities = entity_crud.get_entities_for_episodic("test.md")
    assert all(e["labels"] in ALLOWED_ENTITY_LABELS for e in entities)
```

**Тест:**
- `test_full_episodic_processing_cycle()` - один большой E2E тест

---

#### 5.3 Error Handling
**Файл:** `app/workflows/note_workflow.py`

**Добавляем try/except:**
```python
async def identify_context_node(state: NoteWorkflowState) -> NoteWorkflowState:
    try:
        proposal = await pipgraph_manager.generate_para_proposal(
            state["note_content"]
        )
        state["system_proposal"] = proposal
    except Exception as e:
        logger.error(f"Failed to identify context: {e}")
        state["error"] = str(e)
        # Fallback: создаем дефолтный proposal или прерываем workflow

    return state
```

**Тест:**
- `test_error_handling_llm_failure()` - mock LLM exception, проверяем graceful failure

---

#### 5.4 Logging & Observability
**Файл:** `app/utils/workflow_logger.py`

**Настройка:**
```python
import logging

logger = logging.getLogger("pipgraph.workflow")
logger.setLevel(logging.DEBUG)

# Log важных событий
def log_workflow_step(step_name: str, state: dict):
    logger.info(f"[Workflow] Step: {step_name}")
    logger.debug(f"[Workflow] State: {state}")
```

**Добавляем логи в узлы:**
```python
async def identify_context_node(state):
    log_workflow_step("identify_context", state)
    # ... logic ...
    return state
```

**Тест:**
- `test_workflow_logs_steps()` - проверяем наличие логов (caplog fixture)

---

#### 5.5 Documentation & Examples
**Файл:** `backend/docs/WORKFLOW_EXAMPLES.md`

**Примеры использования:**
```python
# Example 1: Basic note processing
from app.workflows.note_workflow import compiled_workflow

result = await compiled_workflow.ainvoke({
    "note_path": "Notes/daily/2025-11-19.md",
    "note_content": "Today I finalized the homepage design..."
})

# Example 2: Resume after interrupt
result = await compiled_workflow.ainvoke({
    ...previous_state,
    "user_decision": {"action": "confirm"}
})
```

---

### Definition of Done (Iteration 5)

✅ **LangGraph workflow собран** и скомпилирован
✅ **E2E тест проходит** для happy path
✅ **Error handling работает** для LLM failures
✅ **Логирование настроено** для всех узлов
✅ **Документация примеров** создана
✅ **No-Cache проверка:** ручной Cypher запрос подтверждает отсутствие cached полей

**Final Verification:**
```cypher
// Проверка: Episodic не имеет project_id
MATCH (n:Episodic)
RETURN keys(n)  // Должно быть: ["path", "created_at", "updated_at"]

// Проверка: Entity не имеет status
MATCH (e:Entity)
RETURN keys(e)  // Должно быть: ["uuid", "name", "labels", "summary"]

// Проверка: все связи на месте
MATCH (n:Episodic)-[:IS_PART_OF]->(p:Project)
MATCH (n)-[:MENTIONS]->(e:Entity)
MATCH (e)-[:HAS_CHECK]->(c:UserCheckStatus)
RETURN count(*)
```

---

## Rollout Plan (Порядок разработки)

### Week 1
- **Day 1-2:** Iteration 1 (Database Setup)
- **Day 3-4:** Iteration 2 (L1/L2 Identification)
- **Day 5:** Iteration 3 начало (UserCheckStatus CRUD)

### Week 2
- **Day 6:** Iteration 3 завершение (Interrupt Flow)
- **Day 7-8:** Iteration 4 (Context Extraction)
- **Day 9:** Iteration 5 (Integration)
- **Day 10:** Buffer для bug fixes

---

## Приоритизация (если нужно сократить scope)

**Must-Have (нельзя пропустить):**
1. Iteration 1 - без БД ничего не работает
2. Iteration 2 - core логика L1/L2
3. Iteration 4 - core логика L3
4. Iteration 5 (E2E test только) - проверка интеграции

**Nice-to-Have (можно упростить):**
- Iteration 3 - можно заменить на hardcoded user_decision в тестах
- Error handling - можно добавить после MVP
- Logging - базовый уровень достаточно

---

## Next Steps

После прочтения этого документа:
- **Начните с Iteration 1, Task 1.1** (Neo4j Schema)
- **Используйте [03_DATA_STRUCTURES.md](./03_DATA_STRUCTURES.md)** для моделей
- **Пишите тесты параллельно** с кодом (см. [05_TESTING_STRATEGY.md](./05_TESTING_STRATEGY.md))
- **Сверяйтесь с [01_MVP_SCOPE.md](./01_MVP_SCOPE.md)**, чтобы не добавлять лишнее

**Удачи! 🚀**
