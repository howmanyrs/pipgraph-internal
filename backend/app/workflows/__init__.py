"""
LangGraph Workflows для PipGraph

Этот модуль содержит workflows для обработки заметок с PARA идентификацией.
"""

from app.workflows.state import (
    PARAWorkflowState,
    serialize_proposal,
    serialize_user_decision,
    deserialize_user_decision,
)
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
    check_error_status,
)

__all__ = [
    # State
    "PARAWorkflowState",
    "serialize_proposal",
    "serialize_user_decision",
    "deserialize_user_decision",
    # Nodes
    "identify_context_node",
    "apply_proposal_node",
    "wait_for_decision_node",
    "process_decision_node",
    "extract_content_node",
    "save_entities_node",
    # Conditions
    "check_suggestion_status",
    "should_continue_decisions",
    "check_error_status",
]
