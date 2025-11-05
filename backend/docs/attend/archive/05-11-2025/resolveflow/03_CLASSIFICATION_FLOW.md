# Поток Классификации PARA: Детали Реализации

**Дата**: 2025-10-27
**Контекст**: [02_ARCHITECTURE_DECISION.md](./02_ARCHITECTURE_DECISION.md)

---

## Обзор

Этот документ описывает **детальную логику** метода `classify_note_as_para()` включая:
- Структуру промпта
- Парсинг ответа LLM
- Обработку граничных случаев
- Примеры классификации

---

## Сигнатура Метода

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
        source_description: Optional context about note source (e.g., "Obsidian vault: Projects")
        confidence_threshold: Minimum confidence score to return classification (0.0-1.0)

    Returns:
        tuple of (para_type, attributes, confidence):
            - para_type: "Project" | "Area" | "Resource" | "Archive" | None
                       None if confidence below threshold or no clear type
            - attributes: dict of extracted PARA-specific attributes
                         e.g., {"deadline": "2024-12-31", "status": "active", "goal": "..."}
            - confidence: float 0.0-1.0 representing LLM's certainty

    Example:
        >>> para_type, attrs, conf = await manager.classify_note_as_para(
        ...     episode_body="Launch new product by Q4 2024...",
        ...     name="Product Launch Campaign"
        ... )
        >>> print(para_type, conf)
        "Project" 0.92
        >>> print(attrs)
        {"deadline": "2024-12-31", "status": "active", "goal": "Launch product successfully"}

    Notes:
        - Uses PARA docstrings from para_entities.py as classification criteria
        - Returns None if note doesn't fit any PARA category (e.g., pure dialogue)
        - Low confidence (<threshold) results in None to avoid misclassification
    """
```

---

## Промпт Для Классификации

### Полный Промпт (Шаблон)

```python
PARA_CLASSIFICATION_PROMPT = """You are an expert in the PARA method (Projects, Areas, Resources, Archive) \
for personal knowledge management. Your task is to analyze a note and determine which PARA category it belongs to.

## PARA Type Definitions

### Project
{docstring from para_entities.Project}

### Area
{docstring from para_entities.Area}

### Resource
{docstring from para_entities.Resource}

### Archive
{docstring from para_entities.Archive}

## Note to Classify

**Title**: {name}

**Source**: {source_description}

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

4. **Extract type-specific attributes** according to the Pydantic model fields

5. **Assess your confidence** (0.0 to 1.0):
   - 0.9-1.0: Very clear (explicit markers, unambiguous)
   - 0.7-0.89: Clear (strong indicators)
   - 0.5-0.69: Moderate (could be multiple types, chose most likely)
   - <0.5: Unclear (don't classify)

## Output Format (JSON)

Return a JSON object with this structure:

```json
{
  "para_type": "Project" | "Area" | "Resource" | "Archive" | null,
  "confidence": 0.85,
  "reasoning": "Brief explanation of why you chose this type (1-2 sentences)",
  "attributes": {
    // Type-specific attributes based on the Pydantic model
    // For Project: "status", "deadline", "goal", "completion_criteria"
    // For Area: "goal", "review_frequency", "responsibilities", "success_indicators"
    // For Resource: "description", "category", "tags", "source_type"
    // For Archive: "original_type", "archived_at", "archival_reason", "outcome"
  }
}
```

**Important**:
- Return only the JSON object, no additional text
- If attributes cannot be extracted, use empty dict `{}`
- Dates should be in ISO format: "2024-12-31"
- Lists should be JSON arrays: ["item1", "item2"]

## Examples

### Example 1: Clear Project
**Input Note Title**: "Q4 Marketing Campaign"
**Content**: "Launch new product marketing by December 31st. Goal: 10k signups. Success: conversion rate >5%"

**Output**:
```json
{
  "para_type": "Project",
  "confidence": 0.95,
  "reasoning": "Clear time-bound goal with explicit deadline and success criteria",
  "attributes": {
    "status": "active",
    "deadline": "2024-12-31",
    "goal": "10k signups",
    "completion_criteria": "conversion rate >5%"
  }
}
```

### Example 2: Clear Area
**Input Note Title**: "Personal Health"
**Content**: "Ongoing fitness and wellness. Weekly review every Monday. Goals: exercise 3x/week, 7hrs sleep."

**Output**:
```json
{
  "para_type": "Area",
  "confidence": 0.88,
  "reasoning": "Ongoing responsibility with no endpoint, has regular review frequency",
  "attributes": {
    "goal": "Maintain physical fitness and wellness",
    "review_frequency": "weekly",
    "responsibilities": ["Exercise 3x per week", "Get 7 hours of sleep"],
    "success_indicators": ["Consistent energy levels", "Weight stable"]
  }
}
```

### Example 3: Resource
**Input Note Title**: "Python Async Programming"
**Content**: "Collection of asyncio tutorials, best practices, and code examples. Tags: #python #async #tutorial"

**Output**:
```json
{
  "para_type": "Resource",
  "confidence": 0.90,
  "reasoning": "Pure reference material, no action required, tagged for learning",
  "attributes": {
    "description": "Collection of asyncio tutorials and best practices",
    "category": "Tutorial",
    "tags": ["python", "async", "tutorial"],
    "source_type": "curated collection"
  }
}
```

### Example 4: Ambiguous Case
**Input Note Title**: "Meeting Notes - Team Sync"
**Content**: "Discussed current projects. John mentioned API redesign. Need to follow up next week."

**Output**:
```json
{
  "para_type": null,
  "confidence": 0.35,
  "reasoning": "Meeting notes without clear PARA classification - could be related to Project but not the project itself",
  "attributes": {}
}
```

Now classify the note provided above.
"""
```

---

## Реализация Метода

### Полный Код

```python
import json
import logging
from datetime import datetime
from typing import Any

from graphiti_core import Graphiti
from graphiti_core.llm_client import LLMClient

from app.models.para_entities import Project, Area, Resource, Archive
from config.para_config import PARA_ENTITY_TYPES

logger = logging.getLogger(__name__)


async def classify_note_as_para(
    self,
    episode_body: str,
    name: str,
    source_description: str | None = None,
    confidence_threshold: float = 0.6,
) -> tuple[str | None, dict, float]:
    """Classify entire note as PARA type using LLM."""

    # ====== 1. Build Prompt Context ======
    prompt = self._build_classification_prompt(
        episode_body=episode_body,
        name=name,
        source_description=source_description,
    )

    # ====== 2. Call LLM ======
    try:
        response = await self.clients.llm_client.generate_response(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,  # Low temperature for consistency
            max_tokens=1000,  # Sufficient for classification response
        )

        response_text = response.get("choices", [{}])[0].get("message", {}).get("content", "")

    except Exception as e:
        logger.error(f"LLM call failed during PARA classification: {e}")
        return None, {}, 0.0

    # ====== 3. Parse LLM Response ======
    try:
        # Extract JSON from response (sometimes LLM wraps it in markdown)
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

    # ====== 4. Validate Result ======
    # Check confidence threshold
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

    # ====== 5. Validate and Clean Attributes ======
    cleaned_attributes = self._validate_para_attributes(para_type, attributes)

    # ====== 6. Log Result ======
    logger.info(
        f"Note classified as {para_type} (confidence: {confidence:.2f}). "
        f"Reasoning: {reasoning}"
    )
    logger.debug(f"Extracted attributes: {cleaned_attributes}")

    return para_type, cleaned_attributes, confidence


def _build_classification_prompt(
    self,
    episode_body: str,
    name: str,
    source_description: str | None,
) -> str:
    """Build the full classification prompt with PARA docstrings."""

    # Extract docstrings from PARA models
    project_docstring = Project.__doc__ or ""
    area_docstring = Area.__doc__ or ""
    resource_docstring = Resource.__doc__ or ""
    archive_docstring = Archive.__doc__ or ""

    # Truncate episode_body if too long (to save tokens)
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

[... rest of template as shown above ...]

Now classify the note provided above.
"""

    return prompt


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


def _validate_para_attributes(self, para_type: str, attributes: dict) -> dict:
    """
    Validate and clean extracted attributes based on PARA type's Pydantic model.

    Returns cleaned dict with only valid fields and proper types.
    """

    # Get the Pydantic model for this PARA type
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
            # Handle datetime fields
            if field_info.annotation == datetime or str(field_info.annotation).startswith('datetime'):
                if isinstance(value, str):
                    # Try to parse ISO format
                    try:
                        cleaned[field_name] = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    except ValueError:
                        logger.warning(f"Invalid datetime format for {field_name}: {value}")
                        continue
                elif isinstance(value, datetime):
                    cleaned[field_name] = value

            # Handle list fields
            elif 'list' in str(field_info.annotation):
                if isinstance(value, list):
                    cleaned[field_name] = value
                elif isinstance(value, str):
                    # Convert comma-separated string to list
                    cleaned[field_name] = [item.strip() for item in value.split(',')]

            # Handle string fields
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

---

## Граничные Случаи

### Case 1: Смешанные Заметки (Project + Resource)

**Пример**: Заметка "API Design Project" содержит:
- Дедлайн и цель (Project маркеры)
- Большой блок справочной информации (Resource контент)

**Решение**:
```json
{
  "para_type": "Project",
  "confidence": 0.75,
  "reasoning": "Primarily a project with deadline, resource section is secondary",
  "attributes": {
    "deadline": "2024-12-31",
    "status": "active",
    // Можно добавить meta-атрибут
    "contains_reference_material": true
  }
}
```

**Альтернатива**: Добавить secondary_type в metadata.

---

### Case 2: Очень Короткие Заметки

**Пример**: "Meeting with John - API discussion"

**Проблема**: Недостаточно контекста для классификации.

**Решение**:
```json
{
  "para_type": null,
  "confidence": 0.30,
  "reasoning": "Insufficient content to determine PARA type",
  "attributes": {}
}
```

**Threshold**: Если note_body < 50 символов, можно skip классификацию автоматически.

---

### Case 3: Диалоги и Транскрипты

**Пример**: Заметка с транскриптом разговора.

**Проблема**: Это EpisodeType.message, не подходит под PARA.

**Решение**:
```json
{
  "para_type": null,
  "confidence": 0.40,
  "reasoning": "Conversational content, not a PARA-structured note",
  "attributes": {}
}
```

**Note**: Можно добавить специальную логику для `source=EpisodeType.message` чтобы skip классификацию.

---

### Case 4: Архивные Проекты

**Пример**: "Q2 2023 Campaign - COMPLETED"

**Проблема**: Это Project или Archive?

**Решение**: Классифицировать как **Archive**:
```json
{
  "para_type": "Archive",
  "confidence": 0.88,
  "reasoning": "Explicitly marked as completed, contains retrospective content",
  "attributes": {
    "original_type": "Project",
    "original_name": "Q2 2023 Campaign",
    "archived_at": "2023-06-30",
    "archival_reason": "Project completed successfully",
    "outcome": "Achieved 15k signups, exceeded target by 50%"
  }
}
```

**Принцип**: Archive state > Active state в приоритете.

---

### Case 5: Очень Длинные Заметки (>10k tokens)

**Проблема**: LLM context window ограничен, или слишком дорого.

**Решение - Truncation Strategy**:
```python
def _truncate_for_classification(episode_body: str, max_chars: int = 4000) -> str:
    """
    Smart truncation for long notes.
    Takes first 75% and last 25% of allowed chars.
    """
    if len(episode_body) <= max_chars:
        return episode_body

    first_part = episode_body[: int(max_chars * 0.75)]
    last_part = episode_body[- int(max_chars * 0.25):]

    return first_part + "\n\n[... truncated ...]\n\n" + last_part
```

**Обоснование**:
- Первая часть обычно содержит summary, title, goal
- Последняя часть часто содержит deadlines, outcomes, tags

---

## Оптимизации

### Opt-1: Кеширование Результатов

Если заметка обрабатывается повторно (re-ingest), не нужно классифицировать снова.

**Реализация**:
```python
async def classify_note_as_para(self, ..., use_cache: bool = True):
    if use_cache:
        # Check if episode already exists and has PARA label
        existing_episode = await EpisodicNode.get_by_uuid(self.driver, uuid)
        if existing_episode and existing_episode.labels:
            logger.info(f"Using cached PARA type: {existing_episode.labels[0]}")
            # Retrieve attributes from node properties
            cached_attrs = await self._load_para_attributes(existing_episode.uuid)
            return existing_episode.labels[0], cached_attrs, 1.0  # confidence=1.0 for cache

    # ... proceed with LLM classification
```

---

### Opt-2: Batch Classification

Если обрабатываем много заметок сразу, можно batch LLM calls.

**Реализация**:
```python
async def classify_notes_batch(
    self,
    notes: list[tuple[str, str]],  # [(name, body), ...]
) -> list[tuple[str | None, dict, float]]:
    """Classify multiple notes in one LLM call."""

    # Build batch prompt
    batch_prompt = "Classify the following {len(notes)} notes:\n\n"
    for i, (name, body) in enumerate(notes):
        batch_prompt += f"## Note {i+1}: {name}\n{body[:500]}...\n\n"

    batch_prompt += "Return JSON array: [{para_type, confidence, attributes}, ...]"

    # ... call LLM and parse array
```

**Trade-off**: Меньше LLM calls, но меньше точность (LLM может путаться между заметками).

---

### Opt-3: Использование Более Дешевой Модели

Классификация проще, чем entity extraction → можно использовать более дешевую модель.

**Конфигурация**:
```python
# В PipGraphManager.__init__
self.classification_llm_client = LLMClient(
    model="gpt-4o-mini",  # Вместо gpt-4
    # Или claude-3-haiku
)

# В classify_note_as_para
response = await self.classification_llm_client.generate_response(...)
```

**Экономия**: ~80% стоимости при ~10% потере точности.

---

## Метрики и Мониторинг

### Метрики для Логирования

```python
# После классификации
logger.info(
    "PARA Classification",
    extra={
        "note_name": name,
        "para_type": para_type,
        "confidence": confidence,
        "note_length": len(episode_body),
        "has_attributes": bool(attributes),
        "processing_time_ms": (end_time - start_time) * 1000,
    }
)
```

### Dashboard Metrics

Собирать для анализа:
- **Distribution of PARA types**: Сколько Project vs Area vs Resource
- **Average confidence by type**: У каких типов ниже уверенность?
- **Classification time**: Среднее время классификации
- **Null classification rate**: % заметок, которые не классифицированы

---

## Примеры Классификации (Реальные Кейсы)

### Пример 1: Clear Project

**Input**:
```
Title: "Launch Product X by Q4"
Body: """
# Product X Launch Campaign

**Deadline**: December 31, 2024
**Goal**: Successfully launch Product X and achieve 10,000 signups

## Milestones
- [ ] Beta testing complete by Oct 15
- [ ] Marketing materials ready by Nov 1
- [ ] Launch event on Dec 15

## Success Criteria
- 10,000 signups within first month
- Conversion rate > 5%
- NPS score > 8
"""
```

**Output**:
```json
{
  "para_type": "Project",
  "confidence": 0.96,
  "reasoning": "Clear time-bound project with explicit deadline, milestones, and success criteria",
  "attributes": {
    "status": "active",
    "deadline": "2024-12-31",
    "goal": "Successfully launch Product X and achieve 10,000 signups",
    "completion_criteria": "10,000 signups, conversion rate >5%, NPS >8"
  }
}
```

---

### Пример 2: Clear Area

**Input**:
```
Title: "Team Management"
Body: """
# Team Management

Ongoing responsibility for leading the engineering team.

**Aspirational Goal**: Build and maintain a high-performing, happy team

**Review**: Weekly 1-on-1s, monthly team retrospectives

**Key Responsibilities**:
- Conduct regular 1-on-1s with all team members
- Ensure clear communication of goals and priorities
- Remove blockers and provide resources
- Foster team culture and psychological safety

**Success Indicators**:
- Team satisfaction score > 4.0/5
- Low turnover rate
- Consistent sprint velocity
- High-quality code reviews
"""
```

**Output**:
```json
{
  "para_type": "Area",
  "confidence": 0.93,
  "reasoning": "Ongoing responsibility with no endpoint, has regular review cadence and success metrics",
  "attributes": {
    "goal": "Build and maintain a high-performing, happy team",
    "review_frequency": "weekly",
    "responsibilities": [
      "Conduct regular 1-on-1s",
      "Ensure clear communication",
      "Remove blockers",
      "Foster team culture"
    ],
    "success_indicators": [
      "Team satisfaction score >4.0",
      "Low turnover rate",
      "Consistent sprint velocity"
    ]
  }
}
```

---

### Пример 3: Clear Resource

**Input**:
```
Title: "Python Async Programming Guide"
Body: """
# Python Async Programming Guide

A comprehensive collection of asyncio tutorials, patterns, and best practices.

**Category**: Tutorial / Reference Guide
**Tags**: #python #async #asyncio #concurrency
**Last Updated**: 2024-10-01

## Contents
- Introduction to async/await syntax
- Common asyncio patterns (gather, wait_for, etc.)
- Error handling in async code
- Testing async functions
- Performance considerations

## Resources
- Official Python docs: https://docs.python.org/3/library/asyncio.html
- Real Python tutorial: https://realpython.com/async-io-python/
- Code examples: https://github.com/...
"""
```

**Output**:
```json
{
  "para_type": "Resource",
  "confidence": 0.94,
  "reasoning": "Pure reference material with no action required, explicitly categorized and tagged for learning",
  "attributes": {
    "topic": "Python Async Programming",
    "description": "Comprehensive collection of asyncio tutorials, patterns, and best practices",
    "category": "Tutorial",
    "tags": ["python", "async", "asyncio", "concurrency"],
    "source_type": "curated collection",
    "last_reviewed": "2024-10-01"
  }
}
```

---

### Пример 4: Archive

**Input**:
```
Title: "[COMPLETED] Q2 2023 Marketing Campaign"
Body: """
# Q2 2023 Marketing Campaign - POST-MORTEM

**Status**: Completed on 2023-06-30
**Original Goal**: Achieve 5,000 new signups by end of Q2

## Outcome
Successfully completed! Results:
- 7,500 signups (150% of target)
- Conversion rate: 6.2% (exceeded 5% target)
- Total budget used: $45k (under $50k budget)

## Lessons Learned
- Social media ads (Instagram/TikTok) performed better than expected
- Email campaign had lower engagement than previous quarters
- Influencer partnerships were highly effective

## Archive Reason
Project successfully completed. Learnings documented for future campaigns.
"""
```

**Output**:
```json
{
  "para_type": "Archive",
  "confidence": 0.91,
  "reasoning": "Explicitly marked as completed with retrospective analysis and outcomes documented",
  "attributes": {
    "original_type": "Project",
    "original_name": "Q2 2023 Marketing Campaign",
    "archived_at": "2023-06-30",
    "archival_reason": "Project successfully completed",
    "outcome": "Achieved 7,500 signups (150% of target), conversion rate 6.2%, under budget. Key learnings: social media ads effective, influencer partnerships successful."
  }
}
```

---

### Пример 5: Null Classification

**Input**:
```
Title: "Meeting Notes - Oct 27"
Body: """
Quick sync with John and Sarah.

- Discussed current API redesign progress
- John mentioned performance issues with database queries
- Sarah will look into caching strategies
- Follow-up meeting next week
"""
```

**Output**:
```json
{
  "para_type": null,
  "confidence": 0.38,
  "reasoning": "Meeting notes without clear PARA structure - could be related to a Project but not the project itself. Insufficient markers for classification.",
  "attributes": {}
}
```

---

## Связанные Документы

- **Назад**: [02_ARCHITECTURE_DECISION.md](./02_ARCHITECTURE_DECISION.md)
- **Далее**: [04_EDGE_ENRICHMENT.md](./04_EDGE_ENRICHMENT.md) - Расширенный edge_type_map
- **Реализация**: [05_IMPLEMENTATION_PLAN.md](./05_IMPLEMENTATION_PLAN.md) - Пошаговый план

---

## Checklist для Имплементации

- [ ] Создать `_build_classification_prompt()` метод
- [ ] Реализовать `classify_note_as_para()` с error handling
- [ ] Добавить `_extract_json_from_response()` helper
- [ ] Реализовать `_validate_para_attributes()` с Pydantic валидацией
- [ ] Добавить truncation strategy для длинных заметок
- [ ] Реализовать кеширование результатов (optional)
- [ ] Настроить логирование метрик
- [ ] Написать unit tests с примерами из этого документа
- [ ] Протестировать граничные случаи (короткие заметки, диалоги, смешанные)
- [ ] Измерить производительность (время классификации)
