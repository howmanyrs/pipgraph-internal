# Checknote Implementation Plan

## Анализ проблемы

### Проблема с текущим дизайном

В документе [sqlite_metadata_storage.md](./sqlite_metadata_storage.md) предлагается проверять дубликаты через:

```python
# 3. If duplicate found
if result['status'] == 'duplicate'
```

**Однако** структура результата `AddEpisodeResults` из graphiti_core не содержит поле `status`:

```python
# graphiti_core/nodes.py
class AddEpisodeResults(BaseModel):
    episode: EpisodicNode
    episodic_edges: list[EpisodicEdge]
    nodes: list[EntityNode]
    edges: list[EntityEdge]
    communities: list[CommunityNode]
    community_edges: list[CommunityEdge]
```

### Корневая причина

Graphiti всегда создает новый эпизод и извлекает сущности через LLM. Метод `add_episode()` (и наша обертка `PipGraphManager.process_note()`) **не проверяет дубликаты** - это ответственность приложения.

**Вывод**: Проверка на дубликаты должна происходить **ДО** вызова `process_note()`, а не после.

---

## Решение: Pre-flight Checknote

### Архитектурный подход

```
┌─────────────────────────────────────────┐
│ API Layer (WebSocket/REST)              │
│ app/api/notes.py                        │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ Service Layer                            │
│ app/services/note_processor.py          │  ← ЗДЕСЬ добавляется проверка дубликатов
│                                          │
│ 1. Вычислить content_hash                │
│ 2. Проверить SQLite metadata DB          │
│ 3. if duplicate:                         │
│      return existing episode_uuid        │
│    else:                                 │
│      call PipGraphManager.process_note() │
│      save metadata to SQLite             │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ PipGraph Manager (без изменений)        │
│ app/services/pipgraph_manager.py        │
│                                          │
│ - Пошаговая обработка заметки           │
│ - Точки интервенции                     │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ Graphiti Core (библиотека)              │
│ - extract_nodes()                       │
│ - resolve_extracted_nodes()             │
│ - extract_edges()                       │
│ - add_nodes_and_edges_bulk()            │
└─────────────────────────────────────────┘
```

---

## Детальная реализация

### 1. SQLite Metadata Database

#### Схема таблицы

```sql
CREATE TABLE episode_metadata (
    episode_uuid TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    group_id TEXT NOT NULL,
    file_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processing_status TEXT DEFAULT 'completed', -- 'completed', 'failed', 'orphaned'
    error_message TEXT
);

-- Быстрый поиск дубликатов
CREATE INDEX idx_content_hash_group ON episode_metadata(content_hash, group_id);

-- Поиск по пути файла для обновлений
CREATE INDEX idx_file_path ON episode_metadata(file_path);
```

#### Жизненный цикл записи

1. **Создание**: После успешного `process_note()` сохраняем хеш
2. **Проверка**: Перед обработкой ищем по хешу
3. **Очистка**: Периодически удаляем orphaned записи (episode удален из Neo4j)

---

### 2. Модуль проверки заметок

#### Новый файл: `app/services/checknote.py`

```python
"""
Checknote service using SQLite for content hash tracking.

Архитектура:
- SQLite хранит маппинг content_hash → episode_uuid
- Проверка дубликатов происходит ДО вызова LLM
- Независим от graphiti_core (работает на уровне приложения)
"""

import hashlib
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ChecknoteResult(BaseModel):
    """Результат проверки на дубликаты"""
    is_duplicate: bool
    existing_episode_uuid: Optional[str] = None
    content_hash: str


class ChecknoteService:
    """Сервис для отслеживания дубликатов заметок через SQLite"""

    def __init__(self, db_path: str = "data/episode_metadata.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Инициализация SQLite базы с индексами"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episode_metadata (
                    episode_uuid TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    file_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processing_status TEXT DEFAULT 'completed'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_content_hash_group
                ON episode_metadata(content_hash, group_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_file_path
                ON episode_metadata(file_path)
            """)

    @staticmethod
    def compute_hash(content: str) -> str:
        """Вычислить SHA-256 хеш контента"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def check_duplicate(
        self,
        content: str,
        group_id: str
    ) -> ChecknoteResult:
        """
        Проверить, существует ли эпизод с таким же контентом.

        Args:
            content: Текст заметки для проверки
            group_id: ID группы графа (для изоляции)

        Returns:
            ChecknoteResult с флагом дубликата и UUID существующего эпизода
        """
        content_hash = self.compute_hash(content)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT episode_uuid
                FROM episode_metadata
                WHERE content_hash = ? AND group_id = ? AND processing_status = 'completed'
                LIMIT 1
                """,
                (content_hash, group_id)
            )
            result = cursor.fetchone()

        if result:
            return ChecknoteResult(
                is_duplicate=True,
                existing_episode_uuid=result[0],
                content_hash=content_hash
            )
        else:
            return ChecknoteResult(
                is_duplicate=False,
                content_hash=content_hash
            )

    def save_metadata(
        self,
        episode_uuid: str,
        content_hash: str,
        group_id: str,
        file_path: Optional[str] = None,
        processing_status: str = "completed"
    ):
        """
        Сохранить метаданные эпизода после успешной обработки.

        Args:
            episode_uuid: UUID созданного эпизода из Neo4j
            content_hash: Хеш контента (из check_duplicate)
            group_id: ID группы графа
            file_path: Путь к файлу заметки (опционально)
            processing_status: Статус обработки
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO episode_metadata
                (episode_uuid, content_hash, group_id, file_path, processing_status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (episode_uuid, content_hash, group_id, file_path, processing_status)
            )

    def cleanup_orphaned(self, valid_uuids: list[str]):
        """
        Удалить записи для эпизодов, которых больше нет в Neo4j.

        Args:
            valid_uuids: Список UUID эпизодов, существующих в Neo4j
        """
        placeholders = ','.join('?' * len(valid_uuids))
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"DELETE FROM episode_metadata WHERE episode_uuid NOT IN ({placeholders})",
                valid_uuids
            )
```

---

### 3. Интеграция в `note_processor.py`

#### Обновленный файл: `app/services/note_processor.py`

```python
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel

from app.models.note import NotePayload
from app.models.graph import GraphData, Node
from graphiti_core.nodes import EpisodeType
from app.services.llm_graphiti_client import get_graphiti
from app.services.pipgraph_manager import PipGraphManager, AddEpisodeResults
from app.services.checknote import ChecknoteService, ChecknoteResult


class NoteProcessingResult(BaseModel):
    """
    Обертка над AddEpisodeResults с информацией о проверке дубликатов.

    Этот класс расширяет результат обработки заметки, добавляя:
    - Флаг дубликата
    - UUID эпизода (новый или существующий)
    - Полные результаты обработки (если это новая заметка)
    """
    status: str  # "created" | "duplicate"
    episode_uuid: str
    content_hash: str
    is_duplicate: bool
    processing_details: Optional[AddEpisodeResults] = None  # None для дубликатов


# Глобальный экземпляр сервиса checknote
_checknote_service = ChecknoteService()


async def process_and_store_note(note: NotePayload) -> NoteProcessingResult:
    """
    Обработка заметки с проверкой дубликатов.

    Workflow:
    1. Проверить хеш контента в SQLite
    2. Если дубликат - вернуть существующий episode_uuid
    3. Если новая - обработать через PipGraphManager
    4. Сохранить метаданные в SQLite

    Args:
        note: Payload заметки с контентом и путем

    Returns:
        NoteProcessingResult с флагом дубликата и UUID эпизода
    """
    print(f"Checking for duplicate: '{note.file_path}'...")

    # ЭТАП 1: Проверка дубликатов (без LLM!)
    group_id = "default"  # TODO: получать из конфигурации пользователя
    check_result = _checknote_service.check_duplicate(note.content, group_id)

    if check_result.is_duplicate:
        print(f"⚠️  Duplicate found: episode_uuid={check_result.existing_episode_uuid}")
        return NoteProcessingResult(
            status="duplicate",
            episode_uuid=check_result.existing_episode_uuid,
            content_hash=check_result.content_hash,
            is_duplicate=True,
            processing_details=None
        )

    # ЭТАП 2: Обработка новой заметки (с LLM)
    print(f"Processing new note '{note.file_path}' with PipGraphManager...")

    graphiti = await get_graphiti()
    pipgraph = PipGraphManager(graphiti)

    result = await pipgraph.process_note(
        name=note.file_path,
        episode_body=note.content,
        source=EpisodeType.text,
        source_description=f"Obsidian note from {note.file_path}",
        reference_time=datetime.now(timezone.utc)
    )

    # ЭТАП 3: Сохранение метаданных
    _checknote_service.save_metadata(
        episode_uuid=result.episode.uuid,
        content_hash=check_result.content_hash,
        group_id=group_id,
        file_path=note.file_path,
        processing_status="completed"
    )

    print(f"✅ Successfully processed: episode_uuid={result.episode.uuid}")

    return NoteProcessingResult(
        status="created",
        episode_uuid=result.episode.uuid,
        content_hash=dup_check.content_hash,
        is_duplicate=False,
        processing_details=result
    )
```

---

### 4. Обновление API

#### `app/api/notes.py` (WebSocket)

```python
@router.websocket("/ws/process")
async def websocket_process_note(websocket: WebSocket):
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        note = NotePayload(**data)

        # Используем новый метод с проверкой дубликатов
        result = await process_and_store_note(note)

        # Отправляем результат с флагом дубликата
        await websocket.send_json({
            "status": result.status,  # "created" | "duplicate"
            "episode_uuid": result.episode_uuid,
            "is_duplicate": result.is_duplicate,
            "content_hash": result.content_hash,
            "nodes_count": len(result.processing_details.nodes) if result.processing_details else 0
        })

    except Exception as e:
        await websocket.send_json({"error": str(e)})
    finally:
        await websocket.close()
```

---

## Обработка ошибок

### Сценарии

1. **LLM fail после проверки хеша**:
   ```python
   try:
       result = await pipgraph.process_note(...)
   except Exception as e:
       # Метаданные НЕ сохраняются в SQLite
       # При повторной попытке заметка будет обработана снова
       raise
   ```

2. **SQLite недоступен**:
   ```python
   try:
       check_result = _checknote_service.check_duplicate(...)
   except sqlite3.Error:
       # Fallback: обрабатывать как новую заметку
       # Логировать предупреждение
       logger.warning("SQLite unavailable, skipping checknote")
   ```

3. **Orphaned metadata** (episode удален из Neo4j, но остался в SQLite):
   - Периодическая задача `cleanup_orphaned()`
   - Вызывается через cron/scheduler
   - Запрашивает все episode UUIDs из Neo4j и удаляет лишние из SQLite

---

## Преимущества подхода

### 1. Производительность
- **Без LLM для дубликатов**: Проверка хеша в SQLite ~1ms vs LLM extraction ~2-5s
- **Индексированные запросы**: `(content_hash, group_id)` - O(log n)

### 2. Совместимость
- **Не модифицирует graphiti_core**: Используем `AddEpisodeResults` как есть
- **Не модифицирует PipGraphManager**: Проверка дубликатов на уровне выше
- **Обратная совместимость**: Старый код работает без изменений

### 3. Гибкость
- **Легко отключить**: Убрать вызов `check_duplicate()`
- **Легко расширить**: Добавить поля в SQLite (processing_time, retry_count)
- **Легко мигрировать**: SQLite → PostgreSQL для production

### 4. Прозрачность
- **Понятный workflow**: Проверка → Обработка → Сохранение
- **Отдельный статус**: `{"status": "duplicate"}` vs `{"status": "created"}`
- **Логирование**: Видно на каком этапе произошел отказ

---

## Тестирование

### Unit тесты

```python
# tests/unit/test_checknote.py

import pytest
from app.services.checknote import ChecknoteService

@pytest.fixture
def checknote_service(tmp_path):
    db_path = tmp_path / "test.db"
    return ChecknoteService(str(db_path))

def test_first_note_not_duplicate(checknote_service):
    result = checknote_service.check_duplicate("Hello world", "group1")
    assert not result.is_duplicate
    assert result.existing_episode_uuid is None

def test_same_content_is_duplicate(checknote_service):
    content = "Hello world"
    group_id = "group1"

    # Первая проверка
    check1 = checknote_service.check_duplicate(content, group_id)
    assert not check1.is_duplicate

    # Сохраняем метаданные
    checknote_service.save_metadata("uuid-123", check1.content_hash, group_id)

    # Вторая проверка того же контента
    check2 = checknote_service.check_duplicate(content, group_id)
    assert check2.is_duplicate
    assert check2.existing_episode_uuid == "uuid-123"

def test_different_groups_not_duplicate(checknote_service):
    content = "Hello world"

    # Сохраняем в group1
    check1 = checknote_service.check_duplicate(content, "group1")
    checknote_service.save_metadata("uuid-1", check1.content_hash, "group1")

    # Проверяем в group2
    check2 = checknote_service.check_duplicate(content, "group2")
    assert not check2.is_duplicate  # Разные группы!
```

### Integration тесты

```python
# tests/integration/test_note_processor_checknote.py

import pytest
from app.services.note_processor import process_and_store_note
from app.models.note import NotePayload

@pytest.mark.integration
async def test_duplicate_note_skips_llm(mock_graphiti):
    """Тест: повторная заметка не вызывает LLM"""
    note = NotePayload(
        file_path="test.md",
        content="Test content"
    )

    # Первая обработка
    result1 = await process_and_store_note(note)
    assert result1.status == "created"
    assert not result1.is_duplicate

    # Вторая обработка того же контента
    result2 = await process_and_store_note(note)
    assert result2.status == "duplicate"
    assert result2.is_duplicate
    assert result2.episode_uuid == result1.episode_uuid

    # Проверяем, что LLM вызван только 1 раз
    assert mock_graphiti.add_episode.call_count == 1
```

---

## Roadmap

### Phase 1: Базовая проверка дубликатов ✅
- [x] SQLite schema
- [x] ChecknoteService
- [x] Интеграция в note_processor
- [x] Unit тесты

### Phase 2: Production готовность
- [ ] Периодическая очистка orphaned metadata
- [ ] Мониторинг SQLite размера
- [ ] Graceful degradation при недоступности SQLite
- [ ] Метрики (% дубликатов, время проверки)

### Phase 3: Расширенные сценарии
- [ ] Обновление заметок (file_path match, но content изменился)
- [ ] Частичные обновления (append to episode)
- [ ] Batch checknote для импорта vault

---

## Альтернативные подходы (не рекомендуются)

### ❌ Вариант 1: Хранить хеш в Neo4j

**Проблема**: Graphiti не поддерживает кастомные свойства в EpisodicNode

```python
# Можно через episode.save() + ручной UPDATE, но это хрупко:
await episode.save(driver)
await driver.execute_query(
    "MATCH (e:Episodic {uuid: $uuid}) SET e.content_hash = $hash",
    uuid=episode.uuid, hash=content_hash
)
```

**Недостатки**:
- Модифицируем поведение graphiti_core
- Хеш не используется в запросах графа
- Сложнее миграция на новую версию Graphiti

### ❌ Вариант 2: Проверка дубликатов через Cypher

```python
# Запрос на совпадение контента (очень медленно!)
records = await driver.execute_query(
    "MATCH (e:Episodic {content: $content, group_id: $group_id}) RETURN e.uuid",
    content=content, group_id=group_id
)
```

**Недостатки**:
- Полное сравнение строк без индекса - O(n)
- Не работает если `store_raw_episode_content=False`
- Не масштабируется (1000+ заметок = медленный запрос)

---

## Заключение

Предложенный подход с **pre-flight checknote** через SQLite:

1. ✅ Не модифицирует graphiti_core
2. ✅ Экономит LLM токены (проверка хеша вместо extraction)
3. ✅ Возвращает понятный статус `{"status": "duplicate"|"created"}`
4. ✅ Легко тестируется и расширяется
5. ✅ Совместим с существующей архитектурой PipGraph

Этот дизайн готов к реализации и не требует изменений в `PipGraphManager` или `graphiti_core`.
