Но все же response_model.model_json_schema()  получает на вход модель:
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

Но в ней нет ничего лишнего. откуду берутся поля properties?
Отличный вопрос! Давайте разберем, откуда берутся properties, required, title и другие метаполя.
🔍 Откуда берутся метаполя в JSON Schema?
model_json_schema() — это метод Pydantic, который автоматически генерирует JSON Schema из определения модели.
Bash
⎿
Analyze how Pydantic generates JSON schema
IN
cd /home/anton/pipgraph/backend && source .venv/bin/activate && python3 << 'EOF'
from pydantic import BaseModel, Field

# Ваша модель EdgeDuplicate
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

print("=" * 60)
print("Исходная модель EdgeDuplicate:")
print("=" * 60)
print(EdgeDuplicate.__name__)
print(EdgeDuplicate.model_fields)

print("\n" + "=" * 60)
print("Что генерирует model_json_schema():")
print("=" * 60)

import json
schema = EdgeDuplicate.model_json_schema()
print(json.dumps(schema, indent=2))

print("\n" + "=" * 60)
print("Откуда взялись поля:")
print("=" * 60)
print(f"'title': '{schema.get('title')}' ← Взято из имени класса EdgeDuplicate")
print(f"'type': '{schema.get('type')}' ← Pydantic знает, что это object (класс)")
print(f"'required': {schema.get('required')} ← Поля с '...' (обязательные)")
print(f"'properties': {{...}} ← Генерируется из model_fields")

print("\n" + "=" * 60)
print("Детальный разбор 'properties':")
print("=" * 60)

for field_name, field_info in EdgeDuplicate.model_fields.items():
    print(f"\nПоле: {field_name}")
    print(f"  Тип: {field_info.annotation}")
    print(f"  Описание: {field_info.description}")
    print(f"  Обязательное: {field_info.is_required()}")
    
    # Что попадает в properties
    prop = schema['properties'][field_name]
    print(f"  → В schema: {json.dumps(prop, ensure_ascii=False)}")
EOF
OUT
============================================================
Исходная модель EdgeDuplicate:
============================================================
EdgeDuplicate
{'duplicate_facts': FieldInfo(annotation=list[int], required=True, description='List of idx values of any duplicate facts. If no duplicate facts are found, default to empty list.'), 'contradicted_facts': FieldInfo(annotation=list[int], required=True, description='List of idx values of facts that should be invalidated. If no facts should be invalidated, the list should be empty.'), 'fact_type': FieldInfo(annotation=str, required=True, description='One of the provided fact types or DEFAULT')}

============================================================
Что генерирует model_json_schema():
============================================================
{
  "properties": {
    "duplicate_facts": {
      "description": "List of idx values of any duplicate facts. If no duplicate facts are found, default to empty list.",
      "items": {
        "type": "integer"
      },
      "title": "Duplicate Facts",
      "type": "array"
    },
    "contradicted_facts": {
      "description": "List of idx values of facts that should be invalidated. If no facts should be invalidated, the list should be empty.",
      "items": {
        "type": "integer"
      },
      "title": "Contradicted Facts",
      "type": "array"
    },
    "fact_type": {
      "description": "One of the provided fact types or DEFAULT",
      "title": "Fact Type",
      "type": "string"
    }
  },
  "required": [
    "duplicate_facts",
    "contradicted_facts",
    "fact_type"
  ],
  "title": "EdgeDuplicate",
  "type": "object"
}

============================================================
Откуда взялись поля:
============================================================
'title': 'EdgeDuplicate' ← Взято из имени класса EdgeDuplicate
'type': 'object' ← Pydantic знает, что это object (класс)
'required': ['duplicate_facts', 'contradicted_facts', 'fact_type'] ← Поля с '...' (обязательные)
'properties': {...} ← Генерируется из model_fields

============================================================
Детальный разбор 'properties':
============================================================

Поле: duplicate_facts
  Тип: list[int]
  Описание: List of idx values of any duplicate facts. If no duplicate facts are found, default to empty list.
  Обязательное: True
  → В schema: {"description": "List of idx values of any duplicate facts. If no duplicate facts are found, default to empty list.", "items": {"type": "integer"}, "title": "Duplicate Facts", "type": "array"}

Поле: contradicted_facts
  Тип: list[int]
  Описание: List of idx values of facts that should be invalidated. If no facts should be invalidated, the list should be empty.
  Обязательное: True
  → В schema: {"description": "List of idx values of facts that should be invalidated. If no facts should be invalidated, the list should be empty.", "items": {"type": "integer"}, "title": "Contradicted Facts", "type": "array"}

Поле: fact_type
  Тип: <class 'str'>
  Описание: One of the provided fact types or DEFAULT
  Обязательное: True
  → В schema: {"description": "One of the provided fact types or DEFAULT", "title": "Fact Type", "type": "string"}
Отлично! Теперь видно откуда что берется. Давайте посмотрим на трансформацию подробнее:
Bash
⎿
Explain JSON Schema generation step by step
IN
source .venv/bin/activate && python3 << 'EOF'
from pydantic import BaseModel, Field

class EdgeDuplicate(BaseModel):
    duplicate_facts: list[int] = Field(
        ...,
        description='List of idx values of any duplicate facts.'
    )

print("=" * 70)
print("ШАГ 1: Исходная Pydantic модель")
print("=" * 70)
print("""
class EdgeDuplicate(BaseModel):
    duplicate_facts: list[int] = Field(..., description='...')
                     ↓
              Python класс
""")

print("=" * 70)
print("ШАГ 2: Pydantic анализирует класс")
print("=" * 70)
print(f"""
Имя класса: {EdgeDuplicate.__name__}
           ↓
       title: 'EdgeDuplicate'  ← Автоматически!
       
Базовый класс: BaseModel
              ↓
          type: 'object'  ← Все BaseModel это objects в JSON Schema
          
Поле с '...': duplicate_facts (обязательное)
             ↓
         required: ['duplicate_facts']  ← Все обязательные поля
""")

print("=" * 70)
print("ШАГ 3: Для каждого поля генерируется описание")
print("=" * 70)
print("""
duplicate_facts: list[int]
                ↓
    - Python тип list[int] → JSON Schema type: 'array', items: {type: 'integer'}
    
Field(description='...')
                ↓
    - description копируется в schema
    
Имя поля 'duplicate_facts'
                ↓
    - title: 'Duplicate Facts'  ← Автоматически из snake_case в Title Case!
""")

print("=" * 70)
print("ШАГ 4: Все собирается в JSON Schema")
print("=" * 70)
import json
schema = EdgeDuplicate.model_json_schema()
print(json.dumps(schema, indent=2))

print("\n" + "=" * 70)
print("КЛЮЧЕВОЙ МОМЕНТ:")
print("=" * 70)
print("""
Метаполя (properties, required, title, type) НЕ БЫЛИ в вашей модели!
Они АВТОМАТИЧЕСКИ ГЕНЕРИРУЮТСЯ Pydantic по стандарту JSON Schema.

Это не баг, это фича - JSON Schema стандарт требует эти поля.
Проблема в том, что Qwen интерпретирует их буквально.
""")

print("=" * 70)
print("Стандарт JSON Schema:")
print("=" * 70)
print("""
Правильный JSON Schema ДОЛЖЕН иметь:
{
  "type": "object",              ← Тип схемы
  "properties": {                ← Описание свойств
    "field_name": {...}
  },
  "required": ["field_name"],    ← Обязательные поля
  "title": "ModelName"           ← Название схемы
}

Это официальный формат: https://json-schema.org/
""")
EOF
OUT
======================================================================
ШАГ 1: Исходная Pydantic модель
======================================================================
