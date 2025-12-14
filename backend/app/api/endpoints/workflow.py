"""
Workflow management endpoints.

Provides REST API for managing LangGraph workflows:
- Start new workflow
- Get workflow status
- Resume workflow with user answer
"""

import logging
from typing import Dict
from datetime import datetime, timezone
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
    start_workflow as start_langgraph_workflow,
    resume_workflow as resume_langgraph_workflow,
    get_workflow_status as get_langgraph_status,
    get_compiled_app,
)
from app.crud.episodic_crud import EpisodicCRUD
from app.crud.para_crud import PARAContainerCRUD

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

        # Ensure required nodes exist in Neo4j before starting workflow
        episodic_crud = EpisodicCRUD()
        para_crud = PARAContainerCRUD()

        # 1. Create Episodic node if it doesn't exist
        existing_episodic = episodic_crud.get_episodic(request.file_path)
        if not existing_episodic:
            logger.info(f"[start_workflow] Creating Episodic node: {request.file_path}")
            episodic_crud.create_episodic(
                path=request.file_path,
                content=request.content,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
        else:
            logger.info(f"[start_workflow] Episodic node already exists: {request.file_path}")

        # 2. Ensure mock container exists (required by mock_proposal_generator)
        mock_project_id = "mock-project-alpha"
        existing_project = para_crud.get_project(mock_project_id)
        if not existing_project:
            logger.info(f"[start_workflow] Creating mock Project: {mock_project_id}")
            para_crud.create_project(
                project_id=mock_project_id,
                name="Mock Project Alpha",
                status="active"
            )
        else:
            logger.info(f"[start_workflow] Mock Project already exists: {mock_project_id}")

        # Generate thread_id
        thread_id = f"note:{request.file_path}"

        # Get compiled workflow app
        workflow_app = await get_compiled_app()

        # Start workflow and get result state
        result = await start_langgraph_workflow(
            workflow=workflow_app,
            note_path=request.file_path,
            note_content=request.content,
            thread_id=thread_id,
        )

        # Store mapping
        _workflow_mapping[workflow_id] = {
            "thread_id": thread_id,
            "file_path": request.file_path,
        }

        # Use result directly - it contains current state after ainvoke()
        status = result.get("status", "processing")

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

        # Get compiled workflow app
        workflow_app = await get_compiled_app()

        # Resume workflow with user's answer
        final_state = await resume_langgraph_workflow(
            workflow=workflow_app,
            user_decision=request.answer,
            thread_id=thread_id,
        )

        # Extract status and pending question
        status = final_state.get("status", "completed")
        next_question = final_state.get("pending_question")

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
