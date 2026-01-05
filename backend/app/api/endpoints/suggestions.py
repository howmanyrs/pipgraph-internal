"""
Suggestions management endpoints.

Provides REST API for managing workflow suggestions:
- Get suggestions for a specific note (by file_path)
- Submit decision on a suggestion (auto-resolves thread_id)
- Get all pending suggestions (inbox)

Refactored to be stateless and use file_path/note_path as identifiers.
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query

from app.api.schemas.suggestions import (
    SuggestionItem,
    SuggestionsResponse,
    DecisionRequest,
    DecisionResponse,
    InboxSuggestion,
    InboxResponse,
    InboxCountResponse,
)
from app.workflows import langgraph_service
from app.crud import relationship_crud

logger = logging.getLogger(__name__)

router = APIRouter(tags=["suggestions"])


@router.get("/suggestions", response_model=SuggestionsResponse)
async def get_suggestions(
    file_path: str = Query(..., description="Path to the note file (e.g., meetings/sync.md)")
) -> SuggestionsResponse:
    """
    Get all suggestions for a specific note.

    Returns the pending suggestion(s) for the specified note,
    queried from Neo4j :SUGGESTS relationships.

    Example:
        GET /api/v1/suggestions?file_path=meetings/sync.md

    Returns:
        SuggestionsResponse with list of suggestions
    """
    try:
        thread_id = f"note:{file_path}"
        
        # Check if workflow exists/is active for this note
        state = await langgraph_service.get_workflow_status(thread_id)
        
        # Even if state is missing (expired), we might still have suggestions in DB.
        # However, strictly speaking, suggestions are tied to an active workflow interrupt.
        # We proceed to check DB if we have a valid file_path.

        suggestions = []
        
        # Query Neo4j for full suggestion data
        crud = relationship_crud.RelationshipCRUD()
        suggestions_data = crud.get_suggestions(file_path)

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

        if suggestions:
            logger.info(f"[get_suggestions] Found {len(suggestions)} suggestions for {file_path}")

        return SuggestionsResponse(
            file_path=file_path,
            suggestions=suggestions,
        )

    except Exception as e:
        logger.error(f"[get_suggestions] Error: {e}", exc_info=True)
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
        crud = relationship_crud.RelationshipCRUD()
        suggestion = crud.get_suggestion_by_id(suggestion_id)

        if not suggestion:
            raise HTTPException(status_code=404, detail=f"Suggestion {suggestion_id} not found")

        note_path = suggestion["episodic_path"]
        
        # Derive thread_id from note_path
        thread_id = f"note:{note_path}"

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
            "suggestion_id": suggestion_id,
            "action": workflow_action,
        }

        # Add action-specific fields
        if request.action == "create_custom" and request.custom_container_name:
            answer["custom_container_name"] = request.custom_container_name
            # Default to Project if container_type is missing, or infer from somewhere else
            answer["custom_container_type"] = suggestion.get("container_type", "Project")

        # Resume workflow with decision
        workflow_app = await langgraph_service.get_compiled_app()
        final_state = await langgraph_service.resume_workflow(
            workflow=workflow_app,
            user_decision=answer,
            thread_id=thread_id
        )

        # Get cascade results (with None check)
        if final_state is None:
            # This might happen if the workflow state was lost or thread_id is wrong
            raise ValueError(f"Workflow resume returned None for thread_id={thread_id}")
            
        cascade_applied = (final_state.get("cascade_result") or {}).get("applied", [])

        return DecisionResponse(
            success=True,
            file_path=note_path,
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
        crud = relationship_crud.RelationshipCRUD()
        all_suggestions = crud.get_all_pending_suggestions()

        suggestions = []

        for sugg in all_suggestions:
            # Use current time as created_at (TODO: add timestamp to Neo4j :SUGGESTS)
            created_at = datetime.now(timezone.utc)

            suggestion = InboxSuggestion(
                suggestion_id=sugg["suggestion_id"],
                note_path=sugg["note_path"],  # Using note_path directly
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
        crud = relationship_crud.RelationshipCRUD()
        all_suggestions = crud.get_all_pending_suggestions()
        count = len(all_suggestions)

        return InboxCountResponse(count=count)

    except Exception as e:
        logger.error(f"[get_inbox_count] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))