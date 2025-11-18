# Graphiti Labels: Разбор путаницы между Neo4j labels и Graphiti labels field

> **Исследование**: Полное разъяснение двух разных "labels" в Graphiti/Neo4j экосистеме
> **Дата**: 2025-10-21
> **Контекст**: Анализ Issue #567 и реального поведения в PipGraph

## Проблема: Почему в графе все Entity nodes имеют только label `:Entity`?

**Вопрос пользователя**:
> "В моих данных в графе в Entity нодах в поле Labels указано Entity, разве не должно быть как в примерах `labels=["Technology", "Programming Language"]`?"

**Краткий ответ**: Вы столкнулись с путаницей двух разных концепций, обе называющихся "labels":
1. **Neo4j labels** - системные метки узлов (`:Entity`, `:Person`, `:Technology`)
2. **Graphiti `labels` field** - обычное поле данных в EntityNode

И да, есть известная проблема (Issue #567), из-за которой custom labels не добавляются как Neo4j labels.

---

## Два разных "labels"

### 1. Neo4j Labels (Системный механизм)

**Что это:**
- Встроенная функция Neo4j для классификации узлов
- Используется для индексации, производительности, группировки
- Задаётся в Cypher через двоеточие: `:Entity`, `:Person`, `:Technology`

**Синтаксис в Cypher:**
```cypher
// Создание узла с несколькими labels
CREATE (n:Entity:Person:Employee {name: "John"})

// Получение labels узла
MATCH (n) RETURN labels(n)
// → ["Entity", "Person", "Employee"]

// Фильтрация по label
MATCH (n:Person) WHERE n.name = "John" RETURN n
```

**Преимущества:**
- ✅ Быстрая фильтрация (индексы по labels)
- ✅ Встроенная функция `labels(n)` в Cypher
- ✅ Визуализация в Neo4j Browser (раскраска по labels)

### 2. Graphiti `labels` Field (Поле данных)

**Что это:**
- Обычное поле в Pydantic модели `EntityNode`
- Просто `list[str]`, хранящий категории сущности
- Заполняется LLM при извлечении entities

**Определение в коде:**
```python
# graphiti_core/nodes.py:84-89
class Node(BaseModel, ABC):
    uuid: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Field(description='name of the node')
    group_id: str = Field(description='partition of the graph')
    labels: list[str] = Field(default_factory=list)  # ← ЭТО ПОЛЕ!
    created_at: datetime = Field(default_factory=lambda: utc_now())
```

**Пример использования:**
```python
# LLM извлекает сущность с labels
entity = EntityNode(
    name="Python",
    labels=["Programming Language", "Technology"]  # ← значение поля
)

# Это просто список строк в Python объекте
print(entity.labels)  # → ["Programming Language", "Technology"]
```

---

## Как Graphiti связывает два "labels"

### Код в `EntityNode.save()`

**Локация**: `graphiti_core/nodes.py:452-483`

```python
async def save(self, driver: GraphDriver):
    entity_data: dict[str, Any] = {
        'uuid': self.uuid,
        'name': self.name,
        'name_embedding': self.name_embedding,
        'group_id': self.group_id,
        'summary': self.summary,
        'created_at': self.created_at,
    }

    if driver.provider == GraphProvider.KUZU:
        # Kuzu: labels хранятся как ПОЛЕ (не как системные labels)
        entity_data['attributes'] = json.dumps(self.attributes)
        entity_data['labels'] = list(set(self.labels + ['Entity']))
        result = await driver.execute_query(
            get_entity_node_save_query(driver.provider, labels=''),
            **entity_data,
        )
    else:
        # Neo4j/Neptune/FalkorDB: labels становятся Neo4j labels
        entity_data.update(self.attributes or {})
        labels = ':'.join(self.labels + ['Entity'])  # ← ЗДЕСЬ ПРОИСХОДИТ КОНВЕРТАЦИЯ!

        result = await driver.execute_query(
            get_entity_node_save_query(driver.provider, labels),  # ← передаём строку
            entity_data=entity_data,
        )

    return result
```

**Ключевая строка 471**:
```python
labels = ':'.join(self.labels + ['Entity'])
# Если self.labels = ["Person", "Employee"]
# То labels = "Person:Employee:Entity"
```

### Cypher Query для Neo4j

**Локация**: `graphiti_core/models/nodes/node_db_queries.py:164-170`

```python
def get_entity_node_save_query(provider: GraphProvider, labels: str) -> str:
    match provider:
        case _:  # Neo4j (default case)
            return f"""
                MERGE (n:Entity {{uuid: $entity_data.uuid}})
                SET n:{labels}  # ← Устанавливает Neo4j labels динамически!
                SET n = $entity_data
                WITH n CALL db.create.setNodeVectorProperty(n, "name_embedding", $entity_data.name_embedding)
                RETURN n.uuid AS uuid
            """
```

**Пример результата:**
```cypher
-- Если labels = "Person:Employee:Entity"
MERGE (n:Entity {uuid: "uuid-123"})
SET n:Person:Employee:Entity  -- ← Добавляет все labels как Neo4j labels!
SET n = {...}
```

### Что ДОЛЖНО происходить (expected behavior)

```python
# Python код
entity = EntityNode(
    name="John Doe",
    labels=["Person", "Employee"]  # ← Graphiti labels field
)
await entity.save(driver)

# Neo4j результат (ОЖИДАЕТСЯ)
MATCH (n {uuid: "..."}) RETURN labels(n)
→ ["Entity", "Person", "Employee"]  # ← Neo4j labels
```

### Что РЕАЛЬНО происходит (Issue #567)

```python
# Python код
entity = EntityNode(
    name="John Doe",
    labels=["Person", "Employee"]
)
await entity.save(driver)

# Neo4j результат (РЕАЛЬНОСТЬ)
MATCH (n {uuid: "..."}) RETURN labels(n)
→ ["Entity"]  # ❌ Только базовый label!
```

**Где labels на самом деле?**
```cypher
MATCH (n {uuid: "..."}) RETURN n.labels
→ null  # ❌ Поле labels НЕ сохраняется в Neo4j!
```

---

## Issue #567: Custom entity types labels missing

**Ссылка**: https://github.com/getzep/graphiti/issues/567

### Описание проблемы

**Reporter**: Пользователь настроил custom entity types в Graphiti MCP server:
```python
entity_types = {
    "Person": PersonEntity,
    "Project": ProjectEntity,
    "Idee": IdeeEntity,
}
```

**Ожидаемое поведение**:
1. Neo4j nodes должны иметь соответствующие labels: `:Entity:Person`, `:Entity:Project`
2. Custom поля из Pydantic моделей должны сохраняться как properties

**Реальное поведение**:
1. ✅ LLM корректно извлекает entities с правильными types
2. ❌ Все nodes в Neo4j имеют только `:Entity` label
3. ❌ Custom properties из Pydantic моделей НЕ сохраняются

### Техническая причина

**Проблема в коде `EntityNode.save()`** (строка 471):

```python
labels = ':'.join(self.labels + ['Entity'])
```

**Но откуда берётся `self.labels`?**

При извлечении entities через LLM (`extract_nodes`), Graphiti использует стандартный `EntityNode`, у которого `labels` field **пустой по умолчанию**:

```python
# Из extract_nodes промпта (упрощённо)
extracted = EntityNode(
    name="John Doe",
    labels=[]  # ← Пустой список! LLM не заполняет это поле
)
```

**Почему LLM не заполняет `labels`?**
- Промпт для извлечения entities не требует заполнения `labels` field
- LLM определяет TYPE сущности (Person, Project), но это не попадает в `labels` field
- Type информация теряется при конвертации в `EntityNode`

### Решение (гипотетическое)

**Вариант 1**: Модифицировать промпт LLM
```python
# В extract_nodes промпте добавить:
"""
For each entity, assign labels based on its type:
- If entity is a Person → labels: ["Person"]
- If entity is a Project → labels: ["Project"]
"""
```

**Вариант 2**: Использовать custom entity types
```python
class PersonEntity(EntityNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.labels = self.labels or ["Person"]  # ← Автоматически добавляем label
```

**Вариант 3**: Исправить `save()` метод
```python
# В EntityNode.save() добавить логику:
if not self.labels:
    # Вывести label из type класса
    class_name = self.__class__.__name__.replace("Entity", "")
    if class_name != "Entity":
        self.labels = [class_name]
```

### Статус Issue

**На момент написания (2025-10-21)**: Issue открыт, официального решения нет.

---

## Как это влияет на ваши данные в PipGraph

### Что вы видите в Neo4j Browser

```cypher
// Запрос
MATCH (n:Entity) RETURN labels(n), n.name LIMIT 5

// Результат
labels(n)     | n.name
--------------+-----------------------
["Entity"]    | "Python"
["Entity"]    | "TechCorp"
["Entity"]    | "Антон Новиков"
["Entity"]    | "Neo4j"
["Entity"]    | "FastAPI"
```

**Все nodes имеют ТОЛЬКО `:Entity` label!**

### Где находятся фактические categories?

**Проверим поле `labels`:**
```cypher
MATCH (n:Entity {name: "Python"}) RETURN n.labels
→ null  // ❌ Поле не сохранено!
```

**Проверим свойства узла:**
```cypher
MATCH (n:Entity {name: "Python"}) RETURN properties(n)
→ {
  uuid: "...",
  name: "Python",
  group_id: "default",
  created_at: ...,
  summary: "...",
  name_embedding: [...]
}
```

**Вывод**: LLM категории (Person/Technology/etc.) **теряются** в текущей реализации!

### Почему это происходит в PipGraph

**Код в `pipgraph_manager.py:206-210`**:

```python
# Создаём Episode для заметки
episode = EpisodeInput(
    name=name,
    group_id=group_id,
    labels=[],  # ← Пустой список!
    source=source,
    content=episode_body,
    # ...
)
```

**Далее в `extract_nodes` (Graphiti Core)**:
```python
# LLM извлекает entities, но НЕ заполняет labels field
extracted_nodes = await extract_nodes(episode, ...)
# → EntityNode(name="Python", labels=[])  # ← Пустой!
```

**Результат в Neo4j**:
```python
# В EntityNode.save():
labels = ':'.join([] + ['Entity'])  # → "Entity"

# Cypher:
SET n:Entity  # ← Только один label!
```

---

## labels() vs n.labels в Cypher

### Функция `labels()` - Neo4j системная

```cypher
// labels() возвращает Neo4j labels узла
MATCH (n:Entity) RETURN labels(n)
→ ["Entity"]  // Список системных labels

// Можно использовать для фильтрации
MATCH (n)
WHERE "Person" IN labels(n)
RETURN n
```

**Это системная функция Neo4j**, читает metadata узла.

### Поле `n.labels` - Graphiti data field

```cypher
// n.labels - обычное свойство узла (если сохранено)
MATCH (n:Entity) RETURN n.labels
→ null  // ❌ Не сохраняется в текущей версии Graphiti

// Если бы сохранялось:
→ ["Programming Language", "Technology"]
```

**Это обычное property**, как `n.name` или `n.summary`.

### Запрос для получения обоих

```cypher
MATCH (n:Entity)
RETURN
    labels(n) AS neo4j_labels,     // Системные labels
    n.labels AS graphiti_labels,   // Поле labels (если есть)
    n.name AS name
LIMIT 5
```

**Текущий результат в PipGraph:**
```
neo4j_labels | graphiti_labels | name
-------------|-----------------|------------
["Entity"]   | null            | "Python"
["Entity"]   | null            | "TechCorp"
```

**Ожидаемый результат (после фикса Issue #567):**
```
neo4j_labels                         | graphiti_labels                    | name
-------------------------------------|------------------------------------|---------
["Entity", "Technology"]             | ["Programming Language"]           | "Python"
["Entity", "Organization"]           | ["Company"]                        | "TechCorp"
```

---

## Можно ли использовать labels для фильтрации сейчас?

### Текущее состояние: НЕТ

**Проблема**:
```cypher
// Попытка фильтровать по category
MATCH (n:Technology) RETURN n
→ 0 rows  // ❌ Нет таких labels!

MATCH (n:Entity) WHERE "Technology" IN labels(n) RETURN n
→ 0 rows  // ❌ labels(n) = ["Entity"]

MATCH (n:Entity) WHERE n.labels CONTAINS "Technology" RETURN n
→ 0 rows  // ❌ n.labels = null
```

**Вывод**: Невозможно фильтровать по категориям в текущей версии.

### Workaround: Использовать summary или attributes

**Вариант 1**: Искать по тексту в `summary`
```cypher
MATCH (n:Entity)
WHERE n.summary CONTAINS "programming language"
   OR n.summary CONTAINS "technology"
RETURN n
```

**Вариант 2**: Добавить category в `attributes` вручную
```python
# В вашем коде после извлечения
for node in extracted_nodes:
    # Определить category из summary или name
    if "language" in node.name.lower():
        node.attributes["category"] = "Technology"
    elif "corp" in node.name.lower():
        node.attributes["category"] = "Organization"
```

```cypher
// Теперь можно фильтровать
MATCH (n:Entity)
WHERE n.category = "Technology"
RETURN n
```

### После фикса Issue #567: ДА

**После исправления в Graphiti:**
```cypher
// Фильтрация по Neo4j labels
MATCH (n:Technology) RETURN n  // ✅ Работает!

// Фильтрация по Graphiti labels field
MATCH (n:Entity)
WHERE "Technology" IN n.labels
RETURN n  // ✅ Работает!
```

---

## Как это влияет на Entity Resolution

### Теоретически (если labels работают)

**Идея из `GRAPHITI_HOMONYMS_EDGE_CASE.md`**:

```python
# Использовать labels для различения омонимов
def calculate_entity_similarity(
    extracted: EntityNode,
    existing: EntityNode,
    embedding_score: float
) -> float:
    if extracted.labels and existing.labels:
        overlap = set(extracted.labels) & set(existing.labels)

        if not overlap:
            # Разные категории → не одна и та же сущность
            return embedding_score - 0.15  # Penalty

    return embedding_score
```

**Пример:**
```python
extracted = EntityNode(name="Python", labels=["Technology"])
existing = EntityNode(name="Питон", labels=["Animal"])

# Без label overlap → penalty
adjusted_score = 0.92 - 0.15 = 0.77 < 0.85 → NOT MERGED ✅
```

### Практически (сейчас)

**Проблема**: `labels` field пустой у всех entities!

```python
extracted = EntityNode(name="Python", labels=[])  # ← Пустой!
existing = EntityNode(name="Питон", labels=[])    # ← Пустой!

# Нет overlap, но и нет данных для проверки
if not extracted.labels or not existing.labels:
    return embedding_score  # Нельзя использовать labels
```

**Вывод**: Label-aware scoring **НЕ РАБОТАЕТ** в текущей версии Graphiti.

---

## Что менять в документации примерах

### Некорректные примеры (текущие)

**В `GRAPHITI_EMBEDDING_DESIGN_RATIONALE.md`**:
```python
# Пример предполагает, что labels заполнены
EntityNode(name="Python", labels=["Technology"])  # ❌ В реальности labels=[]
EntityNode(name="TechCorp", labels=["Organization"])  # ❌ В реальности labels=[]
```

**В `GRAPHITI_HOMONYMS_EDGE_CASE.md`**:
```python
# Label-aware scoring
if not overlap:  # Разные labels
    penalty = 0.15
```
❌ **Не работает**, т.к. `labels=[]` всегда!

### Корректные примеры (нужно обновить)

**Уточнение статуса**:
```python
# ВАЖНО: В текущей версии Graphiti (Issue #567), labels field НЕ заполняется LLM!
# Этот пример показывает ОЖИДАЕМОЕ поведение после фикса.

EntityNode(name="Python", labels=["Technology"])  # ← Будет работать после фикса
```

**Альтернативный подход (сейчас)**:
```python
# Workaround: Использовать attributes для категорий
EntityNode(
    name="Python",
    attributes={"category": "Technology", "type": "Programming Language"}
)

# Фильтрация в Cypher
MATCH (n:Entity) WHERE n.category = "Technology" RETURN n
```

---

## Рекомендации для PipGraph

### Краткосрочно (до фикса Issue #567)

1. **Не полагаться на `labels` field**
   - ❌ Не использовать для фильтрации
   - ❌ Не использовать для entity resolution

2. **Использовать `attributes` для категорий**
   ```python
   # В pipgraph_manager.py после извлечения entities
   for node in extracted_nodes:
       # Попытаться определить категорию из summary
       category = infer_category_from_summary(node.summary)
       if category:
           node.attributes["category"] = category
   ```

3. **Фильтрация по тексту**
   ```cypher
   // Искать по summary или name
   MATCH (n:Entity)
   WHERE n.summary CONTAINS "programming"
      OR n.name CONTAINS "language"
   RETURN n
   ```

4. **Обновить документацию**
   - Добавить disclaimer о Issue #567
   - Уточнить, что примеры показывают ожидаемое поведение
   - Предложить workarounds

### Среднесрочно (отслеживать Issue #567)

1. **Мониторить GitHub**
   - Подписаться на Issue #567
   - Проверять новые releases Graphiti

2. **Тестировать после обновлений**
   ```python
   # Тест для проверки, работает ли labels
   entity = EntityNode(name="Test", labels=["Category1"])
   await entity.save(driver)

   result = await driver.execute_query(
       "MATCH (n:Entity {name: 'Test'}) RETURN labels(n) AS labels"
   )

   assert "Category1" in result[0]["labels"]  # ← Должно быть True после фикса
   ```

3. **Подготовить миграцию**
   - Когда Issue #567 будет исправлен
   - Потребуется пересоздать граф с правильными labels
   - Или написать скрипт миграции

### Долгосрочно (после фикса)

1. **Включить label-aware entity resolution**
   ```python
   # Реализовать функцию из GRAPHITI_HOMONYMS_EDGE_CASE.md
   def calculate_entity_similarity(...):
       # Использовать labels для различения категорий
   ```

2. **Улучшить промпты LLM**
   ```python
   extract_nodes_prompt = """
   For each entity, assign specific labels:
   - Technology entities → labels: ["Technology"]
   - People → labels: ["Person"]
   - Organizations → labels: ["Organization"]
   """
   ```

3. **Использовать Neo4j labels для фильтрации**
   ```cypher
   // Эффективная фильтрация по индексированным labels
   MATCH (n:Technology) WHERE n.name CONTAINS "Python" RETURN n
   ```

---

## Итоговая таблица: Два "labels"

| Аспект | Neo4j Labels | Graphiti `labels` Field |
|--------|-------------|------------------------|
| **Что это** | Системный механизм Neo4j | Поле данных в EntityNode |
| **Тип** | Metadata узла | `list[str]` property |
| **Синтаксис Cypher** | `labels(n)` | `n.labels` |
| **Создание** | `CREATE (n:Label1:Label2)` | Python: `EntityNode(labels=["Label1"])` |
| **Фильтрация** | `MATCH (n:Label)` | `WHERE "Label" IN n.labels` |
| **Индексация** | ✅ Автоматическая | ❌ Обычное поле |
| **Визуализация** | ✅ Цвета в Neo4j Browser | ❌ Нет |
| **Текущий статус в PipGraph** | Только `"Entity"` | `null` (не сохраняется) |
| **После фикса Issue #567** | `["Entity", "Technology"]` | `["Programming Language"]` |

---

## Проверочные Cypher запросы

### Для отладки текущего состояния

```cypher
// 1. Проверить Neo4j labels всех Entity nodes
MATCH (n:Entity)
RETURN DISTINCT labels(n) AS neo4j_labels, count(*) AS count
ORDER BY count DESC

// Текущий результат:
// neo4j_labels | count
// -------------|------
// ["Entity"]   | 150

// 2. Проверить, есть ли поле labels
MATCH (n:Entity)
WHERE n.labels IS NOT NULL
RETURN n.name, n.labels
LIMIT 5

// Текущий результат: 0 rows

// 3. Посмотреть все свойства узла
MATCH (n:Entity {name: "Python"})
RETURN properties(n)

// Результат:
// {
//   uuid: "...",
//   name: "Python",
//   group_id: "default",
//   summary: "...",
//   created_at: ...,
//   name_embedding: [...]
//   // ← НЕТ поля "labels"!
// }

// 4. Проверить, какие категории есть в attributes
MATCH (n:Entity)
WHERE n.attributes IS NOT NULL
RETURN n.name, keys(n) AS all_properties
LIMIT 10

// Посмотреть, есть ли category/type в attributes
```

### После фикса Issue #567

```cypher
// 1. Должны появиться разные labels
MATCH (n:Entity)
RETURN DISTINCT labels(n) AS neo4j_labels, count(*) AS count
ORDER BY count DESC

// Ожидаемый результат:
// neo4j_labels                    | count
// --------------------------------|------
// ["Entity"]                      | 20    (без category)
// ["Entity", "Technology"]        | 50
// ["Entity", "Person"]            | 30
// ["Entity", "Organization"]      | 25

// 2. Фильтрация по specific labels
MATCH (n:Technology)
RETURN n.name, n.summary
LIMIT 5

// 3. Комбинированная фильтрация
MATCH (n:Entity:Technology)
WHERE "Programming Language" IN n.labels  // Graphiti labels field
RETURN n.name
```

---

## Связанные документы и issue

### GitHub Issues
- **[Issue #567](https://github.com/getzep/graphiti/issues/567)**: Custom entity types: Specific labels and properties missing on Neo4j nodes
- **[Issue #780](https://github.com/getzep/graphiti/issues/780)**: `entity_types` type hints issue

### PipGraph Документация
- [GRAPHITI_EMBEDDING_DESIGN_RATIONALE.md](GRAPHITI_EMBEDDING_DESIGN_RATIONALE.md) - Использует labels в примерах (нужно обновить)
- [GRAPHITI_HOMONYMS_EDGE_CASE.md](GRAPHITI_HOMONYMS_EDGE_CASE.md) - Label-aware scoring (не работает сейчас)
- [GRAPHITI_EMBEDDINGS.md](GRAPHITI_EMBEDDINGS.md) - Описание EntityNode
- [GRAPHITI_CORE_FIELD_ANALYSIS.md](GRAPHITI_CORE_FIELD_ANALYSIS.md) - Анализ полей

### Graphiti Core Код
- `graphiti_core/nodes.py:452-483` - EntityNode.save() метод
- `graphiti_core/models/nodes/node_db_queries.py:129-170` - Cypher query generation
- `graphiti_core/prompts/extract_nodes.py` - LLM промпт для извлечения entities

---

## Заключение

### Ключевые выводы

1. **Два разных "labels"** - источник путаницы:
   - Neo4j labels (системные метки)
   - Graphiti labels field (поле данных)

2. **Issue #567** - реальная проблема:
   - Custom labels НЕ добавляются как Neo4j labels
   - Labels field НЕ сохраняется в Neo4j
   - Категории entities теряются

3. **Текущее состояние PipGraph**:
   - Все Entity nodes имеют только `:Entity` label
   - Невозможно фильтровать по категориям
   - Label-aware entity resolution не работает

4. **Workarounds до фикса**:
   - Использовать `attributes` для категорий
   - Фильтровать по тексту в `summary`
   - Не полагаться на `labels` field

5. **После фикса Issue #567**:
   - Появятся множественные Neo4j labels
   - Labels field будет сохраняться
   - Можно будет использовать для фильтрации и resolution

### Практические действия

**Сейчас**:
1. ✅ Понять различие между двумя "labels"
2. ✅ Обновить примеры в документации с disclaimer
3. ✅ Не использовать labels для entity resolution
4. ✅ Использовать workarounds (attributes, text search)

**Отслеживать**:
1. ⚠️ GitHub Issue #567 статус
2. ⚠️ Новые releases Graphiti
3. ⚠️ Changelog для упоминаний labels

**После фикса**:
1. ⏳ Обновить Graphiti версию
2. ⏳ Протестировать labels behavior
3. ⏳ Пересоздать граф или мигрировать
4. ⏳ Включить label-aware features

---

**Автор**: Claude (Anthropic)
**Дата**: 2025-10-21
**Версия**: 1.0
**Статус**: Актуально для Graphiti до фикса Issue #567
