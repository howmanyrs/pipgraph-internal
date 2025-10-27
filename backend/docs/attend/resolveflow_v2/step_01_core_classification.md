# Этап 1: Реализация Core Classification

**Цель**: Создать метод `classify_note_as_para()` для ранней классификации заметок по типам PARA (Projects, Areas, Resources, Archive).

**Время**: 1-2 дня

## Краткое Резюме

**Что делаем**: Добавляем 4 метода в класс `PipGraphManager`:
1. `classify_note_as_para()` - основной метод классификации через LLM
2. `_build_classification_prompt()` - построение промпта с PARA docstrings
3. `_extract_json_from_response()` - парсинг JSON из ответа LLM
4. `_validate_para_attributes()` - валидация атрибутов через Pydantic

**Результат**: Метод возвращает `(para_type, attributes, confidence)`, который будет использоваться в `process_note()` для:
- Присвоения Neo4j label (`labels=["Project"]`)
- Сохранения confidence для взаимодействия с пользователем
- Извлечения PARA-атрибутов (deadline, goal, status, и т.д.)

**Ключевое отличие от старого подхода**: PARA-типы НЕ передаются в `extract_nodes` - классификация происходит на уровне эпизода, не внутренних сущностей.

---

## Контекст

### Что такое PARA?

PARA - метод организации знаний по 4 категориям:
- **Project**: Инициатива с конкретной целью и дедлайном (например, "Запустить маркетинговую кампанию к декабрю")
- **Area**: Постоянная сфера ответственности без конечной даты (например, "Здоровье", "Управление командой")
- **Resource**: Справочные материалы, не требующие действий (например, "Лучшие практики Python")
- **Archive**: Завершенные или неактуальные материалы

### Зачем нужна ранняя классификация?

Классификация заметки **до** создания `EpisodicNode` позволяет:
1. Присвоить PARA-тип как Neo4j label для быстрых запросов
2. Сохранить confidence score для возможности переспросить пользователя
3. Извлечь PARA-специфичные атрибуты (deadline, goal, status и т.д.)
4. Не передавать PARA типы в `extract_nodes` - они обрабатываются на уровне эпизода

---

## Принятые Решения

### 1. Использование основной LLM для классификации

**Решение**: Используем ту же LLM модель, что и для `extract_nodes`, через `self.clients.llm_client`.

**Почему**: Классификация требует тонкого понимания контекста. Мы можем переспросить пользователя при низкой уверенности, поэтому качество важнее скорости.

### 2. Отдельный метод классификации

**Решение**: Реализуем как самостоятельный метод `classify_note_as_para()` в классе `PipGraphManager`.

**Почему**: Классификация - отдельная ответственность, не связанная с извлечением сущностей.

### 3. Хранение результата

**PARA-тип**: Сохраняется в поле `labels` объекта `EpisodicNode` для использования native Neo4j labels:
```python
labels=[para_type] if para_type else []  # Например: labels=["Project"]
```

**Confidence**: ВСЕГДА сохраняется как свойство `para_confidence` узла Neo4j для взаимодействия с пользователем:
```python
# Пример использования
if para_confidence < 0.7:
    # Запросить уточнение у пользователя
```

**PARA-атрибуты**: Сохраняются как свойства узла (deadline, goal, status и т.д.)

---

## Шаги Реализации

### Обзор архитектуры

**Где**: Файл `backend/app/services/pipgraph_manager.py`, класс `PipGraphManager`

**Взаимодействие с process_note()**:
```
User calls process_note(name="Q4 Campaign", episode_body="...")
   ↓
1. ОБЯЗАТЕЛЬНАЯ классификация: classify_note_as_para()
   → LLM returns: ("Project", {"deadline": "2024-12-31", ...}, 0.92)
   ↓
2. Create EpisodicNode(labels=["Project"], ...)
   ↓
3. Save episode to Neo4j
   ↓
4. Store PARA metadata: confidence + attributes (через _store_para_metadata)
   ↓
5. extract_nodes(entity_types={})  # БЕЗ PARA типов!
   → Извлекает только Person, Task, Organization...
```

**Важно**: PARA-типы НЕ передаются в `extract_nodes`, так как классификация происходит на уровне эпизода, а не внутренних сущностей.

---

### Шаг 1.1: Создать основной метод classify_note_as_para()

**Файл**: `backend/app/services/pipgraph_manager.py`

**Где добавить**: В класс `PipGraphManager`, после существующих методов обработки

**Добавить метод**:

```python
async def classify_note_as_para(
    self,
    episode_body: str,
    name: str,
    source_description: str | None = None,
    confidence_threshold: float = 0.6,
) -> tuple[str | None, dict, float]:
    """
    Classify entire note as PARA type using LLM.

    This method analyzes the full note content and determines which PARA category
    it belongs to: Project, Area, Resource, or Archive.

    Args:
        episode_body: Full text content of the note
        name: Title/name of the note
        source_description: Optional context about note source
        confidence_threshold: Minimum confidence score to return classification (0.0-1.0)

    Returns:
        tuple of (para_type, attributes, confidence):
            - para_type: "Project" | "Area" | "Resource" | "Archive" | None
            - attributes: dict of extracted PARA-specific attributes
            - confidence: float 0.0-1.0 representing LLM's certainty

    Notes:
        - Uses PARA docstrings from para_entities.py as classification criteria
        - Returns None if note doesn't fit any PARA category
        - Low confidence (<threshold) results in None to avoid misclassification
    """

    # 1. Build classification prompt
    prompt = self._build_classification_prompt(episode_body, name, source_description)

    # 2. Call LLM
    try:
        response = await self.clients.llm_client.generate_response(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,  # Low temperature for consistency
            max_tokens=1000,
        )
        response_text = response.get("choices", [{}])[0].get("message", {}).get("content", "")

    except Exception as e:
        logger.error(f"LLM call failed during PARA classification: {e}")
        return None, {}, 0.0

    # 3. Parse LLM response
    try:
        json_text = self._extract_json_from_response(response_text)
        result = json.loads(json_text)

        para_type = result.get("para_type")
        confidence = float(result.get("confidence", 0.0))
        reasoning = result.get("reasoning", "")
        attributes = result.get("attributes", {})

    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.warning(f"Failed to parse LLM response for PARA classification: {e}")
        logger.debug(f"Raw response: {response_text}")
        return None, {}, 0.0

    # 4. Validate result
    if confidence < confidence_threshold:
        logger.info(
            f"PARA classification below threshold: {para_type} "
            f"(confidence: {confidence:.2f} < {confidence_threshold})"
        )
        return None, {}, confidence

    # Validate para_type
    if para_type not in ["Project", "Area", "Resource", "Archive", None]:
        logger.warning(f"Invalid para_type returned: {para_type}")
        return None, {}, confidence

    # If null classification, return early
    if para_type is None:
        logger.info(f"Note '{name}' not classified into PARA type (confidence: {confidence:.2f})")
        return None, {}, confidence

    # 5. Validate and clean attributes
    cleaned_attributes = self._validate_para_attributes(para_type, attributes)

    # 6. Log result
    logger.info(
        f"Note classified as {para_type} (confidence: {confidence:.2f}). "
        f"Reasoning: {reasoning}"
    )
    logger.debug(f"Extracted attributes: {cleaned_attributes}")

    return para_type, cleaned_attributes, confidence
```

---

### Шаг 1.2: Создать метод _build_classification_prompt()

**Добавить helper method** в класс `PipGraphManager`:

**Цель**: Построить промпт для LLM с определениями PARA типов из docstrings моделей.

```python
def _build_classification_prompt(
    self,
    episode_body: str,
    name: str,
    source_description: str | None,
) -> str:
    """Build the full classification prompt with PARA docstrings."""

    from app.models.para_entities import Project, Area, Resource, Archive

    # Extract docstrings from PARA models
    # Эти docstrings содержат критерии идентификации и примеры
    project_docstring = Project.__doc__ or ""
    area_docstring = Area.__doc__ or ""
    resource_docstring = Resource.__doc__ or ""
    archive_docstring = Archive.__doc__ or ""

    # Truncate episode_body if too long
    max_body_length = 4000  # Characters, not tokens
    if len(episode_body) > max_body_length:
        # Take first 3000 chars + last 1000 chars
        episode_body = episode_body[:3000] + "\n\n[...content truncated...]\n\n" + episode_body[-1000:]

    # Format source_description
    source_str = source_description if source_description else "Unknown source"

    # Build full prompt
    prompt = f"""You are an expert in the PARA method (Projects, Areas, Resources, Archive) \
for personal knowledge management. Your task is to analyze a note and determine which PARA category it belongs to.

## PARA Type Definitions

### Project
{project_docstring}

### Area
{area_docstring}

### Resource
{resource_docstring}

### Archive
{archive_docstring}

## Note to Classify

**Title**: {name}

**Source**: {source_str}

**Content**:
{episode_body}

## Your Task

1. **Analyze the note** based on the PARA type definitions above
2. **Look for key markers**:
   - Deadlines or time-bound goals → Project
   - Ongoing responsibilities, no endpoint → Area
   - Reference material, no action required → Resource
   - Explicitly marked as completed/archived → Archive

3. **Determine the dominant PARA type**. If the note doesn't fit any category clearly, return null.

4. **Extract type-specific attributes** according to the Pydantic model fields:
   - Project: status, deadline, goal, completion_criteria
   - Area: goal, review_frequency, responsibilities, success_indicators
   - Resource: description, category, tags, source_type
   - Archive: original_type, archived_at, archival_reason, outcome

5. **Assess your confidence** (0.0 to 1.0):
   - 0.9-1.0: Very clear (explicit markers, unambiguous)
   - 0.7-0.89: Clear (strong indicators)
   - 0.5-0.69: Moderate (could be multiple types, chose most likely)
   - <0.5: Unclear (don't classify)

## Output Format (JSON)

Return a JSON object with this structure:

```json
{{
  "para_type": "Project" | "Area" | "Resource" | "Archive" | null,
  "confidence": 0.85,
  "reasoning": "Brief explanation of why you chose this type (1-2 sentences)",
  "attributes": {{
    // Type-specific attributes based on the Pydantic model
    // Example for Project: {{"status": "active", "deadline": "2024-12-31", "goal": "Launch product"}}
    // Only include attributes you can extract with reasonable certainty
  }}
}}
```

**Important**:
- Return only the JSON object, no additional text
- If attributes cannot be extracted, use empty dict `{{}}`
- Dates should be in ISO format: "2024-12-31"
- Lists should be JSON arrays: ["item1", "item2"]
- Only extract attributes that are explicitly or clearly implied in the note

Now classify the note provided above.
"""

    return prompt
```

---

### Шаг 1.3: Создать метод _extract_json_from_response()

**Добавить helper method** в класс `PipGraphManager`:

**Цель**: Извлечь JSON из ответа LLM, обрабатывая markdown code blocks.

```python
def _extract_json_from_response(self, response_text: str) -> str:
    """Extract JSON from LLM response, handling markdown code blocks."""

    # Remove markdown code fences if present
    if "```json" in response_text:
        start = response_text.find("```json") + 7
        end = response_text.find("```", start)
        return response_text[start:end].strip()
    elif "```" in response_text:
        start = response_text.find("```") + 3
        end = response_text.find("```", start)
        return response_text[start:end].strip()
    else:
        return response_text.strip()
```

---

### Шаг 1.4: Создать метод _validate_para_attributes()

**Добавить helper method** в класс `PipGraphManager`:

**Цель**: Валидировать и очистить атрибуты на основе Pydantic моделей PARA типов.

```python
def _validate_para_attributes(self, para_type: str, attributes: dict) -> dict:
    """
    Validate and clean extracted attributes based on PARA type's Pydantic model.

    Returns cleaned dict with only valid fields and proper types.

    Args:
        para_type: PARA type (Project, Area, Resource, Archive)
        attributes: Raw attributes dict from LLM response

    Returns:
        Cleaned dict with validated fields and proper types
    """

    from config.para_config import PARA_ENTITY_TYPES
    from datetime import datetime

    # Get the Pydantic model for this PARA type
    # PARA_ENTITY_TYPES = {"Project": Project, "Area": Area, ...}
    model = PARA_ENTITY_TYPES.get(para_type)
    if not model:
        return {}

    cleaned = {}

    # Iterate through model fields and validate
    for field_name, field_info in model.model_fields.items():
        value = attributes.get(field_name)

        if value is None:
            continue

        # Type conversion and validation
        try:
            # Handle datetime fields (deadline, archived_at, etc.)
            if field_info.annotation == datetime or str(field_info.annotation).startswith('datetime'):
                if isinstance(value, str):
                    # Try to parse ISO format (2024-12-31 or 2024-12-31T00:00:00Z)
                    try:
                        cleaned[field_name] = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    except ValueError:
                        logger.warning(f"Invalid datetime format for {field_name}: {value}")
                        continue
                elif isinstance(value, datetime):
                    cleaned[field_name] = value

            # Handle list fields (tags, responsibilities, etc.)
            elif 'list' in str(field_info.annotation):
                if isinstance(value, list):
                    cleaned[field_name] = value
                elif isinstance(value, str):
                    # Convert comma-separated string to list
                    cleaned[field_name] = [item.strip() for item in value.split(',')]

            # Handle string fields (goal, status, etc.)
            elif field_info.annotation == str or 'str' in str(field_info.annotation):
                cleaned[field_name] = str(value)

            # Handle other types as-is
            else:
                cleaned[field_name] = value

        except Exception as e:
            logger.warning(f"Failed to validate attribute {field_name}: {e}")
            continue

    return cleaned
```

**Важные детали**:
- Использует `PARA_ENTITY_TYPES` из `config.para_config` для получения Pydantic моделей
- Поддерживает автоматическую конвертацию типов (string → datetime, string → list)
- Игнорирует неизвестные поля (только те, что есть в Pydantic модели)
- Gracefully обрабатывает ошибки валидации (логирует warning, пропускает поле)

---

### Шаг 1.5: Добавить необходимые импорты

**В начале файла pipgraph_manager.py**, добавить (если отсутствуют):

```python
import json
from datetime import datetime
```

---

## Проверка Реализации

### Checklist функциональности

После реализации этих методов, метод `classify_note_as_para()` должен:

1. ✅ Принимать текст заметки (episode_body, name, source_description)
2. ✅ Использовать PARA docstrings из моделей для контекста LLM
3. ✅ Вызывать LLM через `self.clients.llm_client`
4. ✅ Обрабатывать ошибки LLM gracefully (возвращать None, {}, 0.0)
5. ✅ Парсить JSON из markdown code blocks (```json...```)
6. ✅ Валидировать confidence threshold (по умолчанию 0.6)
7. ✅ Проверять корректность para_type ("Project" | "Area" | "Resource" | "Archive" | None)
8. ✅ Очищать и типизировать атрибуты через Pydantic models
9. ✅ Логировать результаты (info для успеха, warning для ошибок)
10. ✅ Возвращать tuple: (para_type, attributes, confidence)

### Пример использования

```python
# В методе process_note(), ДО создания EpisodicNode:
para_type, para_attrs, para_confidence = await self.classify_note_as_para(
    episode_body="Launch marketing campaign by Q4 2024",
    name="Q4 Campaign",
    source_description="Obsidian note",
)

# Результат:
# para_type = "Project"
# para_attrs = {"deadline": datetime(2024, 12, 31), "goal": "Launch campaign", ...}
# para_confidence = 0.92
```

### Ожидаемое поведение

**Успешная классификация**:
```
INFO: Note classified as Project (confidence: 0.92). Reasoning: Contains deadline Q4 2024...
DEBUG: Extracted attributes: {'deadline', 'goal', 'status'}
```

**Низкая уверенность**:
```
INFO: PARA classification below threshold: Project (confidence: 0.55 < 0.6)
```

**Нет классификации**:
```
INFO: Note 'Daily notes' not classified into PARA type (confidence: 0.45)
```

**Ошибка LLM**:
```
ERROR: LLM call failed during PARA classification: ConnectionError...
```

---

## Следующий Этап

После реализации этих методов переходите к **Этапу 2: Интеграция в process_note()**.

Там будет:
1. Модификация сигнатуры `process_note()` (убрать флаги `use_para_entities`)
2. Вызов `classify_note_as_para()` перед созданием EpisodicNode
3. Передача `para_type` в `labels` при создании EpisodicNode
4. Сохранение metadata (confidence + attributes) через `_store_para_metadata()`
5. Настройка entity_types БЕЗ PARA типов для extract_nodes

---

## Приложение: Структура PARA Моделей

### Project (app/models/para_entities.py)

```python
class Project(BaseModel):
    title: str                          # Название проекта
    status: str = "active"              # active, completed, on_hold, cancelled, archived
    deadline: Optional[datetime]        # Дедлайн проекта
    goal: Optional[str]                 # Конкретная измеримая цель
    completion_criteria: Optional[str]  # Критерии завершения
```

### Area (app/models/para_entities.py)

```python
class Area(BaseModel):
    title: str                                  # Название области
    goal: Optional[str]                         # Долгосрочная цель или стандарт
    review_frequency: Optional[str]             # Как часто пересматривать (weekly, monthly, etc.)
    responsibilities: Optional[list[str]]       # Список обязанностей
    success_indicators: Optional[list[str]]     # Индикаторы успеха
```

### Resource (app/models/para_entities.py)

```python
class Resource(BaseModel):
    title: str                          # Название ресурса
    description: Optional[str]          # Краткое описание содержимого
    category: Optional[str]             # Категория (tutorial, reference, documentation, etc.)
    tags: Optional[list[str]]           # Теги для организации
    source_type: Optional[str]          # article, book, video, course, etc.
```

### Archive (app/models/para_entities.py)

```python
class Archive(BaseModel):
    title: str                          # Оригинальное название
    original_type: Optional[str]        # Исходный тип (Project, Area, Resource)
    archived_at: Optional[datetime]     # Когда архивировано
    archival_reason: Optional[str]      # Почему архивировано (completed, obsolete, cancelled)
    outcome: Optional[str]              # Результат (для завершенных проектов)
```

### PARA_ENTITY_TYPES (config/para_config.py)

```python
from app.models.para_entities import Project, Area, Resource, Archive

PARA_ENTITY_TYPES = {
    "Project": Project,
    "Area": Area,
    "Resource": Resource,
    "Archive": Archive,
}
```

**Использование в коде**:
```python
from config.para_config import PARA_ENTITY_TYPES

# Получить модель по типу
model = PARA_ENTITY_TYPES.get("Project")  # Returns Project class
fields = model.model_fields  # Pydantic fields info
```
