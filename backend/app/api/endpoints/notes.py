from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError, BaseModel
from typing import Optional, Dict, Any
from app.models.note import NotePayload
from app.services import note_processor
from app.workflows.para_graph import (
    start_workflow_legacy as start_workflow,
    resume_workflow_legacy as resume_workflow,
    get_workflow_status,
)

router = APIRouter()


# ============================================================================
# Models for workflow REST API
# ============================================================================

class WorkflowStartRequest(BaseModel):
    """Request to start a new workflow"""
    file_path: str
    content: str


class WorkflowResumeRequest(BaseModel):
    """Request to resume a workflow with user answer"""
    thread_id: str
    answer: Dict[str, Any]


class WorkflowStatusResponse(BaseModel):
    """Response with workflow status"""
    thread_id: str
    status: str
    file_path: Optional[str] = None
    pending_question: Optional[Dict[str, Any]] = None
    episode_uuid: Optional[str] = None
    error: Optional[str] = None


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


# ============================================================================
# REST API endpoints for LangGraph workflow (for testing and debugging)
# ============================================================================

@router.post("/notes/workflow/start")
async def start_note_workflow(request: WorkflowStartRequest) -> WorkflowStatusResponse:
    """
    Start a new LangGraph workflow for note processing.

    This is an alternative to WebSocket for testing. Use this endpoint to:
    1. Start processing a note
    2. Get the thread_id for tracking
    3. Check if there's a pending question

    Example:
        POST /api/v1/notes/workflow/start
        {
            "file_path": "meetings/sync.md",
            "content": "# Meeting with John Smith..."
        }

        Response:
        {
            "thread_id": "note:meetings/sync.md",
            "status": "waiting_user",
            "pending_question": {...}
        }
    """
    try:
        thread_id = await start_workflow(
            file_path=request.file_path,
            content=request.content,
        )

        # Get current state
        state = await get_workflow_status(thread_id)

        return WorkflowStatusResponse(
            thread_id=thread_id,
            status=state.get("status", "unknown"),
            file_path=state.get("file_path"),
            pending_question=state.get("pending_question"),
            episode_uuid=state.get("episode_uuid"),
            error=state.get("error"),
        )

    except Exception as e:
        return WorkflowStatusResponse(
            thread_id=f"note:{request.file_path}",
            status="error",
            error=str(e),
        )


@router.post("/notes/workflow/resume")
async def resume_note_workflow(request: WorkflowResumeRequest) -> WorkflowStatusResponse:
    """
    Resume a workflow with user's answer.

    Example:
        POST /api/v1/notes/workflow/resume
        {
            "thread_id": "note:meetings/sync.md",
            "answer": {
                "question_id": "...",
                "action": "confirm"
            }
        }

        Response:
        {
            "thread_id": "note:meetings/sync.md",
            "status": "completed",
            "episode_uuid": "..."
        }
    """
    try:
        final_state = await resume_workflow(
            thread_id=request.thread_id,
            user_answer=request.answer,
        )

        return WorkflowStatusResponse(
            thread_id=request.thread_id,
            status=final_state.get("status", "unknown"),
            file_path=final_state.get("file_path"),
            pending_question=final_state.get("pending_question"),
            episode_uuid=final_state.get("episode_uuid"),
            error=final_state.get("error"),
        )

    except Exception as e:
        return WorkflowStatusResponse(
            thread_id=request.thread_id,
            status="error",
            error=str(e),
        )


@router.get("/notes/workflow/status/{thread_id}")
async def get_note_workflow_status(thread_id: str) -> WorkflowStatusResponse:
    """
    Get current status of a workflow.

    Example:
        GET /api/v1/notes/workflow/status/note:meetings/sync.md

        Response:
        {
            "thread_id": "note:meetings/sync.md",
            "status": "waiting_user",
            "pending_question": {...}
        }
    """
    try:
        state = await get_workflow_status(thread_id)

        if not state:
            return WorkflowStatusResponse(
                thread_id=thread_id,
                status="not_found",
                error="Workflow not found",
            )

        return WorkflowStatusResponse(
            thread_id=thread_id,
            status=state.get("status", "unknown"),
            file_path=state.get("file_path"),
            pending_question=state.get("pending_question"),
            episode_uuid=state.get("episode_uuid"),
            error=state.get("error"),
        )

    except Exception as e:
        return WorkflowStatusResponse(
            thread_id=thread_id,
            status="error",
            error=str(e),
        )