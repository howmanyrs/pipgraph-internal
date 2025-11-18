# Implementation Roadmap - Практический план

**Дата создания:** 2025-11-17
**Статус:** Implementation Guide
**Версия:** 2.0
**Связанные документы:**
- [03_PIPGRAPH_MANAGER_REFACTORING.md](./03_PIPGRAPH_MANAGER_REFACTORING.md)
- [04_LANGGRAPH_WORKFLOW_UPDATED.md](./04_LANGGRAPH_WORKFLOW_UPDATED.md)

---

## Обзор

Этот документ предоставляет **практический план имплементации** рефакторинга PipGraphManager и расширения LangGraph workflow.

### Две стратегии

1. **Quick Wins Path** (4-5 дней) - немедленная ценность для MVP
2. **Full Implementation Path** (11-16 дней) - полный L1/L2/L3 workflow

---

## Phase 0: Quick Wins (Рекомендуется начать)

**Цель:** Получить значительное улучшение MVP за 4-5 дней без полного рефакторинга

**Длительность:** 4-5 дней
**Риск:** Низкий
**Ценность:** Высокая

### Day 1: Extract Entities Without Saving

**Задача:** Разбить `process_note()` чтобы пользователь видел сущности ДО сохранения

#### Изменения в PipGraphManager

```python
# backend/app/services/pipgraph_manager.py

async def extract_entities_from_note(
    self,
    note_content: str,
    note_name: str,
    reference_time: datetime,
    source: EpisodeType = EpisodeType.text,
    group_id: Optional[str] = None,
    entity_types: Optional[dict] = None,
    excluded_entity_types: Optional[list] = None
) -> tuple[List[EntityNode], str]:
    """
    Извлекает сущности БЕЗ сохранения в Neo4j.

    Это копия логики из process_note() до момента bulk save.
    """
    # 1. Create EpisodicNode
    episode = EpisodicNode(
        name=note_name,
        content=note_content,
        source=source,
        source_description=f"Obsidian note: {note_name}",
        created_at=reference_time,
        valid_at=reference_time,
        group_id=group_id
    )

    # 2. Extract nodes (LLM call)
    entity_types_to_use = entity_types or self.entity_types_config
    extracted_nodes = await self.graphiti.extract_nodes(
        episode,
        entity_types=entity_types_to_use,
        excluded_entity_types=excluded_entity_types
    )

    # 3. Resolve against existing graph
    resolved_map = await self.graphiti.resolve_extracted_nodes(
        episode,
        extracted_nodes
    )

    # 4. Return entities WITHOUT calling add_nodes_and_edges_bulk()
    return (extracted_nodes, episode.uuid)
```

#### Изменения в Workflow

```python
# backend/app/services/note_workflow.py

async def extract_entities_node(state: NoteWorkflowState) -> dict:
    """ОБНОВЛЕНО: используем новый метод"""

    pipgraph = get_pipgraph_manager()

    # НОВЫЙ метод - НЕ сохраняет в Neo4j!
    entities, episode_uuid = await pipgraph.extract_entities_from_note(
        note_content=state["content"],
        note_name=state["file_path"],
        reference_time=datetime.now(timezone.utc)
    )

    # Остальная логика без изменений
    ...
```

#### Testing

```python
# tests/unit/test_pipgraph_manager.py

@pytest.mark.asyncio
async def test_extract_entities_without_saving(mock_graphiti):
    """Test that entities are extracted but NOT saved to Neo4j"""

    manager = PipGraphManager(mock_graphiti)

    entities, episode_uuid = await manager.extract_entities_from_note(
        note_content="Met with John Smith to discuss Q4 project",
        note_name="test.md",
        reference_time=datetime.now()
    )

    # Entities returned
    assert len(entities) > 0
    assert episode_uuid is not None

    # But NOT saved to Neo4j
    mock_graphiti.add_nodes_and_edges_bulk.assert_not_called()
```

**Definition of Done:**
- ✅ `extract_entities_from_note()` метод реализован
- ✅ Unit test проходит
- ✅ `extract_entities_node` обновлена
- ✅ E2E тест: entities извлекаются но НЕ сохраняются до finalize

**Ценность:**
- Пользователь видит сущности ДО того, как они попали в граф
- Можно тестировать extraction отдельно от saving
- Фундамент для остальных Quick Wins

---

### Days 2-3: UserCheckStatus Creation

**Задача:** Сохранять историю подтверждений пользователя в Neo4j

#### Day 2: Метод сохранения

```python
# backend/app/services/pipgraph_manager.py

async def save_entity_confirmation_check(
    self,
    entity_uuid: str,
    status: str,  # "confirmed" | "modified" | "rejected" | "skipped"
    user_action: str,
    confidence: float,
    modified_fields: Optional[List[str]] = None,
    modifications: Optional[List[dict]] = None,
    user_comment: Optional[str] = None,
    system_suggestion: Optional[str] = None
) -> str:
    """Создает UserCheckStatus node для entity confirmation"""

    check_id = f"check_{uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)

    # Serialize modifications if present
    modifications_json = None
    if modifications:
        modifications_json = json.dumps(modifications)

    query = """
    MATCH (e:EntityNode {uuid: $entity_uuid})

    CREATE (check:UserCheckStatus {
        id: $check_id,
        status: $status,
        confirmation_level: 'entity',
        confidence: $confidence,
        timestamp: $timestamp,
        user_action: $user_action,
        modified_fields: $modified_fields,
        modifications: $modifications,
        user_comment: $user_comment,
        system_suggestion: $system_suggestion,
        auto_confirmed: false,
        skip_count: 0
    })

    CREATE (e)-[:HAS_CHECK {is_current: true}]->(check)

    RETURN check.id AS check_id
    """

    params = {
        "entity_uuid": entity_uuid,
        "check_id": check_id,
        "status": status,
        "confidence": confidence,
        "timestamp": now,
        "user_action": user_action,
        "modified_fields": modified_fields,
        "modifications": modifications_json,
        "user_comment": user_comment,
        "system_suggestion": system_suggestion
    }

    async with self.driver.session() as session:
        result = await session.run(query, params)
        record = await result.single()
        return record["check_id"]
```

#### Day 3: Интеграция в workflow

```python
# backend/app/services/note_workflow.py

async def finalize_node(state: NoteWorkflowState) -> dict:
    """ОБНОВЛЕНО: сохраняем UserCheckStatus"""

    pipgraph = get_pipgraph_manager()

    user_action = state.get("user_answer", {}).get("action", "confirmed")
    entity_uuid = state["entities"][0]["uuid"]  # MVP: первая сущность

    # НОВОЕ: Сохраняем UserCheckStatus
    check_id = await pipgraph.save_entity_confirmation_check(
        entity_uuid=entity_uuid,
        status=user_action if user_action != "skip" else "skipped",
        user_action=user_action,
        confidence=0.85,  # TODO: from LLM
        user_comment=state.get("user_answer", {}).get("comment")
    )

    logger.info(f"[finalize] Created UserCheckStatus: {check_id}")

    # Остальная логика без изменений
    ...
```

#### Testing

```python
# tests/integration/test_user_check_status.py

@pytest.mark.asyncio
async def test_user_check_status_created(neo4j_driver):
    """Test that UserCheckStatus node is created in Neo4j"""

    manager = PipGraphManager(graphiti)

    # Create entity first
    entity_uuid = "test_entity_123"

    # Save confirmation
    check_id = await manager.save_entity_confirmation_check(
        entity_uuid=entity_uuid,
        status="confirmed",
        user_action="confirm",
        confidence=0.85
    )

    # Verify in Neo4j
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (e:EntityNode {uuid: $uuid})-[:HAS_CHECK {is_current: true}]->(check)
            RETURN check
            """,
            {"uuid": entity_uuid}
        )
        record = await result.single()

        assert record is not None
        check = record["check"]
        assert check["status"] == "confirmed"
        assert check["confirmation_level"] == "entity"
```

**Definition of Done:**
- ✅ `save_entity_confirmation_check()` метод реализован
- ✅ Unit tests для Cypher query проходят
- ✅ Integration test с Neo4j проходит
- ✅ `finalize_node` обновлена и создает UserCheckStatus
- ✅ E2E тест: история подтверждений видна в Neo4j

**Ценность:**
- Полная история решений пользователя
- Audit trail для всех подтверждений
- Можно анализировать паттерны подтверждений

---

### Day 4: Modify Entity Action

**Задача:** Пользователь может исправлять имена и атрибуты сущностей

#### Метод модификации

```python
# backend/app/services/pipgraph_manager.py

async def modify_entity_attributes(
    self,
    entity_uuid: str,
    changes: dict
) -> bool:
    """Применяет модификации пользователя к EntityNode"""

    # Build SET clauses dynamically
    set_clauses = []
    params = {"entity_uuid": entity_uuid}

    for field, value in changes.items():
        if field in ["name", "summary"]:
            # Top-level fields
            set_clauses.append(f"e.{field} = ${field}")
            params[field] = value
        else:
            # Nested in attributes (JSON field)
            # Note: Neo4j doesn't support nested JSON updates easily
            # Workaround: update entire attributes object
            set_clauses.append(f"e.attributes.{field} = ${field}")
            params[field] = value

    query = f"""
    MATCH (e:EntityNode {{uuid: $entity_uuid}})
    SET {', '.join(set_clauses)}
    RETURN e.uuid AS uuid
    """

    async with self.driver.session() as session:
        result = await session.run(query, params)
        return result.single() is not None
```

#### Интеграция в workflow

```python
# backend/app/services/note_workflow.py

async def finalize_node(state: NoteWorkflowState) -> dict:
    """ОБНОВЛЕНО: применяем модификации"""

    pipgraph = get_pipgraph_manager()
    user_answer = state.get("user_answer", {})

    if user_answer.get("action") == "modify":
        entity_uuid = state["entities"][0]["uuid"]
        modifications = user_answer.get("modifications", {})

        # НОВОЕ: Применяем модификации
        await pipgraph.modify_entity_attributes(
            entity_uuid=entity_uuid,
            changes=modifications
        )

        logger.info(f"[finalize] Modified entity: {entity_uuid}")

        # Сохраняем UserCheckStatus с modifications
        check_id = await pipgraph.save_entity_confirmation_check(
            entity_uuid=entity_uuid,
            status="modified",
            user_action="modify",
            confidence=0.85,
            modified_fields=list(modifications.keys()),
            modifications=[
                {
                    "field_name": k,
                    "original_value": None,  # TODO
                    "new_value": v,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                for k, v in modifications.items()
            ]
        )

    # Остальная логика...
```

#### Testing

```python
# tests/integration/test_entity_modification.py

@pytest.mark.asyncio
async def test_modify_entity_attributes(neo4j_driver):
    """Test entity modification"""

    manager = PipGraphManager(graphiti)

    # Create entity
    entity_uuid = "test_entity_456"

    # Modify
    success = await manager.modify_entity_attributes(
        entity_uuid=entity_uuid,
        changes={
            "name": "John K. Smith",
            "role": "CEO"
        }
    )

    assert success

    # Verify in Neo4j
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (e:EntityNode {uuid: $uuid}) RETURN e",
            {"uuid": entity_uuid}
        )
        record = await result.single()
        entity = record["e"]

        assert entity["name"] == "John K. Smith"
        assert entity["attributes"]["role"] == "CEO"
```

**Definition of Done:**
- ✅ `modify_entity_attributes()` метод реализован
- ✅ Unit tests проходят
- ✅ Integration test с Neo4j проходит
- ✅ `finalize_node` обрабатывает action="modify"
- ✅ E2E тест: пользователь может изменить имя сущности

**Ценность:**
- Пользователь может исправлять ошибки LLM
- FieldModification records в UserCheckStatus
- Улучшенное UX

---

### Day 5: E2E Testing + Quick Wins Integration

**Задача:** Протестировать полный flow с Quick Wins изменениями

#### E2E тест

```python
# tests/e2e/test_quick_wins_flow.py

@pytest.mark.asyncio
async def test_full_flow_with_quick_wins():
    """
    E2E тест полного flow с Quick Wins:
    1. Extract entities (NOT saved yet)
    2. User modifies entity
    3. UserCheckStatus created
    4. Modified entity saved to Neo4j
    """

    # 1. Start workflow
    thread_id = await start_workflow(
        file_path="test/quickwins.md",
        content="Met with John Smith to discuss Q4 project"
    )

    # 2. Get pending question
    state = await get_workflow_status(thread_id)
    assert state["status"] == "waiting_user"
    assert state["pending_question"]["entity_name"] == "John Smith"

    # 3. Modify entity name
    await resume_workflow(
        thread_id=thread_id,
        user_answer={
            "action": "modify",
            "modifications": {
                "name": "John K. Smith"
            }
        }
    )

    # 4. Verify UserCheckStatus created
    check_history = await pipgraph.get_check_history(entity_uuid)
    assert len(check_history) == 1
    assert check_history[0]["status"] == "modified"
    assert check_history[0]["modified_fields"] == ["name"]

    # 5. Verify entity modified in Neo4j
    entity = await pipgraph.get_entity_by_uuid(entity_uuid)
    assert entity.name == "John K. Smith"
```

**Definition of Done:**
- ✅ E2E тест проходит
- ✅ Все Quick Wins интегрированы
- ✅ Backward compatibility с старым API
- ✅ Документация обновлена

**Ценность:**
- Полная уверенность в Quick Wins
- Готово к feedback от пользователей

---

## Quick Wins Summary

**Итого 4-5 дней:**
- ✅ Extract entities without saving
- ✅ UserCheckStatus history в Neo4j
- ✅ Modify entity action
- ✅ E2E tests

**Добавлено методов:** 3 из 17 (18%)
**Ценность:** 70% от Full Implementation

**Рекомендация:** **НАЧАТЬ С ЭТОГО**, собрать feedback, затем решать про L1/L2.

---

## Phase 1: L1 PARA Classification (Days 6-8)

**Предусловие:** Quick Wins завершены

**Длительность:** 2-3 дня
**Риск:** Средний (новый LLM prompt)

### Day 6: PipGraphManager методы для L1

**Добавить 3 метода:**

```python
# 1. classify_para_type()
# 2. save_para_classification_check()
# 3. update_note_para_type()
```

**Детали:** См. [03_PIPGRAPH_MANAGER_REFACTORING.md](./03_PIPGRAPH_MANAGER_REFACTORING.md) §5

**Testing:**
- Unit tests для каждого метода
- Mock LLM responses для `classify_para_type()`

### Day 7: LangGraph nodes для L1

**Добавить 4 nodes:**

```python
# 1. classify_para_node
# 2. ask_para_confirmation_node
# 3. process_para_response_node
# 4. save_para_auto_node
```

**Детали:** См. [04_LANGGRAPH_WORKFLOW_UPDATED.md](./04_LANGGRAPH_WORKFLOW_UPDATED.md) §4

**Testing:**
- Unit tests для каждой node
- Integration tests с mock PipGraphManager

### Day 8: L1 Integration + Testing

**Задачи:**
- Добавить L1 поля в `NoteWorkflowState`
- Обновить REST API endpoints
- E2E тест L1 flow
- Performance testing (LLM latency)

**Definition of Done:**
- ✅ Все 3 L1 метода реализованы
- ✅ Все 4 L1 nodes реализованы
- ✅ E2E тест: PARA classification работает
- ✅ UserCheckStatus для L1 создается
- ✅ Latency < 2 секунды

---

## Phase 2: L2 Container Assignment (Days 9-11)

**Предусловие:** Phase 1 завершена

**Длительность:** 2-3 дня
**Риск:** Средний (embedding search)

### Day 9: PipGraphManager методы для L2

**Добавить 4 метода:**

```python
# 1. find_similar_containers() - embedding search
# 2. create_para_container()
# 3. link_note_to_container()
# 4. save_container_assignment_check()
```

**Детали:** См. [03_PIPGRAPH_MANAGER_REFACTORING.md](./03_PIPGRAPH_MANAGER_REFACTORING.md) §5

**Testing:**
- Unit tests
- Mock embedding responses

### Day 10: LangGraph nodes для L2

**Добавить 4 nodes:**

```python
# 1. find_containers_node
# 2. ask_container_node
# 3. process_container_response_node
# 4. assign_container_auto_node
```

**Детали:** См. [04_LANGGRAPH_WORKFLOW_UPDATED.md](./04_LANGGRAPH_WORKFLOW_UPDATED.md) §4

**Testing:**
- Unit tests для nodes
- Integration tests

### Day 11: L2 Integration + Testing

**Задачи:**
- Добавить L2 поля в State
- Создать Project/Area/Resource nodes в Neo4j schema
- E2E тест L1→L2 flow
- Performance testing (embedding search)

**Definition of Done:**
- ✅ Все 4 L2 метода реализованы
- ✅ Все 4 L2 nodes реализованы
- ✅ E2E тест: Container assignment работает
- ✅ PARA containers создаются в Neo4j
- ✅ [:IS_PART_OF] relationships создаются
- ✅ Latency < 1 секунда для search

---

## Phase 3: Full L3 + Auto-confirm (Days 12-15)

**Предусловие:** Phase 2 завершена

**Длительность:** 3-4 дня
**Риск:** Низкий (большая часть уже есть)

### Day 12: Remaining L3 методы

**Добавить 3 метода:**

```python
# 1. reject_entity()
# 2. get_entity_by_uuid()
# 3. bulk_save_confirmed_entities()
```

**Testing:**
- Unit tests
- Integration tests с Neo4j

### Day 13: Priority + Auto-confirm

**Добавить 2 метода (pure functions):**

```python
# 1. calculate_entity_priority()
# 2. should_auto_confirm()
```

**Добавить node:**

```python
# prioritize_entities_node
```

**Testing:**
- Unit tests для priority logic
- Verify auto-confirm rate > 50%

### Days 14-15: Full Flow Integration

**Задачи:**
- Интегрировать все nodes в один граф
- Обновить conditional edges
- E2E тест L1→L2→L3 полного flow
- Performance testing всего workflow

**Definition of Done:**
- ✅ Все 17 методов PipGraphManager реализованы
- ✅ Все 10-12 nodes LangGraph реализованы
- ✅ E2E тест полного flow проходит
- ✅ Auto-confirm работает для >50% entities
- ✅ Приоритизация работает корректно
- ✅ UserCheckStatus для всех уровней создается

---

## Phase 4: History + Polish (Day 16)

**Предусловие:** Phase 3 завершена

**Длительность:** 1 день
**Риск:** Низкий

### Day 16: Finalization

**Добавить 2 метода:**

```python
# 1. update_check_status() - NEXT chain
# 2. get_check_history()
```

**Задачи:**
- Тесты для history chain
- Update documentation
- Performance benchmarks
- Production readiness checklist

**Definition of Done:**
- ✅ History chain работает
- ✅ Вся документация обновлена
- ✅ Performance benchmarks пройдены
- ✅ Готово к production

---

## Testing Strategy

### Unit Tests

**Coverage target:** >90%

```
tests/unit/
├── test_pipgraph_manager.py       # Все 17 методов
├── test_workflow_nodes.py          # Все nodes
├── test_priority_logic.py          # Priority helpers
└── test_state_serialization.py    # State model
```

### Integration Tests

**Coverage target:** Все critical paths

```
tests/integration/
├── test_neo4j_operations.py       # CRUD operations
├── test_user_check_status.py      # UserCheckStatus creation
├── test_para_containers.py        # Container management
└── test_workflow_persistence.py   # Checkpoint/resume
```

### E2E Tests

**Coverage target:** Все user scenarios

```
tests/e2e/
├── test_quick_wins_flow.py        # Quick Wins scenario
├── test_full_l1_l2_l3_flow.py     # Full workflow
├── test_auto_confirm_flow.py      # Auto-confirm scenario
└── test_modification_flow.py      # Modify entities scenario
```

---

## Risks & Mitigation

### Risk 1: LLM Latency

**Проблема:** PARA classification может быть медленной (>3 секунды)

**Митигация:**
- Кэшировать classifications для похожих заметок
- Batch processing для multiple notes
- Использовать быстрые модели (GPT-3.5 вместо GPT-4)

### Risk 2: Neo4j Schema Changes

**Проблема:** UserCheckStatus nodes могут конфликтовать с существующей схемой

**Митигация:**
- Тщательный review схемы перед началом
- Migration scripts для существующих данных
- Backward compatibility layer

### Risk 3: State Serialization Issues

**Проблема:** Расширенный State может не сериализоваться

**Митигация:**
- Все поля должны быть JSON-serializable
- `total=False` в TypedDict
- Тесты для serialization/deserialization

### Risk 4: Auto-confirm False Positives

**Проблема:** Auto-confirm может пропустить ошибки LLM

**Митигация:**
- Консервативные thresholds (confidence > 0.95)
- User feedback loop для adjustment
- Audit trail в UserCheckStatus

---

## Success Metrics

### Code Quality

- ✅ PipGraphManager: 17 методов, <100 строк каждый
- ✅ LangGraph: 10-12 nodes, <50 строк каждая
- ✅ Test coverage >90%
- ✅ No Cypher in LangGraph nodes

### Functionality

- ✅ L1/L2/L3 работают end-to-end
- ✅ Auto-confirm rate >50%
- ✅ UserCheckStatus history полная
- ✅ PARA containers создаются корректно

### Performance

- ✅ L1 latency <2 секунды
- ✅ L2 latency <1 секунда
- ✅ L3 latency 3-5 секунд
- ✅ Interrupt/resume <500ms

### User Experience

- ✅ User questions reduced by >50% (auto-confirm)
- ✅ Modification workflow intuitive
- ✅ Clear confirmation messages

---

## Rollout Strategy

### Week 1: Quick Wins

- Days 1-5: Implement Quick Wins
- Deploy to staging
- Internal testing
- Collect feedback

### Week 2: L1 + L2

- Days 6-11: Implement L1 and L2
- Deploy to staging
- Beta users testing
- Iterate based on feedback

### Week 3: Full L3 + Production

- Days 12-16: Full L3 + Polish
- Production deployment
- Monitor metrics
- Hotfix if needed

---

## Rollback Plan

Если что-то пойдет не так, откат выполняется в 3 этапа:

### Rollback Level 1: Feature Flag

```python
# backend/app/core/config.py

class Settings(BaseSettings):
    ENABLE_L1_PARA_CLASSIFICATION: bool = False
    ENABLE_L2_CONTAINER_ASSIGNMENT: bool = False
    ENABLE_AUTO_CONFIRM: bool = False
```

**Действие:** Отключить новые фичи через env vars

### Rollback Level 2: Use Legacy process_note()

```python
# backend/app/services/note_workflow.py

async def extract_entities_node(state):
    if USE_LEGACY_MODE:
        # Используем старый process_note()
        result = await pipgraph.process_note(...)
    else:
        # Используем новый extract_entities_from_note()
        entities, uuid = await pipgraph.extract_entities_from_note(...)
```

**Действие:** Переключиться на legacy метод

### Rollback Level 3: Full Revert

**Действие:** Git revert к последнему stable commit

**Риск:** Потеря UserCheckStatus данных (но episodes/entities сохранены)

---

## Next Steps

**После Quick Wins:**
1. Собрать user feedback (1 неделя)
2. Определить priority: L1 или L2 первым?
3. Начать Phase 1

**После Full Implementation:**
1. Production monitoring (2 недели)
2. Optimize slow parts
3. Расширить auto-confirm логику
4. Добавить analytics dashboard

---

## Заключение

**Quick Wins Path (рекомендуется):**
- 4-5 дней
- 70% ценности
- Низкий риск
- Немедленный feedback

**Full Implementation Path:**
- 11-16 дней
- 100% ценности
- Полный L1/L2/L3 workflow
- Production-ready

**Рекомендация:** Начать с Quick Wins, собрать feedback, затем решать про L1/L2.

---

**Готово к началу работы!** 🚀

**Следующий шаг:** Читай [README.md](./README.md) для навигации по всей серии.
