from datetime import datetime, timezone
from app.models.note import NotePayload
from app.models.graph import GraphData, Node

from graphiti_core.nodes import EpisodeType
from app.services.llm_graphiti_client import get_graphiti

async def process_and_store_note(note: NotePayload) -> GraphData:
    """
    Основная бизнес-логика: обрабатывает заметку с использованием Graphiti.

    Использует graphiti.add_episode для обработки и сохранения заметки в граф.
    """
    print(f"Processing content from '{note.file_path}' with Graphiti...")

    # Получить экземпляр Graphiti
    graphiti = await get_graphiti()

    # Добавить заметку как эпизод в Graphiti
    await graphiti.add_episode(
        name=note.file_path,  # Используем путь к файлу как имя эпизода
        episode_body=note.content,  # Содержимое заметки
        source=EpisodeType.text,  # Тип источника - текст
        source_description=f"Obsidian note from {note.file_path}",
        reference_time=datetime.now(timezone.utc)
    )

    print(f"Successfully added episode for '{note.file_path}'")

    # Заглушка для возврата GraphData (в будущем можно извлечь из Graphiti)
    graph_data = GraphData(
        nodes=[
            Node(id="note1", label="Note", properties={
                "path": note.file_path,
                "processed": True
            })
        ],
        relationships=[]
    )

    return graph_data