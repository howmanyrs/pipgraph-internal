"""
Pydantic schemas for development/testing endpoints.

Schemas for direct note processing bypassing the workflow system.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ProcessNoteRequest(BaseModel):
    """Request to process a note directly through Graphiti."""

    name: str = Field(..., description="Name/title of the episode")
    episode_body: str = Field(..., description="Content of the note to process")
    source_description: Optional[str] = Field(
        "Development test note",
        description="Description of the episode source"
    )
    reference_time: Optional[datetime] = Field(
        None,
        description="Reference time for the episode (defaults to current time)"
    )
    use_para_entities: bool = Field(
        False,
        description="Whether to use PARA entity types for extraction"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Test Meeting Note",
                    "episode_body": "Met with John to discuss the API migration project. We need to update the authentication system.",
                    "source_description": "Development test",
                    "reference_time": None,
                    "use_para_entities": True
                }
            ]
        }
    }


class ProcessNoteResponse(BaseModel):
    """Response from direct note processing."""

    success: bool = Field(..., description="Whether processing was successful")
    episode_uuid: Optional[str] = Field(None, description="UUID of created episode")
    nodes_count: int = Field(0, description="Number of nodes extracted")
    edges_count: int = Field(0, description="Number of edges created")
    error: Optional[str] = Field(None, description="Error message if processing failed")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "episode_uuid": "ep_abc123",
                    "nodes_count": 5,
                    "edges_count": 3,
                    "error": None
                }
            ]
        }
    }


class GetEpisodicResponse(BaseModel):
    """Response from getting an Episodic node by path."""

    success: bool = Field(..., description="Whether the episodic was found")
    episodic: Optional[dict] = Field(None, description="Episodic node properties")
    error: Optional[str] = Field(None, description="Error message if retrieval failed")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "episodic": {
                        "name": "notes/meeting-2024-01-15.md",
                        "created_at": "2024-01-15T10:00:00Z",
                        "valid_at": "2024-01-15T10:00:00Z",
                        "uuid": "ep_abc123"
                    },
                    "error": None
                }
            ]
        }
    }


class ListEpisodicResponse(BaseModel):
    """Response from listing all Episodic nodes."""

    success: bool = Field(..., description="Whether retrieval was successful")
    episodics: list[dict] = Field(default_factory=list, description="List of Episodic nodes")
    count: int = Field(0, description="Number of episodics returned")
    error: Optional[str] = Field(None, description="Error message if retrieval failed")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "episodics": [
                        {
                            "name": "Test Meeting",
                            "created_at": "2024-01-15T10:00:00Z",
                            "valid_at": "2024-01-15T10:00:00Z",
                            "uuid": "ep_abc123"
                        }
                    ],
                    "count": 1,
                    "error": None
                }
            ]
        }
    }


class CreateEpisodeRequest(BaseModel):
    """Request to create an Episodic node without full processing."""

    name: str = Field(..., description="Name/title of the episode (note path or title)")
    content: str = Field(..., description="Content of the note")
    source_description: Optional[str] = Field(
        "Obsidian note",
        description="Description of the episode source"
    )
    reference_time: Optional[datetime] = Field(
        None,
        description="Reference time for the episode (defaults to current time)"
    )
    obsidian_path: Optional[str] = Field(
        None,
        description="Full path to note in Obsidian vault"
    )
    frontmatter: Optional[dict] = Field(
        None,
        description="YAML frontmatter metadata from the note"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Meeting Notes 2024-01-15",
                    "content": "Discussed API migration timeline with the team...",
                    "source_description": "Obsidian note",
                    "reference_time": "2024-01-15T10:00:00Z",
                    "obsidian_path": "notes/meetings/2024-01-15.md",
                    "frontmatter": {"tags": ["meeting", "api"], "status": "draft"}
                }
            ]
        }
    }


class CreateEpisodeResponse(BaseModel):
    """Response from episode creation."""

    success: bool = Field(..., description="Whether creation was successful")
    uuid: Optional[str] = Field(None, description="UUID of created episode")
    created_at: Optional[datetime] = Field(None, description="Timestamp when episode was created")
    error: Optional[str] = Field(None, description="Error message if creation failed")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "uuid": "550e8400-e29b-41d4-a716-446655440000",
                    "created_at": "2024-01-15T10:00:00Z",
                    "error": None
                }
            ]
        }
    }
