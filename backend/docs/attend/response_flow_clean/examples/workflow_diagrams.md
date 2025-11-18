%% ============================================================================
%% Mermaid диаграммы для MVP системы многоуровневых подтверждений
%% ============================================================================
%%
%% Этот файл содержит визуальные диаграммы для:
%% - LangGraph workflow
%% - Схема графа Neo4j
%% - История подтверждений
%% - Приоритизация уточнений
%%
%% Дата: 2025-11-17
%% Версия: 1.0
%%
%% Использование:
%%   Скопируйте нужную диаграмму в markdown-файл или используйте в
%%   инструментах, поддерживающих Mermaid (GitHub, GitLab, Obsidian и др.)
%%
%% ============================================================================


%% ============================================================================
%% 1. LANGGRAPH WORKFLOW (основной граф)
%% ============================================================================

graph TD
    START([START]) --> extract[extract_entities_node<br/>Извлечение сущностей из заметки]

    extract --> check[check_clarification_node<br/>Проверка необходимости уточнений]

    check --> should_continue{Есть ли<br/>pending clarifications?}

    should_continue -->|Да, есть вопросы| request[request_clarification_node<br/>🔴 INTERRUPT<br/>Запрос уточнения у пользователя]
    should_continue -->|Нет вопросов| finalize[finalize_node<br/>Сохранение в Neo4j]

    request --> |Пользователь ответил| process[process_response_node<br/>Обработка ответа]

    process --> check

    finalize --> END([END])

    style request fill:#ffc078,stroke:#f76707,stroke-width:2px
    style check fill:#74c0fc,stroke:#1971c2
    style finalize fill:#a9e34b,stroke:#5c940d
    style extract fill:#b197fc,stroke:#7950f2


%% ============================================================================
%% 2. СХЕМА ГРАФА NEO4J (общая структура)
%% ============================================================================

graph TB
    subgraph "PARA Containers"
        Project[Project<br/>id, name, deadline, status]
        Area[Area<br/>id, name, goal]
        Resource[Resource<br/>id, topic, category]
    end

    subgraph "Content"
        Note[Note<br/>path, para_type, created_at]
        Entity[EntityNode<br/>uuid, name, labels]
    end

    subgraph "User Checks"
        Check1[UserCheckStatus<br/>status: confirmed<br/>level: entity]
        Check2[UserCheckStatus<br/>status: pending<br/>level: entity]
        Check3[UserCheckStatus<br/>status: confirmed<br/>level: para_classification]
    end

    Note -->|IS_PART_OF| Project
    Note -->|IS_PART_OF| Area
    Note -->|IS_PART_OF| Resource
    Note -->|CONTAINS| Entity

    Entity -->|HAS_CHECK<br/>is_current: true| Check1
    Entity -->|HAS_CHECK<br/>is_current: false| Check2
    Note -->|HAS_CHECK<br/>is_current: true| Check3

    Check1 -->|NEXT| Check2

    style Project fill:#ffd43b,stroke:#fab005
    style Area fill:#74c0fc,stroke:#1971c2
    style Resource fill:#b197fc,stroke:#7950f2
    style Check1 fill:#a9e34b,stroke:#5c940d
    style Check2 fill:#ffa8a8,stroke:#f03e3e
    style Check3 fill:#a9e34b,stroke:#5c940d


%% ============================================================================
%% 3. ИСТОРИЯ ПОДТВЕРЖДЕНИЙ (цепочка NEXT)
%% ============================================================================

graph LR
    Entity[EntityNode:<br/>John Smith] -->|HAS_CHECK<br/>is_current: true| Current

    Current[UserCheckStatus<br/>status: confirmed<br/>timestamp: 12:05<br/>user_action: confirm] -->|NEXT| Previous
    Previous[UserCheckStatus<br/>status: skipped<br/>timestamp: 12:02<br/>user_action: skip] -->|NEXT| Older
    Older[UserCheckStatus<br/>status: pending<br/>timestamp: 12:00<br/>user_action: null]

    style Current fill:#a9e34b,stroke:#5c940d,stroke-width:2px
    style Previous fill:#ffc078,stroke:#f76707
    style Older fill:#ffa8a8,stroke:#f03e3e


%% ============================================================================
%% 4. ПРИМЕР ПОЛНОГО ГРАФА ДЛЯ ЗАМЕТКИ
%% ============================================================================

graph TB
    Note[Note:<br/>"meetings/sync.md"<br/>para_type: Project]

    Project[Project:<br/>"Q4 Marketing"<br/>deadline: 2024-12-31<br/>status: active]

    Person1[EntityNode:<br/>John Smith<br/>Person]
    Person2[EntityNode:<br/>Anna Petrova<br/>Person]
    Task1[EntityNode:<br/>Prepare slides<br/>Task]

    CheckNote[UserCheckStatus<br/>level: container_assignment<br/>status: confirmed]
    CheckP1[UserCheckStatus<br/>level: entity<br/>status: confirmed]
    CheckP2[UserCheckStatus<br/>level: entity<br/>status: modified]
    CheckT1[UserCheckStatus<br/>level: entity<br/>status: auto_confirmed]

    Note -->|IS_PART_OF| Project
    Note -->|CONTAINS| Person1
    Note -->|CONTAINS| Person2
    Note -->|CONTAINS| Task1

    Note -->|HAS_CHECK<br/>is_current: true| CheckNote
    Person1 -->|HAS_CHECK<br/>is_current: true| CheckP1
    Person2 -->|HAS_CHECK<br/>is_current: true| CheckP2
    Task1 -->|HAS_CHECK<br/>is_current: true| CheckT1

    Task1 -->|ASSIGNED_TO| Person2

    style Project fill:#ffd43b,stroke:#fab005
    style CheckNote fill:#a9e34b,stroke:#5c940d
    style CheckP1 fill:#a9e34b,stroke:#5c940d
    style CheckP2 fill:#74c0fc,stroke:#1971c2
    style CheckT1 fill:#d0bfff,stroke:#9775fa


%% ============================================================================
%% 5. ПРИОРИТИЗАЦИЯ УТОЧНЕНИЙ
%% ============================================================================

graph TD
    Start[Все pending clarifications] --> Sort[Сортировка по приоритету]

    Sort --> L1[Level 1: PARA Classification<br/>priority: 1-5]
    Sort --> L2[Level 2: Container Assignment<br/>priority: 6-10]
    Sort --> L3[Level 3: Entity Confirmation<br/>priority: 11-20]

    L3 --> SubL3[Сортировка внутри L3]

    SubL3 --> P1[Project/Area/Person<br/>priority: 1-2<br/>HIGHEST]
    SubL3 --> P2[Organization/Task<br/>priority: 3<br/>MEDIUM]
    SubL3 --> P3[Idea/Source<br/>priority: 4-5<br/>LOW]

    P3 --> AutoConfirm{confidence > 0.95?}
    AutoConfirm -->|Да| Auto[Auto-confirm]
    AutoConfirm -->|Нет| Ask[Спросить пользователя]

    style L1 fill:#ffd43b,stroke:#fab005
    style L2 fill:#74c0fc,stroke:#1971c2
    style L3 fill:#b197fc,stroke:#7950f2
    style P1 fill:#ff6b6b,stroke:#f03e3e
    style P2 fill:#ffc078,stroke:#f76707
    style P3 fill:#a9e34b,stroke:#5c940d
    style Auto fill:#d0bfff,stroke:#9775fa


%% ============================================================================
%% 6. МНОГОУРОВНЕВАЯ СИСТЕМА (ИЕРАРХИЯ)
%% ============================================================================

graph TD
    Note[Заметка] --> L1[Level 1: PARA Classification]
    L1 --> L2[Level 2: Container Assignment]
    L2 --> L3[Level 3: Entity Confirmation]
    L3 --> L4[Level 4: Attribute Validation<br/>НЕ В MVP]

    L1 -.->|Вопрос| Q1[Project? Area? Resource?]
    L2 -.->|Вопрос| Q2[Какой проект?<br/>Создать новый или выбрать?]
    L3 -.->|Вопрос| Q3[Подтвердить Person?<br/>Изменить имя?]
    L4 -.->|Вопрос| Q4[Email корректен?]

    style L1 fill:#ffd43b,stroke:#fab005
    style L2 fill:#74c0fc,stroke:#1971c2
    style L3 fill:#b197fc,stroke:#7950f2
    style L4 fill:#ffa8a8,stroke:#f03e3e,stroke-dasharray: 5 5
    style Q4 fill:#ffa8a8,stroke:#f03e3e,stroke-dasharray: 5 5


%% ============================================================================
%% 7. WEBSOCKET COMMUNICATION FLOW
%% ============================================================================

sequenceDiagram
    participant Client as Obsidian Plugin
    participant Server as FastAPI WebSocket
    participant LG as LangGraph Workflow
    participant Neo4j as Neo4j Database

    Client->>Server: process_note {file_path, content}
    Server->>LG: Start workflow (thread_id)

    LG->>LG: extract_entities_node
    LG->>LG: check_clarification_node
    LG->>LG: request_clarification_node (INTERRUPT)

    LG-->>Server: clarification_request
    Server-->>Client: L1: PARA Classification?

    Note over Client: Пользователь отвечает<br/>(может быть через 1 день)

    Client->>Server: clarification_response {choice: Project}
    Server->>LG: Resume workflow

    LG->>LG: process_response_node
    LG->>LG: check_clarification_node
    LG->>LG: request_clarification_node (INTERRUPT)

    LG-->>Server: clarification_request
    Server-->>Client: L2: Создать проект?

    Client->>Server: clarification_response {action: create_new}
    Server->>LG: Resume workflow

    LG->>LG: process_response_node
    LG->>Neo4j: Create Project node
    LG->>LG: check_clarification_node
    LG->>LG: finalize_node
    LG->>Neo4j: Save all entities

    LG-->>Server: workflow_complete
    Server-->>Client: processing_complete


%% ============================================================================
%% 8. STATE TRANSITIONS (UserCheckStatus)
%% ============================================================================

stateDiagram-v2
    [*] --> pending: Сущность извлечена

    pending --> confirmed: Пользователь подтвердил
    pending --> modified: Пользователь изменил
    pending --> rejected: Пользователь отклонил
    pending --> skipped: Пользователь пропустил
    pending --> auto_confirmed: Высокая уверенность

    skipped --> confirmed: Вернулись, подтвердили
    skipped --> modified: Вернулись, изменили
    skipped --> rejected: Вернулись, отклонили

    confirmed --> [*]
    modified --> [*]
    rejected --> [*]
    auto_confirmed --> [*]


%% ============================================================================
%% 9. ФАЗЫ РЕАЛИЗАЦИИ MVP
%% ============================================================================

gantt
    title Фазы реализации MVP (5-7 недель)
    dateFormat YYYY-MM-DD
    section Phase 1
    UserCheckStatus nodes           :p1_1, 2025-11-18, 10d
    Базовый LangGraph workflow      :p1_2, after p1_1, 7d
    WebSocket endpoint              :p1_3, after p1_2, 4d
    section Phase 2
    PARA containers models          :p2_1, after p1_3, 5d
    L1 PARA classification          :p2_2, after p2_1, 5d
    L2 Container assignment         :p2_3, after p2_2, 4d
    section Phase 3
    L3 Entity confirmation          :p3_1, after p2_3, 5d
    Приоритизация сущностей         :p3_2, after p3_1, 4d
    Auto-confirm логика             :p3_3, after p3_2, 3d
    section Phase 4 (optional)
    Skip/defer механизм             :p4_1, after p3_3, 5d
    Batch clarifications            :p4_2, after p4_1, 5d
    Аналитика                       :p4_3, after p4_2, 4d


%% ============================================================================
%% КОНЕЦ ФАЙЛА
%% ============================================================================
