from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel

from app.models.note import NotePayload

from graphiti_core.nodes import EpisodeType
from app.services.llm_graphiti_client import get_graphiti
from app.services.pipgraph_manager import PipGraphManager, AddEpisodeResults
from app.services.checknote import ChecknoteService


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
        print("   Skipping LLM processing (content hash matches)")
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
        print("   ⚠️  Update handling not implemented yet (Phase 2)")

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
    print("   Processing with PipGraphManager...")

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