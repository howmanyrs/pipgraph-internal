from app.models.note import NotePayload
from app.models.graph import GraphData, Node, Relationship
from app.crud import graph_crud

def process_and_store_note(note: NotePayload) -> GraphData:
    """
    Основная бизнес-логика: обрабатывает заметку, извлекает граф и сохраняет его.
    """
    # Шаг 1: Вызов LLM для извлечения сущностей (заглушка)
    # В реальной реализации здесь будет вызов к Разработчику 3
    print(f"Processing content from '{note.file_path}'...")
    graph_data = GraphData(
        nodes=[
            Node(id="person1", label="Person", properties={"name": "Иван"}),
            Node(id="company1", label="Company", properties={"name": "ООО 'Рога и копыта'"})
        ],
        relationships=[
            Relationship(source_id="person1", target_id="company1", type="WORKS_AT")
        ]
    )

    # Шаг 2: Сохранение извлеченных данных в БД через CRUD слой
    graph_crud.save_graph_data(graph_data)

    return graph_data