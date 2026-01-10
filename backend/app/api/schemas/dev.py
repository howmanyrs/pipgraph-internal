"""
Pydantic schemas for development/testing endpoints.

Schemas for direct note processing bypassing the workflow system.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
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
    file_path: Optional[str] = Field(
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
                    "file_path": "notes/meetings/2024-01-15.md",
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


class CreateParaEntityRequest(BaseModel):
    """Request to create a PARA entity node without full processing pipeline."""

    para_type: str = Field(
        ...,
        description="PARA classification: 'Project', 'Area', 'Resource', or 'Archive'"
    )
    name: str = Field(..., description="Entity display name")
    summary: str = Field("", description="Description/summary of the entity")
    group_id: Optional[str] = Field(None, description="Graph partition ID (defaults to provider default)")
    file_path: Optional[str] = Field(None, description="Optional path to source note in Obsidian vault")
    attributes: Optional[dict] = Field(None, description="Optional custom attributes dict")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "para_type": "Project",
                    "name": "Website Redesign Q1 2024",
                    "summary": "Complete redesign of company website with new branding",
                    "file_path": "projects/website-redesign.md",
                    "attributes": {"status": "active", "priority": "high"}
                }
            ]
        }
    }


class CreateParaEntityResponse(BaseModel):
    """Response from PARA entity creation."""

    success: bool = Field(..., description="Whether creation was successful")
    uuid: Optional[str] = Field(None, description="UUID of created entity")
    para_type: Optional[str] = Field(None, description="PARA type of the entity")
    name: Optional[str] = Field(None, description="Name of the entity")
    created_at: Optional[datetime] = Field(None, description="Timestamp when entity was created")
    error: Optional[str] = Field(None, description="Error message if creation failed")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "uuid": "550e8400-e29b-41d4-a716-446655440000",
                    "para_type": "Project",
                    "name": "Website Redesign Q1 2024",
                    "created_at": "2024-01-15T10:00:00Z",
                    "error": None
                }
            ]
        }
    }


class LinkEntityEpisodeRequest(BaseModel):
    """Request to create a MENTIONS relationship between existing Episodic and Entity nodes."""

    episodic_uuid: str = Field(..., description="UUID of existing Episodic node")
    entity_uuid: str = Field(..., description="UUID of existing Entity node")
    created_at: Optional[datetime] = Field(
        None,
        description="Optional timestamp for the relationship (defaults to current time)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "episodic_uuid": "550e8400-e29b-41d4-a716-446655440000",
                    "entity_uuid": "660e8400-e29b-41d4-a716-446655440111",
                    "created_at": None
                }
            ]
        }
    }


class LinkEntityEpisodeResponse(BaseModel):
    """Response from MENTIONS relationship creation."""

    success: bool = Field(..., description="Whether link creation was successful")
    edge_uuid: Optional[str] = Field(None, description="UUID of created MENTIONS edge")
    episodic_uuid: Optional[str] = Field(None, description="UUID of source Episodic node")
    entity_uuid: Optional[str] = Field(None, description="UUID of target Entity node")
    created_at: Optional[datetime] = Field(None, description="Timestamp when relationship was created")
    error: Optional[str] = Field(None, description="Error message if creation failed")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "edge_uuid": "770e8400-e29b-41d4-a716-446655440222",
                    "episodic_uuid": "550e8400-e29b-41d4-a716-446655440000",
                    "entity_uuid": "660e8400-e29b-41d4-a716-446655440111",
                    "created_at": "2024-01-08T10:30:00Z",
                    "error": None
                }
            ]
        }
    }


class ParaEntityProperty(BaseModel):
    """Single PARA entity with properties."""

    uuid: str = Field(..., description="Unique entity identifier")
    name: str = Field(..., description="Entity display name")
    para_type: str = Field(..., description="PARA type (Project, Area, Resource, Archive)")
    created_at: Optional[datetime] = Field(None, description="Entity creation timestamp")
    summary: Optional[str] = Field(None, description="Entity description/summary")
    attributes: dict = Field(default_factory=dict, description="Custom attributes (status, priority, etc.)")


class ListParaEntitiesResponse(BaseModel):
    """Response from listing PARA entities."""

    success: bool = Field(..., description="Whether retrieval was successful")
    entities: list[ParaEntityProperty] = Field(default_factory=list, description="List of PARA entities")
    count: int = Field(0, description="Number of entities returned")
    error: Optional[str] = Field(None, description="Error message if retrieval failed")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "entities": [
                        {
                            "uuid": "550e8400-e29b-41d4-a716-446655440000",
                            "name": "Website Redesign Q1 2024",
                            "para_type": "Project",
                            "created_at": "2024-01-15T10:00:00Z",
                            "summary": "Complete redesign of company website",
                            "attributes": {"status": "active", "priority": "high"}
                        }
                    ],
                    "count": 1,
                    "error": None
                }
            ]
        }
    }


class ProcessExistingEpisodeRequest(BaseModel):
    """Request to process an existing Episodic node with entity extraction.

    Preconditions:
    - Episodic node with given UUID must exist
    - Episodic must be linked to at least one PARA Entity via MENTIONS
    """

    episodic_uuid: str = Field(..., description="UUID of existing Episodic node")
    update_communities: bool = Field(
        default=False,
        description="Whether to update communities after processing"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "episodic_uuid": "550e8400-e29b-41d4-a716-446655440000",
                    "update_communities": False
                }
            ]
        }
    }


class ProcessExistingEpisodeResponse(BaseModel):
    """Response from processing an existing Episodic node."""

    success: bool = Field(..., description="Whether processing was successful")
    episode_uuid: Optional[str] = Field(None, description="UUID of the processed episode")
    nodes_count: int = Field(0, description="Number of nodes extracted/updated")
    edges_count: int = Field(0, description="Number of entity edges created")
    episodic_edges_count: int = Field(0, description="Number of new MENTIONS edges created")
    para_entities_updated: List[str] = Field(
        default_factory=list,
        description="Names of PARA entities whose summary was updated"
    )
    error: Optional[str] = Field(None, description="Error message if processing failed")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "episode_uuid": "550e8400-e29b-41d4-a716-446655440000",
                    "nodes_count": 5,
                    "edges_count": 3,
                    "episodic_edges_count": 4,
                    "para_entities_updated": ["Website Redesign Q1 2024"],
                    "error": None
                }
            ]
        }
    }


class MakeSuggestionsRequest(BaseModel):
    """Request to find relevant PARA entities for an episodic note."""

    episodic_name: str = Field(..., description="Name (path) of the Episodic node")
    limit: int = Field(
        10,
        description="Maximum number of suggestions to return",
        ge=1,
        le=50
    )
    min_score: float = Field(
        0.0,
        description="Minimum relevance score (0.0-1.0)",
        ge=0.0,
        le=1.0
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "episodic_name": "notes/meeting-2024-01-15.md",
                    "limit": 10,
                    "min_score": 0.0
                }
            ]
        }
    }


class ParaSuggestion(BaseModel):
    """A single PARA entity suggestion with relevance score."""

    uuid: str = Field(..., description="Entity UUID")
    name: str = Field(..., description="Entity name")
    para_type: str = Field(..., description="PARA type (Project, Area, Resource, Archive)")
    summary: str = Field(..., description="Entity summary")
    score: float = Field(..., description="Relevance score from search")
    attributes: dict = Field(default_factory=dict, description="Custom attributes")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "uuid": "550e8400-e29b-41d4-a716-446655440000",
                    "name": "Website Redesign Q1 2024",
                    "para_type": "Project",
                    "summary": "Complete redesign of company website",
                    "score": 0.85,
                    "attributes": {"status": "active"}
                }
            ]
        }
    }


class MakeSuggestionsResponse(BaseModel):
    """Response containing relevant PARA entity suggestions."""

    success: bool = Field(..., description="Whether search was successful")
    episodic_uuid: Optional[str] = Field(None, description="UUID of the Episodic node")
    suggestions: List[ParaSuggestion] = Field(
        default_factory=list,
        description="List of relevant PARA entities sorted by score"
    )
    count: int = Field(0, description="Number of suggestions returned")
    error: Optional[str] = Field(None, description="Error message if search failed")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "episodic_uuid": "660e8400-e29b-41d4-a716-446655440111",
                    "suggestions": [
                        {
                            "uuid": "550e8400-e29b-41d4-a716-446655440000",
                            "name": "Website Redesign Q1 2024",
                            "para_type": "Project",
                            "summary": "Complete redesign of company website",
                            "score": 0.85,
                            "attributes": {"status": "active"}
                        }
                    ],
                    "count": 1,
                    "error": None
                }
            ]
        }
    }
