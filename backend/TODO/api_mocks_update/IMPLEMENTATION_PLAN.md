# API Update Implementation Plan

Пошаговый план обновления REST API для работы с mock workflow.

---

## Phase 1: API Structure Refactoring

Реорганизация файловой структуры и маршрутов.

### 1.1 Create New Files

- [ ] **1.1.1** Создать `backend/app/api/endpoints/workflow.py`
  - Пустой файл с router setup
  - `router = APIRouter(prefix="/workflow", tags=["workflow"])`

- [ ] **1.1.2** Создать `backend/app/api/endpoints/suggestions.py`
  - Пустой файл с router setup
  - `router = APIRouter(prefix="/suggestion", tags=["suggestions"])`

- [ ] **1.1.3** Создать `backend/app/api/schemas/` директорию
  - `__init__.py`
  - `workflow.py`
  - `suggestions.py`

### 1.2 Update Main Router

- [ ] **1.2.1** Обновить `backend/app/api/main.py`
  - Импортировать новые routers
  - Зарегистрировать под `/api/v1/`

### 1.3 ID Schema Change

- [ ] **1.3.1** Создать функцию генерации workflow_id
  - Формат: `wf_{uuid_short}` (например `wf_a1b2c3d4`)
  - Без специальных символов (URL-safe)

- [ ] **1.3.2** Обновить LangGraph thread_id generation
  - Использовать новый формат вместо `note:path`

- [ ] **1.3.3** Добавить mapping workflow_id ↔ note_path
  - В Neo4j или в памяти (для начала)

---

## Phase 2: Workflow Endpoints

Основные endpoints для управления workflow.

**File**: `backend/app/api/endpoints/workflow.py`

### 2.1 Start Workflow

- [ ] **2.1.1** Endpoint `POST /workflow/start`
  - Request: `WorkflowCreateRequest(file_path, content)`
  - Response: `WorkflowCreateResponse(workflow_id, status, file_path)`
  - Вызывает `run_para_workflow()`

- [ ] **2.1.2** Обработка ошибок
  - 400: Invalid request
  - 500: Workflow creation failed

### 2.2 Get Status

- [ ] **2.2.1** Endpoint `GET /workflow/{workflow_id}/status`
  - Response: `WorkflowStatusResponse`
  - Поля: workflow_id, status, file_path, pending_question, episode_uuid, error

- [ ] **2.2.2** Статусы workflow
  - `processing` - выполняется
  - `waiting_user` - ждет решения пользователя
  - `completed` - завершен
  - `error` - ошибка

### 2.3 Resume Workflow

- [ ] **2.3.1** Endpoint `POST /workflow/{workflow_id}/resume`
  - Request: `WorkflowResumeRequest(answer)`
  - Response: `WorkflowResumeResponse(status, next_question)`
  - Вызывает workflow resume с user answer

---

## Phase 3: Suggestions Endpoints

Endpoints для работы с suggestions.

**File**: `backend/app/api/endpoints/suggestions.py`

### 3.1 Get Workflow Suggestions

- [ ] **3.1.1** Endpoint `GET /workflow/{workflow_id}/suggestions`
  - Response: `SuggestionsResponse(workflow_id, suggestions[])`
  - Включает alternatives для каждого suggestion

- [ ] **3.1.2** Формат suggestion
  ```python
  {
    "suggestion_id": str,
    "suggestion_type": str,  # "para_link" | "property_update"
    "container_type": str,   # "Project" | "Area" | ...
    "container_name": str,
    "confidence": float,
    "alternatives": list
  }
  ```

### 3.2 Submit Decision

- [ ] **3.2.1** Endpoint `POST /suggestion/{suggestion_id}/decision`
  - Request: `DecisionRequest(action, modified_value?)`
  - Response: `DecisionResponse(success, workflow_id, cascade_applied)`

- [ ] **3.2.2** Поддерживаемые actions
  - `confirm` - подтвердить suggestion
  - `dismiss` - отклонить
  - `modify` - изменить значение
  - `create_custom` - создать свой container

- [ ] **3.2.3** Cascade integration
  - Вызвать cascade после decision
  - Включить `cascade_applied` в response

---

## Phase 4: Inbox Endpoint

Endpoint для получения всех pending suggestions.

**File**: `backend/app/api/endpoints/suggestions.py`

### 4.1 Get All Pending

- [ ] **4.1.1** Endpoint `GET /inbox/suggestions`
  - Response: `InboxResponse(suggestions[], total_count)`
  - Вызывает `relationship_crud.get_all_pending_suggestions()`

- [ ] **4.1.2** Формат inbox suggestion
  ```python
  {
    "suggestion_id": str,
    "workflow_id": str,
    "note_path": str,
    "suggestion_type": str,
    "container_name": str,
    "confidence": float,
    "created_at": datetime
  }
  ```

### 4.2 Count Endpoint (Optional)

- [ ] **4.2.1** Endpoint `GET /inbox/count`
  - Response: `{"count": int}`
  - Для badge в UI

---

## Phase 5: Schemas & Documentation

Pydantic models и документация.

**File**: `backend/app/api/schemas/workflow.py`

### 5.1 Workflow Schemas

- [ ] **5.1.1** `WorkflowCreateRequest`
  - file_path: str
  - content: str

- [ ] **5.1.2** `WorkflowCreateResponse`
  - workflow_id: str
  - status: str
  - file_path: str

- [ ] **5.1.3** `WorkflowStatusResponse`
  - workflow_id: str
  - status: str
  - file_path: Optional[str]
  - pending_question: Optional[dict]
  - episode_uuid: Optional[str]
  - error: Optional[str]

- [ ] **5.1.4** `WorkflowResumeRequest`
  - answer: dict

- [ ] **5.1.5** `WorkflowResumeResponse`
  - workflow_id: str
  - status: str
  - next_question: Optional[dict]

**File**: `backend/app/api/schemas/suggestions.py`

### 5.2 Suggestion Schemas

- [ ] **5.2.1** `SuggestionItem`
  - suggestion_id: str
  - suggestion_type: str
  - container_type: str
  - container_name: str
  - confidence: float
  - alternatives: list

- [ ] **5.2.2** `SuggestionsResponse`
  - workflow_id: str
  - suggestions: list[SuggestionItem]

- [ ] **5.2.3** `DecisionRequest`
  - action: str
  - modified_value: Optional[str]
  - custom_container_name: Optional[str]

- [ ] **5.2.4** `DecisionResponse`
  - success: bool
  - workflow_id: str
  - suggestion_id: str
  - action: str
  - cascade_applied: list

- [ ] **5.2.5** `InboxSuggestion`
  - suggestion_id: str
  - workflow_id: str
  - note_path: str
  - suggestion_type: str
  - container_name: str
  - confidence: float
  - created_at: datetime

- [ ] **5.2.6** `InboxResponse`
  - suggestions: list[InboxSuggestion]
  - total_count: int

### 5.3 Documentation

- [ ] **5.3.1** Добавить docstrings к endpoints
  - Описание
  - Примеры request/response

- [ ] **5.3.2** Проверить OpenAPI docs
  - `GET /docs` должен показывать все endpoints
  - Правильные schemas

- [ ] **5.3.3** Добавить curl примеры в README
  - Start workflow
  - Get suggestions
  - Submit decision
  - Get inbox

---

## Phase 6: Tests

Unit и integration тесты для API.

**File**: `backend/tests/api/test_workflow_endpoints.py`

- [ ] **6.1** Test `POST /workflow/start`
  - Valid request → 200, workflow_id returned
  - Invalid request → 400

- [ ] **6.2** Test `GET /workflow/{id}/status`
  - Existing workflow → 200, status
  - Non-existing → 404

- [ ] **6.3** Test `POST /workflow/{id}/resume`
  - Valid answer → 200, updated status
  - Invalid workflow_id → 404

**File**: `backend/tests/api/test_suggestions_endpoints.py`

- [ ] **6.4** Test `GET /workflow/{id}/suggestions`
  - Workflow with suggestions → 200, list
  - No suggestions → 200, empty list

- [ ] **6.5** Test `POST /suggestion/{id}/decision`
  - Valid decision → 200, success
  - Invalid suggestion_id → 404
  - Invalid action → 400

- [ ] **6.6** Test `GET /inbox/suggestions`
  - With pending → 200, list
  - Empty → 200, empty list

---

## Acceptance Criteria

### Functional

- [ ] CLI может запустить workflow через `POST /workflow/start`
- [ ] CLI может получить статус через `GET /workflow/{id}/status`
- [ ] CLI может получить suggestions через `GET /workflow/{id}/suggestions`
- [ ] CLI может отправить decision через `POST /suggestion/{id}/decision`
- [ ] CLI может получить inbox через `GET /inbox/suggestions`
- [ ] Все endpoints возвращают корректные JSON responses

### Non-functional

- [ ] workflow_id URL-safe (без спец. символов)
- [ ] OpenAPI docs актуальны
- [ ] Все schemas валидируются Pydantic
- [ ] Error responses с понятными сообщениями

---

## Dependencies

### Зависит от:
- [x] Mock реализации (L1, L2, L3) - выполнено
- [x] LangGraph workflow с interrupts - выполнено
- [x] RelationshipCRUD для suggestions - выполнено

### Блокирует:
- Cascade functionality (использует decision endpoint)
- CLI update (использует новые endpoints)

---

## Migration Notes

### Deprecation

Старые endpoints остаются для обратной совместимости:
- `POST /api/v1/notes/workflow/start` → deprecated
- `POST /api/v1/notes/workflow/resume` → deprecated
- `GET /api/v1/notes/workflow/status/{id}` → deprecated

Добавить deprecation warnings в логи.

### Breaking Changes

- `thread_id` заменен на `workflow_id`
- Новый формат ID (без двоеточий)
- Структура response изменена

CLI нужно обновить для работы с новыми endpoints.
