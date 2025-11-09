# Feedback Graph v0.1 - LangGraph Structure

**Дата создания:** 2025-11-09
**Версия:** 0.1
**Источник:** [user_check_mvp_plan.md](./user_check_mvp_plan.md)

---

## Общий граф взаимодействия

```mermaid
flowchart TD
    START([START]) --> extract_entities[Extract Entities Node]

    extract_entities --> check_clarification[Check Clarification Node]

    check_clarification --> decision{Has Pending<br/>Clarifications?}

    decision -->|NO| finalize[Finalize Node]
    decision -->|YES| request_clarification[Request Clarification Node]

    request_clarification --> interrupt[INTERRUPT]
    interrupt -.->|State saved to SQLite| db[(SQLite<br/>AsyncSqliteSaver)]

    interrupt -.->|User disconnects| disconnect[Client Disconnect]
    disconnect -.->|1 day later| reconnect[Client Reconnect]

    reconnect -.->|Resume via Command| resume[RESUME]
    resume --> process_response[Process Response Node]

    process_response --> check_clarification

    finalize --> END([END])

    style interrupt fill:#ff6b6b,stroke:#c92a2a,color:#fff
    style resume fill:#51cf66,stroke:#2f9e44,color:#fff
    style db fill:#339af0,stroke:#1971c2,color:#fff
    style disconnect fill:#adb5bd,stroke:#495057,color:#fff
    style reconnect fill:#adb5bd,stroke:#495057,color:#fff
    style decision fill:#ffd43b,stroke:#fab005,color:#000
```

---

## Детальная структура с состояниями

```mermaid
stateDiagram-v2
    [*] --> ExtractEntities: START

    ExtractEntities --> CheckClarification: Entities extracted<br/>(user_check='pending')

    CheckClarification --> HasPending: Analyze entities

    HasPending --> RequestClarification: YES (pending_clarifications > 0)
    HasPending --> Finalize: NO (all confirmed/rejected)

    RequestClarification --> Interrupted: interrupt() called

    Interrupted --> SavedState: State → SQLite

    SavedState --> Disconnected: Client disconnects

    Disconnected --> WaitingForUser: Waiting...

    WaitingForUser --> Reconnected: Client reconnects<br/>(after hours/days)

    Reconnected --> LoadState: Load state from SQLite

    LoadState --> Resumed: Command(resume=response)

    Resumed --> ProcessResponse: User response received

    ProcessResponse --> UpdateEntity: Update entity.user_check<br/>(CONFIRMED/MODIFIED/<br/>REJECTED/SKIPPED)

    UpdateEntity --> CheckClarification: Loop back<br/>(check next clarification)

    Finalize --> [*]: END

    note right of Interrupted
        Graph execution PAUSED
        WebSocket can disconnect
        State persisted
    end note

    note right of WaitingForUser
        Can wait indefinitely
        User answers when ready
    end note

    note right of ProcessResponse
        Entity status updated
        Pending clarifications--
    end note
```

---

## Граф с типами сообщений WebSocket

```mermaid
graph TB
    subgraph Client["Client (Obsidian Plugin)"]
        C1[Connect WebSocket]
        C2[Send Note Data]
        C3[Receive Status Updates]
        C4[Show Clarification UI]
        C5[Send User Response]
        C6[Receive Completion]
    end

    subgraph Server["Server (LangGraph + WebSocket)"]
        S1[Accept Connection]
        S2[Start/Resume Thread]
        S3[Execute Graph]
        S4[Stream Events]
        S5[Handle Interrupt]
        S6[Wait for Response]
        S7[Resume Graph]
        S8[Send Completion]
    end

    subgraph Graph["LangGraph Nodes"]
        N1[extract_entities]
        N2[check_clarification]
        N3[request_clarification]
        N4[process_response]
        N5[finalize]
    end

    C1 --> S1
    C2 -->|file_path, content| S2
    S2 --> S3
    S3 --> N1
    N1 --> N2
    N2 --> N3
    N3 -->|interrupt| S5
    S5 --> S4
    S4 -->|processing_status| C3
    S4 -->|clarification_request| C4
    C4 --> C5
    C5 -->|user_response| S6
    S6 --> S7
    S7 --> N4
    N4 --> N2
    N2 --> N5
    N5 --> S8
    S8 -->|processing_complete| C6

    style N3 fill:#ff6b6b,stroke:#c92a2a,color:#fff
    style S5 fill:#ff6b6b,stroke:#c92a2a,color:#fff
    style C4 fill:#ffd43b,stroke:#fab005,color:#000
```

---

## Детальный flow с user_check статусами

```mermaid
flowchart TD
    Start([Client sends note]) --> Init[Initial State<br/>file_path, content]

    Init --> E1[Extract Entities Node]
    E1 --> E2[PipGraphManager.process_note]
    E2 --> E3[Mark entities as<br/>user_check='PENDING']

    E3 --> C1[Check Clarification Node]
    C1 --> C2{Any entities<br/>with PENDING?}

    C2 -->|YES| C3[Mark as<br/>AWAITING_INPUT]
    C2 -->|NO| F1[Finalize Node]

    C3 --> C4[Create clarification_request]
    C4 --> C5{Has pending<br/>clarifications?}

    C5 -->|YES| R1[Request Clarification Node]
    C5 -->|NO| F1

    R1 --> R2[interrupt clarification]
    R2 --> R3[⏸️ PAUSE EXECUTION]

    R3 -.->|Save state| DB[(SQLite DB<br/>sessions.db)]

    R3 -.->|Disconnect| D1[Client Disconnect]
    D1 -.->|Time passes| D2[1 hour / 1 day / 1 week]
    D2 -.->|Reconnect| D3[Client Reconnect]

    D3 -.->|Load state| DB
    D3 -.->|Send pending| WS1[WebSocket sends<br/>clarification_request]

    WS1 --> WS2[Client shows UI]
    WS2 --> WS3[User chooses action]

    WS3 -->|confirm| R4[▶️ RESUME with response]
    WS3 -->|modify| R4
    WS3 -->|reject| R4
    WS3 -->|skip| R4

    R4 --> P1[Process Response Node]

    P1 --> P2{User action?}

    P2 -->|confirm| P3[user_check='CONFIRMED']
    P2 -->|modify| P4[user_check='MODIFIED'<br/>+ apply changes]
    P2 -->|reject| P5[user_check='REJECTED']
    P2 -->|skip| P6[user_check='SKIPPED']

    P3 --> P7[Remove from pending_clarifications]
    P4 --> P7
    P5 --> P7
    P6 --> P7

    P7 --> C1

    F1 --> F2[Filter CONFIRMED & MODIFIED]
    F2 --> F3[Save to Neo4j<br/>via PipGraphManager]
    F3 --> F4[Send processing_complete]
    F4 --> End([END])

    style R3 fill:#ff6b6b,stroke:#c92a2a,color:#fff,stroke-width:3px
    style R4 fill:#51cf66,stroke:#2f9e44,color:#fff,stroke-width:3px
    style DB fill:#339af0,stroke:#1971c2,color:#fff
    style WS2 fill:#ffd43b,stroke:#fab005,color:#000
    style D1 fill:#adb5bd,stroke:#495057
    style D2 fill:#adb5bd,stroke:#495057
    style D3 fill:#adb5bd,stroke:#495057
```

---

## Циклический процесс clarifications

```mermaid
sequenceDiagram
    participant Client
    participant WebSocket
    participant Graph
    participant Node as request_clarification
    participant SQLite
    participant User

    Client->>WebSocket: Connect + send note
    WebSocket->>Graph: Start execution

    Graph->>Graph: extract_entities
    Note over Graph: Entities marked<br/>user_check='pending'

    Graph->>Graph: check_clarification
    Note over Graph: Create 3 clarifications<br/>Set current = first

    loop For each clarification
        Graph->>Node: request_clarification
        Node->>Node: interrupt(clarification)
        Node-->>SQLite: Save state
        Node-->>WebSocket: Return control
        WebSocket->>Client: Send clarification_request

        Client->>User: Show modal
        Note over User: User can disconnect here

        alt User disconnects
            Client--xWebSocket: Disconnect
            Note over SQLite: State persisted
            Note over User: 1 day passes...
            Client->>WebSocket: Reconnect
            WebSocket->>SQLite: Load state
            SQLite-->>WebSocket: Pending clarification
            WebSocket->>Client: Send pending request
        end

        User->>Client: Choose action (confirm/modify/reject/skip)
        Client->>WebSocket: Send response
        WebSocket->>Graph: Command(resume=response)
        Graph->>Graph: process_response
        Note over Graph: Update entity.user_check<br/>Remove from pending
        Graph->>Graph: check_clarification (loop back)
    end

    Graph->>Graph: finalize
    Graph->>WebSocket: Completion
    WebSocket->>Client: processing_complete
```

---

## Легенда

### Цвета нод

- 🟥 **Красный** (`#ff6b6b`) - INTERRUPT (pause execution)
- ▶️ **Зеленый** (`#51cf66`) - RESUME (continue execution)
- 💾 **Синий** (`#339af0`) - Persistent storage (SQLite)
- ⚠️ **Желтый** (`#ffd43b`) - Conditional decision / User interaction
- ⏸️ **Серый** (`#adb5bd`) - Client lifecycle events

### Типы соединений

- **Сплошная линия** (`-->`) - Прямой переход между нодами
- **Пунктирная линия** (`-.->`) - Асинхронные события (disconnect/reconnect/save)
- **Стрелка** в обе стороны - Цикл (loop back)

### Статусы user_check

1. `PENDING` - Извлечено, не показано пользователю
2. `AWAITING_INPUT` - Запрошено подтверждение, ждем ответа
3. `CONFIRMED` - Пользователь подтвердил
4. `MODIFIED` - Пользователь отредактировал
5. `REJECTED` - Пользователь отклонил
6. `SKIPPED` - Пользователь пропустил

---

## Использование

### Просмотр в VSCode

1. Установить расширение "Markdown Preview Mermaid Support"
2. Открыть файл в Preview режиме (Ctrl+Shift+V)

### Экспорт диаграмм

```bash
# Install mermaid-cli
npm install -g @mermaid-js/mermaid-cli

# Export to PNG
mmdc -i feedback_graph_v01.md -o graph.png

# Export to SVG
mmdc -i feedback_graph_v01.md -o graph.svg
```

### Online редактор

https://mermaid.live - для быстрого просмотра и редактирования

---

## См. также

- [user_check_mvp_plan.md](./user_check_mvp_plan.md) - Полный план MVP
- [state_serialization_details.md](./state_serialization_details.md) - Детали сериализации state
- [Session Management](./user_check_mvp_plan.md#session-management) - Управление сессиями

---

**Документ создан:** 2025-11-09
**Автор:** Claude Code
**Статус:** Ready for review
