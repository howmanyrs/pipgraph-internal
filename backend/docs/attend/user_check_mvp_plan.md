# MVP Plan: user_check + Multi-Round Feedback Cycle

**Дата создания:** 2025-11-05
**Цель:** Реализовать минимальную рабочую версию multi-round WebSocket messaging с clarification request/response flow для системы user_check

---

## Оглавление

1. [Executive Summary](#executive-summary)
2. [Архитектурное решение](#архитектурное-решение)
3. [Совместимость LangGraph + Graphiti](#совместимость-langgraph--graphiti)
4. [user_check State Machine](#user_check-state-machine)
5. [LangGraph Structure](#langgraph-structure)
6. [Pydantic Models](#pydantic-models)
7. [Session Management](#session-management)
8. [WebSocket Integration](#websocket-integration)
9. [Implementation Roadmap](#implementation-roadmap)
10. [Code Examples](#code-examples)
11. [Testing Strategy](#testing-strategy)

---

## Executive Summary

### Проблема

Текущая система обрабатывает заметки автоматически без возможности пользователя подтвердить или скорректировать:
- Определенный PARA тип заметки (Project/Area/Resource/Archive)
- Извлеченные сущности (Person, Organization, Task)
- Связи между сущностями

Пользователь должен иметь возможность:
- Ответить сразу или через день/неделю
- Подтвердить предложенный вариант
- Выбрать альтернативу из списка
- Создать новый вариант
- Промолчать (timeout/skip)

### Решение

**MVP включает:**
1. **LangGraph** - workflow управление с `interrupt()` для паузы и `Command(resume=...)` для продолжения
2. **Graphiti (PipGraphManager)** - извлечение сущностей и сохранение в граф
3. **AsyncSqliteSaver** - persistent sessions, пользователь может ответить через день
4. **WebSocket** - transport для streaming events и real-time communication
5. **user_check attribute** - workflow-атрибут для отслеживания статуса подтверждения

### Критерий успеха MVP

Работающий demo:
```
1. Client → send note → server
2. Server → extract entities → clarification request
3. Client disconnect
4. (1 day later)
5. Client reconnect → receive pending request
6. Client → send response
7. Server → process feedback → complete
```

---

## Архитектурное решение

### Разделение ответственности

```
┌──────────────────────────────────────────────────────────┐
│                     USER (Obsidian)                      │
└────────────────────────┬─────────────────────────────────┘
                         │ WebSocket
                         ↓
┌──────────────────────────────────────────────────────────┐
│                  LANGGRAPH WORKFLOW                      │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐          │
│  │ Extract  │ → │ Clarify  │ → │ Finalize │          │
│  │ Entities │    │ (pause)  │    │ & Save   │          │
│  └──────────┘    └──────────┘    └──────────┘          │
│                       ↓                                  │
│                  interrupt()                             │
│                  [wait for user]                         │
│                       ↓                                  │
│                  Command(resume=...)                     │
└────────────────────────┬─────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────┐
│              PIPGRAPH MANAGER (Graphiti)                 │
│  - extract_nodes()                                       │
│  - resolve_extracted_nodes()                             │
│  - extract_edges()                                       │
│  - add_nodes_and_edges_bulk()                            │
└────────────────────────┬─────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────┐
│                      NEO4J DATABASE                      │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│               ASYNCSQLITESAVER (State)                   │
│  - LangGraph thread state                                │
│  - Pending clarifications                                │
│  - Conversation history                                  │
└──────────────────────────────────────────────────────────┘
```

### Компоненты

| Компонент | Ответственность | Технология |
|-----------|-----------------|------------|
| **LangGraph** | Workflow orchestration, interrupt/resume | langgraph |
| **PipGraphManager** | Entity extraction, graph operations | graphiti_core |
| **AsyncSqliteSaver** | Persistent state storage | langgraph.checkpoint.aiosqlite |
| **WebSocket** | Real-time communication | FastAPI WebSocket |
| **user_check** | Workflow status tracking | node.attributes (dict) |

### Почему именно такая архитектура?

**LangGraph для workflow:**
- ✅ Встроенная поддержка `interrupt()` для human-in-the-loop
- ✅ Persistent checkpointing из коробки
- ✅ Thread-based sessions (один thread = одна заметка)
- ✅ Resume через месяцы на другой машине

**PipGraphManager (Graphiti) для graph:**
- ✅ Уже реализовано извлечение сущностей
- ✅ Интеграция с Neo4j
- ✅ PARA entity types
- ✅ Точки интервенции уже размечены в коде

**Их совместимость:**
- LangGraph nodes вызывают async методы PipGraphManager
- Нет конфликтов event loop (оба на asyncio)
- Проверено в production (Zep integration example)

---

## Совместимость LangGraph + Graphiti

### Анализ на основе Zep Example

**Источник:** https://help.getzep.com/graphiti/integrations/lang-graph-agent

#### Ключевые паттерны интеграции

**1. Graphiti вызывается из LangGraph nodes:**

```python
async def chatbot_node(state: State):
    # 1. Search Graphiti for context
    edge_results = await client.search(
        query,
        center_node_uuid=state['user_node_uuid'],
        num_results=5
    )
    facts_string = edges_to_facts_string(edge_results)

    # 2. Build context with facts
    system_message = SystemMessage(content=f"Facts: {facts_string}")

    # 3. Generate response
    response = await llm.ainvoke(messages)

    # 4. Save to Graphiti (non-blocking!)
    asyncio.create_task(
        client.add_episode(
            episode_body=f"User: {state['messages'][-1]}\nBot: {response.content}",
            source=EpisodeType.message,
            reference_time=datetime.now()
        )
    )

    return {'messages': [response]}
```

**Ключевой момент:** `asyncio.create_task()` для неблокирующего сохранения!

**2. LangGraph управляет state, Graphiti - facts:**

```python
class State(TypedDict):
    messages: Annotated[list, add_messages]  # LangGraph state
    user_name: str
    user_node_uuid: str  # Ссылка на Graphiti node

# State persistence
memory = MemorySaver()  # or AsyncSqliteSaver
graph = graph_builder.compile(checkpointer=memory)
```

**3. Нет конфликтов:**
- LangGraph async + Graphiti async = одна event loop
- PipGraphManager - это обычная async функция, вызывается из node
- Checkpointing не мешает Neo4j operations

### Применение для PipGraph

```python
async def extract_entities_node(state: NoteProcessingState):
    """LangGraph node вызывающий PipGraphManager"""

    # 1. Вызываем PipGraphManager (обертка Graphiti)
    result = await state['pipgraph_manager'].process_note(
        name=state['file_path'],
        episode_body=state['content'],
        source_description='Obsidian note',
        reference_time=datetime.now(timezone.utc)
    )

    # 2. Добавляем user_check к новым сущностям
    for node in result.nodes:
        if is_new_entity(node, state):
            node.attributes['user_check'] = 'pending'

    # 3. Обновляем state
    return {
        'episode_uuid': result.episode.uuid,
        'entities': result.nodes,
        'relationships': result.edges
    }
```

**НЕТ КОНФЛИКТОВ потому что:**
- `PipGraphManager.process_note()` = обычная async функция
- Вызывается как любая другая async операция
- Neo4j driver уже async (graphiti_core использует asyncio)
- LangGraph checkpointer работает с Python objects, не мешает database

---

## user_check State Machine

### Статусы

```python
from enum import Enum

class UserCheckStatus(str, Enum):
    """Статусы подтверждения пользователя для сущностей"""

    # Начальные состояния
    PENDING = "pending"              # Извлечено, не показано пользователю
    AWAITING_INPUT = "awaiting_input"  # Запрошено подтверждение, ждем ответа

    # Финальные состояния
    CONFIRMED = "confirmed"          # Пользователь подтвердил (или auto-confirm)
    MODIFIED = "modified"            # Пользователь отредактировал
    REJECTED = "rejected"            # Пользователь отклонил
    SKIPPED = "skipped"              # Пользователь пропустил решение
    TIMED_OUT = "timed_out"          # Timeout истек (не используется в MVP)
```

### State Machine Diagram

```
                    [Entity Extracted]
                            ↓
                       PENDING
                            ↓
                [needs_clarification?]
                    ↙           ↘
                YES              NO
                 ↓                ↓
          AWAITING_INPUT     CONFIRMED
                 ↓
        [interrupt() - pause]
                 ↓
         [User reconnects]
                 ↓
         [User responds]
          ↙      ↓      ↘
    CONFIRMED  MODIFIED  REJECTED/SKIPPED
```

### Lifecycle

```python
# 1. Извлечение сущности (extract_entities_node)
entity.attributes['user_check'] = UserCheckStatus.PENDING
entity.attributes['user_check_timestamp'] = utc_now().isoformat()

# 2. Проверка нужна ли clarification (check_clarification_node)
if needs_clarification(entity):
    entity.attributes['user_check'] = UserCheckStatus.AWAITING_INPUT
    # → interrupt() pause

# 3. Пользователь отвечает (process_response_node)
if user_action == "confirm":
    entity.attributes['user_check'] = UserCheckStatus.CONFIRMED
elif user_action == "modify":
    entity.attributes.update(user_modifications)
    entity.attributes['user_check'] = UserCheckStatus.MODIFIED
elif user_action == "reject":
    entity.attributes['user_check'] = UserCheckStatus.REJECTED
elif user_action == "skip":
    entity.attributes['user_check'] = UserCheckStatus.SKIPPED

entity.attributes['user_check_timestamp'] = utc_now().isoformat()

# 4. Финализация (finalize_node)
confirmed_entities = [
    e for e in entities
    if e.attributes.get('user_check') in [
        UserCheckStatus.CONFIRMED,
        UserCheckStatus.MODIFIED
    ]
]
await save_to_neo4j(confirmed_entities)
```

### Почему НЕ в entity_types?

**Неправильно:**
```python
class Project(BaseModel):
    deadline: str = Field(description="Project deadline")
    goal: str = Field(description="Main objective")
    user_check: str = Field(description="User confirmation status")  # ❌
```

**Почему не работает:**
- `extract_attributes_from_nodes()` вызывает LLM с JSON Schema
- LLM пытается найти `user_check` в тексте заметки (nonsense!)
- Field description = "instructions for extraction", не metadata storage

**Правильно:**
```python
# После извлечения добавляем напрямую
entity.attributes['user_check'] = 'pending'  # ✅
```

**Почему работает:**
- user_check = workflow state, не semantic attribute
- Добавляется в коде, не извлекается LLM
- Паттерн из pipgraph_manager.py:306: `node.attributes['user_description'] = description`

---

## LangGraph Structure

### Graph Definition

```python
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.aiosqlite import AsyncSqliteSaver

# 1. Define state
class NoteProcessingState(TypedDict):
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

    # Workflow metadata
    pipgraph_manager: PipGraphManager  # Pass manager as state
    processing_stage: str

# 2. Create graph
graph_builder = StateGraph(NoteProcessingState)

# 3. Add nodes
graph_builder.add_node("extract_entities", extract_entities_node)
graph_builder.add_node("check_clarification", check_clarification_node)
graph_builder.add_node("request_clarification", request_clarification_node)
graph_builder.add_node("process_response", process_response_node)
graph_builder.add_node("finalize", finalize_node)

# 4. Define edges
graph_builder.add_edge(START, "extract_entities")
graph_builder.add_edge("extract_entities", "check_clarification")

# Conditional: нужна ли clarification?
graph_builder.add_conditional_edges(
    "check_clarification",
    should_request_clarification,  # function
    {
        "clarify": "request_clarification",
        "finalize": "finalize"
    }
)

graph_builder.add_edge("request_clarification", "process_response")
graph_builder.add_edge("process_response", "check_clarification")  # Loop!
graph_builder.add_edge("finalize", END)

# 5. Compile with persistent checkpoint
checkpointer = AsyncSqliteSaver.from_conn_string("sessions.db")
graph = graph_builder.compile(checkpointer=checkpointer)
```

### Nodes Implementation

#### Node 1: Extract Entities

```python
async def extract_entities_node(state: NoteProcessingState) -> dict:
    """
    Извлекает сущности из заметки через PipGraphManager.
    Добавляет user_check='pending' к новым сущностям.
    """
    logger.info(f"Extracting entities from {state['file_path']}")

    # Call PipGraphManager (wraps Graphiti)
    result = await state['pipgraph_manager'].process_note(
        name=state['file_path'],
        episode_body=state['content'],
        source_description='Obsidian note',
        reference_time=datetime.now(timezone.utc)
    )

    # Mark new entities as pending
    for entity in result.nodes:
        if not entity.attributes.get('user_check'):
            entity.attributes['user_check'] = UserCheckStatus.PENDING
            entity.attributes['user_check_timestamp'] = utc_now().isoformat()

    return {
        'episode_uuid': result.episode.uuid,
        'entities': result.nodes,
        'relationships': result.edges,
        'processing_stage': 'entities_extracted'
    }
```

#### Node 2: Check Clarification Needed

```python
def should_request_clarification(state: NoteProcessingState) -> str:
    """
    Conditional edge function: проверяет есть ли pending clarifications.
    """
    # Check if any entities need clarification
    needs_clarification = any(
        entity.attributes.get('user_check') == UserCheckStatus.AWAITING_INPUT
        for entity in state['entities']
    )

    # Check if there are pending clarifications not yet sent
    has_pending = len(state.get('pending_clarifications', [])) > 0

    if needs_clarification or has_pending:
        return "clarify"
    else:
        return "finalize"


async def check_clarification_node(state: NoteProcessingState) -> dict:
    """
    Проверяет какие сущности нуждаются в подтверждении.
    Создает clarification requests.
    """
    logger.info("Checking if clarification is needed")

    pending_clarifications = []

    for entity in state['entities']:
        # В MVP: все новые сущности требуют подтверждения
        if entity.attributes.get('user_check') == UserCheckStatus.PENDING:
            # Mark as awaiting input
            entity.attributes['user_check'] = UserCheckStatus.AWAITING_INPUT

            # Create clarification request
            clarification = {
                'request_id': f"clarif_{uuid4().hex[:8]}",
                'entity_uuid': entity.uuid,
                'entity_name': entity.name,
                'entity_type': entity.labels[0] if entity.labels else 'Entity',
                'question': f"Подтвердите сущность '{entity.name}' типа {entity.labels[0]}?",
                'options': [
                    {'action': 'confirm', 'label': 'Подтвердить'},
                    {'action': 'modify', 'label': 'Редактировать'},
                    {'action': 'reject', 'label': 'Отклонить'},
                    {'action': 'skip', 'label': 'Пропустить'}
                ]
            }
            pending_clarifications.append(clarification)

    # Pick first clarification for this round
    current = pending_clarifications[0] if pending_clarifications else None

    return {
        'pending_clarifications': pending_clarifications,
        'current_clarification': current,
        'entities': state['entities']  # Updated with AWAITING_INPUT status
    }
```

#### Node 3: Request Clarification (with interrupt)

```python
from langgraph.types import interrupt

async def request_clarification_node(state: NoteProcessingState) -> dict:
    """
    Отправляет clarification request пользователю и ПАУЗИТ выполнение.

    interrupt() останавливает graph execution.
    State сохраняется в checkpointer (SQLite).
    Resume через Command(resume=user_response).
    """
    logger.info("Requesting clarification from user")

    clarification = state['current_clarification']

    if not clarification:
        logger.warning("No current clarification, skipping")
        return {}

    # КЛЮЧЕВОЙ МОМЕНТ: interrupt() паузит выполнение
    # Возвращает control до получения user response
    user_response = interrupt(clarification)

    # Код ниже НЕ выполняется до resume!
    # Когда пользователь отвечает и graph.ainvoke(Command(resume=...))
    # вызывается, user_response будет содержать ответ

    logger.info(f"User responded: {user_response}")

    return {
        'user_response': user_response
    }
```

**Важно:** `interrupt()` работает как:
```python
# До interrupt():
print("Before interrupt")
user_response = interrupt({"question": "Answer?"})
# ← Execution STOPS here, state saved to SQLite

# (User disconnects, 1 day passes, user reconnects)

# Resume via: graph.ainvoke(Command(resume={"answer": "yes"}), config)
# ↓ Execution CONTINUES here
print(f"After interrupt: {user_response}")  # {'answer': 'yes'}
```

#### Node 4: Process Response

```python
async def process_response_node(state: NoteProcessingState) -> dict:
    """
    Обрабатывает ответ пользователя, обновляет entity status.
    """
    user_response = state.get('user_response')
    current_clarification = state['current_clarification']

    if not user_response or not current_clarification:
        return {}

    # Find entity
    entity_uuid = current_clarification['entity_uuid']
    entity = next(
        (e for e in state['entities'] if e.uuid == entity_uuid),
        None
    )

    if not entity:
        logger.error(f"Entity not found: {entity_uuid}")
        return {}

    # Process user action
    action = user_response.get('action')

    if action == 'confirm':
        entity.attributes['user_check'] = UserCheckStatus.CONFIRMED
        logger.info(f"Entity confirmed: {entity.name}")

    elif action == 'modify':
        # Apply modifications
        modifications = user_response.get('modifications', {})
        entity.attributes.update(modifications)
        entity.attributes['user_check'] = UserCheckStatus.MODIFIED
        logger.info(f"Entity modified: {entity.name}")

    elif action == 'reject':
        entity.attributes['user_check'] = UserCheckStatus.REJECTED
        logger.info(f"Entity rejected: {entity.name}")

    elif action == 'skip':
        entity.attributes['user_check'] = UserCheckStatus.SKIPPED
        logger.info(f"Entity skipped: {entity.name}")

    entity.attributes['user_check_timestamp'] = utc_now().isoformat()

    # Remove processed clarification
    remaining = [
        c for c in state['pending_clarifications']
        if c['request_id'] != current_clarification['request_id']
    ]

    # Set next clarification
    next_clarification = remaining[0] if remaining else None

    return {
        'entities': state['entities'],
        'pending_clarifications': remaining,
        'current_clarification': next_clarification,
        'user_response': None  # Clear
    }
```

#### Node 5: Finalize

```python
async def finalize_node(state: NoteProcessingState) -> dict:
    """
    Финализирует обработку: сохраняет подтвержденные сущности в Neo4j.
    """
    logger.info("Finalizing note processing")

    # Filter confirmed/modified entities
    confirmed_entities = [
        e for e in state['entities']
        if e.attributes.get('user_check') in [
            UserCheckStatus.CONFIRMED,
            UserCheckStatus.MODIFIED
        ]
    ]

    rejected_entities = [
        e for e in state['entities']
        if e.attributes.get('user_check') == UserCheckStatus.REJECTED
    ]

    logger.info(
        f"Confirmed: {len(confirmed_entities)}, "
        f"Rejected: {len(rejected_entities)}, "
        f"Total: {len(state['entities'])}"
    )

    # Save to Neo4j (already saved by PipGraphManager, но можно обновить статусы)
    # В MVP: PipGraphManager уже сохранил всё в extract_entities_node
    # Здесь можно добавить update статусов если нужно

    return {
        'processing_stage': 'completed',
        'confirmed_count': len(confirmed_entities),
        'rejected_count': len(rejected_entities)
    }
```

### Graph Flow Visualization

```
START
  ↓
extract_entities (вызывает PipGraphManager)
  ↓
  [entities с user_check='pending']
  ↓
check_clarification
  ↓
  [создаёт pending_clarifications]
  ↓
  [conditional edge]
  ├─→ finalize → END (если нет clarifications)
  │
  └─→ request_clarification
       ↓
       interrupt(clarification_request)
       ↓
       [PAUSE - state saved to SQLite]
       ↓
       [User disconnects]
       ↓
       [1 day passes...]
       ↓
       [User reconnects → graph.ainvoke(Command(resume=response))]
       ↓
       [RESUME - user_response received]
       ↓
     process_response
       ↓
       [update entity.user_check]
       ↓
     check_clarification (LOOP)
       ↓
       [conditional: more clarifications?]
       ├─→ YES → request_clarification (loop)
       └─→ NO → finalize → END
```

---

## Pydantic Models

### State Models

```python
from typing import TypedDict, Annotated, Optional
from pydantic import BaseModel
from graphiti_core.nodes import EntityNode
from graphiti_core.edges import EntityEdge

class NoteProcessingState(TypedDict):
    """
    LangGraph state для обработки заметки.
    Сохраняется в AsyncSqliteSaver между interrupt/resume.
    """
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
    pipgraph_manager: PipGraphManager
    processing_stage: str  # "started" | "entities_extracted" | "completed"
```

### WebSocket Message Models

```python
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field

class MessageType(str, Enum):
    """Типы WebSocket сообщений"""
    PROCESSING_STATUS = "processing_status"
    CLARIFICATION_REQUEST = "clarification_request"
    USER_RESPONSE = "user_response"
    PROCESSING_COMPLETE = "processing_complete"
    ERROR = "error"


class WebSocketMessage(BaseModel):
    """Базовая структура WebSocket сообщения"""
    message_type: MessageType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: dict


class ProcessingStatusData(BaseModel):
    """Статус обработки заметки"""
    stage: str  # "started" | "extracting" | "clarifying" | "finalizing"
    message: str
    progress: Optional[float] = None  # 0.0 - 1.0


class ClarificationOption(BaseModel):
    """Опция для выбора пользователем"""
    action: str  # "confirm" | "modify" | "reject" | "skip"
    label: str
    description: Optional[str] = None


class ClarificationRequestData(BaseModel):
    """Запрос подтверждения от пользователя"""
    request_id: str
    entity_uuid: str
    entity_name: str
    entity_type: str
    question: str
    options: list[ClarificationOption]
    context: Optional[dict] = None


class UserResponseData(BaseModel):
    """Ответ пользователя на clarification request"""
    request_id: str
    action: str  # "confirm" | "modify" | "reject" | "skip"
    modifications: Optional[dict] = None  # For "modify" action
    comment: Optional[str] = None


class EntitySummary(BaseModel):
    """Краткая информация о сущности для клиента"""
    uuid: str
    name: str
    type: str
    user_check: str
    attributes: dict


class ProcessingCompleteData(BaseModel):
    """Результат обработки заметки"""
    episode_uuid: str
    status: str  # "success" | "partial" | "failed"
    confirmed_count: int
    rejected_count: int
    entities: list[EntitySummary]
    message: str
```

### Helper Constructors

```python
def create_clarification_message(clarification: dict) -> WebSocketMessage:
    """Создает WebSocket сообщение с clarification request"""
    return WebSocketMessage(
        message_type=MessageType.CLARIFICATION_REQUEST,
        data=ClarificationRequestData(**clarification).dict()
    )


def create_processing_status_message(stage: str, message: str) -> WebSocketMessage:
    """Создает сообщение о статусе обработки"""
    return WebSocketMessage(
        message_type=MessageType.PROCESSING_STATUS,
        data=ProcessingStatusData(stage=stage, message=message).dict()
    )
```

---

## Session Management

### Thread ID Strategy

**Решение:** `thread_id = f"note:{file_path}"`

**Обоснование:**
- Одна заметка = один LangGraph thread
- Повторная обработка той же заметки = resume существующего thread
- История взаимодействий как чат на тему заметки

**Пример:**
```python
file_path = "Projects/Q4 Marketing Campaign.md"
thread_id = "note:Projects/Q4 Marketing Campaign.md"

config = {
    "configurable": {
        "thread_id": thread_id
    }
}
```

### Persistence with AsyncSqliteSaver

```python
from langgraph.checkpoint.aiosqlite import AsyncSqliteSaver

# Setup
checkpointer = AsyncSqliteSaver.from_conn_string("sessions.db")
graph = graph_builder.compile(checkpointer=checkpointer)

# Start processing (new session)
result = await graph.ainvoke(initial_state, config=config)
# → State saved to sessions.db after interrupt()

# Resume (same config)
result = await graph.ainvoke(
    Command(resume=user_response),
    config=config  # Same thread_id!
)
# → Loads state from sessions.db, continues execution
```

### Session Lifecycle

```python
# 1. Client connects, sends file_path
file_path = "Projects/Q4 Marketing.md"
thread_id = f"note:{file_path}"
config = {"configurable": {"thread_id": thread_id}}

# 2. Check if thread exists
state = await graph.aget_state(config)

if state and state.next:
    # Thread exists and has pending steps
    logger.info(f"Resuming thread: {thread_id}")
    # Send pending clarifications if any
else:
    # New thread
    logger.info(f"Starting new thread: {thread_id}")
    # Start processing

# 3. Execute graph
async for event in graph.astream_events(state, config):
    if event["event"] == "on_interrupt":
        # Send clarification to client
        await websocket.send_json(event["data"])
        # Wait for response
        user_response = await websocket.receive_json()
        # Resume
        await graph.ainvoke(Command(resume=user_response), config)

# 4. Client disconnect
# State automatically saved in SQLite by checkpointer

# 5. Client reconnect (1 day later)
# Load state, send pending clarifications, continue
```

### State Structure in SQLite

AsyncSqliteSaver хранит:
```sql
CREATE TABLE checkpoints (
    thread_id TEXT,
    checkpoint_id TEXT,
    checkpoint BLOB,  -- Pickled state
    metadata JSONB,
    PRIMARY KEY (thread_id, checkpoint_id)
);
```

**Что сохраняется:**
- `NoteProcessingState` (полностью)
- Pending clarifications
- Current clarification
- Entities с user_check статусами
- Graph execution position (какой node следующий)

**Что НЕ сохраняется:**
- WebSocket connection (ephemeral)
- PipGraphManager instance (recreate on resume)

### Cleanup Strategy (для MVP - ручной)

```python
async def cleanup_old_threads(max_age_days: int = 30):
    """Удаляет старые thread states"""
    # В MVP: manual cleanup script
    # В production: background task
    pass
```

---

## WebSocket Integration

### WebSocket Endpoint

```python
from fastapi import WebSocket, WebSocketDisconnect
from langgraph.types import Command

@router.websocket("/ws/notes/feedback")
async def websocket_feedback_endpoint(
    websocket: WebSocket,
    pipgraph_manager: PipGraphManager = Depends(get_pipgraph_manager)
):
    """
    WebSocket endpoint для multi-round feedback cycle.

    Flow:
    1. Client connects
    2. Client sends {"file_path": "...", "content": "..."}
    3. Server starts/resumes LangGraph execution
    4. Server streams events to client (status, clarifications)
    5. Client sends responses when ready
    6. Repeat until completion
    """
    await websocket.accept()

    try:
        # 1. Receive initial message
        data = await websocket.receive_json()
        file_path = data["file_path"]
        content = data.get("content", "")

        # 2. Setup thread config
        thread_id = f"note:{file_path}"
        config = {"configurable": {"thread_id": thread_id}}

        # 3. Check if resuming or starting new
        state_snapshot = await graph.aget_state(config)

        if state_snapshot and state_snapshot.next:
            # Resuming existing thread
            logger.info(f"Resuming thread: {thread_id}")

            # Send pending clarifications if any
            current_state = state_snapshot.values
            if current_state.get('current_clarification'):
                clarification_msg = create_clarification_message(
                    current_state['current_clarification']
                )
                await websocket.send_json(clarification_msg.dict())

                # Wait for response
                user_response = await websocket.receive_json()

                # Resume graph
                await execute_graph_with_feedback(
                    websocket,
                    pipgraph_manager,
                    config,
                    resume_value=user_response
                )
        else:
            # New thread
            logger.info(f"Starting new thread: {thread_id}")

            # Send processing started status
            await websocket.send_json(
                create_processing_status_message(
                    "started",
                    f"Processing note: {file_path}"
                ).dict()
            )

            # Initial state
            initial_state = NoteProcessingState(
                file_path=file_path,
                content=content,
                episode_uuid=None,
                entities=[],
                relationships=[],
                pending_clarifications=[],
                current_clarification=None,
                user_response=None,
                pipgraph_manager=pipgraph_manager,
                processing_stage="started"
            )

            # Execute graph
            await execute_graph_with_feedback(
                websocket,
                pipgraph_manager,
                config,
                initial_state=initial_state
            )

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {thread_id}")
        # State already saved by checkpointer

    except Exception as e:
        logger.error(f"Error in WebSocket handler: {e}", exc_info=True)
        await websocket.send_json(
            WebSocketMessage(
                message_type=MessageType.ERROR,
                data={"error": str(e)}
            ).dict()
        )
        await websocket.close()
```

### Graph Execution with Feedback

```python
async def execute_graph_with_feedback(
    websocket: WebSocket,
    pipgraph_manager: PipGraphManager,
    config: dict,
    initial_state: Optional[NoteProcessingState] = None,
    resume_value: Optional[dict] = None
):
    """
    Выполняет LangGraph с обработкой interrupt/resume через WebSocket.

    Streams events to client:
    - Processing status updates
    - Clarification requests (on interrupt)
    - Completion status
    """
    try:
        # Prepare input
        if resume_value:
            # Resuming with user response
            graph_input = Command(resume=resume_value)
        else:
            # Starting new
            graph_input = initial_state

        # Stream graph execution
        async for event in graph.astream_events(graph_input, config):
            event_type = event.get("event")

            if event_type == "on_chain_start":
                # Node started
                node_name = event.get("name", "unknown")
                await websocket.send_json(
                    create_processing_status_message(
                        node_name,
                        f"Executing: {node_name}"
                    ).dict()
                )

            elif event_type == "on_chain_end":
                # Node completed
                node_name = event.get("name", "unknown")
                logger.info(f"Node completed: {node_name}")

            elif event_type == "on_interrupt":
                # interrupt() called - need user input
                clarification = event.get("value")

                # Send clarification request to client
                clarification_msg = create_clarification_message(clarification)
                await websocket.send_json(clarification_msg.dict())

                # Wait for user response
                user_response_raw = await websocket.receive_json()

                # Validate response
                user_response = UserResponseData(**user_response_raw)

                # Resume graph with response
                await graph.ainvoke(
                    Command(resume=user_response.dict()),
                    config
                )

        # Processing complete
        final_state = await graph.aget_state(config)

        await websocket.send_json(
            WebSocketMessage(
                message_type=MessageType.PROCESSING_COMPLETE,
                data=ProcessingCompleteData(
                    episode_uuid=final_state.values.get('episode_uuid', ''),
                    status="success",
                    confirmed_count=final_state.values.get('confirmed_count', 0),
                    rejected_count=final_state.values.get('rejected_count', 0),
                    entities=[
                        EntitySummary(
                            uuid=e.uuid,
                            name=e.name,
                            type=e.labels[0] if e.labels else 'Entity',
                            user_check=e.attributes.get('user_check', 'unknown'),
                            attributes=e.attributes
                        )
                        for e in final_state.values.get('entities', [])
                    ],
                    message="Note processing completed"
                ).dict()
            ).dict()
        )

    except Exception as e:
        logger.error(f"Error executing graph: {e}", exc_info=True)
        raise
```

### Client-Side Flow (Pseudocode)

```typescript
// Obsidian plugin
class FeedbackCycleClient {
    async processNote(filePath: string, content: string) {
        const ws = new WebSocket("ws://localhost:8000/ws/notes/feedback");

        // 1. Connect and send note
        ws.onopen = () => {
            ws.send(JSON.stringify({
                file_path: filePath,
                content: content
            }));
        };

        // 2. Handle messages
        ws.onmessage = async (event) => {
            const message = JSON.parse(event.data);

            switch (message.message_type) {
                case "processing_status":
                    this.showStatus(message.data.message);
                    break;

                case "clarification_request":
                    // Show UI to user
                    const userResponse = await this.showClarificationUI(
                        message.data
                    );

                    // Send response back
                    ws.send(JSON.stringify(userResponse));
                    break;

                case "processing_complete":
                    this.updateFrontmatter(message.data);
                    ws.close();
                    break;

                case "error":
                    this.showError(message.data.error);
                    break;
            }
        };
    }

    async showClarificationUI(clarification) {
        // Show modal with options
        // User can:
        // - Confirm
        // - Modify (open editor)
        // - Reject
        // - Skip
        // - Close modal (disconnect, resume later)

        return {
            request_id: clarification.request_id,
            action: "confirm",  // or "modify", "reject", "skip"
            modifications: {}
        };
    }
}
```

### Resume After Disconnect

```python
# Client reconnects after 1 day
ws = new WebSocket("ws://localhost:8000/ws/notes/feedback");

ws.onopen = () => {
    // Send same file_path
    ws.send(JSON.stringify({
        file_path: "Projects/Q4 Marketing.md",
        content: ""  // Can be empty, not needed for resume
    }));
};

// Server detects existing thread, sends pending clarification
ws.onmessage = (event) => {
    const message = JSON.parse(event.data);

    if (message.message_type === "clarification_request") {
        // User sees pending question
        showClarificationUI(message.data);
    }
};
```

---

## Implementation Roadmap

### MVP Timeline: 7 дней

#### День 1-2: LangGraph Setup + Simple Graph

**Tasks:**
- [ ] Install LangGraph: `pip install langgraph`
- [ ] Create `NoteProcessingState` TypedDict
- [ ] Implement simple 2-node graph (extract → finalize)
- [ ] Setup AsyncSqliteSaver checkpointer
- [ ] Test basic graph execution with state persistence

**Deliverable:** Working LangGraph that calls PipGraphManager and saves state

**Files:**
- `backend/app/services/feedback_graph.py` - Graph definition
- `backend/app/models/feedback_state.py` - State models
- `tests/unit/test_feedback_graph.py` - Unit tests

---

#### День 3-4: Interrupt/Resume Flow

**Tasks:**
- [ ] Add `check_clarification_node`
- [ ] Add `request_clarification_node` with `interrupt()`
- [ ] Add `process_response_node`
- [ ] Implement conditional edges (clarify vs finalize)
- [ ] Test interrupt → save → resume cycle
- [ ] Add user_check status updates

**Deliverable:** Graph с interrupt/resume, user_check tracking

**Files:**
- Update `feedback_graph.py` with 5 nodes
- `backend/app/services/clarification_handler.py` - Helper functions
- `tests/integration/test_interrupt_resume.py`

---

#### День 5-6: WebSocket Integration

**Tasks:**
- [ ] Create WebSocket endpoint `/ws/notes/feedback`
- [ ] Implement `execute_graph_with_feedback()` streaming
- [ ] Add message models (Pydantic)
- [ ] Handle disconnect/reconnect scenarios
- [ ] Test with real WebSocket client
- [ ] Stream processing status, clarifications, completion

**Deliverable:** Working WebSocket ↔ LangGraph integration

**Files:**
- `backend/app/api/endpoints/feedback_websocket.py`
- `backend/app/models/websocket_messages.py`
- `tests/e2e/test_websocket_feedback.py`

---

#### День 7: Testing + Demo

**Tasks:**
- [ ] E2E test: note → clarification → disconnect → reconnect → complete
- [ ] Demo script (Python client simulating Obsidian)
- [ ] Documentation updates
- [ ] Performance testing (SQLite read/write speed)
- [ ] Error handling improvements

**Deliverable:** MVP ready for integration with Obsidian plugin

**Files:**
- `examples/feedback_demo.py` - Demo script
- `backend/docs/FEEDBACK_CYCLE_API.md` - API docs
- Update `backend/README.md` with new features

---

### Post-MVP Enhancements (не в scope)

- [ ] Confidence scoring для auto-confirm
- [ ] PARA classification feedback
- [ ] Timeout handling (soft timeouts with notifications)
- [ ] Batch clarifications (multiple entities at once)
- [ ] History UI (view all past interactions)
- [ ] Redis checkpointer (для distributed setup)
- [ ] Metrics (response time, confirmation rate)

---

## Code Examples

### Example 1: Complete Graph Definition

```python
# backend/app/services/feedback_graph.py

from typing import TypedDict, Optional
from uuid import uuid4
from datetime import datetime

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.aiosqlite import AsyncSqliteSaver
from langgraph.types import interrupt, Command

from graphiti_core.nodes import EntityNode
from graphiti_core.edges import EntityEdge
from app.services.pipgraph_manager import PipGraphManager
import logging

logger = logging.getLogger(__name__)


class UserCheckStatus:
    PENDING = "pending"
    AWAITING_INPUT = "awaiting_input"
    CONFIRMED = "confirmed"
    MODIFIED = "modified"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class NoteProcessingState(TypedDict):
    file_path: str
    content: str
    episode_uuid: Optional[str]
    entities: list[EntityNode]
    relationships: list[EntityEdge]
    pending_clarifications: list[dict]
    current_clarification: Optional[dict]
    user_response: Optional[dict]
    pipgraph_manager: PipGraphManager
    processing_stage: str


async def extract_entities_node(state: NoteProcessingState) -> dict:
    """Extract entities via PipGraphManager"""
    logger.info(f"Extracting entities from {state['file_path']}")

    result = await state['pipgraph_manager'].process_note(
        name=state['file_path'],
        episode_body=state['content'],
        source_description='Obsidian note',
        reference_time=datetime.now()
    )

    for entity in result.nodes:
        if not entity.attributes.get('user_check'):
            entity.attributes['user_check'] = UserCheckStatus.PENDING
            entity.attributes['user_check_timestamp'] = datetime.utcnow().isoformat()

    return {
        'episode_uuid': result.episode.uuid,
        'entities': result.nodes,
        'relationships': result.edges,
        'processing_stage': 'entities_extracted'
    }


async def check_clarification_node(state: NoteProcessingState) -> dict:
    """Check which entities need clarification"""
    logger.info("Checking clarification needs")

    pending_clarifications = []

    for entity in state['entities']:
        if entity.attributes.get('user_check') == UserCheckStatus.PENDING:
            entity.attributes['user_check'] = UserCheckStatus.AWAITING_INPUT

            clarification = {
                'request_id': f"clarif_{uuid4().hex[:8]}",
                'entity_uuid': entity.uuid,
                'entity_name': entity.name,
                'entity_type': entity.labels[0] if entity.labels else 'Entity',
                'question': f"Подтвердите сущность '{entity.name}'?",
                'options': [
                    {'action': 'confirm', 'label': 'Подтвердить'},
                    {'action': 'modify', 'label': 'Редактировать'},
                    {'action': 'reject', 'label': 'Отклонить'},
                    {'action': 'skip', 'label': 'Пропустить'}
                ]
            }
            pending_clarifications.append(clarification)

    current = pending_clarifications[0] if pending_clarifications else None

    return {
        'pending_clarifications': pending_clarifications,
        'current_clarification': current,
        'entities': state['entities']
    }


async def request_clarification_node(state: NoteProcessingState) -> dict:
    """Request clarification from user (with interrupt)"""
    logger.info("Requesting clarification")

    clarification = state['current_clarification']

    if not clarification:
        return {}

    # INTERRUPT: pause execution, wait for user response
    user_response = interrupt(clarification)

    logger.info(f"User responded: {user_response}")

    return {'user_response': user_response}


async def process_response_node(state: NoteProcessingState) -> dict:
    """Process user response"""
    user_response = state.get('user_response')
    current_clarification = state['current_clarification']

    if not user_response or not current_clarification:
        return {}

    entity_uuid = current_clarification['entity_uuid']
    entity = next((e for e in state['entities'] if e.uuid == entity_uuid), None)

    if not entity:
        return {}

    action = user_response.get('action')

    if action == 'confirm':
        entity.attributes['user_check'] = UserCheckStatus.CONFIRMED
    elif action == 'modify':
        entity.attributes.update(user_response.get('modifications', {}))
        entity.attributes['user_check'] = UserCheckStatus.MODIFIED
    elif action == 'reject':
        entity.attributes['user_check'] = UserCheckStatus.REJECTED
    elif action == 'skip':
        entity.attributes['user_check'] = UserCheckStatus.SKIPPED

    entity.attributes['user_check_timestamp'] = datetime.utcnow().isoformat()

    remaining = [
        c for c in state['pending_clarifications']
        if c['request_id'] != current_clarification['request_id']
    ]

    return {
        'entities': state['entities'],
        'pending_clarifications': remaining,
        'current_clarification': remaining[0] if remaining else None,
        'user_response': None
    }


async def finalize_node(state: NoteProcessingState) -> dict:
    """Finalize processing"""
    logger.info("Finalizing")

    confirmed = [
        e for e in state['entities']
        if e.attributes.get('user_check') in [
            UserCheckStatus.CONFIRMED,
            UserCheckStatus.MODIFIED
        ]
    ]

    rejected = [
        e for e in state['entities']
        if e.attributes.get('user_check') == UserCheckStatus.REJECTED
    ]

    logger.info(f"Confirmed: {len(confirmed)}, Rejected: {len(rejected)}")

    return {
        'processing_stage': 'completed',
        'confirmed_count': len(confirmed),
        'rejected_count': len(rejected)
    }


def should_request_clarification(state: NoteProcessingState) -> str:
    """Conditional edge: clarify or finalize?"""
    has_pending = len(state.get('pending_clarifications', [])) > 0
    return "clarify" if has_pending else "finalize"


# Build graph
def create_feedback_graph(checkpointer_path: str = "sessions.db"):
    """Create and compile feedback graph"""

    graph_builder = StateGraph(NoteProcessingState)

    # Add nodes
    graph_builder.add_node("extract_entities", extract_entities_node)
    graph_builder.add_node("check_clarification", check_clarification_node)
    graph_builder.add_node("request_clarification", request_clarification_node)
    graph_builder.add_node("process_response", process_response_node)
    graph_builder.add_node("finalize", finalize_node)

    # Add edges
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
    graph_builder.add_edge("process_response", "check_clarification")
    graph_builder.add_edge("finalize", END)

    # Compile with checkpointer
    checkpointer = AsyncSqliteSaver.from_conn_string(checkpointer_path)

    return graph_builder.compile(checkpointer=checkpointer)


# Global instance
feedback_graph = create_feedback_graph()
```

### Example 2: WebSocket Handler

```python
# backend/app/api/endpoints/feedback_websocket.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from langgraph.types import Command
import logging

from app.services.feedback_graph import feedback_graph, NoteProcessingState
from app.services.pipgraph_manager import PipGraphManager
from app.models.websocket_messages import (
    WebSocketMessage,
    MessageType,
    create_processing_status_message,
    create_clarification_message
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/notes/feedback")
async def websocket_feedback_endpoint(
    websocket: WebSocket,
    pipgraph_manager: PipGraphManager = Depends(get_pipgraph_manager)
):
    """Multi-round feedback cycle via WebSocket"""
    await websocket.accept()
    thread_id = None

    try:
        # Receive note data
        data = await websocket.receive_json()
        file_path = data["file_path"]
        content = data.get("content", "")

        thread_id = f"note:{file_path}"
        config = {"configurable": {"thread_id": thread_id}}

        # Check if resuming
        state_snapshot = await feedback_graph.aget_state(config)

        if state_snapshot and state_snapshot.next:
            # Resume
            logger.info(f"Resuming thread: {thread_id}")

            current_state = state_snapshot.values
            if current_state.get('current_clarification'):
                # Send pending clarification
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
            # New
            logger.info(f"Starting new thread: {thread_id}")

            await websocket.send_json(
                create_processing_status_message(
                    "started",
                    f"Processing {file_path}"
                ).dict()
            )

            initial_state = NoteProcessingState(
                file_path=file_path,
                content=content,
                episode_uuid=None,
                entities=[],
                relationships=[],
                pending_clarifications=[],
                current_clarification=None,
                user_response=None,
                pipgraph_manager=pipgraph_manager,
                processing_stage="started"
            )

            # Execute graph with feedback loop
            async for event in feedback_graph.astream_events(initial_state, config):
                event_type = event.get("event")

                if event_type == "on_chain_start":
                    node_name = event.get("name", "unknown")
                    await websocket.send_json(
                        create_processing_status_message(
                            node_name,
                            f"Executing: {node_name}"
                        ).dict()
                    )

                elif event_type == "on_interrupt":
                    clarification = event.get("value")

                    # Send to client
                    clarification_msg = create_clarification_message(clarification)
                    await websocket.send_json(clarification_msg.dict())

                    # Wait for response
                    user_response_raw = await websocket.receive_json()

                    # Resume
                    await feedback_graph.ainvoke(
                        Command(resume=user_response_raw),
                        config
                    )

            # Send completion
            final_state = await feedback_graph.aget_state(config)
            await websocket.send_json(
                WebSocketMessage(
                    message_type=MessageType.PROCESSING_COMPLETE,
                    data={
                        "status": "success",
                        "confirmed_count": final_state.values.get('confirmed_count', 0),
                        "message": "Processing complete"
                    }
                ).dict()
            )

    except WebSocketDisconnect:
        logger.info(f"Client disconnected: {thread_id}")

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await websocket.send_json(
            WebSocketMessage(
                message_type=MessageType.ERROR,
                data={"error": str(e)}
            ).dict()
        )
```

### Example 3: Demo Script

```python
# examples/feedback_demo.py

import asyncio
import websockets
import json

async def demo_feedback_cycle():
    """Demo: send note → receive clarification → disconnect → reconnect → respond"""

    uri = "ws://localhost:8000/ws/notes/feedback"

    # Phase 1: Initial connection
    print("=== Phase 1: Initial Connection ===")
    async with websockets.connect(uri) as ws:
        # Send note
        await ws.send(json.dumps({
            "file_path": "Projects/Demo Project.md",
            "content": "Meeting with John Smith about Q4 goals."
        }))

        # Receive messages
        while True:
            message = json.loads(await ws.recv())
            print(f"Received: {message['message_type']}")

            if message['message_type'] == 'clarification_request':
                print(f"Question: {message['data']['question']}")
                print("Disconnecting without answering...")
                break

    print("\n=== Simulating 1 day delay ===\n")
    await asyncio.sleep(2)  # Simulate delay

    # Phase 2: Reconnect and answer
    print("=== Phase 2: Reconnect ===")
    async with websockets.connect(uri) as ws:
        # Send same file_path
        await ws.send(json.dumps({
            "file_path": "Projects/Demo Project.md",
            "content": ""  # Not needed for resume
        }))

        # Receive pending clarification
        message = json.loads(await ws.recv())
        print(f"Received pending: {message['message_type']}")

        if message['message_type'] == 'clarification_request':
            request_id = message['data']['request_id']

            # Answer
            print("Answering: confirm")
            await ws.send(json.dumps({
                "request_id": request_id,
                "action": "confirm"
            }))

            # Receive completion
            while True:
                message = json.loads(await ws.recv())
                print(f"Received: {message['message_type']}")

                if message['message_type'] == 'processing_complete':
                    print(f"Success! Confirmed: {message['data']['confirmed_count']}")
                    break


if __name__ == "__main__":
    asyncio.run(demo_feedback_cycle())
```

---

## Testing Strategy

### Unit Tests

```python
# tests/unit/test_feedback_graph.py

import pytest
from app.services.feedback_graph import (
    extract_entities_node,
    check_clarification_node,
    process_response_node,
    UserCheckStatus
)

@pytest.mark.asyncio
async def test_extract_entities_marks_as_pending(mock_pipgraph_manager):
    """Test that extracted entities get user_check='pending'"""
    state = {
        'file_path': 'test.md',
        'content': 'Test content',
        'pipgraph_manager': mock_pipgraph_manager,
        'entities': []
    }

    result = await extract_entities_node(state)

    assert len(result['entities']) > 0
    assert result['entities'][0].attributes['user_check'] == UserCheckStatus.PENDING


@pytest.mark.asyncio
async def test_check_clarification_creates_requests():
    """Test clarification request creation"""
    entity = MockEntity(
        uuid='entity1',
        name='John Doe',
        labels=['Person'],
        attributes={'user_check': UserCheckStatus.PENDING}
    )

    state = {
        'entities': [entity],
        'pending_clarifications': [],
        'current_clarification': None
    }

    result = await check_clarification_node(state)

    assert len(result['pending_clarifications']) == 1
    assert result['current_clarification'] is not None
    assert entity.attributes['user_check'] == UserCheckStatus.AWAITING_INPUT
```

### Integration Tests

```python
# tests/integration/test_interrupt_resume.py

import pytest
from langgraph.types import Command
from app.services.feedback_graph import create_feedback_graph

@pytest.mark.asyncio
async def test_interrupt_resume_cycle(tmp_path, mock_pipgraph_manager):
    """Test full interrupt → save → resume cycle"""

    # Create graph with temp DB
    db_path = tmp_path / "test.db"
    graph = create_feedback_graph(str(db_path))

    thread_id = "test_thread"
    config = {"configurable": {"thread_id": thread_id}}

    # Phase 1: Start processing
    initial_state = {
        'file_path': 'test.md',
        'content': 'John Doe worked on project',
        'pipgraph_manager': mock_pipgraph_manager,
        # ...
    }

    # This will hit interrupt()
    with pytest.raises(Exception):  # interrupt raises
        await graph.ainvoke(initial_state, config)

    # Check state saved
    state_snapshot = await graph.aget_state(config)
    assert state_snapshot is not None
    assert len(state_snapshot.values['pending_clarifications']) > 0

    # Phase 2: Resume with response
    user_response = {
        'request_id': state_snapshot.values['current_clarification']['request_id'],
        'action': 'confirm'
    }

    result = await graph.ainvoke(Command(resume=user_response), config)

    # Check completion
    assert result['processing_stage'] == 'completed'
    assert result['confirmed_count'] == 1
```

### E2E Tests

```python
# tests/e2e/test_websocket_feedback.py

import pytest
from fastapi.testclient import TestClient
from app.api.main import app

@pytest.mark.asyncio
async def test_websocket_disconnect_reconnect():
    """Test WebSocket disconnect → reconnect → resume flow"""

    with TestClient(app) as client:
        # Phase 1: Connect and get clarification
        with client.websocket_connect("/ws/notes/feedback") as ws:
            # Send note
            ws.send_json({
                "file_path": "test.md",
                "content": "Test content"
            })

            # Receive clarification
            message = ws.receive_json()
            while message['message_type'] != 'clarification_request':
                message = ws.receive_json()

            clarification = message
            # Disconnect without answering

        # Phase 2: Reconnect
        with client.websocket_connect("/ws/notes/feedback") as ws:
            # Send same file_path
            ws.send_json({
                "file_path": "test.md",
                "content": ""
            })

            # Receive pending clarification
            message = ws.receive_json()
            assert message['message_type'] == 'clarification_request'
            assert message['data']['request_id'] == clarification['data']['request_id']

            # Answer
            ws.send_json({
                "request_id": message['data']['request_id'],
                "action": "confirm"
            })

            # Receive completion
            message = ws.receive_json()
            while message['message_type'] != 'processing_complete':
                message = ws.receive_json()

            assert message['data']['status'] == 'success'
```

---

## Заключение

### Что MVP дает?

✅ **Multi-round feedback cycle** - пользователь может ответить когда угодно
✅ **Persistent sessions** - state сохраняется в SQLite, survives restarts
✅ **Interrupt/resume flow** - LangGraph `interrupt()` для human-in-the-loop
✅ **user_check tracking** - workflow-атрибут для статуса подтверждения
✅ **WebSocket transport** - real-time streaming, disconnect/reconnect support
✅ **Integration с Graphiti** - нет конфликтов, PipGraphManager вызывается из nodes

### Что НЕ включено (post-MVP)?

- Confidence scoring для auto-confirm
- PARA classification feedback
- Batch clarifications
- Timeout notifications
- History UI
- Redis checkpointer
- Advanced error recovery

### Критерий успеха

Работающий demo где:
1. Заметка отправляется на сервер
2. Извлекаются сущности
3. Запрашивается подтверждение
4. Пользователь disconnect
5. Через день reconnect
6. Видит pending request
7. Отвечает
8. Processing завершается

### Next Steps

1. ✅ План составлен и одобрен
2. → Начать реализацию (День 1-2: LangGraph setup)
3. → Итеративная разработка по roadmap
4. → Testing на каждом этапе
5. → Integration с Obsidian plugin

---

**Документ создан:** 2025-11-05
**Версия:** 1.0
**Статус:** Готов к реализации
