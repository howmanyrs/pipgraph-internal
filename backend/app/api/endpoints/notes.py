from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from app.models.note import NotePayload
from app.services import note_processor

router = APIRouter()


def _get_status_message(status: str) -> str:
    """Пользовательские сообщения для каждого статуса"""
    messages = {
        "new": "Note processed successfully",
        "duplicate": "Note already processed with identical content",
        "updated": "Note content has changed (update handling coming in Phase 2)"
    }
    return messages.get(status, "Unknown status")


@router.websocket("/ws/notes/process")
async def process_note_websocket(websocket: WebSocket):
    """
    Принимает WebSocket соединение для полного цикла обработки заметки.

    Возвращает статус обработки:
    - "new": заметка обработана впервые
    - "duplicate": повторная обработка идентичного контента (LLM не вызывался)
    - "updated": обнаружено изменение контента (Phase 2 - пока не обрабатывается)
    """
    await websocket.accept()
    try:
        data = await websocket.receive_json()

        try:
            payload = NotePayload(**data)
        except ValidationError as e:
            await websocket.send_json({"status": "error", "message": str(e)})
            await websocket.close()
            return

        # 1. Отправляем клиенту подтверждение о начале работы
        await websocket.send_json({
            "status": "processing",
            "message": f"Note '{payload.file_path}' received, starting processing..."
        })

        # 2. Вызываем бизнес-логику асинхронно (с проверкой дубликатов)
        result = await note_processor.process_and_store_note(payload)

        # 3. Отправляем финальный результат
        await websocket.send_json({
            "status": result.status,  # "new" | "duplicate" | "updated"
            "episode_uuid": result.episode_uuid,
            "content_hash": result.content_hash,
            "old_content_hash": result.old_content_hash,  # Только для "updated"
            "nodes_count": len(result.processing_details.nodes) if result.processing_details else 0,
            "edges_count": len(result.processing_details.edges) if result.processing_details else 0,
            "message": _get_status_message(result.status)
        })

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        try:
            await websocket.send_json({"status": "error", "message": f"An unexpected error occurred: {str(e)}"})
        except RuntimeError:
            # Connection already closed, cannot send error message
            pass
    finally:
        # Only close if connection is still open
        if websocket.client_state.name != "DISCONNECTED":
            await websocket.close()