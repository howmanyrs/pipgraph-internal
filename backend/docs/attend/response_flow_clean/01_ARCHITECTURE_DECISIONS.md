# Одобренные архитектурные решения

**Дата создания:** 2025-11-17
**Статус:** Утверждено для реализации
**Версия:** 1.0

---

## Введение

Этот документ описывает **одобренные архитектурные решения** для MVP-системы многоуровневых подтверждений. Все решения прошли обсуждение и были утверждены для реализации.

Альтернативные подходы и отклоненные варианты не включены — см. исходную документацию в `response_flow/` для деталей.

---

## Решение 1: UserCheck Status как отдельные ноды

### Суть решения

**Вариант 2: "Нода Статуса"** — каждое событие подтверждения пользователя хранится как **отдельная нода** `(:UserCheckStatus)` в Neo4j.

### Статус

✅ **ОДОБРЕНО**

Цитата пользователя из `response_to_user_check_granularity_proposal.md`:
> "Спасибо, Вариант 2: 'Нода Статуса' - это то что нужно в данный момент!"

### Структура

```cypher
// Сущность и текущий статус
(entity:EntityNode)-[:HAS_CHECK {is_current: true}]->(current:UserCheckStatus)

// История изменений
(current)-[:NEXT]->(previous:UserCheckStatus)
(previous)-[:NEXT]->(older:UserCheckStatus)
```

**Ключевые свойства:**
- `is_current: true` на связи `[:HAS_CHECK]` — указывает актуальный статус
- Цепочка `[:NEXT]` — сохраняет полную историю действий пользователя
- Каждая нода `UserCheckStatus` содержит полный snapshot состояния

### Почему это решение

#### ✅ Преимущества

1. **Производительность запросов**
   - Все поля индексируемы напрямую
   - Запросы типа "все pending статусы" работают мгновенно
   - Не требуется разбор JSON на уровне БД

2. **Полная история (Audit Trail)**
   - Каждое действие пользователя сохранено как отдельная нода
   - Можно отследить всю историю изменений: `pending → skipped → confirmed`
   - Критично для обучения ML-моделей на исправлениях пользователя

3. **Гибкость аналитики**
   - Легко ответить на вопросы:
     - "Какие типы сущностей чаще всего пропускают?"
     - "Как часто система ошибается в предложениях?"
     - "Какие поля чаще всего корректируются?"
   - Агрегирующие запросы работают эффективно

4. **Графовая модель**
   - Соответствует философии Neo4j: метаданные = отдельные ноды
   - Связи `HAS_CHECK`, `NEXT` семантически выразительны
   - Масштабируется без изменения схемы

#### ❌ Отклоненные альтернативы

**Вариант 0**: Хранение в атрибутах (JSON-объект `user_check`)
- Проблема: Neo4j не индексирует вложенные JSON-поля
- Проблема: Нет истории статусов
- Проблема: Сложные аналитические запросы

**Вариант 1**: Гибридный подход (ключевые поля + JSON)
- Проблема: Частично решает производительность, но не историю
- Проблема: Негибко — каждое новое поле требует изменения схемы

**Вариант 3**: Типизированные отношения (`[:CONFIRMED]`, `[:REJECTED]`)
- Проблема: Потеря истории при смене статуса
- Проблема: Перегрузка типами отношений

### Источники

- `response_to_user_check_granularity_proposal.md` (раздел "Вариант 2")
- `response_to_storage_architecture.md` (детальная спецификация)

---

## Решение 2: PARA entities как отдельные ноды

### Суть решения

Высокоуровневые сущности PARA (Project, Area, Resource) хранятся как **отдельные ноды** в Neo4j, а не как атрибуты заметки.

### Статус

✅ **ОДОБРЕНО**

Рекомендация из `user_check_granularity_proposal.md` (раздел 4.5):
> "### 4.5 Рекомендация: Вариант A (Отдельные ноды)"
>
> **Обоснование:**
> 1. Соответствует архитектуре из PARA_TYPES_ARCHITECTURE.md
> 2. Гибкость и масштабируемость
> 3. Целостность данных
> 4. Мощные графовые запросы

### Структура

```cypher
// PARA контейнер
(p:Project {
    id: "proj_123",
    name: "Q4 Marketing Campaign",
    status: "active",
    deadline: "2024-12-31",
    goal: "Increase signups by 20%"
})

// Заметка связана с проектом
(n:Note {
    path: "meetings/sync.md",
    para_type: "Project",     // Кешированный тип (для быстрых фильтров)
    project_id: "proj_123"     // Ссылка на контейнер
})

// Основная связь
(n)-[:IS_PART_OF]->(p)
```

**Hybrid подход:**
- Атрибуты `para_type` и `project_id` на заметке — для быстрых фильтров без JOIN
- Нода `Project` — единственный источник истины для метаданных
- Связь `IS_PART_OF` — семантически значимая

### Почему это решение

#### ✅ Преимущества

1. **Целостность данных**
   - Один проект = один узел (нет дублирования)
   - Изменение дедлайна проекта = обновление одной ноды
   - Все связанные заметки автоматически видят изменения

2. **Мощные запросы**
   ```cypher
   // Все активные проекты с дедлайном в этом месяце
   MATCH (p:Project {status: "active"})
   WHERE p.deadline >= date() AND p.deadline <= date() + duration({months: 1})
   RETURN p

   // Все задачи в проекте, назначенные на конкретного человека
   MATCH (p:Project {name: "Q4 Marketing"})<-[:IS_PART_OF]-(n:Note)
         -[:MENTIONS]->(t:Task)-[:ASSIGNED_TO]->(person:Person)
   RETURN person.name, collect(t.description)
   ```

3. **Масштабируемость**
   - Легко добавлять поля к Project (team, budget, milestones)
   - Можно создавать связи между проектами: `(p1)-[:DEPENDS_ON]->(p2)`
   - Архивация без потери связей: `SET p.status = 'archived'`

4. **Соответствие архитектуре PARA**
   Из `PARA_TYPES_ARCHITECTURE.md`:
   > "метод PARA — это не просто система папок, а **набор высокоуровневых узлов-агрегаторов**"

#### ❌ Отклоненные альтернативы

**Вариант B**: Хранение в атрибутах заметки
- Проблема: Дублирование данных (каждая заметка хранит `project_name: "Q4 Marketing"`)
- Проблема: Нет единого источника истины для проекта
- Проблема: Изменение названия проекта = обновление всех заметок
- Проблема: Сложные агрегирующие запросы

### Источники

- `user_check_granularity_proposal.md` (раздел 4: "Архитектурный вопрос")
- `PARA_TYPES_ARCHITECTURE.md` (раздел 2: "Формальная Модель Данных")

---

## Решение 3: Многоуровневая система подтверждений (L1-L3)

### Суть решения

Система уточнений организована в **4 уровня гранулярности**, из которых **3 уровня реализуются в MVP** (L1-L3), а L4 откладывается на пост-MVP.

### Статус

✅ **ОДОБРЕНО** (L1-L3 для MVP)
⏸️ **ОТЛОЖЕНО** (L4 для пост-MVP)

### Уровни подтверждений

#### Level 1: PARA Classification

**Что:** Определение типа заметки (Project/Area/Resource/Archive)

**Где хранится:**
```cypher
(n:Note)-[:HAS_CHECK {is_current: true}]->(c:UserCheckStatus {
    confirmation_level: 'para_classification',
    status: 'confirmed',
    original_suggestion: 'Project',
    user_choice: 'Area',
    confidence: 0.70
})
```

**Вопрос пользователю:**
```
Определите тип заметки "Q4 Marketing Campaign":
[ ] Project - цель с дедлайном
[x] Area - сфера ответственности
[ ] Resource - справочный материал
```

#### Level 2: Container Assignment

**Что:** Привязка заметки к конкретному Project/Area/Resource

**Где хранится:**
```cypher
(n:Note)-[:HAS_CHECK {is_current: true}]->(c:UserCheckStatus {
    confirmation_level: 'container_assignment',
    status: 'confirmed',
    action: 'create_new',
    container_type: 'Project',
    container_id: 'proj_123',
    container_name: 'Q4 Marketing Campaign'
})
```

**Вопрос пользователю:**
```
К какому проекту отнести заметку?
[x] Создать новый проект "Q4 Marketing Campaign"
[ ] Добавить к существующему: "Marketing Strategy 2024" (40% совпадение)
```

**Результат:** Создается нода `(p:Project)` и связь `(n)-[:IS_PART_OF]->(p)`

#### Level 3: Entity Confirmation

**Что:** Подтверждение извлеченных сущностей (Person, Organization, Task и др.)

**Где хранится:**
```cypher
(e:EntityNode {name: "John Smith", labels: ["Person"]})-[:HAS_CHECK {is_current: true}]->(c:UserCheckStatus {
    confirmation_level: 'entity',
    status: 'modified',
    confidence: 0.85,
    user_action: 'modify',
    modified_fields: ['name'],
    modifications: '[{"field_name": "name", "original_value": "John", "new_value": "John Smith"}]'
})
```

**Вопрос пользователю:**
```
Подтвердите сущность:
Person: John Smith (уверенность: 85%)
Контекст: "Meeting with John Smith about API design"

[x] Подтвердить
[ ] Изменить имя/тип
[ ] Отклонить
[ ] Пропустить
```

#### Level 4: Attribute Validation _(Не в MVP)_

**Что:** Проверка конкретных атрибутов сущности (email, role и т.д.)

**Статус:** Отложено на пост-MVP

**Причина:** Добавляет сложность без критической необходимости. Атрибуты можно валидировать на уровне L3.

### Приоритизация уровней

**Последовательность:** L1 → L2 → L3

Нельзя спрашивать L3, не закончив L1 и L2. Логика:
1. Сначала определяем тип заметки (Project/Area/Resource)
2. Затем привязываем к конкретному контейнеру
3. Только потом подтверждаем сущности внутри заметки

### Почему это решение

#### ✅ Преимущества

1. **Структурированность**
   - Четкая иерархия вопросов
   - Понятная последовательность для пользователя
   - Каждый уровень решает конкретную задачу

2. **Гибкость**
   - Можно пропустить уровни (L4 не в MVP)
   - Можно добавлять новые уровни без переписывания

3. **Минимизация усилий пользователя**
   - Важные вопросы (L1, L2) задаются первыми
   - Несущественные детали (L4) можно пропустить
   - Приоритизация внутри L3 (см. Решение 4)

### Источники

- `user_check_granularity_proposal.md` (раздел 2: "Уровни подтверждения")
- `per_node_confirmation_overview.md` (работа с уровнями)

---

## Решение 4: Приоритизация сущностей в L3

### Суть решения

Не все сущности одинаково важны. Система **приоритизирует** вопросы на основе:
1. Типа сущности (Project важнее Question)
2. Уверенности системы (низкая confidence → выше приоритет)
3. Зависимостей (блокирующие вопросы первыми)

### Статус

✅ **ОДОБРЕНО**

### Таблица приоритетов

```python
ENTITY_PRIORITY = {
    'Project': 1,      # Высший приоритет - структура PARA
    'Area': 1,
    'Person': 2,       # Важные сущности
    'Organization': 2,
    'Task': 3,         # Средний приоритет
    'Decision': 3,
    'Idea': 4,         # Низкий приоритет - можно пропустить
    'Source': 4,
    'Question': 5      # Самый низкий приоритет
}
```

### Автоматическое подтверждение

Сущности с **высокой уверенностью** и **низким приоритетом** подтверждаются автоматически:

```python
def should_auto_confirm(entity, confidence):
    priority = ENTITY_PRIORITY[entity.type]

    if confidence > 0.95 and priority >= 4:
        return True  # Очень высокая уверенность + низкий приоритет

    if confidence > 0.90 and priority >= 3:
        return True  # Высокая уверенность + средний приоритет

    return False
```

**Пример:**
- `Source("https://example.com")` с confidence 0.96 → auto_confirmed
- `Task("Prepare slides")` с confidence 0.92 → auto_confirmed
- `Person("John Smith")` с confidence 0.85 → требует подтверждения

### Почему это решение

#### ✅ Преимущества

1. **Экономия времени пользователя**
   - Не нужно подтверждать очевидные вещи
   - Фокус на важных решениях (PARA структура, ключевые люди)

2. **Гибкость настройки**
   - Пороги confidence можно настроить под конкретного пользователя
   - Приоритеты типов можно переопределить

3. **Прозрачность**
   - Автоподтверждение фиксируется в статусе `auto_confirmed`
   - Пользователь может просмотреть и отменить

### Источники

- `user_check_granularity_proposal.md` (раздел 2.4: "Level 3: Entity Confirmation")
- `user_check_granularity_proposal.md` (раздел 5.4: "Skip/Defer механизм")

---

## Решение 5: Стратегия управления историей

### Суть решения

**Комбинированный подход** для доступа к истории:
1. Текущий статус: через свойство `is_current: true` на связи
2. Полная история: через цепочку отношений `[:NEXT]`

### Статус

✅ **ОДОБРЕНО**

### Структура

```cypher
// Текущий статус (быстрый доступ)
(entity)-[:HAS_CHECK {is_current: true}]->(current_check:UserCheckStatus)

// История (для аудита)
(current_check)-[:NEXT]->(previous_check)
(previous_check)-[:NEXT]->(older_check)
```

### Запросы

**Получить текущий статус (для UI/dashboards):**
```cypher
MATCH (e:EntityNode {uuid: 'ent_123'})-[:HAS_CHECK {is_current: true}]->(c:UserCheckStatus)
RETURN c.status, c.timestamp
```

**Получить полную историю (для аудита):**
```cypher
MATCH (e:EntityNode {uuid: 'ent_123'})-[:HAS_CHECK]->(c:UserCheckStatus)-[:NEXT*0..]->(h:UserCheckStatus)
RETURN c, h
ORDER BY c.timestamp DESC
```

### Алгоритм обновления статуса

При изменении статуса (транзакция):

```python
# 1. Найти текущий статус
MATCH (entity)-[r:HAS_CHECK {is_current: true}]->(old_check)
SET r.is_current = false

# 2. Создать новый статус
CREATE (new_check:UserCheckStatus {...})

# 3. Связать с entity
CREATE (entity)-[:HAS_CHECK {is_current: true}]->(new_check)

# 4. Связать с историей
CREATE (new_check)-[:NEXT]->(old_check)
```

### Почему это решение

#### ✅ Преимущества

1. **Производительность**
   - Запросы к текущему статусу работают мгновенно (индекс на `is_current`)
   - Не нужно сканировать всю цепочку для простых операций

2. **Полнота истории**
   - Ни одно действие пользователя не теряется
   - Можно восстановить состояние на любой момент времени

3. **Простота**
   - Одна связь `HAS_CHECK` для текущего состояния
   - Одно отношение `NEXT` для истории
   - Понятная семантика

### Источники

- `response_to_storage_architecture.md` (раздел "Combined Approach")

---

## Решение 6: LangGraph с interrupt/resume

### Суть решения

Использовать **LangGraph** для оркестрации workflow с возможностью **прерывания** (interrupt) и **возобновления** (resume) при получении ответа пользователя.

### Статус

✅ **ОДОБРЕНО**

### Технологический стек

- **LangGraph**: Workflow orchestration
- **AsyncSqliteSaver**: Persistent state storage (для MVP)
- **FastAPI WebSocket**: Real-time communication
- **PipGraphManager**: Wrapper над Graphiti для извлечения сущностей

### Ключевые концепции

#### Interrupt

Метод `interrupt()` останавливает выполнение графа и ждет ввода пользователя:

```python
@node
async def request_clarification_node(state):
    clarification = state['current_clarification']

    # Останавливаем выполнение и ждем ответа пользователя
    user_response = interrupt(clarification)

    return {'user_response': user_response}
```

#### Resume

Пользователь может отключиться и вернуться позже. Состояние сохраняется в SQLite:

```python
# Thread ID = уникальный идентификатор сессии
thread_id = f"note:{file_path}"

# Возобновление при подключении
config = {"configurable": {"thread_id": thread_id}}
async for event in graph.astream(None, config, stream_mode="updates"):
    # Продолжение с места остановки
    ...
```

### Почему это решение

#### ✅ Преимущества

1. **Асинхронность**
   - Пользователь может отключиться на любой момент
   - Состояние сохраняется автоматически
   - Workflow продолжается с места остановки

2. **Простота**
   - Декларативное описание графа
   - Встроенная сериализация состояния
   - Не нужно писать собственную логику сохранения/восстановления

3. **Отладка**
   - Визуализация графа через `.get_graph().draw_mermaid()`
   - Пошаговое выполнение для тестирования
   - История переходов между нодами

### Источники

- `user_check_mvp_plan.md` (раздел "Technology Stack")
- `state_serialization_details.md` (детали сериализации)

---

## Решение 7: Базовые индексы для MVP

### Суть решения

Для MVP создаются **только критичные индексы**, необходимые для основных операций.

### Статус

✅ **ОДОБРЕНО**

### Список индексов

```cypher
// 1. Поиск по статусу (для dashboards)
CREATE INDEX check_status FOR (c:UserCheckStatus) ON (c.status);

// 2. Поиск по времени (для аналитики)
CREATE INDEX check_timestamp FOR (c:UserCheckStatus) ON (c.timestamp);

// 3. Композитный индекс для частых запросов
CREATE INDEX check_status_timestamp FOR (c:UserCheckStatus) ON (c.status, c.timestamp);

// 4. Поиск сущностей по UUID
CREATE INDEX entity_uuid FOR (e:EntityNode) ON (e.uuid);

// 5. Поиск PARA контейнеров по ID
CREATE INDEX project_id FOR (p:Project) ON (p.id);
CREATE INDEX area_id FOR (a:Area) ON (a.id);
CREATE INDEX resource_id FOR (r:Resource) ON (r.id);
```

### Что НЕ включено в MVP

- ❌ Full-text индексы на текстовых полях
- ❌ Индексы на атрибутах сущностей (email, role и др.)
- ❌ Specialized индексы для аналитики
- ❌ Composite индексы на 3+ полях

Эти индексы будут добавлены по мере необходимости после запуска MVP.

### Источники

- `response_to_storage_architecture.md` (раздел "Indexing Strategy")

---

## Сводная таблица решений

| Решение | Статус | Источник | Приоритет |
|---------|--------|----------|-----------|
| **1. UserCheck Status Nodes** | ✅ Одобрено | response_to_user_check_granularity_proposal.md | Высокий |
| **2. PARA как отдельные ноды** | ✅ Одобрено | user_check_granularity_proposal.md §4.5 | Высокий |
| **3. Уровни L1-L3** | ✅ Одобрено | user_check_granularity_proposal.md §2 | Высокий |
| **3. Уровень L4** | ⏸️ Пост-MVP | user_check_granularity_proposal.md §2.5 | Низкий |
| **4. Приоритизация сущностей** | ✅ Одобрено | user_check_granularity_proposal.md §2.4 | Средний |
| **5. Combined history strategy** | ✅ Одобрено | response_to_storage_architecture.md | Высокий |
| **6. LangGraph interrupt/resume** | ✅ Одобрено | user_check_mvp_plan.md | Высокий |
| **7. Базовые индексы** | ✅ Одобрено | response_to_storage_architecture.md | Средний |

---

## Критерии успеха архитектуры

Архитектура считается успешной, если:

1. ✅ **Все pending статусы** находятся за < 50ms (индекс на `status`)
2. ✅ **История сущности** загружается за < 100ms (отношения NEXT)
3. ✅ **Состояние workflow** восстанавливается после отключения
4. ✅ **Новые уровни подтверждений** можно добавить без изменения существующих
5. ✅ **Аналитика** (типа "статистика по типам") работает эффективно

---

**Следующий документ:** [02_DATA_MODELS.md](./02_DATA_MODELS.md)
