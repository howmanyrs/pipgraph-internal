# Changelog: LangGraph Workflow MVP

**Дата:** 2025-11-17
**Версия:** 0.1.0 (MVP)
**Тип:** Feature - новая функциональность

---

## Обзор изменений

Добавлен минимальный рабочий каркас LangGraph workflow для обработки заметок с поддержкой interrupt/resume механизма. MVP демонстрирует один вопрос пользователю (L3: entity confirmation) и может быть расширен до полной системы многоуровневых подтверждений (L1/L2/L3).

---

## Новые файлы

### Models
- **`app/models/workflow_state.py`**
  - `NoteWorkflowState` (TypedDict) - состояние для LangGraph
  - `ClarificationQuestion` - структура вопроса пользователю
  - `UserAnswer` - структура ответа
  - `WorkflowStatus` - статус для API
  - Утилиты сериализации `EntityNode`

### Services
- **`app/services/note_workflow.py`**
  - `extract_entities_node` - извлечение через PipGraphManager
  - `ask_user_node` - вопрос пользователю (INTERRUPT)
  - `finalize_node` - завершение обработки
  - `should_ask_user` - условная логика
  - `create_workflow()` - построение StateGraph
  - `app` - скомпилированный workflow с AsyncSqliteSaver
  - Helper функции: `start_workflow()`, `resume_workflow()`, `get_workflow_status()`

### API
- **`app/api/websockets/workflow.py`**
  - WebSocket endpoint `/ws/workflow`
  - Обработка сообщений: `start`, `answer`, `status`
  - Real-time коммуникация с клиентом

### Documentation
- **`docs/WORKFLOW_MVP.md`**
  - Полное руководство по использованию
  - Примеры REST API и WebSocket
  - Инструкции по расширению
  - FAQ и troubleshooting

- **`QUICKSTART_WORKFLOW.md`**
  - Быстрый старт для первого запуска
  - Установка зависимостей
  - Проверка работоспособности

### Tests
- **`test_workflow_mvp.py`**
  - Автоматический тест через REST API
  - Демонстрация полного цикла: start → question → answer → complete

---

## Измененные файлы

### Dependencies
- **`requirements.txt`**
  - Добавлено: `langgraph>=0.2.0`
  - Добавлено: `langchain-core>=0.3.0`
  - Добавлено: `aiosqlite>=0.20.0`

### API
- **`app/api/main.py`**
  - Импортирован `workflow` router
  - Подключен WebSocket endpoint

- **`app/api/endpoints/notes.py`**
  - Добавлены модели: `WorkflowStartRequest`, `WorkflowResumeRequest`, `WorkflowStatusResponse`
  - Добавлены endpoints:
    - `POST /notes/workflow/start` - запуск workflow
    - `POST /notes/workflow/resume` - возобновление с ответом
    - `GET /notes/workflow/status/{thread_id}` - получение статуса

---

## Новые зависимости

```txt
langgraph>=0.2.0       # Orchestration framework для stateful workflows
langchain-core>=0.3.0  # Базовые компоненты LangChain
aiosqlite>=0.20.0      # Async SQLite для persistence
```

**Установка:**
```bash
pip install -r requirements.txt
```

---

## API Endpoints

### REST API (новые)

#### POST `/api/v1/notes/workflow/start`
Запуск нового workflow для заметки.

**Request:**
```json
{
  "file_path": "meetings/test.md",
  "content": "# Meeting notes..."
}
```

**Response:**
```json
{
  "thread_id": "note:meetings/test.md",
  "status": "processing",
  "pending_question": {
    "question_id": "abc-123",
    "question_type": "entity_confirmation",
    "question_text": "Подтвердите сущность: John Smith (Person)?",
    "entity_uuid": "ent_456",
    "entity_name": "John Smith",
    "entity_type": "Person",
    "suggested_action": "confirm",
    "confidence": 0.85
  }
}
```

#### POST `/api/v1/notes/workflow/resume`
Возобновление workflow с ответом пользователя.

**Request:**
```json
{
  "thread_id": "note:meetings/test.md",
  "answer": {
    "question_id": "abc-123",
    "action": "confirm"
  }
}
```

**Response:**
```json
{
  "thread_id": "note:meetings/test.md",
  "status": "completed",
  "episode_uuid": "episode_789"
}
```

#### GET `/api/v1/notes/workflow/status/{thread_id}`
Получить текущий статус workflow.

**Response:**
```json
{
  "thread_id": "note:meetings/test.md",
  "status": "completed",
  "episode_uuid": "episode_789"
}
```

### WebSocket (новый)

#### WS `/ws/workflow`

**Клиент → Сервер (start):**
```json
{
  "type": "start",
  "file_path": "meetings/test.md",
  "content": "# Meeting notes..."
}
```

**Сервер → Клиент (question):**
```json
{
  "type": "question",
  "thread_id": "note:meetings/test.md",
  "data": {
    "question_id": "abc-123",
    "question_text": "Подтвердите сущность: John Smith (Person)?"
  }
}
```

**Клиент → Сервер (answer):**
```json
{
  "type": "answer",
  "thread_id": "note:meetings/test.md",
  "data": {
    "question_id": "abc-123",
    "action": "confirm"
  }
}
```

**Сервер → Клиент (completed):**
```json
{
  "type": "completed",
  "thread_id": "note:meetings/test.md",
  "data": {
    "episode_uuid": "episode_789"
  }
}
```

---

## Архитектурные решения

### 1. Параллельная работа с существующим API

- Старый endpoint `/ws/notes/process` продолжает работать
- Новый workflow `/notes/workflow/start` работает параллельно
- Постепенная миграция без breaking changes

### 2. Использование существующего PipGraphManager

- Workflow использует `PipGraphManager.process_note()` как есть
- Нет дублирования логики извлечения сущностей
- Легко расширяемо (точки интервенции уже есть в PipGraphManager)

### 3. Persistence через AsyncSqliteSaver

- Состояние сохраняется в `workflow_checkpoints.db`
- Workflow можно возобновить после перезапуска сервера
- В production легко заменить на Redis/Postgres

### 4. Два способа взаимодействия

- **REST API** - для тестирования и отладки
- **WebSocket** - для real-time коммуникации с UI

---

## Что реализовано в MVP

✅ **Базовый workflow:**
- 3 узла: extract → ask → finalize
- Условная логика (нужен ли вопрос?)
- Interrupt/resume механизм

✅ **Persistence:**
- AsyncSqliteSaver для состояния
- Возобновление после перезапуска

✅ **API:**
- REST endpoints для start/resume/status
- WebSocket для real-time

✅ **Интеграция:**
- Использует PipGraphManager
- Работает с Neo4j через Graphiti

✅ **Один вопрос:**
- L3: entity confirmation (первая сущность)

---

## Что НЕ реализовано (для будущих фаз)

❌ **L1/L2 подтверждения:**
- PARA classification (L1)
- Container assignment (L2)

❌ **Множественные вопросы:**
- Приоритизация
- Batch questions

❌ **Действия пользователя:**
- Modify не применяется к сущности
- Reject не удаляет сущность
- Skip не сохраняется

❌ **История:**
- UserCheckStatus nodes в Neo4j
- Связи через `:NEXT`

❌ **Auto-confirm:**
- Нет автоподтверждения высокоуверенных сущностей

---

## Миграция / Обратная совместимость

### Для существующих пользователей

1. **Ничего не меняется** - старый API продолжает работать
2. **Опционально** - можно попробовать новый `/notes/workflow/start`
3. **Новые зависимости** - требуется `pip install -r requirements.txt`

### Для разработчиков

1. **Установить зависимости:**
   ```bash
   pip install langgraph>=0.2.0 langchain-core>=0.3.0 aiosqlite>=0.20.0
   ```

2. **Запустить тест:**
   ```bash
   python test_workflow_mvp.py
   ```

3. **Читать документацию:**
   - [QUICKSTART_WORKFLOW.md](QUICKSTART_WORKFLOW.md)
   - [docs/WORKFLOW_MVP.md](docs/WORKFLOW_MVP.md)

---

## Следующие шаги (после MVP)

### Фаза 1: L1/L2 подтверждения (1-2 недели)
- Добавить PARA classification (L1)
- Добавить container assignment (L2)
- Создать PARA nodes в Neo4j

### Фаза 2: История (1 неделя)
- UserCheckStatus nodes
- Связи через `:NEXT`
- API для просмотра истории

### Фаза 3: Приоритизация (3-5 дней)
- Сортировка вопросов по важности
- Auto-confirm логика
- Batch questions

См. детальный план в [docs/attend/response_flow_clean/05_IMPLEMENTATION_PHASES.md](docs/attend/response_flow_clean/05_IMPLEMENTATION_PHASES.md)

---

## Тестирование

### Автоматический тест
```bash
python test_workflow_mvp.py
```

### Ручной тест (REST API)
```bash
# 1. Start
curl -X POST http://localhost:8000/api/v1/notes/workflow/start \
  -H "Content-Type: application/json" \
  -d '{"file_path": "test.md", "content": "Meeting with John Smith."}'

# 2. Resume
curl -X POST http://localhost:8000/api/v1/notes/workflow/resume \
  -H "Content-Type: application/json" \
  -d '{"thread_id": "note:test.md", "answer": {"action": "confirm"}}'
```

---

## Риски и ограничения

### Известные ограничения MVP

1. **Только один вопрос** - спрашивает про первую сущность
2. **Нет обработки modify/reject** - действия пользователя не применяются
3. **SQLite для persistence** - не подходит для high-load production
4. **Нет миграций** - старые данные не переносятся автоматически

### Риски

1. **Сложность LangGraph** - требуется время на изучение
2. **Сериализация состояния** - PipGraphManager нельзя сериализовать
3. **Performance** - AsyncSqliteSaver медленнее Redis

### Mitigation

1. ✅ Документация и примеры
2. ✅ Используем существующий PipGraphManager (не сериализуем)
3. ✅ Миграция на Redis запланирована

---

## Контакты и поддержка

**Документация:**
- [WORKFLOW_MVP.md](docs/WORKFLOW_MVP.md)
- [QUICKSTART_WORKFLOW.md](QUICKSTART_WORKFLOW.md)
- [response_flow_clean/](docs/attend/response_flow_clean/)

**Логи:**
```bash
export LOG_LEVEL=DEBUG
uvicorn app.api.main:app --reload
```

---

**Версия:** 0.1.0 (MVP)
**Дата:** 2025-11-17
**Автор:** Claude Code + Anton
