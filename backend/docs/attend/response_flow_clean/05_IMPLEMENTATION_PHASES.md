# Фазы реализации MVP

**Дата создания:** 2025-11-17
**Статус:** План для реализации
**Версия:** 1.0

---

## Введение

Этот документ описывает **поэтапный план реализации MVP** системы многоуровневых подтверждений. Каждая фаза независима и доставляет работающую функциональность.

---

## Общая стратегия

### Принципы

1. **Инкрементальность**: Каждая фаза добавляет ценность
2. **Тестируемость**: После каждой фазы можно протестировать систему end-to-end
3. **Минимализм**: Только необходимые компоненты, без "gold plating"
4. **Гибкость**: Можно остановиться на любой фазе, если достигнут нужный результат

### Фазы

- **Phase 1**: UserCheckStatus nodes + базовый LangGraph workflow (2-3 недели)
- **Phase 2**: PARA containers + L1/L2 clarifications (2 недели)
- **Phase 3**: L3 entity confirmation + приоритизация (1-2 недели)
- **Phase 4** (опционально): Расширенные возможности (2 недели)

**Общая длительность MVP**: 5-7 недель

---

## Phase 1: UserCheckStatus Nodes + Базовый Workflow

### Цели

✅ Создать инфраструктуру для хранения статусов подтверждений
✅ Реализовать базовый LangGraph workflow с interrupt/resume
✅ Протестировать сохранение/восстановление состояния

### Ключевые компоненты

#### 1.1 Модели данных

**Файлы для создания/обновления:**
- `app/models/user_check.py` (новый файл)

**Что создать:**
```python
# app/models/user_check.py
class UserCheckStatus(BaseModel):
    id: str
    status: Literal["pending", "confirmed", "modified", "rejected", "skipped", "auto_confirmed"]
    confirmation_level: Literal["para_classification", "container_assignment", "entity", "attribute"]
    confidence: Optional[float]
    timestamp: datetime
    user_action: Optional[str]
    modified_fields: Optional[List[str]]
    modifications: Optional[str]
    user_comment: Optional[str]
    system_suggestion: Optional[str]
    auto_confirmed: bool
    skip_count: int

class FieldModification(BaseModel):
    field_name: str
    original_value: Optional[str]
    new_value: str
    timestamp: datetime
```

#### 1.2 Neo4j схема

**Что сделать:**
1. Создать migration script: `app/db/migrations/001_create_user_check_schema.py`
2. Создать индексы и constraints

**Cypher команды:**
```cypher
// Constraints
CREATE CONSTRAINT check_id_unique FOR (c:UserCheckStatus) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT check_status_exists FOR (c:UserCheckStatus) REQUIRE c.status IS NOT NULL;

// Indexes
CREATE INDEX check_status FOR (c:UserCheckStatus) ON (c.status);
CREATE INDEX check_timestamp FOR (c:UserCheckStatus) ON (c.timestamp);
CREATE INDEX check_status_timestamp FOR (c:UserCheckStatus) ON (c.status, c.timestamp);
```

#### 1.3 CRUD операции

**Файлы:**
- `app/crud/user_check_crud.py` (новый файл)

**Функции:**
```python
async def create_user_check(check: UserCheckStatus) -> str:
    """Создать новый UserCheckStatus node"""

async def get_current_check(entity_uuid: str) -> Optional[UserCheckStatus]:
    """Получить текущий статус сущности"""

async def get_check_history(entity_uuid: str) -> List[UserCheckStatus]:
    """Получить полную историю проверок"""

async def update_check_status(
    entity_uuid: str,
    new_check: UserCheckStatus
) -> UserCheckStatus:
    """Обновить статус (создает новый check, связывает с историей)"""
```

#### 1.4 Базовый LangGraph workflow

**Файлы:**
- `app/services/note_processing_workflow.py` (новый файл)

**Что создать:**
```python
# Состояние
class NoteProcessingState(TypedDict):
    file_path: str
    content: str
    entities: List[EntityNode]
    current_clarification: Optional[Dict]
    user_response: Optional[Dict]

# Узлы
async def extract_entities_node(state): ...
async def check_clarification_node(state): ...
async def request_clarification_node(state): ...
async def process_response_node(state): ...
async def finalize_node(state): ...

# Граф
workflow = StateGraph(NoteProcessingState)
workflow.add_node("extract_entities", extract_entities_node)
# ... добавить остальные узлы

# Компиляция
checkpointer = AsyncSqliteSaver.from_conn_string("checkpoints.db")
app = workflow.compile(checkpointer=checkpointer)
```

#### 1.5 WebSocket endpoint (базовый)

**Файлы:**
- `app/api/websockets/note_processing.py` (новый файл)

**Что создать:**
```python
@router.websocket("/ws/process")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    async for message in websocket.iter_json():
        if message["type"] == "process_note":
            await start_processing(message["file_path"], message["content"])

        elif message["type"] == "clarification_response":
            await resume_processing(message["file_path"], message["response"])
```

### Критерии готовности Phase 1

✅ UserCheckStatus ноды создаются в Neo4j
✅ LangGraph workflow запускается и останавливается на interrupt
✅ Состояние сохраняется в AsyncSqliteSaver
✅ После перезапуска приложения workflow можно возобновить
✅ Простой тест: отправить заметку → получить clarification → ответить → workflow завершается

### Риски

- **Сложность LangGraph**: Может потребоваться больше времени на изучение
- **Сериализация состояния**: PipGraphManager нельзя сериализовать напрямую

### Что НЕ делаем в Phase 1

- ❌ PARA классификация (L1/L2) — пока только заглушки
- ❌ Приоритизация — все вопросы одинаковы
- ❌ Auto-confirm логика
- ❌ UI для истории статусов

---

## Phase 2: PARA Containers + L1/L2 Clarifications

### Цели

✅ Реализовать PARA контейнеры (Project/Area/Resource) как отдельные ноды
✅ Добавить уровни L1 (PARA classification) и L2 (container assignment)
✅ Интегрировать с workflow

### Ключевые компоненты

#### 2.1 PARA модели

**Файлы:**
- `app/models/para_containers.py` (новый файл или расширить существующий)

**Что создать:**
```python
class Project(BaseModel):
    id: str
    name: str
    status: Literal["active", "completed", "archived", "on_hold"]
    deadline: Optional[date]
    goal: Optional[str]
    created_at: datetime
    team: Optional[List[str]]

class Area(BaseModel):
    id: str
    name: str
    goal: Optional[str]
    review_frequency: Optional[Literal["weekly", "monthly", "quarterly"]]
    active: bool

class Resource(BaseModel):
    id: str
    topic: str
    category: Optional[str]
    tags: Optional[List[str]]
```

#### 2.2 PARA CRUD операции

**Файлы:**
- `app/crud/para_crud.py` (новый файл)

**Функции:**
```python
async def create_project(project: Project) -> str:
    """Создать Project node"""

async def create_area(area: Area) -> str:
    """Создать Area node"""

async def create_resource(resource: Resource) -> str:
    """Создать Resource node"""

async def find_matching_containers(
    para_type: str,
    content: str
) -> List[Dict]:
    """Найти похожие контейнеры для заметки"""

async def link_note_to_container(
    note_path: str,
    container_id: str,
    container_type: str
):
    """Создать связь (Note)-[:IS_PART_OF]->(Container)"""
```

#### 2.3 PARA classification service

**Файлы:**
- `app/services/para_classification.py` (новый файл)

**Функции:**
```python
async def classify_para_type(content: str) -> tuple[str, float]:
    """
    Классифицировать заметку по PARA типу.
    Returns: (type, confidence)
    """
    # Можно использовать LLM или простые эвристики для MVP
    if "deadline" in content.lower():
        return ("Project", 0.80)
    elif "ongoing" in content.lower():
        return ("Area", 0.75)
    else:
        return ("Resource", 0.60)
```

#### 2.4 Расширение workflow

**Файлы:**
- `app/services/note_processing_workflow.py` (обновить)

**Что добавить:**

1. В `extract_entities_node`:
   ```python
   # Классифицировать заметку
   para_type, confidence = await classify_para_type(state["content"])
   return {
       "para_suggestion": (para_type, confidence),
       # ... остальное
   }
   ```

2. В `check_clarification_node`:
   ```python
   # Добавить L1 clarification
   if not state.get("para_classification_check"):
       clarifications.append({
           "level": "para_classification",
           "priority": 1,
           "suggested": state["para_suggestion"][0],
           "confidence": state["para_suggestion"][1]
       })

   # Добавить L2 clarification
   if state.get("para_classification_check") and not state.get("container_assignment_check"):
       suggestions = await find_matching_containers(...)
       clarifications.append({
           "level": "container_assignment",
           "priority": 2,
           "suggestions": suggestions
       })
   ```

3. В `process_response_node`:
   ```python
   # Обработка L1
   if clarification["level"] == "para_classification":
       check = create_para_classification_check(user_response)
       return {"para_classification_check": check}

   # Обработка L2
   elif clarification["level"] == "container_assignment":
       if user_response["action"] == "create_new":
           container_id = await create_project(...)
       else:
           container_id = user_response["selected_id"]

       await link_note_to_container(note_path, container_id, ...)
       check = create_container_assignment_check(...)
       return {"container_assignment_check": check}
   ```

### Критерии готовности Phase 2

✅ Project/Area/Resource ноды создаются в Neo4j
✅ Заметки связываются с контейнерами через `IS_PART_OF`
✅ L1 clarification (PARA type) работает
✅ L2 clarification (container assignment) работает
✅ Можно создать новый проект или выбрать существующий
✅ End-to-end тест: заметка → L1 question → L2 question → привязка к проекту

### Риски

- **Качество классификации**: Простые эвристики могут давать низкую точность
- **Поиск похожих контейнеров**: Требует embedding или full-text search

### Что НЕ делаем в Phase 2

- ❌ L3 (entity confirmation) — только структура PARA
- ❌ Сложные алгоритмы поиска похожих проектов
- ❌ Reclassification (изменение типа существующей заметки)

---

## Phase 3: L3 Entity Confirmation + Приоритизация

### Цели

✅ Реализовать L3 (entity confirmation)
✅ Добавить приоритизацию сущностей
✅ Реализовать auto-confirm логику

### Ключевые компоненты

#### 3.1 Приоритизация

**Файлы:**
- `app/services/clarification_helpers.py` (новый файл)

**Что создать:**
```python
ENTITY_PRIORITY = {
    'Project': 1,
    'Area': 1,
    'Person': 2,
    'Organization': 2,
    'Task': 3,
    'Decision': 3,
    'Idea': 4,
    'Source': 4,
    'Question': 5
}

def should_auto_confirm(entity_type: str, confidence: float) -> bool:
    """Определяет нужно ли автоподтверждение"""
    priority = ENTITY_PRIORITY.get(entity_type, 5)

    if confidence > 0.95 and priority >= 4:
        return True
    if confidence > 0.90 and priority >= 3:
        return True

    return False

def calculate_clarification_priority(clarification: Dict) -> float:
    """Рассчитывает приоритет вопроса"""
    level_weight = {
        "para_classification": 1,
        "container_assignment": 2,
        "entity": 10
    }

    score = level_weight[clarification["level"]]
    score += (1.0 - clarification.get("confidence", 0.5)) * 10

    if clarification["level"] == "entity":
        entity_priority = ENTITY_PRIORITY.get(clarification["entity_type"], 5)
        score += entity_priority

    return score
```

#### 3.2 L3 обработка в workflow

**Файлы:**
- `app/services/note_processing_workflow.py` (обновить)

**Что добавить:**

1. В `extract_entities_node`:
   ```python
   # Пометить сущности как pending
   for entity in entities:
       confidence = calculate_entity_confidence(entity)

       # Auto-confirm если критерии выполнены
       if should_auto_confirm(entity.labels[0], confidence):
           check = UserCheckStatus(
               status="auto_confirmed",
               confirmation_level="entity",
               confidence=confidence,
               auto_confirmed=True
           )
       else:
           check = UserCheckStatus(
               status="pending",
               confirmation_level="entity",
               confidence=confidence
           )

       await create_user_check_with_link(entity.uuid, check)
   ```

2. В `check_clarification_node`:
   ```python
   # Добавить L3 clarifications
   for entity in state["entities"]:
       current_check = await get_current_check(entity.uuid)

       if current_check.status == "pending":
           clarifications.append({
               "level": "entity_confirmation",
               "priority": ENTITY_PRIORITY[entity.labels[0]],
               "entity_uuid": entity.uuid,
               "entity_name": entity.name,
               "entity_type": entity.labels[0],
               "confidence": current_check.confidence
           })

   # Сортировать по приоритету
   clarifications.sort(key=calculate_clarification_priority)
   ```

3. В `process_response_node`:
   ```python
   elif clarification["level"] == "entity_confirmation":
       entity = find_entity(clarification["entity_uuid"])

       if user_response["action"] == "confirm":
           new_check = UserCheckStatus(
               status="confirmed",
               confirmation_level="entity",
               user_action="confirm"
           )

       elif user_response["action"] == "modify":
           modifications = []

           if "new_name" in user_response:
               entity.name = user_response["new_name"]
               modifications.append(FieldModification(
                   field_name="name",
                   original_value=original_name,
                   new_value=entity.name
               ))

           new_check = UserCheckStatus(
               status="modified",
               confirmation_level="entity",
               user_action="modify",
               modified_fields=[m.field_name for m in modifications],
               modifications=json.dumps([m.dict() for m in modifications])
           )

       await update_check_status(entity.uuid, new_check)
   ```

### Критерии готовности Phase 3

✅ L3 clarifications генерируются для всех pending сущностей
✅ Сущности сортируются по приоритету (Person выше Source)
✅ Auto-confirm работает для высокоуверенных сущностей
✅ Можно confirm/modify/reject/skip сущности
✅ История изменений сохраняется в modifications
✅ End-to-end тест: заметка с 5 сущностями → L1 → L2 → L3 (3 вопроса) → завершение

### Риски

- **Производительность**: Много сущностей = много вопросов
- **UX**: Пользователь устает от большого количества вопросов

### Что НЕ делаем в Phase 3

- ❌ L4 (attribute validation)
- ❌ Batch clarifications (показ нескольких вопросов сразу)
- ❌ Skip/defer механизм (делаем в Phase 4)

---

## Phase 4 (Опционально): Расширенные возможности

### Цели

✅ Добавить skip/defer механизм
✅ Улучшить UX (batch clarifications, keyboard shortcuts)
✅ Добавить аналитику и метрики

### Ключевые компоненты

#### 4.1 Skip/Defer

**Что добавить:**
```python
# В process_response_node
elif user_response["action"] == "skip":
    skip_count = current_check.skip_count + 1
    new_check = UserCheckStatus(
        status="skipped",
        confirmation_level="entity",
        skip_count=skip_count,
        user_comment=user_response.get("comment")
    )

elif user_response["action"] == "defer":
    new_check = UserCheckStatus(
        status="skipped",
        confirmation_level="entity",
        defer_until=user_response.get("defer_until"),
        defer_reason=user_response.get("reason")
    )
```

#### 4.2 Batch Clarifications

**Идея:** Показывать 3-5 похожих вопросов одновременно (например, все Person сущности).

**Реализация:**
```python
def group_clarifications_for_batch(clarifications: List[Dict]) -> List[List[Dict]]:
    """Группирует похожие вопросы для batch обработки"""
    batches = []
    current_batch = []

    for c in clarifications:
        if c["level"] == "entity_confirmation":
            if len(current_batch) < 5 and (
                not current_batch or current_batch[0]["entity_type"] == c["entity_type"]
            ):
                current_batch.append(c)
            else:
                batches.append(current_batch)
                current_batch = [c]
        else:
            batches.append([c])

    if current_batch:
        batches.append(current_batch)

    return batches
```

#### 4.3 Аналитика

**Запросы:**
```cypher
// Статистика по статусам
MATCH (c:UserCheckStatus {confirmation_level: 'entity'})
WHERE c.timestamp >= datetime() - duration({days: 7})
RETURN c.status, count(*) AS count

// Самые часто модифицируемые поля
MATCH (c:UserCheckStatus {status: 'modified'})
UNWIND c.modified_fields AS field
RETURN field, count(*) AS count
ORDER BY count DESC
LIMIT 10
```

### Критерии готовности Phase 4

✅ Skip/defer работает
✅ Batch clarifications реализованы
✅ Базовая аналитика доступна через API
✅ История статусов доступна для просмотра в UI

### Риски

- **Scope creep**: Легко увлечься дополнительными фичами

---

## Сводная таблица фаз

| Фаза | Длительность | Ключевые фичи | Критерий успеха |
|------|--------------|---------------|-----------------|
| **Phase 1** | 2-3 недели | UserCheckStatus nodes, LangGraph, interrupt/resume | Workflow сохраняется и восстанавливается |
| **Phase 2** | 2 недели | PARA containers, L1/L2 clarifications | Заметки привязываются к проектам |
| **Phase 3** | 1-2 недели | L3 entity confirmation, приоритизация, auto-confirm | Сущности подтверждаются с приоритетом |
| **Phase 4** | 2 недели | Skip/defer, batch, аналитика | Удобный UX, метрики работают |

**Итого:** 5-7 недель для полного MVP (без Phase 4 — 5 недель)

---

## Стратегия тестирования (минимальная для MVP)

### Phase 1

- ✅ Unit тесты: CRUD для UserCheckStatus
- ✅ Integration тест: LangGraph workflow с mock PipGraphManager
- ✅ E2E тест: Отправка заметки → interrupt → resume → завершение

### Phase 2

- ✅ Unit тесты: PARA CRUD операции
- ✅ Integration тест: L1/L2 workflow
- ✅ E2E тест: Заметка → PARA classification → container assignment

### Phase 3

- ✅ Unit тесты: Приоритизация, auto-confirm логика
- ✅ Integration тест: L3 workflow с modifications
- ✅ E2E тест: Полный цикл L1 → L2 → L3 с несколькими сущностями

---

## Следующие шаги после MVP

После завершения MVP (Phase 1-3) можно рассмотреть:

1. **Migration to Redis**: Заменить AsyncSqliteSaver на Redis для production
2. **L4 (Attribute Validation)**: Детальная проверка атрибутов
3. **ML-based classification**: Обучить модель на исправлениях пользователя
4. **Advanced analytics**: Dashboard с метриками и insights
5. **Reclassification**: UI для изменения классификации старых заметок
6. **Performance optimization**: Vectorный поиск для похожих контейнеров

---

**Готово!** Документация для MVP завершена. Следующий шаг — примеры кода в `examples/`.
