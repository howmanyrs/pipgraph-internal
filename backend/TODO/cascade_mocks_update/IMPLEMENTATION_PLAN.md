# Cascade Mock Implementation Plan

Пошаговый план реализации cascade функционала для автоматического разрешения похожих suggestions.

---

## Phase 1: CRUD Extensions

Расширить `RelationshipCRUD` методами для cascade queries.

**File**: `backend/app/crud/relationship_crud.py`

- [x] **1.1** Добавить метод `get_suggestions_by_container(container_id: str) -> list[dict]`
  - Query: найти все `:SUGGESTS` ведущие к конкретному container
  - Return: list of suggestion dicts with episodic_path, confidence, suggestion_id

- [x] **1.2** Добавить метод `get_all_pending_suggestions() -> list[dict]`
  - Query: найти все `:SUGGESTS` в графе
  - Return: list with note_path, container info, confidence
  - Для: Inbox endpoint

- [x] **1.3** Добавить метод `find_episodics_for_container(container_id: str) -> list[str]`
  - Query: найти все Episodic с `:IS_PART_OF` к container
  - Return: list of episodic paths
  - Для: контекст при cascade

- [x] **1.4** Добавить метод `batch_resolve_suggestions(suggestion_ids: list[str], container_id: str)`
  - Транзакция: удалить `:SUGGESTS`, создать `:IS_PART_OF` для списка
  - Для: эффективный cascade apply

---

## Phase 2: Cascade Service

Создать сервис для логики cascade.

**File**: `backend/app/services/cascade_service.py`

- [x] **2.1** Создать класс `CascadeService`
  - Dependencies: RelationshipCRUD, settings
  - Config: cascade_threshold (default 0.85)

- [x] **2.2** Метод `find_cascade_candidates(container_id: str, exclude_suggestion_id: str) -> list[CascadeCandidate]`
  - Найти все `:SUGGESTS` к тому же container
  - Исключить текущий suggestion_id
  - Return: list of candidates with confidence

- [x] **2.3** Метод `apply_cascade(container_id: str, candidates: list[CascadeCandidate]) -> CascadeResult`
  - Фильтр по threshold
  - Вызвать batch_resolve_suggestions
  - Return: list of applied, list of skipped

- [x] **2.4** Метод `process_decision_with_cascade(suggestion_id: str, decision: UserDecision) -> DecisionWithCascadeResult`
  - Основной метод: обработать decision + cascade
  - Return: decision_result + cascade_applied

- [x] **2.5** Добавить Pydantic модели
  - `CascadeCandidate` - suggestion info + confidence
  - `CascadeResult` - applied + skipped lists
  - `DecisionWithCascadeResult` - combined response

---

## Phase 3: Mock Cascade

Создать детерминированный мок для тестирования.

**File**: `backend/app/services/mocks/mock_cascade.py`

- [x] **3.1** Функция `mock_find_cascade_candidates(container_id: str) -> list[dict]`
  - Возвращает фиксированный список (2 candidates)
  - Confidence: 0.92, 0.73 (один пройдет threshold, один нет)

- [x] **3.2** Функция `mock_apply_cascade(candidates: list[dict], threshold: float) -> dict`
  - Детерминированная фильтрация
  - Return: {applied: [...], skipped: [...]}

- [x] **3.3** Обновить `backend/app/services/mocks/__init__.py`
  - Экспорт новых mock функций

---

## Phase 4: Workflow Integration

Интегрировать cascade в workflow processing.

**File**: `backend/app/workflows/para_workflow.py`

- [x] **4.1** Обновить `process_decision_node`
  - После process_user_decision вызвать cascade_service.find_cascade_candidates
  - Применить cascade если есть candidates
  - Добавить результат в state

- [x] **4.2** Обновить `PARAWorkflowState`
  - Добавить поле `cascade_result: Optional[dict]`
  - Для tracking что было auto-resolved

**File**: `backend/app/services/pipgraph_manager.py`

- [x] **4.3** Рефакторинг `process_user_decision`
  - Вернуть container_id после confirm
  - Для передачи в cascade service

---

## Phase 5: Test Script

Один тестовый скрипт для проверки cascade функционала (по образцу `test_iteration5_workflow.py`).

**File**: `backend/scripts/test_cascade_workflow.py`

- [x] **5.1** Setup test data
  - Создать container (Project)
  - Создать 3 Episodic nodes
  - Создать :SUGGESTS для каждого к одному container
  - Разные confidence: 0.92, 0.88, 0.73

- [x] **5.2** Test cascade auto-resolve
  - Confirm первый suggestion
  - Проверить что второй (0.88 > 0.85) auto-resolved
  - Проверить что третий (0.73 < 0.85) остался pending

- [x] **5.3** Verification queries
  - Вывести Neo4j queries для проверки в Browser
  - Check :IS_PART_OF relationships
  - Check remaining :SUGGESTS

- [x] **5.4** Cleanup
  - Удалить тестовые данные

---

## Acceptance Criteria

### Functional

- [x] При confirm suggestion автоматически находятся похожие
- [x] Cascade применяется только для confidence > 0.85
- [x] Cascade result доступен в workflow state
- [x] Workflows корректно resume после cascade

### Non-functional

- [x] Mock cascade детерминированный
- [x] Batch operations для эффективности
- [x] Все методы async
- [x] Type hints и Pydantic models

---

## Dependencies

Этот план зависит от:
- [x] Iteration 1-5 из MOCK_IMPLEMENTATION_CHECKLIST.md (выполнено)
- [x] RelationshipCRUD base implementation (выполнено)
- [x] LangGraph workflow with interrupt (выполнено)

---

## Notes

### Threshold Tuning

Начальный threshold 0.85 - можно настроить после тестирования с реальными данными. В mock используем фиксированные значения для предсказуемости.

### Future Enhancements

После базовой реализации можно добавить:
- Cascade preview endpoint для UI confirmation
- Grouping suggestions by container in inbox
- Similarity search через embeddings (вместо same container)
