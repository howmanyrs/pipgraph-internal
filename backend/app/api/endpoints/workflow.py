"""
Workflow management endpoints.

Provides REST API for managing LangGraph workflows:
- Start new workflow
- Get workflow status
- Resume workflow with user answer
"""

import logging
from typing import Dict
from fastapi import APIRouter, HTTPException

from app.api.schemas.workflow import (
    WorkflowCreateRequest,
    WorkflowCreateResponse,
    WorkflowStatusResponse,
    WorkflowResumeRequest,
    WorkflowResumeResponse,
    generate_workflow_id,
)
from app.workflows.para_graph import (
    start_workflow_legacy as start_langgraph_workflow,
    resume_workflow_legacy as resume_langgraph_workflow,
    get_workflow_status as get_langgraph_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflow", tags=["workflow"])

# In-memory mapping: workflow_id -> thread_id (note:path format)
# TODO: Move to Neo4j or Redis for persistence
_workflow_mapping: Dict[str, dict] = {}


def _get_thread_id(workflow_id: str) -> str:
    """Get LangGraph thread_id from workflow_id."""
    if workflow_id not in _workflow_mapping:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
    return _workflow_mapping[workflow_id]["thread_id"]


def _get_workflow_id_by_thread(thread_id: str) -> str | None:
    """Get workflow_id from thread_id (reverse lookup)."""
    for wf_id, data in _workflow_mapping.items():
        if data["thread_id"] == thread_id:
            return wf_id
    return None


@router.post("/start", response_model=WorkflowCreateResponse)
async def start_workflow(request: WorkflowCreateRequest) -> WorkflowCreateResponse:
    """
    Start a new LangGraph workflow for note processing.

    Creates a new workflow with a URL-safe workflow_id and begins processing
    the note content. The workflow may pause to ask for user input.

    Example:
        POST /api/v1/workflow/start
        {
            "file_path": "meetings/sync.md",
            "content": "# Meeting with John Smith..."
        }

    Returns:
        WorkflowCreateResponse with workflow_id, status, and file_path
    """
    try:
        # Generate new workflow_id
        workflow_id = generate_workflow_id()

        # Start LangGraph workflow
        thread_id = await start_langgraph_workflow(
            file_path=request.file_path,
            content=request.content,
        )

        # Store mapping
        _workflow_mapping[workflow_id] = {
            "thread_id": thread_id,
            "file_path": request.file_path,
        }

        # Get current state
        state = await get_langgraph_status(thread_id)

        # Determine status
        status = state.get("status", "processing")
        if state.get("pending_question"):
            status = "waiting_user"

        logger.info(f"[start_workflow] Created workflow {workflow_id} -> {thread_id}")

        return WorkflowCreateResponse(
            workflow_id=workflow_id,
            status=status,
            file_path=request.file_path,
        )

    except Exception as e:
        logger.error(f"[start_workflow] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start workflow: {str(e)}")


@router.get("/{workflow_id}/status", response_model=WorkflowStatusResponse)
async def get_workflow_status(workflow_id: str) -> WorkflowStatusResponse:
    """
    Get current status of a workflow.

    Example:
        GET /api/v1/workflow/wf_a1b2c3d4/status

    Returns:
        WorkflowStatusResponse with status, pending_question, etc.
    """
    try:
        thread_id = _get_thread_id(workflow_id)
        state = await get_langgraph_status(thread_id)

        if not state:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

        # Determine status
        status = state.get("status", "unknown")
        if state.get("pending_question") and status != "completed":
            status = "waiting_user"

        return WorkflowStatusResponse(
            workflow_id=workflow_id,
            status=status,
            file_path=state.get("file_path"),
            pending_question=state.get("pending_question"),
            episode_uuid=state.get("episode_uuid"),
            error=state.get("error"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[get_workflow_status] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workflow_id}/resume", response_model=WorkflowResumeResponse)
async def resume_workflow(workflow_id: str, request: WorkflowResumeRequest) -> WorkflowResumeResponse:
    """
    Resume a workflow with user's answer.

    Example:
        POST /api/v1/workflow/wf_a1b2c3d4/resume
        {
            "answer": {
                "question_id": "...",
                "action": "confirm"
            }
        }

    Returns:
        WorkflowResumeResponse with updated status
    """
    try:
        thread_id = _get_thread_id(workflow_id)

        # Resume workflow
        final_state = await resume_langgraph_workflow(
            thread_id=thread_id,
            user_answer=request.answer,
        )

        # Determine status
        status = final_state.get("status", "unknown")
        next_question = final_state.get("pending_question")
        if next_question and status != "completed":
            status = "waiting_user"

        # Get cascade results if available
        cascade_applied = final_state.get("cascade_result", {}).get("applied", [])

        return WorkflowResumeResponse(
            workflow_id=workflow_id,
            status=status,
            next_question=next_question,
            episode_uuid=final_state.get("episode_uuid"),
            cascade_applied=cascade_applied,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[resume_workflow] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Export mapping access for suggestions endpoint
def get_workflow_mapping() -> Dict[str, dict]:
    """Get the workflow mapping for use by other modules."""
    return _workflow_mapping
