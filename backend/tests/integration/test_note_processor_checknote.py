"""
Integration тесты для note_processor с checknote функциональностью.

Проверяем:
1. Дубликаты не вызывают LLM
2. Обновления заметок корректно обнаруживаются
3. Метаданные сохраняются после обработки
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from app.services.note_processor import process_and_store_note
from app.models.note import NotePayload
from app.services.checknote import ChecknoteService
from app.services.pipgraph_manager import AddEpisodeResults
from graphiti_core.nodes import EpisodicNode


@pytest.fixture
def temp_checknote_service(tmp_path):
    """Временный ChecknoteService для тестов"""
    db_path = tmp_path / "test_integration.db"
    return ChecknoteService(str(db_path))


@pytest.fixture
def mock_pipgraph_result():
    """Mock результата PipGraphManager.process_note()"""
    mock_episode = Mock(spec=EpisodicNode)
    mock_episode.uuid = "test-episode-uuid-123"

    # Create a proper AddEpisodeResults instance instead of Mock
    mock_result = AddEpisodeResults(
        episode=mock_episode,
        episodic_edges=[],
        nodes=[],
        edges=[],
        communities=[],
        community_edges=[]
    )

    return mock_result


@pytest.mark.integration
async def test_new_note_calls_llm(temp_checknote_service, mock_pipgraph_result):
    """Тест: новая заметка вызывает LLM и сохраняет метаданные"""
    note = NotePayload(
        file_path="test/new_note.md",
        content="This is a new note about thermodynamics"
    )

    # Mock PipGraphManager
    with patch("app.services.note_processor._checknote_service", temp_checknote_service), \
         patch("app.services.note_processor.get_graphiti") as mock_get_graphiti, \
         patch("app.services.note_processor.PipGraphManager") as MockPipGraphManager:

        # Настройка моков
        mock_graphiti = AsyncMock()
        mock_get_graphiti.return_value = mock_graphiti

        mock_manager = AsyncMock()
        mock_manager.process_note = AsyncMock(return_value=mock_pipgraph_result)
        MockPipGraphManager.return_value = mock_manager

        # Выполнение
        result = await process_and_store_note(note)

        # Проверка
        assert result.status == "new"
        assert result.episode_uuid == "test-episode-uuid-123"
        assert result.content_hash is not None
        assert result.processing_details is not None

        # Проверяем, что LLM был вызван
        mock_manager.process_note.assert_called_once()

        # Проверяем, что метаданные сохранены
        metadata = temp_checknote_service.get_metadata_by_path(
            file_path=note.file_path,
            group_id="default"
        )
        assert metadata is not None
        assert metadata["episode_uuid"] == "test-episode-uuid-123"


@pytest.mark.integration
async def test_duplicate_note_skips_llm(temp_checknote_service, mock_pipgraph_result):
    """Тест: повторная заметка не вызывает LLM"""
    note = NotePayload(
        file_path="test/duplicate.md",
        content="Same content twice"
    )

    with patch("app.services.note_processor._checknote_service", temp_checknote_service), \
         patch("app.services.note_processor.get_graphiti") as mock_get_graphiti, \
         patch("app.services.note_processor.PipGraphManager") as MockPipGraphManager:

        # Настройка моков
        mock_graphiti = AsyncMock()
        mock_get_graphiti.return_value = mock_graphiti

        mock_manager = AsyncMock()
        mock_manager.process_note = AsyncMock(return_value=mock_pipgraph_result)
        MockPipGraphManager.return_value = mock_manager

        # Первая обработка
        result1 = await process_and_store_note(note)
        assert result1.status == "new"
        assert mock_manager.process_note.call_count == 1

        # Вторая обработка того же контента
        result2 = await process_and_store_note(note)

        # Проверка
        assert result2.status == "duplicate"
        assert result2.episode_uuid == result1.episode_uuid
        assert result2.content_hash == result1.content_hash
        assert result2.processing_details is None

        # LLM должен быть вызван только 1 раз (не 2!)
        assert mock_manager.process_note.call_count == 1


@pytest.mark.integration
async def test_updated_note_detected(temp_checknote_service, mock_pipgraph_result):
    """Тест: обновление заметки обнаруживается"""
    file_path = "test/updated.md"

    with patch("app.services.note_processor._checknote_service", temp_checknote_service), \
         patch("app.services.note_processor.get_graphiti") as mock_get_graphiti, \
         patch("app.services.note_processor.PipGraphManager") as MockPipGraphManager:

        # Настройка моков
        mock_graphiti = AsyncMock()
        mock_get_graphiti.return_value = mock_graphiti

        mock_manager = AsyncMock()
        mock_manager.process_note = AsyncMock(return_value=mock_pipgraph_result)
        MockPipGraphManager.return_value = mock_manager

        # Первая версия
        note_v1 = NotePayload(file_path=file_path, content="Version 1")
        result1 = await process_and_store_note(note_v1)
        assert result1.status == "new"

        # Измененная версия
        note_v2 = NotePayload(file_path=file_path, content="Version 2 - updated content")
        result2 = await process_and_store_note(note_v2)

        # Проверка
        assert result2.status == "updated"
        assert result2.episode_uuid == result1.episode_uuid  # Тот же эпизод
        assert result2.old_content_hash == result1.content_hash
        assert result2.content_hash != result1.content_hash  # Хеши различаются
        assert result2.processing_details is None  # Phase 2 не реализована


@pytest.mark.integration
async def test_different_files_same_content_both_processed(temp_checknote_service, mock_pipgraph_result):
    """Тест: одинаковый контент в разных файлах обрабатывается отдельно"""
    content = "Same content in different files"

    with patch("app.services.note_processor._checknote_service", temp_checknote_service), \
         patch("app.services.note_processor.get_graphiti") as mock_get_graphiti, \
         patch("app.services.note_processor.PipGraphManager") as MockPipGraphManager:

        # Настройка моков с разными UUID для разных файлов
        mock_graphiti = AsyncMock()
        mock_get_graphiti.return_value = mock_graphiti

        mock_manager = AsyncMock()

        # Первый вызов
        mock_episode_1 = Mock(spec=EpisodicNode)
        mock_episode_1.uuid = "uuid-file1"
        mock_result_1 = AddEpisodeResults(
            episode=mock_episode_1,
            episodic_edges=[],
            nodes=[],
            edges=[],
            communities=[],
            community_edges=[]
        )

        # Второй вызов
        mock_episode_2 = Mock(spec=EpisodicNode)
        mock_episode_2.uuid = "uuid-file2"
        mock_result_2 = AddEpisodeResults(
            episode=mock_episode_2,
            episodic_edges=[],
            nodes=[],
            edges=[],
            communities=[],
            community_edges=[]
        )

        mock_manager.process_note = AsyncMock(side_effect=[mock_result_1, mock_result_2])
        MockPipGraphManager.return_value = mock_manager

        # Обработка двух файлов с одинаковым контентом
        note1 = NotePayload(file_path="file1.md", content=content)
        result1 = await process_and_store_note(note1)

        note2 = NotePayload(file_path="file2.md", content=content)
        result2 = await process_and_store_note(note2)

        # Проверка: оба должны быть обработаны как NEW
        assert result1.status == "new"
        assert result2.status == "new"
        assert result1.episode_uuid != result2.episode_uuid

        # LLM должен быть вызван дважды
        assert mock_manager.process_note.call_count == 2


@pytest.mark.integration
async def test_metadata_persists_across_checks(temp_checknote_service, mock_pipgraph_result):
    """Тест: метаданные сохраняются между проверками"""
    note = NotePayload(
        file_path="test/persist.md",
        content="Persistent note"
    )

    with patch("app.services.note_processor._checknote_service", temp_checknote_service), \
         patch("app.services.note_processor.get_graphiti") as mock_get_graphiti, \
         patch("app.services.note_processor.PipGraphManager") as MockPipGraphManager:

        mock_graphiti = AsyncMock()
        mock_get_graphiti.return_value = mock_graphiti

        mock_manager = AsyncMock()
        mock_manager.process_note = AsyncMock(return_value=mock_pipgraph_result)
        MockPipGraphManager.return_value = mock_manager

        # Первая обработка
        result1 = await process_and_store_note(note)
        episode_uuid_1 = result1.episode_uuid

        # Проверка метаданных
        metadata = temp_checknote_service.get_metadata_by_path(
            file_path=note.file_path,
            group_id="default"
        )
        assert metadata["episode_uuid"] == episode_uuid_1

        # Вторая обработка (дубликат)
        result2 = await process_and_store_note(note)

        # Метаданные должны остаться теми же
        metadata2 = temp_checknote_service.get_metadata_by_path(
            file_path=note.file_path,
            group_id="default"
        )
        assert metadata2["episode_uuid"] == episode_uuid_1
        assert result2.episode_uuid == episode_uuid_1
