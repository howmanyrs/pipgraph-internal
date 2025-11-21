"""
Suggestions management endpoints.

Provides REST API for managing workflow suggestions:
- Get suggestions for a workflow
- Submit decision on a suggestion
- Get all pending suggestions (inbox)
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException

from app.api.schemas.suggestions import (
    SuggestionItem,
    SuggestionsResponse,
    DecisionRequest,
    DecisionResponse,
    InboxSuggestion,
    InboxResponse,
    InboxCountResponse,
)
from app.services.note_workflow import get_workflow_status as get_langgraph_status

logger = logging.getLogger(__name__)

router = APIRouter(tags=["suggestions"])

# Import workflow mapping from workflow endpoint
# This creates a dependency - in production, use shared storage
from app.api.endpoints.workflow import get_workflow_mapping, _get_thread_id


@router.get("/workflow/{workflow_id}/suggestions", response_model=SuggestionsResponse)
async def get_workflow_suggestions(workflow_id: str) -> SuggestionsResponse:
    """
    Get all suggestions for a workflow.

    Returns the pending suggestion(s) for the specified workflow,
    including alternatives for each suggestion.

    Example:
        GET /api/v1/workflow/wf_a1b2c3d4/suggestions

    Returns:
        SuggestionsResponse with list of suggestions
    """
    try:
        thread_id = _get_thread_id(workflow_id)
        state = await get_langgraph_status(thread_id)

        if not state:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

        suggestions = []

        # Get pending question from state
        pending_question = state.get("pending_question")
        if pending_question:
            # Convert workflow question to suggestion format
            suggestion = SuggestionItem(
                suggestion_id=pending_question.get("question_id", "unknown"),
                suggestion_type=pending_question.get("question_type", "entity_confirmation"),
                container_type=pending_question.get("entity_type", "Unknown"),
                container_name=pending_question.get("entity_name", "Unknown"),
                confidence=pending_question.get("confidence", 0.0),
                alternatives=pending_question.get("alternatives", []),
            )
            suggestions.append(suggestion)

        return SuggestionsResponse(
            workflow_id=workflow_id,
            suggestions=suggestions,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[get_workflow_suggestions] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/suggestion/{suggestion_id}/decision", response_model=DecisionResponse)
async def submit_decision(suggestion_id: str, request: DecisionRequest) -> DecisionResponse:
    """
    Submit a decision on a suggestion.

    Supported actions:
    - confirm: Accept the suggestion
    - dismiss: Reject the suggestion
    - modify: Change the suggested value
    - create_custom: Create a new container

    Example:
        POST /api/v1/suggestion/sug_abc123/decision
        {
            "action": "confirm"
        }

    Returns:
        DecisionResponse with result and cascade information
    """
    try:
        # Find workflow by suggestion_id
        workflow_id = None
        thread_id = None
        mapping = get_workflow_mapping()

        for wf_id, data in mapping.items():
            tid = data["thread_id"]
            state = await get_langgraph_status(tid)
            if state:
                pending = state.get("pending_question", {})
                if pending.get("question_id") == suggestion_id:
                    workflow_id = wf_id
                    thread_id = tid
                    break

        if not workflow_id:
            raise HTTPException(status_code=404, detail=f"Suggestion {suggestion_id} not found")

        # Validate action
        valid_actions = ["confirm", "dismiss", "modify", "create_custom"]
        if request.action not in valid_actions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid action: {request.action}. Must be one of: {valid_actions}"
            )

        # Build answer for workflow
        answer = {
            "question_id": suggestion_id,
            "action": request.action,
        }

        if request.action == "modify" and request.modified_value:
            answer["modified_value"] = request.modified_value
        elif request.action == "create_custom" and request.custom_container_name:
            answer["custom_container_name"] = request.custom_container_name

        # Resume workflow with decision
        from app.services.note_workflow import resume_workflow as resume_langgraph_workflow
        final_state = await resume_langgraph_workflow(thread_id, answer)

        # Get cascade results
        cascade_applied = final_state.get("cascade_result", {}).get("applied", [])

        return DecisionResponse(
            success=True,
            workflow_id=workflow_id,
            suggestion_id=suggestion_id,
            action=request.action,
            cascade_applied=cascade_applied,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[submit_decision] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inbox/suggestions", response_model=InboxResponse)
async def get_inbox_suggestions() -> InboxResponse:
    """
    Get all pending suggestions across all workflows.

    Returns a list of all suggestions awaiting user decision,
    sorted by creation time (newest first).

    Example:
        GET /api/v1/inbox/suggestions

    Returns:
        InboxResponse with list of pending suggestions
    """
    try:
        suggestions = []
        mapping = get_workflow_mapping()

        for workflow_id, data in mapping.items():
            thread_id = data["thread_id"]
            file_path = data["file_path"]

            state = await get_langgraph_status(thread_id)
            if not state:
                continue

            pending_question = state.get("pending_question")
            if pending_question and state.get("status") != "completed":
                # Get created_at from state or use current time
                created_at_str = state.get("processing_started_at")
                if created_at_str:
                    created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                else:
                    created_at = datetime.now(timezone.utc)

                suggestion = InboxSuggestion(
                    suggestion_id=pending_question.get("question_id", "unknown"),
                    workflow_id=workflow_id,
                    note_path=file_path,
                    suggestion_type=pending_question.get("question_type", "entity_confirmation"),
                    container_name=pending_question.get("entity_name", "Unknown"),
                    confidence=pending_question.get("confidence", 0.0),
                    created_at=created_at,
                )
                suggestions.append(suggestion)

        # Sort by created_at descending (newest first)
        suggestions.sort(key=lambda x: x.created_at, reverse=True)

        return InboxResponse(
            suggestions=suggestions,
            total_count=len(suggestions),
        )

    except Exception as e:
        logger.error(f"[get_inbox_suggestions] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inbox/count", response_model=InboxCountResponse)
async def get_inbox_count() -> InboxCountResponse:
    """
    Get count of pending suggestions.

    Useful for displaying a badge in the UI.

    Example:
        GET /api/v1/inbox/count

    Returns:
        InboxCountResponse with count
    """
    try:
        count = 0
        mapping = get_workflow_mapping()

        for workflow_id, data in mapping.items():
            thread_id = data["thread_id"]
            state = await get_langgraph_status(thread_id)

            if state and state.get("pending_question") and state.get("status") != "completed":
                count += 1

        return InboxCountResponse(count=count)

    except Exception as e:
        logger.error(f"[get_inbox_count] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
