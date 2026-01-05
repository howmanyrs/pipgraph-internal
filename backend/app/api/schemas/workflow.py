"""
Pydantic schemas for workflow endpoints.
Refactored to use file_path as the unique identifier (stateless API).
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class WorkflowCreateRequest(BaseModel):
    """Request to start a new workflow."""

    file_path: str = Field(..., description="Path to the note file (acts as unique ID)")
    content: str = Field(..., description="Content of the note")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "file_path": "meetings/sync.md",
                    "content": "# Meeting with John Smith\n\nDiscussed project timeline..."
                }
            ]
        }
    }


class WorkflowCreateResponse(BaseModel):
    """Response after starting a workflow."""

    file_path: str = Field(..., description="Path to the processed note (unique ID)")
    status: str = Field(..., description="Current workflow status")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "file_path": "meetings/sync.md",
                    "status": "waiting_user"
                }
            ]
        }
    }


class WorkflowStatusResponse(BaseModel):
    """Response with detailed workflow status."""

    file_path: str = Field(..., description="Path to the note file (unique ID)")
    status: str = Field(..., description="Current status: processing, waiting_user, completed, error")
    pending_question: Optional[Dict[str, Any]] = Field(None, description="Question awaiting user response")
    episode_uuid: Optional[str] = Field(None, description="UUID of created episode (when completed)")
    error: Optional[str] = Field(None, description="Error message if status is error")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "file_path": "meetings/sync.md",
                    "status": "waiting_user",
                    "pending_question": {
                        "question_id": "q_123",
                        "question_type": "para_link",
                        "container_name": "Project Alpha"
                    },
                    "episode_uuid": None,
                    "error": None
                }
            ]
        }
    }


class WorkflowResumeRequest(BaseModel):
    """Request to resume a workflow with user answer."""

    file_path: str = Field(..., description="Path to the note file (identifies the workflow thread)")
    answer: Dict[str, Any] = Field(..., description="User's answer to the pending question")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "file_path": "meetings/sync.md",
                    "answer": {
                        "suggestion_id": "sug_123",
                        "action": "confirm"
                    }
                }
            ]
        }
    }


class WorkflowResumeResponse(BaseModel):
    """Response after resuming a workflow."""

    file_path: str = Field(..., description="Path to the note file")
    status: str = Field(..., description="Updated workflow status")
    next_question: Optional[Dict[str, Any]] = Field(None, description="Next question if any")
    episode_uuid: Optional[str] = Field(None, description="UUID of created episode (when completed)")
    cascade_applied: Optional[list] = Field(None, description="List of auto-resolved suggestions")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "file_path": "meetings/sync.md",
                    "status": "completed",
                    "next_question": None,
                    "episode_uuid": "ep_xyz789",
                    "cascade_applied": []
                }
            ]
        }
    }


