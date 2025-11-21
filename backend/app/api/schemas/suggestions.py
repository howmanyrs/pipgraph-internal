"""
Pydantic schemas for suggestions endpoints.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class SuggestionItem(BaseModel):
    """Single suggestion item."""

    suggestion_id: str = Field(..., description="Unique suggestion identifier")
    suggestion_type: str = Field(..., description="Type: para_link or property_update")
    container_type: str = Field(..., description="PARA type: Project, Area, Resource, Archive")
    container_name: str = Field(..., description="Name of the suggested container")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0-1")
    alternatives: List[dict] = Field(default_factory=list, description="Alternative suggestions")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "suggestion_id": "sug_abc123",
                    "suggestion_type": "para_link",
                    "container_type": "Project",
                    "container_name": "Project Alpha",
                    "confidence": 0.92,
                    "alternatives": [
                        {"container_name": "Project Beta", "confidence": 0.75}
                    ]
                }
            ]
        }
    }


class SuggestionsResponse(BaseModel):
    """Response with workflow suggestions."""

    workflow_id: str = Field(..., description="Workflow identifier")
    suggestions: List[SuggestionItem] = Field(default_factory=list, description="List of suggestions")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "workflow_id": "wf_a1b2c3d4",
                    "suggestions": [
                        {
                            "suggestion_id": "sug_abc123",
                            "suggestion_type": "para_link",
                            "container_type": "Project",
                            "container_name": "Project Alpha",
                            "confidence": 0.92,
                            "alternatives": []
                        }
                    ]
                }
            ]
        }
    }


class DecisionRequest(BaseModel):
    """Request to submit a decision on a suggestion."""

    action: str = Field(..., description="Action: confirm, dismiss, modify, create_custom")
    modified_value: Optional[str] = Field(None, description="Modified value for 'modify' action")
    custom_container_name: Optional[str] = Field(None, description="Name for 'create_custom' action")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "action": "confirm"
                },
                {
                    "action": "modify",
                    "modified_value": "Project Beta"
                },
                {
                    "action": "create_custom",
                    "custom_container_name": "New Project"
                }
            ]
        }
    }


class DecisionResponse(BaseModel):
    """Response after submitting a decision."""

    success: bool = Field(..., description="Whether the decision was processed successfully")
    workflow_id: str = Field(..., description="Associated workflow identifier")
    suggestion_id: str = Field(..., description="Processed suggestion identifier")
    action: str = Field(..., description="Action that was performed")
    cascade_applied: List[dict] = Field(default_factory=list, description="Auto-resolved suggestions via cascade")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "workflow_id": "wf_a1b2c3d4",
                    "suggestion_id": "sug_abc123",
                    "action": "confirm",
                    "cascade_applied": [
                        {
                            "suggestion_id": "sug_def456",
                            "note_path": "meetings/other.md",
                            "confidence": 0.88
                        }
                    ]
                }
            ]
        }
    }


class InboxSuggestion(BaseModel):
    """Suggestion item in inbox view."""

    suggestion_id: str = Field(..., description="Unique suggestion identifier")
    workflow_id: str = Field(..., description="Associated workflow identifier")
    note_path: str = Field(..., description="Path to the source note")
    suggestion_type: str = Field(..., description="Type: para_link or property_update")
    container_name: str = Field(..., description="Suggested container name")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    created_at: datetime = Field(..., description="When the suggestion was created")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "suggestion_id": "sug_abc123",
                    "workflow_id": "wf_a1b2c3d4",
                    "note_path": "meetings/sync.md",
                    "suggestion_type": "para_link",
                    "container_name": "Project Alpha",
                    "confidence": 0.92,
                    "created_at": "2024-01-15T10:30:00Z"
                }
            ]
        }
    }


class InboxResponse(BaseModel):
    """Response with all pending suggestions."""

    suggestions: List[InboxSuggestion] = Field(default_factory=list, description="List of pending suggestions")
    total_count: int = Field(..., description="Total number of pending suggestions")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "suggestions": [
                        {
                            "suggestion_id": "sug_abc123",
                            "workflow_id": "wf_a1b2c3d4",
                            "note_path": "meetings/sync.md",
                            "suggestion_type": "para_link",
                            "container_name": "Project Alpha",
                            "confidence": 0.92,
                            "created_at": "2024-01-15T10:30:00Z"
                        }
                    ],
                    "total_count": 1
                }
            ]
        }
    }


class InboxCountResponse(BaseModel):
    """Response with count of pending suggestions."""

    count: int = Field(..., description="Number of pending suggestions")
