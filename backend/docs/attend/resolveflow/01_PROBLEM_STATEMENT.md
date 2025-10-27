# Постановка Проблемы: Ранняя Классификация PARA-Сущностей

**Дата**: 2025-10-27
**Автор**: Система PipGraph
**Контекст**: Оптимизация процесса извлечения PARA-сущностей из заметок

---

## Текущее Состояние (As-Is)

### Как работает сейчас

В текущей реализации PARA entity types (`Project`, `Area`, `Resource`, `Archive`) обрабатываются на этапе **extract_nodes** вместе с другими типами сущностей (`Person`, `Organization`, `Task`, etc.):

```python
# pipgraph_manager.py:209-220
if use_para_entities:
    if entity_types is None:
        entity_types = PARA_ENTITY_TYPES  # Включает Project, Area, Resource, Archive
        logger.info("Using default PARA entity types...")
```

**Поток обработки**:
```
1. Создание EpisodicNode (labels=[])
   ↓
2. extract_nodes(entity_types=PARA_ENTITY_TYPES + другие)
   - LLM анализирует текст
   - Извлекает Person, Organization, Task...
   - И ТАКЖЕ пытается классифицировать Project, Area, Resource, Archive
   ↓
3. resolve_extracted_nodes()
   ↓
4. extract_edges(edge_type_map, edge_types)
   - На этом этапе уже слишком поздно влиять на контекст
   ↓
5. Сохранение в граф
```

### Проблемы текущего подхода

#### 1. **Смешение уровней абстракции**

PARA-типы - это **высокоуровневая классификация всей заметки**:
- Project: "Запуск маркетинговой кампании Q4"
- Area: "Личное здоровье и фитнес"
- Resource: "Руководство по Python asyncio"

В то время как другие entity types - это **локальные сущности внутри заметки**:
- Person: "Владимир Иванов"
- Task: "Подготовить презентацию к 01.11"
- Organization: "ООО ТехноСфера"

LLM пытается одновременно решить две разные задачи:
- "Что это за заметка в целом?" (PARA классификация)
- "Какие конкретные сущности упомянуты?" (entity extraction)

#### 2. **Потеря контекста для extract_edges**

Когда мы доходим до этапа `extract_edges`, LLM уже не знает, что это заметка типа `Project` или `Area`. Поэтому он:
- Не может приоритизировать правильные типы связей
- Пропускает семантически значимые PARA-специфичные связи:
  - `(Project) -[:CONTRIBUTES_TO]-> (Area)`
  - `(Project) -[:USES]-> (Resource)`
  - `(Task) -[:BELONGS_TO]-> (Project)`

**Пример**: Заметка "Запуск продукта Q4" содержит задачи, людей, дедлайн.
- Текущий подход: LLM создает только `MENTIONS` и `RELATES_TO` между сущностями
- Желаемое: Знать, что это `Project`, и создавать `ASSIGNED_TO`, `CONTRIBUTES_TO`

#### 3. **Неэффективное использование label у EpisodicNode**

```python
# pipgraph_manager.py:244-253
episode = EpisodicNode(
    name=name,
    labels=[],  # ← Пусто! Не используем возможность маркировать эпизод
    source=source,
    content=episode_body,
    ...
)
```

Neo4j и Graphiti поддерживают labels для узлов, но мы не используем эту возможность для явной маркировки типа заметки.

**Упущенные возможности**:
- Быстрый поиск всех Project-заметок: `MATCH (e:EpisodicNode:Project)`
- Фильтрация по типу при поиске
- Явная типизация в графе

#### 4. **Перегрузка entity_types**

Файл `para_config.py:35-40`:
```python
PARA_ENTITY_TYPES: dict[str, type[BaseModel]] = {
    "Project": Project,    # 130+ строк docstring
    "Area": Area,          # 130+ строк docstring
    "Resource": Resource,  # 130+ строк docstring
    "Archive": Archive,    # 130+ строк docstring
}
```

Каждый раз при вызове `extract_nodes` LLM получает **~500 строк** PARA docstrings в контексте, даже если в заметке нет PARA-классификации или она уже очевидна.

**Последствия**:
- Увеличенное время обработки
- Больше токенов в контексте
- Потенциальная путаница LLM между задачами

#### 5. **Неполный edge_type_map**

Текущий `para_config.py:108-124`:
```python
PARA_EDGE_TYPE_MAP: dict[tuple[str, str], list[str]] = {
    ("Project", "Area"): ["ContributesTo", "SpawnedFrom"],
    ("Project", "Resource"): ["UsesResource"],
    ("Area", "Resource"): ["UsesResource"],
    ("Archive", "Project"): ["RELATES_TO"],
    # ...
    ("Entity", "Entity"): ["RELATES_TO"],  # Fallback
}
```

**Проблема**: Нет отношений между PARA и базовыми entity types!

Отсутствуют:
- `("Project", "Person")`: Кто работает над проектом?
- `("Task", "Project")`: К какому проекту относится задача?
- `("Area", "Person")`: Кто ответственен за область?

#### 6. **Отсутствие кастомных промптов для edges**

Graphiti's `extract_edges` поддерживает `custom_prompt`, но:
- Он используется только внутри для reflexion loop
- Нет способа передать PARA-специфичные инструкции снаружи
- LLM не знает, что "эта заметка - Project, поэтому ищи ASSIGNED_TO edges"

---

## Желаемое Состояние (To-Be)

### Идеальный поток обработки

```
1. classify_note_as_para(episode_body, name)
   - LLM анализирует всю заметку
   - Возвращает: ("Project", {"deadline": "2024-12-31", ...})
   ↓
2. Создание EpisodicNode(labels=["Project"])
   - Явно маркируем эпизод типом PARA
   ↓
3. extract_nodes(entity_types=БАЗОВЫЕ_ТИПЫ)  # БЕЗ PARA
   - LLM извлекает только Person, Task, Organization...
   - Фокус на конкретных сущностях, а не классификации
   ↓
4. resolve_extracted_nodes()
   - Учитывает PARA label эпизода
   ↓
5. extract_edges(custom_prompt=PARA_CONTEXT)
   - LLM получает инструкцию: "Это Project, ищи ASSIGNED_TO, CONTRIBUTES_TO"
   - Использует расширенный edge_type_map с PARA ↔ Entity связями
   ↓
6. Сохранение в граф
   - Эпизод имеет label "Project"
   - Связи семантически богаче
```

### Ключевые улучшения

1. **Разделение ответственности**:
   - PARA классификация = отдельный этап
   - Entity extraction = только сущности

2. **Контекст для edges**:
   - LLM знает тип заметки
   - Создает релевантные связи

3. **Явная типизация эпизодов**:
   - `EpisodicNode` имеет PARA label
   - Возможность фильтрации и поиска

4. **Эффективность**:
   - Меньше токенов в entity extraction
   - Фокусированные промпты

---

## Требования к Решению

### Функциональные требования

**FR-1**: Классификация заметки должна происходить **до** создания `EpisodicNode`
**FR-2**: PARA-тип должен сохраняться в `labels` поле эпизода
**FR-3**: PARA-типы НЕ должны передаваться в `entity_types` для `extract_nodes`
**FR-4**: `edge_type_map` должен включать связи между PARA и базовыми типами
**FR-5**: LLM должен получать PARA-контекст при извлечении связей

### Нефункциональные требования

**NFR-1**: Время обработки заметки не должно увеличиться > 20%
**NFR-2**: Точность классификации PARA должна быть ≥ 85%
**NFR-3**: Решение должно быть обратно совместимо с `use_para_entities=False`
**NFR-4**: Код должен быть готов к апдейту graphiti без критических изменений

### Ограничения

**C-1**: Graphiti's `extract_edges` не принимает `custom_prompt` как параметр (только внутренний reflexion)
**C-2**: Нельзя изменять graphiti core library напрямую (vendor-копия возможна)
**C-3**: Должна сохраниться возможность работы без PARA (`use_para_entities=False`)

---

## Метрики Успеха

### Качество классификации

- **Accuracy**: % правильно классифицированных заметок
  - Target: ≥ 85%
- **Precision по типам**:
  - Project: ≥ 90% (самый важный)
  - Area: ≥ 80%
  - Resource: ≥ 85%
  - Archive: ≥ 75%

### Качество связей

- **PARA-Entity Edges**: Количество созданных семантически значимых связей
  - До: преимущественно `RELATES_TO`, `MENTIONS`
  - После: `ASSIGNED_TO`, `BELONGS_TO`, `CONTRIBUTES_TO`, `USES`
  - Target: ≥ 60% связей с типизированными PARA-edge types

### Производительность

- **Время обработки заметки**: Не должно увеличиться существенно
  - Дополнительный LLM-вызов для классификации: ~500-1000ms
  - Экономия на уменьшении контекста в extract_nodes: ~300-500ms
  - **Net overhead**: < 20%

### Граф-качество

- **Episodic Labels**: % эпизодов с явным PARA label
  - Target: ≥ 70% (некоторые заметки могут не классифицироваться)

---

## Связанные Документы

- [PARA_ENTITY_DOCSTRINGS.md](../PARA_ENTITY_DOCSTRINGS.md) - Текущие docstrings для PARA
- [PARA_TYPES_ARCHITECTURE.md](../PARA_TYPES_ARCHITECTURE.md) - Архитектурная модель PARA
- [PARA_INTEGRATION.md](../../custom_entities/PARA_INTEGRATION.md) - Руководство по интеграции
- [pipgraph_manager.py](../../../app/services/pipgraph_manager.py) - Текущая реализация

---

## Вопросы для Обсуждения

1. **Уровень уверенности классификации**: При каком threshold не классифицировать заметку?
   - Предложение: Если confidence < 0.6, оставить `labels=[]`

2. **Смешанные заметки**: Что делать, если заметка - одновременно Project И Resource?
   - Предложение: Выбирать доминирующий тип, добавлять вторичный в metadata

3. **Реклассификация**: Можно ли изменить PARA-тип существующей заметки?
   - Предложение: Да, через отдельный API endpoint

4. **Fallback стратегия**: Что если classify_note_as_para() падает?
   - Предложение: Логировать ошибку, продолжать без PARA label

---

## Следующий Шаг

См. [02_ARCHITECTURE_DECISION.md](./02_ARCHITECTURE_DECISION.md) для детального архитектурного решения.
