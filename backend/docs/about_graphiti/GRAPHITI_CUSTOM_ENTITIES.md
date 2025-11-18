# Graphiti Custom Entities: Field Descriptions Usage

## Введение

Этот документ объясняет, как Graphiti использует информацию о кастомных entity типах (Pydantic модели) для извлечения атрибутов из текста с помощью LLM.

## Двухэтапный процесс извлечения

Graphiti использует **два раздельных вызова LLM** для работы с кастомными entity:

### Этап 1: Классификация Entity (extract_nodes)

**Цель**: Определить, какие entity есть в тексте и к какому типу они относятся.

**Используется**: Только `__doc__` (docstring класса)

**Пример**:
```python
class Person(BaseModel):
    """A person entity with biographical information."""  # ← Используется здесь
    age: Optional[int] = Field(None, description="Age of the person")
```

### Этап 2: Извлечение атрибутов (extract_attributes_from_node)

**Цель**: Извлечь конкретные значения атрибутов для найденного entity.

**Используется**: Field `description` через JSON Schema

**Пример**:
```python
class Person(BaseModel):
    """A person entity with biographical information."""
    age: Optional[int] = Field(None, description="Age of the person")  # ← Используется здесь
    occupation: Optional[str] = Field(None, description="Current occupation")  # ← И здесь
```

## Детальный flow: Как используются Field descriptions

### Шаг 1: Формирование контекста

📍 **Файл**: `graphiti_core/utils/maintenance/node_operations.py:340-354`

```python
async def extract_attributes_from_node(
    llm_client: LLMClient,
    node: EntityNode,
    episode: EpisodicNode | None = None,
    previous_episodes: list[EpisodicNode] | None = None,
    entity_type: type[BaseModel] | None = None,  # ← Ваша Pydantic модель
):
    attributes_context = {
        'node': {
            'name': node.name,              # 'John Doe'
            'summary': node.summary,        # 'A software engineer'
            'entity_types': node.labels,    # ['Entity', 'Person']
            'attributes': node.attributes,  # {} (пока пусто)
        },
        'episode_content': episode.content,  # Текст заметки
        'previous_episodes': [...],          # История предыдущих эпизодов
    }
```

### Шаг 2: Вызов LLM с response_model

📍 **Файл**: `graphiti_core/utils/maintenance/node_operations.py:365-375`

```python
    llm_response = await llm_client.generate_response(
        prompt=prompt_library.extract_nodes.extract_attributes(attributes_context),
        response_model=entity_type,  # ← Ваш класс Person передается сюда
        model_size=ModelSize.small,
    )
```

### Шаг 3: Генерация базового промпта

📍 **Файл**: `graphiti_core/prompts/extract_nodes.py:250-277`

```python
def extract_attributes(context: dict[str, Any]) -> list[Message]:
    return [
        Message(
            role='system',
            content='You are a helpful assistant that extracts entity properties from the provided text.',
        ),
        Message(
            role='user',
            content=f"""
            <MESSAGES>
            {context['episode_content']}
            </MESSAGES>

            Given the above MESSAGES and the following ENTITY, update any of its attributes.
            Use the provided attribute descriptions to better understand how each attribute should be determined.

            <ENTITY>
            {context['node']}
            </ENTITY>
            """,
        ),
    ]
```

### Шаг 4: LLM Client добавляет JSON Schema

📍 **Файл**: `graphiti_core/llm_client/client.py:139-145`

**Ключевой момент**: JSON Schema генерируется из Pydantic модели и добавляется в промпт

```python
async def generate_response(
    self,
    messages: list[Message],
    response_model: type[BaseModel] | None = None,
    ...
):
    if response_model is not None:
        # Генерация JSON Schema из Pydantic модели
        serialized_model = json.dumps(response_model.model_json_schema())

        # Добавление схемы в конец промпта
        messages[-1].content += (
            f'\n\nRespond with a JSON object in the following format:\n\n{serialized_model}'
        )
```

### Шаг 5: Что видит LLM

**Пример для класса Person**:

```python
class Person(BaseModel):
    """A person entity with biographical information."""
    age: Optional[int] = Field(None, description="Age of the person")
    occupation: Optional[str] = Field(None, description="Current occupation")
    location: Optional[str] = Field(None, description="Current location")
```

**JSON Schema, добавленная в промпт**:

```json
{
  "description": "A person entity with biographical information.",
  "properties": {
    "age": {
      "anyOf": [{"type": "integer"}, {"type": "null"}],
      "default": null,
      "description": "Age of the person",  ← Field description попадает сюда
      "title": "Age"
    },
    "occupation": {
      "anyOf": [{"type": "string"}, {"type": "null"}],
      "default": null,
      "description": "Current occupation",  ← Field description попадает сюда
      "title": "Occupation"
    },
    "location": {
      "anyOf": [{"type": "string"}, {"type": "null"}],
      "default": null,
      "description": "Current location",  ← Field description попадает сюда
      "title": "Location"
    }
  },
  "title": "Person",
  "type": "object"
}
```

**Полный промпт для LLM**:

```
<MESSAGES>
John is 35 years old and works as a Senior Developer at Google in Mountain View.
</MESSAGES>

Given the above MESSAGES and the following ENTITY, update any of its attributes.
Use the provided attribute descriptions to better understand how each attribute should be determined.

<ENTITY>
{
  "name": "John Doe",
  "summary": "A software engineer",
  "entity_types": ["Entity", "Person"],
  "attributes": {}
}
</ENTITY>

Respond with a JSON object in the following format:

{
  "properties": {
    "age": {
      "type": "integer",
      "description": "Age of the person"  ← LLM читает это как инструкцию!
    },
    "occupation": {
      "type": "string",
      "description": "Current occupation"  ← И это!
    },
    "location": {
      "type": "string",
      "description": "Current location"  ← И это!
    }
  }
}
```

### Шаг 6: LLM анализирует и извлекает

LLM читает:
- **Текст**: "John is 35 years old and works as a Senior Developer at Google in Mountain View"
- **Инструкцию schema**: `"description": "Age of the person"`
- **Связывает**: "35 years old" → `age: 35`
- **Инструкцию schema**: `"description": "Current occupation"`
- **Связывает**: "Senior Developer" → `occupation: "Senior Developer"`

**Ответ LLM**:
```json
{
  "age": 35,
  "occupation": "Senior Developer",
  "location": "Mountain View"
}
```

### Шаг 7: Валидация и сохранение

📍 **Файл**: `graphiti_core/utils/maintenance/node_operations.py:383-389`

```python
    # Валидация через Pydantic (проверка типов)
    if entity_type is not None:
        entity_type(**llm_response)

    # Обновление атрибутов entity
    node.attributes.update(llm_response)
    # node.attributes = {'age': 35, 'occupation': 'Senior Developer', 'location': 'Mountain View'}

    return node
```

### Шаг 8: Сохранение в Neo4j

📍 **Файл**: `graphiti_core/nodes.py:452-483`

Атрибуты "разворачиваются" в свойства Neo4j узла:

```cypher
CREATE (n:Entity:Person {
  uuid: '...',
  name: 'John Doe',
  summary: 'A software engineer',
  age: 35,                      -- Из attributes
  occupation: 'Senior Developer', -- Из attributes
  location: 'Mountain View'      -- Из attributes
})
```

## Сводная таблица: Как используются части Pydantic модели

| Часть модели | Где используется | Цель | Этап |
|--------------|------------------|------|------|
| `class Person(BaseModel):` | node_operations.py | Имя типа → Neo4j label | 1 (классификация) |
| `"""Docstring"""` | extract_nodes промпт | Классификация: это Person или Resource? | 1 (классификация) |
| `age: Optional[int]` | model_json_schema() | JSON Schema: тип поля для валидации | 2 (атрибуты) |
| `Field(..., description="...")` | model_json_schema() | JSON Schema: инструкция для LLM | 2 (атрибуты) |

## Ключевая концепция: Schema-Guided Generation

Field `description` **НЕ парсится** кодом Graphiti напрямую. Вместо этого:

1. Pydantic автоматически включает descriptions в `model_json_schema()`
2. Вся JSON Schema передается LLM как часть промпта
3. LLM сам читает descriptions и понимает, какие значения извлекать
4. LLM возвращает JSON, соответствующий схеме

Это паттерн **"Schema-Guided Generation"** - современные LLM умеют:
- Читать JSON Schema
- Понимать descriptions как инструкции
- Генерировать валидный JSON согласно схеме

## Практические рекомендации

### 1. Пишите качественные descriptions

**Плохо**:
```python
age: Optional[int] = Field(None, description="Age")
```

**Хорошо**:
```python
age: Optional[int] = Field(None, description="Age of the person in years")
```

**Отлично**:
```python
age: Optional[int] = Field(
    None,
    description="Current age of the person in years. Extract from phrases like 'X years old', 'age X', 'born in YYYY' (calculate from current year)."
)
```

### 2. Различайте docstring и Field descriptions

**Docstring** - для классификации типа entity:
```python
class Project(BaseModel):
    """A time-bound initiative with specific goals and deliverables."""
```

**Field descriptions** - для извлечения конкретных значений:
```python
    deadline: Optional[datetime] = Field(
        None,
        description="Project deadline. Extract from phrases like 'due by', 'deadline', 'must finish by'."
    )
```

### 3. Используйте Optional для ненадежных данных

Если атрибут может отсутствовать в тексте - делайте его `Optional`:

```python
class Person(BaseModel):
    age: Optional[int] = None  # Может не быть в тексте
    occupation: Optional[str] = None  # Может не быть в тексте
```

### 4. Добавляйте примеры в descriptions

```python
birth_date: Optional[datetime] = Field(
    None,
    description="Date of birth. Examples: 'born on Jan 15, 1990', 'birthday: 1990-01-15', 'DOB: 01/15/1990'."
)
```

## Отладка

### Проверка JSON Schema

```python
from your_models import Person
import json

schema = Person.model_json_schema()
print(json.dumps(schema, indent=2))
```

### Проверка, что descriptions попали в schema

```python
schema = Person.model_json_schema()
for field_name, field_info in schema['properties'].items():
    print(f"{field_name}: {field_info.get('description', 'NO DESCRIPTION!')}")
```

### Логирование промптов

В `graphiti_core/llm_client/client.py` можно добавить логирование перед отправкой:

```python
logger.debug(f"Full prompt sent to LLM:\n{messages[-1].content}")
```

## См. также

- [backend/docs/ARCHITECTURE.md](ARCHITECTURE.md) - Общая архитектура
- [backend/app/models/para_entities.py](../app/models/para_entities.py) - Примеры PARA entity
- [backend/config/para_config.py](../config/para_config.py) - Конфигурация PARA типов
- [Pydantic JSON Schema](https://docs.pydantic.dev/latest/concepts/json_schema/) - Документация Pydantic
