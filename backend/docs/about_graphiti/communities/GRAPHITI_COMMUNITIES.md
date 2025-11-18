# Graphiti Community Detection - Механизм определения сообществ

> **Источник**: `graphiti_core/utils/maintenance/community_operations.py`
> **Версия анализа**: 2025-10-21

## Обзор

Graphiti использует механизм **автоматического обнаружения сообществ** (community detection) для группировки связанных сущностей (Entity) в граф-базе данных. Сообщества представляют собой кластеры тесно связанных сущностей, которые суммаризируются с помощью LLM для создания высокоуровневых представлений знаний.

## Архитектура системы сообществ

### Основные компоненты

1. **CommunityNode** - узел графа, представляющий сообщество
   - `name` - краткое описание сообщества (генерируется LLM)
   - `summary` - полная суммаризация всех сущностей сообщества
   - `group_id` - идентификатор группы (наследуется от сущностей)

2. **CommunityEdge** - связь HAS_MEMBER между сообществом и сущностью
   - `source_node_uuid` - UUID сообщества
   - `target_node_uuid` - UUID сущности-члена
   - `created_at` - время создания связи

3. **Алгоритм Label Propagation** - метод кластеризации графа

## Процесс определения сообществ

### 1. Извлечение кластеров (`get_community_clusters`)

**Входные данные**: список `group_ids` (опционально, если `None` - обрабатываются все группы)

**Алгоритм**:

```python
# Для каждого group_id:
1. Получить все Entity-узлы с данным group_id
2. Для каждого узла построить projection - граф соседей:
   - Найти все связи RELATES_TO с другими Entity в той же группе
   - Подсчитать количество рёбер между узлами (edge_count)
3. Применить алгоритм Label Propagation к projection
4. Получить список кластеров (списков UUID)
5. Загрузить EntityNode объекты для каждого кластера
```

**Cypher-запрос для построения projection**:
```cypher
MATCH (n:Entity {group_id: $group_id, uuid: $uuid})
      -[e:RELATES_TO]-
      (m:Entity {group_id: $group_id})
WITH count(e) AS count, m.uuid AS uuid
RETURN uuid, count
```

**Результат**: `list[list[EntityNode]]` - список кластеров сущностей

---

### 2. Label Propagation Algorithm (`label_propagation`)

**Описание**: Классический алгоритм обнаружения сообществ в графах, основанный на распространении меток.

**Принцип работы**:

```
1. Инициализация: каждый узел получает уникальную метку (community_id)
   community_map = {uuid: i for i, uuid in enumerate(projection.keys())}

2. Итеративное обновление:
   Для каждого узла:
   - Подсчитать, сколько соседей принадлежит каждому сообществу
     (с учётом веса рёбер - edge_count)
   - Выбрать сообщество с максимальной суммой весов
   - Если вес > 1: принять это сообщество
   - Иначе: выбрать сообщество с максимальным ID

3. Остановка: когда ни один узел не меняет сообщество

4. Формирование кластеров:
   Сгруппировать узлы по финальным меткам сообществ
```

**Код критической части**:
```python
for uuid, neighbors in projection.items():
    community_candidates: dict[int, int] = defaultdict(int)
    for neighbor in neighbors:
        # Суммируем веса рёбер для каждого кандидата-сообщества
        community_candidates[community_map[neighbor.node_uuid]] += neighbor.edge_count

    # Сортируем по весу (убывание)
    community_lst = [(count, community) for community, count in community_candidates.items()]
    community_lst.sort(reverse=True)

    candidate_rank, community_candidate = community_lst[0] if community_lst else (0, -1)

    # Условие принятия сообщества
    if community_candidate != -1 and candidate_rank > 1:
        new_community = community_candidate
    else:
        new_community = max(community_candidate, curr_community)
```

**Особенности реализации**:
- **Взвешенный граф**: учитывается количество рёбер между узлами (`edge_count`)
- **Порог активации**: сообщество принимается только если вес > 1
- **Разрешение конфликтов**: при равных весах выбирается сообщество с большим ID

---

### 3. Построение сообщества (`build_community`)

**Входные данные**:
- `llm_client` - клиент для работы с LLM
- `community_cluster` - список EntityNode из одного кластера
- `ensure_ascii` - флаг ASCII-безопасности

**Процесс**:

```python
1. Собрать summaries всех сущностей кластера
2. Иерархическая суммаризация (парами):
   while len(summaries) > 1:
       - Если нечётное количество - отложить один summary
       - Разбить summaries пополам
       - Параллельно суммаризировать пары (left, right) через LLM
       - Собрать новые summaries
       - Если был отложен summary - добавить обратно

3. Получить финальный summary (единственный оставшийся)
4. Сгенерировать name через LLM (краткое описание summary)
5. Создать CommunityNode с полученными данными
6. Создать CommunityEdge для каждой сущности кластера
```

**LLM-промпты**:

- **summarize_pair** (`prompts/summarize_nodes.py`):
  ```
  System: "You are a helpful assistant that combines summaries."
  User: "Synthesize the information from the following two summaries
         into a single succinct summary. Summaries must be under 250 words."
  ```

- **summary_description**:
  ```
  System: "You are a helpful assistant that describes provided contents
          in a single sentence."
  User: "Create a short one sentence description of the summary that
         explains what kind of information is summarized."
  ```

**Оптимизация**:
- Параллельная обработка пар через `semaphore_gather`
- Ограничение конкурентности: `MAX_COMMUNITY_BUILD_CONCURRENCY = 10`

---

### 4. Массовое построение сообществ (`build_communities`)

**Входные данные**: `driver`, `llm_client`, `group_ids`, `ensure_ascii`

**Процесс**:
```python
1. Получить все кластеры через get_community_clusters()
2. Параллельно построить сообщества для каждого кластера
   (с ограничением Semaphore(10))
3. Разделить результаты на CommunityNode и CommunityEdge списки
4. Вернуть (community_nodes, community_edges)
```

**Используется в**:
- Полная перестройка графа сообществ
- Batch-обработка новых данных

---

### 5. Инкрементальное обновление (`update_community`)

**Назначение**: Добавление новой сущности в существующее сообщество без полной пересборки.

**Процесс**:

```python
1. Определить сообщество для новой сущности (determine_entity_community):

   a) Проверить, есть ли уже связь (c:Community)-[:HAS_MEMBER]->(n:Entity)
      - Если да → вернуть это сообщество, is_new=False

   b) Найти сообщества соседних сущностей:
      MATCH (c:Community)-[:HAS_MEMBER]->(m:Entity)-[:RELATES_TO]-(n:Entity)

   c) Подсчитать частоту каждого сообщества (mode)
      - Выбрать сообщество с max_count
      - Если max_count == 0 → вернуть None

   d) Вернуть найденное сообщество, is_new=True

2. Если сообщество не найдено → вернуть пустые списки

3. Обновить summary сообщества:
   - Суммаризировать пару (entity.summary, community.summary)
   - Сгенерировать новый name через LLM

4. Если is_new == True:
   - Создать и сохранить CommunityEdge (HAS_MEMBER)

5. Обновить name_embedding для сообщества

6. Сохранить CommunityNode в базе

7. Вернуть ([community], [edges])
```

**Cypher-запрос для поиска сообществ соседей**:
```cypher
MATCH (c:Community)-[:HAS_MEMBER]->(m:Entity)
      -[:RELATES_TO]-(n:Entity {uuid: $entity_uuid})
RETURN c.uuid, c.name, c.summary, c.group_id, ...
```

**Стратегия выбора сообщества**:
- **Мода (mode)** - выбирается сообщество, которое встречается чаще всего среди соседей
- Это эвристика для минимизации количества "мостовых" узлов между сообществами

---

## Вспомогательные операции

### `remove_communities(driver)`
Удаляет все Community-узлы из графа:
```cypher
MATCH (c:Community)
DETACH DELETE c
```

**Используется перед**: полной пересборкой сообществ

---

## Интеграция с PipGraph

### Использование в PipGraphManager

```python
# backend/app/services/pipgraph_manager.py
async def process_note(self, note: Note) -> ProcessingResult:
    # ... обработка заметки ...

    # Обновление сообществ происходит автоматически
    # через graphiti.add_episode() -> maintenance tasks
```

### Maintenance цикл Graphiti

Community detection запускается во время **фоновых задач обслуживания** (`maintenance`):

1. **После добавления эпизода** (`add_episode`):
   - Создаются новые Entity и Edge
   - Запускается `update_community` для новых сущностей

2. **Периодическая пересборка**:
   - `build_communities()` - полное пересоздание сообществ
   - Используется при значительных изменениях графа

---

## Особенности работы с Neo4j

### Поддержка разных провайдеров

Код адаптируется под разные графовые БД:

**Neo4j** (стандартный):
```cypher
MATCH (n:Entity)-[e:RELATES_TO]-(m:Entity)
```

**Kuzu** (специфичная модель):
```cypher
MATCH (n:Entity)-[:RELATES_TO]-(e:RelatesToNode_)-[:RELATES_TO]-(m:Entity)
```

**Neptune** (AWS):
```cypher
UNWIND $duplicate_node_uuids AS duplicate_tuple
MATCH (n:Entity {uuid: duplicate_tuple.source})
      -[r:RELATES_TO {name: 'IS_DUPLICATE_OF'}]->
      (m:Entity {uuid: duplicate_tuple.target})
```

---

## Ограничения и компромиссы

### 1. Статические сообщества
- **Проблема**: Кластеры определяются алгоритмом, не учитывают семантику
- **Следствие**: Сущности могут попасть в "неправильное" сообщество

### 2. Порог активации (edge_count > 1)
- **Цель**: Фильтрация слабых связей
- **Риск**: Изолированные сущности (1-2 связи) не формируют сообщества

### 3. Парная суммаризация (pairwise)
- **Преимущество**: Параллелизм, контроль размера промпта
- **Недостаток**: Потеря контекста при многих итерациях

### 4. LLM-зависимость
- **Критично**: summary и name генерируются LLM
- **Стоимость**: O(N * log N) LLM-вызовов для N сущностей
- **Качество**: Зависит от качества промптов и модели

### 5. Конкурентность
- **Ограничение**: `MAX_COMMUNITY_BUILD_CONCURRENCY = 10`
- **Причина**: Ограничение rate limits LLM API

---

## Производительность

### Сложность алгоритмов

| Операция | Временная сложность | Пространство |
|----------|---------------------|--------------|
| `label_propagation` | O(I * E) | O(N) |
| `build_community` | O(N * log N) LLM | O(N) |
| `build_communities` | O(C * N * log N) LLM | O(C * N) |
| `update_community` | O(D + 2) LLM | O(D) |

Где:
- **I** - количество итераций (обычно 3-10)
- **E** - количество рёбер в графе
- **N** - размер кластера
- **C** - количество кластеров
- **D** - степень узла (количество соседей)

### Оптимизации

1. **Параллельная суммаризация пар**: `semaphore_gather`
2. **Кэширование projection**: не пересчитывается для одного `group_id`
3. **Инкрементальное обновление**: `update_community` вместо полной пересборки
4. **Semaphore для LLM**: предотвращает перегрузку API

---

## Примеры использования

### 1. Полная пересборка сообществ

```python
from graphiti_core.utils.maintenance.community_operations import (
    build_communities,
    remove_communities
)

# Удалить старые сообщества
await remove_communities(driver)

# Построить новые сообщества для всех групп
community_nodes, community_edges = await build_communities(
    driver=driver,
    llm_client=llm_client,
    group_ids=None,  # Все группы
    ensure_ascii=True
)

# Сохранить в базу
for node in community_nodes:
    await node.save(driver)

for edge in community_edges:
    await edge.save(driver)
```

### 2. Добавление новой сущности в сообщество

```python
from graphiti_core.utils.maintenance.community_operations import update_community

# После создания новой EntityNode
entity = EntityNode(
    name="Новая сущность",
    summary="Описание сущности",
    group_id="group_123"
)
await entity.save(driver)

# Автоматическое добавление в подходящее сообщество
communities, edges = await update_community(
    driver=driver,
    llm_client=llm_client,
    embedder=embedder,
    entity=entity,
    ensure_ascii=True
)

if communities:
    print(f"Сущность добавлена в сообщество: {communities[0].name}")
else:
    print("Подходящее сообщество не найдено")
```

### 3. Получение кластеров для анализа

```python
from graphiti_core.utils.maintenance.community_operations import get_community_clusters

# Получить кластеры для конкретной группы
clusters = await get_community_clusters(
    driver=driver,
    group_ids=["group_123"]
)

# Анализ размеров кластеров
for i, cluster in enumerate(clusters):
    print(f"Кластер {i}: {len(cluster)} сущностей")
    for entity in cluster[:3]:  # Первые 3
        print(f"  - {entity.name}")
```

---

## Рекомендации по использованию в PipGraph

### 1. Стратегия обновления

**Real-time обновление** (текущий подход):
- Использовать `update_community` после каждой обработки заметки
- **Плюс**: Актуальность данных
- **Минус**: Множественные LLM-вызовы

**Batch обновление** (рекомендация):
```python
# Накапливать изменения
new_entities = []
# ... обработка заметок ...

# Периодическая пересборка (раз в час/день)
if should_rebuild_communities():
    await remove_communities(driver)
    await build_communities(driver, llm_client, group_ids)
```

### 2. Мониторинг качества

```python
# Проверка размеров сообществ
query = """
MATCH (c:Community)-[:HAS_MEMBER]->(e:Entity)
RETURN c.name, count(e) AS size
ORDER BY size DESC
"""
records, _, _ = await driver.execute_query(query)

for record in records:
    if record['size'] < 3:
        logger.warning(f"Малое сообщество: {record['c.name']}")
    elif record['size'] > 50:
        logger.warning(f"Слишком большое сообщество: {record['c.name']}")
```

### 3. Оптимизация LLM-вызовов

```python
# Кэширование суммари для неизменных сущностей
# (реализовать в PipGraphManager)

cache = {}  # entity.uuid -> community_uuid

async def update_with_cache(entity):
    if entity.uuid in cache:
        # Проверить, изменилась ли сущность
        if not entity.has_changed():
            return cache[entity.uuid]

    communities, _ = await update_community(...)
    if communities:
        cache[entity.uuid] = communities[0].uuid
    return communities
```

---

## Дальнейшие исследования

1. **Альтернативные алгоритмы кластеризации**:
   - Louvain algorithm (лучшая модулярность)
   - Leiden algorithm (более стабильные сообщества)
   - GNN-based clustering (учёт семантики)

2. **Гибридный подход**:
   - Структурная кластеризация (Label Propagation)
   - Семантическая кластеризация (embedding similarity)
   - Комбинация обоих методов

3. **Адаптивные пороги**:
   - Вместо фиксированного `edge_count > 1`
   - Использовать статистику графа (медиана, квантили)

4. **Иерархические сообщества**:
   - Создание мета-сообществ (сообществ сообществ)
   - Многоуровневая структура знаний

---

## Связанные файлы

- `graphiti_core/utils/maintenance/community_operations.py` - основной модуль
- `graphiti_core/utils/maintenance/edge_operations.py` - вспомогательные операции
- `graphiti_core/prompts/summarize_nodes.py` - промпты для LLM
- `graphiti_core/nodes.py` - определение CommunityNode
- `graphiti_core/edges.py` - определение CommunityEdge

---

## Заключение

Механизм определения сообществ в Graphiti представляет собой комбинацию:

1. **Классического графового алгоритма** (Label Propagation) для структурной кластеризации
2. **LLM-обработки** для семантической суммаризации кластеров
3. **Инкрементальных обновлений** для эффективной работы в реальном времени

Система эффективно работает для средних графов (тысячи узлов), но требует оптимизации LLM-вызовов для больших объёмов данных. В контексте PipGraph рекомендуется использовать batch-обновления сообществ для снижения затрат на API.
