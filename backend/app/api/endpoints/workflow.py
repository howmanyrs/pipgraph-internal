"""
Workflow management endpoints.

Provides REST API for managing LangGraph workflows:
- Start new workflow (stateless, based on file path)
- Get workflow status
- Resume workflow with user answer

Refactored to remove workflow_id and use file_path as the primary identifier.
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query

from app.api.schemas.workflow import (
    WorkflowCreateRequest,
    WorkflowCreateResponse,
    WorkflowStatusResponse,
    WorkflowResumeRequest,
    WorkflowResumeResponse,
)
from app.workflows import langgraph_service
from app.services.graphiti import get_graphiti, PipGraphManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.post("/start", response_model=WorkflowCreateResponse)
async def start_workflow(request: WorkflowCreateRequest) -> WorkflowCreateResponse:
    """
    Start or restart a LangGraph workflow for note processing.

    Uses the file path to generate a consistent thread_id.
    If a workflow already exists for this note, it will be restarted/updated.

    Example:
        POST /api/v1/workflow/start
        {
            "file_path": "meetings/sync.md",
            "content": "# Meeting with John Smith..."
        }

    Returns:
        WorkflowCreateResponse with status and file_path
    """
    try:
        # Generate thread_id consistently from file path
        thread_id = f"note:{request.file_path}"
        logger.info(f"[start_workflow] Processing note: {request.file_path} -> {thread_id}")

        # Get Graphiti instance and manager
        graphiti = await get_graphiti()
        manager = PipGraphManager(graphiti)

        # Create Episodic node using Service Layer
        # Note: Due to unique constraint on Episodic.name, duplicate creates will fail
        # TODO: Add get_or_create_episode() method to PipGraphManager for cleaner handling (для более чистой обработки дубликатов)
        ref_time = datetime.now(timezone.utc)

        try:
            episode = await manager.create_episode(
                name=request.file_path,
                content=request.content,
                source_description="Workflow processing",
                reference_time=ref_time,
                file_path=request.file_path,
            )
            logger.info(f"[start_workflow] Episode created: {episode.uuid}")

        except Exception as e:
            # Handle constraint violation - node already exists
            error_msg = str(e).lower()
            if "already exists" in error_msg or "constraint" in error_msg:
                logger.info(f"[start_workflow] Episode already exists: {request.file_path}")
                # Continue - the node exists, which is what we need
            else:
                # Re-raise unexpected errors
                logger.error(f"[start_workflow] Unexpected error creating episode: {e}")
                raise


        # # 2. Ensure mock container exists (required by mock_proposal_generator)
        # mock_project_id = "mock-project-alpha"
        # existing_project = container_crud.get_project(mock_project_id)
        # if not existing_project:
        #     logger.info(f"[start_workflow] Creating mock Project: {mock_project_id}")
        #     container_crud.create_project(
        #         project_id=mock_project_id,
        #         name="Mock Project Alpha",
        #         status="active"
        #     )        


        # Get compiled workflow app
        workflow_app = await langgraph_service.get_compiled_app()

        # Start workflow and get result state
        result = await langgraph_service.start_workflow(
            workflow=workflow_app,
            note_path=request.file_path,
            note_content=request.content,
            thread_id=thread_id,
        )

        # Use result directly - it contains current state after ainvoke()
        status = result.get("status", "processing")

        return WorkflowCreateResponse(
            file_path=request.file_path,
            status=status,
        )

    except Exception as e:
        logger.error(f"[start_workflow] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start workflow: {str(e)}")


@router.get("/status", response_model=WorkflowStatusResponse)
async def get_workflow_status(
    file_path: str = Query(..., description="Path to the note file (e.g., meetings/sync.md)")
) -> WorkflowStatusResponse:
    """
    Get current status of a workflow by file path.

    Example:
        GET /api/v1/workflow/status?file_path=meetings/sync.md

    Returns:
        WorkflowStatusResponse with status, pending_question, etc.
    """
    try:
        thread_id = f"note:{file_path}"
        state = await langgraph_service.get_workflow_status(thread_id)

        if not state:
            # Instead of 404, we might return a status indicating "not started" or 404.
            # Here we return 404 to be consistent with previous behavior.
            raise HTTPException(status_code=404, detail=f"No workflow state found for: {file_path}")

        # Determine status
        status = state.get("status", "unknown")

        return WorkflowStatusResponse(
            file_path=file_path,
            status=status,
            pending_question=state.get("pending_question"),
            episode_uuid=state.get("episode_uuid"),
            error=state.get("error"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[get_workflow_status] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resume", response_model=WorkflowResumeResponse)
async def resume_workflow(request: WorkflowResumeRequest) -> WorkflowResumeResponse:
    """
    Resume a workflow with user's answer.

    Example:
        POST /api/v1/workflow/resume
        {
            "file_path": "meetings/sync.md",
            "answer": {
                "suggestion_id": "...",
                "action": "confirm"
            }
        }

    Returns:
        WorkflowResumeResponse with updated status
    """
    try:
        thread_id = f"note:{request.file_path}"
        logger.info(f"[resume_workflow] Resuming workflow for: {request.file_path}")

        # Get compiled workflow app
        workflow_app = await langgraph_service.get_compiled_app()

        # Resume workflow with user's answer
        final_state = await langgraph_service.resume_workflow(
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
            file_path=request.file_path,
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
