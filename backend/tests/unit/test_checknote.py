"""
Unit тесты для ChecknoteService v2 (file-path-first checking).

Тестируем три сценария:
1. NEW - заметка впервые добавляется
2. DUPLICATE - повторная обработка идентичного контента
3. UPDATED - обработка заметки с измененным контентом
"""

import pytest
from pathlib import Path
from app.services.checknote import ChecknoteService


@pytest.fixture
def checknote_service(tmp_path):
    """Создать временный ChecknoteService для тестов"""
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
    assert result.old_content_hash is None
    assert result.new_content_hash is not None


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


def test_compute_hash_deterministic(checknote_service):
    """Хеш одинакового контента должен быть детерминированным"""
    content = "Test content"
    hash1 = checknote_service.compute_hash(content)
    hash2 = checknote_service.compute_hash(content)
    assert hash1 == hash2


def test_compute_hash_different_content(checknote_service):
    """Хеш разного контента должен отличаться"""
    hash1 = checknote_service.compute_hash("Content 1")
    hash2 = checknote_service.compute_hash("Content 2")
    assert hash1 != hash2


def test_get_metadata_by_path(checknote_service):
    """Проверка получения метаданных по пути"""
    file_path = "test.md"
    group_id = "group1"
    content = "Test content"

    # Сначала метаданных нет
    metadata = checknote_service.get_metadata_by_path(file_path, group_id)
    assert metadata is None

    # Сохраняем метаданные
    check = checknote_service.check_note_status(file_path, content, group_id)
    checknote_service.save_metadata(
        file_path=file_path,
        episode_uuid="uuid-123",
        content_hash=check.new_content_hash,
        group_id=group_id
    )

    # Получаем метаданные
    metadata = checknote_service.get_metadata_by_path(file_path, group_id)
    assert metadata is not None
    assert metadata["episode_uuid"] == "uuid-123"
    assert metadata["content_hash"] == check.new_content_hash
    assert metadata["processing_status"] == "completed"


def test_update_content_hash(checknote_service):
    """Проверка обновления хеша контента"""
    file_path = "test.md"
    group_id = "group1"

    # Сохраняем исходную заметку
    old_hash = checknote_service.compute_hash("Old content")
    checknote_service.save_metadata(file_path, "uuid-old", old_hash, group_id)

    # Обновляем хеш
    new_hash = checknote_service.compute_hash("New content")
    checknote_service.update_content_hash(file_path, group_id, "uuid-new", new_hash)

    # Проверяем, что метаданные обновились
    metadata = checknote_service.get_metadata_by_path(file_path, group_id)
    assert metadata["episode_uuid"] == "uuid-new"
    assert metadata["content_hash"] == new_hash


def test_cleanup_orphaned(checknote_service):
    """Проверка удаления orphaned записей"""
    group_id = "group1"

    # Создаем несколько заметок
    for i in range(5):
        check = checknote_service.check_note_status(f"note{i}.md", f"Content {i}", group_id)
        checknote_service.save_metadata(
            file_path=f"note{i}.md",
            episode_uuid=f"uuid-{i}",
            content_hash=check.new_content_hash,
            group_id=group_id
        )

    # Удаляем orphaned (оставляем только uuid-0 и uuid-1)
    checknote_service.cleanup_orphaned(["uuid-0", "uuid-1"])

    # Проверяем, что остались только 2 записи
    for i in range(2):
        metadata = checknote_service.get_metadata_by_path(f"note{i}.md", group_id)
        assert metadata is not None

    for i in range(2, 5):
        metadata = checknote_service.get_metadata_by_path(f"note{i}.md", group_id)
        assert metadata is None


def test_save_metadata_with_error(checknote_service):
    """Проверка сохранения метаданных с ошибкой"""
    file_path = "error.md"
    group_id = "group1"
    content_hash = checknote_service.compute_hash("Content")

    checknote_service.save_metadata(
        file_path=file_path,
        episode_uuid="uuid-error",
        content_hash=content_hash,
        group_id=group_id,
        processing_status="failed",
        error_message="LLM timeout"
    )

    metadata = checknote_service.get_metadata_by_path(file_path, group_id)
    assert metadata["processing_status"] == "failed"
    assert metadata["error_message"] == "LLM timeout"


def test_insert_or_replace(checknote_service):
    """Проверка INSERT OR REPLACE при повторном сохранении"""
    file_path = "test.md"
    group_id = "group1"

    # Первое сохранение
    hash1 = checknote_service.compute_hash("Content 1")
    checknote_service.save_metadata(file_path, "uuid-1", hash1, group_id)

    metadata1 = checknote_service.get_metadata_by_path(file_path, group_id)
    assert metadata1["episode_uuid"] == "uuid-1"
    assert metadata1["content_hash"] == hash1

    # Второе сохранение (REPLACE)
    hash2 = checknote_service.compute_hash("Content 2")
    checknote_service.save_metadata(file_path, "uuid-2", hash2, group_id)

    metadata2 = checknote_service.get_metadata_by_path(file_path, group_id)
    assert metadata2["episode_uuid"] == "uuid-2"
    assert metadata2["content_hash"] == hash2

    # Должна быть только одна запись
    assert metadata2["created_at"] is not None
    assert metadata2["updated_at"] is not None
