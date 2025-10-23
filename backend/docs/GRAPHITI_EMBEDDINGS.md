# Graphiti Embeddings - Механизм создания векторных представлений

> **Источник**: Анализ кодовой базы Graphiti Core и PipGraph
> **Версия анализа**: 2025-10-21

## Обзор

Graphiti Core использует **векторные представления (embeddings)** для семантического поиска и сопоставления сущностей и отношений в графовой базе данных. Embeddings создаются с помощью специализированных языковых моделей и хранятся как свойства узлов и рёбер в Neo4j.

**Ключевые типы embeddings**:
1. **Entity name embeddings** - векторы имён сущностей (`EntityNode.name_embedding`)
2. **Relationship fact embeddings** - векторы описаний отношений (`EntityEdge.fact_embedding`)

**Назначение**:
- Семантический поиск похожих сущностей
- Автоматическое связывание дубликатов
- Поиск релевантных отношений по смыслу
- Ранжирование результатов поиска по семантической близости

---

## Архитектура системы embeddings

### Компоненты

```
┌─────────────────────────────────────────────────┐
│          Graphiti Client                        │
│  ┌───────────────────────────────────────────┐  │
│  │   LLM Client (OpenRouter/Cloud.ru)        │  │
│  │   - Извлечение сущностей                  │  │
│  │   - Генерация описаний                    │  │
│  └───────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────┐  │
│  │   Embedder (OpenAIEmbedder)               │  │
│  │   - Модель: Qwen/Qwen3-Embedding-0.6B     │  │
│  │   - API: Cloud.ru (OpenAI-совместимый)    │  │
│  │   - Вход: текстовые строки                │  │
│  │   - Выход: векторы float[]                │  │
│  └───────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────┐  │
│  │   Neo4j Driver                            │  │
│  │   - Сохранение векторов как свойств       │  │
│  │   - Индексация для быстрого поиска        │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### Инициализация embedder

**Локация**: [backend/app/services/llm_graphiti_client.py:48-54](backend/app/services/llm_graphiti_client.py#L48-L54)

```python
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig

embedder = OpenAIEmbedder(
    config=OpenAIEmbedderConfig(
        api_key=settings.CLOUDRU_API_KEY,
        embedding_model=settings.CLOUDRU_EMBEDDING_MODEL,
        base_url=settings.CLOUDRU_BASE_URL,
    )
)

graphiti = Graphiti(
    neo4j_uri=settings.NEO4J_URI,
    neo4j_user=settings.NEO4J_USER,
    neo4j_password=settings.NEO4J_PASSWORD,
    llm_client=llm_client,
    embedder=embedder  # Передаётся в конструктор
)
```

**Конфигурация по умолчанию** ([backend/config/settings.py:15](backend/config/settings.py#L15)):
```python
# Cloud.ru LLM Configuration
CLOUDRU_EMBEDDING_MODEL: str = "Qwen/Qwen3-Embedding-0.6B"
CLOUDRU_BASE_URL: str = "https://api.cloudru.com/v1"
```

**Альтернативные модели** ([backend/config/settings.py:30](backend/config/settings.py#L30)):
```python
# OpenRouter LLM Configuration
OPENROUTER_EMBEDDING_MODEL: str = "openai/text-embedding-3-small"
```

---

## Entity Name Embeddings

### Определение поля

**Класс**: `EntityNode` ([graphiti_core/nodes.py](graphiti_core/nodes.py))

```python
class EntityNode(Node):
    # Inherited from Node base class
    uuid: str                                    # auto-generated UUID
    name: str                                    # entity name
    group_id: str                                # partition key
    labels: list[str]                           # entity type labels
    created_at: datetime                        # creation timestamp

    # EntityNode specific
    name_embedding: list[float] | None = Field(
        default=None,
        description='embedding of the name'
    )
    summary: str = Field(
        description='regional summary of surrounding edges',
        default_factory=str
    )
    attributes: dict[str, Any] = Field(
        default={},
        description='Additional attributes of the node. Dependent on node labels'
    )
```

### Источник данных для embedding

**Входные данные**: `EntityNode.name` (строка)

**Примеры**:
- `"Антон Новиков"` → вектор [0.123, -0.456, 0.789, ...]
- `"Python"` → вектор [0.234, -0.567, 0.890, ...]
- `"Neo4j Database"` → вектор [0.345, -0.678, 0.901, ...]

**Процесс**:
1. LLM извлекает сущность из текста эпизода → получает `name = "Python"`
2. При сохранении узла embedder получает строку `"Python"`
3. Embedder вызывает API модели embeddings → получает вектор размерности N
4. Вектор сохраняется в поле `name_embedding`

### Назначение

**1. Semantic Entity Search**
```cypher
// Найти сущности, семантически похожие на "программирование"
MATCH (n:Entity)
WHERE n.name_embedding IS NOT NULL
WITH n, vector.similarity(n.name_embedding, $query_embedding) AS score
WHERE score > 0.8
RETURN n.name, score
ORDER BY score DESC
```

**2. Duplicate Detection**
```python
# Автоматическое обнаружение дубликатов по семантической близости
# Например: "Антон" и "Anton Novikov" могут быть одной сущностью
similarity = cosine_similarity(entity1.name_embedding, entity2.name_embedding)
if similarity > THRESHOLD:
    merge_entities(entity1, entity2)
```

**3. Entity Resolution**
- Сопоставление извлечённых сущностей с существующими в графе
- Используется в методе `resolve_extracted_nodes()` ([backend/app/services/pipgraph_manager.py:237-243](backend/app/services/pipgraph_manager.py#L237-L243))

---

## Relationship Fact Embeddings

### Определение поля

**Класс**: `EntityEdge` ([graphiti_core/edges.py](graphiti_core/edges.py))

```python
class EntityEdge(Edge):
    # From Edge base class
    uuid: str
    group_id: str
    source_node_uuid: str                # UUID источника
    target_node_uuid: str                # UUID цели
    created_at: datetime

    # EntityEdge specific
    name: str                              # Relationship name (e.g., "WORKS_AT")
    fact: str                              # Natural language fact
    fact_embedding: list[float] | None = Field(
        default=None,
        description='embedding'
    )
    episodes: list[str]                   # Episode UUIDs that mention this edge
    expired_at: datetime | None            # When edge became invalid
    valid_at: datetime | None              # When edge became true
    invalid_at: datetime | None            # When edge stopped being true
    attributes: dict[str, Any]            # FREE-FORM custom fields
```

### Источник данных для embedding

**Входные данные**: `EntityEdge.fact` (строка - естественноязыковое описание отношения)

**Примеры**:
- `"Антон работает Python-разработчиком в компании X"` → вектор [...]
- `"Neo4j is a graph database management system"` → вектор [...]
- `"Graphiti использует embeddings для семантического поиска"` → вектор [...]

**Формат fact**:
```python
# Пример из извлечения отношений LLM
edge = EntityEdge(
    name="WORKS_AT",
    fact="Антон Новиков работает Python-разработчиком в компании TechCorp с 2020 года",
    source_node_uuid="uuid_anton",
    target_node_uuid="uuid_techcorp"
)
```

### Назначение

**1. Semantic Relationship Search**
```cypher
// Найти отношения, связанные с темой "занятость"
MATCH ()-[r:RELATES_TO]->()
WHERE r.fact_embedding IS NOT NULL
WITH r, vector.similarity(r.fact_embedding, $query_embedding) AS score
WHERE score > 0.75
RETURN r.fact, score
ORDER BY score DESC
```

**2. Relationship Deduplication**
```python
# Обнаружение дубликатов отношений с разной формулировкой
# "Антон работает в X" vs "Anton is employed by X"
similarity = cosine_similarity(edge1.fact_embedding, edge2.fact_embedding)
if similarity > 0.9 and same_entities(edge1, edge2):
    merge_edges(edge1, edge2)
```

**3. Contextual Search**
```python
# Поиск фактов, релевантных запросу пользователя
query = "Кто работает разработчиком?"
query_embedding = embedder.create([query])[0]

# Поиск ближайших фактов по семантике
results = search_edges_by_embedding(query_embedding, top_k=10)
```

---

## Процесс генерации embeddings

### Полный pipeline обработки заметки

**Локация**: [backend/app/services/pipgraph_manager.py:113-333](backend/app/services/pipgraph_manager.py#L113-L333)

```python
async def process_note(self, note: Note) -> ProcessingResult:
    """
    Полный цикл обработки заметки с генерацией embeddings
    """

    # ЭТАП 1: СОЗДАНИЕ ЭПИЗОДА
    # Локация: строка 188-210
    episode = EpisodicNode(
        name=note.title,
        group_id=note.vault_name,
        source=EpisodeType.text,
        source_description='Obsidian note',
        content=note.content,
        valid_at=note.created_at,
    )

    # ЭТАП 2: ИЗВЛЕЧЕНИЕ СУЩНОСТЕЙ (LLM)
    # Локация: строки 226-228
    extracted_nodes: list[EntityNode] = await extract_nodes(
        self.driver,
        [episode],
        self.llm_client,
    )
    # Результат: список EntityNode с заполненными name, но БЕЗ embeddings

    # ЭТАП 3: РЕЗОЛЮЦИЯ СУЩНОСТЕЙ
    # Локация: строки 237-243
    hydrated_nodes = await resolve_extracted_nodes(
        self.driver,
        [episode],
        extracted_nodes,
        self.embedder,  # Используется для поиска похожих
    )
    # Результат: сопоставление с существующими сущностями

    # ЭТАП 4: ИЗВЛЕЧЕНИЕ ОТНОШЕНИЙ (LLM)
    # Локация: строки 244-252
    entity_edges: list[EntityEdge] = await extract_edges(
        self.driver,
        [episode],
        hydrated_nodes,
        self.llm_client,
    )
    # Результат: список EntityEdge с заполненными fact, но БЕЗ embeddings

    # ЭТАП 5: ИЗВЛЕЧЕНИЕ АТРИБУТОВ
    # Локация: строки 282-284
    hydrated_nodes = await extract_node_attributes(
        self.driver,
        self.llm_client,
        hydrated_nodes,
        self.entity_types,
    )

    # ЭТАП 6: СОХРАНЕНИЕ В БД + ГЕНЕРАЦИЯ EMBEDDINGS
    # Локация: строки 302-305
    # ⚡ ЗДЕСЬ ПРОИСХОДИТ СОЗДАНИЕ EMBEDDINGS ⚡
    await add_nodes_and_edges_bulk(
        self.driver,
        [episode],
        episodic_edges,
        hydrated_nodes,
        entity_edges,
        self.embedder  # Передаётся для генерации embeddings
    )

    # ВНУТРИ add_nodes_and_edges_bulk:
    # 1. Для каждого EntityNode:
    #    - Вызов: embedder.create([node.name])
    #    - Результат: node.name_embedding = [0.123, ...]
    #
    # 2. Для каждого EntityEdge:
    #    - Вызов: embedder.create([edge.fact])
    #    - Результат: edge.fact_embedding = [0.456, ...]
    #
    # 3. Сохранение в Neo4j с embeddings

    return ProcessingResult(...)
```

### Детальная схема генерации

```
Входные данные
├─ EntityNode.name: "Python"
└─ EntityEdge.fact: "Python is a programming language"

        ↓ [add_nodes_and_edges_bulk]

┌─────────────────────────────────────┐
│   OpenAIEmbedder.create()           │
│                                     │
│   Input:  ["Python"]                │
│   ↓                                 │
│   POST https://api.cloudru.com/v1   │
│   {                                 │
│     "model": "Qwen/Qwen3-...",      │
│     "input": ["Python"]             │
│   }                                 │
│   ↓                                 │
│   Response: {                       │
│     "data": [{                      │
│       "embedding": [0.123, ...]     │
│     }]                              │
│   }                                 │
│   ↓                                 │
│   Return: [[0.123, -0.456, ...]]    │
└─────────────────────────────────────┘

        ↓

EntityNode.name_embedding = [0.123, -0.456, ...]
EntityEdge.fact_embedding = [0.234, -0.567, ...]

        ↓ [Neo4j MERGE/CREATE]

┌─────────────────────────────────────┐
│   Neo4j Property Storage            │
│                                     │
│   (:Entity {                        │
│     name: "Python",                 │
│     name_embedding: [0.123, ...]    │
│   })                                │
│                                     │
│   ()-[:RELATES_TO {                 │
│     fact: "Python is...",           │
│     fact_embedding: [0.234, ...]    │
│   }]->()                            │
└─────────────────────────────────────┘
```

---

## Конфигурация моделей embeddings

### Поддерживаемые модели

**1. Qwen3-Embedding (по умолчанию)**

```python
# backend/config/settings.py
CLOUDRU_EMBEDDING_MODEL: str = "Qwen/Qwen3-Embedding-0.6B"
```

**Характеристики**:
- Провайдер: Cloud.ru
- Размерность: зависит от модели (обычно 768 или 1024)
- Язык: мультиязычная (поддержка русского)
- Стоимость: определяется Cloud.ru pricing

**2. OpenAI text-embedding-3-small**

```python
# Альтернативная конфигурация
OPENROUTER_EMBEDDING_MODEL: str = "openai/text-embedding-3-small"
```

**Характеристики**:
- Провайдер: OpenRouter → OpenAI
- Размерность: 1536
- Язык: мультиязычная
- Стоимость: ~$0.00002 / 1K tokens

### Тестирование embedding модели

**Локация**: [backend/tests/integration/test_openai_generic_config.py:78-98](backend/tests/integration/test_openai_generic_config.py#L78-L98)

```python
import pytest
from openai import AsyncOpenAI
from backend.config.settings import settings

@pytest.mark.asyncio
@pytest.mark.integration
async def test_embedding_model():
    """Test embedding model connection through Cloud.ru provider."""
    client = AsyncOpenAI(
        api_key=settings.CLOUDRU_API_KEY,
        base_url=settings.CLOUDRU_BASE_URL
    )

    response = await client.embeddings.create(
        model=settings.CLOUDRU_EMBEDDING_MODEL,
        input=["Как написать хороший код?"]
    )

    # Проверка формата ответа
    assert response.data
    assert len(response.data) > 0
    assert response.data[0].embedding

    # Проверка размерности
    embedding_dim = len(response.data[0].embedding)
    print(f"Embedding dimension: {embedding_dim}")
    assert embedding_dim > 0

    # Проверка типа данных
    assert all(isinstance(x, float) for x in response.data[0].embedding)
```

**Запуск теста**:
```bash
cd backend/
pytest tests/integration/test_openai_generic_config.py::test_embedding_model -v
```

### Смена модели embeddings

```python
# backend/.env
# Вариант 1: Cloud.ru (по умолчанию)
CLOUDRU_API_KEY=sk-or-v1-...
CLOUDRU_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B
CLOUDRU_BASE_URL=https://api.cloudru.com/v1

# Вариант 2: OpenRouter → OpenAI
CLOUDRU_API_KEY=sk-or-v1-...
CLOUDRU_EMBEDDING_MODEL=openai/text-embedding-3-small
CLOUDRU_BASE_URL=https://openrouter.ai/api/v1

# Вариант 3: Прямой OpenAI
CLOUDRU_API_KEY=sk-...
CLOUDRU_EMBEDDING_MODEL=text-embedding-3-small
CLOUDRU_BASE_URL=https://api.openai.com/v1
```

---

## Хранение embeddings в Neo4j

### Формат хранения

**Properties** (не отдельные узлы):
```cypher
// Entity node с embedding
CREATE (n:Entity {
    uuid: "uuid-123",
    name: "Python",
    name_embedding: [0.123, -0.456, 0.789, ...],  // Массив float
    summary: "Programming language...",
    group_id: "default"
})

// Relationship с embedding
CREATE (a)-[:RELATES_TO {
    uuid: "uuid-456",
    fact: "Python is used for data science",
    fact_embedding: [0.234, -0.567, 0.890, ...],  // Массив float
    name: "USED_FOR"
}]->(b)
```

### Индексация для поиска

**Vector Index** (Neo4j 5.11+):
```cypher
// Создание векторного индекса для Entity nodes
CREATE VECTOR INDEX entity_name_embedding
FOR (n:Entity)
ON (n.name_embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 768,           // Размерность модели
    `vector.similarity_function`: 'cosine'
  }
}

// Создание векторного индекса для отношений
CREATE VECTOR INDEX edge_fact_embedding
FOR ()-[r:RELATES_TO]-()
ON (r.fact_embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 768,
    `vector.similarity_function`: 'cosine'
  }
}
```

### Semantic Search Query

**Поиск похожих сущностей**:
```cypher
// Найти top-10 сущностей, семантически близких к запросу
CALL db.index.vector.queryNodes(
    'entity_name_embedding',
    10,                           // top_k
    $query_embedding              // Embedding запроса
) YIELD node, score

RETURN node.name, node.summary, score
ORDER BY score DESC
```

**Поиск похожих фактов**:
```cypher
// Найти top-5 отношений по семантике
CALL db.index.vector.queryRelationships(
    'edge_fact_embedding',
    5,
    $query_embedding
) YIELD relationship, score

MATCH (source)-[relationship]->(target)
RETURN
    source.name,
    relationship.fact,
    target.name,
    score
ORDER BY score DESC
```

---

## Интеграция с PipGraph

### Использование в PipGraphManager

**Конфигурация** ([backend/app/services/llm_graphiti_client.py:23-67](backend/app/services/llm_graphiti_client.py#L23-L67)):

```python
def create_graphiti_client(
    settings: Settings,
    use_openrouter: bool = False
) -> Graphiti:
    """
    Создаёт Graphiti клиент с настроенным embedder
    """

    # Выбор провайдера LLM
    if use_openrouter:
        llm_client = OpenAIClient(
            api_key=settings.OPENROUTER_API_KEY,
            model=settings.OPENROUTER_CHAT_MODEL,
            base_url=settings.OPENROUTER_BASE_URL,
        )

        embedder = OpenAIEmbedder(
            config=OpenAIEmbedderConfig(
                api_key=settings.OPENROUTER_API_KEY,
                embedding_model=settings.OPENROUTER_EMBEDDING_MODEL,
                base_url=settings.OPENROUTER_BASE_URL,
            )
        )
    else:
        llm_client = OpenAIClient(
            api_key=settings.CLOUDRU_API_KEY,
            model=settings.CLOUDRU_CHAT_MODEL,
            base_url=settings.CLOUDRU_BASE_URL,
        )

        embedder = OpenAIEmbedder(
            config=OpenAIEmbedderConfig(
                api_key=settings.CLOUDRU_API_KEY,
                embedding_model=settings.CLOUDRU_EMBEDDING_MODEL,
                base_url=settings.CLOUDRU_BASE_URL,
            )
        )

    # Создание Graphiti с embedder
    return Graphiti(
        neo4j_uri=settings.NEO4J_URI,
        neo4j_user=settings.NEO4J_USER,
        neo4j_password=settings.NEO4J_PASSWORD,
        llm_client=llm_client,
        embedder=embedder  # ⚡ Ключевой параметр
    )
```

### Пример использования

**Обработка заметки с автоматической генерацией embeddings**:

```python
from backend.app.services.pipgraph_manager import PipGraphManager
from backend.app.schemas.note import Note

# Инициализация
manager = PipGraphManager(
    graphiti=graphiti_client,  # С настроенным embedder
    neo4j_driver=driver
)

# Обработка заметки
note = Note(
    title="Python Development",
    content="Python is a high-level programming language...",
    vault_name="tech-notes",
    created_at=datetime.now()
)

result = await manager.process_note(note)

# Результат: все сущности и отношения имеют embeddings
for entity in result.entities:
    assert entity.name_embedding is not None
    print(f"Entity: {entity.name}, embedding dim: {len(entity.name_embedding)}")

for edge in result.edges:
    assert edge.fact_embedding is not None
    print(f"Fact: {edge.fact}, embedding dim: {len(edge.fact_embedding)}")
```

---

## Производительность и стоимость

### Метрики производительности

**Время генерации embedding**:
- Одиночный запрос: ~100-300ms
- Батч 10 сущностей: ~500-800ms
- Батч 50 сущностей: ~1-2s

**Рекомендации по оптимизации**:

1. **Batch Processing**:
```python
# Вместо:
for node in nodes:
    node.name_embedding = await embedder.create([node.name])

# Использовать:
names = [node.name for node in nodes]
embeddings = await embedder.create(names)  # Один запрос
for node, emb in zip(nodes, embeddings):
    node.name_embedding = emb
```

2. **Кэширование**:
```python
# Кэш для избежания повторных вызовов
embedding_cache = {}

def get_embedding_cached(text: str):
    if text not in embedding_cache:
        embedding_cache[text] = embedder.create([text])[0]
    return embedding_cache[text]
```

3. **Ленивая генерация**:
```python
# Генерировать embeddings только для новых сущностей
if node.name_embedding is None:
    node.name_embedding = await embedder.create([node.name])
```

### Стоимость API вызовов

**Qwen3-Embedding (Cloud.ru)**:
- Ценообразование: зависит от Cloud.ru
- Примерная стоимость: ~$0.00001-0.00005 / 1K tokens

**OpenAI text-embedding-3-small**:
- Ценообразование: $0.00002 / 1K tokens
- Пример: 1000 сущностей (средняя длина 10 tokens) = $0.0002

**Оценка для PipGraph**:
```
Средний Obsidian vault: 1000 заметок
Средняя заметка: 5 сущностей + 10 отношений
Итого: 5000 entities + 10000 edges = 15000 embeddings

При средней длине текста 15 tokens:
15000 * 15 = 225K tokens
225K * $0.00002 = $0.0045 (менее цента!)
```

---

## Ограничения и известные проблемы

### 1. Размерность embeddings

**Проблема**: Разные модели имеют разную размерность
- Qwen3-Embedding: 768/1024 (зависит от версии)
- OpenAI text-embedding-3-small: 1536
- OpenAI text-embedding-3-large: 3072

**Следствие**: При смене модели необходимо:
1. Пересоздать векторные индексы
2. Регенерировать все embeddings

**Решение**:
```python
# Проверка размерности перед созданием индекса
sample_embedding = await embedder.create(["test"])
dimension = len(sample_embedding[0])

# Создание индекса с правильной размерностью
await create_vector_index(dimension=dimension)
```

### 2. Языковая зависимость

**Проблема**: Качество embeddings зависит от языка модели

**Qwen3**: Хорошо работает с русским и английским
**OpenAI**: Оптимизирована для английского

**Рекомендация для PipGraph**:
- Для русскоязычных заметок: Qwen3-Embedding
- Для англоязычных заметок: OpenAI models
- Для мультиязычных: тестировать обе модели

### 3. NULL embeddings

**Проблема**: При ошибке API embedding может быть `None`

**Обработка**:
```python
# В запросах Neo4j
MATCH (n:Entity)
WHERE n.name_embedding IS NOT NULL  // Фильтр
WITH n, vector.similarity(...)
```

**Retry логика**:
```python
async def create_embedding_safe(text: str, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await embedder.create([text])
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(f"Failed to create embedding: {e}")
                return None
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
```

### 4. Drift при обновлении моделей

**Проблема**: Провайдер может обновить модель → изменятся embeddings

**Индикаторы проблемы**:
- Снижение качества semantic search
- Изменение similarity scores
- Несопоставимые embeddings старых и новых сущностей

**Решение**:
```python
# Версионирование embeddings
class EntityNode(Node):
    name_embedding: list[float] | None
    embedding_model_version: str = "qwen3-0.6b-v1"  # Трекинг версии

# При смене модели - пересоздать все embeddings
await regenerate_all_embeddings(new_model="qwen3-0.6b-v2")
```

---

## Связанные файлы и документация

### Ключевые файлы кода

**PipGraph**:
- [backend/app/services/llm_graphiti_client.py](backend/app/services/llm_graphiti_client.py) - Инициализация embedder
- [backend/app/services/pipgraph_manager.py](backend/app/services/pipgraph_manager.py) - Процесс обработки заметок
- [backend/config/settings.py](backend/config/settings.py) - Конфигурация моделей

**Graphiti Core**:
- `graphiti_core/nodes.py` - Определение EntityNode с name_embedding
- `graphiti_core/edges.py` - Определение EntityEdge с fact_embedding
- `graphiti_core/embedder/openai.py` - Реализация OpenAIEmbedder

**Тесты**:
- [backend/tests/integration/test_openai_generic_config.py](backend/tests/integration/test_openai_generic_config.py) - Тесты embedding моделей

### Связанная документация

- [GRAPHITI_CORE_FIELD_ANALYSIS.md](GRAPHITI_CORE_FIELD_ANALYSIS.md) - Анализ полей Graphiti
- [GRAPHITI_QUICK_REFERENCE.md](GRAPHITI_QUICK_REFERENCE.md) - Быстрый справочник
- [GRAPHITI_COMMUNITIES.md](GRAPHITI_COMMUNITIES.md) - Community detection (также использует embeddings)

---

## Примеры использования

### 1. Поиск сущностей по семантике

```python
from backend.app.services.llm_graphiti_client import create_graphiti_client
from backend.config.settings import settings

# Инициализация
graphiti = create_graphiti_client(settings)

# Создание embedding для запроса
query = "программирование на Python"
query_embedding = await graphiti.embedder.create([query])

# Поиск в Neo4j
query_cypher = """
CALL db.index.vector.queryNodes(
    'entity_name_embedding',
    10,
    $query_embedding
) YIELD node, score
WHERE score > 0.7
RETURN node.name, node.summary, score
ORDER BY score DESC
"""

results = await graphiti.driver.execute_query(
    query_cypher,
    query_embedding=query_embedding[0]
)

for record in results:
    print(f"{record['node.name']}: {record['score']:.3f}")
```

### 2. Обнаружение дубликатов

```python
from backend.app.crud.entities import get_all_entities

# Получить все сущности
entities = await get_all_entities(driver, group_id="tech-notes")

# Поиск дубликатов по embeddings
duplicates = []
for i, entity1 in enumerate(entities):
    for entity2 in entities[i+1:]:
        similarity = cosine_similarity(
            entity1.name_embedding,
            entity2.name_embedding
        )
        if similarity > 0.95:  # Очень высокая схожесть
            duplicates.append((entity1, entity2, similarity))

# Отчёт о дубликатах
for e1, e2, score in duplicates:
    print(f"Possible duplicate: {e1.name} ↔ {e2.name} (score: {score:.3f})")
```

### 3. Semantic Relationship Discovery

```python
# Найти все отношения, связанные с "работой"
query = "employment relationship"
query_embedding = await graphiti.embedder.create([query])

query_cypher = """
CALL db.index.vector.queryRelationships(
    'edge_fact_embedding',
    20,
    $query_embedding
) YIELD relationship, score
MATCH (source)-[relationship]->(target)
RETURN
    source.name AS from_entity,
    relationship.fact AS fact,
    target.name AS to_entity,
    score
ORDER BY score DESC
"""

results = await graphiti.driver.execute_query(
    query_cypher,
    query_embedding=query_embedding[0]
)

for record in results:
    print(f"{record['from_entity']} → {record['to_entity']}")
    print(f"  Fact: {record['fact']}")
    print(f"  Score: {record['score']:.3f}\n")
```

---

## Заключение

Система embeddings в Graphiti обеспечивает:

1. **Семантический поиск** - находить сущности и отношения по смыслу, а не по точному совпадению текста
2. **Автоматическое связывание** - обнаруживать дубликаты и схожие сущности
3. **Интеллектуальную индексацию** - организовывать знания на основе семантической близости

**Ключевые принципы**:
- Embeddings генерируются **автоматически** при сохранении сущностей и отношений
- Источник данных для embeddings - **простые строки** (`name` для сущностей, `fact` для отношений)
- Используется **OpenAI-совместимый API** (Cloud.ru/OpenRouter)
- Embeddings хранятся как **свойства Neo4j**, доступны для векторного поиска

**Рекомендации для PipGraph**:
- Использовать **Qwen3-Embedding** для русскоязычных заметок
- Настроить **векторные индексы** в Neo4j для оптимального поиска
- Реализовать **кэширование** для часто используемых embeddings
- Мониторить **стоимость API** при масштабировании

Система embeddings является критически важным компонентом Graphiti, обеспечивающим интеллектуальную обработку знаний в графовой базе данных.
