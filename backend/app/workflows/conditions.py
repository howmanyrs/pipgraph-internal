"""
Conditional Logic for PARA Workflow

Функции для определения следующего узла в workflow на основе состояния.
"""

import logging
from typing import Literal

from app.workflows.state import PARAWorkflowState
from app.crud import relationship_crud

logger = logging.getLogger(__name__)


def check_suggestion_status(
    state: PARAWorkflowState
) -> Literal["wait_for_decision_node", "extract_content_node"]:
    """
    Determine next node based on suggestion status.

    Проверяет состояние suggestions и context для определения
    следующего шага в workflow:
    - Если есть pending suggestions → wait_for_decision_node
    - Если есть подтвержденный контекст → extract_content_node
    - Если ничего нет → raise ValueError

    Args:
        state: Current workflow state

    Returns:
        Name of the next node to execute

    Raises:
        ValueError: If state is invalid (no suggestions and no context)
    """
    note_path = state["note_path"]

    logger.info(f"[check_suggestion_status] Checking status for: {note_path}")

    crud = relationship_crud.RelationshipCRUD()

    # Check for pending suggestions
    suggestions = crud.get_suggestions(note_path)

    if suggestions:
        logger.info(
            f"[check_suggestion_status] Found {len(suggestions)} pending suggestions "
            f"→ wait_for_decision_node"
        )
        return "wait_for_decision_node"

    # Check for confirmed context
    context = crud.get_episodic_para_context(note_path)

    if context:
        logger.info(
            f"[check_suggestion_status] Found context: {context['container_name']} "
            f"→ extract_content_node"
        )
        return "extract_content_node"

    # No suggestions and no context - proceed to extraction
    logger.warning(
        f"[check_suggestion_status] No suggestions or confirmed context for {note_path}, "
        f"proceeding directly to extract_content_node"
    )
    return "extract_content_node"


def should_continue_decisions(
    state: PARAWorkflowState
) -> Literal["wait_for_decision_node", "extract_content_node"]:
    """
    Synchronous version for simple state-based routing.

    Checks pending_suggestions in state without database query.
    Useful for quick routing after process_decision_node.

    Args:
        state: Current workflow state

    Returns:
        Name of the next node to execute
    """
    pending = state.get("pending_suggestions", [])

    if pending:
        logger.info(
            f"[should_continue_decisions] {len(pending)} pending "
            f"→ wait_for_decision_node"
        )
        return "wait_for_decision_node"

    logger.info("[should_continue_decisions] No pending → extract_content_node")
    return "extract_content_node"


def check_error_status(
    state: PARAWorkflowState
) -> Literal["continue", "error"]:
    """
    Check if workflow encountered an error.

    Used for error handling branch in workflow.

    Args:
        state: Current workflow state

    Returns:
        "error" if state has error, "continue" otherwise
    """
    if state.get("status") == "error":
        error = state.get("error", "Unknown error")
        logger.error(f"[check_error_status] Workflow error: {error}")
        return "error"

    return "continue"
