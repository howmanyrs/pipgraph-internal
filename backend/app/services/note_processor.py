from datetime import datetime, timezone
from app.models.note import NotePayload
from app.models.graph import GraphData, Node

from graphiti_core.nodes import EpisodeType
from app.services.llm_graphiti_client import get_graphiti
from app.services.pipgraph_manager import PipGraphManager

async def process_and_store_note(note: NotePayload) -> GraphData:
    """
    Основная бизнес-логика: обрабатывает заметку с использованием PipGraphManager.

    Использует PipGraphManager.process_note для пошаговой обработки и сохранения заметки в граф.
    В будущем здесь будут добавлены точки интервенции для взаимодействия с пользователем.
    """
    print(f"Processing content from '{note.file_path}' with PipGraphManager...")

    # Получить экземпляр Graphiti
    graphiti = await get_graphiti()

    # Создать менеджер для контролируемой обработки
    pipgraph = PipGraphManager(graphiti)

    # Обработать заметку через PipGraphManager
    result = await pipgraph.process_note(
        name=note.file_path,  # Используем путь к файлу как имя эпизода
        episode_body=note.content,  # Содержимое заметки
        source=EpisodeType.text,  # Тип источника - текст
        source_description=f"Obsidian note from {note.file_path}",
        reference_time=datetime.now(timezone.utc)
    )

    print(f"Successfully processed note '{note.file_path}': "
          f"{len(result.nodes)} nodes, {len(result.edges)} edges")

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