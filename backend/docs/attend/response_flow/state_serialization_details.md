# State Serialization Details: PipGraphManager in LangGraph

**Дата создания:** 2025-11-09
**Связанный документ:** [user_check_mvp_plan.md](./user_check_mvp_plan.md)
**Цель:** Технические детали сериализации state в LangGraph с ephemeral объектами

---

## Проблема

`NoteProcessingState` содержит `pipgraph_manager: PipGraphManager`, который **не может быть сериализован** в SQLite, так как содержит:

```python
class PipGraphManager:
    def __init__(self, graphiti: Graphiti):
        self.graphiti = graphiti
        self.clients = graphiti.clients       # httpx.AsyncClient - HTTP connections
        self.driver = graphiti.driver         # neo4j.AsyncDriver - DB connection
        self.embedder = graphiti.embedder     # OpenAI client
        # ↑ Активные соединения, сокеты, threads - НЕ сериализуемы
```

**Попытка сериализации:**
```python
# LangGraph пытается сохранить state:
state = {
    'file_path': 'note.md',
    'entities': [...],
    'pipgraph_manager': pipgraph_manager  # ← ОШИБКА!
}

# AsyncSqliteSaver использует JsonPlusSerializer (msgpack):
serialized = serde.dumps(state)
# SerializationError: Cannot serialize <neo4j.AsyncDriver> object
```

---

## Механизм сериализации LangGraph

### 1. Что используется

**По умолчанию:** [`JsonPlusSerializer`](https://reference.langchain.com/python/langgraph/checkpoints/#langgraph.checkpoint.serde.jsonplus.JsonPlusSerializer)

- Основан на **ormsgpack** (MessagePack), не pickle
- Поддерживает: примитивы, коллекции, datetime, enums, LangChain/LangGraph объекты
- **НЕ поддерживает:** активные соединения, сокеты, file descriptors

### 2. Что сериализуется автоматически

```python
class NoteProcessingState(TypedDict):
    # ✅ Автоматически сериализуется
    file_path: str                          # → msgpack
    content: str                            # → msgpack
    episode_uuid: Optional[str]             # → msgpack
    processing_stage: str                   # → msgpack
    pending_clarifications: list[dict]      # → msgpack
    current_clarification: Optional[dict]   # → msgpack
    user_response: Optional[dict]           # → msgpack

    # ✅ Сериализуется если EntityNode/EntityEdge поддерживают msgpack
    entities: list[EntityNode]              # → msgpack
    relationships: list[EntityEdge]         # → msgpack

    # ❌ НЕ может быть сериализован
    pipgraph_manager: PipGraphManager       # → ОШИБКА!
```

### 3. Процесс сохранения в SQLite

```python
# При вызове interrupt():
# 1. LangGraph вызывает checkpointer.put()
await checkpointer.put(config, checkpoint, metadata)

# 2. AsyncSqliteSaver сериализует state
serialized_state = self.serde.dumps_typed(checkpoint['channel_values'])

# 3. Сохраняет в SQLite
await cursor.execute(
    "INSERT INTO checkpoints (thread_id, checkpoint_id, checkpoint) VALUES (?, ?, ?)",
    (thread_id, checkpoint_id, serialized_state)
)
```

---

## Рекомендованное решение (комбинированное)

### Стратегия

1. **Custom serializer** исключает `pipgraph_manager` из сериализации
2. **TypedDict с `total=False`** делает поле опциональным
3. **Manual injection** при resume добавляет новый manager instance

### Шаг 1: Custom Serializer

```python
# backend/app/services/feedback_state_serializer.py

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
import logging

logger = logging.getLogger(__name__)


class FeedbackStateSerializer(JsonPlusSerializer):
    """
    Custom serializer для NoteProcessingState.

    Исключает ephemeral поля (pipgraph_manager) при сериализации,
    так как они содержат несериализуемые объекты (DB connections, HTTP clients).

    При десериализации эти поля будут отсутствовать и должны быть
    добавлены вручную через injection.
    """

    # Поля, которые НЕ сохраняются в SQLite
    EXCLUDED_KEYS = {'pipgraph_manager'}

    def dumps_typed(self, obj):
        """
        Сериализует объект, исключая ephemeral поля.

        Args:
            obj: Объект для сериализации (обычно dict state)

        Returns:
            Tuple[str, bytes]: (type_name, serialized_data)
        """
        if isinstance(obj, dict):
            # Создаем копию без excluded ключей
            filtered_obj = {
                k: v for k, v in obj.items()
                if k not in self.EXCLUDED_KEYS
            }
            logger.debug(
                f"Serializing state. Excluded keys: {self.EXCLUDED_KEYS & obj.keys()}"
            )
            return super().dumps_typed(filtered_obj)

        return super().dumps_typed(obj)

    def loads_typed(self, data):
        """
        Десериализует объект из SQLite.

        Note: ephemeral поля (pipgraph_manager) будут отсутствовать
        и должны быть добавлены вручную после загрузки.

        Args:
            data: Tuple[str, bytes] из dumps_typed

        Returns:
            Десериализованный объект (dict без pipgraph_manager)
        """
        result = super().loads_typed(data)
        logger.debug(f"Deserialized state. Keys: {result.keys() if isinstance(result, dict) else 'N/A'}")
        return result
```

### Шаг 2: State Definition

```python
# backend/app/models/feedback_state.py

from typing import TypedDict, Optional, TYPE_CHECKING
from graphiti_core.nodes import EntityNode
from graphiti_core.edges import EntityEdge

if TYPE_CHECKING:
    from app.services.pipgraph_manager import PipGraphManager


class NoteProcessingState(TypedDict, total=False):
    """
    LangGraph state для обработки заметки.

    Persistent fields сохраняются в AsyncSqliteSaver между interrupt/resume.
    Ephemeral fields НЕ сохраняются и должны быть recreated при resume.

    Note: total=False делает все поля опциональными, что позволяет
    десериализовать state без pipgraph_manager.
    """

    # === PERSISTENT FIELDS (сохраняются в SQLite) ===

    # Input
    file_path: str
    content: str

    # Processing results
    episode_uuid: Optional[str]
    entities: list[EntityNode]
    relationships: list[EntityEdge]

    # Clarification tracking
    pending_clarifications: list[dict]
    current_clarification: Optional[dict]
    user_response: Optional[dict]

    # Workflow metadata
    processing_stage: str  # "started" | "entities_extracted" | "completed"

    # === EPHEMERAL FIELDS (НЕ сохраняются) ===

    pipgraph_manager: 'PipGraphManager'
    """
    PipGraphManager instance - НЕ сериализуется в SQLite.

    Почему не сериализуется:
    - Содержит neo4j.AsyncDriver (активное DB соединение)
    - Содержит httpx.AsyncClient (HTTP connections к LLM API)
    - Содержит OpenAI embedder client

    Lifecycle:
    - NEW session: инжектируется в initial_state
    - RESUME session: инжектируется вручную после aget_state()

    См. FeedbackStateSerializer.EXCLUDED_KEYS
    """
```

### Шаг 3: Graph Creation

```python
# backend/app/services/feedback_graph.py

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.models.feedback_state import NoteProcessingState
from app.services.feedback_state_serializer import FeedbackStateSerializer


def create_feedback_graph(db_path: str = "sessions.db"):
    """
    Создает и компилирует LangGraph для feedback cycle.

    Args:
        db_path: Путь к SQLite базе для checkpoints

    Returns:
        Compiled graph с custom serializer
    """
    # 1. Define graph structure
    graph_builder = StateGraph(NoteProcessingState)

    # 2. Add nodes
    graph_builder.add_node("extract_entities", extract_entities_node)
    graph_builder.add_node("check_clarification", check_clarification_node)
    graph_builder.add_node("request_clarification", request_clarification_node)
    graph_builder.add_node("process_response", process_response_node)
    graph_builder.add_node("finalize", finalize_node)

    # 3. Add edges
    graph_builder.add_edge(START, "extract_entities")
    graph_builder.add_edge("extract_entities", "check_clarification")
    graph_builder.add_conditional_edges(
        "check_clarification",
        should_request_clarification,
        {
            "clarify": "request_clarification",
            "finalize": "finalize"
        }
    )
    graph_builder.add_edge("request_clarification", "process_response")
    graph_builder.add_edge("process_response", "check_clarification")  # Loop
    graph_builder.add_edge("finalize", END)

    # 4. Create checkpointer with custom serializer
    checkpointer = AsyncSqliteSaver.from_conn_string(
        db_path,
        serde=FeedbackStateSerializer()  # ← Custom serializer
    )

    # 5. Compile
    return graph_builder.compile(checkpointer=checkpointer)


# Singleton instance
feedback_graph = create_feedback_graph()
```

### Шаг 4: WebSocket Handler (Manual Injection)

```python
# backend/app/api/endpoints/feedback_websocket.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from langgraph.types import Command
import logging

from app.services.feedback_graph import feedback_graph
from app.services.pipgraph_manager import PipGraphManager
from app.dependencies import get_pipgraph_manager
from app.models.feedback_state import NoteProcessingState

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/notes/feedback")
async def websocket_feedback_endpoint(
    websocket: WebSocket,
    pipgraph_manager: PipGraphManager = Depends(get_pipgraph_manager)
):
    """
    WebSocket endpoint для multi-round feedback cycle.

    Handles:
    - NEW sessions: создает initial_state с manager
    - RESUME sessions: инжектирует manager в loaded state
    """
    await websocket.accept()
    thread_id = None

    try:
        # 1. Receive note data
        data = await websocket.receive_json()
        file_path = data["file_path"]
        content = data.get("content", "")

        # 2. Setup thread config
        thread_id = f"note:{file_path}"
        config = {"configurable": {"thread_id": thread_id}}

        # 3. Check if resuming existing thread
        state_snapshot = await feedback_graph.aget_state(config)

        if state_snapshot and state_snapshot.next:
            # === RESUME EXISTING THREAD ===
            logger.info(f"Resuming thread: {thread_id}")

            # CRITICAL: Inject new PipGraphManager instance
            # (deserialized state doesn't have it)
            current_state = state_snapshot.values
            current_state['pipgraph_manager'] = pipgraph_manager  # ← INJECTION

            logger.debug(f"Injected PipGraphManager into resumed state")

            # Send pending clarification if any
            if current_state.get('current_clarification'):
                clarification_msg = create_clarification_message(
                    current_state['current_clarification']
                )
                await websocket.send_json(clarification_msg.dict())

                # Wait for response
                user_response = await websocket.receive_json()

                # Resume graph
                await feedback_graph.ainvoke(
                    Command(resume=user_response),
                    config
                )

        else:
            # === NEW THREAD ===
            logger.info(f"Starting new thread: {thread_id}")

            # Send processing started status
            await websocket.send_json(
                create_processing_status_message(
                    "started",
                    f"Processing note: {file_path}"
                ).dict()
            )

            # Create initial state with PipGraphManager
            initial_state = NoteProcessingState(
                file_path=file_path,
                content=content,
                episode_uuid=None,
                entities=[],
                relationships=[],
                pending_clarifications=[],
                current_clarification=None,
                user_response=None,
                pipgraph_manager=pipgraph_manager,  # ← INJECTION
                processing_stage="started"
            )

            # Execute graph
            await execute_graph_with_feedback(
                websocket,
                config,
                initial_state=initial_state
            )

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {thread_id}")
        # State already saved by checkpointer

    except Exception as e:
        logger.error(f"Error in WebSocket handler: {e}", exc_info=True)
        await websocket.send_json({
            "message_type": "error",
            "data": {"error": str(e)}
        })
        await websocket.close()
```

---

## Lifecycle Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    SESSION 1: NEW                            │
└─────────────────────────────────────────────────────────────┘

1. WebSocket connect
   ↓
2. pipgraph_manager_1 = get_pipgraph_manager()  # NEW instance
   - Creates neo4j.AsyncDriver connection
   - Creates httpx.AsyncClient
   ↓
3. initial_state = {
       'file_path': 'note.md',
       'content': '...',
       'pipgraph_manager': pipgraph_manager_1,  # ← IN MEMORY
       ...
   }
   ↓
4. graph.ainvoke(initial_state, config)
   ↓
5. extract_entities_node(state)
   - Uses state['pipgraph_manager'].process_note()
   - Saves entities to Neo4j
   ↓
6. interrupt() called in request_clarification_node
   ↓
7. AsyncSqliteSaver.put(checkpoint)
   - FeedbackStateSerializer.dumps_typed() called
   - EXCLUDES 'pipgraph_manager' key
   - Serializes remaining fields to msgpack
   - Saves to SQLite:
     {
       'file_path': 'note.md',
       'entities': [...],
       'pending_clarifications': [...]
       # NO pipgraph_manager!
     }
   ↓
8. WebSocket disconnect
   ↓
9. pipgraph_manager_1 destroyed
   - Neo4j connection closed
   - HTTP clients closed


┌─────────────────────────────────────────────────────────────┐
│            SESSION 2: RESUME (1 day later)                   │
└─────────────────────────────────────────────────────────────┘

1. WebSocket reconnect (same file_path)
   ↓
2. pipgraph_manager_2 = get_pipgraph_manager()  # NEW instance #2
   - Creates NEW neo4j.AsyncDriver
   - Creates NEW httpx.AsyncClient
   ↓
3. state_snapshot = graph.aget_state(config)
   - AsyncSqliteSaver loads from SQLite
   - FeedbackStateSerializer.loads_typed() called
   - Returns:
     {
       'file_path': 'note.md',
       'entities': [...],
       'pending_clarifications': [...]
       # pipgraph_manager MISSING!
     }
   ↓
4. MANUAL INJECTION:
   state_snapshot.values['pipgraph_manager'] = pipgraph_manager_2
   - Adds NEW manager to loaded state
   ↓
5. graph.ainvoke(Command(resume=user_response), config)
   ↓
6. process_response_node(state)
   - state['pipgraph_manager'] now exists! (injected)
   - Can use manager.process_note() if needed
   ↓
7. ... continues execution ...
   ↓
8. finalize_node() saves final results to Neo4j
```

---

## Common Pitfalls & Troubleshooting

### 1. Забыли инжектировать manager при resume

**Симптом:**
```python
KeyError: 'pipgraph_manager'
# или
AttributeError: 'NoneType' object has no attribute 'process_note'
```

**Решение:**
```python
# ALWAYS inject after aget_state():
state_snapshot = await graph.aget_state(config)
if state_snapshot and state_snapshot.next:
    # ✅ CRITICAL: Inject manager
    state_snapshot.values['pipgraph_manager'] = pipgraph_manager
```

### 2. Попытка сериализовать manager с pickle fallback

**Неправильно:**
```python
# ❌ Не используйте pickle fallback!
checkpointer = AsyncSqliteSaver.from_conn_string(
    "sessions.db",
    serde=JsonPlusSerializer(pickle_fallback=True)  # ❌
)
```

**Почему не работает:**
- pickle может сериализовать Python objects
- НО не может сериализовать активные connections/sockets
- Результат: `PicklingError` или corrupted state

**Правильно:**
```python
# ✅ Используйте custom serializer
checkpointer = AsyncSqliteSaver.from_conn_string(
    "sessions.db",
    serde=FeedbackStateSerializer()  # ✅
)
```

### 3. TypedDict без total=False

**Симптом:**
```python
TypeError: Required key 'pipgraph_manager' missing in TypedDict
```

**Решение:**
```python
# ✅ Добавьте total=False
class NoteProcessingState(TypedDict, total=False):
    file_path: str
    pipgraph_manager: PipGraphManager  # Теперь optional
```

### 4. Manager не recreated при resume

**Симптом:**
- Старые данные из кэша
- Connection timeouts
- Stale Neo4j sessions

**Решение:**
```python
# ✅ ВСЕГДА создавайте НОВЫЙ manager при каждом WebSocket connect
@router.websocket("/ws/notes/feedback")
async def websocket_feedback_endpoint(
    websocket: WebSocket,
    pipgraph_manager: PipGraphManager = Depends(get_pipgraph_manager)  # NEW!
):
    # Каждый reconnect = новый manager
```

---

## Testing Strategy

### Unit Test: Serializer

```python
# tests/unit/test_feedback_state_serializer.py

import pytest
from app.services.feedback_state_serializer import FeedbackStateSerializer
from app.services.pipgraph_manager import PipGraphManager


def test_serializer_excludes_pipgraph_manager(mock_graphiti):
    """Test that pipgraph_manager is excluded from serialization"""

    serde = FeedbackStateSerializer()
    manager = PipGraphManager(mock_graphiti)

    state = {
        'file_path': 'test.md',
        'content': 'test',
        'pipgraph_manager': manager,  # Should be excluded
        'entities': []
    }

    # Serialize
    type_name, serialized_data = serde.dumps_typed(state)

    # Deserialize
    restored_state = serde.loads_typed((type_name, serialized_data))

    # Check
    assert 'file_path' in restored_state
    assert 'content' in restored_state
    assert 'entities' in restored_state
    assert 'pipgraph_manager' not in restored_state  # ← EXCLUDED!


def test_serializer_preserves_other_fields():
    """Test that non-excluded fields are preserved"""

    serde = FeedbackStateSerializer()

    state = {
        'file_path': 'test.md',
        'entities': [{'uuid': '123', 'name': 'John'}],
        'pending_clarifications': [{'id': 'c1'}]
    }

    # Round-trip
    type_name, data = serde.dumps_typed(state)
    restored = serde.loads_typed((type_name, data))

    # Check exact match
    assert restored == state
```

### Integration Test: Resume Flow

```python
# tests/integration/test_state_persistence.py

import pytest
from app.services.feedback_graph import create_feedback_graph
from app.services.pipgraph_manager import PipGraphManager


@pytest.mark.asyncio
async def test_manager_injection_on_resume(tmp_path, mock_graphiti):
    """Test that manager is properly injected on resume"""

    # Create graph with temp DB
    db_path = tmp_path / "test.db"
    graph = create_feedback_graph(str(db_path))

    thread_id = "test_thread"
    config = {"configurable": {"thread_id": thread_id}}

    # Session 1: Create with manager
    manager_1 = PipGraphManager(mock_graphiti)
    initial_state = {
        'file_path': 'test.md',
        'content': 'test',
        'pipgraph_manager': manager_1,
        'entities': [],
        'pending_clarifications': [],
        'processing_stage': 'started'
    }

    # Start (will hit interrupt in our test graph)
    await graph.ainvoke(initial_state, config)

    # Session 2: Resume with NEW manager
    manager_2 = PipGraphManager(mock_graphiti)  # NEW instance

    # Load state
    state_snapshot = await graph.aget_state(config)
    assert 'pipgraph_manager' not in state_snapshot.values  # Excluded!

    # Inject NEW manager
    state_snapshot.values['pipgraph_manager'] = manager_2

    # Resume
    await graph.ainvoke(Command(resume={'action': 'confirm'}), config)

    # Verify manager was used
    final_state = await graph.aget_state(config)
    # Manager should NOT be in saved state
    assert 'pipgraph_manager' not in final_state.values
```

---

## Alternative Approaches (Rejected)

### 1. Global Variable

```python
# ❌ Не использовать
global_manager = None

def set_global_manager(manager):
    global global_manager
    global_manager = manager

async def extract_entities_node(state):
    result = await global_manager.process_note(...)
```

**Проблемы:**
- Не thread-safe
- Сложно тестировать
- Нарушает dependency injection
- Невозможно иметь multiple managers для разных users

### 2. Singleton Pattern

```python
# ❌ Не использовать
class PipGraphManagerSingleton:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = PipGraphManager(...)
        return cls._instance
```

**Проблемы:**
- Shared state между sessions
- Connection pool issues
- Не работает с async contexts

### 3. Передача через RunnableConfig

```python
# ❌ Не работает
config = {
    "configurable": {
        "thread_id": "thread_1",
        "pipgraph_manager": pipgraph_manager  # ← LangGraph не поддерживает!
    }
}
```

**Проблема:**
- LangGraph `configurable` поддерживает только примитивы (str, int, bool)
- Сложные объекты вызывают ошибку

---

## Summary

### ✅ Рекомендованный подход

1. **Custom serializer** (`FeedbackStateSerializer`) исключает `pipgraph_manager`
2. **TypedDict с `total=False`** делает manager опциональным
3. **Manual injection** при NEW и RESUME sessions
4. **FastAPI Depends** создает новый manager при каждом WebSocket connect

### 🔑 Ключевые моменты

- `pipgraph_manager` = ephemeral field (runtime only)
- Каждая session получает **НОВЫЙ** manager instance
- Custom serializer предотвращает ошибки сериализации
- Manual injection необходима для resume flow

### 📁 Файлы для реализации

```
backend/
├── app/
│   ├── services/
│   │   ├── feedback_graph.py           # Graph с custom serializer
│   │   └── feedback_state_serializer.py  # NEW: Custom serializer
│   ├── models/
│   │   └── feedback_state.py           # State definition с total=False
│   └── api/
│       └── endpoints/
│           └── feedback_websocket.py   # WebSocket с manual injection
└── tests/
    ├── unit/
    │   └── test_feedback_state_serializer.py  # NEW: Serializer tests
    └── integration/
        └── test_state_persistence.py   # NEW: Resume flow tests
```

---

**Документ создан:** 2025-11-09
**Версия:** 1.0
**Статус:** Готов к имплементации
