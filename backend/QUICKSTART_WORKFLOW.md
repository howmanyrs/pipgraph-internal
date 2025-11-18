# Быстрый старт LangGraph Workflow MVP

## 1. Установка зависимостей

```bash
cd backend/
pip install -r requirements.txt
# или
uv pip install -r requirements.txt
```

**Новые зависимости:**
- `langgraph>=0.2.0` - orchestration framework
- `langchain-core>=0.3.0` - базовые компоненты
- `aiosqlite>=0.20.0` - async SQLite для checkpoints

---

## 2. Запуск сервера

```bash
uvicorn app.api.main:app --reload
```

Сервер запустится на `http://localhost:8000`

---

## 3. Проверка работоспособности

### Вариант A: Автоматический тест

```bash
python test_workflow_mvp.py
```

### Вариант B: Ручной тест через curl

```bash
# 1. Запустить workflow
curl -X POST http://localhost:8000/api/v1/notes/workflow/start \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "test.md",
    "content": "Meeting with John Smith about the Q4 project."
  }'

# Получите ответ с thread_id и pending_question

# 2. Ответить на вопрос
curl -X POST http://localhost:8000/api/v1/notes/workflow/resume \
  -H "Content-Type: application/json" \
  -d '{
    "thread_id": "note:test.md",
    "answer": {
      "question_id": "<question_id из ответа выше>",
      "action": "confirm"
    }
  }'
```

---

## 4. Что ожидать

**Успешный запуск:**
1. ✅ Сервер запущен без ошибок
2. ✅ POST `/notes/workflow/start` возвращает `thread_id` и `pending_question`
3. ✅ POST `/notes/workflow/resume` завершает workflow со статусом `completed`
4. ✅ Создается файл `workflow_checkpoints.db` (состояние workflow)

**Возможные ошибки:**

**Error: "Module 'langgraph' not found"**
```bash
pip install langgraph>=0.2.0
```

**Error: "Cannot connect to Neo4j"**
- Убедитесь, что Neo4j запущен
- Проверьте `.env` файл с настройками подключения

**Error: "OpenRouter API key not set"**
- Добавьте `OPENROUTER_API_KEY` в `.env`

---

## 5. Архитектура файлов

```
backend/
├── app/
│   ├── models/
│   │   └── workflow_state.py          ✨ НОВЫЙ
│   ├── services/
│   │   └── note_workflow.py           ✨ НОВЫЙ
│   ├── api/
│   │   ├── endpoints/
│   │   │   └── notes.py               📝 ОБНОВЛЕН (добавлены workflow endpoints)
│   │   └── websockets/
│   │       └── workflow.py            ✨ НОВЫЙ
│   └── ...
├── requirements.txt                    📝 ОБНОВЛЕН (добавлены langgraph, aiosqlite)
├── test_workflow_mvp.py                ✨ НОВЫЙ
├── workflow_checkpoints.db             ✨ СОЗДАЕТСЯ автоматически
└── docs/
    ├── WORKFLOW_MVP.md                 ✨ НОВЫЙ (полная документация)
    └── ...
```

---

## 6. Endpoints

### REST API

- **POST** `/api/v1/notes/workflow/start` - Запустить workflow
- **POST** `/api/v1/notes/workflow/resume` - Возобновить с ответом
- **GET** `/api/v1/notes/workflow/status/{thread_id}` - Статус workflow

### WebSocket

- **WS** `/ws/workflow` - Real-time взаимодействие

---

## 7. Следующие шаги

После успешного запуска MVP:

1. **Добавить L1/L2 подтверждения** (PARA classification + containers)
2. **UserCheckStatus nodes** в Neo4j для истории
3. **Приоритизация** вопросов
4. **Auto-confirm** для высокоуверенных сущностей

См. полную документацию в [docs/WORKFLOW_MVP.md](docs/WORKFLOW_MVP.md)

---

## Поддержка

**Документация:**
- [WORKFLOW_MVP.md](docs/WORKFLOW_MVP.md) - полное руководство
- [response_flow_clean/](docs/attend/response_flow_clean/) - архитектура L1/L2/L3

**Логи:**
```bash
# Включить DEBUG
export LOG_LEVEL=DEBUG
uvicorn app.api.main:app --reload
```
