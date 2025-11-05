# Архитектурное Решение: Ранняя Классификация PARA

**Дата**: 2025-10-27
**Статус**: Proposed → Approved
**Контекст**: [01_PROBLEM_STATEMENT.md](./01_PROBLEM_STATEMENT.md)

---

## Обзор Решения

Переносим классификацию PARA-типов на **ранний этап** обработки заметки - **до создания EpisodicNode**. Классификация становится отдельным этапом с собственным LLM-вызовом, результат сохраняется в `labels` поле эпизода.

### Архитектурная Диаграмма

```
┌─────────────────────────────────────────────────────────────┐
│                    process_note()                           │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  НОВЫЙ ЭТАП: classify_note_as_para()                        │
│  ┌────────────────────────────────────────────┐             │
│  │ LLM Call: Analyze full note                │             │
│  │ Input: episode_body, name                  │             │
│  │ Context: PARA docstrings                   │             │
│  │ Output: (para_type, attributes, confidence)│             │
│  └────────────────────────────────────────────┘             │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Create EpisodicNode                                        │
│  ┌────────────────────────────────────────────┐             │
│  │ labels = [para_type] if para_type else []  │ ← KEY!     │
│  │ Store para_attributes in metadata          │             │
│  └────────────────────────────────────────────┘             │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  extract_nodes()                                            │
│  ┌────────────────────────────────────────────┐             │
│  │ entity_types = БАЗОВЫЕ (БЕЗ PARA!)         │ ← CHANGE!  │
│  │ Извлекает: Person, Task, Organization...   │             │
│  │ НЕ извлекает: Project, Area, Resource...   │             │
│  └────────────────────────────────────────────┘             │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  resolve_extracted_nodes()                                  │
│  ┌────────────────────────────────────────────┐             │
│  │ Учитывает episode.labels (PARA context)    │ ← ENHANCE! │
│  └────────────────────────────────────────────┘             │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  extract_edges()                                            │
│  ┌────────────────────────────────────────────┐             │
│  │ edge_type_map: РАСШИРЕННЫЙ с PARA↔Entity   │ ← CHANGE!  │
│  │ custom_prompt: PARA-specific instructions  │ ← NEW!     │
│  └────────────────────────────────────────────┘             │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Save to graph                                              │
│  - EpisodicNode has PARA label                              │
│  - Rich PARA-aware edges                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Ключевые Архитектурные Решения

### AD-1: Отдельный Метод Классификации

**Решение**: Создать `classify_note_as_para()` как **отдельный метод** в `PipGraphManager`.

**Обоснование**:
- Разделение ответственности (SRP): классификация vs извлечение сущностей
- Возможность переиспользования (будущий API endpoint для реклассификации)
- Легче тестировать изолированно
- Можно кешировать результаты для оптимизации

**Альтернативы отклонены**:
- ❌ Встроить в `extract_nodes`: Смешение уровней абстракции
- ❌ Сделать pre-processing вне `PipGraphManager`: Потеря контекста

**Сигнатура**:
```python
async def classify_note_as_para(
    self,
    episode_body: str,
    name: str,
    source_description: str | None = None,
) -> tuple[str | None, dict, float]:
    """
    Classify entire note as PARA type using LLM.

    Returns:
        (para_type, attributes, confidence)
        - para_type: "Project" | "Area" | "Resource" | "Archive" | None
        - attributes: Extracted PARA-specific attributes
        - confidence: 0.0-1.0, how confident LLM is
    """
```

---

### AD-2: PARA Label в EpisodicNode

**Решение**: Использовать `labels` поле `EpisodicNode` для хранения PARA-типа.

**Обоснование**:
- Neo4j native: labels - это первоклассный концепт в Neo4j
- Быстрый поиск: `MATCH (e:EpisodicNode:Project)` очень эффективен
- Graphiti поддерживает: `EpisodicNode.labels: list[str]`
- Семантическая ясность: label = type of entity

**Структура**:
```python
episode = EpisodicNode(
    name="Launch Q4 Campaign",
    labels=["Project"],  # ← PARA type здесь!
    source=EpisodeType.text,
    content=episode_body,
    # ... остальные поля
)
```

**Альтернативы отклонены**:
- ❌ Использовать `name` prefix: "Project: Launch..." - нарушает UX
- ❌ Хранить в attributes: Не используем native Neo4j labels
- ❌ Создавать отдельный узел ParaNode: Дублирование, усложнение

---

### AD-3: Удаление PARA из entity_types

**Решение**: При `use_para_entities=True` НЕ передавать PARA в `entity_types` для `extract_nodes`.

**Обоснование**:
- Уменьшение контекста: -500 строк docstrings из LLM промпта
- Фокус LLM: только на извлечении конкретных сущностей
- Избежание дублирования: PARA уже определен на предыдущем этапе

**Реализация**:
```python
# pipgraph_manager.py
if use_para_entities:
    # НЕ добавляем PARA в entity_types
    if entity_types is None:
        entity_types = {}  # Или базовые типы: Person, Task, Organization

    # PARA edge_types и edge_type_map остаются для extract_edges
    if edge_types is None:
        edge_types = PARA_EDGE_TYPES

    if edge_type_map is None:
        edge_type_map = PARA_EDGE_TYPE_MAP_EXTENDED  # ← Расширенная версия
```

**Вопрос**: А если пользователь хочет И PARA, И кастомные entity types?

**Ответ**:
```python
# Если пользователь передал свои entity_types, не трогаем их
if use_para_entities and entity_types is None:
    # Используем только базовые, без PARA
    entity_types = {}
```

---

### AD-4: Расширенный edge_type_map

**Решение**: Создать `PARA_EDGE_TYPE_MAP_EXTENDED` с полным набором PARA ↔ Entity связей.

**Обоснование**:
- Семантическое богатство: Каждая связь имеет смысл
- Контекстная релевантность: LLM выбирает подходящий тип на основе PARA контекста
- Расширяемость: Легко добавлять новые типы связей

**Структура** (см. детали в [04_EDGE_ENRICHMENT.md](./04_EDGE_ENRICHMENT.md)):
```python
PARA_EDGE_TYPE_MAP_EXTENDED: dict[tuple[str, str], list[str]] = {
    # ====== PARA ↔ PARA ======
    ("Project", "Area"): ["ContributesTo", "SpawnedFrom"],
    ("Project", "Resource"): ["UsesResource"],
    ("Area", "Resource"): ["UsesResource"],
    ("Area", "Project"): ["SpawnedFrom"],  # Reverse

    # ====== PARA ↔ Entity ======
    ("Project", "Person"): ["MENTIONS", "AssignedTo", "LeadBy"],
    ("Project", "Organization"): ["MENTIONS", "PartnersWith"],
    ("Project", "Task"): ["CONTAINS"],

    ("Area", "Person"): ["MENTIONS", "ManagedBy"],
    ("Area", "Task"): ["CONTAINS"],

    ("Resource", "Person"): ["MENTIONS", "AuthoredBy"],
    ("Resource", "Source"): ["REFERENCES"],

    # ====== Entity ↔ PARA (Reverse) ======
    ("Person", "Project"): ["WorksOn", "Leads"],
    ("Person", "Area"): ["Manages", "ResponsibleFor"],

    ("Task", "Project"): ["BelongsTo"],
    ("Task", "Area"): ["BelongsTo"],

    # ====== Fallback ======
    ("Entity", "Entity"): ["RELATES_TO", "MENTIONS"],
}
```

**Принципы дизайна**:
1. Двунаправленность: Если есть `(A, B)`, добавить и `(B, A)` если семантически оправдано
2. Специфичность: Конкретные типы предпочтительнее `RELATES_TO`
3. Расширяемость: Структура позволяет добавлять новые типы без изменения кода

---

### AD-5: PARA-Контекст для extract_edges

**Проблема**: `extract_edges` не принимает `custom_prompt` как параметр функции.

**Решение (Поэтапный Подход)**:

#### Этап 1 (MVP): Hack через previous_episodes

```python
# Внедрить PARA-инструкции в контекст через episode content
para_instructions = build_para_edge_instructions(para_type)

# Создать "виртуальный" эпизод с инструкциями
instruction_episode = EpisodicNode(
    name="_PARA_CONTEXT_",
    content=para_instructions,
    ...
)

# Передать в previous_episodes
previous_episodes_with_context = previous_episodes + [instruction_episode]

extracted_edges = await extract_edges(
    ...
    previous_episodes=previous_episodes_with_context,  # ← Hack!
    ...
)
```

**Pros**: Не требует изменения graphiti, работает сейчас
**Cons**: Хрупкое решение, может сломаться при апдейте

#### Этап 2 (Production): Wrapper функция

```python
# app/services/para_edge_extractor.py

async def extract_edges_with_para_context(
    clients: GraphitiClients,
    episode: EpisodicNode,
    nodes: list[EntityNode],
    previous_episodes: list[EpisodicNode],
    edge_type_map: dict,
    para_type: str | None,
    **kwargs
) -> list[EntityEdge]:
    """
    Wrapper around graphiti's extract_edges with PARA context injection.
    """
    # Внедрить PARA контекст
    if para_type:
        custom_context = build_para_edge_instructions(para_type)
        # Добавить в episode content или previous_episodes

    # Вызвать оригинальную функцию
    return await extract_edges(clients, episode, nodes, previous_episodes, ...)
```

**Pros**: Чистое решение, изолированная логика
**Cons**: Требует рефакторинга

#### Этап 3 (Future): Vendor graphiti

Если хак не работает надежно:
1. Скопировать `extract_edges` из graphiti в локальный модуль
2. Добавить параметр `custom_prompt: str = ""`
3. Использовать свою версию

**Решение для MVP**: Используем Этап 1 (hack), готовимся к Этапу 2 (wrapper).

---

### AD-6: Хранение PARA Attributes

**Решение**: Сохранять извлеченные PARA-атрибуты в **metadata эпизода**.

**Обоснование**:
- Полнота данных: Не теряем результат классификации
- Возможность анализа: Можно строить аналитику на основе дедлайнов, review_frequency и т.д.
- Будущее использование: API для поиска Projects по deadline

**Структура**:
```python
# После classify_note_as_para
para_type, para_attrs, confidence = await self.classify_note_as_para(...)

# Сохранить в episode (создать кастомное поле или использовать встроенное)
episode = EpisodicNode(
    name=name,
    labels=[para_type] if para_type else [],
    # Опция 1: Добавить в content (не идеально)
    # Опция 2: Использовать кастомное поле (требует расширения модели)
    # Опция 3: Сохранить в отдельный атрибут после создания
    ...
)

# После сохранения эпизода, добавить attributes как свойства узла
await self.driver.execute_query(
    """
    MATCH (e:EpisodicNode {uuid: $uuid})
    SET e += $attributes
    """,
    uuid=episode.uuid,
    attributes=para_attrs
)
```

**Альтернативы**:
- ❌ Не сохранять: Потеря данных
- ❌ Создавать отдельный узел ParaNode: Усложнение

**Выбранный подход**: Сохранять как properties узла EpisodicNode через отдельный запрос.

---

### AD-7: Обратная Совместимость

**Требование**: Решение не должно ломать существующий функционал.

**Реализация**:
```python
async def process_note(
    self,
    ...,
    use_para_entities: bool = True,  # По умолчанию включено
    enable_early_para_classification: bool = True,  # ← НОВЫЙ параметр
):
    """
    Parameters:
        enable_early_para_classification: If True, classify note as PARA before extract_nodes.
                                          If False, use old behavior (PARA in entity_types).
    """

    para_type = None
    para_attrs = {}

    if use_para_entities and enable_early_para_classification:
        # НОВОЕ поведение: ранняя классификация
        para_type, para_attrs, _ = await self.classify_note_as_para(...)
        # НЕ добавляем PARA в entity_types
        entity_types = entity_types or {}

    elif use_para_entities and not enable_early_para_classification:
        # СТАРОЕ поведение: PARA в entity_types
        entity_types = entity_types or PARA_ENTITY_TYPES

    else:
        # Без PARA вообще
        entity_types = entity_types or {}
```

**Тестирование**:
- `use_para_entities=False` → Без PARA (как раньше)
- `use_para_entities=True, enable_early_para_classification=False` → Старое PARA поведение
- `use_para_entities=True, enable_early_para_classification=True` → Новое поведение

---

## Детали Реализации

### Модуль classify_note_as_para

**Файл**: `app/services/pipgraph_manager.py`

**Логика**:
1. Построить prompt с PARA docstrings
2. Вызвать LLM через `self.clients.llm_client`
3. Распарсить JSON-ответ
4. Валидировать confidence threshold
5. Вернуть результат

**Промпт** (упрощенная версия, детали в [03_CLASSIFICATION_FLOW.md](./03_CLASSIFICATION_FLOW.md)):
```
You are a PARA classification expert. Analyze the following note and determine its PARA type.

PARA Types:
{docstrings from Project, Area, Resource, Archive}

Note Title: {name}
Note Content: {episode_body}
Source: {source_description}

Return JSON:
{
  "para_type": "Project" | "Area" | "Resource" | "Archive" | null,
  "attributes": { ... extracted attributes ... },
  "confidence": 0.85,
  "reasoning": "This note describes a time-bound goal with a deadline..."
}
```

---

### Модификация process_note

**Файл**: `app/services/pipgraph_manager.py`

**Изменения**:

**До** (строки 241-254):
```python
episode = (
    await EpisodicNode.get_by_uuid(self.driver, uuid)
    if uuid is not None
    else EpisodicNode(
        name=name,
        group_id=group_id,
        labels=[],  # ← Пусто
        source=source,
        content=episode_body,
        ...
    )
)
```

**После**:
```python
# НОВЫЙ ШАГ: Классификация
para_type = None
para_attrs = {}
if use_para_entities and enable_early_para_classification:
    para_type, para_attrs, confidence = await self.classify_note_as_para(
        episode_body, name, source_description
    )
    logger.info(f"Note classified as: {para_type} (confidence: {confidence:.2f})")

# Создание эпизода с PARA label
episode = (
    await EpisodicNode.get_by_uuid(self.driver, uuid)
    if uuid is not None
    else EpisodicNode(
        name=name,
        group_id=group_id,
        labels=[para_type] if para_type else [],  # ← PARA type!
        source=source,
        content=episode_body,
        ...
    )
)

# Сохранить PARA attributes (после создания эпизода в БД)
if para_type and para_attrs:
    await self._store_para_attributes(episode.uuid, para_attrs)
```

---

### Новая конфигурация edge_type_map

**Файл**: `config/para_config.py`

**Добавить**:
```python
# Расширенная версия с PARA ↔ Entity связями
PARA_EDGE_TYPE_MAP_EXTENDED: dict[tuple[str, str], list[str]] = {
    # ... полный набор связей
}

# Функция для выбора правильной версии
def get_edge_type_map(extended: bool = True) -> dict:
    """Get edge type map (extended or basic PARA)."""
    return PARA_EDGE_TYPE_MAP_EXTENDED if extended else PARA_EDGE_TYPE_MAP
```

---

## Риски и Митигации

### Риск 1: Ошибочная Классификация

**Описание**: LLM неправильно определяет PARA-тип заметки.

**Вероятность**: Средняя (10-15% случаев)

**Влияние**: Среднее (неправильный label, но не критично)

**Митигация**:
1. Использовать confidence threshold (≥ 0.6)
2. Логировать все классификации для анализа
3. Добавить возможность ручной реклассификации (API endpoint)
4. Тестировать на большом датасете заметок

### Риск 2: Увеличение Времени Обработки

**Описание**: Дополнительный LLM-вызов замедляет процесс.

**Вероятность**: Высокая (обязательно произойдет)

**Влияние**: Низкое (если оверхед < 20%)

**Митигация**:
1. Использовать быструю модель для классификации (gpt-4o-mini)
2. Кешировать результаты для повторных обработок
3. Параллелизировать где возможно
4. Оптимизировать промпт (короче = быстрее)

### Риск 3: Хак с custom_prompt Хрупкий

**Описание**: Hack через previous_episodes может сломаться при апдейте graphiti.

**Вероятность**: Средняя (зависит от graphiti roadmap)

**Влияние**: Высокое (потеря PARA-контекста в edges)

**Митигация**:
1. Закрепить версию graphiti (не auto-update)
2. Покрыть тестами behaviour извлечения edges с PARA контекстом
3. Подготовить Этап 2 (wrapper) заранее
4. Мониторить graphiti releases

### Риск 4: Конфликт с Пользовательскими entity_types

**Описание**: Если пользователь передал свои entity_types, может быть неожиданное поведение.

**Вероятность**: Низкая (редкий use case)

**Влияние**: Среднее (путаница в API)

**Митигация**:
1. Четко документировать поведение:
   - `use_para_entities=True, entity_types=None` → Используем базовые без PARA
   - `use_para_entities=True, entity_types={...}` → Используем переданные без модификации
2. Добавить валидацию и предупреждения в логи

---

## Альтернативные Архитектуры (Рассмотрены и Отклонены)

### Альтернатива A: PARA как Пост-обработка

**Идея**: Классифицировать заметку ПОСЛЕ extract_nodes на основе извлеченных сущностей.

**Pros**:
- Не нужен отдельный LLM-вызов
- Можно использовать извлеченные attributes для классификации

**Cons**:
- ❌ Слишком поздно для влияния на extract_edges
- ❌ Потеря контекста (уже разбили заметку на сущности)
- ❌ Хуже accuracy (меньше информации для классификации)

**Решение**: Отклонена.

---

### Альтернатива B: PARA как Мета-Entity

**Идея**: Создавать отдельный узел ParaNode, связанный с EpisodicNode.

```
(EpisodicNode) -[:HAS_TYPE]-> (ParaNode:Project)
```

**Pros**:
- Разделение concerns (episode vs classification)
- Можно добавить несколько классификаций

**Cons**:
- ❌ Усложнение графа (лишний узел)
- ❌ Не используем native labels
- ❌ Медленнее запросы (нужен JOIN)

**Решение**: Отклонена.

---

### Альтернатива C: PARA в Name Prefix

**Идея**: Добавлять префикс к имени заметки: "Project: Launch Q4 Campaign".

**Pros**:
- Нет изменений в структуре данных
- Видно тип прямо в имени

**Cons**:
- ❌ Нарушает UX (пользователь видит "Project:" в Obsidian)
- ❌ Хрупкое парсинг ("Project:" vs "project:" vs "[Project]")
- ❌ Не используем Neo4j labels

**Решение**: Отклонена.

---

## Связанные Документы

- **Следующий шаг**: [03_CLASSIFICATION_FLOW.md](./03_CLASSIFICATION_FLOW.md) - Детали промпта и логики классификации
- **Edge enrichment**: [04_EDGE_ENRICHMENT.md](./04_EDGE_ENRICHMENT.md) - Полный edge_type_map
- **Реализация**: [05_IMPLEMENTATION_PLAN.md](./05_IMPLEMENTATION_PLAN.md) - Пошаговый план кода

---

## Вопросы и Ответы

**Q: Что если заметка одновременно Project И Resource?**

A: Выбираем доминирующий тип на основе ключевых маркеров:
- Если есть deadline → Project
- Если нет deadline, но есть goal → Area
- Если чисто справочная → Resource

Вторичный тип можно добавить в metadata: `secondary_type: "Resource"`.

---

**Q: Нужно ли реклассифицировать существующие заметки?**

A: Опционально. Существующие заметки без PARA label продолжат работать. Для миграции см. [07_MIGRATION_GUIDE.md](./07_MIGRATION_GUIDE.md).

---

**Q: Как быть с очень длинными заметками (>10k токенов)?**

A: Использовать truncation strategy:
1. Брать first 500 tokens (summary обычно вначале)
2. + Last 200 tokens (часто выводы или metadata)
3. Если есть явные маркеры (## Deadline, ## Goal), извлечь их контекст

---

**Q: Можно ли использовать более дешевую модель для классификации?**

A: Да! Классификация проще, чем извлечение сущностей. Можно использовать:
- gpt-4o-mini (дешевле и быстрее)
- claude-3-haiku
- Даже fine-tuned модель на основе датасета классифицированных заметок

---

## Финальная Оценка Решения

| Критерий | Оценка | Комментарий |
|----------|--------|-------------|
| **Separation of Concerns** | ✅ Отлично | PARA классификация изолирована |
| **Performance** | ⚠️ Хорошо | +500ms на классификацию, но -300ms на extract_nodes |
| **Maintainability** | ✅ Отлично | Чистая архитектура, легко расширять |
| **Backward Compatibility** | ✅ Отлично | `enable_early_para_classification` flag |
| **Robustness** | ⚠️ Хорошо | Hack с custom_prompt требует мониторинга |
| **Testability** | ✅ Отлично | Каждый этап тестируется отдельно |

**Общая оценка**: ✅ **Рекомендуется к реализации**

---

**Утверждено**: 2025-10-27
**Следующий шаг**: Детализация промпта в [03_CLASSIFICATION_FLOW.md](./03_CLASSIFICATION_FLOW.md)
