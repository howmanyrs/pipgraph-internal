"""
Pydantic schemas for workflow endpoints.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import uuid


def generate_workflow_id() -> str:
    """
    Generate a URL-safe workflow ID.

    Format: wf_{uuid_short} (e.g., wf_a1b2c3d4)
    """
    short_uuid = uuid.uuid4().hex[:8]
    return f"wf_{short_uuid}"


class WorkflowCreateRequest(BaseModel):
    """Request to start a new workflow."""

    file_path: str = Field(..., description="Path to the note file")
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

    workflow_id: str = Field(..., description="Unique workflow identifier")
    status: str = Field(..., description="Current workflow status")
    file_path: str = Field(..., description="Path to the processed note")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "workflow_id": "wf_a1b2c3d4",
                    "status": "waiting_user",
                    "file_path": "meetings/sync.md"
                }
            ]
        }
    }


class WorkflowStatusResponse(BaseModel):
    """Response with detailed workflow status."""

    workflow_id: str = Field(..., description="Unique workflow identifier")
    status: str = Field(..., description="Current status: processing, waiting_user, completed, error")
    file_path: Optional[str] = Field(None, description="Path to the note file")
    pending_question: Optional[Dict[str, Any]] = Field(None, description="Question awaiting user response")
    episode_uuid: Optional[str] = Field(None, description="UUID of created episode (when completed)")
    error: Optional[str] = Field(None, description="Error message if status is error")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "workflow_id": "wf_a1b2c3d4",
                    "status": "waiting_user",
                    "file_path": "meetings/sync.md",
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

    answer: Dict[str, Any] = Field(..., description="User's answer to the pending question")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "answer": {
                        "question_id": "q_123",
                        "action": "confirm"
                    }
                }
            ]
        }
    }


class WorkflowResumeResponse(BaseModel):
    """Response after resuming a workflow."""

    workflow_id: str = Field(..., description="Unique workflow identifier")
    status: str = Field(..., description="Updated workflow status")
    next_question: Optional[Dict[str, Any]] = Field(None, description="Next question if any")
    episode_uuid: Optional[str] = Field(None, description="UUID of created episode (when completed)")
    cascade_applied: Optional[list] = Field(None, description="List of auto-resolved suggestions")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "workflow_id": "wf_a1b2c3d4",
                    "status": "completed",
                    "next_question": None,
                    "episode_uuid": "ep_xyz789",
                    "cascade_applied": []
                }
            ]
        }
    }
