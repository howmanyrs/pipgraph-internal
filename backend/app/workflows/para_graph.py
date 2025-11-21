"""
PARA Workflow Graph Assembly

Сборка StateGraph для обработки заметок с PARA идентификацией.
Связывает все nodes из para_workflow.py в единый граф с условными переходами.

Архитектура:
    identify_context → apply_proposal → [check_suggestion_status]
                                              ↓
                                    wait_for_decision (INTERRUPT)
                                              ↓
                                    process_decision
                                              ↓
                                    [should_continue_decisions]
                                              ↓
                                    extract_content → save_entities → END
"""

import logging
from typing import Optional

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.workflows.state import PARAWorkflowState
from app.workflows.para_workflow import (
    identify_context_node,
    apply_proposal_node,
    wait_for_decision_node,
    process_decision_node,
    extract_content_node,
    save_entities_node,
)
from app.workflows.conditions import (
    check_suggestion_status,
    should_continue_decisions,
)

logger = logging.getLogger(__name__)


def create_para_workflow(checkpointer=None):
    """
    Create and compile PARA workflow graph.

    Args:
        checkpointer: Optional checkpointer for state persistence.
                     If None, MemorySaver is used (in-memory storage).

    Returns:
        Compiled workflow graph ready for execution.

    Usage:
        # Basic usage with in-memory checkpointer
        workflow = create_para_workflow()

        # With custom checkpointer for persistence
        from langgraph.checkpoint.sqlite import SqliteSaver
        checkpointer = SqliteSaver.from_conn_string("workflow.db")
        workflow = create_para_workflow(checkpointer)
    """
    logger.info("[create_para_workflow] Building PARA workflow graph")

    # Create StateGraph
    workflow = StateGraph(PARAWorkflowState)

    # ========================================================================
    # Add Nodes
    # ========================================================================

    workflow.add_node("identify_context", identify_context_node)
    workflow.add_node("apply_proposal", apply_proposal_node)
    workflow.add_node("wait_for_decision", wait_for_decision_node)
    workflow.add_node("process_decision", process_decision_node)
    workflow.add_node("extract_content", extract_content_node)
    workflow.add_node("save_entities", save_entities_node)

    # ========================================================================
    # Set Entry Point
    # ========================================================================

    workflow.set_entry_point("identify_context")

    # ========================================================================
    # Add Edges
    # ========================================================================

    # Linear edge: identify_context → apply_proposal
    workflow.add_edge("identify_context", "apply_proposal")

    # Conditional edge: apply_proposal → (wait_for_decision OR extract_content)
    workflow.add_conditional_edges(
        "apply_proposal",
        check_suggestion_status,
        {
            "wait_for_decision_node": "wait_for_decision",
            "extract_content_node": "extract_content",
        }
    )

    # Linear edge: wait_for_decision → process_decision
    workflow.add_edge("wait_for_decision", "process_decision")

    # Conditional edge: process_decision → (wait_for_decision OR extract_content)
    workflow.add_conditional_edges(
        "process_decision",
        should_continue_decisions,
        {
            "wait_for_decision_node": "wait_for_decision",
            "extract_content_node": "extract_content",
        }
    )

    # Linear edge: extract_content → save_entities
    workflow.add_edge("extract_content", "save_entities")

    # Terminal edge: save_entities → END
    workflow.add_edge("save_entities", END)

    # ========================================================================
    # Compile with Checkpointer
    # ========================================================================

    if checkpointer is None:
        checkpointer = MemorySaver()
        logger.info("[create_para_workflow] Using in-memory checkpointer")
    else:
        logger.info(f"[create_para_workflow] Using provided checkpointer: {type(checkpointer)}")

    compiled = workflow.compile(checkpointer=checkpointer)

    logger.info("[create_para_workflow] Workflow compiled successfully")

    return compiled


# ============================================================================
# Workflow Execution Helpers
# ============================================================================

async def start_workflow(
    workflow,
    note_path: str,
    note_content: str,
    thread_id: str,
) -> dict:
    """
    Start PARA workflow for a note.

    Args:
        workflow: Compiled workflow graph
        note_path: Path to the note file (Episode.name)
        note_content: Note content for processing
        thread_id: Unique thread ID for state persistence

    Returns:
        dict with workflow state after execution/interrupt

    Example:
        workflow = create_para_workflow()
        result = await start_workflow(
            workflow,
            note_path="Notes/test.md",
            note_content="Test note about project",
            thread_id="thread-123"
        )

        if result["status"] == "waiting_user":
            # Handle interrupt - get suggestions from result
            suggestions = result.get("pending_suggestions", [])
    """
    from datetime import datetime, timezone

    logger.info(f"[start_workflow] Starting workflow for: {note_path}")

    initial_state = {
        "note_path": note_path,
        "note_content": note_content,
        "processing_started_at": datetime.now(timezone.utc).isoformat(),
        "status": "processing",
        "pending_suggestions": [],
        "extracted_entities": [],
    }

    config = {"configurable": {"thread_id": thread_id}}

    try:
        result = await workflow.ainvoke(initial_state, config)
        logger.info(f"[start_workflow] Workflow completed with status: {result.get('status')}")
        return result

    except Exception as e:
        logger.error(f"[start_workflow] Workflow error: {e}", exc_info=True)
        raise


async def resume_workflow(
    workflow,
    user_decision: dict,
    thread_id: str,
) -> dict:
    """
    Resume PARA workflow after user decision.

    Args:
        workflow: Compiled workflow graph
        user_decision: User decision payload (dict with action, suggestion_id, etc.)
        thread_id: Thread ID used when starting workflow

    Returns:
        dict with workflow state after execution/interrupt

    Example:
        # User confirmed link suggestion
        decision = {
            "suggestion_id": "uuid-123",
            "action": "confirm"
        }
        result = await resume_workflow(workflow, decision, thread_id="thread-123")

        if result["status"] == "waiting_user":
            # More suggestions to process
            pass
        elif result["status"] == "completed":
            # Workflow finished
            entities = result.get("extracted_entities", [])
    """
    from app.workflows.state import serialize_user_decision
    from app.models.proposal import UserDecisionPayload

    logger.info(f"[resume_workflow] Resuming with decision: {user_decision.get('action')}")

    config = {"configurable": {"thread_id": thread_id}}

    # Convert dict to UserDecisionPayload if needed, then serialize
    if isinstance(user_decision, dict):
        decision_payload = UserDecisionPayload(
            suggestion_id=user_decision["suggestion_id"],
            action=user_decision["action"],
            selected_container_id=user_decision.get("selected_container_id"),
            custom_container_type=user_decision.get("custom_container_type"),
            custom_container_name=user_decision.get("custom_container_name"),
        )
        serialized_decision = serialize_user_decision(decision_payload)
    else:
        serialized_decision = serialize_user_decision(user_decision)

    try:
        # Resume with Command containing the user decision
        from langgraph.types import Command

        result = await workflow.ainvoke(
            Command(resume=serialized_decision),
            config
        )

        logger.info(f"[resume_workflow] Workflow resumed with status: {result.get('status')}")
        return result

    except Exception as e:
        logger.error(f"[resume_workflow] Resume error: {e}", exc_info=True)
        raise


def get_workflow_state(workflow, thread_id: str) -> Optional[dict]:
    """
    Get current workflow state for a thread.

    Args:
        workflow: Compiled workflow graph
        thread_id: Thread ID to query

    Returns:
        Current state dict or None if not found
    """
    config = {"configurable": {"thread_id": thread_id}}

    try:
        state = workflow.get_state(config)
        if state and state.values:
            return dict(state.values)
        return None

    except Exception as e:
        logger.error(f"[get_workflow_state] Error: {e}")
        return None


# ============================================================================
# Module-level workflow instance (optional convenience)
# ============================================================================

# Pre-built workflow with default checkpointer
# Usage: from app.workflows.para_graph import default_workflow
_default_workflow = None


def get_default_workflow():
    """
    Get or create default workflow instance with in-memory checkpointer.

    Note: For production, use create_para_workflow() with persistent checkpointer.

    Returns:
        Compiled workflow graph
    """
    global _default_workflow

    if _default_workflow is None:
        _default_workflow = create_para_workflow()

    return _default_workflow
