# PipGraphManager Refactoring: Architecture Analysis

**Дата создания:** 2025-11-17
**Статус:** Architectural Analysis
**Версия:** 1.0

---

## Executive Summary

### Ключевой вывод

**Да, нужно добавить много новых методов в PipGraphManager.**

Текущая реализация имеет только **один монолитный метод `process_note()`**, который делает всё сразу: извлекает сущности, разрешает их, создаёт связи и сохраняет в Neo4j. Для полноценного LangGraph workflow с L1/L2/L3 подтверждениями нужны **17 гранулярных CRUD операций**, которые можно вызывать из разных узлов графа.

### Разделение ответственности

| Компонент | Ответственность |
|-----------|----------------|
| **LangGraph** | Оркестрация workflow, ветвление, interrupt/resume, управление состоянием, приоритизация вопросов |
| **PipGraphManager** | CRUD операции в Neo4j, извлечение сущностей (via Graphiti), создание UserCheckStatus nodes, управление PARA контейнерами |

### Текущее состояние архитектуры

**Оценка качества:** 6/10

✅ **Что работает:**
- LangGraph интеграция с interrupt/resume
- PipGraphManager существует и извлекает сущности
- Базовый MVP workflow функционирует

❌ **Что требует улучшения:**
- PipGraphManager монолитный (1 метод вместо 17)
- Нет гранулярных CRUD операций
- UserCheckStatus не реализован
- PARA контейнеры не создаются
- Нет методов для модификации сущностей

---

## 1. Текущее состояние PipGraphManager

### Файл: `app/services/pipgraph_manager.py`

### Существующие методы

**Единственный метод: `process_note()`** (строки 120-373)

```python
async def process_note(
    self,
    name: str,
    episode_body: str,
    source: EpisodeType,
    source_description: str,
    reference_time: datetime,
    group_id: Optional[str] = None,
    success_callback: Optional[Callable] = None,
    entity_types: Optional[dict] = None,
    excluded_entity_types: Optional[list] = None
) -> ProcessResult:
    """
    Обрабатывает заметку: извлекает сущности, разрешает дубликаты, сохраняет в Neo4j.

    Проблема: делает ВСЁ сразу, нет точек вмешательства для пользователя.
    """
```

### Что делает `process_note()`

1. **Создаёт эпизод** (EpisodicNode)
2. **Извлекает сущности** через Graphiti LLM (`extract_nodes()`)
3. **Разрешает дубликаты** (`resolve_extracted_nodes()`)
4. **Извлекает связи** (`extract_edges()`)
5. **Сохраняет в Neo4j** (`add_nodes_and_edges_bulk()`)

### Проблемы текущей архитектуры

❌ **Монолитность**: Невозможно выполнить отдельные операции
❌ **Нет intervention points**: Комментарии TODO указывают, где нужно спросить пользователя, но это не реализовано
❌ **Чёрный ящик**: Нельзя извлечь сущности БЕЗ сохранения в Neo4j
❌ **Нет CRUD**: Нельзя обновить отдельную сущность или создать UserCheckStatus
❌ **Нет истории**: Нет методов для работы с историей изменений

### Комментарии в коде (TODO intervention points)

```python
# Строки 269-271: После извлечения сущностей
# TODO: show user found entities for confirmation

# Строки 295-307: ГЛАВНАЯ ТОЧКА ВМЕШАТЕЛЬСТВА
# TODO: Спросить пользователя описания для новых сущностей

# Строки 329-331: После извлечения связей
# TODO: Handle orphaned notes
```

**Эти точки вмешательства НЕ реализованы** - это просто комментарии!

---

## 2. Текущее состояние LangGraph Workflow

### Файл: `app/services/note_workflow.py`

### Существующие узлы

#### 1. `extract_entities_node` (строки 42-94)

```python
async def extract_entities_node(state: NoteWorkflowState) -> dict:
    """Извлекает сущности через PipGraphManager.process_note()"""

    graphiti = await get_graphiti()
    pipgraph = PipGraphManager(graphiti)  # ← Создаётся заново в каждой node

    result = await pipgraph.process_note(...)  # ← Вызов монолитного метода

    # Сериализует сущности для хранения в state
    serialized_entities = [serialize_entity(e) for e in result.nodes]

    return {
        "entities": serialized_entities,
        "episode_uuid": result.episode.uuid,
        "needs_confirmation": len(result.nodes) > 0
    }
```

**Проблема:** Вызывает `process_note()`, который уже СОХРАНИЛ всё в Neo4j. Пользователь видит вопрос ПОСЛЕ того, как данные уже в базе!

#### 2. `ask_user_node` (строки 97-147)

```python
async def ask_user_node(state: NoteWorkflowState) -> dict:
    """Задаёт вопрос про ПЕРВУЮ сущность (MVP limitation)"""

    first_entity = state["entities"][0]  # ← Только первая сущность

    question = ClarificationQuestion(...)

    user_answer = interrupt(question.model_dump())  # ← INTERRUPT

    return {"pending_question": ..., "user_answer": user_answer}
```

**Ограничения MVP:**
- Только первая сущность
- Только L3 (entity confirmation)
- Нет L1 (PARA classification) и L2 (container assignment)

#### 3. `finalize_node` (строки 150-177)

```python
async def finalize_node(state: NoteWorkflowState) -> dict:
    """Финализирует обработку"""

    user_action = state.get("user_answer", {}).get("action", "unknown")

    # TODO: Сохранить UserCheckStatus node в Neo4j
    # TODO: Обновить сущность, если action = "modify"

    return {"status": "completed"}
```

**Проблема:** TODO комментарии не реализованы! Ответы пользователя просто логируются, но не применяются к графу.

### Структура workflow

```
START → extract_entities → check_needs_question
                              ↓                    ↓
                        (needs_confirmation)  (no questions)
                              ↓                    ↓
                          ask_user              finalize → END
                              ↓
                          finalize → END
```

### Ограничения текущего MVP

❌ Только L3 (entity confirmation)
❌ Только один вопрос (первая сущность)
❌ Ответы пользователя НЕ применяются к Neo4j
❌ UserCheckStatus nodes НЕ создаются
❌ PARA контейнеры НЕ создаются
❌ Нет приоритизации вопросов
❌ Нет auto-confirm логики

---

## 3. Разделение ответственности

### Что должен делать LangGraph (Orchestration Layer)

**Ответственность:**
1. ✅ Управление состоянием workflow (StateGraph)
2. ✅ Ветвление и условная логика (conditional_edges)
3. ✅ Interrupt/resume для пользовательского ввода
4. ✅ Persistence состояния (AsyncSqliteSaver)
5. ✅ Приоритизация вопросов (какой вопрос задать первым)
6. ✅ Последовательность L1 → L2 → L3
7. ✅ Auto-confirm логика (пропуск вопросов с высокой уверенностью)

**НЕ должен делать:**
- ❌ Прямые Cypher запросы
- ❌ Извлечение сущностей (делегирует PipGraphManager)
- ❌ Знание схемы Neo4j
- ❌ Построение Cypher запросов

**Пример LangGraph node:**

```python
async def process_response_node(state: NoteWorkflowState) -> dict:
    """Обрабатывает ответ пользователя - ОРКЕСТРАЦИЯ"""

    current_q = state["current_clarification"]
    user_response = state["user_response"]

    # Делегирует CRUD операции PipGraphManager
    pipgraph = get_pipgraph_manager()

    if current_q["level"] == "para_classification":
        # Делегирует сохранение UserCheckStatus
        await pipgraph.save_para_classification_check(
            note_path=state["file_path"],
            status="confirmed",
            original_suggestion=current_q["original"],
            user_choice=user_response["choice"],
            confidence=current_q["confidence"]
        )

    elif current_q["level"] == "entity_confirmation":
        if user_response["action"] == "modify":
            # Делегирует модификацию сущности
            await pipgraph.modify_entity_attributes(
                entity_uuid=current_q["entity_uuid"],
                changes=user_response["modifications"]
            )

        # Делегирует сохранение подтверждения
        await pipgraph.save_entity_confirmation_check(
            entity_uuid=current_q["entity_uuid"],
            status=user_response["action"],
            ...
        )

    return {"clarification_processed": True}
```

### Что должен делать PipGraphManager (CRUD Layer)

**Ответственность:**
1. ✅ Извлечение сущностей из текста (via Graphiti LLM)
2. ✅ CRUD операции с EntityNode
3. ✅ CRUD операции с UserCheckStatus
4. ✅ CRUD операции с PARA контейнерами (Project/Area/Resource)
5. ✅ Создание и обновление связей
6. ✅ Bulk операции для эффективности
7. ✅ Генерация embeddings (via Graphiti)
8. ✅ История изменений (NEXT chains)

**НЕ должен делать:**
- ❌ Оркестрация workflow
- ❌ Решения о том, когда спрашивать пользователя
- ❌ Persistence состояния workflow (это LangGraph)
- ❌ Приоритизация вопросов

**Пример метода PipGraphManager:**

```python
class PipGraphManager:
    """CRUD операции для Neo4j графа"""

    async def save_para_classification_check(
        self,
        note_path: str,
        status: str,
        original_suggestion: str,
        user_choice: str,
        confidence: float,
        user_comment: Optional[str] = None
    ) -> str:
        """
        Создаёт UserCheckStatus node для L1 подтверждения.

        Чистая CRUD операция - НЕ знает о workflow.
        """
        check_id = f"check_{uuid4().hex[:8]}"

        # Cypher query для создания node и relationship
        query = """
        MATCH (n:Note {path: $note_path})
        CREATE (check:UserCheckStatus {
            id: $check_id,
            status: $status,
            confirmation_level: 'para_classification',
            ...
        })
        CREATE (n)-[:HAS_CHECK {is_current: true}]->(check)
        RETURN check.id
        """

        # Выполняет query через Neo4j driver
        result = await self.driver.execute(query, params)
        return check_id
```

### Граница ответственности

```
┌─────────────────────────────────────────────────────────┐
│                    LangGraph Node                        │
│  (Оркестрация: что делать, когда, в каком порядке)      │
└────────────────────┬────────────────────────────────────┘
                     │ делегирует
                     ↓
┌─────────────────────────────────────────────────────────┐
│               PipGraphManager Method                     │
│     (CRUD: как сохранить, обновить, получить)           │
└────────────────────┬────────────────────────────────────┘
                     │ использует
                     ↓
┌─────────────────────────────────────────────────────────┐
│                  Neo4j Driver                            │
│          (Выполнение Cypher запросов)                    │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Пробелы в архитектуре

### Отсутствующие операции (17 методов)

#### L1: PARA Classification (3 метода)

1. ❌ `classify_para_type(content: str) -> tuple[str, float]`
   - LLM call для определения Project/Area/Resource/Archive
   - Возвращает (para_type, confidence)

2. ❌ `save_para_classification_check(note_path, status_data) -> str`
   - Создаёт UserCheckStatus с confirmation_level="para_classification"
   - Линкует к Note через [:HAS_CHECK {is_current: true}]

3. ❌ `update_note_para_type(note_path: str, para_type: str) -> bool`
   - Обновляет кэшированный para_type на Note node
   - Для быстрого фильтрования без joins

#### L2: Container Assignment (4 метода)

4. ❌ `find_similar_containers(note_content, para_type) -> List[dict]`
   - Поиск существующих Project/Area/Resource через embeddings
   - Возвращает candidates с confidence scores

5. ❌ `create_para_container(container_type, metadata) -> str`
   - Создаёт новый Project/Area/Resource node
   - Возвращает container_id

6. ❌ `link_note_to_container(note_path, container_id) -> bool`
   - Создаёт [:IS_PART_OF] relationship
   - Обновляет кэшированный container_id на Note

7. ❌ `save_container_assignment_check(note_path, status_data) -> str`
   - UserCheckStatus с confirmation_level="container_assignment"

#### L3: Entity Confirmation (5 методов)

8. ❌ `extract_entities_from_note(content) -> tuple[List[EntityNode], str]`
   - **КРИТИЧНО:** Извлекает сущности БЕЗ сохранения в Neo4j
   - Разбивает монолитный process_note() на части
   - Возвращает (entities, episode_uuid)

9. ❌ `save_entity_confirmation_check(entity_uuid, status_data) -> str`
   - UserCheckStatus с confirmation_level="entity"
   - Включает FieldModification если status="modified"

10. ❌ `modify_entity_attributes(entity_uuid, changes: dict) -> bool`
    - Применяет изменения пользователя к EntityNode
    - Пример: {"name": "John Smith", "role": "CEO"}

11. ❌ `reject_entity(entity_uuid: str) -> bool`
    - Отмечает сущность как rejected
    - Создаёт UserCheckStatus с status="rejected"

12. ❌ `get_entity_by_uuid(entity_uuid: str) -> Optional[EntityNode]`
    - Простой getter для деталей сущности

#### History Management (2 метода)

13. ❌ `update_check_status(entity_uuid, new_status_data) -> str`
    - Обновляет UserCheckStatus с сохранением истории
    - Шаги:
      1. Находит текущий [:HAS_CHECK {is_current: true}]
      2. Ставит is_current = false
      3. Создаёт новый UserCheckStatus
      4. Линкует через [:NEXT] chain
    - Возвращает new_check_id

14. ❌ `get_check_history(entity_uuid: str) -> List[dict]`
    - Проходит по [:NEXT] chain от current до oldest
    - Возвращает полную историю для аудита

#### Bulk Operations (1 метод)

15. ❌ `bulk_save_confirmed_entities(entities, episode_uuid, edges) -> bool`
    - Сохраняет только confirmed/modified сущности
    - Эффективнее, чем process_note() который сохраняет всё сразу
    - Использовать в finalize_node после подтверждений

#### Priority Helpers (2 метода)

16. ❌ `calculate_entity_priority(entity, confidence) -> int`
    - Возвращает priority score 1-5
    - На основе entity type (Person=2, Task=3, Question=5)
    - Используется LangGraph для сортировки вопросов

17. ❌ `should_auto_confirm(entity, confidence) -> bool`
    - Логика из документации:
      - confidence > 0.95 и priority >= 4 → True
      - confidence > 0.90 и priority >= 3 → True
    - Возвращает True если нужен auto-confirm

---

## 5. Предлагаемая архитектура PipGraphManager

### Полная структура класса

```python
class PipGraphManager:
    """
    CRUD операции для PipGraph workflow с поддержкой LangGraph.

    Ответственность:
    - Извлечение сущностей (via Graphiti)
    - Neo4j CRUD операции
    - UserCheckStatus management
    - PARA container management

    НЕ управляет:
    - Workflow orchestration (это LangGraph)
    - User interaction (это LangGraph nodes)
    """

    def __init__(self, graphiti: Graphiti):
        self.graphiti = graphiti
        self.driver = graphiti.driver
        self.clients = graphiti.clients
        self.embedder = graphiti.embedder

    # ========================================
    # L1: PARA Classification
    # ========================================

    async def classify_para_type(
        self,
        content: str,
        previous_episodes: Optional[List[EpisodicNode]] = None
    ) -> tuple[str, float]:
        """
        Классифицирует заметку по методу PARA через LLM.

        Args:
            content: Текст заметки
            previous_episodes: Предыдущие эпизоды для контекста

        Returns:
            (para_type, confidence) где:
            - para_type: "Project" | "Area" | "Resource" | "Archive"
            - confidence: 0.0-1.0

        Example:
            >>> para_type, conf = await manager.classify_para_type("Meeting notes about Q4 campaign")
            >>> print(para_type)  # "Project"
            >>> print(conf)       # 0.87
        """
        # LLM prompt с определениями PARA
        # Парсинг ответа
        # Возврат (type, confidence)
        pass

    async def save_para_classification_check(
        self,
        note_path: str,
        status: str,  # "confirmed" | "modified" | "rejected" | "skipped"
        original_suggestion: str,
        user_choice: str,
        confidence: float,
        user_comment: Optional[str] = None
    ) -> str:
        """
        Создаёт UserCheckStatus node для L1 подтверждения.

        Создаёт:
        - UserCheckStatus node с confirmation_level="para_classification"
        - [:HAS_CHECK {is_current: true}] связь к Note

        Args:
            note_path: Путь к заметке
            status: Статус подтверждения
            original_suggestion: Что предложила система
            user_choice: Что выбрал пользователь
            confidence: Уверенность LLM
            user_comment: Комментарий пользователя

        Returns:
            check_id: UUID созданного UserCheckStatus

        Example:
            >>> check_id = await manager.save_para_classification_check(
            ...     note_path="meetings/sync.md",
            ...     status="confirmed",
            ...     original_suggestion="Project",
            ...     user_choice="Project",
            ...     confidence=0.87
            ... )
        """
        # Cypher: CREATE UserCheckStatus node
        # Cypher: MATCH Note, CREATE [:HAS_CHECK] relationship
        # Return check_id
        pass

    async def update_note_para_type(
        self,
        note_path: str,
        para_type: str
    ) -> bool:
        """
        Обновляет кэшированный para_type атрибут на Note node.

        Это кэш для быстрого фильтрования. Source of truth -
        это [:IS_PART_OF] relationship к PARA контейнеру.

        Args:
            note_path: Путь к заметке
            para_type: "Project" | "Area" | "Resource" | "Archive"

        Returns:
            True если успешно
        """
        # Cypher: MATCH Note, SET para_type
        pass

    # ========================================
    # L2: Container Assignment
    # ========================================

    async def find_similar_containers(
        self,
        note_content: str,
        container_type: str,  # "Project" | "Area" | "Resource"
        limit: int = 5
    ) -> List[dict]:
        """
        Находит существующие PARA контейнеры, похожие на текст заметки.

        Использует semantic similarity (embeddings) для предложения контейнеров.

        Args:
            note_content: Текст заметки
            container_type: Тип контейнера для поиска
            limit: Максимум результатов

        Returns:
            List[{
                "id": str,
                "name": str,
                "confidence": float,
                "metadata": dict  # deadline, goal, etc.
            }]

        Example:
            >>> containers = await manager.find_similar_containers(
            ...     "Marketing campaign Q4",
            ...     "Project",
            ...     limit=3
            ... )
            >>> print(containers[0]["name"])  # "Q4 Marketing Campaign"
        """
        # Generate embedding для note content
        # Search для похожих Project/Area/Resource nodes
        # Return sorted by similarity
        pass

    async def create_para_container(
        self,
        container_type: str,
        name: str,
        metadata: dict
    ) -> str:
        """
        Создаёт новый Project/Area/Resource node.

        Args:
            container_type: "Project" | "Area" | "Resource"
            name: Название контейнера
            metadata: {
                "deadline": date,      # для Project
                "goal": str,
                "status": str,
                ...
            }

        Returns:
            container_id: UUID созданного контейнера

        Example:
            >>> container_id = await manager.create_para_container(
            ...     "Project",
            ...     "Q4 Marketing Campaign",
            ...     {"deadline": "2024-12-31", "status": "active"}
            ... )
        """
        # Cypher: CREATE (p:Project {...}) или (a:Area {...})
        # Generate UUID
        # Return container_id
        pass

    async def link_note_to_container(
        self,
        note_path: str,
        container_id: str,
        container_type: str
    ) -> bool:
        """
        Создаёт [:IS_PART_OF] relationship между Note и PARA container.

        Также обновляет кэшированный container_id на Note.

        Args:
            note_path: Путь к заметке
            container_id: UUID контейнера
            container_type: "Project" | "Area" | "Resource"

        Returns:
            True если успешно
        """
        # Cypher: MATCH Note, MATCH Container
        # CREATE [:IS_PART_OF {assigned_at: datetime()}]
        # SET note.project_id = container_id (cache)
        pass

    async def save_container_assignment_check(
        self,
        note_path: str,
        status: str,
        action: str,  # "create_new" | "link_existing"
        container_type: str,
        container_id: str,
        container_name: str,
        created_new: bool = False,
        container_metadata: Optional[dict] = None
    ) -> str:
        """
        Создаёт UserCheckStatus для L2 подтверждения.

        Returns:
            check_id: UUID созданного UserCheckStatus
        """
        # Cypher: CREATE UserCheckStatus с confirmation_level="container_assignment"
        pass

    # ========================================
    # L3: Entity Confirmation
    # ========================================

    async def extract_entities_from_note(
        self,
        note_content: str,
        note_name: str,
        reference_time: datetime,
        source: EpisodeType = EpisodeType.text,
        group_id: Optional[str] = None,
        entity_types: Optional[dict] = None,
        excluded_entity_types: Optional[list] = None
    ) -> tuple[List[EntityNode], str]:
        """
        Извлекает сущности БЕЗ сохранения в Neo4j.

        Это ГЛАВНАЯ ТОЧКА ВМЕШАТЕЛЬСТВА из process_note().
        Вместо немедленного сохранения возвращает сущности для просмотра.

        Args:
            note_content: Текст заметки
            note_name: Название заметки
            reference_time: Время создания
            source: Тип источника (text, audio, etc.)
            group_id: ID группы эпизодов
            entity_types: Разрешённые типы сущностей
            excluded_entity_types: Исключённые типы

        Returns:
            (entities, episode_uuid) где:
            - entities: List[EntityNode] для проверки пользователем
            - episode_uuid: UUID созданного эпизода

        Example:
            >>> entities, ep_uuid = await manager.extract_entities_from_note(
            ...     "Met with John Smith to discuss Q4 project",
            ...     "meetings/sync.md",
            ...     datetime.now()
            ... )
            >>> print(len(entities))  # 2 (John Smith, Q4 project)
        """
        # Create EpisodicNode
        # Call extract_nodes()
        # Call resolve_extracted_nodes()
        # НЕ вызываем add_nodes_and_edges_bulk() пока!
        # Return entities для LangGraph
        pass

    async def save_entity_confirmation_check(
        self,
        entity_uuid: str,
        status: str,  # "confirmed" | "modified" | "rejected" | "skipped"
        user_action: str,
        confidence: float,
        modified_fields: Optional[List[str]] = None,
        modifications: Optional[List[dict]] = None,  # List[FieldModification]
        user_comment: Optional[str] = None,
        system_suggestion: Optional[str] = None
    ) -> str:
        """
        Создаёт UserCheckStatus для entity confirmation.

        Если status="modified", включает modifications JSON.

        Args:
            entity_uuid: UUID сущности
            status: Статус подтверждения
            user_action: Действие пользователя
            confidence: Уверенность LLM
            modified_fields: Список изменённых полей
            modifications: List[FieldModification] objects
            user_comment: Комментарий
            system_suggestion: Что предложила система

        Returns:
            check_id: UUID созданного UserCheckStatus
        """
        # Cypher: CREATE UserCheckStatus с confirmation_level="entity"
        # Если modifications: serialize FieldModification list to JSON
        # CREATE [:HAS_CHECK {is_current: true}] to EntityNode
        pass

    async def modify_entity_attributes(
        self,
        entity_uuid: str,
        changes: dict
    ) -> bool:
        """
        Применяет модификации пользователя к EntityNode.

        Args:
            entity_uuid: UUID сущности
            changes: {"name": "John Smith", "role": "CEO", ...}

        Returns:
            True если успешно

        Example:
            >>> await manager.modify_entity_attributes(
            ...     "ent_123",
            ...     {"name": "John K. Smith", "role": "CEO"}
            ... )
        """
        # Cypher: MATCH EntityNode
        # SET entity.name = ..., entity.attributes.role = ...
        pass

    async def reject_entity(
        self,
        entity_uuid: str
    ) -> bool:
        """
        Отмечает сущность как rejected.

        Стратегия TBD: удалить node или просто установить статус?
        Для MVP: создаём rejected UserCheckStatus.

        Args:
            entity_uuid: UUID сущности

        Returns:
            True если успешно
        """
        # Create UserCheckStatus с status="rejected"
        # Optional: DELETE entity если нужно
        pass

    async def get_entity_by_uuid(
        self,
        entity_uuid: str
    ) -> Optional[EntityNode]:
        """
        Простой getter для деталей сущности.

        Args:
            entity_uuid: UUID сущности

        Returns:
            EntityNode или None если не найдена
        """
        # Cypher: MATCH EntityNode WHERE uuid = ...
        pass

    # ========================================
    # History Management
    # ========================================

    async def update_check_status(
        self,
        entity_or_note_uuid: str,
        new_status_data: dict
    ) -> str:
        """
        Обновляет UserCheckStatus с сохранением истории.

        Шаги:
        1. Находит текущий [:HAS_CHECK {is_current: true}] relationship
        2. Устанавливает is_current = false
        3. Создаёт новый UserCheckStatus node
        4. Создаёт [:HAS_CHECK {is_current: true}] к новому node
        5. Создаёт [:NEXT] link от нового к старому

        Args:
            entity_or_note_uuid: UUID сущности или заметки
            new_status_data: Данные для нового статуса

        Returns:
            new_check_id: UUID нового UserCheckStatus
        """
        # Cypher transaction (все шаги атомарно)
        pass

    async def get_check_history(
        self,
        entity_uuid: str
    ) -> List[dict]:
        """
        Получает полную историю UserCheckStatus для сущности.

        Проходит по [:NEXT] chain от current до oldest.

        Args:
            entity_uuid: UUID сущности

        Returns:
            List[UserCheckStatus dicts], сначала новые
        """
        # Cypher: MATCH path с [:NEXT*0..]
        # Return ordered by timestamp DESC
        pass

    # ========================================
    # Bulk Operations
    # ========================================

    async def bulk_save_confirmed_entities(
        self,
        entities: List[EntityNode],
        episode_uuid: str,
        entity_edges: List[EntityEdge]
    ) -> bool:
        """
        Сохраняет только confirmed/modified сущности в Neo4j.

        Эффективнее чем process_note() который сохраняет всё сразу.
        Использовать в finalize_node после подтверждений пользователя.

        Args:
            entities: Только подтверждённые сущности
            episode_uuid: UUID эпизода
            entity_edges: Связи между сущностями

        Returns:
            True если успешно
        """
        # Filter entities to only confirmed/modified
        # Call Graphiti's add_nodes_and_edges_bulk()
        pass

    # ========================================
    # Priority Helpers
    # ========================================

    def calculate_entity_priority(
        self,
        entity: EntityNode,
        confidence: float
    ) -> int:
        """
        Вычисляет priority score для сущности.

        На основе:
        - Entity type (Person=2, Task=3, Question=5)
        - Confidence (низкая confidence = выше priority)

        Args:
            entity: Сущность для оценки
            confidence: Уверенность LLM

        Returns:
            1-5 где 1 = highest priority
        """
        # ENTITY_PRIORITY map из документации
        # Adjust for confidence
        pass

    def should_auto_confirm(
        self,
        entity: EntityNode,
        confidence: float
    ) -> bool:
        """
        Определяет, нужно ли auto-confirm сущность.

        Логика из документации:
        - confidence > 0.95 и priority >= 4 → True
        - confidence > 0.90 и priority >= 3 → True

        Args:
            entity: Сущность для проверки
            confidence: Уверенность LLM

        Returns:
            True если нужен auto-confirm
        """
        # Calculate priority
        # Apply threshold logic
        pass

    # ========================================
    # Existing Method (Legacy)
    # ========================================

    async def process_note(self, ...):
        """
        LEGACY: Полная обработка заметки без вмешательства.

        Для MVP workflow предпочтительнее использовать:
        - extract_entities_from_note() для извлечения
        - bulk_save_confirmed_entities() для сохранения

        Этот метод может быть deprecated в будущих версиях.
        """
        # Сохранить существующую реализацию для backward compatibility
        pass
```

---

## 6. Примеры использования

### Пример 1: L1 PARA Classification в LangGraph

```python
# В node LangGraph
async def classify_para_node(state: NoteWorkflowState) -> dict:
    """L1: Классификация заметки по PARA"""

    pipgraph = get_pipgraph_manager()

    # Делегируем классификацию PipGraphManager
    para_type, confidence = await pipgraph.classify_para_type(
        content=state["content"]
    )

    return {
        "para_classification": para_type,
        "para_confidence": confidence,
        "needs_para_confirmation": confidence < 0.85  # Спросить если неуверенны
    }
```

### Пример 2: Сохранение UserCheckStatus

```python
# В process_response_node
async def process_response_node(state: NoteWorkflowState) -> dict:
    """Обрабатывает ответ пользователя"""

    pipgraph = get_pipgraph_manager()
    current_q = state["current_clarification"]
    user_resp = state["user_response"]

    if current_q["level"] == "para_classification":
        # Сохраняем подтверждение L1
        check_id = await pipgraph.save_para_classification_check(
            note_path=state["file_path"],
            status="confirmed" if user_resp["action"] == "confirm" else "modified",
            original_suggestion=current_q["original_suggestion"],
            user_choice=user_resp.get("choice", current_q["original_suggestion"]),
            confidence=current_q["confidence"],
            user_comment=user_resp.get("comment")
        )

        # Обновляем кэшированный тип
        if user_resp["action"] != "reject":
            await pipgraph.update_note_para_type(
                note_path=state["file_path"],
                para_type=user_resp["choice"]
            )

    return {"clarification_processed": True, "check_id": check_id}
```

### Пример 3: Извлечение сущностей БЕЗ сохранения

```python
# В extract_entities_node
async def extract_entities_node(state: NoteWorkflowState) -> dict:
    """L3: Извлекает сущности для проверки"""

    pipgraph = get_pipgraph_manager()

    # НОВЫЙ метод - НЕ сохраняет в Neo4j сразу!
    entities, episode_uuid = await pipgraph.extract_entities_from_note(
        note_content=state["content"],
        note_name=state["file_path"],
        reference_time=datetime.now(timezone.utc)
    )

    # Вычисляем приоритеты для каждой сущности
    entities_with_priority = []
    for entity in entities:
        priority = pipgraph.calculate_entity_priority(entity, 0.85)
        auto_confirm = pipgraph.should_auto_confirm(entity, 0.85)

        entities_with_priority.append({
            "entity": serialize_entity(entity),
            "priority": priority,
            "auto_confirm": auto_confirm
        })

    # Фильтруем auto-confirmed сущности
    needs_confirmation = [
        e for e in entities_with_priority
        if not e["auto_confirm"]
    ]

    return {
        "entities": entities_with_priority,
        "episode_uuid": episode_uuid,
        "pending_clarifications": needs_confirmation  # Только те, что нужно спросить
    }
```

### Пример 4: Финализация с сохранением только подтверждённых

```python
# В finalize_node
async def finalize_node(state: NoteWorkflowState) -> dict:
    """Сохраняет подтверждённые сущности в Neo4j"""

    pipgraph = get_pipgraph_manager()

    # Собираем только confirmed/modified сущности
    confirmed_entities = []
    for entity_data in state["entities"]:
        entity = deserialize_entity(entity_data["entity"])

        # Проверяем статус подтверждения
        if entity_data.get("confirmation_status") in ["confirmed", "modified"]:
            confirmed_entities.append(entity)

    # НОВЫЙ метод - сохраняет только выбранные сущности
    success = await pipgraph.bulk_save_confirmed_entities(
        entities=confirmed_entities,
        episode_uuid=state["episode_uuid"],
        entity_edges=state.get("entity_edges", [])
    )

    return {
        "status": "completed" if success else "error",
        "processing_completed_at": datetime.now(timezone.utc).isoformat()
    }
```

---

## 7. План рефакторинга

### Фаза 1: Рефакторинг PipGraphManager (3-5 дней)

**Цель:** Разбить монолитный `process_note()` на гранулярные CRUD методы

**Задачи:**

1. **День 1: Извлечение сущностей**
   - Создать `extract_entities_from_note()` из `process_note()`
   - Вернуть entities БЕЗ сохранения в Neo4j
   - Unit tests

2. **День 2: L1 PARA операции**
   - `classify_para_type()` - LLM call
   - `save_para_classification_check()` - UserCheckStatus
   - `update_note_para_type()` - cache update
   - Unit tests

3. **День 3: L3 Entity операции**
   - `save_entity_confirmation_check()`
   - `modify_entity_attributes()`
   - `reject_entity()`
   - `get_entity_by_uuid()`
   - Unit tests

4. **День 4: L2 Container операции**
   - `find_similar_containers()` - embeddings search
   - `create_para_container()`
   - `link_note_to_container()`
   - `save_container_assignment_check()`
   - Unit tests

5. **День 5: History + Bulk + Helpers**
   - `update_check_status()` - NEXT chain
   - `get_check_history()`
   - `bulk_save_confirmed_entities()`
   - `calculate_entity_priority()` - pure function
   - `should_auto_confirm()` - pure function
   - Unit tests
   - Integration tests

**Итого:** 17 новых методов за 5 дней

**Backward Compatibility:**
- Сохранить `process_note()` как legacy метод
- Пометить `@deprecated` в документации
- Обновить существующий код постепенно

### Фаза 2: Расширение LangGraph Workflow (5-7 дней)

**Цель:** Добавить L1/L2 уровни и приоритизацию

**Задачи:**

1. **Дни 1-2: L1 PARA Classification**
   - Добавить `classify_para_node`
   - Обновить `NoteWorkflowState` для L1 полей
   - Добавить conditional edge для L1 confirmation
   - E2E тест L1

2. **Дни 3-4: L2 Container Assignment**
   - Добавить `find_containers_node`
   - Добавить `assign_container_node`
   - Обновить state для L2 полей
   - E2E тест L2

3. **Дни 5-6: Приоритизация и Auto-confirm**
   - Добавить `check_clarification_node` с сортировкой
   - Интегрировать `should_auto_confirm()` logic
   - Обновить `process_response_node` для всех уровней
   - E2E тест полного flow L1→L2→L3

4. **День 7: Финализация**
   - Обновить `finalize_node` использовать `bulk_save_confirmed_entities()`
   - Интеграционные тесты
   - Performance testing

**Итого:** Полный L1/L2/L3 workflow за 7 дней

### Фаза 3: CRUD Layer Expansion (опционально, 2-3 дня)

**Цель:** Переместить низкоуровневые Neo4j операции из PipGraphManager в CRUD layer

**Задачи:**

1. **День 1: CRUD инфраструктура**
   - Создать Neo4j session context manager
   - Добавить Cypher query builders
   - Transaction management

2. **День 2: Рефакторинг PipGraphManager**
   - Переместить Cypher queries в CRUD layer
   - PipGraphManager вызывает CRUD функции
   - Unit tests для CRUD layer

3. **День 3: Integration**
   - E2E тесты с новым CRUD layer
   - Performance comparison

**Опционально** - можно оставить в PipGraphManager для MVP

---

## 8. Быстрые победы (Quick Wins)

### Quick Win 1: Извлечение без сохранения (1 день)

**Изменения:**
- Рефакторить `process_note()` → `extract_entities_from_note()`
- Вернуть entities до bulk save
- Обновить `extract_entities_node` использовать новый метод

**Ценность:**
- Пользователь видит сущности ДО сохранения в Neo4j
- Можно протестировать извлечение отдельно от сохранения

### Quick Win 2: UserCheckStatus creation (2 дня)

**Изменения:**
- Добавить только `save_entity_confirmation_check()`
- Обновить `finalize_node` для сохранения статусов
- Создать UserCheckStatus history в Neo4j

**Ценность:**
- История подтверждений пользователя в графе
- Аудит trail для всех решений

### Quick Win 3: Modify action (1 день)

**Изменения:**
- Добавить `modify_entity_attributes()`
- Обработать action="modify" в `process_response_node`
- Применить изменения к EntityNode

**Ценность:**
- Пользователь может исправлять имена/атрибуты сущностей
- FieldModification records в UserCheckStatus

**Итого:** 4 дня для значительного улучшения MVP без полного L1/L2

---

## 9. Метрики успеха

### Архитектурные метрики

✅ **Разделение ответственности:**
- LangGraph nodes < 50 строк каждая (только оркестрация)
- PipGraphManager методы < 100 строк каждая (чистый CRUD)
- Нет Cypher запросов в LangGraph nodes

✅ **Покрытие тестами:**
- Unit tests для каждого PipGraphManager метода (>90% coverage)
- Integration tests для каждого LangGraph node
- E2E tests для L1→L2→L3 flow

✅ **Функциональность:**
- Все 17 методов PipGraphManager реализованы
- L1/L2/L3 workflow работает end-to-end
- UserCheckStatus nodes создаются для всех подтверждений
- PARA containers создаются и линкуются
- History chain работает (NEXT relationships)

### Производительность

✅ **Efficiency:**
- Bulk operations используются вместо individual saves
- Embeddings генерируются batch'ами
- Neo4j connections pooled

✅ **User Experience:**
- Interrupt latency < 1 секунда
- Resume latency < 500ms
- Auto-confirm работает для >50% high-confidence entities

---

## 10. Рекомендации

### Критический путь для MVP

1. **Рефакторинг PipGraphManager** (3-5 дней) ← НАЧАТЬ ЗДЕСЬ
2. **Расширение LangGraph workflow** (5-7 дней)
3. **E2E тестирование** (2-3 дня)
4. **Документация** (1 день)

**Всего:** 11-16 дней для полной L1/L2/L3 реализации

### Альтернативный путь (Quick Wins First)

1. **Extract entities without saving** (1 день)
2. **UserCheckStatus creation** (2 дня)
3. **Modify action** (1 день)
4. **E2E тест базового flow** (1 день)

**Всего:** 5 дней для значительного улучшения текущего MVP

Затем можно добавлять L1/L2 постепенно.

### Оценка качества архитектуры

**Текущее состояние:** 6/10
- ✅ LangGraph интеграция работает
- ✅ PipGraphManager существует
- ❌ PipGraphManager монолитный
- ❌ Нет гранулярных CRUD
- ❌ UserCheckStatus не реализован

**Целевое состояние:** 9/10
- ✅ Гранулярные CRUD методы
- ✅ Полный L1/L2/L3 workflow
- ✅ UserCheckStatus history
- ✅ PARA containers
- ✅ Чёткое разделение ответственности

---

## Заключение

**Архитектура звучная, но неполная.**

MVP имеет правильную структуру (LangGraph для оркестрации, PipGraphManager для CRUD), но **PipGraphManager нужно рефакторить** от одного монолитного метода "делай всё" к **15-17 гранулярным CRUD операциям**.

После рефакторинга LangGraph workflow можно расширить для поддержки полной системы подтверждений L1/L2/L3 с историей UserCheckStatus.

**Ключевая мысль:** PipGraphManager должен быть **набором инструментов CRUD операций**, а не единственным методом `process_note()` как чёрный ящик. LangGraph nodes вызывают эти операции по мере необходимости для пошагового построения workflow.

---

**Статус:** Готово к имплементации
**Следующий шаг:** Начать Фазу 1 - Рефакторинг PipGraphManager
**Документ обновлён:** 2025-11-17
