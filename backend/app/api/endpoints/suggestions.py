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
from app.workflows.para_graph import get_workflow_status as get_langgraph_status

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
    queried from Neo4j :SUGGESTS relationships.

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

        # Get note_path and pending_suggestions from workflow state
        note_path = state.get("note_path")
        pending_suggestions = state.get("pending_suggestions", [])

        if note_path and pending_suggestions:
            # Query Neo4j for full suggestion data
            from app.crud.relationship_crud import RelationshipCRUD
            relationship_crud = RelationshipCRUD()
            suggestions_data = relationship_crud.get_suggestions(note_path)

            # Convert to SuggestionItem format
            for sugg in suggestions_data:
                suggestion = SuggestionItem(
                    suggestion_id=sugg["suggestion_id"],
                    suggestion_type=sugg["suggestion_type"],
                    container_type=sugg["container_type"],
                    container_name=sugg["container_name"],
                    container_id=sugg["container_id"],
                    confidence=sugg["confidence"],
                    reasoning=sugg["reasoning"],
                    target_field=sugg.get("target_field"),
                    suggested_value=sugg.get("suggested_value"),
                    alternatives=[],  # TODO: Add alternatives support if needed
                )
                suggestions.append(suggestion)

            logger.info(f"[get_workflow_suggestions] Found {len(suggestions)} suggestions for {workflow_id}")

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
        # Get suggestion from Neo4j to find associated note_path
        from app.crud.relationship_crud import RelationshipCRUD
        relationship_crud = RelationshipCRUD()
        suggestion = relationship_crud.get_suggestion_by_id(suggestion_id)

        if not suggestion:
            raise HTTPException(status_code=404, detail=f"Suggestion {suggestion_id} not found")

        note_path = suggestion["episodic_path"]

        # Find workflow by note_path
        workflow_id = None
        thread_id = None
        mapping = get_workflow_mapping()

        for wf_id, data in mapping.items():
            if data["file_path"] == note_path:
                workflow_id = wf_id
                thread_id = data["thread_id"]
                break

        if not workflow_id:
            raise HTTPException(status_code=404, detail=f"No active workflow found for note: {note_path}")

        # Validate action
        valid_actions = ["confirm", "dismiss", "modify", "create_custom"]
        if request.action not in valid_actions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid action: {request.action}. Must be one of: {valid_actions}"
            )

        # Map REST API actions to workflow actions
        workflow_action = request.action
        if request.action == "modify":
            # Modify is not directly supported by workflow - treat as dismiss for now
            # TODO: Implement proper modify support for property_update suggestions
            workflow_action = "dismiss"
            logger.warning(f"[submit_decision] 'modify' action not supported, treating as dismiss")

        # Build answer for workflow (UserDecisionPayload format)
        answer = {
            "suggestion_id": suggestion_id,  # Changed from question_id
            "action": workflow_action,
        }

        # Add action-specific fields
        if request.action == "create_custom" and request.custom_container_name:
            answer["custom_container_name"] = request.custom_container_name
            # Determine container type from suggestion
            logger.debug(f"[submit_decision] suggestion before .get('container_type'): {suggestion}")
            answer["custom_container_type"] = suggestion.get("container_type", "Project")

        # Resume workflow with decision
        from app.workflows.para_graph import resume_workflow, get_compiled_app
        workflow_app = await get_compiled_app()
        final_state = await resume_workflow(
            workflow=workflow_app,
            user_decision=answer,
            thread_id=thread_id
        )

        # Get cascade results (with None check)
        if final_state is None:
            raise ValueError(f"Workflow resume returned None for thread_id={thread_id}")
        logger.debug(f"[submit_decision] final_state before .get('cascade_result'): {final_state}")
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

    Returns a list of all suggestions awaiting user decision from Neo4j,
    sorted by confidence (highest first).

    Example:
        GET /api/v1/inbox/suggestions

    Returns:
        InboxResponse with list of pending suggestions
    """
    try:
        # Query all pending suggestions from Neo4j
        from app.crud.relationship_crud import RelationshipCRUD
        relationship_crud = RelationshipCRUD()
        all_suggestions = relationship_crud.get_all_pending_suggestions()

        # Map to get workflow_id for each suggestion
        mapping = get_workflow_mapping()
        suggestions = []

        for sugg in all_suggestions:
            # Try to find workflow_id by note_path
            workflow_id = None
            for wf_id, data in mapping.items():
                if data["file_path"] == sugg["note_path"]:
                    workflow_id = wf_id
                    break

            # Use current time as created_at (TODO: add timestamp to Neo4j :SUGGESTS)
            created_at = datetime.now(timezone.utc)

            suggestion = InboxSuggestion(
                suggestion_id=sugg["suggestion_id"],
                workflow_id=workflow_id if workflow_id else "unknown",
                note_path=sugg["note_path"],
                suggestion_type=sugg["suggestion_type"],
                container_name=sugg["container_name"],
                confidence=sugg["confidence"],
                created_at=created_at,
            )
            suggestions.append(suggestion)

        # Sort by confidence descending (highest first)
        suggestions.sort(key=lambda x: x.confidence, reverse=True)

        logger.info(f"[get_inbox_suggestions] Found {len(suggestions)} pending suggestions")

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

    Queries Neo4j for total number of :SUGGESTS relationships.
    Useful for displaying a badge in the UI.

    Example:
        GET /api/v1/inbox/count

    Returns:
        InboxCountResponse with count
    """
    try:
        # Query count directly from Neo4j
        from app.crud.relationship_crud import RelationshipCRUD
        relationship_crud = RelationshipCRUD()
        all_suggestions = relationship_crud.get_all_pending_suggestions()
        count = len(all_suggestions)

        logger.info(f"[get_inbox_count] Found {count} pending suggestions")

        return InboxCountResponse(count=count)

    except Exception as e:
        logger.error(f"[get_inbox_count] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
