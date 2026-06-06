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


class GetEpisodicsByEntityResponse(BaseModel):
    """Response from getting episodics that mention a specific entity."""

    success: bool = Field(..., description="Whether retrieval was successful")
    entity_uuid: Optional[str] = Field(None, description="UUID of the queried entity")
    episodics: list[dict] = Field(
        default_factory=list,
        description="List of Episodic nodes mentioning the entity"
    )
    count: int = Field(0, description="Number of episodics returned")
    error: Optional[str] = Field(None, description="Error message if retrieval failed")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "entity_uuid": "660e8400-e29b-41d4-a716-446655440111",
                    "episodics": [
                        {
                            "uuid": "550e8400-e29b-41d4-a716-446655440000",
                            "name": "Meeting Notes 2024-01-15",
                            "created_at": "2024-01-15T10:00:00Z",
                            "valid_at": "2024-01-15T10:00:00Z",
                            "source": "ingestion",
                            "content": "Discussed project timeline...",
                            "source_description": "Obsidian note",
                            "group_id": "default"
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

    content: str = Field(..., description="Content of the note")
    name: Optional[str] = Field(
        None,
        description="Name/title of the episode. If not provided, will be auto-generated "
                   "from content using LLM (recommended for better naming consistency)"
    )
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
    uuid: Optional[str] = Field(
        None,
        description="Optional client-supplied UUID (e.g. crypto.randomUUID()). When "
                   "provided, the server MERGEs on it — re-posting the same UUID upserts "
                   "the same Episodic instead of creating a duplicate (idempotent outbox "
                   "delivery). When omitted, the server generates one."
    )
    generate_name: bool = Field(
        False,
        description="When true, generate the final name asynchronously via the job "
                   "queue: the Episodic is created immediately with the provided `name` "
                   "as a provisional title and status='processing'; a background job "
                   "later overwrites `name` with an LLM-generated one and clears status. "
                   "When false (default), behaviour is unchanged — `name` is stored as-is, "
                   "or generated synchronously if absent."
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
    name: Optional[str] = Field(None, description="Name of the episode (auto-generated or provided)")
    created_at: Optional[datetime] = Field(None, description="Timestamp when episode was created")
    status: Optional[str] = Field(
        None,
        description="Transient processing status, if any. 'processing' means an async "
                   "naming job was enqueued (poll GET /episodic/{uuid} until it clears)."
    )
    error: Optional[str] = Field(None, description="Error message if creation failed")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "uuid": "550e8400-e29b-41d4-a716-446655440000",
                    "name": "Project Planning Meeting",
                    "created_at": "2024-01-15T10:00:00Z",
                    "status": None,
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


class LinkParaNodesRequest(BaseModel):
    """Request to create a BELONGS_TO relationship between two PARA Entity nodes."""

    source_entity_uuid: str = Field(..., description="UUID of source Entity (child)")
    target_entity_uuid: str = Field(..., description="UUID of target Entity (parent)")
    created_at: Optional[datetime] = Field(
        None,
        description="Optional timestamp for the relationship (defaults to current time)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "source_entity_uuid": "550e8400-e29b-41d4-a716-446655440000",
                    "target_entity_uuid": "660e8400-e29b-41d4-a716-446655440111",
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


class LinkParaNodesResponse(BaseModel):
    """Response from BELONGS_TO relationship creation."""

    success: bool = Field(..., description="Whether link creation was successful")
    edge_uuid: Optional[str] = Field(None, description="UUID of created BELONGS_TO edge")
    source_entity_uuid: Optional[str] = Field(None, description="UUID of source Entity (child)")
    target_entity_uuid: Optional[str] = Field(None, description="UUID of target Entity (parent)")
    created_at: Optional[datetime] = Field(None, description="Timestamp when relationship was created")
    error: Optional[str] = Field(None, description="Error message if creation failed")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "edge_uuid": "770e8400-e29b-41d4-a716-446655440333",
                    "source_entity_uuid": "550e8400-e29b-41d4-a716-446655440000",
                    "target_entity_uuid": "660e8400-e29b-41d4-a716-446655440111",
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
    file_path: Optional[str] = Field(None, description="Client-side filesystem binding (vault folder mirroring this entity); read-projection only, not an identity")
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
                            "file_path": "Projects/website-redesign",
                            "attributes": {"status": "active", "priority": "high"}
                        }
                    ],
                    "count": 1,
                    "error": None
                }
            ]
        }
    }


class UpdateParaEntityRequest(BaseModel):
    """Request to update mutable fields of an existing PARA entity.

    Only ``summary`` is editable for now (S8 partial); ``name`` / ``file_path``
    are not handled yet. Fields left ``None`` are unchanged.
    """

    summary: Optional[str] = Field(
        None,
        description="New summary text. None = leave unchanged."
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "summary": "Maintenance domain covering fitness, sleep, and nutrition."
                }
            ]
        }
    }


class UpdateParaEntityResponse(BaseModel):
    """Response from updating a PARA entity. Returns the updated entity."""

    success: bool = Field(..., description="Whether the entity was found and updated")
    entity: Optional["ParaEntityProperty"] = Field(
        None, description="The updated PARA entity (None if not found)"
    )
    error: Optional[str] = Field(None, description="Error message if the update failed")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "entity": {
                        "uuid": "660e8400-e29b-41d4-a716-446655440111",
                        "name": "Health",
                        "para_type": "Area",
                        "created_at": "2024-01-15T10:00:00Z",
                        "summary": "Maintenance domain covering fitness, sleep, and nutrition.",
                        "file_path": "PipGraph/Areas/Health",
                        "attributes": {}
                    },
                    "error": None
                }
            ]
        }
    }


class UpdateEpisodicRequest(BaseModel):
    """Request to update mutable fields of an existing Episodic.

    Narrow by design: only ``file_path`` is editable (the Episodic mirror of the
    S1 ``file_path`` symmetry). Fields left ``None`` are unchanged.
    """

    file_path: Optional[str] = Field(
        None,
        description="New file path. None = leave unchanged."
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "file_path": "Inbox/Meeting notes (1).md"
                }
            ]
        }
    }


class UpdateEpisodicResponse(BaseModel):
    """Response from updating an Episodic. Returns the updated episodic."""

    success: bool = Field(..., description="Whether the episodic was found and updated")
    episodic: Optional[dict] = Field(
        None, description="The updated Episodic node (None if not found)"
    )
    error: Optional[str] = Field(None, description="Error message if the update failed")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "episodic": {
                        "uuid": "550e8400-e29b-41d4-a716-446655440000",
                        "name": "Meeting notes",
                        "file_path": "Inbox/Meeting notes (1).md",
                        "created_at": "2024-01-15T10:00:00Z",
                        "valid_at": "2024-01-15T10:00:00Z",
                        "source": "text",
                        "content": "...",
                        "source_description": "obsidian",
                        "group_id": "default"
                    },
                    "error": None
                }
            ]
        }
    }


class PlaceEpisodeRequest(BaseModel):
    """Request to place an Episodic into a PARA folder-entity (move+link, E7).

    One act: set the Episodic's ``file_path`` to the new (cross-folder) location
    **and** MERGE the ``MENTIONS`` edge to the entity. Unlike the narrow
    ``PATCH /episodic/{uuid}`` (which rejects cross-folder moves, guard E6), this
    re-points placement and edge together, so a cross-folder ``file_path`` is the
    intended behaviour here. The physical file move is the client's responsibility.
    """

    episodic_uuid: str = Field(..., description="UUID of the Episodic being placed")
    entity_uuid: str = Field(..., description="UUID of the PARA Entity (folder) it is filed under")
    file_path: str = Field(..., description="New vault-relative path inside the entity's folder")
    process: bool = Field(
        False,
        description=(
            "If true, enqueue the heavy extraction pipeline after linking (P2): the "
            "node is stamped status='process_existing_episode' atomically with the "
            "move+link, a background job runs the pipeline, and the client polls "
            "GET /episodic/{uuid} until status clears. If false (default), only "
            "move+link is performed (synchronous, as before)."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "episodic_uuid": "550e8400-e29b-41d4-a716-446655440000",
                    "entity_uuid": "660e8400-e29b-41d4-a716-446655440111",
                    "file_path": "Areas/Health/Meeting notes.md",
                    "process": True
                }
            ]
        }
    }


class PlaceEpisodeResponse(BaseModel):
    """Response from placing an Episodic (move+link). Returns the updated episodic."""

    success: bool = Field(..., description="Whether the Episodic was found and placed")
    episodic: Optional[dict] = Field(
        None, description="The updated Episodic node (None if not found)"
    )
    entity_uuid: Optional[str] = Field(None, description="UUID of the entity it was linked to")
    edge_uuid: Optional[str] = Field(None, description="UUID of the MENTIONS edge (MERGE — stable across re-placement)")
    error: Optional[str] = Field(None, description="Error message if the placement failed")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "episodic": {
                        "uuid": "550e8400-e29b-41d4-a716-446655440000",
                        "name": "Meeting notes",
                        "file_path": "Areas/Health/Meeting notes.md",
                        "created_at": "2024-01-15T10:00:00Z",
                        "valid_at": "2024-01-15T10:00:00Z",
                        "source": "text",
                        "content": "...",
                        "source_description": "obsidian",
                        "group_id": "default"
                    },
                    "entity_uuid": "660e8400-e29b-41d4-a716-446655440111",
                    "edge_uuid": "770e8400-e29b-41d4-a716-446655440222",
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

    episodic_uuid: str = Field(..., description="UUID of the Episodic node")
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
                    "episodic_uuid": "550e8400-e29b-41d4-a716-446655440000",
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


class ListUnlinkedEpisodicResponse(BaseModel):
    """Response from listing Episodic nodes without PARA entity mentions."""

    success: bool = Field(..., description="Whether retrieval was successful")
    episodics: list[dict] = Field(
        default_factory=list,
        description="List of Episodic nodes without PARA entity mentions"
    )
    count: int = Field(0, description="Number of episodics returned")
    error: Optional[str] = Field(None, description="Error message if retrieval failed")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "episodics": [
                        {
                            "uuid": "550e8400-e29b-41d4-a716-446655440000",
                            "name": "Unclassified Note",
                            "created_at": "2024-01-15T10:00:00Z",
                            "valid_at": "2024-01-15T10:00:00Z",
                            "source": "text",
                            "content": "Note content...",
                            "source_description": "Obsidian note",
                            "group_id": "default"
                        }
                    ],
                    "count": 1,
                    "error": None
                }
            ]
        }
    }


class DeleteNodeResponse(BaseModel):
    """Response from node deletion."""

    success: bool = Field(..., description="Whether deletion was successful")
    node_uuid: Optional[str] = Field(None, description="UUID of the deleted node")
    node_type: Optional[str] = Field(None, description="Type of the deleted node (Episodic or Entity)")
    error: Optional[str] = Field(None, description="Error message if deletion failed")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "node_uuid": "550e8400-e29b-41d4-a716-446655440000",
                    "node_type": "Episodic",
                    "error": None
                }
            ]
        }
    }


class DeleteParaEntityResponse(BaseModel):
    """Response from cascade deletion of a PARA Entity."""

    success: bool = Field(..., description="Whether the entity was found and deleted")
    entity_uuid: Optional[str] = Field(None, description="UUID of the deleted entity")
    deleted_episodics_count: int = Field(
        0, description="Number of orphaned Episodics deleted along with the entity"
    )
    error: Optional[str] = Field(None, description="Error message if deletion failed")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "entity_uuid": "660e8400-e29b-41d4-a716-446655440111",
                    "deleted_episodics_count": 3,
                    "error": None,
                }
            ]
        }
    }


class GetParaTreeResponse(BaseModel):
    """Response from getting PARA tree structure."""

    success: bool = Field(..., description="Whether tree retrieval was successful")
    tree: list[dict] = Field(default_factory=list, description="PARA tree structure (list of root nodes)")
    count: int = Field(0, description="Number of root nodes in the tree")
    error: Optional[str] = Field(None, description="Error message if retrieval failed")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "tree": [
                        {
                            "id": "550e8400-e29b-41d4-a716-446655440000",
                            "name": "Product Development",
                            "type": "Area",
                            "children": [
                                {
                                    "id": "660e8400-e29b-41d4-a716-446655440111",
                                    "name": "Website Redesign",
                                    "type": "Project",
                                    "children": []
                                }
                            ]
                        }
                    ],
                    "count": 1,
                    "error": None
                }
            ]
        }
    }


# --- LLM provider configuration (/dev/llm-config) ---


class LlmProviderDefaults(BaseModel):
    """Default base_url + model names for a provider (no api_key). Lets clients prefill."""

    base_url: str = Field(..., description="Default OpenAI-compatible base URL")
    main_model: str = Field(..., description="Default main model id")
    small_model: str = Field(..., description="Default small/fast model id")
    embedding_model: str = Field(..., description="Default embedding model id")


class LlmConfigEntry(BaseModel):
    """A resolved LLM config. The api_key is never returned — only whether it is set."""

    provider: str = Field(..., description='Active provider: "cloudru" | "openrouter"')
    base_url: str = Field(..., description="OpenAI-compatible base URL")
    main_model: str = Field(..., description="Main model id")
    small_model: str = Field(..., description="Small/fast model id")
    embedding_model: str = Field(..., description="Embedding model id")
    api_key_set: bool = Field(..., description="Whether a non-empty api_key is configured")
    api_key_hint: Optional[str] = Field(
        None, description="Last 4 chars of the api_key, for recognition only"
    )


class GetLlmConfigResponse(BaseModel):
    """Current LLM config state: what's running vs what applies after restart."""

    success: bool = Field(..., description="Whether the state was read successfully")
    active: Optional[LlmConfigEntry] = Field(
        None, description="Config the running Graphiti singleton was built on"
    )
    saved: Optional[LlmConfigEntry] = Field(
        None, description="Config that will apply after the next backend restart"
    )
    restart_required: bool = Field(
        False, description="True if saved differs from active (restart to apply)"
    )
    providers: dict[str, LlmProviderDefaults] = Field(
        default_factory=dict, description="Per-provider defaults for client prefill"
    )
    error: Optional[str] = Field(None, description="Error message if read failed")


class UpdateLlmConfigRequest(BaseModel):
    """Patch the saved LLM config. Omitted model/base_url fields fall back to the
    selected provider's defaults; an empty/omitted api_key keeps the saved key
    (unless the provider changed)."""

    provider: str = Field(..., description='"cloudru" | "openrouter"')
    api_key: Optional[str] = Field(
        None, description="Provider API key; empty/omitted keeps the existing key"
    )
    main_model: Optional[str] = Field(None, description="Main model id (optional)")
    small_model: Optional[str] = Field(None, description="Small model id (optional)")
    embedding_model: Optional[str] = Field(None, description="Embedding model id (optional)")
    base_url: Optional[str] = Field(None, description="Override base URL (optional)")


class LlmConfigUpdateResponse(BaseModel):
    """Result of a PATCH/reset on the saved LLM config."""

    success: bool = Field(..., description="Whether the write succeeded")
    restart_required: bool = Field(
        False, description="True if the change differs from the running config"
    )
    saved: Optional[LlmConfigEntry] = Field(
        None, description="The config now persisted (applies after restart)"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Non-fatal warnings (e.g. embedding-model change invalidates vectors)",
    )
    error: Optional[str] = Field(None, description="Error message if the write failed")
