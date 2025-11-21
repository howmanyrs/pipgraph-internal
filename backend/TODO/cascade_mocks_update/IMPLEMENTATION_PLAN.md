# Cascade Mock Implementation Plan

Пошаговый план реализации cascade функционала для автоматического разрешения похожих suggestions.

---

## Phase 1: CRUD Extensions

Расширить `RelationshipCRUD` методами для cascade queries.

**File**: `backend/app/crud/relationship_crud.py`

- [ ] **1.1** Добавить метод `get_suggestions_by_container(container_id: str) -> list[dict]`
  - Query: найти все `:SUGGESTS` ведущие к конкретному container
  - Return: list of suggestion dicts with episodic_path, confidence, suggestion_id

- [ ] **1.2** Добавить метод `get_all_pending_suggestions() -> list[dict]`
  - Query: найти все `:SUGGESTS` в графе
  - Return: list with note_path, container info, confidence
  - Для: Inbox endpoint

- [ ] **1.3** Добавить метод `find_episodics_for_container(container_id: str) -> list[str]`
  - Query: найти все Episodic с `:IS_PART_OF` к container
  - Return: list of episodic paths
  - Для: контекст при cascade

- [ ] **1.4** Добавить метод `batch_resolve_suggestions(suggestion_ids: list[str], container_id: str)`
  - Транзакция: удалить `:SUGGESTS`, создать `:IS_PART_OF` для списка
  - Для: эффективный cascade apply

---

## Phase 2: Cascade Service

Создать сервис для логики cascade.

**File**: `backend/app/services/cascade_service.py`

- [ ] **2.1** Создать класс `CascadeService`
  - Dependencies: RelationshipCRUD, settings
  - Config: cascade_threshold (default 0.85)

- [ ] **2.2** Метод `find_cascade_candidates(container_id: str, exclude_suggestion_id: str) -> list[CascadeCandidate]`
  - Найти все `:SUGGESTS` к тому же container
  - Исключить текущий suggestion_id
  - Return: list of candidates with confidence

- [ ] **2.3** Метод `apply_cascade(container_id: str, candidates: list[CascadeCandidate]) -> CascadeResult`
  - Фильтр по threshold
  - Вызвать batch_resolve_suggestions
  - Return: list of applied, list of skipped

- [ ] **2.4** Метод `process_decision_with_cascade(suggestion_id: str, decision: UserDecision) -> DecisionWithCascadeResult`
  - Основной метод: обработать decision + cascade
  - Return: decision_result + cascade_applied

- [ ] **2.5** Добавить Pydantic модели
  - `CascadeCandidate` - suggestion info + confidence
  - `CascadeResult` - applied + skipped lists
  - `DecisionWithCascadeResult` - combined response

---

## Phase 3: Mock Cascade

Создать детерминированный мок для тестирования.

**File**: `backend/app/services/mocks/mock_cascade.py`

- [ ] **3.1** Функция `mock_find_cascade_candidates(container_id: str) -> list[dict]`
  - Возвращает фиксированный список (2 candidates)
  - Confidence: 0.92, 0.73 (один пройдет threshold, один нет)

- [ ] **3.2** Функция `mock_apply_cascade(candidates: list[dict], threshold: float) -> dict`
  - Детерминированная фильтрация
  - Return: {applied: [...], skipped: [...]}

- [ ] **3.3** Обновить `backend/app/services/mocks/__init__.py`
  - Экспорт новых mock функций

---

## Phase 4: Workflow Integration

Интегрировать cascade в workflow processing.

**File**: `backend/app/workflows/para_workflow.py`

- [ ] **4.1** Обновить `process_decision_node`
  - После process_user_decision вызвать cascade_service.find_cascade_candidates
  - Применить cascade если есть candidates
  - Добавить результат в state

- [ ] **4.2** Обновить `PARAWorkflowState`
  - Добавить поле `cascade_result: Optional[dict]`
  - Для tracking что было auto-resolved

**File**: `backend/app/services/pipgraph_manager.py`

- [ ] **4.3** Рефакторинг `process_user_decision`
  - Вернуть container_id после confirm
  - Для передачи в cascade service

---

## Phase 5: API Endpoints

Добавить/расширить endpoints.

**File**: `backend/app/api/routes/workflow.py` (или новый файл)

- [ ] **5.1** Endpoint `GET /inbox/suggestions`
  - Вызвать relationship_crud.get_all_pending_suggestions()
  - Return: list of suggestions with grouping by container (optional)

- [ ] **5.2** Расширить response `POST /suggestion/{id}/decision`
  - Добавить `cascade_applied` в response
  - Schema update для DecisionResponse

- [ ] **5.3** Добавить Pydantic schemas
  - `InboxSuggestionsResponse`
  - `DecisionResponseWithCascade`

---

## Phase 6: Tests

Unit и integration тесты.

**File**: `backend/tests/unit/services/test_cascade_service.py`

- [ ] **6.1** Test `find_cascade_candidates`
  - Setup: create container + multiple suggestions
  - Assert: returns correct candidates

- [ ] **6.2** Test `apply_cascade` с threshold
  - Setup: candidates with different confidence
  - Assert: only high confidence applied

- [ ] **6.3** Test `process_decision_with_cascade`
  - Full flow test

**File**: `backend/tests/unit/services/test_mock_cascade.py`

- [ ] **6.4** Test mock determinism
  - Assert: всегда возвращает одинаковый результат

**File**: `backend/tests/integration/test_workflow_cascade.py`

- [ ] **6.5** Test workflow with cascade
  - Create 3 notes with suggestions to same container
  - Confirm one
  - Assert: other 2 auto-resolved

- [ ] **6.6** Test cascade threshold
  - One candidate above threshold, one below
  - Assert: only one applied

**File**: `backend/tests/integration/test_inbox_endpoint.py`

- [ ] **6.7** Test `GET /inbox/suggestions`
  - Setup: multiple pending suggestions
  - Assert: all returned with correct format

---

## Acceptance Criteria

### Functional

- [ ] При confirm suggestion автоматически находятся похожие
- [ ] Cascade применяется только для confidence > 0.85
- [ ] Response включает информацию о cascade
- [ ] Inbox endpoint возвращает все pending suggestions
- [ ] Workflows корректно resume после cascade

### Non-functional

- [ ] Mock cascade детерминированный
- [ ] Batch operations для эффективности
- [ ] Все методы async
- [ ] Type hints и Pydantic models

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
