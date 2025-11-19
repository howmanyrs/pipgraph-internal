# Testing Strategy - Стратегия тестирования MVP

**Цель:** Определить, как и что тестировать на каждой итерации MVP, учитывая архитектуру, основанную на связях (Relationship-based State).

---

## Testing Pyramid для MVP

```
         /\
        /  \
       /E2E \          ← 1-2 теста (full cycle: Suggest -> Confirm -> Extract)
      /------\
     /  INT   \        ← 5-10 тестов (Graph operations & State transitions)
    /----------\
   /   UNIT     \      ← 20-30 тестов (Business logic, Pydantic validation)
  /--------------\
```

**Приоритеты:**
1. **Unit тесты** - валидация моделей и логика принятия решений (thresholds).
2. **Integration тесты** - проверка корректности трансформации графа (CRUD связей).
3. **E2E тесты** - проверка полного цикла workflow через LangGraph.

---

## Test Markers (pytest)

```python
# pytest.ini or conftest.py
pytest_plugins = ["pytest_asyncio"]

markers = [
    "unit: Unit tests (no external dependencies)",
    "integration: Integration tests (require Neo4j)",
    "e2e: End-to-end tests (require Neo4j + LLM mocks)",
    "llm: Tests that require real LLM API (expensive, slow)",
    "slow: Slow tests (>5 seconds)"
]
```

**Запуск тестов:**
```bash
# Только unit (fast)
pytest -m unit

# Unit + Integration (require Neo4j)
pytest -m "unit or integration"

# E2E только
pytest -m e2e
```

---

## Iteration 1: Database Setup & Foundation

### Unit Tests (No Neo4j)

#### Schema Validation
```python
# tests/unit/test_schema_definitions.py

def test_allowed_entity_labels_defined():
    """Проверяем, что whitelist типов сущностей определен."""
    from app.config.graphiti_config import ALLOWED_ENTITY_LABELS

    assert "Concept" in ALLOWED_ENTITY_LABELS
    assert "Task" in ALLOWED_ENTITY_LABELS

def test_graphiti_standard_labels():
    """Проверяем соответствие стандартным меткам Graphiti."""
    from app.config.graphiti_config import GRAPHITI_EPISODE_LABEL, GRAPHITI_ENTITY_LABEL
    
    assert GRAPHITI_EPISODE_LABEL == "Episode"
    assert GRAPHITI_ENTITY_LABEL == "Entity"
```

---

### Integration Tests (With Neo4j)

#### PARA Container CRUD
```python
# tests/integration/test_para_crud.py

import pytest
from app.crud.para_crud import PARAContainerCRUD

@pytest.mark.integration
async def test_create_project(neo4j_session):
    """Создает проект в Neo4j."""
    crud = PARAContainerCRUD(neo4j_session)

    project = await crud.create_project(
        project_id="test-proj-123",
        name="Test Project",
        status="active"
    )

    assert project["id"] == "test-proj-123"
    assert project["name"] == "Test Project"

    # Verify in DB
    result = await neo4j_session.run("MATCH (p:Project {id: $id}) RETURN p", id="test-proj-123")
    assert (await result.single()) is not None

@pytest.mark.integration
async def test_ensure_inbox_exists(neo4j_session):
    """Проверяет создание дефолтной Area 'Inbox'."""
    crud = PARAContainerCRUD(neo4j_session)
    
    # First call creates it
    inbox1 = await crud.ensure_inbox_exists()
    assert inbox1["name"] == "Inbox"
    
    # Second call returns the same node
    inbox2 = await crud.ensure_inbox_exists()
    assert inbox1["id"] == inbox2["id"]
```

#### Episodic CRUD (Standard Graphiti Node)
```python
# tests/integration/test_episodic_crud.py

@pytest.mark.integration
async def test_create_episodic_node(neo4j_session):
    """Создает узел Episode с правильными свойствами."""
    crud = EpisodicCRUD(neo4j_session)

    episodic = await crud.create_episodic(
        path="Notes/test.md",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    assert episodic["path"] == "Notes/test.md"

    # Verify Graphiti compatibility (Label=Episode, name=path)
    result = await neo4j_session.run(
        "MATCH (n:Episode {name: $path}) RETURN n", 
        path="Notes/test.md"
    )
    record = await result.single()
    assert record is not None
    assert "project_id" not in record["n"] # No-Cache Policy
```

#### Relationship CRUD (State Management)
```python
# tests/integration/test_relationship_crud.py

@pytest.mark.integration
async def test_create_suggestion(neo4j_session, sample_episodic, sample_project):
    """Создает связь :SUGGESTS."""
    crud = RelationshipCRUD(neo4j_session)

    await crud.create_suggestion(
        episodic_path=sample_episodic["path"],
        container_id=sample_project["id"],
        confidence=0.85,
        reasoning="Test reasoning"
    )

    # Verify relationship properties
    result = await neo4j_session.run(
        """
        MATCH (n:Episode {name: $path})-[r:SUGGESTS]->(p:Project)
        RETURN r.confidence, r.reasoning
        """,
        path=sample_episodic["path"]
    )
    record = await result.single()
    assert record["r.confidence"] == 0.85
    assert record["r.reasoning"] == "Test reasoning"

@pytest.mark.integration
async def test_create_link_is_part_of(neo4j_session, sample_episodic, sample_project):
    """Создает связь :IS_PART_OF."""
    crud = RelationshipCRUD(neo4j_session)

    await crud.create_link(
        episodic_path=sample_episodic["path"],
        container_id=sample_project["id"]
    )

    # Verify context retrieval
    context = await crud.get_episodic_para_context(sample_episodic["path"])
    assert context["id"] == sample_project["id"]
    assert context["name"] == sample_project["name"]
```

---

## Iteration 2: L1/L2 PARA Identification

### Unit Tests (Mocked LLM)

#### Proposal Generation
```python
# tests/unit/test_pipgraph_manager.py

@pytest.mark.unit
async def test_generate_para_proposal_structure():
    """Генерирует валидную PARAProposal."""
    manager = PipGraphManager(...)
    
    # Mock internal methods
    with patch.object(manager, "classify_note_para", return_value="Project"):
        with patch.object(manager, "find_similar_containers", return_value=[...]):
             # ... mock LLM selection ...
             proposal = await manager.generate_para_proposal("content")
             
             assert proposal.para_type == "Project"
             assert proposal.primary_candidate.confidence > 0
```

### Integration Tests (Graph Logic)

```python
@pytest.mark.integration
async def test_apply_proposal_high_confidence(neo4j_session, sample_episodic, sample_project):
    """При высокой уверенности создается :IS_PART_OF."""
    manager = PipGraphManager(neo4j_session)
    
    proposal = PARAProposal(
        para_type="Project",
        primary_candidate=PARACandidate(id=sample_project["id"], name="Test", confidence=0.98),
        alternatives=[], 
        reasoning="..."
    )

    await manager.apply_proposal_to_graph(sample_episodic["path"], proposal)

    # Verify IS_PART_OF exists
    crud = RelationshipCRUD(neo4j_session)
    context = await crud.get_episodic_para_context(sample_episodic["path"])
    assert context is not None
    
    # Verify SUGGESTS does NOT exist
    suggestion = await crud.get_suggestion(sample_episodic["path"])
    assert suggestion is None

@pytest.mark.integration
async def test_apply_proposal_low_confidence(neo4j_session, sample_episodic, sample_project):
    """При низкой уверенности создается :SUGGESTS."""
    manager = PipGraphManager(neo4j_session)
    
    proposal = PARAProposal(
        para_type="Project",
        primary_candidate=PARACandidate(id=sample_project["id"], name="Test", confidence=0.60),
        alternatives=[], 
        reasoning="..."
    )

    await manager.apply_proposal_to_graph(sample_episodic["path"], proposal)

    # Verify SUGGESTS exists
    crud = RelationshipCRUD(neo4j_session)
    suggestion = await crud.get_suggestion(sample_episodic["path"])
    assert suggestion is not None
    assert suggestion["confidence"] == 0.60

    # Verify IS_PART_OF does NOT exist
    context = await crud.get_episodic_para_context(sample_episodic["path"])
    assert context is None
```

---

## Iteration 3: User Interaction Flow

### Integration Tests (Decision Processing)

```python
@pytest.mark.integration
async def test_process_decision_confirm(neo4j_session, sample_episodic, sample_project):
    """Action 'confirm': Трансформация :SUGGESTS -> :IS_PART_OF."""
    crud = RelationshipCRUD(neo4j_session)
    # Setup: Create SUGGESTS
    await crud.create_suggestion(sample_episodic["path"], sample_project["id"], 0.8, "...")

    manager = PipGraphManager(neo4j_session)
    decision = UserDecisionPayload(action="confirm")
    
    await manager.process_user_decision(sample_episodic["path"], decision)

    # Verify transformation
    assert (await crud.get_suggestion(sample_episodic["path"])) is None
    assert (await crud.get_episodic_para_context(sample_episodic["path"]))["id"] == sample_project["id"]

@pytest.mark.integration
async def test_process_decision_dismiss(neo4j_session, sample_episodic, sample_project):
    """Action 'dismiss': Удаление :SUGGESTS -> Создание связи с Inbox."""
    crud = RelationshipCRUD(neo4j_session)
    # Setup: Create SUGGESTS to Project
    await crud.create_suggestion(sample_episodic["path"], sample_project["id"], 0.8, "...")

    manager = PipGraphManager(neo4j_session)
    decision = UserDecisionPayload(action="dismiss")
    
    await manager.process_user_decision(sample_episodic["path"], decision)

    # Verify linked to Inbox
    context = await crud.get_episodic_para_context(sample_episodic["path"])
    assert context["name"] == "Inbox"
    assert context["type"] == "Area"
```

### Workflow Tests (Conditional Logic)

```python
@pytest.mark.unit
async def test_check_suggestion_status_logic():
    """Проверка логики выбора следующего узла."""
    from app.workflows.conditions import check_suggestion_status
    
    # Mock State with active SUGGESTS
    with patch("app.crud.relationship_crud.RelationshipCRUD.get_suggestion", return_value={"confidence": 0.8}):
        next_node = await check_suggestion_status(mock_state)
        assert next_node == "wait_for_decision_node"

    # Mock State with established Context
    with patch("app.crud.relationship_crud.RelationshipCRUD.get_suggestion", return_value=None):
        with patch("app.crud.relationship_crud.RelationshipCRUD.get_episodic_para_context", return_value={"id": "1"}):
            next_node = await check_suggestion_status(mock_state)
            assert next_node == "extract_content_node"
```

---

## Iteration 4: L3 Context-Aware Extraction

### Integration Tests

```python
@pytest.mark.integration
async def test_extract_uses_graph_context(neo4j_session, sample_episodic, sample_project):
    """Проверяем, что Graphiti получает контекст из связи :IS_PART_OF."""
    # Setup: Link note to project
    rel_crud = RelationshipCRUD(neo4j_session)
    await rel_crud.create_link(sample_episodic["path"], sample_project["id"])

    manager = PipGraphManager(neo4j_session)
    
    # Mock Graphiti
    with patch("app.services.graphiti_client.graphiti.extract") as mock_extract:
        mock_extract.return_value = {"entities": []}
        
        await manager.extract_entities_with_context(sample_episodic["path"], "content")
        
        # Verify prompt contained project name
        call_args = mock_extract.call_args
        assert sample_project["name"] in call_args[1]["context"]

@pytest.mark.integration
async def test_save_entity_creates_mentions(neo4j_session, sample_episodic):
    """Сохранение создает связь :MENTIONS."""
    crud = EntityCRUD(neo4j_session)
    entity = ExtractedCandidate(uuid="ent-1", name="Test", labels=["Concept"], summary="...")
    
    await crud.batch_save_entities([entity], sample_episodic["path"])

    # Verify relationship
    result = await neo4j_session.run(
        """
        MATCH (n:Episode {name: $path})-[r:MENTIONS]->(e:Entity {uuid: $uuid})
        RETURN r.status
        """,
        path=sample_episodic["path"],
        uuid="ent-1"
    )
    record = await result.single()
    assert record is not None
    assert record["r.status"] == "confirmed"
```

---

## Iteration 5: Integration & E2E Testing

### E2E Test (Full Cycle)

```python
# tests/e2e/test_full_flow.py

@pytest.mark.e2e
@pytest.mark.integration
async def test_full_episodic_processing_cycle(neo4j_session):
    """
    E2E: Note -> Low Confidence -> SUGGESTS -> Interrupt -> User Confirm -> IS_PART_OF -> Extraction
    """
    from app.workflows.note_workflow import compiled_workflow

    # 1. Setup: Create Project
    para_crud = PARAContainerCRUD(neo4j_session)
    project = await para_crud.create_project("proj-1", "Alpha Project")

    # 2. Mock LLM (Low confidence) & Graphiti
    with patch("app.services.pipgraph_manager.PipGraphManager.generate_para_proposal") as mock_proposal:
        mock_proposal.return_value = PARAProposal(
            para_type="Project",
            primary_candidate=PARACandidate(id="proj-1", name="Alpha Project", confidence=0.6),
            alternatives=[], reasoning="..."
        )
        
        with patch("app.services.graphiti_client.graphiti.extract") as mock_extract:
            mock_extract.return_value = {"entities": [{"uuid": "ent-1", "name": "Entity1", "labels": ["Concept"], "summary": "..."}]}

            # 3. Run Initial Workflow
            state = await compiled_workflow.ainvoke({
                "note_path": "Notes/test.md",
                "note_content": "content"
            })

            # 4. Verify Interrupt & SUGGESTS
            rel_crud = RelationshipCRUD(neo4j_session)
            suggestion = await rel_crud.get_suggestion("Notes/test.md")
            assert suggestion is not None
            assert suggestion["confidence"] == 0.6

            # 5. Resume with Decision
            decision = UserDecisionPayload(action="confirm")
            state = await compiled_workflow.ainvoke({
                **state,
                "user_decision": decision
            })

            # 6. Verify Final State
            # SUGGESTS gone, IS_PART_OF present
            assert (await rel_crud.get_suggestion("Notes/test.md")) is None
            context = await rel_crud.get_episodic_para_context("Notes/test.md")
            assert context["id"] == "proj-1"
            
            # Entity saved
            ent_result = await neo4j_session.run("MATCH (e:Entity {uuid: 'ent-1'}) RETURN e")
            assert (await ent_result.single()) is not None
```

---

## Fixtures (conftest.py)

```python
@pytest.fixture
async def sample_episodic(neo4j_session):
    """Создает тестовый Episode (Episodic)."""
    crud = EpisodicCRUD(neo4j_session)
    return await crud.create_episodic(
        path="Notes/test.md",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

@pytest.fixture
async def sample_project(neo4j_session):
    """Создает тестовый Project."""
    crud = PARAContainerCRUD(neo4j_session)
    return await crud.create_project(
        project_id="test-proj",
        name="Sample Project",
        status="active"
    )
```

---

## Coverage Goals

| Layer | Target Coverage |
|-------|----------------|
| CRUD Operations | ≥90% |
| PipGraphManager | ≥80% |
| Workflow Nodes | ≥80% |
| Pydantic Models | ≥95% |

**Помните:** В MVP мы тестируем поведение графа (наличие правильных связей), а не внутреннее состояние Python объектов. Граф — источник истины.