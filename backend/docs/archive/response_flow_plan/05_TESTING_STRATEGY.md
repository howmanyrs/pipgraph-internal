# Testing Strategy - Стратегия тестирования MVP

**Цель:** Определить, как и что тестировать на каждой итерации MVP.

---

## Testing Pyramid для MVP

```
         /\
        /  \
       /E2E \          ← 1-2 теста (full cycle)
      /------\
     /  INT   \        ← 5-10 тестов (DB operations)
    /----------\
   /   UNIT     \      ← 20-30 тестов (business logic)
  /--------------\
```

**Приоритеты:**
1. **Unit тесты** - быстрые, изолированные, много
2. **Integration тесты** - проверяют Neo4j операции
3. **E2E тесты** - проверяют полный цикл (минимум)

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

# Все кроме реальных LLM вызовов
pytest -m "not llm"

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

    assert len(ALLOWED_ENTITY_LABELS) == 4
    assert "Concept" in ALLOWED_ENTITY_LABELS
    assert "Person" in ALLOWED_ENTITY_LABELS

def test_para_type_enum_values():
    """Проверяем валидные PARA типы."""
    from app.models.enums import PARAType

    assert PARAType.PROJECT == "Project"
    assert PARAType.AREA == "Area"
    assert PARAType.RESOURCE == "Resource"
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
    result = await neo4j_session.run(
        "MATCH (p:Project {id: $id}) RETURN p",
        id="test-proj-123"
    )
    record = await result.single()
    assert record is not None

@pytest.mark.integration
async def test_list_projects_by_status(neo4j_session, sample_projects):
    """Фильтрация проектов по статусу."""
    crud = PARAContainerCRUD(neo4j_session)

    active_projects = await crud.list_projects(status="active")

    assert len(active_projects) == 2
    assert all(p["status"] == "active" for p in active_projects)
```

---

#### Episodic CRUD
```python
# tests/integration/test_episodic_crud.py

@pytest.mark.integration
async def test_create_episodic(neo4j_session):
    """Создает episodic в Neo4j."""
    crud = EpisodicCRUD(neo4j_session)

    episodic = await crud.create_episodic(
        path="Notes/test.md",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    assert episodic["path"] == "Notes/test.md"
    assert "created_at" in episodic

@pytest.mark.integration
async def test_episodic_has_no_project_id_field(neo4j_session):
    """Проверяем, что Episodic НЕ имеет cached поля project_id."""
    crud = EpisodicCRUD(neo4j_session)

    episodic = await crud.create_episodic(path="Notes/test.md", ...)

    # Verify in DB
    result = await neo4j_session.run(
        "MATCH (n:Episodic {path: $path}) RETURN keys(n) as fields",
        path="Notes/test.md"
    )
    record = await result.single()
    fields = record["fields"]

    assert "path" in fields
    assert "created_at" in fields
    assert "updated_at" in fields
    assert "project_id" not in fields  # ✅ No-Cache Policy
```

---

#### Relationship CRUD
```python
# tests/integration/test_relationship_crud.py

@pytest.mark.integration
async def test_link_episodic_to_project(neo4j_session, sample_project, sample_episodic):
    """Создает связь [:IS_PART_OF]."""
    crud = RelationshipCRUD(neo4j_session)

    result = await crud.link_episodic_to_container(
        episodic_path=sample_episodic["path"],
        container_id=sample_project["id"],
        container_type="Project"
    )

    # Verify relationship exists
    cypher_result = await neo4j_session.run(
        "MATCH (n:Episodic {path: $path})-[:IS_PART_OF]->(p:Project {id: $id}) RETURN count(*) as cnt",
        path=sample_episodic["path"],
        id=sample_project["id"]
    )
    record = await cypher_result.single()
    assert record["cnt"] == 1

@pytest.mark.integration
async def test_get_episodic_para_context(neo4j_session, linked_episodic):
    """Получает PARA контекст через traversal."""
    crud = RelationshipCRUD(neo4j_session)

    context = await crud.get_episodic_para_context(linked_episodic["path"])

    assert context is not None
    assert context["type"] == "Project"
    assert context["name"] == "Sample Project"
```

---

### Fixtures для Iteration 1

```python
# tests/conftest.py

import pytest
from neo4j import AsyncGraphDatabase

@pytest.fixture(scope="session")
async def neo4j_driver():
    """Neo4j driver для тестов."""
    driver = AsyncGraphDatabase.driver(
        "bolt://localhost:7687",
        auth=("neo4j", "test_password")
    )
    yield driver
    await driver.close()

@pytest.fixture
async def neo4j_session(neo4j_driver):
    """Чистая сессия для каждого теста."""
    async with neo4j_driver.session() as session:
        # Cleanup before test
        await session.run("MATCH (n) DETACH DELETE n")
        yield session
        # Cleanup after test
        await session.run("MATCH (n) DETACH DELETE n")

@pytest.fixture
async def sample_project(neo4j_session):
    """Создает тестовый проект."""
    crud = PARAContainerCRUD(neo4j_session)
    return await crud.create_project(
        project_id="test-proj",
        name="Sample Project",
        status="active"
    )

@pytest.fixture
async def sample_episodic(neo4j_session):
    """Создает тестовый episodic."""
    crud = EpisodicCRUD(neo4j_session)
    return await crud.create_episodic(
        path="Notes/test.md",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

@pytest.fixture
async def linked_episodic(neo4j_session, sample_project, sample_episodic):
    """Episodic, привязанный к проекту."""
    crud = RelationshipCRUD(neo4j_session)
    await crud.link_episodic_to_container(
        episodic_path=sample_episodic["path"],
        container_id=sample_project["id"],
        container_type="Project"
    )
    return sample_episodic
```

---

## Iteration 2: L1/L2 PARA Identification

### Unit Tests (Mocked LLM)

#### PARA Classification
```python
# tests/unit/test_pipgraph_manager_identification.py

from unittest.mock import AsyncMock, patch
import pytest

@pytest.mark.unit
async def test_classify_episodic_para_returns_project():
    """Классифицирует заметку как Project (mock LLM)."""
    manager = PipGraphManager(...)

    # Mock LLM response
    with patch.object(manager, "_call_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = {"para_type": "Project", "reasoning": "..."}

        para_type = await manager.classify_episodic_para(
            episodic_content="This is a project plan for website redesign..."
        )

        assert para_type == "Project"
        mock_llm.assert_called_once()

@pytest.mark.unit
async def test_classify_episodic_para_returns_area():
    """Классифицирует заметку как Area."""
    manager = PipGraphManager(...)

    with patch.object(manager, "_call_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = {"para_type": "Area", "reasoning": "..."}

        para_type = await manager.classify_episodic_para(
            episodic_content="Health routines and fitness tracking..."
        )

        assert para_type == "Area"
```

---

#### Similarity Search
```python
@pytest.mark.unit
async def test_find_similar_containers_returns_top_3():
    """Находит топ-3 похожих контейнеров (mock embeddings)."""
    manager = PipGraphManager(...)

    # Mock embedding function
    with patch.object(manager, "_get_embedding", new_callable=AsyncMock) as mock_embed:
        mock_embed.return_value = [0.1, 0.2, 0.3, ...]  # Fake vector

        # Mock container retrieval
        with patch.object(manager, "_get_all_containers", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = [
                {"id": "proj-1", "name": "Website", "embedding": [0.1, 0.2, ...]},
                {"id": "proj-2", "name": "Mobile", "embedding": [0.5, 0.6, ...]},
                {"id": "proj-3", "name": "Backend", "embedding": [0.1, 0.3, ...]}
            ]

            results = await manager.find_similar_containers(
                episodic_content="Design homepage",
                para_type="Project",
                top_k=3
            )

            assert len(results) == 3
            assert all("similarity" in r for r in results)
            # Check sorted by similarity
            assert results[0]["similarity"] >= results[1]["similarity"]
```

---

#### Proposal Generation
```python
@pytest.mark.unit
async def test_generate_para_proposal_structure():
    """Генерирует валидную PARAProposal."""
    manager = PipGraphManager(...)

    # Mock dependencies
    with patch.object(manager, "classify_episodic_para", new_callable=AsyncMock) as mock_classify:
        mock_classify.return_value = "Project"

        with patch.object(manager, "find_similar_containers", new_callable=AsyncMock) as mock_similar:
            mock_similar.return_value = [
                {"id": "proj-1", "name": "Website", "confidence": 0.87},
                {"id": "proj-2", "name": "Mobile", "confidence": 0.72}
            ]

            with patch.object(manager, "_llm_select_best_match", new_callable=AsyncMock) as mock_select:
                mock_select.return_value = {
                    "primary_id": "proj-1",
                    "reasoning": "..."
                }

                proposal = await manager.generate_para_proposal(
                    episodic_content="Design mockups..."
                )

                assert proposal.para_type == "Project"
                assert proposal.primary_candidate.id == "proj-1"
                assert len(proposal.alternatives) >= 1
                assert proposal.reasoning is not None
```

---

### Integration Tests

```python
@pytest.mark.integration
async def test_auto_link_episodic_creates_relationship(neo4j_session, sample_project, sample_note):
    """auto_link_episodic создает [:IS_PART_OF] в графе."""
    manager = PipGraphManager(neo4j_session)

    await manager.auto_link_episodic(
        episodic_path=sample_note["path"],
        container_id=sample_project["id"],
        container_type="Project"
    )

    # Verify link
    crud = RelationshipCRUD(neo4j_session)
    context = await crud.get_episodic_para_context(sample_note["path"])

    assert context["id"] == sample_project["id"]
```

---

## Iteration 3: User Interaction Flow

### Unit Tests

#### UserCheckStatus Creation
```python
@pytest.mark.unit
def test_user_decision_payload_validation():
    """Валидация UserDecisionPayload."""
    from app.models.user_decision import UserDecisionPayload

    # Valid: confirm
    payload = UserDecisionPayload(action="confirm")
    assert payload.action == "confirm"

    # Valid: link_to_alternative
    payload = UserDecisionPayload(
        action="link_to_alternative",
        selected_container_id="proj-123"
    )
    assert payload.selected_container_id == "proj-123"

    # Invalid action
    with pytest.raises(ValidationError):
        UserDecisionPayload(action="invalid_action")
```

---

#### Decision Processing Logic
```python
@pytest.mark.unit
async def test_process_linking_decision_confirm():
    """Обработка confirm action (mock)."""
    manager = PipGraphManager(...)

    # Mock auto_link_episodic
    with patch.object(manager, "auto_link_episodic", new_callable=AsyncMock) as mock_link:
        decision = UserDecisionPayload(action="confirm")
        proposal = PARAProposal(
            para_type="Project",
            primary_candidate=PARACandidate(id="proj-1", name="Website", confidence=0.9),
            alternatives=[],
            reasoning="..."
        )

        await manager.process_linking_decision(
            episodic_path="test.md",
            proposal=proposal,
            user_decision=decision
        )

        # Verify auto_link called with primary
        mock_link.assert_called_once_with(
            episodic_path="test.md",
            container_id="proj-1",
            container_type="Project"
        )
```

---

### Integration Tests

```python
@pytest.mark.integration
async def test_create_check_and_link_to_note(neo4j_session, sample_note):
    """Создает UserCheckStatus и линкует к Note."""
    crud = UserCheckCRUD(neo4j_session)

    check = await crud.create_check(
        check_id="check-123",
        timestamp=datetime.utcnow(),
        status="pending",
        outcome="pending",
        comment=None
    )

    await crud.link_check_to_episodic(
        check_id=check["id"],
        episodic_path=sample_note["path"],
        is_current=True
    )

    # Verify relationship
    current_check = await crud.get_current_check_for_episodic(sample_note["path"])

    assert current_check is not None
    assert current_check["status"] == "pending"
```

---

### Workflow Tests (LangGraph)

```python
# tests/integration/test_workflow_interrupt.py

@pytest.mark.integration
async def test_workflow_interrupts_on_low_confidence(neo4j_session):
    """Workflow прерывается при низкой уверенности."""
    from app.workflows.episodic_workflow import compiled_workflow

    # Mock LLM для низкой confidence
    with patch("app.services.pipgraph_manager.PipGraphManager.generate_para_proposal") as mock_proposal:
        mock_proposal.return_value = PARAProposal(
            para_type="Project",
            primary_candidate=PARACandidate(id="proj-1", name="Test", confidence=0.65),  # Low!
            alternatives=[],
            reasoning="..."
        )

        state = await compiled_workflow.ainvoke({
            "episodic_path": "test.md",
            "episodic_content": "Some content..."
        })

        # Verify interrupt occurred
        assert state["system_proposal"] is not None
        assert state["user_decision"] is None
        assert state["final_context"] is None  # Not yet decided

@pytest.mark.integration
async def test_workflow_resume_after_decision(neo4j_session, sample_project):
    """Workflow возобновляется после получения решения."""
    # ... (interrupted state from previous test)

    # Provide user decision
    user_decision = UserDecisionPayload(action="confirm")

    state = await compiled_workflow.ainvoke({
        ...interrupted_state,
        "user_decision": user_decision
    })

    # Verify workflow continued
    assert state["final_context"] is not None
    assert state["final_context"]["id"] == "proj-1"
```

---

## Iteration 4: L3 Context-Aware Extraction

### Unit Tests (Mocked Graphiti)

```python
@pytest.mark.unit
async def test_extract_entities_with_context_injection():
    """Context инжектируется в Graphiti промпт."""
    manager = PipGraphManager(...)

    # Mock Graphiti
    with patch("app.services.graphiti_client.graphiti.add_episode", new_callable=AsyncMock) as mock_graphiti:
        mock_graphiti.return_value = {
            "entities": [
                {"uuid": "ent-1", "name": "Homepage Design", "labels": ["Concept"], "summary": "..."}
            ]
        }

        # Mock PARA context retrieval
        with patch.object(manager, "get_episodic_para_context", new_callable=AsyncMock) as mock_context:
            mock_context.return_value = {"id": "proj-1", "name": "Website Redesign", "type": "Project"}

            entities = await manager.extract_entities_with_context(
                episodic_path="test.md",
                episodic_content="Design mockups for homepage..."
            )

            # Verify Graphiti called with context
            mock_graphiti.assert_called_once()
            call_args = mock_graphiti.call_args
            assert "Website Redesign" in call_args[1]["context"]  # Context injection!

            assert len(entities) == 1
            assert entities[0].name == "Homepage Design"
```

---

### Integration Tests (With Neo4j)

```python
@pytest.mark.integration
async def test_save_entity_creates_node(neo4j_session):
    """Сохранение Entity в граф."""
    crud = EntityCRUD(neo4j_session)

    entity = await crud.save_entity(
        uuid="ent-123",
        name="User Authentication",
        labels=["Concept", "Task"],
        summary="Implement OAuth2 login"
    )

    # Verify in DB
    result = await neo4j_session.run(
        "MATCH (e:Entity {uuid: $uuid}) RETURN e",
        uuid="ent-123"
    )
    record = await result.single()
    assert record is not None
    assert record["e"]["name"] == "User Authentication"

@pytest.mark.integration
async def test_batch_save_entities_creates_mentions_relationships(neo4j_session, sample_note):
    """batch_save_entities создает [:MENTIONS] связи."""
    crud = EntityCRUD(neo4j_session)

    entities = [
        ExtractedCandidate(uuid="ent-1", name="Concept A", labels=["Concept"], summary="..."),
        ExtractedCandidate(uuid="ent-2", name="Task B", labels=["Task"], summary="...")
    ]

    await crud.batch_save_entities(
        entities=entities,
        episodic_path=sample_note["path"]
    )

    # Verify relationships
    result = await neo4j_session.run(
        "MATCH (n:Episodic {path: $path})-[:MENTIONS]->(e:Entity) RETURN count(e) as cnt",
        path=sample_note["path"]
    )
    record = await result.single()
    assert record["cnt"] == 2
```

---

### Schema Whitelist Tests

```python
@pytest.mark.unit
def test_entity_label_whitelist_validation():
    """ExtractedCandidate валидирует labels по whitelist."""
    from app.models.extracted_candidate import ExtractedCandidate

    # Valid labels
    entity = ExtractedCandidate(
        uuid="ent-1",
        name="Test",
        labels=["Concept", "Task"],
        summary="..."
    )
    assert entity.labels == ["Concept", "Task"]

    # Invalid label
    with pytest.raises(ValidationError):
        ExtractedCandidate(
            uuid="ent-2",
            name="Test",
            labels=["InvalidType"],  # Not in whitelist!
            summary="..."
        )
```

---

## Iteration 5: Integration & E2E Testing

### E2E Test (Full Cycle)

```python
# tests/e2e/test_full_episodic_processing.py

@pytest.mark.e2e
@pytest.mark.integration
async def test_full_episodic_processing_cycle(neo4j_session):
    """
    E2E: Note → L1/L2 → User Confirm → L3 → Entities Saved

    Full happy path test.
    """
    from app.workflows.episodic_workflow import compiled_workflow

    # Setup: Create test project
    para_crud = PARAContainerCRUD(neo4j_session)
    project = await para_crud.create_project(
        project_id="proj-website",
        name="Website Redesign",
        status="active"
    )

    # Mock LLM responses
    with patch("app.services.pipgraph_manager.PipGraphManager._call_llm") as mock_llm:
        # Mock L1/L2: High confidence → auto-link
        mock_llm.side_effect = [
            {"para_type": "Project", "reasoning": "..."},  # classify
            {"primary_id": project["id"], "reasoning": "..."}  # select best match
        ]

        # Mock Graphiti extraction
        with patch("app.services.graphiti_client.graphiti.add_episode") as mock_graphiti:
            mock_graphiti.return_value = {
                "entities": [
                    {
                        "uuid": "ent-1",
                        "name": "Homepage Redesign",
                        "labels": ["Concept", "Task"],
                        "summary": "Complete redesign of homepage"
                    },
                    {
                        "uuid": "ent-2",
                        "name": "Design Mockups",
                        "labels": ["Task"],
                        "summary": "Create visual mockups"
                    }
                ]
            }

            # Execute workflow
            initial_state = {
                "episodic_path": "Notes/daily/2025-11-19.md",
                "episodic_content": "Today I finalized the homepage redesign mockups. We decided to use a minimalist approach."
            }

            result = await compiled_workflow.ainvoke(initial_state)

            # ✅ Verify L1/L2: Note linked to Project
            relationship_crud = RelationshipCRUD(neo4j_session)
            para_context = await relationship_crud.get_episodic_para_context("Notes/daily/2025-11-19.md")

            assert para_context is not None
            assert para_context["id"] == project["id"]
            assert para_context["name"] == "Website Redesign"

            # ✅ Verify L3: Entities extracted and saved
            entity_crud = EntityCRUD(neo4j_session)
            entities = await entity_crud.get_entities_for_episodic("Notes/daily/2025-11-19.md")

            assert len(entities) == 2
            assert any(e["name"] == "Homepage Redesign" for e in entities)
            assert any(e["name"] == "Design Mockups" for e in entities)

            # ✅ Verify No-Cache Policy: Note has no project_id field
            note_result = await neo4j_session.run(
                "MATCH (n:Episodic {path: $path}) RETURN keys(n) as fields",
                path="Notes/daily/2025-11-19.md"
            )
            note_record = await note_result.single()
            assert "project_id" not in note_record["fields"]

            # ✅ Verify No-Cache Policy: Entity has no status field
            entity_result = await neo4j_session.run(
                "MATCH (e:Entity {uuid: $uuid}) RETURN keys(e) as fields",
                uuid="ent-1"
            )
            entity_record = await entity_result.single()
            assert "status" not in entity_record["fields"]

            # ✅ Verify UserCheckStatus created
            check_crud = UserCheckCRUD(neo4j_session)
            checks = await check_crud.get_all_checks_for_episodic("Notes/daily/2025-11-19.md")
            assert len(checks) >= 1  # At least one check (auto-link or entity confirmation)
```

---

### Error Handling Tests

```python
@pytest.mark.integration
async def test_workflow_handles_llm_failure_gracefully(neo4j_session):
    """Workflow не падает при LLM ошибке."""
    from app.workflows.episodic_workflow import compiled_workflow

    # Mock LLM to raise exception
    with patch("app.services.pipgraph_manager.PipGraphManager._call_llm") as mock_llm:
        mock_llm.side_effect = Exception("LLM API timeout")

        initial_state = {
            "episodic_path": "test.md",
            "episodic_content": "..."
        }

        result = await compiled_workflow.ainvoke(initial_state)

        # Verify error captured
        assert result.get("error") is not None
        assert "LLM API timeout" in result["error"]

        # Verify workflow stopped gracefully (no crash)
        assert result.get("final_context") is None
```

---

## Testing Best Practices

### 1. Mock External Dependencies
```python
# Good: Mock LLM calls
@patch("app.services.pipgraph_manager.PipGraphManager._call_llm")
async def test_something(mock_llm):
    mock_llm.return_value = {"para_type": "Project"}
    ...

# Bad: Real LLM call in unit test
async def test_something():
    result = await manager.classify_episodic_para(...)  # Calls real API!
```

---

### 2. Use Fixtures для Reusability
```python
# conftest.py
@pytest.fixture
async def sample_workflow_state():
    """Готовое состояние workflow для тестов."""
    return {
        "episodic_path": "test.md",
        "episodic_content": "...",
        "system_proposal": PARAProposal(...),
        "user_decision": None
    }

# Usage in test
async def test_something(sample_workflow_state):
    state = sample_workflow_state
    ...
```

---

### 3. Cleanup After Tests
```python
@pytest.fixture
async def neo4j_session(neo4j_driver):
    async with neo4j_driver.session() as session:
        yield session
        # Cleanup после каждого теста
        await session.run("MATCH (n) DETACH DELETE n")
```

---

### 4. Параллельный запуск тестов
```bash
# Install pytest-xdist
pip install pytest-xdist

# Run tests in parallel
pytest -n auto  # Auto-detect CPU cores
pytest -n 4     # Use 4 workers
```

**Важно:** Integration тесты с Neo4j могут конфликтовать при параллельном запуске. Используйте разные databases или sequential execution для integration.

---

## Coverage Goals

### Minimum Coverage для MVP

| Layer | Target Coverage |
|-------|----------------|
| CRUD Operations | ≥90% |
| PipGraphManager Methods | ≥80% |
| Workflow Nodes | ≥80% |
| Pydantic Models | ≥95% (validation logic) |
| Overall | ≥80% |

**Проверка coverage:**
```bash
# Install coverage plugin
pip install pytest-cov

# Run with coverage
pytest --cov=app --cov-report=html

# Open report
open htmlcov/index.html
```

---

## CI/CD Testing Strategy

### GitHub Actions Example
```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-asyncio
      - name: Run unit tests
        run: pytest -m unit --maxfail=3

  integration-tests:
    runs-on: ubuntu-latest
    services:
      neo4j:
        image: neo4j:5.12
        env:
          NEO4J_AUTH: neo4j/test_password
        ports:
          - 7687:7687
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run integration tests
        run: pytest -m integration
        env:
          NEO4J_URI: bolt://localhost:7687
          NEO4J_USER: neo4j
          NEO4J_PASSWORD: test_password
```

---

## Quick Reference: Test Commands

```bash
# All unit tests (fast, no external deps)
pytest -m unit

# All integration tests (require Neo4j)
pytest -m integration

# E2E tests only
pytest -m e2e

# Exclude expensive LLM tests
pytest -m "not llm"

# Run specific file
pytest tests/unit/test_pipgraph_manager.py

# Run specific test
pytest tests/unit/test_pipgraph_manager.py::test_classify_episodic_para

# Verbose output
pytest -v

# Stop after first failure
pytest -x

# Run with coverage
pytest --cov=app --cov-report=term

# Parallel execution (careful with integration tests!)
pytest -n auto -m unit
```

---

## Next Steps

После прочтения этого документа:
- **Настройте pytest** с markers и fixtures
- **Пишите тесты параллельно** с кодом (TDD approach)
- **Запускайте тесты часто** после каждого изменения
- **Проверяйте coverage** перед каждым commit

**Помните:** Хорошие тесты - это инвестиция, которая окупается при рефакторинге и добавлении новых фич.

---

**Готово к тестированию! 🧪**
