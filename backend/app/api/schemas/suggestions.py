"""
Pydantic schemas for suggestions endpoints.
Refactored to use file_path/note_path as identifiers instead of workflow_id.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class SuggestionItem(BaseModel):
    """Single suggestion item."""

    suggestion_id: str = Field(..., description="Unique suggestion identifier")
    suggestion_type: str = Field(..., description="Type: link or property_update")
    container_type: str = Field(..., description="PARA type: Project, Area, Resource, Archive")
    container_name: str = Field(..., description="Name of the suggested container")
    container_id: str = Field(..., description="Container ID in Neo4j")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0-1")
    reasoning: str = Field(..., description="Explanation for this suggestion")
    target_field: Optional[str] = Field(None, description="Field to update (for property_update type)")
    suggested_value: Optional[str] = Field(None, description="New value (for property_update type)")
    alternatives: List[dict] = Field(default_factory=list, description="Alternative suggestions")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "suggestion_id": "sug_abc123",
                    "suggestion_type": "link",
                    "container_type": "Project",
                    "container_name": "Project Alpha",
                    "container_id": "proj-001",
                    "confidence": 0.92,
                    "reasoning": "Content matches project goals",
                    "alternatives": []
                }
            ]
        }
    }


class SuggestionsResponse(BaseModel):
    """Response with workflow suggestions."""

    file_path: str = Field(..., description="Path to the note file (unique ID)")
    suggestions: List[SuggestionItem] = Field(default_factory=list, description="List of suggestions")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "file_path": "meetings/sync.md",
                    "suggestions": [
                        {
                            "suggestion_id": "sug_abc123",
                            "suggestion_type": "link",
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
    file_path: str = Field(..., description="Associated note path")
    suggestion_id: str = Field(..., description="Processed suggestion identifier")
    action: str = Field(..., description="Action that was performed")
    cascade_applied: List[dict] = Field(default_factory=list, description="Auto-resolved suggestions via cascade")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "file_path": "meetings/sync.md",
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
    note_path: str = Field(..., description="Path to the source note")
    suggestion_type: str = Field(..., description="Type: link or property_update")
    container_name: str = Field(..., description="Suggested container name")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    created_at: datetime = Field(..., description="When the suggestion was created")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "suggestion_id": "sug_abc123",
                    "note_path": "meetings/sync.md",
                    "suggestion_type": "link",
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
                            "note_path": "meetings/sync.md",
                            "suggestion_type": "link",
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