# Этап 2: Интеграция Классификации в Process Flow

**Цель**: Интегрировать обязательную PARA классификацию в метод `process_note()` и модифицировать создание `EpisodicNode` для сохранения PARA label и confidence.

**Время**: 1 день
**Контекст**: [02_ARCHITECTURE_DECISION.md](../resolveflow/02_ARCHITECTURE_DECISION.md), [step_01_core_classification.md](./step_01_core_classification.md)

---

## Принятые Решения

### 1. Обязательная ранняя классификация (до создания EpisodicNode)

Из [02_ARCHITECTURE_DECISION.md](../resolveflow/02_ARCHITECTURE_DECISION.md):
> Классификация заметки должна происходить **до** создания `EpisodicNode`

**Решение**: Всегда вызываем `classify_note_as_para()` перед созданием объекта EpisodicNode.

### 2. Хранение PARA label в EpisodicNode.labels

PARA-тип (если определен) сохраняется в поле `labels` для использования Neo4j native labels:
```python
labels=[para_type] if para_type else []
```

### 3. Хранение confidence для взаимодействия с пользователем

Сохраняем `para_confidence` как свойство узла, чтобы можно было:
- Запрашивать уточнение при низкой уверенности (например, < 0.7)
- Отслеживать качество классификации
- Анализировать распределение confidence

### 4. Хранение PARA attributes как свойства узла

PARA-атрибуты (deadline, goal, и т.д.) сохраняются как properties узла Neo4j через отдельный запрос после создания эпизода.

### 5. PARA НЕ используется в entity_types

PARA-классификация происходит на уровне эпизода (EpisodicNode), поэтому PARA типы НЕ передаются в `extract_nodes` как `entity_types`.

---

## Шаги Реализации

### Шаг 2.1: Упростить сигнатуру метода process_note()

**Файл**: `backend/app/services/pipgraph_manager.py`

**Модифицировать сигнатуру метода process_note()**:

```python
async def process_note(
    self,
    name: str,
    episode_body: str,
    source: EpisodeType = EpisodeType.text,
    source_description: str | None = None,
    reference_time: datetime | None = None,
    uuid: str | None = None,
    group_id: str | None = None,
    entity_types: dict[str, type[BaseModel]] | None = None,
    edge_types: dict[str, type[BaseModel]] | None = None,
    edge_type_map: dict[tuple[str, str], list[str]] | None = None,
) -> AddEpisodeResults:
    """
    Process a note through the Graphiti pipeline.

    PARA Classification:
        - Always performed before creating EpisodicNode
        - Stores PARA type as Neo4j label
        - Stores confidence score for user interaction decisions
        - Stores PARA-specific attributes as node properties

    Args:
        name: Note title
        episode_body: Note content
        source: Episode type (text, audio, image, etc.)
        source_description: Optional description of the source
        reference_time: When the event occurred (defaults to now)
        uuid: Optional UUID for updating existing episode
        group_id: Optional group identifier
        entity_types: Custom entity types for extraction (PARA types excluded)
        edge_types: Custom edge types for extraction
        edge_type_map: Custom edge type mapping
    """
```

**Изменения**:
- ❌ Убран `use_para_entities` — классификация всегда выполняется
- ❌ Убран `enable_early_para_classification` — классификация всегда ранняя
- ✅ Добавлено описание обязательной PARA-классификации в docstring

---

### Шаг 2.2: Обязательная классификация перед созданием EpisodicNode

**Найти в process_note()** (примерно строки 220-240):

```python
# Existing validation code...
now = datetime.now(timezone.utc)
```

**Добавить ПОСЛЕ валидации, ДО создания EpisodicNode**:

```python
# ====== PARA Classification (Always Performed) ======
logger.info(f"Classifying note '{name}' as PARA type...")

para_type, para_attrs, para_confidence = await self.classify_note_as_para(
    episode_body=episode_body,
    name=name,
    source_description=source_description,
)

# Store confidence for user interaction decisions
if para_type:
    logger.info(
        f"Note classified as PARA type: {para_type} "
        f"(confidence: {para_confidence:.2f})"
    )
    # Confidence будет сохранен как свойство узла для последующего использования
else:
    logger.info(
        f"Note not classified into any PARA type "
        f"(confidence: {para_confidence:.2f})"
    )
```

**Важно**: Confidence всегда сохраняется, даже если `para_type` отсутствует. Это позволяет отслеживать случаи, когда LLM не уверен в классификации.

---

### Шаг 2.3: Модифицировать создание EpisodicNode с PARA label

**Найти в process_note()** (примерно строки 241-254):

**БЫЛО**:
```python
episode = (
    await EpisodicNode.get_by_uuid(self.driver, uuid)
    if uuid is not None
    else EpisodicNode(
        name=name,
        group_id=group_id,
        labels=[],  # ← Пусто!
        source=source,
        content=episode_body,
        source_description=source_description,
        created_at=now,
        valid_at=reference_time,
    )
)
```

**СТАЛО**:
```python
episode = (
    await EpisodicNode.get_by_uuid(self.driver, uuid)
    if uuid is not None
    else EpisodicNode(
        name=name,
        group_id=group_id,
        labels=[para_type] if para_type else [],  # ← PARA label!
        source=source,
        content=episode_body,
        source_description=source_description,
        created_at=now,
        valid_at=reference_time,
    )
)
```

---

### Шаг 2.4: Создать метод для сохранения PARA metadata

**Добавить новый метод** в `PipGraphManager`:

```python
async def _store_para_metadata(
    self,
    episode_uuid: str,
    para_type: str | None,
    para_attrs: dict,
    para_confidence: float,
) -> None:
    """
    Store PARA-specific metadata as properties of the EpisodicNode.

    Stores:
        - para_confidence: Float value for user interaction decisions
        - PARA-specific attributes (deadline, goal, status, etc.)

    Args:
        episode_uuid: UUID of the episode node
        para_type: PARA type (or None if not classified)
        para_attrs: Dictionary of PARA attributes to store
        para_confidence: Confidence score from classification
    """

    try:
        # Prepare metadata to store
        metadata = {
            "para_confidence": para_confidence,
        }

        # Add PARA-specific attributes if available
        if para_attrs:
            metadata.update(para_attrs)

        # Build Cypher query to add metadata as properties
        query = """
        MATCH (e:EpisodicNode {uuid: $uuid})
        SET e += $metadata
        RETURN e.uuid as uuid
        """

        result = await self.driver.execute_query(
            query,
            uuid=episode_uuid,
            metadata=metadata,
        )

        logger.debug(
            f"Stored PARA metadata for episode {episode_uuid}: "
            f"type={para_type}, confidence={para_confidence:.2f}, "
            f"attributes={list(para_attrs.keys())}"
        )

    except Exception as e:
        logger.error(
            f"Failed to store PARA metadata for episode {episode_uuid}: {e}"
        )
        # Don't fail the whole process if metadata storage fails
```

**Важно**: Метод всегда сохраняет `para_confidence`, даже если PARA-тип не определен. Это позволяет:
- Запрашивать уточнение у пользователя при низкой уверенности
- Анализировать качество классификации
- Улучшать промпты на основе статистики

---

### Шаг 2.5: Вызвать сохранение PARA metadata после создания узла

**Найти в process_note()** после сохранения episode в БД (примерно после `await episode.save(self.driver)`):

**Добавить**:

```python
# Save episode to database
await episode.save(self.driver)

# ====== Store PARA metadata (always performed) ======
await self._store_para_metadata(
    episode_uuid=episode.uuid,
    para_type=para_type,
    para_attrs=para_attrs,
    para_confidence=para_confidence,
)
logger.debug(
    f"PARA metadata stored for episode {episode.uuid} "
    f"(confidence: {para_confidence:.2f})"
)
```

---

### Шаг 2.6: Упростить логику entity_types

**Найти в process_note()** (примерно строки 209-220):

**БЫЛО**:
```python
if use_para_entities:
    if entity_types is None:
        entity_types = PARA_ENTITY_TYPES  # Включает Project, Area, Resource, Archive
        logger.info("Using default PARA entity types...")
```

**СТАЛО**:
```python
# PARA classification is now always performed at episode level,
# so PARA types are NOT included in entity_types for extract_nodes
if entity_types is None:
    entity_types = {}  # Use only base entity types (Person, Task, etc.)
    logger.info("Using default entity types (PARA excluded - handled at episode level)")
```

**Объяснение**: PARA-классификация теперь всегда происходит на уровне эпизода, поэтому PARA типы НЕ передаются в `extract_nodes`.

---

### Шаг 2.7: Настроить edge_type_map и edge_types

**Найти в process_note()** (после настройки entity_types):

**Добавить**:

```python
# Configure edge types (will be extended in Step 3)
if edge_types is None:
    from config.para_config import PARA_EDGE_TYPES
    edge_types = PARA_EDGE_TYPES
    logger.info("Using PARA edge types")

if edge_type_map is None:
    from config.para_config import PARA_EDGE_TYPE_MAP
    edge_type_map = PARA_EDGE_TYPE_MAP
    logger.info("Using PARA edge type map")
```

**Примечание**: На этапе 3 мы заменим `PARA_EDGE_TYPES` и `PARA_EDGE_TYPE_MAP` на расширенные версии.

---

## Пример Полного Потока

После реализации, процесс обработки заметки будет выглядеть так:

```
1. User calls process_note(name="Q4 Campaign", episode_body="...")
   ↓
2. ОБЯЗАТЕЛЬНО: classify_note_as_para()
   → LLM returns: ("Project", {"deadline": "2024-12-31", ...}, 0.92)
   → para_confidence ВСЕГДА сохраняется
   ↓
3. Create EpisodicNode(labels=["Project"], ...)
   ↓
4. Save episode to Neo4j
   ↓
5. Store PARA metadata (confidence + attributes)
   ↓
6. extract_nodes(entity_types={})  # БЕЗ PARA типов
   → Извлекает только Person, Task, Organization...
   ↓
7. resolve_extracted_nodes()
   ↓
8. extract_edges(episode_with_context, ...)  # С PARA контекстом (этап 4)
   ↓
9. Return результат с:
   - episode.labels = ["Project"]
   - episode.para_confidence = 0.92
   - episode.deadline = "2024-12-31"
```

---

## Использование Confidence для Взаимодействия с Пользователем

После сохранения confidence можно реализовать логику уточнения:

```python
# Пример использования (будет реализовано позже)
if para_confidence < 0.7:
    # Запросить уточнение у пользователя
    await request_user_clarification(
        episode_uuid=episode.uuid,
        suggested_type=para_type,
        confidence=para_confidence,
    )
```

**Варианты использования confidence**:
- **< 0.5**: Предложить пользователю выбрать тип вручную
- **0.5 - 0.7**: Показать предложенный тип с запросом подтверждения
- **> 0.7**: Использовать автоматически, но показать в UI для корректировки

---

## Проверка Реализации

После реализации должно работать:

1. ✅ PARA классификация ВСЕГДА вызывается до создания EpisodicNode
2. ✅ PARA label сохраняется в `episode.labels`
3. ✅ Confidence ВСЕГДА сохраняется как `episode.para_confidence`
4. ✅ PARA атрибуты сохраняются как properties узла Neo4j
5. ✅ PARA типы НЕ передаются в `extract_nodes`
6. ✅ Нет флагов `use_para_entities` и `enable_early_para_classification`

---

## Пример Запроса к Neo4j

После обработки Project-заметки с deadline, в Neo4j будет:

```cypher
MATCH (e:EpisodicNode:Project)
WHERE e.name = "Q4 Campaign"
RETURN e.uuid, e.labels, e.para_confidence, e.deadline, e.goal, e.status
```

Результат:
```
uuid: "abc-123-..."
labels: ["Project"]
para_confidence: 0.92
deadline: "2024-12-31T00:00:00+00:00"
goal: "Launch product successfully"
status: "active"
```

Пример запроса для поиска заметок с низкой уверенностью:
```cypher
MATCH (e:EpisodicNode)
WHERE e.para_confidence < 0.7
RETURN e.uuid, e.name, e.para_confidence, e.labels
ORDER BY e.para_confidence ASC
```

---

## Следующий Этап

См. [step_03_extended_edges.md](./step_03_extended_edges.md) для создания расширенного набора edge types и PARA_EDGE_TYPE_MAP_EXTENDED.
