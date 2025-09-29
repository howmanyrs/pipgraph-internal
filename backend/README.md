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
│   │   └── graph_crud.py     # <-- Логика работы с графовой БД (пока заглушка)
│   ├── models/               # Pydantic модели (контракты данных)
│   │   ├── graph.py          # Модели для узлов и связей графа
│   │   └── note.py           # Модель для входящих данных заметки
│   └── services/             # Слой бизнес-логики
│       └── note_processor.py # <-- Основная логика обработки заметки
│
└── requirements.txt          # Зависимости проекта
```

### Шаг 2: Конфигурация и переменные окружения

Проект использует [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) для управления конфигурацией через переменные окружения и `.env` файлы. Настройки определены в модуле `config/settings.py`.

#### Обязательные переменные окружения

Для корректной работы бэкенда необходимо настроить следующие переменные:

```bash
# OpenAI API для LLM обработки
OPENAI_API_KEY=your_openai_api_key_here

# Neo4j соединение
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
```

#### Способы настройки переменных

**Вариант 1: Файл `.env` (рекомендуется для разработки)**

Создайте файл `.env` в корне папки `backend/`:

```bash
cd backend/
cat > .env << 'EOF'
OPENAI_API_KEY=your_openai_api_key_here
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
EOF
```

**Вариант 2: Переменные окружения системы**

```bash
export OPENAI_API_KEY="your_openai_api_key_here"
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your_neo4j_password"
```

**Вариант 3: Передача при запуске**

```bash
OPENAI_API_KEY=your_key NEO4J_URI=bolt://localhost:7687 \
NEO4J_USER=neo4j NEO4J_PASSWORD=your_password \
uvicorn app.api.main:app --reload
```

#### Использование настроек в коде

Импортируйте готовый экземпляр настроек:

```python
from config.settings import settings

# Использование в коде
openai_key = settings.OPENAI_API_KEY
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
from app.models.graph import GraphData, Node, Relationship
from app.crud import graph_crud

def process_and_store_note(note: NotePayload) -> GraphData:
    """
    Основная бизнес-логика: обрабатывает заметку, извлекает граф и сохраняет его.
    """
    # Шаг 1: Вызов LLM для извлечения сущностей (заглушка)
    # В реальной реализации здесь будет вызов к Разработчику 3
    print(f"Processing content from '{note.file_path}'...")
    graph_data = GraphData(
        nodes=[
            Node(id="person1", label="Person", properties={"name": "Иван"}),
            Node(id="company1", label="Company", properties={"name": "ООО 'Рога и копыта'"})
        ],
        relationships=[
            Relationship(source_id="person1", target_id="company1", type="WORKS_AT")
        ]
    )

    # Шаг 2: Сохранение извлеченных данных в БД через CRUD слой
    graph_crud.save_graph_data(graph_data)

    return graph_data
```

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