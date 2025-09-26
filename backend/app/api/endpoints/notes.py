from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from app.models.note import NotePayload
from app.services import note_processor

router = APIRouter()

@router.websocket("/ws/notes/process")
async def process_note_websocket(websocket: WebSocket):
    """
    Принимает WebSocket соединение для полного цикла обработки заметки.
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

        # 2. Вызываем бизнес-логику (для прототипа - синхронно)
        # В будущем здесь может быть фоновая задача (Celery, BackgroundTasks)
        graph_data = note_processor.process_and_store_note(payload)

        # 3. Отправляем финальный результат
        await websocket.send_json({
            "status": "done",
            "data": graph_data.dict() # Сериализуем Pydantic модель в dict
        })

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        await websocket.send_json({"status": "error", "message": f"An unexpected error occurred: {str(e)}"})
    finally:
        await websocket.close()