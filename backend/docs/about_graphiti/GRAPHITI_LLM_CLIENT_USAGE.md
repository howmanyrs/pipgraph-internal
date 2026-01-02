# Использование Graphiti LLM Client

Руководство по использованию LLM клиента graphiti для формирования запросов к языковым моделям.

## Содержание

- [Введение](#введение)
- [Примеры использования](#примеры-использования)
- [Рекомендации: Graphiti vs LangChain](#рекомендации-graphiti-vs-langchain)
- [Практический пример: замена mock на LLM](#практический-пример-замена-mock-на-llm)
- [Патчи для специфичных провайдеров](#патчи-для-специфичных-провайдеров)

---

## Введение

### Что такое Graphiti LLM Client

Graphiti предоставляет унифицированный интерфейс для работы с различными LLM провайдерами. Основной метод — `generate_response`:

```python
async def generate_response(
    messages: list[Message],                    # Список сообщений (system + user)
    response_model: type[BaseModel] | None,     # Pydantic модель для структуры ответа
    max_tokens: int | None = None,              # Лимит токенов
    model_size: ModelSize = ModelSize.medium,   # Размер модели (small/medium)
) -> dict[str, Any]
```

### Как работает response_model

Для `OpenAIGenericClient` (OpenRouter, Ollama и другие совместимые API) `response_model` обрабатывается так:

1. JSON schema модели сериализуется через `model_json_schema()`
2. Schema добавляется к последнему сообщению:
   ```
   Respond with a JSON object in the following format:
   {"properties": {"field": {"type": "string"}, ...}, ...}
   ```
3. Устанавливается `response_format={'type': 'json_object'}`
4. LLM возвращает JSON, который можно валидировать через Pydantic

> **Примечание**: `OpenAIClient` (нативный OpenAI API) использует Structured Outputs API, передавая `response_model` напрямую в `responses.parse()`.

---

## Примеры использования

### Пример 1: Минимальный промпт

Создание простого запроса без использования фабрики промптов:

```python
from graphiti_core.prompts.models import Message
from graphiti_core.llm_client import OpenAIGenericClient
from graphiti_core.llm_client.config import LLMConfig
from pydantic import BaseModel, Field

# 1. Определяем структуру ответа
class ParaClassification(BaseModel):
    """Результат классификации заметки по методологии PARA."""
    para_type: str = Field(
        description="Один из: Project, Area, Resource, Archive"
    )
    confidence: float = Field(
        description="Уверенность классификации от 0 до 1"
    )
    reasoning: str = Field(
        description="Обоснование выбора категории"
    )


# 2. Создаём LLM клиент
config = LLMConfig(
    api_key="sk-or-v1-...",
    base_url="https://openrouter.ai/api/v1",
    model="anthropic/claude-3-haiku"
)
llm_client = OpenAIGenericClient(config)


# 3. Формируем промпт как список Message
note_content = "Нужно подготовить презентацию для клиента до пятницы"

messages = [
    Message(
        role='system',
        content='Ты эксперт по методологии PARA (Projects, Areas, Resources, Archive). '
                'Классифицируй заметки пользователя по категориям PARA.'
    ),
    Message(
        role='user',
        content=f'''Классифицируй следующую заметку:

<NOTE>
{note_content}
</NOTE>

Верни JSON с полями para_type, confidence и reasoning.'''
    ),
]


# 4. Вызываем LLM
async def classify():
    response = await llm_client.generate_response(
        messages,
        response_model=ParaClassification
    )

    # 5. Валидируем через Pydantic
    result = ParaClassification(**response)

    print(f"Тип: {result.para_type}")        # "Project"
    print(f"Уверенность: {result.confidence}")  # 0.92
    print(f"Причина: {result.reasoning}")     # "Содержит дедлайн и конкретное действие..."

    return result
```

---

### Пример 2: Функция-фабрика промптов (паттерн Graphiti)

Graphiti использует паттерн фабрики промптов — функции, которые принимают контекст и возвращают `list[Message]`:

```python
from graphiti_core.prompts.models import Message
from pydantic import BaseModel, Field
from typing import Any


# Модель ответа
class ExtractedTasks(BaseModel):
    """Извлечённые задачи из заметки."""
    tasks: list[str] = Field(
        description="Список извлечённых задач"
    )
    has_deadline: bool = Field(
        description="Есть ли в заметке упоминание дедлайнов"
    )
    priority: str = Field(
        description="Приоритет: high, medium, low"
    )


# Функция-фабрика промптов
def extract_tasks_prompt(context: dict[str, Any]) -> list[Message]:
    """
    Создаёт промпт для извлечения задач.

    Args:
        context: Словарь с ключами:
            - note_content: str - текст заметки
            - previous_notes: list[str] | None - предыдущие заметки для контекста
            - user_preferences: dict | None - настройки пользователя

    Returns:
        list[Message] для передачи в generate_response
    """
    previous_context = ""
    if context.get('previous_notes'):
        previous_context = f"""
<PREVIOUS_CONTEXT>
{chr(10).join(context['previous_notes'][-3:])}
</PREVIOUS_CONTEXT>
"""

    return [
        Message(
            role='system',
            content='''Ты помощник для извлечения задач из заметок.
Извлекай только конкретные, выполнимые действия.
Игнорируй общие размышления и заметки без действий.'''
        ),
        Message(
            role='user',
            content=f'''
{previous_context}
<NOTE>
{context['note_content']}
</NOTE>

Извлеки все задачи из NOTE. Определи приоритет на основе срочности и важности.
'''
        ),
    ]


# Использование
async def extract_tasks_from_note(note: str, llm_client) -> ExtractedTasks:
    context = {
        'note_content': note,
        'previous_notes': None
    }

    response = await llm_client.generate_response(
        extract_tasks_prompt(context),  # Вызываем фабрику
        response_model=ExtractedTasks
    )

    return ExtractedTasks(**response)


# Пример вызова
async def main():
    result = await extract_tasks_from_note(
        "Завтра встреча с командой в 10:00. Подготовить отчёт. "
        "Также не забыть купить кофе для офиса.",
        llm_client
    )
    # result.tasks = ["Подготовить отчёт", "Купить кофе для офиса"]
    # result.has_deadline = True
    # result.priority = "high"
```

---

### Пример 3: Сложная модель с вложенностью

Для извлечения графовых структур используйте вложенные Pydantic модели:

```python
from pydantic import BaseModel, Field
from typing import Any


# Вложенные модели
class Entity(BaseModel):
    """Извлечённая сущность."""
    name: str = Field(description="Имя сущности")
    entity_type: str = Field(
        description="Тип: Person, Organization, Project, Area, Resource, Concept"
    )
    attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="Дополнительные атрибуты сущности"
    )


class Relationship(BaseModel):
    """Связь между сущностями."""
    source: str = Field(description="Имя исходной сущности")
    target: str = Field(description="Имя целевой сущности")
    relation_type: str = Field(
        description="Тип связи в SCREAMING_SNAKE_CASE (WORKS_ON, BELONGS_TO, RELATED_TO)"
    )
    fact: str = Field(description="Описание факта связи")


class GraphExtraction(BaseModel):
    """Результат извлечения графа знаний."""
    entities: list[Entity] = Field(
        description="Список извлечённых сущностей"
    )
    relationships: list[Relationship] = Field(
        description="Список связей между сущностями"
    )
    summary: str = Field(
        description="Краткое резюме заметки в одном предложении"
    )


# Промпт для извлечения графа
def extract_graph_prompt(context: dict[str, Any]) -> list[Message]:
    return [
        Message(
            role='system',
            content='''Ты эксперт по извлечению графов знаний из текста.
Извлекай сущности и связи между ними.
Используй SCREAMING_SNAKE_CASE для типов связей.
Не придумывай связи, которых нет в тексте.'''
        ),
        Message(
            role='user',
            content=f'''
<NOTE>
{context['note_content']}
</NOTE>

Извлеки все сущности и связи между ними.
Для каждой связи укажи конкретный факт из текста.
'''
        ),
    ]


# Использование
async def extract_knowledge_graph(note: str, llm_client) -> GraphExtraction:
    response = await llm_client.generate_response(
        extract_graph_prompt({'note_content': note}),
        response_model=GraphExtraction
    )

    result = GraphExtraction(**response)

    # Пример обработки результата
    for entity in result.entities:
        print(f"Entity: {entity.name} ({entity.entity_type})")

    for rel in result.relationships:
        print(f"  {rel.source} --[{rel.relation_type}]--> {rel.target}")
        print(f"    Fact: {rel.fact}")

    return result


# Пример
# Входной текст: "Иван работает над проектом Альфа в компании ТехКорп"
#
# Результат:
# entities = [
#     Entity(name="Иван", entity_type="Person"),
#     Entity(name="Альфа", entity_type="Project"),
#     Entity(name="ТехКорп", entity_type="Organization")
# ]
# relationships = [
#     Relationship(source="Иван", target="Альфа", relation_type="WORKS_ON",
#                  fact="Иван работает над проектом Альфа"),
#     Relationship(source="Иван", target="ТехКорп", relation_type="EMPLOYED_BY",
#                  fact="Иван работает в компании ТехКорп")
# ]
```

---

## Рекомендации: Graphiti vs LangChain

### Сравнительная таблица

| Критерий | Graphiti LLM Client | LangChain |
|----------|---------------------|-----------|
| **Зависимости** | Минимум (openai, pydantic) | Много (langchain-core, langchain-openai, ...) |
| **Контроль над промптами** | Полный — видно что отправляется | Абстрагирован через templates |
| **Отладка** | Прозрачно — простой dict/list | Сложнее — цепочки абстракций |
| **Structured Output** | JSON schema в промпте | `with_structured_output()` |
| **Интеграция с Neo4j** | Нативная через graphiti | Требует отдельной настройки |
| **Retry логика** | Встроенная с error feedback | Через `tenacity` или вручную |
| **Кривая обучения** | Низкая | Средняя-высокая |

### Когда использовать Graphiti LLM Client

- Проект уже использует graphiti для работы с графом
- Нужен полный контроль над промптами
- Важна простота отладки
- Не требуются сложные цепочки (chains) и агенты

### Когда использовать LangChain

- Нужны готовые интеграции с многими инструментами
- Требуются сложные цепочки обработки
- Используется LCEL (LangChain Expression Language)
- Проект не завязан на graphiti

### Рекомендация для PipGraph

**Использовать Graphiti LLM Client**, потому что:

1. Graphiti уже в зависимостях проекта
2. Нет необходимости в сложных цепочках — workflow управляется через LangGraph
3. Проще контролировать и отлаживать промпты
4. Меньше абстракций между кодом и LLM

---

## Практический пример: замена mock на LLM

### Текущая архитектура

В `app/services/para/__init__.py` используется переключение между mock и реальными реализациями:

```python
# Текущая конфигурация: MOCK
from app.services.mocks.mock_classifier import classify_note_para

# Для LLM: раскомментировать
# from app.services.llm.real_classifier import classify_note_para
```

### Реализация real_classifier.py

Создайте файл `app/services/llm/real_classifier.py`:

```python
"""
Реальная LLM реализация классификатора PARA.

Заменяет mock_classifier.py для production использования.
"""

from graphiti_core.llm_client import OpenAIGenericClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.prompts.models import Message
from pydantic import BaseModel, Field

from app.core.config import settings


# Модель ответа
class PARAClassificationResult(BaseModel):
    """Результат L1 классификации."""
    para_type: str = Field(
        description="Тип PARA: Project, Area, Resource, Archive"
    )
    confidence: float = Field(
        description="Уверенность от 0 до 1"
    )
    reasoning: str = Field(
        description="Краткое обоснование"
    )


# Фабрика промптов
def para_classification_prompt(note_content: str) -> list[Message]:
    return [
        Message(
            role='system',
            content='''Ты классификатор заметок по методологии PARA:

- **Project**: Имеет конкретную цель и дедлайн. Примеры: "Подготовить отчёт к пятнице", "Запустить сайт".
- **Area**: Область ответственности без конкретного дедлайна. Примеры: "Здоровье", "Финансы", "Команда".
- **Resource**: Справочная информация, интересы. Примеры: "Рецепты", "Книги для чтения", "Полезные ссылки".
- **Archive**: Завершённые или неактивные элементы.

Классифицируй заметку в одну категорию.'''
        ),
        Message(
            role='user',
            content=f'''Классифицируй заметку:

<NOTE>
{note_content}
</NOTE>'''
        ),
    ]


# Singleton клиент
_llm_client: OpenAIGenericClient | None = None


def get_llm_client() -> OpenAIGenericClient:
    """Получить или создать LLM клиент."""
    global _llm_client
    if _llm_client is None:
        config = LLMConfig(
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
            model=settings.LLM_MODEL or "anthropic/claude-3-haiku",
            temperature=0.0,
        )
        _llm_client = OpenAIGenericClient(config)
    return _llm_client


async def classify_note_para(note_content: str) -> str:
    """
    Классифицирует заметку по типу PARA используя LLM.

    Args:
        note_content: Текст заметки

    Returns:
        Тип PARA: "Project", "Area", "Resource", или "Archive"
    """
    client = get_llm_client()

    response = await client.generate_response(
        para_classification_prompt(note_content),
        response_model=PARAClassificationResult
    )

    result = PARAClassificationResult(**response)

    # Валидация типа
    valid_types = {"Project", "Area", "Resource", "Archive"}
    if result.para_type not in valid_types:
        # Fallback на Resource если тип неизвестен
        return "Resource"

    return result.para_type
```

### Переключение на реальную реализацию

В `app/services/para/__init__.py`:

```python
# ============================================================================
# Переключение: закомментируйте одну секцию, раскомментируйте другую
# ============================================================================

# MOCK реализации (для разработки и тестов)
# from app.services.mocks.mock_classifier import classify_note_para
# from app.services.mocks.mock_proposal_generator import generate_para_proposal

# LLM реализации (для production)
from app.services.llm.real_classifier import classify_note_para
from app.services.llm.real_proposal_generator import generate_para_proposal
```

### Тестирование

```python
# tests/services/test_real_classifier.py
import pytest
from app.services.llm.real_classifier import classify_note_para


@pytest.mark.asyncio
@pytest.mark.integration  # Пометка для интеграционных тестов
async def test_classify_project():
    result = await classify_note_para(
        "Нужно подготовить презентацию для клиента до пятницы"
    )
    assert result == "Project"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_classify_area():
    result = await classify_note_para(
        "Регулярно проверять здоровье команды и проводить 1-on-1"
    )
    assert result == "Area"
```

---

## Патчи для специфичных провайдеров

### Проблема

Разные LLM провайдеры по-разному интерпретируют JSON schema инструкции. Graphiti использует стандартный формат:

```
Respond with a JSON object in the following format:
{schema}
```

Но некоторые модели (например, Qwen на Cloud.ru) **копируют schema в ответ** вместо того, чтобы вернуть данные:

```json
// Ожидаемый ответ:
{"para_type": "Project", "confidence": 0.9}

// Проблемный ответ Qwen:
{
  "properties": {"para_type": {...}},  // ← schema!
  "required": [...],
  "type": "object",
  "para_type": "Project",              // ← данные смешаны со schema
  "confidence": 0.9
}
```

### Решение: Патч-клиенты

Для таких случаев создаются патч-клиенты в `app/services/graphiti/`:

| Файл | Провайдер | Проблема | Решение |
|------|-----------|----------|---------|
| `graphiti/patched_client.py` | Cloud.ru (Qwen) | Копирует schema в ответ | Изменена инструкция на "return data only, not the schema" |

### Использование патч-клиента

```python
# Вместо стандартного клиента
# from graphiti_core.llm_client import OpenAIGenericClient

# Используем патч для Cloud.ru
from app.services.graphiti.patched_client import CloudRuPatchedClient

config = LLMConfig(
    api_key=settings.CLOUDRU_API_KEY,
    base_url="https://api.cloud.ru/v1",
    model="qwen/qwen-2.5-72b",
)

# Патч-клиент имеет тот же интерфейс
llm_client = CloudRuPatchedClient(config)
response = await llm_client.generate_response(messages, ResponseModel)
```

### Как создать патч для нового провайдера

1. **Создайте файл** `app/services/graphiti/{provider}_patched_client.py`

2. **Наследуйтесь от OpenAIGenericClient**:
   ```python
   from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient

   class NewProviderPatchedClient(OpenAIGenericClient):
       """
       Patched client for {Provider}.

       Problem: {описание проблемы}
       Solution: {описание решения}
       """
   ```

3. **Переопределите нужный метод** (обычно `generate_response`):
   ```python
   async def generate_response(self, messages, response_model=None, ...):
       # Ваш патч здесь
       if response_model is not None:
           serialized_model = json.dumps(response_model.model_json_schema())
           messages[-1].content += f'\n\n{YOUR_CUSTOM_INSTRUCTION}\n\n{serialized_model}'

       # Остальная логика из родительского класса
       ...
   ```

4. **Задокументируйте** в docstring:
   - Какая проблема решается
   - Как именно патч её решает
   - Ссылка на исследование (если есть)

### Реестр патчей

Для отслеживания всех патчей ведите таблицу в этом документе (раздел выше) или создайте отдельный файл `app/services/PATCHES.md`.

> **Важно**: При обновлении `graphiti_core` проверяйте, не исправлена ли проблема в новой версии, и не конфликтует ли патч с изменениями.

---

## См. также

- [GRAPHITI_QUICK_REFERENCE.md](GRAPHITI_QUICK_REFERENCE.md) — краткий справочник по graphiti
- [GRAPHITI_CUSTOM_ENTITIES.md](GRAPHITI_CUSTOM_ENTITIES.md) — кастомные типы сущностей
- Исходный код: `graphiti_core/llm_client/openai_generic_client.py`
- Примеры использования: `graphiti_core/utils/maintenance/node_operations.py`
- Патч для Cloud.ru: `app/services/graphiti/patched_client.py`
