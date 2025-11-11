# User Check Storage Architecture: Анализ Подходов к Хранению Статусов

**Дата создания:** 2025-11-11
**Статус:** Analysis
**Связанные документы:**
- [user_check_granularity_proposal.md](./user_check_granularity_proposal.md) - детализация статусов
- [user_check_mvp_plan.md](./user_check_mvp_plan.md) - MVP схема
- [PARA_TYPES_ARCHITECTURE.md](../PARA_TYPES_ARCHITECTURE.md) - архитектура графа

---

## Оглавление

1. [Проблематика текущего подхода](#1-проблематика-текущего-подхода)
2. [Три оптимальных подхода](#2-три-оптимальных-подхода)
3. [Сравнительный анализ](#3-сравнительный-анализ)
4. [Рекомендации по выбору](#4-рекомендации-по-выбору)
5. [SQL вариант: детальный разбор](#5-sql-вариант-детальный-разбор)

---

## 1. Проблематика текущего подхода

### 1.1 Текущая структура (из MVP)

**Хранение в атрибутах ноды:**

```python
entity = EntityNode(
    uuid="ent_123",
    name="John Smith",
    labels=["Person"],
    attributes={
        'role': 'CEO',
        'email': 'john@example.com',
        'user_check': {                    # ← Вложенная структура
            'status': 'modified',
            'confirmation_level': 'entity',
            'confidence': 0.75,
            'modified_fields': ['name'],
            'modifications': [...]
        }
    }
)
```

**В Neo4j это хранится как:**

```cypher
(:EntityNode {
    uuid: "ent_123",
    name: "John Smith",
    role: "CEO",
    email: "john@example.com",
    user_check: "{...}"  // ← JSON строка в свойстве
})
```

### 1.2 Проблемы производительности

#### Проблема 1: Индексирование вложенных свойств

Neo4j **НЕ поддерживает** индексы на вложенные JSON свойства:

```cypher
// ❌ НЕВОЗМОЖНО создать индекс:
CREATE INDEX entity_check_status FOR (e:EntityNode)
ON (e.user_check.status)
// Error: Nested properties are not supported for indexing

// ✅ Возможен только индекс на корневое свойство:
CREATE INDEX entity_check FOR (e:EntityNode) ON (e.user_check)
// Но это индексирует ВЕСЬ JSON blob, бесполезно для фильтрации по status
```

**Последствия:**
- Запросы по статусу требуют **full table scan** всех EntityNode
- Фильтрация происходит в памяти, не на уровне индекса
- Производительность деградирует с ростом количества нод

#### Проблема 2: Медленные запросы

**Use Case 1: Dashboard - показать все pending clarifications**

```cypher
// Текущий подход - МЕДЛЕННЫЙ
MATCH (e:EntityNode)
WHERE e.user_check IS NOT NULL
  AND e.user_check.status = 'pending'  // ← Десериализация JSON для каждой ноды
RETURN e.name, e.user_check.confidence
ORDER BY e.user_check.confidence ASC
LIMIT 20

// Выполнение:
// 1. Сканирует ВСЕ EntityNode (10,000 нод)
// 2. Для каждой ноды десериализует user_check JSON
// 3. Проверяет status == 'pending'
// 4. Фильтрует в памяти
// Время: ~500ms для 10K нод, ~5s для 100K
```

**Use Case 2: Аналитика - сколько сущностей по статусам**

```cypher
// Текущий подход - ОЧЕНЬ МЕДЛЕННЫЙ
MATCH (e:EntityNode)
WHERE e.user_check IS NOT NULL
RETURN e.user_check.status AS status, count(*) AS count
ORDER BY count DESC

// Проблема:
// - Full scan всех нод
// - Десериализация JSON для группировки
// - Невозможно использовать агрегатные индексы
// Время: ~1-2s для 10K нод, ~10-15s для 100K
```

**Use Case 3: Найти все modified сущности определенного типа**

```cypher
// Текущий подход
MATCH (e:EntityNode)
WHERE 'Person' IN labels(e)
  AND e.user_check.status = 'modified'
  AND e.user_check.confirmation_level = 'entity'
RETURN e

// Даже если есть индекс на label :Person,
// фильтр по user_check все равно требует полного сканирования Person нод
```

#### Проблема 3: Сложность аналитических запросов

**Пример: История изменений пользователя**

```cypher
// Задача: Найти все сущности, которые пользователь изменил за последнюю неделю
MATCH (e:EntityNode)
WHERE e.user_check IS NOT NULL
  AND e.user_check.status = 'modified'
  AND datetime(e.user_check.timestamp) > datetime() - duration({days: 7})
RETURN e.name,
       e.user_check.modified_fields,
       e.user_check.timestamp

// Проблемы:
// 1. Full scan
// 2. Десериализация timestamp для каждой ноды
// 3. datetime() conversion на каждой итерации
// 4. Невозможно использовать temporal indices
```

#### Проблема 4: Обновление статусов

```cypher
// Задача: Обновить все pending статусы старше 24 часов на skipped
MATCH (e:EntityNode)
WHERE e.user_check.status = 'pending'
  AND datetime(e.user_check.timestamp) < datetime() - duration({hours: 24})
SET e.user_check = apoc.convert.toJson(
    apoc.map.setKey(
        apoc.convert.fromJsonMap(e.user_check),
        'status',
        'skipped'
    )
)

// Проблемы:
// 1. Требует APOC для работы с JSON
// 2. Десериализация → изменение → сериализация для каждой ноды
// 3. Невозможно использовать batch updates
// 4. Легко сломать JSON структуру
```

### 1.3 Почему это критично

**Масштаб проблемы:**

```
Типичный Obsidian vault: 1,000 - 10,000 заметок
Извлеченных сущностей: 5,000 - 50,000 нод
Clarifications на 10-30% сущностей: 500 - 15,000 статусов

Dashboard запросы каждые 5-10 секунд
Аналитика: real-time фильтрация и сортировка
```

**Требования к производительности:**

- **Dashboard**: < 200ms для отображения pending items
- **Аналитика**: < 500ms для группировки по статусам
- **Фильтрация**: < 100ms для поиска по критериям
- **Обновления**: batch updates за < 1s

С текущим подходом эти требования **невыполнимы** при >10,000 сущностей.

---

## 2. Три оптимальных подхода

### Подход A: Hybrid Denormalization в Neo4j

**Идея:** Вынести критичные поля на root level, сохранить детали в JSON.

#### Структура

```cypher
(:EntityNode {
    uuid: "ent_123",
    name: "John Smith",

    // ===== ROOT LEVEL (индексируемые свойства) =====
    user_check_status: "modified",           // ← Индекс!
    user_check_level: "entity",              // ← Индекс!
    user_check_timestamp: datetime(...),     // ← Temporal index!
    user_check_confidence: 0.75,             // ← Range index!

    // ===== ДЕТАЛИ (JSON для полной информации) =====
    user_check_details: "{
        'modified_fields': ['name'],
        'modifications': [...],
        'user_comment': '...'
    }"
})
```

#### Индексы

```cypher
// Создаем индексы на root-level свойства
CREATE INDEX entity_check_status FOR (e:EntityNode) ON (e.user_check_status);
CREATE INDEX entity_check_timestamp FOR (e:EntityNode) ON (e.user_check_timestamp);
CREATE INDEX entity_check_confidence FOR (e:EntityNode) ON (e.user_check_confidence);

// Composite index для частых комбинаций
CREATE INDEX entity_check_composite FOR (e:EntityNode)
ON (e.user_check_status, e.user_check_level);
```

#### Запросы

**Dashboard - все pending:**

```cypher
// ✅ БЫСТРО - использует индекс
MATCH (e:EntityNode)
WHERE e.user_check_status = 'pending'
RETURN e.name, e.user_check_confidence
ORDER BY e.user_check_confidence ASC
LIMIT 20

// Query plan: Index Seek → Filter → Sort
// Время: ~10-20ms для 10K нод, ~50-100ms для 100K
```

**Аналитика - группировка по статусам:**

```cypher
// ✅ БЫСТРО - использует индекс
MATCH (e:EntityNode)
WHERE e.user_check_status IS NOT NULL
RETURN e.user_check_status AS status, count(*) AS count
ORDER BY count DESC

// Query plan: Index Scan → Aggregate
// Время: ~50ms для 10K нод, ~200ms для 100K
```

**История изменений за неделю:**

```cypher
// ✅ БЫСТРО - temporal index
MATCH (e:EntityNode)
WHERE e.user_check_status = 'modified'
  AND e.user_check_timestamp > datetime() - duration({days: 7})
RETURN e.name,
       e.user_check_timestamp,
       apoc.convert.fromJsonMap(e.user_check_details).modified_fields

// Query plan: Composite Index Seek → Temporal Filter
// Время: ~20-50ms
```

**Batch update старых pending:**

```cypher
// ✅ Эффективный batch update
MATCH (e:EntityNode)
WHERE e.user_check_status = 'pending'
  AND e.user_check_timestamp < datetime() - duration({hours: 24})
SET e.user_check_status = 'skipped',
    e.user_check_timestamp = datetime()
RETURN count(e)

// Query plan: Index Range Seek → Batch Update
// Время: ~100ms для 1000 нод
```

#### Преимущества ✅

1. **Производительность запросов:**
   - Индексы на критичных полях
   - ~10-50x ускорение по сравнению с JSON queries
   - Эффективные batch operations

2. **Аналитика:**
   - Групировка, сортировка, фильтрация работают быстро
   - Поддержка temporal queries
   - Range queries по confidence

3. **Простота миграции:**
   - Минимальные изменения в коде
   - Можно постепенно денормализовать поля
   - Backwards compatible

4. **Баланс:**
   - Быстрые запросы + полная информация
   - Не создает множество дополнительных нод

#### Недостатки ❌

1. **Денормализация:**
   - Дублирование данных (status в двух местах)
   - Нужна синхронизация root-level ↔ JSON details

2. **Частичное решение:**
   - Сложные запросы по вложенным полям в JSON все еще медленные
   - Например: поиск по specific modified_field

3. **Ограничение:**
   - Нужно заранее выбрать какие поля выносить на root level
   - Изменение структуры требует миграции

#### Когда использовать

- ✅ Нужна производительность без радикального рефакторинга
- ✅ Есть четкий набор критичных полей для индексирования
- ✅ Детали нужны редко (только при drill-down)
- ✅ Важна простота миграции от текущего MVP

---

### Подход B: Отдельные ноды UserCheck в Neo4j

**Идея:** Полная нормализация - каждый user_check = отдельная нода.

#### Структура

```cypher
// Entity node - чистый, без статусов
(:EntityNode {
    uuid: "ent_123",
    name: "John Smith",
    role: "CEO"
})

// Отдельная нода для user check
(:UserCheckStatus {
    id: "check_456",
    status: "modified",
    confirmation_level: "entity",
    confidence: 0.75,
    timestamp: datetime(...),
    user_action: "modify",
    user_comment: "Added full name",

    // Модификации как JSON (можно вынести в отдельные ноды)
    modified_fields: ["name"],
    modifications: "[...]"
})

// Связь
(:EntityNode)-[:HAS_USER_CHECK]->(:UserCheckStatus)
```

#### Расширенная модель с историей

```cypher
// Entity
(e:EntityNode {uuid: "ent_123", name: "John Smith"})

// Несколько проверок в истории
(check1:UserCheckStatus {
    id: "check_001",
    status: "pending",
    timestamp: datetime("2025-11-09T10:00:00Z")
})

(check2:UserCheckStatus {
    id: "check_002",
    status: "modified",
    timestamp: datetime("2025-11-09T12:00:00Z")
})

(check3:UserCheckStatus {
    id: "check_003",
    status: "confirmed",
    timestamp: datetime("2025-11-09T14:00:00Z")
})

// Связи с временной последовательностью
(e)-[:HAS_USER_CHECK {is_current: true}]->(check3)
(e)-[:HAS_USER_CHECK]->(check2)
(e)-[:HAS_USER_CHECK]->(check1)

// Или цепочка истории:
(check1)-[:NEXT]->(check2)-[:NEXT]->(check3)
```

#### Индексы

```cypher
// Индексы на UserCheckStatus ноде
CREATE INDEX check_status FOR (c:UserCheckStatus) ON (c.status);
CREATE INDEX check_timestamp FOR (c:UserCheckStatus) ON (c.timestamp);
CREATE INDEX check_level FOR (c:UserCheckStatus) ON (c.confirmation_level);

// Composite index
CREATE INDEX check_composite FOR (c:UserCheckStatus)
ON (c.status, c.timestamp);
```

#### Запросы

**Dashboard - все pending:**

```cypher
// ✅ ОЧЕНЬ БЫСТРО - через индекс на UserCheckStatus
MATCH (e:EntityNode)-[r:HAS_USER_CHECK]->(c:UserCheckStatus)
WHERE r.is_current = true
  AND c.status = 'pending'
RETURN e.name, c.confidence, c.timestamp
ORDER BY c.confidence ASC
LIMIT 20

// Query plan:
// 1. Index Seek на UserCheckStatus.status
// 2. Traverse к EntityNode
// 3. Filter on relationship property
// Время: ~5-10ms для любого количества нод!
```

**Аналитика - группировка:**

```cypher
// ✅ ОЧЕНЬ БЫСТРО - агрегация на индексированной ноде
MATCH (:EntityNode)-[:HAS_USER_CHECK {is_current: true}]->(c:UserCheckStatus)
RETURN c.status AS status, count(*) AS count
ORDER BY count DESC

// Query plan: Index Scan → Aggregate
// Время: ~10-20ms
```

**История изменений сущности:**

```cypher
// ✅ Полная история доступна через граф
MATCH (e:EntityNode {uuid: "ent_123"})-[:HAS_USER_CHECK]->(c:UserCheckStatus)
RETURN c.status, c.timestamp, c.user_action
ORDER BY c.timestamp ASC

// Видим всю хронологию изменений статуса
```

**Сложная аналитика - паттерны изменений:**

```cypher
// Пример: Какие сущности чаще всего изменяются пользователем?
MATCH (e:EntityNode)-[:HAS_USER_CHECK]->(c:UserCheckStatus)
WHERE c.status = 'modified'
WITH e, count(c) AS modification_count
WHERE modification_count > 2
RETURN e.name, e.labels, modification_count
ORDER BY modification_count DESC

// Impossible с JSON approach, easy с нодами
```

**Temporal queries - изменения за период:**

```cypher
MATCH (e:EntityNode)-[:HAS_USER_CHECK]->(c:UserCheckStatus)
WHERE c.timestamp >= datetime("2025-11-01")
  AND c.timestamp < datetime("2025-11-11")
  AND c.status IN ['modified', 'confirmed']
RETURN e.name, c.status, c.timestamp
ORDER BY c.timestamp DESC

// Temporal index делает это очень быстрым
```

#### Преимущества ✅

1. **Максимальная производительность:**
   - Fastest possible queries (индексы на всех полях)
   - Constant time lookups независимо от размера графа
   - Эффективные joins через граф

2. **Полная история:**
   - Audit trail - видим все изменения статусов
   - Temporal analysis - когда и как менялись статусы
   - Паттерны поведения пользователя

3. **Гибкость аналитики:**
   - Любые аналитические запросы
   - Агрегации, группировки без ограничений
   - Machine learning на истории изменений

4. **Чистая модель:**
   - Separation of concerns: Entity ≠ Status
   - Легко расширять (добавить новые поля в UserCheckStatus)
   - Нет дублирования данных

5. **Масштабируемость:**
   - Производительность не зависит от количества entities
   - Можно архивировать старые check ноды
   - Эффективный sharding (если понадобится)

#### Недостатки ❌

1. **Больше нод в графе:**
   - Для 10,000 entities с checks = +10,000 UserCheckStatus нод
   - Увеличение размера базы (~30-50%)
   - Больше объектов для управления lifecycle

2. **Сложность реализации:**
   - Нужны CRUD операции для UserCheckStatus
   - Управление связями HAS_USER_CHECK
   - Логика для is_current flag или история

3. **Joins в запросах:**
   - Всегда нужен MATCH через связь
   - Чуть сложнее писать запросы (но быстрее выполняются)

4. **Миграция:**
   - Требует рефакторинга существующего кода
   - Нужно мигрировать данные из JSON в ноды
   - Изменения в моделях (Pydantic, Graphiti)

#### Когда использовать

- ✅ Нужна **максимальная производительность** аналитики
- ✅ Важна **полная история** изменений статусов
- ✅ Планируется **сложная аналитика** и ML
- ✅ Масштаб: >50,000 сущностей с checks
- ✅ Готовы инвестировать в рефакторинг

---

### Подход C: Отдельная SQL база (Polyglot Persistence)

**Идея:** Разделить ответственность - Neo4j для графа знаний, PostgreSQL для транзакционных статусов.

#### Архитектура

```
┌─────────────────────────────────────────────────────────┐
│                      Backend API                         │
└─────────────────────────────────────────────────────────┘
         │                           │
         │                           │
    ┌────▼────┐                 ┌────▼────┐
    │  Neo4j  │                 │  PgSQL  │
    │  Graph  │                 │   DB    │
    └─────────┘                 └─────────┘
         │                           │
         │                           │
    [Semantic]                  [Transactional]
    [Knowledge]                 [Status Tracking]
    [Entities]                  [user_check data]
    [Relations]                 [Analytics]
```

#### SQL Schema

```sql
-- User check статусы в PostgreSQL
CREATE TABLE user_check_status (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Связь с Entity в Neo4j
    entity_uuid UUID NOT NULL,           -- ← ссылка на EntityNode.uuid
    entity_type VARCHAR(50) NOT NULL,    -- Person, Project, etc.
    entity_name TEXT,                     -- денормализация для быстрых запросов

    -- Status tracking
    status VARCHAR(50) NOT NULL,          -- pending, confirmed, modified, rejected
    confirmation_level VARCHAR(50),       -- para_classification, entity, attribute

    -- Metadata
    confidence DECIMAL(3, 2),             -- 0.00 - 1.00
    priority INTEGER,                     -- 1-5
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- User interaction
    user_action VARCHAR(50),              -- confirm, modify, reject, skip
    user_comment TEXT,

    -- Modifications (JSONB для гибкости)
    modified_fields TEXT[],               -- Array: ['name', 'email']
    modifications JSONB,                  -- Детали изменений

    -- Flags
    is_current BOOLEAN DEFAULT true,      -- Текущий статус vs история
    auto_confirmed BOOLEAN DEFAULT false,

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Индексы для производительности
CREATE INDEX idx_user_check_entity ON user_check_status(entity_uuid);
CREATE INDEX idx_user_check_status ON user_check_status(status);
CREATE INDEX idx_user_check_current ON user_check_status(is_current) WHERE is_current = true;
CREATE INDEX idx_user_check_timestamp ON user_check_status(timestamp);

-- Composite indices для частых запросов
CREATE INDEX idx_user_check_status_level ON user_check_status(status, confirmation_level);
CREATE INDEX idx_user_check_status_time ON user_check_status(status, timestamp);

-- Full-text search на comments
CREATE INDEX idx_user_check_comment_fts ON user_check_status
USING gin(to_tsvector('english', user_comment));

-- JSONB index на modifications
CREATE INDEX idx_user_check_modifications ON user_check_status USING gin(modifications);
```

#### Связь Neo4j ↔ PostgreSQL

**Neo4j хранит только UUID:**

```cypher
(:EntityNode {
    uuid: "ent_123",
    name: "John Smith",
    role: "CEO",
    // NO user_check data here!
})
```

**PostgreSQL хранит статусы:**

```sql
SELECT * FROM user_check_status WHERE entity_uuid = 'ent_123';
```

#### Запросы

**Dashboard - все pending (SQL):**

```sql
-- ✅ СВЕРХБЫСТРО - реляционные индексы
SELECT
    entity_uuid,
    entity_name,
    confidence,
    timestamp
FROM user_check_status
WHERE status = 'pending'
  AND is_current = true
ORDER BY confidence ASC
LIMIT 20;

-- Query plan: Index Scan on idx_user_check_status
-- Время: ~1-5ms для любого количества записей (до миллионов)
```

**Аналитика - группировка (SQL):**

```sql
-- ✅ СВЕРХБЫСТРО - оптимизатор PostgreSQL
SELECT
    status,
    confirmation_level,
    COUNT(*) as count,
    AVG(confidence) as avg_confidence
FROM user_check_status
WHERE is_current = true
GROUP BY status, confirmation_level
ORDER BY count DESC;

-- Query plan: Index Scan → HashAggregate
-- Время: ~5-10ms
```

**Сложная аналитика - временные тренды:**

```sql
-- Пример: Как менялся процент подтверждений по дням
SELECT
    DATE(timestamp) as date,
    status,
    COUNT(*) as count,
    COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY DATE(timestamp)) as percentage
FROM user_check_status
WHERE timestamp >= NOW() - INTERVAL '30 days'
GROUP BY DATE(timestamp), status
ORDER BY date DESC, count DESC;

-- PostgreSQL оптимизирован для таких запросов
```

**История изменений сущности (SQL + Neo4j):**

```sql
-- Сначала получаем историю из SQL
SELECT
    status,
    timestamp,
    user_action,
    user_comment,
    modifications
FROM user_check_status
WHERE entity_uuid = 'ent_123'
ORDER BY timestamp ASC;

-- Затем при необходимости запрашиваем детали из Neo4j
-- (но обычно entity_name уже есть в SQL для денормализации)
```

**Комбинированный запрос - сущности с pending статусами:**

```python
# Python backend - координирует два источника
async def get_pending_entities_with_context():
    # 1. Быстрый запрос в SQL для pending statuses
    sql_result = await pg_pool.fetch("""
        SELECT entity_uuid, entity_name, confidence, timestamp
        FROM user_check_status
        WHERE status = 'pending' AND is_current = true
        ORDER BY confidence ASC
        LIMIT 20
    """)

    entity_uuids = [row['entity_uuid'] for row in sql_result]

    # 2. Запрос в Neo4j для дополнительного контекста (если нужен)
    cypher = """
        MATCH (e:EntityNode)
        WHERE e.uuid IN $uuids
        RETURN e.uuid, labels(e) AS types, e.attributes
    """
    neo4j_result = await neo4j_session.run(cypher, uuids=entity_uuids)

    # 3. Объединяем результаты
    return merge_results(sql_result, neo4j_result)
```

#### Синхронизация

**Стратегия 1: Event-Driven (Рекомендуется)**

```python
# При создании/обновлении entity в Neo4j
async def create_entity_with_check(entity_data, user_check_data):
    # 1. Создаем entity в Neo4j
    entity_uuid = await neo4j_manager.create_entity(entity_data)

    # 2. Emit event
    await event_bus.publish(
        topic="entity.check.created",
        payload={
            "entity_uuid": entity_uuid,
            "entity_type": entity_data['type'],
            "entity_name": entity_data['name'],
            "user_check": user_check_data
        }
    )

    # 3. Handler сохраняет в PostgreSQL
    @event_bus.subscribe("entity.check.created")
    async def handle_check_created(payload):
        await pg_pool.execute(
            """INSERT INTO user_check_status
               (entity_uuid, entity_type, entity_name, status, ...)
               VALUES ($1, $2, $3, $4, ...)""",
            payload['entity_uuid'],
            payload['entity_type'],
            ...
        )
```

**Стратегия 2: Transaction Coordinator (для критичных операций)**

```python
async def update_entity_status_transactional(entity_uuid, new_status):
    async with transaction_coordinator() as txn:
        try:
            # 1. Update в PostgreSQL
            await txn.execute_sql(
                "UPDATE user_check_status SET status = $1 WHERE entity_uuid = $2",
                new_status, entity_uuid
            )

            # 2. Optional: Update metadata в Neo4j (если нужно)
            await txn.execute_cypher(
                "MATCH (e:EntityNode {uuid: $uuid}) SET e.last_check_update = datetime()",
                uuid=entity_uuid
            )

            # 3. Commit обеих транзакций
            await txn.commit()

        except Exception as e:
            await txn.rollback()
            raise
```

**Стратегия 3: Eventual Consistency (для не критичных данных)**

```python
# Periodically sync entity names from Neo4j to PostgreSQL
async def sync_entity_names():
    """Background job - раз в N минут"""

    # 1. Получаем entity_uuids из SQL, которые давно не обновлялись
    stale_entities = await pg_pool.fetch("""
        SELECT DISTINCT entity_uuid
        FROM user_check_status
        WHERE updated_at < NOW() - INTERVAL '1 hour'
    """)

    # 2. Batch query в Neo4j
    cypher = """
        MATCH (e:EntityNode)
        WHERE e.uuid IN $uuids
        RETURN e.uuid, e.name
    """
    neo4j_data = await neo4j_session.run(cypher, uuids=stale_entities)

    # 3. Batch update в PostgreSQL
    await pg_pool.executemany(
        "UPDATE user_check_status SET entity_name = $1 WHERE entity_uuid = $2",
        [(data['name'], data['uuid']) for data in neo4j_data]
    )
```

#### Преимущества ✅

1. **Максимальная производительность:**
   - PostgreSQL **оптимизирован** для транзакционных запросов
   - Индексы работают идеально (B-Tree, GIN, GiST)
   - Query optimizer для сложных аналитических запросов
   - Поддержка materialized views для кэширования

2. **Мощные возможности SQL:**
   - Window functions для трендов
   - CTEs для сложных запросов
   - Full-text search (tsvector)
   - JSONB для гибких полей
   - Triggers, stored procedures

3. **Аналитика и отчеты:**
   - Подключение BI tools (Metabase, Superset, Grafana)
   - SQL queries для dashboards
   - Экспорт в CSV/Excel одной командой
   - Temporal queries (timestamps, intervals)

4. **Разделение ответственности:**
   - Neo4j = semantic knowledge graph (what entities are, how they relate)
   - PostgreSQL = operational state tracking (what's happening with entities)
   - Each DB does what it's best at

5. **Масштабирование независимо:**
   - Можно масштабировать SQL отдельно (replicas, sharding)
   - Neo4j масштабируется для графовых операций
   - Разные retention policies (можно архивировать старые checks в SQL)

6. **Transaction support:**
   - ACID guarantees для critical operations
   - Referential integrity через foreign keys (если нужно)
   - Atomic updates

#### Недостатки ❌

1. **Сложность инфраструктуры:**
   - Два databases = два connection pools
   - Два набора миграций
   - Два источника для мониторинга, бэкапов

2. **Синхронизация:**
   - Нужна логика для координации Neo4j ↔ PostgreSQL
   - Риск inconsistency при падениях
   - Eventual consistency для некритичных полей

3. **Стоимость разработки:**
   - Больше кода (два ORM/query builder)
   - Сложнее debugging (проблема в Neo4j или SQL?)
   - Onboarding новых разработчиков

4. **Дублирование данных:**
   - entity_uuid хранится в обеих базах
   - entity_name denormalized в SQL
   - Нужно поддерживать синхронизацию

5. **Latency комбинированных запросов:**
   - Если нужны данные из обеих баз = два round-trips
   - Хотя для большинства use cases достаточно SQL

#### Когда использовать

- ✅ **Масштаб**: >100,000 сущностей с активными checks
- ✅ **Аналитика**: Нужны сложные SQL запросы, BI dashboards
- ✅ **Производительность**: Критична latency <10ms для статусов
- ✅ **Команда**: Есть опыт с polyglot persistence
- ✅ **Разделение**: Четкая граница между knowledge graph и operational state
- ✅ **Compliance**: Нужны ACID транзакции для audit trail

#### Когда НЕ использовать

- ❌ **Простота**: Приоритет - простота архитектуры
- ❌ **Малый масштаб**: <10,000 entities, hybrid approach достаточен
- ❌ **Команда**: Нет опыта с multi-database системами
- ❌ **Tight coupling**: Queries часто нужны данные из обеих баз одновременно

---

## 3. Сравнительный анализ

### 3.1 Таблица сравнения

| Критерий | Hybrid (A) | Separate Nodes (B) | SQL DB (C) |
|----------|------------|---------------------|------------|
| **Производительность** |
| Simple queries (<100ms) | ⚠️ 20-50ms | ✅ 5-10ms | ✅ 1-5ms |
| Complex analytics | ⚠️ 100-500ms | ✅ 10-50ms | ✅ 5-20ms |
| Batch updates | ✅ Good | ✅ Very good | ✅ Excellent |
| Scalability (100K+ entities) | ⚠️ Degrades | ✅ Good | ✅ Excellent |
| **Сложность** |
| Implementation effort | ✅ Low | ⚠️ Medium | ❌ High |
| Migration from MVP | ✅ Easy | ⚠️ Medium | ❌ Complex |
| Code complexity | ✅ Low | ⚠️ Medium | ❌ High |
| Infrastructure | ✅ Simple | ✅ Simple | ❌ Two DBs |
| **Функциональность** |
| History tracking | ❌ Limited | ✅ Full | ✅ Full |
| Analytics queries | ⚠️ Limited | ✅ Good | ✅ Excellent |
| BI tools integration | ❌ No | ⚠️ Limited | ✅ Native |
| Full-text search | ❌ No | ⚠️ APOC | ✅ Native |
| **Гибкость** |
| Schema evolution | ✅ Easy | ✅ Easy | ⚠️ Migrations |
| Query flexibility | ⚠️ Limited | ✅ Good | ✅ Excellent |
| Custom indices | ⚠️ Limited | ✅ Good | ✅ Excellent |
| **Консистентность** |
| Data integrity | ⚠️ Denorm issues | ✅ Good | ⚠️ Sync needed |
| ACID transactions | ✅ Neo4j | ✅ Neo4j | ✅ PostgreSQL |
| Eventual consistency | N/A | N/A | ⚠️ Risk |
| **Стоимость** |
| Development cost | ✅ Low | ⚠️ Medium | ❌ High |
| Maintenance cost | ✅ Low | ✅ Medium | ⚠️ Medium-High |
| Infrastructure cost | ✅ One DB | ✅ One DB | ⚠️ Two DBs |

### 3.2 Производительность (концептуально)

**Use Case: Dashboard с 20 pending items**

```
Текущий (JSON):    500ms  (10K entities)
Hybrid (A):         20ms  (10x improvement)
Separate Nodes (B):  5ms  (100x improvement)
SQL DB (C):          2ms  (250x improvement)
```

**Use Case: Аналитика - группировка по статусам**

```
Текущий (JSON):    1500ms  (full scan + deserialize)
Hybrid (A):         100ms  (index scan + aggregate)
Separate Nodes (B):  15ms  (index scan + aggregate)
SQL DB (C):           5ms  (optimized aggregation)
```

**Use Case: Batch update 1000 статусов**

```
Текущий (JSON):    2000ms  (deserialize + modify + serialize each)
Hybrid (A):         150ms  (direct property set)
Separate Nodes (B): 100ms  (relationship traversal + update)
SQL DB (C):          50ms  (single UPDATE statement)
```

### 3.3 Масштабируемость

```
              10K entities    100K entities   1M entities
Hybrid (A):   Good           ⚠️ Degrades     ❌ Slow
Nodes (B):    Excellent      Good            ⚠️ OK
SQL (C):      Excellent      Excellent       Good
```

---

## 4. Рекомендации по выбору

### 4.1 Decision Tree

```
START: Сколько entities с user_check ожидается?

├─ < 10,000 entities
│   └─ Нужна ли история изменений статусов?
│       ├─ НЕТ → **HYBRID (A)** ✅ Best choice
│       └─ ДА → **SEPARATE NODES (B)** ✅
│
├─ 10,000 - 50,000 entities
│   └─ Какая аналитика нужна?
│       ├─ Простая (dashboards) → **HYBRID (A)** или **NODES (B)**
│       └─ Сложная (BI, ML) → **SQL DB (C)** ✅
│
└─ > 50,000 entities
    └─ Критична ли latency <10ms?
        ├─ ДА → **SQL DB (C)** ✅ Best performance
        └─ НЕТ → **SEPARATE NODES (B)** ✅ Good balance
```

### 4.2 По сценариям использования

#### Сценарий 1: MVP + быстрая миграция

**Задача:** Улучшить текущее решение с минимальными изменениями

**Выбор: Hybrid (A)** ✅

**Почему:**
- Простая миграция: добавить 3-4 root-level свойства
- Сохранить всю существующую логику
- Получить 10x ускорение запросов
- Возможность потом мигрировать на B или C

**Действия:**
1. Добавить `user_check_status`, `user_check_timestamp` на EntityNode
2. Создать индексы
3. Обновить код для синхронизации root ↔ JSON
4. Измерить производительность

---

#### Сценарий 2: Knowledge management система с историей

**Задача:** Полноценный PARA + audit trail всех изменений

**Выбор: Separate Nodes (B)** ✅

**Почему:**
- История - first-class citizen в графе
- Можно анализировать паттерны изменений
- Гибкие аналитические запросы через Cypher
- Полная интеграция с графом знаний

**Действия:**
1. Создать UserCheckStatus node type
2. Определить связи HAS_USER_CHECK
3. Миграция данных из JSON в ноды
4. Построить dashboard на Cypher queries

---

#### Сценарий 3: Enterprise scale с BI интеграцией

**Задача:** Большой vault (100K+ заметок), dashboards для команды, ML

**Выбор: SQL DB (C)** ✅

**Почему:**
- Масштаб требует реляционных оптимизаций
- BI tools (Metabase) work natively с PostgreSQL
- ML pipelines easier с SQL
- Audit и compliance (ACID transactions)

**Действия:**
1. Setup PostgreSQL alongside Neo4j
2. Define schema, indices
3. Implement sync layer (event-driven)
4. Migrate status tracking to SQL
5. Keep knowledge graph in Neo4j

---

### 4.3 Критерии выбора (Checklist)

**Выбирайте Hybrid (A) если:**
- [ ] Entities: 1,000 - 10,000
- [ ] История НЕ критична (достаточно current state)
- [ ] Нужно быстро улучшить MVP
- [ ] Команда знакома с Neo4j, но не с polyglot
- [ ] Простота > максимальная производительность

**Выбирайте Separate Nodes (B) если:**
- [ ] Entities: 10,000 - 100,000
- [ ] Нужна полная история изменений
- [ ] Аналитика: графовые запросы (Cypher)
- [ ] Хотите всё в одном месте (Neo4j)
- [ ] Готовы на medium complexity для better performance

**Выбирайте SQL DB (C) если:**
- [ ] Entities: 50,000+
- [ ] Критична latency <10ms
- [ ] Нужна интеграция с BI tools (Metabase, Grafana)
- [ ] Команда опытна в polyglot persistence
- [ ] Audit trail и compliance требования
- [ ] ML/analytics pipelines на SQL

---

## 5. SQL вариант: детальный разбор

### 5.1 Зачем нужна отдельная база?

#### Философия разделения

**Neo4j = Знания (Knowledge)**
- Что существует (entities)
- Как связано (relationships)
- Семантика (meaning, context)
- Долгосрочное хранение

**PostgreSQL = Процессы (Operations)**
- Что происходит (status tracking)
- Когда происходит (timestamps)
- Кто делает (user actions)
- Краткосрочное + archive

#### Аналогия

```
Neo4j = Library (книги, авторы, темы)
PostgreSQL = Checkout System (кто взял, когда вернуть, штрафы)

Можно checkout system встроить в каталог библиотеки?
Технически да, но это разные домены.
```

### 5.2 Что хранить где

#### В Neo4j (Knowledge Graph)

```cypher
// Сущности - долгосрочные объекты знаний
(:Person {uuid, name, role, email})
(:Project {uuid, name, deadline, goal})
(:Organization {uuid, name})
(:Task {uuid, description})

// Семантические связи
(Person)-[:WORKS_AT]->(Organization)
(Task)-[:IS_ASSIGNED_TO]->(Person)
(Note)-[:IS_PART_OF]->(Project)

// Что НЕ хранить:
// ❌ user_check статусы (временные, часто меняются)
// ❌ clarification requests (operational data)
// ❌ user interaction logs (transactional)
```

#### В PostgreSQL (Operational State)

```sql
-- Транзакционные статусы
user_check_status (entity_uuid, status, timestamp, ...)

-- Clarification requests/responses
clarification_requests (id, entity_uuid, question, options, ...)
clarification_responses (request_id, user_choice, timestamp, ...)

-- User sessions
user_sessions (id, started_at, note_path, ...)

-- Analytics pre-computed
entity_status_summary (date, status, count, ...)

-- Что НЕ хранить:
// ❌ Entity attributes (в Neo4j)
// ❌ Relationships между entities (в Neo4j)
// ❌ Knowledge graph (в Neo4j)
```

#### Граница между Neo4j и PostgreSQL

| Данные | Neo4j | PostgreSQL | Почему |
|--------|-------|------------|--------|
| Entity metadata (name, role) | ✅ | ⚠️ Denorm | Source of truth |
| Entity relationships | ✅ | ❌ | Граф оптимизирован |
| user_check статусы | ❌ | ✅ | Часто меняются, queries |
| История изменений | ⚠️ | ✅ | SQL лучше для temporal |
| Clarifications | ❌ | ✅ | Operational workflow |
| Аналитика aggregates | ❌ | ✅ | SQL оптимизирован |

### 5.3 Стратегии синхронизации

#### Стратегия 1: Write-Through (Синхронная)

**Когда:** Создание entity с user_check

```python
async def create_entity_with_status(entity_data, check_data):
    async with transaction():
        # 1. Write to Neo4j (source of truth)
        entity_uuid = await neo4j.create_entity(entity_data)

        # 2. Write to PostgreSQL (immediately)
        await pg.execute(
            "INSERT INTO user_check_status (entity_uuid, status, ...) VALUES (...)",
            entity_uuid, check_data['status'], ...
        )

        return entity_uuid

# Pros: Immediate consistency
# Cons: Latency (two writes), partial failure handling
```

#### Стратегия 2: Event-Driven (Асинхронная)

**Когда:** Обновление статусов (не критичные)

```python
# 1. Write to Neo4j
entity_uuid = await neo4j.create_entity(entity_data)

# 2. Publish event
await event_bus.publish("entity.created", {
    "uuid": entity_uuid,
    "data": entity_data
})

# 3. Handler пишет в PostgreSQL (async)
@event_bus.subscribe("entity.created")
async def on_entity_created(event):
    await pg.execute("INSERT INTO user_check_status ...")

# Pros: Decoupled, fast response, resilient
# Cons: Eventual consistency (typically <100ms delay)
```

#### Стратегия 3: Change Data Capture (CDC)

**Когда:** Автоматическая синхронизация entity names

```python
# Option A: PostgreSQL Logical Replication
# Listen to changes in Neo4j → replicate to PostgreSQL

# Option B: Debezium / Kafka Connect
# Neo4j changes → Kafka topic → PostgreSQL consumer

# Option C: Polling (simple но inefficient)
async def sync_entity_names_job():
    """Run every 5 minutes"""
    entities = await neo4j.run("MATCH (e:EntityNode) RETURN e.uuid, e.name")

    for entity in entities:
        await pg.execute(
            "UPDATE user_check_status SET entity_name = $1 WHERE entity_uuid = $2",
            entity['name'], entity['uuid']
        )

# Pros: Automatic, no code changes
# Cons: Complex setup, eventual consistency
```

#### Стратегия 4: Query-Time Join (Hybrid)

**Когда:** Entity name не обязательно всегда синхронизировать

```python
# PostgreSQL хранит только UUID
SELECT entity_uuid, status, timestamp
FROM user_check_status
WHERE status = 'pending'

# При необходимости - join через код
entity_uuids = [row['entity_uuid'] for row in pg_result]

cypher = "MATCH (e:EntityNode) WHERE e.uuid IN $uuids RETURN e.uuid, e.name"
neo4j_result = await neo4j.run(cypher, uuids=entity_uuids)

merged = merge(pg_result, neo4j_result, on='uuid')

# Pros: No denormalization, always fresh data
# Cons: Extra query, latency
```

### 5.4 Consistency гарантии

#### Проблема: Partial Failure

```python
# Scenario: Написали в Neo4j, но PostgreSQL упал
async def create_entity_with_status_UNSAFE(entity_data, check_data):
    entity_uuid = await neo4j.create_entity(entity_data)  # ✅ Success

    await pg.execute("INSERT INTO user_check_status ...")   # ❌ Fails!

    # Result: Entity exists in Neo4j, but NO status in PostgreSQL!
```

#### Решение 1: Saga Pattern

```python
async def create_entity_with_status_SAFE(entity_data, check_data):
    entity_uuid = None
    try:
        # Step 1: Neo4j
        entity_uuid = await neo4j.create_entity(entity_data)

        # Step 2: PostgreSQL
        await pg.execute("INSERT INTO user_check_status ...", entity_uuid, ...)

        return entity_uuid

    except Exception as e:
        # Rollback Neo4j if PostgreSQL failed
        if entity_uuid:
            await neo4j.delete_entity(entity_uuid)
        raise

# Pros: Eventual consistency, compensating transactions
# Cons: Complex, best-effort rollback
```

#### Решение 2: Outbox Pattern

```python
# 1. Write to Neo4j + outbox table (same Neo4j tx)
async def create_entity_with_outbox(entity_data, check_data):
    async with neo4j.transaction():
        entity_uuid = await neo4j.create_entity(entity_data)

        # Write intent to outbox
        await neo4j.create_node({
            "label": "OutboxEvent",
            "type": "user_check_created",
            "payload": {"entity_uuid": entity_uuid, "check_data": check_data},
            "status": "pending"
        })

# 2. Background worker processes outbox
async def process_outbox():
    events = await neo4j.run("MATCH (e:OutboxEvent {status: 'pending'}) RETURN e")

    for event in events:
        try:
            await pg.execute("INSERT INTO user_check_status ...", event['payload'])
            await neo4j.run("MATCH (e:OutboxEvent {id: $id}) SET e.status = 'completed'",
                           id=event['id'])
        except:
            # Retry later
            pass

# Pros: Guaranteed delivery, transactional
# Cons: Eventual consistency, background job needed
```

#### Решение 3: Accept Eventual Inconsistency

```python
# For non-critical data, it's OK to be eventually consistent

# PostgreSQL is "cache" of Neo4j data
# If sync fails, retry later or accept staleness

async def create_entity_eventual(entity_data, check_data):
    entity_uuid = await neo4j.create_entity(entity_data)

    try:
        await pg.execute("INSERT INTO user_check_status ...", entity_uuid, ...)
    except:
        # Log error, but don't fail the request
        logger.error(f"Failed to sync to PostgreSQL: {entity_uuid}")
        # Background job will eventually sync

    return entity_uuid

# Pros: Simple, fast, resilient
# Cons: Temporary inconsistency (acceptable for dashboards, not for billing)
```

### 5.5 Trade-offs

#### Когда SQL DB стоит сложности

✅ **ДА, используйте PostgreSQL если:**

1. **Масштаб:**
   - >50,000 сущностей с активными статусами
   - >1M записей в истории изменений
   - Ожидается рост до >10M записей

2. **Производительность критична:**
   - Dashboard должен загружаться <100ms
   - Real-time аналитика для пользователей
   - Concurrent users делают много queries

3. **Аналитика:**
   - Нужны BI dashboards (Metabase, Grafana)
   - Сложные SQL queries (window functions, CTEs)
   - ML pipelines на Python + pandas (легче с SQL)
   - Экспорт в CSV, Excel

4. **Команда:**
   - Есть опыт с polyglot persistence
   - DevOps может управлять двумя базами
   - Разработчики знают и Neo4j и SQL

5. **Compliance:**
   - Audit trail требования
   - ACID transactions для критичных операций
   - Retention policies (архивировать старые статусы)

#### Когда SQL DB НЕ стоит

❌ **НЕТ, используйте Hybrid или Nodes если:**

1. **Простота важнее:**
   - Малая команда, нет DevOps
   - Нужно быстро запустить MVP
   - Сложность maintenance > performance gains

2. **Малый масштаб:**
   - <10,000 entities с checks
   - Queries не критичны (<1s OK)
   - Hybrid approach даст достаточное ускорение

3. **Tight coupling:**
   - Большинство queries нужны данные из обеих баз
   - Entity context всегда нужен вместе со статусом
   - Complexity join'ов перевешивает performance

4. **Infrastructure constraints:**
   - Не хотите управлять двумя базами
   - Backup, monitoring удвоенная сложность
   - Cost: две базы = больше ресурсов

### 5.6 Миграционный путь к SQL

**Фаза 1: Hybrid (MVP fix)**
- Добавить root-level properties в Neo4j
- Получить quick wins в performance
- Оценить реальные query patterns

**Фаза 2: Measure & Decide**
- Профилировать queries
- Определить bottlenecks
- Если Hybrid достаточен → остановиться
- Если нет → продолжить к SQL

**Фаза 3: Add PostgreSQL**
- Setup PostgreSQL alongside Neo4j
- Migrate status tracking to SQL
- Keep knowledge graph in Neo4j
- Implement sync layer

**Фаза 4: Optimize**
- Tune indices, queries
- Add materialized views
- BI tools integration
- Archive old data

---

## 6. Выводы

### 6.1 Итоговые рекомендации

**Для большинства случаев:**

1. **Стартовать с Hybrid (A)**
   - Быстро, просто, effective
   - 10x performance improvement
   - Легко мигрировать дальше

2. **Если нужна история → Nodes (B)**
   - Полная интеграция с графом
   - Audit trail через связи
   - Мощные аналитические queries

3. **Если масштаб >50K или BI нужны → SQL (C)**
   - Maximum performance
   - Professional tooling
   - Future-proof для enterprise

### 6.2 Anti-Patterns

❌ **Не делайте:**

1. **Storing complex nested JSON без индексов** (текущий подход)
   - Невозможно эффективно query
   - Full table scans

2. **Over-engineering сразу**
   - Не нужен SQL для 1000 entities
   - Start simple, scale when needed

3. **Mixing concerns**
   - Не храните operational state (статусы) и knowledge (entities) одинаково
   - Разделите ответственность

4. **Ignoring sync complexity в polyglot**
   - Если выбрали SQL - инвестируйте в proper sync
   - Eventual consistency может быть OK, но нужна стратегия

### 6.3 Следующие шаги

1. **Оценить масштаб:**
   - Сколько entities ожидается?
   - Какие query patterns критичны?

2. **Выбрать подход:**
   - Используйте decision tree из раздела 4.1
   - Start simple, evolve

3. **Prototype:**
   - Имплементировать выбранный подход
   - Benchmark реальные queries

4. **Measure:**
   - Профилировать production workload
   - Iterate если нужно

---

**Документ создан:** 2025-11-11
**Автор:** Claude Code
**Версия:** 1.0
**Статус:** Analysis - Ready for Decision
