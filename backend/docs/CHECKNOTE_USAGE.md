# Checknote v2 Usage Guide

## Обзор

Checknote v2 - система проверки дубликатов и обновлений заметок перед обработкой через LLM. Использует file-path-first подход для идентификации заметок.

## Ключевые особенности

- **Экономия токенов LLM**: Повторные заметки не обрабатываются
- **Обнаружение обновлений**: Различает дубликаты от измененных заметок
- **Три статуса**: NEW, DUPLICATE, UPDATED
- **SQLite для метаданных**: Быстрая проверка (~1ms)
- **Изоляция групп**: Поддержка мультитенантности

## Архитектура

```
Note → ChecknoteService → SQLite lookup → 3 сценария:
  ├─ NEW: Обработать через LLM → Сохранить метаданные
  ├─ DUPLICATE: Вернуть existing episode_uuid (без LLM)
  └─ UPDATED: Вернуть existing episode_uuid (Phase 2 - не реализовано)
```

## Использование

### Автоматическая проверка

Система автоматически проверяет заметки при вызове `process_and_store_note()`:

```python
from app.models.note import NotePayload
from app.services.note_processor import process_and_store_note

note = NotePayload(
    file_path="coursera/phys/termo.md",
    content="Термодинамика..."
)

result = await process_and_store_note(note)

# result.status может быть: "new", "duplicate", "updated"
# result.episode_uuid - UUID эпизода в Neo4j
# result.content_hash - SHA-256 хеш контента
# result.processing_details - детали обработки (None для duplicate/updated)
```

### Прямое использование ChecknoteService

```python
from app.services.checknote import ChecknoteService

checknote = ChecknoteService()

# Проверить статус заметки
result = checknote.check_note_status(
    file_path="note.md",
    content="Content",
    group_id="default"
)

if result.status == "new":
    # Обработать заметку
    episode_uuid = process_with_llm(...)

    # Сохранить метаданные
    checknote.save_metadata(
        file_path="note.md",
        episode_uuid=episode_uuid,
        content_hash=result.new_content_hash,
        group_id="default"
    )
elif result.status == "duplicate":
    # Использовать существующий episode_uuid
    episode_uuid = result.existing_episode_uuid
```

## WebSocket API Response

При обработке через WebSocket endpoint клиент получает:

```json
{
  "status": "new",  // "new" | "duplicate" | "updated"
  "episode_uuid": "abc-123...",
  "content_hash": "sha256-hash...",
  "old_content_hash": null,  // Только для "updated"
  "nodes_count": 5,
  "edges_count": 3,
  "message": "Note processed successfully"
}
```

## SQLite Schema

```sql
CREATE TABLE episode_metadata (
    file_path TEXT NOT NULL,
    group_id TEXT NOT NULL,
    episode_uuid TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processing_status TEXT DEFAULT 'completed',
    error_message TEXT,
    PRIMARY KEY (file_path, group_id)
);
```

## Тестирование

```bash
# Unit тесты
uv run pytest tests/unit/test_checknote.py -v

# Integration тесты (требуют Neo4j + OpenRouter)
uv run pytest tests/integration/test_note_processor_checknote.py -v -m integration
```

## Сценарии использования

### 1. Новая заметка

```
User сохраняет "coursera/phys/termo.md" впервые
→ Status: NEW
→ LLM обрабатывает заметку
→ Метаданные сохраняются в SQLite
```

### 2. Повторное сохранение (ошибка пользователя)

```
User случайно отправляет ту же заметку снова
→ Status: DUPLICATE
→ LLM НЕ вызывается
→ Возвращается existing episode_uuid
```

### 3. Обновление заметки

```
User редактирует "coursera/phys/termo.md"
→ Status: UPDATED
→ Обнаруживается изменение контента
→ (Phase 2) Переобработать или обновить граф
```

### 4. Одинаковый контент в разных файлах

```
User создает "note1.md" и "note2.md" с идентичным текстом
→ Обе обрабатываются как NEW
→ Создаются два отдельных эпизода
→ Идентификация по file_path, а не по content_hash
```

## Конфигурация

По умолчанию:
- SQLite база: `data/episode_metadata.db`
- Group ID: `"default"`
- Processing status: `"completed"`

Для изменения пути к БД:

```python
from app.services.checknote import ChecknoteService

checknote = ChecknoteService(db_path="custom/path/metadata.db")
```

## Мониторинг

### Проверка метаданных

```python
metadata = checknote.get_metadata_by_path("note.md", "default")
print(f"Episode UUID: {metadata['episode_uuid']}")
print(f"Content hash: {metadata['content_hash']}")
print(f"Created: {metadata['created_at']}")
print(f"Updated: {metadata['updated_at']}")
```

### Очистка orphaned записей

```python
# Получить все существующие episode UUIDs из Neo4j
valid_uuids = await get_all_episode_uuids_from_neo4j()

# Удалить orphaned метаданные
checknote.cleanup_orphaned(valid_uuids)
```

## Ограничения Phase 1

- ✅ Обнаружение NEW/DUPLICATE работает
- ✅ Обнаружение UPDATED работает
- ❌ Обработка UPDATED не реализована (возвращает existing episode_uuid)
- ❌ Нет автоматической очистки orphaned записей (вручную через cleanup_orphaned)
- ❌ Group ID захардкоден как "default" (TODO: конфигурация)

## Roadmap Phase 2

1. Обработка обновлений заметок:
   - Вариант A: Полная переобработка
   - Вариант B: Инкрементальное обновление (diff)
   - Вариант C: Версионирование

2. Production готовность:
   - Периодическая очистка orphaned
   - Graceful degradation при недоступности SQLite
   - Метрики (% дубликатов, время проверки)

3. Расширенные сценарии:
   - Batch checknote для импорта vault
   - API для просмотра истории изменений
   - Уведомления при обновлениях
