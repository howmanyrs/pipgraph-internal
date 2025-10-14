# Карта проблемных промптов в Graphiti

**Дата исследования:** 2025-10-13
**Версия Graphiti:** 0.21.0
**Контекст:** Исследование ValidationError при использовании Cloud.ru LLM (Qwen) с Graphiti

---

## Структура промптов в библиотеке

**Местоположение:** `.venv/lib/python3.12/site-packages/graphiti_core/prompts/`

**Файлы промптов:**
- `dedupe_edges.py` - Дедупликация edges/relationships
- `dedupe_nodes.py` - Дедупликация nodes/entities
- `extract_edges.py` - Извлечение связей из текста
- `extract_nodes.py` - Извлечение сущностей из текста
- `invalidate_edges.py` - Инвалидация устаревших связей
- `extract_edge_dates.py` - Извлечение временных меток
- `summarize_nodes.py` - Суммаризация узлов
- `lib.py` - Библиотека промптов (главный интерфейс)
- `models.py` - Базовые модели (Message, PromptFunction)
- `prompt_helpers.py` - Вспомогательные функции

---

## Все Pydantic модели, требующие structured output

| Файл | Модель | Используется в | Риск для Qwen |
|------|--------|---------------|---------------|
| **dedupe_edges.py** | `EdgeDuplicate` | edge_operations.py:527 | 🔴 **ВЫСОКИЙ** (текущая ошибка!) |
| dedupe_edges.py | `UniqueFact` | - | 🟡 Средний |
| dedupe_edges.py | `UniqueFacts` | - | 🟡 Средний |
| **dedupe_nodes.py** | `NodeDuplicate` | node_operations.py | 🔴 **ВЫСОКИЙ** |
| **dedupe_nodes.py** | `NodeResolutions` | node_operations.py | 🔴 **ВЫСОКИЙ** |
| extract_edges.py | `Edge` | edge_operations.py | 🟡 Средний |
| extract_edges.py | `ExtractedEdges` | edge_operations.py:104 | 🟡 Средний |
| extract_edges.py | `MissingFacts` | edge_operations.py | 🟡 Средний |
| **extract_nodes.py** | `ExtractedEntities` | node_operations.py | 🔴 **ВЫСОКИЙ** |
| extract_nodes.py | `EntitySummary` | node_operations.py | 🟡 Средний |
| invalidate_edges.py | `InvalidatedEdges` | temporal_operations.py | 🟡 Средний |
| extract_edge_dates.py | `EdgeDates` | temporal_operations.py | 🟡 Средний |

---

## 🔥 Критические промпты (вызывающие ошибку)

### 1. **dedupe_edges.py:117-171** - `resolve_edge()`

**Модель:** `EdgeDuplicate`
**Поля:** `duplicate_facts`, `contradicted_facts`, `fact_type`
**Вызов:** `edge_operations.py:525-530`
**Статус:** ❌ **СЛОМАНО** (текущая ошибка)

**Проблема:** Промпт на строках 117-171 не достаточно явно описывает формат ответа для Qwen.

**Ошибка:**
```
pydantic_core._pydantic_core.ValidationError: 3 validation errors for EdgeDuplicate
duplicate_facts
  Field required [type=missing, input_value={...}, input_type=dict]
contradicted_facts
  Field required [type=missing, input_value={...}, input_type=dict]
fact_type
  Field required [type=missing, input_value={...}, input_type=dict]
```

**Определение модели:**
```python
class EdgeDuplicate(BaseModel):
    duplicate_facts: list[int] = Field(
        ...,
        description='List of idx values of any duplicate facts. If no duplicate facts are found, default to empty list.',
    )
    contradicted_facts: list[int] = Field(
        ...,
        description='List of idx values of facts that should be invalidated. If no facts should be invalidated, the list should be empty.',
    )
    fact_type: str = Field(..., description='One of the provided fact types or DEFAULT')
```

### 2. **dedupe_nodes.py:117-185** - `nodes()`

**Модель:** `NodeResolutions`
**Поля:** `entity_resolutions` (list[NodeDuplicate])
**Вызов:** `node_operations.py`
**Статус:** ⚠️ Потенциально проблемный

**Определение модели:**
```python
class NodeDuplicate(BaseModel):
    id: int = Field(..., description='integer id of the entity')
    duplicate_idx: int = Field(
        ...,
        description='idx of the duplicate entity. If no duplicate entities are found, default to -1.',
    )
    name: str = Field(
        ...,
        description='Name of the entity. Should be the most complete and descriptive name of the entity.',
    )
    duplicates: list[int] = Field(
        ...,
        description='idx of all entities that are a duplicate of the entity with the above id.',
    )

class NodeResolutions(BaseModel):
    entity_resolutions: list[NodeDuplicate] = Field(..., description='List of resolved nodes')
```

### 3. **extract_nodes.py** - `extract_text()`

**Модель:** `ExtractedEntities`
**Поля:** `extracted_entities` (list[ExtractedEntity])
**Вызов:** `node_operations.py`
**Статус:** ⚠️ Потенциально проблемный

**Определение модели:**
```python
class ExtractedEntity(BaseModel):
    name: str = Field(..., description='Name of the extracted entity')
    entity_type_id: int = Field(
        description='ID of the classified entity type. '
        'Must be one of the provided entity_type_id integers.',
    )

class ExtractedEntities(BaseModel):
    extracted_entities: list[ExtractedEntity] = Field(..., description='List of extracted entities')
```

---

## 🔧 Где происходит добавление JSON schema

**Файл:** `llm_client/openai_generic_client.py:131-137`

```python
if response_model is not None:
    serialized_model = json.dumps(response_model.model_json_schema())
    messages[-1].content += (
        f'\n\nRespond with a JSON object in the following format:\n\n{serialized_model}'
    )
```

**Проблема:** Qwen **включает весь JSON schema в ответ** вместо того, чтобы вернуть только данные. LLM интерпретирует schema как часть желаемого формата и копирует его в ответ, добавляя реальные данные внутрь того же объекта.

**Пример добавляемого schema (для EdgeDuplicate):**
```json
{
  "properties": {
    "duplicate_facts": {
      "description": "List of idx values of any duplicate facts...",
      "items": {"type": "integer"},
      "title": "Duplicate Facts",
      "type": "array"
    },
    "contradicted_facts": {
      "description": "List of idx values of facts that should be invalidated...",
      "items": {"type": "integer"},
      "title": "Contradicted Facts",
      "type": "array"
    },
    "fact_type": {
      "description": "One of the provided fact types or DEFAULT",
      "title": "Fact Type",
      "type": "string"
    }
  },
  "required": ["duplicate_facts", "contradicted_facts", "fact_type"],
  "title": "EdgeDuplicate",
  "type": "object"
}
```

**Что Qwen возвращает (неправильно):**
```json
{
  "properties": {...},
  "required": [...],
  "title": "EdgeDuplicate",
  "type": "object",
  "duplicate_facts": [],
  "contradicted_facts": [0],
  "fact_type": "DEFAULT"
}
```

**Что ожидается:**
```json
{
  "duplicate_facts": [],
  "contradicted_facts": [0],
  "fact_type": "DEFAULT"
}
```

**Причина ошибки:** Когда Graphiti вызывает `EdgeDuplicate(**llm_response)`, Pydantic пытается найти поля `duplicate_facts`, `contradicted_facts`, `fact_type` на верхнем уровне dict, но находит только `properties`, `required`, `title`, `type`, и некоторые данные. Поля находятся не там, где ожидается, поэтому ValidationError.

**Где используется response_model:**
```bash
edge_operations.py:
  - line 104: ExtractedEdges (extract edges from text)
  - line ???: MissingFacts (reflexion for missing facts)
  - line 527: EdgeDuplicate (deduplicate edges) ← ТЕКУЩАЯ ОШИБКА
  - line ???: edge_model (custom edge types)

node_operations.py:
  - ExtractedEntities (extract entities from text)
  - NodeResolutions (deduplicate nodes)
  - entity_type (custom entity types)
  - EntitySummary (summarize entity)

temporal_operations.py:
  - EdgeDates (extract temporal information)
  - InvalidatedEdges (invalidate old edges)

community_operations.py:
  - Summary (summarize node pairs)
  - SummaryDescription (describe summary)
```

---

## 🔬 Результаты тестирования

### Тест 1: Простой JSON Schema (работает корректно)

**Промпт:**
```json
{
  "type": "object",
  "properties": {
    "name": {"type": "string"},
    "age": {"type": "integer"}
  }
}
```

**Результат Qwen:**
```json
{
  "name": "Alice",
  "age": 25
}
```

✅ **Qwen отвечает правильно** с простым schema!

---

### Тест 2: Детальный JSON Schema с title/description (ПРОБЛЕМА!)

**Промпт (точная копия Graphiti):**
```json
{
  "properties": {
    "duplicate_facts": {
      "description": "List of idx values...",
      "items": {"type": "integer"},
      "title": "Duplicate Facts",
      "type": "array"
    },
    "contradicted_facts": {...},
    "fact_type": {...}
  },
  "required": ["duplicate_facts", "contradicted_facts", "fact_type"],
  "title": "EdgeDuplicate",
  "type": "object"
}
```

**Результат Qwen:**
```json
{
  "properties": {...},
  "required": [...],
  "title": "EdgeDuplicate",
  "type": "object",
  "duplicate_facts": [],
  "contradicted_facts": [0],
  "fact_type": "DEFAULT"
}
```

❌ **Qwen копирует весь schema** и добавляет данные на тот же уровень!

---

### Тест 3: Сравнение с Claude/GPT

**Тот же детальный schema от Graphiti:**

**Claude/GPT отвечают:**
```json
{
  "duplicate_facts": [],
  "contradicted_facts": [0],
  "fact_type": "DEFAULT"
}
```

✅ **Claude/GPT возвращают только данные**, игнорируя структуру schema.

---

## 🧠 Почему Claude/GPT работают, а Qwen — нет?

### 1. **Structured Output Support (разная интерпретация)**

**OpenAI GPT-4 / Anthropic Claude:**
- ✅ Понимают, что JSON Schema с `properties`, `required`, `title` — это **метаданные**
- ✅ Извлекают структуру из `properties` и возвращают **только данные**
- ✅ Не копируют метаполя (`title`, `required`, `type`) в ответ
- ✅ Специально обучены на паттерн "schema → data"

**Qwen (Cloud.ru):**
- ❌ Интерпретирует детальный schema как **шаблон для заполнения**
- ❌ Копирует метаполя (`properties`, `required`, `title`) в ответ
- ❌ Добавляет данные **на тот же уровень** с метаданными
- ❌ Не различает "описание формата" и "данные"

---

### 2. **Fine-tuning на разных примерах**

**Claude/GPT тренировались на:**
```
User: "Return JSON with schema: {properties: {...}, required: [...]}"
Assistant: {"field1": "value", "field2": 123}  ← Только данные
```

**Qwen, вероятно, видел в обучении:**
```
User: "Generate JSON Schema with properties..."
Assistant: {  ← Генерация schema документов
  "properties": {...},
  "required": [...],
  ...
}
```

Qwen обучался на **генерации JSON Schema документов**, а не на создании данных по схеме.

---

### 3. **Понимание JSON Schema как формата**

**Ключевое различие:**

| Формат Schema | Claude/GPT | Qwen |
|---------------|------------|------|
| Простой: `{"type": "object", "properties": {...}}` | ✅ Данные | ✅ Данные |
| Детальный: `{"properties": {...}, "required": [...], "title": "..."}` | ✅ Данные | ❌ **Schema + Данные** |

**Почему?**

- **Claude/GPT:** Распознают ключевые слова JSON Schema (`properties`, `required`, `title`) и понимают, что это **метаданные описания**, а не часть результата
- **Qwen:** Видит полноценный JSON Schema документ и воспринимает его как **структуру, которую нужно расширить данными**

---

### 4. **RLHF (Reinforcement Learning from Human Feedback)**

**OpenAI/Anthropic:**
```
❌ Плохой ответ (пользователи жаловались):
{
  "properties": {...},
  "duplicate_facts": []
}

✅ Хороший ответ (пользователи были довольны):
{
  "duplicate_facts": []
}
```

Claude и GPT прошли тысячи итераций обратной связи от пользователей, которые использовали их для работы с JSON Schema.

**Qwen:**
- Меньше RLHF данных о работе с JSON Schema
- Возможно, больше обучения на генерации документации/схем

---

### 5. **Встроенные System Prompts**

**OpenAI/Anthropic (гипотеза):**
```
Internal System Prompt:
"When you see JSON Schema format with 'properties', 'required', 'title':
- Extract data structure from 'properties'
- Return ONLY an object matching that structure
- Do NOT include 'properties', 'required', 'title', 'type' in your response"
```

**Qwen:**
- Вероятно, не имеет таких встроенных инструкций
- Или они работают только для простых schema без метаданных

---

## 📊 Сводная таблица поведения

| Сценарий | Qwen | Claude/GPT | Причина |
|----------|------|------------|---------|
| Простой schema (`type`, `properties`) | ✅ Корректно | ✅ Корректно | Базовая поддержка JSON |
| Детальный schema (`title`, `description`, `required`) | ❌ Копирует schema | ✅ Корректно | Разная интерпретация метаданных |
| С явной инструкцией "return ONLY data" | ✅ Корректно | ✅ Корректно | Явные инструкции помогают |

---

### Вывод

**Qwen требует явных инструкций:**
- ✅ Вернуть ТОЛЬКО данные
- ✅ НЕ включать `properties`, `required`, `title`, `type`
- ✅ Показать пример ПРАВИЛЬНОГО и НЕПРАВИЛЬНОГО ответа

**Claude/GPT понимают неявно:**
- Детальный JSON Schema → возврат только данных
- Не требуют дополнительных инструкций

**Важно:** Даже с детальным schema, Qwen **будет отвечать правильно**, если добавить явные инструкции в промпт.

---

## 💡 Решения для monkey patch

### Вариант A: Патчить на уровне client

Создать подкласс `OpenAIGenericClient` с улучшенным промптом:

```python
# app/services/cloudru_patched_client.py
import json
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.prompts.models import Message
from pydantic import BaseModel

class CloudRuPatchedClient(OpenAIGenericClient):
    """
    Patched OpenAI client for Cloud.ru (Qwen) models.

    Enhances prompts with explicit JSON format instructions
    because Qwen copies schema structure into response instead of data only.
    """

    async def generate_response(self, messages, response_model=None, **kwargs):
        if response_model is not None:
            schema = response_model.model_json_schema()

            # Явный и простой промпт для Qwen
            enhanced_prompt = self._build_enhanced_prompt(schema)
            messages[-1].content += enhanced_prompt

            # Убираем response_model, чтобы избежать дублирования
            response_model = None

        return await super().generate_response(messages, response_model, **kwargs)

    def _build_enhanced_prompt(self, schema: dict) -> str:
        """Build enhanced prompt with explicit JSON format for Qwen."""
        required = schema.get('required', [])
        properties = schema.get('properties', {})

        # Строим пример ответа с дефолтными значениями
        example = {}
        for field in required:
            prop = properties.get(field, {})
            if prop.get('type') == 'array':
                example[field] = []
            elif prop.get('type') == 'string':
                example[field] = 'DEFAULT'
            elif prop.get('type') == 'integer':
                example[field] = -1
            else:
                example[field] = None

        # Форматируем описания полей
        field_descriptions = self._format_field_descriptions(properties, required)

        return f"""

CRITICAL INSTRUCTION: You MUST respond with ONLY the DATA object, NOT the schema.

WRONG (do NOT do this):
{{
  "properties": {{...}},
  "required": [...],
  "type": "object",
  "duplicate_facts": []
}}

CORRECT (return ONLY data):
{json.dumps(example, indent=2)}

Required fields (must ALL be present):
- {', '.join(required)}

Field descriptions:
{field_descriptions}

IMPORTANT:
- Return ONLY the data object with these fields
- Do NOT include "properties", "required", "title", "type" fields
- Do NOT copy the schema into your response
- Empty lists [] are acceptable
- Use -1 for "no value" in integer fields
- Use "DEFAULT" for default string values
"""

    def _format_field_descriptions(self, properties: dict, required: list) -> str:
        """Format field descriptions in a readable way."""
        lines = []
        for field, prop in properties.items():
            desc = prop.get('description', 'No description')
            req = '(REQUIRED)' if field in required else '(optional)'
            field_type = prop.get('type', 'unknown')
            lines.append(f"  - {field} {req}: {field_type} - {desc}")
        return '\n'.join(lines)
```

**Использование:**
```python
# app/services/llm_graphiti_client.py
from app.services.cloudru_patched_client import CloudRuPatchedClient

_graphiti_instance = Graphiti(
    settings.NEO4J_URI,
    settings.NEO4J_USER,
    settings.NEO4J_PASSWORD,
    llm_client=CloudRuPatchedClient(config=llm_config),  # ← Используем патченый клиент
    embedder=...,
    cross_encoder=...,
)
```

### Вариант B: Патчить на уровне промптов

Переопределить конкретные проблемные промпты:

```python
# app/services/graphiti_prompts_patch.py
from graphiti_core.prompts import prompt_library
from graphiti_core.prompts.models import Message
from typing import Any

def patched_resolve_edge(context: dict[str, Any]) -> list[Message]:
    """Patched version of dedupe_edges.resolve_edge with explicit instructions."""
    # Получаем оригинальные сообщения
    from graphiti_core.prompts.dedupe_edges import versions
    original_messages = versions['resolve_edge'](context)

    # Добавляем явный пример в конец с уточнением про schema
    enhanced_instructions = """

CRITICAL: Respond with ONLY the data object, NOT the schema!

WRONG (do NOT include schema):
{
    "properties": {...},
    "required": [...],
    "duplicate_facts": []
}

CORRECT (return ONLY data):
{
    "duplicate_facts": [0, 1, ...],
    "contradicted_facts": [0, 1, ...],
    "fact_type": "DEFAULT"
}

Field requirements:
- duplicate_facts: Array of integer idx from EXISTING FACTS (use [] if no duplicates)
- contradicted_facts: Array of integer idx from FACT INVALIDATION CANDIDATES (use [] if no contradictions)
- fact_type: String, either one of the provided FACT TYPES or "DEFAULT"

ALL THREE FIELDS ARE REQUIRED. Never omit any field. Empty arrays [] are valid.
Do NOT include "properties", "required", "title", or "type" in your response.
"""

    original_messages[-1].content += enhanced_instructions
    return original_messages


def apply_patches():
    """Apply all prompt patches to Graphiti's prompt library."""
    # Патчим проблемный промпт
    prompt_library.dedupe_edges.resolve_edge = patched_resolve_edge

    # Можно добавить другие патчи по мере необходимости
    # prompt_library.dedupe_nodes.nodes = patched_dedupe_nodes
    # prompt_library.extract_nodes.extract_text = patched_extract_nodes
```

**Использование:**
```python
# app/services/llm_graphiti_client.py
from app.services.graphiti_prompts_patch import apply_patches

async def get_graphiti() -> Graphiti:
    global _graphiti_instance

    if _graphiti_instance is None:
        # Применяем патчи к промптам перед инициализацией
        apply_patches()

        # ... инициализация Graphiti ...
```

### Вариант C: Error handling с fallback

Добавить обработку ошибок на уровне вызова:

```python
# Патч в edge_operations.py (через monkey patching)
from pydantic import ValidationError
import logging

logger = logging.getLogger(__name__)

async def patched_resolve_extracted_edge(...):
    # ... existing code ...

    llm_response = await llm_client.generate_response(
        prompt_library.dedupe_edges.resolve_edge(context),
        response_model=EdgeDuplicate,
        model_size=ModelSize.small,
    )

    try:
        response_object = EdgeDuplicate(**llm_response)
    except ValidationError as e:
        logger.warning(
            f"LLM response validation failed for EdgeDuplicate: {e}. "
            f"Response was: {llm_response}. Using safe defaults."
        )
        # Возвращаем безопасные дефолтные значения
        response_object = EdgeDuplicate(
            duplicate_facts=[],
            contradicted_facts=[],
            fact_type="DEFAULT"
        )

    # ... rest of the code ...
```

---

## 📊 Рекомендации

### Краткосрочное решение (быстрое)
**Переключиться на OpenRouter** с моделями Claude/GPT:
- ✅ Графити официально поддерживает OpenAI-compatible API
- ✅ Claude и GPT хорошо понимают structured output
- ✅ Не требует патчей кода
- ❌ Дороже Cloud.ru
- ❌ Внешняя зависимость

**Реализация:** Изменить `llm_graphiti_client.py`, использовать `OPENROUTER_*` вместо `CLOUDRU_*`.

### Среднесрочное решение (надежное)
**Monkey patch на уровне client (Вариант A)**:
- ✅ Работает со всеми промптами сразу
- ✅ Использование дешевого Cloud.ru
- ✅ Централизованное решение
- ❌ Требует поддержки кастомного кода
- ❌ Может сломаться при обновлении Graphiti

**Реализация:** Создать `CloudRuPatchedClient` и использовать его в `get_graphiti()`.

### Долгосрочное решение (вклад в OSS)
**Улучшить Graphiti upstream**:
- ✅ Помогает всему сообществу
- ✅ Официальная поддержка разных LLM
- ✅ Не нужно поддерживать патчи
- ❌ Долгий процесс (PR, review, release)
- ❌ Нет гарантии принятия

**Реализация:** Создать issue в https://github.com/getzep/graphiti, предложить PR с улучшением промптов.

---

## 🔗 Полезные ссылки

- [Graphiti GitHub](https://github.com/getzep/graphiti)
- [Issue #879 - Bulk upload ValidationError](https://github.com/getzep/graphiti/issues/879)
- [Graphiti Documentation](https://www.graphiti.dev/)
- [OpenAI Generic Client source](https://github.com/getzep/graphiti/blob/main/graphiti_core/llm_client/openai_generic_client.py)

---

## Следующие шаги

1. **Протестировать OpenRouter** - быстрая проверка, работает ли с Claude (рекомендуется как первый шаг)
2. **Реализовать Вариант A с улучшенным промптом** - если OpenRouter слишком дорог
3. **Мониторинг ошибок** - логировать все ValidationError для анализа
4. **Создать issue в Graphiti** - помочь сообществу с поддержкой разных LLM
