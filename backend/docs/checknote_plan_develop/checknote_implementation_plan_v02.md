# Checknote Implementation Plan v02

## Revision History

- **v01**: Checked duplicates by `content_hash` only
- **v02**: Checks by `file_path` first, then compares hashes to detect updates

---

## Анализ проблемы v01

### Критическая ошибка в v01

В [checknote_implementation_plan.md](./checknote_implementation_plan.md) проверка дубликатов происходит только по `content_hash`:

```python
# v01 - НЕПРАВИЛЬНО
SELECT episode_uuid FROM episode_metadata
WHERE content_hash = ? AND group_id = ?
```

**Проблема**: Эта проверка не учитывает **обновления заметок**.

### Реальные сценарии использования

Пользователь редактирует заметку `coursera/phys/termo.md`:

| Действие | file_path | content | content_hash | Что должно произойти? |
|----------|-----------|---------|--------------|----------------------|
| Первое сохранение | coursera/phys/termo.md | "Термодинамика..." | abc123 | **NEW** → обработать |
| Повторное сохранение (ошибочное) | coursera/phys/termo.md | "Термодинамика..." | abc123 | **DUPLICATE** → пропустить |
| Обновление заметки | coursera/phys/termo.md | "Термодинамика + новый раздел" | def456 | **UPDATED** → (будущее) переобработать |

**Вывод**: Нужно проверять **по имени файла (file_path)**, а не по хешу!

---

## Решение: File-path-first Checking

### Архитектурный подход

```
┌─────────────────────────────────────────────────────────┐
│ API Layer (WebSocket/REST)                              │
│ app/api/notes.py                                        │
└──────────────┬──────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────┐
│ Service Layer: app/services/note_processor.py           │
│                                                          │
│ 1. Вычислить new_content_hash для входящей заметки      │
│ 2. Проверить SQLite по (file_path + group_id)          │
│                                                          │
│    ┌─────────────────────────────────────────┐         │
│    │ SQLite Lookup Decision Tree              │         │
│    └─────────────────────────────────────────┘         │
│                                                          │
│    ┌──► file_path NOT FOUND                            │
│    │    → Status: NEW                                   │
│    │    → Action: process_note() → save metadata        │
│    │                                                     │
│    ├──► file_path FOUND + hash MATCHES                 │
│    │    → Status: DUPLICATE                             │
│    │    → Action: return existing_episode_uuid          │
│    │                                                     │
│    └──► file_path FOUND + hash DIFFERENT               │
│         → Status: UPDATED                               │
│         → Action: (Phase 2) re-process or merge         │
│                                                          │
└──────────────┬──────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────┐
│ PipGraph Manager (без изменений)                        │
│ app/services/pipgraph_manager.py                        │
└──────────────┬──────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────┐
│ Graphiti Core → Neo4j                                   │
└─────────────────────────────────────────────────────────┘
```

---

## Детальная реализация

### 1. SQLite Metadata Database v2

#### Схема таблицы (ИЗМЕНЕНА!)

```sql
CREATE TABLE episode_metadata (
    -- COMPOSITE PRIMARY KEY: заметка уникальна по пути в группе
    file_path TEXT NOT NULL,
    group_id TEXT NOT NULL,

    -- Метаданные эпизода
    episode_uuid TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Статус обработки
    processing_status TEXT DEFAULT 'completed', -- 'completed', 'failed', 'orphaned'
    error_message TEXT,

    -- Составной первичный ключ
    PRIMARY KEY (file_path, group_id)
);

-- Индекс для быстрого поиска по пути (PRIMARY KEY уже создает индекс)
-- Дополнительный индекс для обратного поиска: episode_uuid → file_path
CREATE INDEX idx_episode_uuid ON episode_metadata(episode_uuid);

-- Индекс для очистки orphaned записей
CREATE INDEX idx_processing_status ON episode_metadata(processing_status);
```

#### Ключевые изменения от v01

| Аспект | v01 | v02 |
|--------|-----|-----|
| PRIMARY KEY | `episode_uuid` | `(file_path, group_id)` |
| Lookup стратегия | По `content_hash` | По `file_path` → сравнение hash |
| Индексы | `idx_content_hash_group` | `idx_episode_uuid`, `idx_processing_status` |
| Поддержка обновлений | ❌ Нет | ✅ Да (через `updated_at`) |

#### Жизненный цикл записи

1. **Создание**: После успешного `process_note()` → `INSERT` с `file_path` + `content_hash`
2. **Проверка**: Перед обработкой → `SELECT` по `file_path` → сравнение хешей
3. **Обновление**: При изменении контента → `UPDATE` с новым `content_hash` + `updated_at`
4. **Очистка**: Периодически удаляем orphaned записи (episode удален из Neo4j)

---

### 2. Модуль проверки заметок v2

#### Новый файл: `app/services/checknote.py`

```python
"""
Checknote service v2 using file_path-based duplicate detection.

Архитектура:
- SQLite хранит маппинг (file_path, group_id) → (episode_uuid, content_hash)
- Проверка происходит ДО вызова LLM
- Поддерживает три сценария: NEW, DUPLICATE, UPDATED
"""

import hashlib
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel


class ChecknoteResult(BaseModel):
    """Результат проверки заметки (3 возможных статуса)"""
    status: Literal["new", "duplicate", "updated"]
    existing_episode_uuid: Optional[str] = None
    old_content_hash: Optional[str] = None  # Для сценария UPDATED
    new_content_hash: str


class ChecknoteService:
    """Сервис для отслеживания заметок через SQLite v2"""

    def __init__(self, db_path: str = "data/episode_metadata.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Инициализация SQLite базы с составным первичным ключом"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episode_metadata (
                    file_path TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    episode_uuid TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processing_status TEXT DEFAULT 'completed',
                    error_message TEXT,
                    PRIMARY KEY (file_path, group_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_episode_uuid
                ON episode_metadata(episode_uuid)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_processing_status
                ON episode_metadata(processing_status)
            """)

    @staticmethod
    def compute_hash(content: str) -> str:
        """Вычислить SHA-256 хеш контента"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def check_note_status(
        self,
        file_path: str,
        content: str,
        group_id: str
    ) -> ChecknoteResult:
        """
        Проверить статус заметки: NEW, DUPLICATE или UPDATED.

        Алгоритм:
        1. Вычислить хеш нового контента
        2. Поискать запись по (file_path, group_id)
        3. Если не найдена → NEW
        4. Если найдена:
           - Хеш совпадает → DUPLICATE
           - Хеш различается → UPDATED

        Args:
            file_path: Путь к заметке (напр. "coursera/phys/termo.md")
            content: Текст заметки для проверки
            group_id: ID группы графа (для изоляции)

        Returns:
            ChecknoteResult со статусом и метаданными
        """
        new_content_hash = self.compute_hash(content)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT episode_uuid, content_hash
                FROM episode_metadata
                WHERE file_path = ? AND group_id = ? AND processing_status = 'completed'
                """,
                (file_path, group_id)
            )
            result = cursor.fetchone()

        # Сценарий 1: Заметка не найдена → NEW
        if result is None:
            return ChecknoteResult(
                status="new",
                new_content_hash=new_content_hash
            )

        existing_episode_uuid, old_content_hash = result

        # Сценарий 2: Хеш совпадает → DUPLICATE
        if old_content_hash == new_content_hash:
            return ChecknoteResult(
                status="duplicate",
                existing_episode_uuid=existing_episode_uuid,
                old_content_hash=old_content_hash,
                new_content_hash=new_content_hash
            )

        # Сценарий 3: Хеш различается → UPDATED
        return ChecknoteResult(
            status="updated",
            existing_episode_uuid=existing_episode_uuid,
            old_content_hash=old_content_hash,
            new_content_hash=new_content_hash
        )

    def save_metadata(
        self,
        file_path: str,
        episode_uuid: str,
        content_hash: str,
        group_id: str,
        processing_status: str = "completed",
        error_message: Optional[str] = None
    ):
        """
        Сохранить метаданные эпизода после успешной обработки.

        Использует INSERT OR REPLACE для обработки как новых, так и обновленных заметок.

        Args:
            file_path: Путь к заметке
            episode_uuid: UUID созданного эпизода из Neo4j
            content_hash: Хеш контента
            group_id: ID группы графа
            processing_status: Статус обработки
            error_message: Сообщение об ошибке (если есть)
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO episode_metadata
                (file_path, group_id, episode_uuid, content_hash,
                 updated_at, processing_status, error_message)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
                """,
                (file_path, group_id, episode_uuid, content_hash,
                 processing_status, error_message)
            )

    def update_content_hash(
        self,
        file_path: str,
        group_id: str,
        new_episode_uuid: str,
        new_content_hash: str
    ):
        """
        Обновить хеш при переобработке заметки (для сценария UPDATED).

        Args:
            file_path: Путь к заметке
            group_id: ID группы графа
            new_episode_uuid: UUID нового эпизода (после переобработки)
            new_content_hash: Новый хеш контента
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE episode_metadata
                SET episode_uuid = ?,
                    content_hash = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE file_path = ? AND group_id = ?
                """,
                (new_episode_uuid, new_content_hash, file_path, group_id)
            )

    def get_metadata_by_path(
        self,
        file_path: str,
        group_id: str
    ) -> Optional[dict]:
        """
        Получить метаданные заметки по пути.

        Args:
            file_path: Путь к заметке
            group_id: ID группы графа

        Returns:
            Словарь с метаданными или None
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT episode_uuid, content_hash, created_at, updated_at, processing_status
                FROM episode_metadata
                WHERE file_path = ? AND group_id = ?
                """,
                (file_path, group_id)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def cleanup_orphaned(self, valid_uuids: list[str]):
        """
        Удалить записи для эпизодов, которых больше нет в Neo4j.

        Args:
            valid_uuids: Список UUID эпизодов, существующих в Neo4j
        """
        if not valid_uuids:
            return

        placeholders = ','.join('?' * len(valid_uuids))
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                f"DELETE FROM episode_metadata WHERE episode_uuid NOT IN ({placeholders})",
                valid_uuids
            )
            deleted_count = cursor.rowcount
            print(f"Cleaned up {deleted_count} orphaned metadata records")
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
    Результат обработки заметки с поддержкой трех статусов.

    Статусы:
    - "new": Заметка обработана впервые
    - "duplicate": Повторная попытка обработать тот же контент (пропущено)
    - "updated": Заметка с тем же путем, но измененным контентом (Phase 2)
    """
    status: str  # "new" | "duplicate" | "updated"
    episode_uuid: str
    content_hash: str
    old_content_hash: Optional[str] = None  # Для статуса "updated"
    processing_details: Optional[AddEpisodeResults] = None  # None для "duplicate"


# Глобальный экземпляр сервиса checknote
_checknote_service = ChecknoteService()


async def process_and_store_note(note: NotePayload) -> NoteProcessingResult:
    """
    Обработка заметки с проверкой по file_path.

    Workflow:
    1. Проверить SQLite по (file_path + group_id)
    2. Сравнить хеши для определения статуса: NEW, DUPLICATE, UPDATED
    3. В зависимости от статуса:
       - NEW: обработать через PipGraphManager → сохранить метаданные
       - DUPLICATE: вернуть существующий episode_uuid (без LLM!)
       - UPDATED: (Phase 2) переобработать или обновить граф

    Args:
        note: Payload заметки с file_path и content

    Returns:
        NoteProcessingResult со статусом и UUID эпизода
    """
    print(f"Checking note status: '{note.file_path}'...")

    # ЭТАП 1: Проверка статуса заметки (без LLM!)
    group_id = "default"  # TODO: получать из конфигурации пользователя
    check_result = _checknote_service.check_note_status(
        file_path=note.file_path,
        content=note.content,
        group_id=group_id
    )

    # СЦЕНАРИЙ 1: DUPLICATE - пропустить обработку
    if check_result.status == "duplicate":
        print(f"⚠️  Duplicate detected: episode_uuid={check_result.existing_episode_uuid}")
        print(f"   Skipping LLM processing (content hash matches)")
        return NoteProcessingResult(
            status="duplicate",
            episode_uuid=check_result.existing_episode_uuid,
            content_hash=check_result.new_content_hash,
            old_content_hash=check_result.old_content_hash,
            processing_details=None
        )

    # СЦЕНАРИЙ 2: UPDATED - обнаружено изменение контента
    if check_result.status == "updated":
        print(f"📝 Note updated: '{note.file_path}'")
        print(f"   Old hash: {check_result.old_content_hash[:16]}...")
        print(f"   New hash: {check_result.new_content_hash[:16]}...")
        print(f"   ⚠️  Update handling not implemented yet (Phase 2)")

        # TODO Phase 2: Реализовать обновление заметки
        # Варианты:
        # 1. Переобработать заметку полностью (создать новый episode)
        # 2. Инкрементальное обновление (merge новых сущностей)
        # 3. Создать новый episode с ссылкой на предыдущий

        # Пока возвращаем существующий episode_uuid
        return NoteProcessingResult(
            status="updated",
            episode_uuid=check_result.existing_episode_uuid,
            content_hash=check_result.new_content_hash,
            old_content_hash=check_result.old_content_hash,
            processing_details=None
        )

    # СЦЕНАРИЙ 3: NEW - обработка новой заметки (с LLM)
    print(f"✨ New note detected: '{note.file_path}'")
    print(f"   Processing with PipGraphManager...")

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
        file_path=note.file_path,
        episode_uuid=result.episode.uuid,
        content_hash=check_result.new_content_hash,
        group_id=group_id,
        processing_status="completed"
    )

    print(f"✅ Successfully processed: episode_uuid={result.episode.uuid}")

    return NoteProcessingResult(
        status="new",
        episode_uuid=result.episode.uuid,
        content_hash=check_result.new_content_hash,
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

        # Используем новый метод с тремя статусами
        result = await process_and_store_note(note)

        # Отправляем результат клиенту
        await websocket.send_json({
            "status": result.status,  # "new" | "duplicate" | "updated"
            "episode_uuid": result.episode_uuid,
            "content_hash": result.content_hash,
            "old_content_hash": result.old_content_hash,  # Только для "updated"
            "nodes_count": len(result.processing_details.nodes) if result.processing_details else 0,
            "message": _get_status_message(result.status)
        })

    except Exception as e:
        await websocket.send_json({"error": str(e)})
    finally:
        await websocket.close()


def _get_status_message(status: str) -> str:
    """Пользовательские сообщения для каждого статуса"""
    messages = {
        "new": "Note processed successfully",
        "duplicate": "Note already processed with identical content",
        "updated": "Note content has changed (update handling coming in Phase 2)"
    }
    return messages.get(status, "Unknown status")
```

---

## Обработка ошибок

### Сценарии

1. **LLM fail после проверки статуса**:
   ```python
   try:
       result = await pipgraph.process_note(...)
   except Exception as e:
       # Метаданные НЕ сохраняются в SQLite
       # При повторной попытке статус будет снова "new"
       raise
   ```

2. **SQLite недоступен**:
   ```python
   try:
       check_result = _checknote_service.check_note_status(...)
   except sqlite3.Error as e:
       # Fallback: обрабатывать как новую заметку
       logger.warning(f"SQLite unavailable, skipping checknote: {e}")
       # Продолжить обработку без проверки дубликатов
   ```

3. **Orphaned metadata** (episode удален из Neo4j, но остался в SQLite):
   - Периодическая задача `cleanup_orphaned()`
   - Вызывается через cron/scheduler
   - Запрашивает все episode UUIDs из Neo4j и удаляет лишние из SQLite

---

## Преимущества подхода v02

### 1. Производительность

- **Без LLM для дубликатов**: SQLite lookup ~1ms vs LLM extraction ~2-5s
- **Индексированный PRIMARY KEY**: `(file_path, group_id)` - O(log n)
- **Один запрос**: Не нужно сначала искать по хешу, потом по пути

### 2. Корректность

- **Обнаруживает обновления**: Различает дубликаты от измененных заметок
- **Идентификация по имени**: `file_path` - это естественный идентификатор заметки
- **Три статуса**: Ясное разделение сценариев NEW/DUPLICATE/UPDATED

### 3. Совместимость

- **Не модифицирует graphiti_core**: Используем `AddEpisodeResults` как есть
- **Не модифицирует PipGraphManager**: Проверка на уровне выше
- **Обратная совместимость**: Старый код работает без изменений

### 4. Расширяемость

- **Готов к Phase 2**: Архитектура поддерживает обновления заметок
- **Легко мигрировать**: SQLite → PostgreSQL для production
- **Легко расширить**: Добавить `version_number`, `parent_episode_uuid` для версионирования

---

## Тестирование

### Unit тесты

```python
# tests/unit/test_checknote_v2.py

import pytest
from app.services.checknote import ChecknoteService

@pytest.fixture
def checknote_service(tmp_path):
    db_path = tmp_path / "test.db"
    return ChecknoteService(str(db_path))


def test_new_note_status(checknote_service):
    """Первая проверка заметки должна вернуть статус 'new'"""
    result = checknote_service.check_note_status(
        file_path="coursera/phys/termo.md",
        content="Термодинамика...",
        group_id="group1"
    )
    assert result.status == "new"
    assert result.existing_episode_uuid is None


def test_duplicate_note_status(checknote_service):
    """Повторная проверка с тем же контентом должна вернуть 'duplicate'"""
    file_path = "coursera/phys/termo.md"
    content = "Термодинамика..."
    group_id = "group1"

    # Первая проверка
    check1 = checknote_service.check_note_status(file_path, content, group_id)
    assert check1.status == "new"

    # Сохраняем метаданные
    checknote_service.save_metadata(
        file_path=file_path,
        episode_uuid="uuid-123",
        content_hash=check1.new_content_hash,
        group_id=group_id
    )

    # Вторая проверка того же контента
    check2 = checknote_service.check_note_status(file_path, content, group_id)
    assert check2.status == "duplicate"
    assert check2.existing_episode_uuid == "uuid-123"
    assert check2.old_content_hash == check2.new_content_hash


def test_updated_note_status(checknote_service):
    """Проверка заметки с измененным контентом должна вернуть 'updated'"""
    file_path = "coursera/phys/termo.md"
    group_id = "group1"

    # Исходный контент
    old_content = "Термодинамика..."
    check1 = checknote_service.check_note_status(file_path, old_content, group_id)
    checknote_service.save_metadata(
        file_path=file_path,
        episode_uuid="uuid-123",
        content_hash=check1.new_content_hash,
        group_id=group_id
    )

    # Измененный контент
    new_content = "Термодинамика + новый раздел..."
    check2 = checknote_service.check_note_status(file_path, new_content, group_id)

    assert check2.status == "updated"
    assert check2.existing_episode_uuid == "uuid-123"
    assert check2.old_content_hash != check2.new_content_hash


def test_different_groups_isolated(checknote_service):
    """Заметки с одинаковым путем в разных группах должны быть независимы"""
    file_path = "note.md"
    content = "Content"

    # Сохраняем в group1
    check1 = checknote_service.check_note_status(file_path, content, "group1")
    checknote_service.save_metadata(file_path, "uuid-1", check1.new_content_hash, "group1")

    # Проверяем в group2
    check2 = checknote_service.check_note_status(file_path, content, "group2")
    assert check2.status == "new"  # Разные группы!


def test_same_content_different_paths(checknote_service):
    """Одинаковый контент в разных файлах должен считаться разными заметками"""
    content = "Identical content"
    group_id = "group1"

    # Заметка 1
    check1 = checknote_service.check_note_status("path1.md", content, group_id)
    checknote_service.save_metadata("path1.md", "uuid-1", check1.new_content_hash, group_id)

    # Заметка 2 с тем же контентом, но другим путем
    check2 = checknote_service.check_note_status("path2.md", content, group_id)
    assert check2.status == "new"  # Разные пути → разные заметки
```

### Integration тесты

```python
# tests/integration/test_note_processor_v2.py

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
    assert result1.status == "new"

    # Вторая обработка того же контента
    result2 = await process_and_store_note(note)
    assert result2.status == "duplicate"
    assert result2.episode_uuid == result1.episode_uuid

    # Проверяем, что LLM вызван только 1 раз
    assert mock_graphiti.add_episode.call_count == 1


@pytest.mark.integration
async def test_updated_note_detected(mock_graphiti):
    """Тест: обновление заметки обнаруживается"""
    file_path = "coursera/phys/termo.md"

    # Первая версия
    note_v1 = NotePayload(file_path=file_path, content="Version 1")
    result1 = await process_and_store_note(note_v1)
    assert result1.status == "new"

    # Измененная версия
    note_v2 = NotePayload(file_path=file_path, content="Version 2 - updated")
    result2 = await process_and_store_note(note_v2)

    assert result2.status == "updated"
    assert result2.episode_uuid == result1.episode_uuid  # Тот же эпизод
    assert result2.old_content_hash != result2.content_hash  # Хеши различаются
```

---

## Roadmap

### Phase 1: Базовая проверка NEW/DUPLICATE ✅

- [x] SQLite schema с композитным PRIMARY KEY
- [x] ChecknoteService с методом `check_note_status()`
- [x] Интеграция в `note_processor.py`
- [x] Unit тесты для трех статусов
- [x] Обнаружение статуса UPDATED (без обработки)

### Phase 2: Обработка обновлений заметок

- [ ] **Вариант A**: Полная переобработка (создать новый episode)
  - Удалить старый episode из Neo4j
  - Обработать заметку заново через `process_note()`
  - Обновить `episode_uuid` в SQLite

- [ ] **Вариант B**: Инкрементальное обновление
  - Извлечь только новые сущности (diff контента)
  - Добавить их к существующему episode
  - Сохранить новый `content_hash`

- [ ] **Вариант C**: Версионирование заметок
  - Создать новый episode с ссылкой на предыдущий
  - Добавить поле `version_number` в SQLite
  - Хранить историю изменений

### Phase 3: Production готовность

- [ ] Периодическая очистка orphaned metadata
- [ ] Мониторинг размера SQLite
- [ ] Graceful degradation при недоступности SQLite
- [ ] Метрики (% дубликатов, % обновлений, время проверки)

### Phase 4: Расширенные сценарии

- [ ] Batch checknote для импорта vault
- [ ] API для просмотра истории изменений заметки
- [ ] Уведомления при обнаружении обновления

---

## Сравнение v01 vs v02

| Аспект | v01 | v02 |
|--------|-----|-----|
| **Lookup key** | `content_hash` | `file_path` + `group_id` |
| **PRIMARY KEY** | `episode_uuid` | `(file_path, group_id)` |
| **Статусы** | 2 (new, duplicate) | 3 (new, duplicate, updated) |
| **Обнаружение обновлений** | ❌ Нет | ✅ Да |
| **Корректность** | ❌ Ложные дубликаты | ✅ Правильная идентификация |
| **Производительность** | ~1ms | ~1ms (аналогично) |
| **Расширяемость** | Ограничена | Готова к версионированию |

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

### ❌ Вариант 2: Проверка дубликатов через Cypher по name

```python
# Запрос на совпадение name (медленнее SQLite)
records = await driver.execute_query(
    """
    MATCH (e:Episodic {name: $name, group_id: $group_id})
    RETURN e.uuid, e.content
    """,
    name=file_path, group_id=group_id
)
# Затем вычислить хеш e.content и сравнить
```

**Недостатки**:
- Не работает если `store_raw_episode_content=False`
- Нужно передавать весь `content` из Neo4j для вычисления хеша
- Медленнее: Neo4j query ~10-50ms vs SQLite ~1ms
- Нагрузка на Neo4j для простой проверки хеша

---

## Заключение

Предложенный подход с **file-path-first checking** через SQLite v2:

1. ✅ Корректно обнаруживает обновления заметок
2. ✅ Не модифицирует graphiti_core или PipGraphManager
3. ✅ Экономит LLM токены (проверка хеша вместо extraction)
4. ✅ Возвращает понятный статус `"new"|"duplicate"|"updated"`
5. ✅ Легко тестируется и расширяется
6. ✅ Готов к Phase 2 (обработка обновлений)

**Ключевое отличие от v01**: Заметка идентифицируется по `file_path`, а не по `content_hash`. Это позволяет различать повторную обработку того же контента (duplicate) от обновления заметки (updated).

Этот дизайн готов к реализации и полностью совместим с существующей архитектурой PipGraph.
