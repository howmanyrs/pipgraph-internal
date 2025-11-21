"""
Pydantic schemas for API requests and responses.
"""

from app.api.schemas.workflow import (
    WorkflowCreateRequest,
    WorkflowCreateResponse,
    WorkflowStatusResponse,
    WorkflowResumeRequest,
    WorkflowResumeResponse,
)

from app.api.schemas.suggestions import (
    SuggestionItem,
    SuggestionsResponse,
    DecisionRequest,
    DecisionResponse,
    InboxSuggestion,
    InboxResponse,
)

__all__ = [
    # Workflow schemas
    "WorkflowCreateRequest",
    "WorkflowCreateResponse",
    "WorkflowStatusResponse",
    "WorkflowResumeRequest",
    "WorkflowResumeResponse",
    # Suggestion schemas
    "SuggestionItem",
    "SuggestionsResponse",
    "DecisionRequest",
    "DecisionResponse",
    "InboxSuggestion",
    "InboxResponse",
]
