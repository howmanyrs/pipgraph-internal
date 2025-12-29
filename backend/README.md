### **Руководство по реализации Backend "PipGraph" (Версия 1.2)**

**Дата:** 29.12.2025
**Статус:** В активной разработке

#### 1. Введение

Этот документ предоставляет пошаговое техническое руководство для Разработчика 2 (Backend Integration) и Разработчика 3 (Core LLM & Cypher) по созданию бэкенд-сервиса для проекта "PipGraph". Он является практической реализацией архитектуры, описанной в `global-overview.md (Версия 1.2)`.

Основное внимание уделяется созданию асинхронного API на базе WebSocket для обработки заметок, что позволяет клиенту получать мгновенную обратную связь.

### Шаг 1: Структура проекта

Для соответствия общей архитектуре (`global-overview.md`) мы будем использовать следующую структуру папок. Это обеспечит четкое разделение ответственности между слоями приложения.

```
backend/
├── app/
│   ├── api/                  # Слой API (маршрутизация)
│   │   ├── endpoints/        # Файлы с эндпоинтами
│   │   │   ├── workflow.py   # <-- REST API для управления workflow
│   │   │   └── suggestions.py # <-- REST API для suggestions и inbox
│   │   └── main.py           # Главный файл FastAPI приложения
│   ├── crud/                 # Слой доступа к данным (Neo4j)
│   │   ├── relationship_crud.py  # Связи и suggestions
│   │   ├── entity_crud.py        # Сущности
│   │   ├── episodic_crud.py      # Эпизоды
│   │   └── para_crud.py          # PARA контейнеры
│   ├── models/               # Pydantic модели (контракты данных)
│   │   ├── para_entities.py  # Project, Area, Resource, Archive
│   │   ├── proposal.py       # PARACandidate, PARAProposal
│   │   └── entity.py         # Entity models
│   ├── services/             # Слой бизнес-логики
│   │   ├── pipgraph_manager.py      # Обработка заметок с LLM
│   │   ├── proposal_manager.py      # Применение proposals к Neo4j
│   │   ├── cascade_service.py       # Авто-разрешение похожих suggestions
│   │   ├── cloudru_patched_client.py  # Клиент для Cloud.ru/Qwen
│   │   └── mocks/                   # Mock-сервисы для тестирования
│   └── workflows/            # LangGraph workflow
│       ├── para_workflow.py      # State machine (6 nodes)
│       ├── langgraph_service.py  # Сборка и выполнение графа
│       ├── state.py              # PARAWorkflowState
│       └── conditions.py         # Условия переходов
│
├── config/
│   └── settings.py           # Конфигурация через pydantic-settings
├── tests/                    # Тестовая инфраструктура
│   ├── unit/                 # Unit-тесты
│   ├── integration/          # Integration-тесты (Neo4j, LLM)
│   └── e2e/                  # End-to-end тесты
├── scripts/                  # CLI утилиты для ручного тестирования
└── requirements.txt          # Зависимости проекта
```

### Шаг 2: Конфигурация и переменные окружения

Проект использует [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) для управления конфигурацией через переменные окружения и `.env` файлы. Настройки определены в модуле `config/settings.py`.

#### Обязательные переменные окружения

Для корректной работы бэкенда необходимо настроить следующие переменные:

```bash
# OpenRouter API для LLM обработки
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Neo4j соединение
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password

# (Опционально) Cloud.ru/Qwen для альтернативного LLM
CLOUDRU_API_KEY=your_cloudru_key
```

#### Способы настройки переменных

**Вариант 1: Файл `.env` (рекомендуется для разработки)**

Создайте файл `.env` в корне папки `backend/`:

```bash
cd backend/
cat > .env << 'EOF'
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
EOF
```

**Вариант 2: Переменные окружения системы**

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
export OPENROUTER_BASE_URL="https://openrouter.ai/api/v1"
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your_neo4j_password"
```

**Вариант 3: Передача при запуске**

```bash
OPENROUTER_API_KEY=sk-or-v1-... NEO4J_URI=bolt://localhost:7687 \
NEO4J_USER=neo4j NEO4J_PASSWORD=your_password \
uvicorn app.api.main:app --reload
```

#### Использование настроек в коде

Импортируйте готовый экземпляр настроек:

```python
from config.settings import settings

# Использование в коде
openrouter_key = settings.OPENROUTER_API_KEY
neo4j_uri = settings.NEO4J_URI
```

#### Безопасность

- **Никогда не коммитьте** файл `.env` в репозиторий
- Используйте разные настройки для разработки и продакшена
- Для продакшена используйте переменные окружения вместо `.env` файлов

### Шаг 3: Настройка окружения и зависимостей с помощью `uv`

1.  **Устанавливаем `uv`** (если еще не установлен):
    ```bash
    pip install uv
    ```

2.  **Создаем и активируем виртуальное окружение** в папке `backend/`:
    ```bash
    # Перейдите в папку backend
    cd backend

    # Создаем окружение
    uv venv

    # Активируем (команда зависит от вашей ОС)
    # Windows: .\.venv\Scripts\activate
    # macOS/Linux: source .venv/bin/activate
    ```

3.  **Создаем файл `requirements.txt`** с необходимыми пакетами:
    ```
    fastapi
    uvicorn[standard]  # Включает поддержку aiohttp и websockets
    pydantic
    ```

4.  **Устанавливаем зависимости с помощью `uv`**:
    ```bash
    uv pip install -r requirements.txt
    ```

### Шаг 3: Написание кода

Ниже представлен код для каждого файла в структуре `app/`.

#### 1. Слой Моделей (`app/models/`)

Эти файлы определяют структуру данных, с которой работает наше приложение.

**`app/models/note.py`:**```python
from pydantic import BaseModel

class NotePayload(BaseModel):
    """Модель данных для входящей заметки."""
    file_path: str
    content: str
```

**`app/models/graph.py`:**
```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any

class Node(BaseModel):
    """Модель узла в графе."""
    id: str
    label: str
    properties: Dict[str, Any]

class Relationship(BaseModel):
    """Модель связи в графе."""
    source_id: str
    target_id: str
    type: str
    properties: Dict[str, Any] = Field(default_factory=dict)

class GraphData(BaseModel):
    """Модель для представления извлеченных из заметки графовых данных."""
    nodes: List[Node]
    relationships: List[Relationship]
```

#### 2. Слой CRUD (`app/crud/`)

Этот слой инкапсулирует всю логику взаимодействия с Neo4j.

**Основные модули:**
- `relationship_crud.py` - Создание suggestions и связей `:SUGGESTS`, `:IS_PART_OF`
- `entity_crud.py` - Batch-сохранение сущностей
- `episodic_crud.py` - Управление эпизодами (Episodic nodes)
- `para_crud.py` - CRUD для Project/Area/Resource/Archive контейнеров

```python
# Пример: создание suggestion
from app.crud.relationship_crud import create_suggestion

await create_suggestion(
    session=session,
    episode_uuid=episode_uuid,
    container_uuid=container_uuid,
    suggestion_type="link",
    confidence=0.85
)
```

#### 3. Сервисный слой (`app/services/`)

Здесь находится основная бизнес-логика. Сервис использует CRUD-слой для работы с данными.

**Основные сервисы:**

- **PipGraphManager** (`pipgraph_manager.py`) - Пошаговая обработка заметок с LLM
- **ProposalManager** (`proposal_manager.py`) - Применение PARA proposals к Neo4j
- **CascadeService** (`cascade_service.py`) - Авто-разрешение похожих suggestions
- **Mock-сервисы** (`mocks/`) - Детерминированные моки для тестирования без LLM

```python
# Пример использования ProposalManager
from app.services.proposal_manager import ProposalManager

manager = ProposalManager(session)
await manager.apply_proposal_to_graph(proposal, episode_uuid)
```

**LangGraph Workflow** (`app/workflows/`):

```python
from app.workflows.langgraph_service import start_workflow, resume_workflow

# Запуск нового workflow
result = await start_workflow(file_path="note.md", content="...")

# Возобновление с ответом пользователя
result = await resume_workflow(workflow_id, answer={"action": "confirm"})
```

#### 4. Слой API (`app/api/`)

Этот слой отвечает за прием внешних запросов и их передачу в сервисный слой.

**REST API Endpoints:**

```python
# app/api/endpoints/workflow.py
from fastapi import APIRouter
from app.workflows.langgraph_service import start_workflow, resume_workflow

router = APIRouter()

@router.post("/workflow/start")
async def start_workflow_endpoint(request: WorkflowCreateRequest):
    """Запуск нового PARA workflow."""
    result = await start_workflow(request.file_path, request.content)
    return WorkflowStatusResponse(**result)

@router.get("/workflow/{workflow_id}/status")
async def get_status(workflow_id: str):
    """Получить статус workflow."""
    ...

@router.post("/workflow/{workflow_id}/resume")
async def resume(workflow_id: str, request: WorkflowResumeRequest):
    """Возобновить workflow с ответом пользователя."""
    ...
```

```python
# app/api/endpoints/suggestions.py
@router.get("/workflow/{workflow_id}/suggestions")
async def get_suggestions(workflow_id: str):
    """Получить pending suggestions для workflow."""
    ...

@router.post("/suggestion/{suggestion_id}/decision")
async def submit_decision(suggestion_id: str, request: DecisionRequest):
    """Подтвердить/отклонить suggestion."""
    ...

@router.get("/inbox/suggestions")
async def get_inbox():
    """Все pending suggestions."""
    ...
```

**`app/api/main.py`:**
```python
from fastapi import FastAPI
from app.api.endpoints import workflow, suggestions

app = FastAPI(title="PipGraph Backend")

app.include_router(workflow.router, prefix="/api/v1")
app.include_router(suggestions.router, prefix="/api/v1")

@app.get("/")
def read_root():
    return {"status": "PipGraph Backend is running"}
```

### Шаг 4: Запуск сервера

Убедитесь, что вы находитесь в корневой папке `backend/` и виртуальное окружение активно.

```bash
uvicorn app.api.main:app --reload
```

Сервер будет запущен и доступен по адресу: `http://127.0.0.1:8000`

### Шаг 5: Тестирование с помощью `curl`

Для тестирования REST API используйте `curl`:

```bash
# Запуск нового workflow
curl -X POST http://127.0.0.1:8000/api/v1/workflow/start \
  -H "Content-Type: application/json" \
  -d '{"file_path": "test/note.md", "content": "Иван работает в ООО Рога и копыта."}'

# Получить статус workflow
curl http://127.0.0.1:8000/api/v1/workflow/{workflow_id}/status

# Получить pending suggestions
curl http://127.0.0.1:8000/api/v1/workflow/{workflow_id}/suggestions

# Подтвердить suggestion
curl -X POST http://127.0.0.1:8000/api/v1/suggestion/{suggestion_id}/decision \
  -H "Content-Type: application/json" \
  -d '{"action": "confirm"}'

# Получить все pending suggestions (inbox)
curl http://127.0.0.1:8000/api/v1/inbox/suggestions
```

**Ожидаемый результат:**

```json
{
  "workflow_id": "abc123",
  "status": "waiting_for_decision",
  "pending_question": {
    "type": "para_suggestion",
    "suggestions": [...]
  }
}
```

---

## Дополнительная документация

### Архитектурные решения

Подробное описание архитектурных решений и дизайна системы доступно в:

- **[docs/attend/pipgraph_manager_discussion.md](docs/attend/pipgraph_manager_discussion.md)** - Обсуждение дизайна PipGraphManager
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - Архитектурные паттерны и решения
- **[TODO.md](TODO.md)** - Запланированные задачи и технический долг
- **[CHANGELOG.md](CHANGELOG.md)** - История изменений

### Ключевые компоненты

**LangGraph PARA Workflow** - Основной pipeline обработки заметок:
- State machine с 6 nodes: identify_context → apply_proposal → wait_for_decision → process_decision → extract_content → save_entities
- Interrupt/resume поддержка для пользовательских решений
- Cascade авто-разрешение похожих suggestions

**PipGraphManager** - Обертка над Graphiti для извлечения сущностей:
- 7 стадий обработки с точками вмешательства
- Интеграция с LangGraph workflow
- Пошаговый контроль обработки

**CascadeService** - Авто-разрешение похожих suggestions:
- Threshold-based: confidence > 0.85 авто-подтверждает
- Neo4j как источник истины
- Возвращает список авто-разрешённых items

---

## Тестирование

Проект использует **pytest** для тестирования с разделением на unit, integration и e2e тесты.

### Установка тестовых зависимостей

```bash
# Активируйте виртуальное окружение
source .venv/bin/activate  # Linux/macOS
# .\.venv\Scripts\activate  # Windows

# Установите dev-зависимости
uv pip install -r requirements-dev.txt
```

### Структура тестов

```
backend/tests/
├── conftest.py              # Общие фикстуры (Neo4j, LLM клиенты)
├── unit/                    # Быстрые тесты без внешних зависимостей
│   └── test_models.py       # Тесты Pydantic моделей
├── integration/             # Тесты с реальными сервисами
│   ├── test_neo4j.py        # Тест подключения Neo4j
│   ├── test_openrouter.py   # Тест подключения к LLM через OpenRouter
│   └── test_note_processor.py  # Тест полного цикла обработки заметок
└── e2e/                     # End-to-end тесты (полный flow)
```

### Запуск тестов

**Все тесты:**
```bash
pytest
```

**Только unit-тесты (быстрые, без внешних сервисов):**
```bash
pytest -m unit
```

**Только integration-тесты (требуют Neo4j, LLM):**
```bash
pytest -m integration
```

**Исключить медленные тесты:**
```bash
pytest -m "not slow"
```

**Запуск с покрытием кода:**
```bash
pytest --cov=app --cov-report=html
# Отчет будет в htmlcov/index.html
```

**Запуск конкретного теста:**
```bash
pytest tests/integration/test_neo4j.py::test_neo4j_connection_with_driver
```

### Доступные маркеры

- `@pytest.mark.unit` - Unit-тесты (быстрые, без внешних зависимостей)
- `@pytest.mark.integration` - Integration-тесты (требуют Neo4j, LLM)
- `@pytest.mark.e2e` - End-to-end тесты (полный flow приложения)
- `@pytest.mark.slow` - Медленные тесты (LLM вызовы, большие данные)

### Конфигурация для тестов

Тесты используют те же переменные окружения из `.env`:
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` - для Neo4j
- `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL` - для LLM

**⚠️ Рекомендация:** Для integration-тестов используйте отдельную тестовую БД Neo4j.

### Утилиты для ручного тестирования

В директории `scripts/` доступны CLI-утилиты для ручного тестирования:

**Тест подключения Neo4j:**
```bash
python scripts/simple_neo4j_test.py
```

**Интерактивный тест обработки заметок:**
```bash
# Запуск демо-примеров
python scripts/test_note_processor_cli.py --demo

# Интерактивный режим
python scripts/test_note_processor_cli.py --interactive

# Обработка заметки из файла
python scripts/test_note_processor_cli.py --file path/to/note.md
```