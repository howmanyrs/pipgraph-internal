### **Руководство по реализации Backend "PipGraph" (Версия 1.2)**

**Дата:** 26.09.2025
**Статус:** Для разработки

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
│   │   │   └── notes.py      # <-- WebSocket эндпоинт для заметок
│   │   └── main.py           # Главный файл FastAPI приложения
│   ├── crud/                 # Слой доступа к данным (Create, Read, Update, Delete)
│   │   └── graph_crud.py     # <-- Логика работы с Neo4j
│   ├── models/               # Pydantic модели (контракты данных)
│   │   ├── graph.py          # Модели для узлов и связей графа
│   │   └── note.py           # Модель для входящих данных заметки
│   └── services/             # Слой бизнес-логики
│       ├── pipgraph_manager.py     # <-- Обертка над Graphiti с 7 стадиями обработки
│       ├── cloudru_patched_client.py  # <-- Клиент для Cloud.ru/Qwen
│       └── note_processor.py       # <-- Основная логика обработки заметки
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

Этот слой инкапсулирует всю логику взаимодействия с базой данных. На данном этапе это будет простая функция-заглушка.

**`app/crud/graph_crud.py`:**
```python
from app.models.graph import GraphData

def save_graph_data(graph_data: GraphData) -> bool:
    """
    Функция-заглушка для сохранения данных в графовую БД.
    В реальной реализации здесь будет Cypher-запрос к Neo4j.
    """
    print("--- CRUD Layer ---")
    print(f"Saving {len(graph_data.nodes)} nodes and {len(graph_data.relationships)} relationships.")
    print("------------------")
    # Имитируем успешное сохранение
    return True
```

#### 3. Сервисный слой (`app/services/`)

Здесь находится основная бизнес-логика. Сервис использует CRUD-слой для работы с данными.

**`app/services/note_processor.py`:**
```python
from app.models.note import NotePayload
from app.models.graph import GraphData
from app.services.pipgraph_manager import PipGraphManager
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

async def process_and_store_note(note: NotePayload) -> GraphData:
    """
    Основная бизнес-логика: обрабатывает заметку через PipGraphManager.

    PipGraphManager предоставляет 7 стадий обработки с точками контроля:
    1. Валидация входных данных
    2. Извлечение фактов через LLM
    3. Разрешение сущностей
    4. Извлечение связей
    5. Обнаружение дубликатов
    6. Обновление графа в Neo4j
    7. Форматирование результата
    """
    # Получаем экземпляр Graphiti (из зависимостей)
    graphiti = await get_graphiti()

    # Создаем менеджер для пошагового контроля
    manager = PipGraphManager(graphiti)

    # Обрабатываем заметку с полным контролем над процессом
    result = await manager.process_note(
        name=note.file_path,
        content=note.content,
        reference_time=datetime.now(timezone.utc)
    )

    # Логируем результаты извлечения
    logger.info(f"Extracted {result['entity_count']} entities, "
                f"{result['edge_count']} edges from '{note.file_path}'")

    return result
```

**Новые возможности в реализации:**

- **PipGraphManager** (`app/services/pipgraph_manager.py`) - обертка над Graphiti с 7 стадиями обработки
- **CloudRuPatchedClient** (`app/services/cloudru_patched_client.py`) - клиент для Cloud.ru/Qwen моделей
- **Обнаружение дубликатов** - планируется SHA-256 хеширование контента (см. TODO.md)

#### 4. Слой API (`app/api/`)

Этот слой отвечает за прием внешних запросов и их передачу в сервисный слой.

**`app/api/endpoints/notes.py`:**
```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from app.models.note import NotePayload
from app.services import note_processor

router = APIRouter()

@router.websocket("/ws/notes/process")
async def process_note_websocket(websocket: WebSocket):
    """
    Принимает WebSocket соединение для полного цикла обработки заметки.
    """
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        
        try:
            payload = NotePayload(**data)
        except ValidationError as e:
            await websocket.send_json({"status": "error", "message": str(e)})
            await websocket.close()
            return

        # 1. Отправляем клиенту подтверждение о начале работы
        await websocket.send_json({
            "status": "processing",
            "message": f"Note '{payload.file_path}' received, starting processing..."
        })

        # 2. Вызываем бизнес-логику (для прототипа - синхронно)
        # В будущем здесь может быть фоновая задача (Celery, BackgroundTasks)
        graph_data = note_processor.process_and_store_note(payload)

        # 3. Отправляем финальный результат
        await websocket.send_json({
            "status": "done",
            "data": graph_data.dict() # Сериализуем Pydantic модель в dict
        })

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        await websocket.send_json({"status": "error", "message": f"An unexpected error occurred: {str(e)}"})
    finally:
        await websocket.close()
```

**`app/api/main.py`:**
```python
from fastapi import FastAPI
from app.api.endpoints import notes

app = FastAPI(title="PipGraph Backend")

# Подключаем роутер с WebSocket эндпоинтом
# Добавляем префикс для версионирования API
app.include_router(notes.router, prefix="/api/v1")

@app.get("/")
def read_root():
    return {"status": "PipGraph Backend is running"}
```

### Шаг 4: Запуск сервера

Убедитесь, что вы находитесь в корневой папке `backend/` и виртуальное окружение активно.

```bash
uvicorn app.api.main:app --reload
```

Сервер будет запущен и готов принимать WebSocket-соединения по адресу:
`ws://127.0.0.1:8000/api/v1/ws/notes/process`

### Шаг 5: Тестирование с помощью `websocat`

Для тестирования WebSocket-соединения используйте `websocat` или любой другой WebSocket-клиент.

1.  **Установите `websocat`**, если это необходимо (например, `brew install websocat`).
2.  **Выполните тестовый запрос** в новом терминале:

    ```bash
    echo '{"file_path": "test/my_ws_note.md", "content": "Иван по вебсокету работает в ООО Рога и копыта."}' \
    | websocat ws://127.0.0.1:8000/api/v1/ws/notes/process
    ```

**Ожидаемый результат в вашем терминале:**

Вы получите два последовательных ответа от сервера, что демонстрирует асинхронный характер взаимодействия:

1.  **Мгновенный ответ-подтверждение:**
    ```json
    {"status":"processing","message":"Note 'test/my_ws_note.md' received, starting processing..."}
    ```
2.  **Финальный ответ с результатом после "обработки":**
    ```json
    {"status":"done","data":{"nodes":[{"id":"person1","label":"Person","properties":{"name":"Иван"}},{"id":"company1","label":"Company","properties":{"name":"ООО 'Рога и копыта'"}}],"relationships":[{"source_id":"person1","target_id":"company1","type":"WORKS_AT","properties":{}}]}}
    ```

Этот результат подтверждает, что бэкенд готов к интеграции с фронтендом согласно утвержденной архитектуре.

---

## Дополнительная документация

### Архитектурные решения

Подробное описание архитектурных решений и дизайна системы доступно в:

- **[docs/attend/pipgraph_manager_discussion.md](docs/attend/pipgraph_manager_discussion.md)** - Обсуждение дизайна PipGraphManager
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - Архитектурные паттерны и решения
- **[TODO.md](TODO.md)** - Запланированные задачи и технический долг
- **[CHANGELOG.md](CHANGELOG.md)** - История изменений

### Ключевые компоненты

**PipGraphManager** - Обертка над Graphiti для пошагового контроля обработки заметок:
- Скопирован код `add_episode` из graphiti_core для контролируемых модификаций
- 7 стадий обработки с точками вмешательства
- Документированные места для кастомизации
- Позволяет постепенную кастомизацию без изменения библиотеки

**CloudRuPatchedClient** - Кастомный LLM клиент для Cloud.ru/Qwen:
- Исправляет дублирование JSON схемы в ответах Qwen
- Модифицированная инструкция промпта: "return data only, not the schema"
- Однострочное изменение с полной совместимостью с OpenAIGenericClient

**Обнаружение дубликатов заметок** (Высокий приоритет в TODO):
- Планируется верификация через SHA-256 хеш контента
- Сценарий 1: Пропуск обработки если контент не изменился (оптимизация затрат)
- Сценарий 2: Обработка модифицированных заметок (требуется дизайн)
- Включает реализацию `find_episode_by_name()`

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