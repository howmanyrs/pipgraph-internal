"""
Development/testing endpoints.

Provides direct access to core functionality for development and testing purposes.
Bypasses the workflow system for immediate processing.
"""

import logging
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Query, Request

from app.api.schemas.dev import (
    ProcessNoteRequest,
    ProcessNoteResponse,
    GetEpisodicResponse,
    ListEpisodicResponse,
    GetEpisodicsByEntityResponse,
    CreateEpisodeRequest,
    CreateEpisodeResponse,
    CreateParaEntityRequest,
    CreateParaEntityResponse,
    LinkEntityEpisodeRequest,
    LinkEntityEpisodeResponse,
    LinkParaNodesRequest,
    LinkParaNodesResponse,
    ParaEntityProperty,
    ListParaEntitiesResponse,
    UpdateParaEntityRequest,
    UpdateParaEntityResponse,
    ProcessExistingEpisodeRequest,
    ProcessExistingEpisodeResponse,
    MakeSuggestionsRequest,
    MakeSuggestionsResponse,
    ParaSuggestion,
    ListUnlinkedEpisodicResponse,
    DeleteNodeResponse,
    DeleteParaEntityResponse,
    GetParaTreeResponse,
)
from app.services.graphiti import get_graphiti, PipGraphManager
from app.services.graphiti.para_tree import PARATreeBuilder

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dev", tags=["development"])


@router.post("/process-note", response_model=ProcessNoteResponse)
async def process_note_direct(request: ProcessNoteRequest) -> ProcessNoteResponse:
    """
    Process a note directly through Graphiti without workflow orchestration.

    This endpoint is intended for development and testing purposes.
    It bypasses the LangGraph workflow and PARA classification,
    directly calling the entity extraction pipeline.

    Example:
        POST /api/v1/dev/process-note
        {
            "name": "Test Meeting",
            "episode_body": "Discussed API migration with the team...",
            "source_description": "Development test",
            "use_para_entities": true
        }

    Returns:
        ProcessNoteResponse with processing results
    """
    try:
        logger.info(f"[process_note_direct] Processing note: {request.name}")

        # Get Graphiti instance
        graphiti = await get_graphiti()
        manager = PipGraphManager(graphiti)

        # Use current time if not provided
        ref_time = request.reference_time or datetime.now(timezone.utc)

        # Process note directly
        result = await manager.process_note(
            name=request.name,
            episode_body=request.episode_body,
            source_description=request.source_description,
            reference_time=ref_time,
            use_para_entities=request.use_para_entities,
        )

        # Extract results
        episode_uuid = result.episode.uuid if result.episode else None
        nodes_count = len(result.nodes) if result.nodes else 0
        edges_count = len(result.edges) if result.edges else 0

        logger.info(
            f"[process_note_direct] Success: episode={episode_uuid}, "
            f"nodes={nodes_count}, edges={edges_count}"
        )

        return ProcessNoteResponse(
            success=True,
            episode_uuid=episode_uuid,
            nodes_count=nodes_count,
            edges_count=edges_count,
            error=None,
        )

    except Exception as e:
        logger.error(f"[process_note_direct] Error: {e}", exc_info=True)
        return ProcessNoteResponse(
            success=False,
            episode_uuid=None,
            nodes_count=0,
            edges_count=0,
            error=str(e),
        )


@router.get("/episodic", response_model=GetEpisodicResponse)
async def get_episodic_by_path(
    note_path: str = Query(..., description="Path to the note (Episodic.name)")
) -> GetEpisodicResponse:
    """
    Retrieve an Episodic node by its path (name).

    This endpoint provides direct access to Episodic nodes stored in Neo4j.
    The path corresponds to the note's file path in the file system.

    Example:
        GET /api/v1/dev/episodic?note_path=notes/meeting-2024-01-15.md

    Returns:
        GetEpisodicResponse with episodic node properties or error
    """
    try:
        logger.info(f"[get_episodic_by_path] Retrieving episodic: '{note_path}' (length: {len(note_path)})")
        logger.info(f"[get_episodic_by_path] note_path repr: {repr(note_path)}")

        # Get Graphiti instance and manager
        graphiti = await get_graphiti()
        manager = PipGraphManager(graphiti)

        # Get episodic from database using new manager method
        episodic = await manager.get_episodic_by_name(note_path)

        if episodic:
            logger.info(f"[get_episodic_by_path] Found episodic: {note_path} (uuid: {episodic.uuid})")

            # Convert EpisodicNode to dict for response
            episodic_dict = {
                "uuid": episodic.uuid,
                "name": episodic.name,
                "created_at": episodic.created_at.isoformat() if episodic.created_at else None,
                "valid_at": episodic.valid_at.isoformat() if episodic.valid_at else None,
                "source": episodic.source.value if episodic.source else None,
                "content": episodic.content,
                "source_description": episodic.source_description,
                "group_id": episodic.group_id,
            }

            return GetEpisodicResponse(
                success=True,
                episodic=episodic_dict,
                error=None,
            )
        else:
            logger.warning(f"[get_episodic_by_path] Episodic not found: {note_path}")
            return GetEpisodicResponse(
                success=False,
                episodic=None,
                error=f"Episodic not found: {note_path}",
            )

    except Exception as e:
        logger.error(f"[get_episodic_by_path] Error: {e}", exc_info=True)
        return GetEpisodicResponse(
            success=False,
            episodic=None,
            error=str(e),
        )


@router.get("/episodic/list", response_model=ListEpisodicResponse)
async def list_all_episodic(
    limit: int = Query(100, description="Maximum number of nodes to return", ge=1, le=1000)
) -> ListEpisodicResponse:
    """
    List all Episodic nodes in the database.

    This endpoint helps debug and inspect what Episodic nodes are stored.
    Useful for verifying node names when searching by path.

    Example:
        GET /api/v1/dev/episodic/list?limit=10

    Returns:
        ListEpisodicResponse with list of episodic nodes
    """
    try:
        logger.info(f"[list_all_episodic] Retrieving up to {limit} episodic nodes")

        # Get Graphiti instance and manager
        graphiti = await get_graphiti()
        manager = PipGraphManager(graphiti)

        # Get all episodics from database using new manager method
        episodics = await manager.list_episodics(limit=limit)

        logger.info(f"[list_all_episodic] Found {len(episodics)} episodic nodes")

        # Convert EpisodicNode objects to dicts for response
        episodics_dicts = [
            {
                "uuid": ep.uuid,
                "name": ep.name,
                "created_at": ep.created_at.isoformat() if ep.created_at else None,
                "valid_at": ep.valid_at.isoformat() if ep.valid_at else None,
                "source": ep.source.value if ep.source else None,
                "content": ep.content,
                "source_description": ep.source_description,
                "group_id": ep.group_id,
            }
            for ep in episodics
        ]

        # Log all names for debugging
        if episodics_dicts:
            names = [e.get("name") for e in episodics_dicts]
            logger.info(f"[list_all_episodic] Names: {names}")

        return ListEpisodicResponse(
            success=True,
            episodics=episodics_dicts,
            count=len(episodics_dicts),
            error=None,
        )

    except Exception as e:
        logger.error(f"[list_all_episodic] Error: {e}", exc_info=True)
        return ListEpisodicResponse(
            success=False,
            episodics=[],
            count=0,
            error=str(e),
        )


@router.get("/episodic/unlinked", response_model=ListUnlinkedEpisodicResponse)
async def list_unlinked_episodic(
    limit: int = Query(100, description="Maximum number of nodes to return", ge=1, le=1000)
) -> ListUnlinkedEpisodicResponse:
    """
    List all Episodic nodes that are NOT linked to any PARA entities.

    Returns Episodic nodes that do not have MENTIONS relationships to any
    Project, Area, Resource, or Archive entities. These are "orphaned" or
    "unclassified" notes that need to be categorized into the PARA system.

    Use cases:
    - Finding notes that need PARA classification
    - Inbox-like view of uncategorized notes
    - Identifying notes that require user intervention

    Query Parameters:
    - limit: Maximum results (1-1000, default 100)

    Example:
        GET /api/v1/dev/episodic/unlinked?limit=50

    Returns:
        ListUnlinkedEpisodicResponse with list of unlinked episodic nodes
    """
    try:
        logger.info(f"[list_unlinked_episodic] Retrieving up to {limit} unlinked episodic nodes")

        # Get Graphiti instance and manager
        graphiti = await get_graphiti()
        manager = PipGraphManager(graphiti)

        # Get unlinked episodics from database
        episodics = await manager.list_unlinked_episodics(limit=limit)

        logger.info(f"[list_unlinked_episodic] Found {len(episodics)} unlinked episodic nodes")

        # Convert EpisodicNode objects to dicts for response
        episodics_dicts = [
            {
                "uuid": ep.uuid,
                "name": ep.name,
                "created_at": ep.created_at.isoformat() if ep.created_at else None,
                "valid_at": ep.valid_at.isoformat() if ep.valid_at else None,
                "source": ep.source.value if ep.source else None,
                "content": ep.content,
                "source_description": ep.source_description,
                "group_id": ep.group_id,
            }
            for ep in episodics
        ]

        # Log sample names for debugging
        if episodics_dicts:
            sample_names = [e.get("name") for e in episodics_dicts[:5]]
            logger.info(f"[list_unlinked_episodic] Sample names: {sample_names}")

        return ListUnlinkedEpisodicResponse(
            success=True,
            episodics=episodics_dicts,
            count=len(episodics_dicts),
            error=None,
        )

    except ValueError as e:
        # Validation errors (invalid limit, etc.)
        logger.warning(f"[list_unlinked_episodic] Validation error: {e}")
        return ListUnlinkedEpisodicResponse(
            success=False,
            episodics=[],
            count=0,
            error=f"Validation error: {str(e)}",
        )

    except Exception as e:
        # Unexpected errors (database connection, etc.)
        logger.error(f"[list_unlinked_episodic] Error: {e}", exc_info=True)
        return ListUnlinkedEpisodicResponse(
            success=False,
            episodics=[],
            count=0,
            error=str(e),
        )


@router.post("/episode", response_model=CreateEpisodeResponse)
async def create_episode(request: CreateEpisodeRequest) -> CreateEpisodeResponse:
    """
    Create an Episodic node without full processing pipeline.

    This endpoint creates only the Episodic node in Neo4j without:
    - Entity extraction (L3)
    - Edge creation
    - Community updates

    The name will be auto-generated from content using LLM if not provided.

    Use this for:
    - Fast note ingestion without LLM processing
    - Incremental loading of notes
    - Development and testing

    Example (auto-generate name):
        POST /api/v1/dev/episode
        {
            "content": "Today we discussed the project timeline and decided to push the deadline by 2 weeks...",
            "source_description": "Obsidian note",
            "file_path": "notes/meetings/2024-01-15.md"
        }

    Example (explicit name):
        POST /api/v1/dev/episode
        {
            "name": "Q1 Planning Meeting",
            "content": "Discussed project timeline...",
            "source_description": "Obsidian note"
        }

    Returns:
        CreateEpisodeResponse with created episode UUID and timestamp
    """
    try:
        name_info = f"name='{request.name}'" if request.name else "auto-generating name"
        logger.info(f"[create_episode] Creating episode: {name_info}")

        # Get Graphiti instance
        graphiti = await get_graphiti()
        manager = PipGraphManager(graphiti)

        # Use current time if not provided
        ref_time = request.reference_time or datetime.now(timezone.utc)

        # Create episode without full processing
        # Note: positional args changed - content comes first now
        episode = await manager.create_episode(
            content=request.content,
            source_description=request.source_description or "Obsidian note",
            reference_time=ref_time,
            name=request.name,  # Optional - will auto-generate if None
            file_path=request.file_path,
            frontmatter=request.frontmatter,
        )

        logger.info(f"[create_episode] Success: uuid={episode.uuid}, name='{episode.name}'")

        return CreateEpisodeResponse(
            success=True,
            uuid=episode.uuid,
            name=episode.name,
            created_at=episode.created_at,
            error=None,
        )

    except Exception as e:
        logger.error(f"[create_episode] Error: {e}", exc_info=True)
        return CreateEpisodeResponse(
            success=False,
            uuid=None,
            created_at=None,
            error=str(e),
        )


@router.get("/episodics/by-entity", response_model=GetEpisodicsByEntityResponse)
async def get_episodics_by_entity(
    entity_uuid: str = Query(
        ...,
        description="UUID of the Entity node to query",
        min_length=1
    ),
    limit: int = Query(
        50,
        description="Maximum number of episodics to return",
        ge=1,
        le=500
    )
) -> GetEpisodicsByEntityResponse:
    """
    Get all Episodic nodes that mention a specific Entity.

    Returns Episodic nodes that have a MENTIONS relationship to the
    specified Entity, ordered by creation date (newest first).

    This is useful for:
    - Viewing all notes mentioning a specific project/area/resource
    - Timeline of entity mentions
    - Content analysis for entity context

    Query Parameters:
    - entity_uuid: UUID of the Entity to query (required)
    - limit: Maximum results (1-500, default 50)

    Example:
        GET /api/v1/dev/episodics/by-entity?entity_uuid=660e8400-e29b-41d4-a716-446655440111&limit=100

    Returns:
        GetEpisodicsByEntityResponse with episodics and metadata
    """
    try:
        logger.info(
            f"[get_episodics_by_entity] Querying episodics mentioning "
            f"entity {entity_uuid} (limit={limit})"
        )

        # Get Graphiti instance and manager
        graphiti = await get_graphiti()
        manager = PipGraphManager(graphiti)

        # Get episodics from database
        episodics = await manager.get_episodics_by_entity_uuid(
            entity_uuid=entity_uuid,
            limit=limit
        )

        logger.info(
            f"[get_episodics_by_entity] Found {len(episodics)} episodics "
            f"for entity {entity_uuid}"
        )

        # Convert EpisodicNode objects to dicts for response
        episodics_dicts = [
            {
                "uuid": ep.uuid,
                "name": ep.name,
                "created_at": ep.created_at.isoformat() if ep.created_at else None,
                "valid_at": ep.valid_at.isoformat() if ep.valid_at else None,
                "source": ep.source.value if ep.source else None,
                "content": ep.content,
                "source_description": ep.source_description,
                "group_id": ep.group_id,
            }
            for ep in episodics
        ]

        return GetEpisodicsByEntityResponse(
            success=True,
            entity_uuid=entity_uuid,
            episodics=episodics_dicts,
            count=len(episodics_dicts),
            error=None,
        )

    except ValueError as e:
        # Validation errors (invalid UUID, bad limit, etc.)
        logger.warning(f"[get_episodics_by_entity] Validation error: {e}")
        return GetEpisodicsByEntityResponse(
            success=False,
            entity_uuid=entity_uuid,
            episodics=[],
            count=0,
            error=f"Validation error: {str(e)}",
        )

    except Exception as e:
        # Unexpected errors (database connection, etc.)
        logger.error(f"[get_episodics_by_entity] Error: {e}", exc_info=True)
        return GetEpisodicsByEntityResponse(
            success=False,
            entity_uuid=entity_uuid,
            episodics=[],
            count=0,
            error=str(e),
        )


@router.post("/para-entity", response_model=CreateParaEntityResponse)
async def create_para_entity(request: CreateParaEntityRequest) -> CreateParaEntityResponse:
    """
    Create a PARA Entity node without full processing pipeline.

    This endpoint creates only the PARA Entity node in Neo4j without:
    - Entity extraction from text (L3)
    - Relationship creation
    - Embedding computation

    Use this for:
    - Manual PARA container creation (Projects, Areas, Resources, Archives)
    - Reverse workflow (graph → Obsidian note)
    - Seeding initial graph structure
    - Development and testing

    The created entity will have composite labels (e.g., :Entity:Project)
    and can be linked to episodes using relationship creation endpoints.

    Example:
        POST /api/v1/dev/para-entity
        {
            "para_type": "Project",
            "name": "Website Redesign Q1 2024",
            "summary": "Complete redesign of company website",
            "file_path": "projects/website-redesign.md",
            "attributes": {"status": "active", "priority": "high"}
        }

    Returns:
        CreateParaEntityResponse with created entity UUID and metadata
    """
    try:
        logger.info(f"[create_para_entity] Creating {request.para_type}: {request.name}")

        # Get Graphiti instance
        graphiti = await get_graphiti()
        manager = PipGraphManager(graphiti)

        # Create PARA entity without full processing
        entity = await manager.create_para_entity(
            para_type=request.para_type,
            name=request.name,
            summary=request.summary,
            group_id=request.group_id,
            file_path=request.file_path,
            attributes=request.attributes,
        )

        logger.info(
            f"[create_para_entity] Success: {request.para_type} "
            f"'{request.name}' (uuid={entity.uuid})"
        )

        return CreateParaEntityResponse(
            success=True,
            uuid=entity.uuid,
            para_type=entity.para_type,
            name=entity.name,
            created_at=entity.created_at,
            error=None,
        )

    except ValueError as e:
        # Handle invalid para_type validation error
        logger.error(f"[create_para_entity] Validation error: {e}", exc_info=True)
        return CreateParaEntityResponse(
            success=False,
            uuid=None,
            para_type=None,
            name=None,
            created_at=None,
            error=str(e),
        )
    except Exception as e:
        logger.error(f"[create_para_entity] Error: {e}", exc_info=True)
        return CreateParaEntityResponse(
            success=False,
            uuid=None,
            para_type=None,
            name=None,
            created_at=None,
            error=str(e),
        )


@router.post("/link-entity-episode", response_model=LinkEntityEpisodeResponse)
async def link_entity_to_episode(request: LinkEntityEpisodeRequest) -> LinkEntityEpisodeResponse:
    """
    Create a MENTIONS relationship between existing Episodic and Entity nodes.

    This endpoint creates only the relationship without:
    - Entity extraction from text (L3)
    - LLM processing
    - Embedding computation

    Use this for:
    - Linking manually created PARA entities to episodes
    - Retroactive relationship creation after manual node creation
    - Data migration and repair operations
    - Connecting entities created via /para-entity to episodes

    The MENTIONS edge is the only edge type that can originate from Episodic
    nodes (Graphiti architecture constraint). It uses MERGE semantics, making
    it idempotent (safe to call multiple times with same parameters).

    Example:
        POST /api/v1/dev/link-entity-episode
        {
            "episodic_uuid": "550e8400-e29b-41d4-a716-446655440000",
            "entity_uuid": "660e8400-e29b-41d4-a716-446655440111"
        }

    Returns:
        LinkEntityEpisodeResponse with created edge UUID and metadata
    """
    try:
        logger.info(
            f"[link_entity_to_episode] Creating MENTIONS: "
            f"{request.episodic_uuid} -> {request.entity_uuid}"
        )

        # Get Graphiti instance
        graphiti = await get_graphiti()
        manager = PipGraphManager(graphiti)

        # Create MENTIONS relationship
        edge = await manager.link_entity_to_episode(
            episodic_uuid=request.episodic_uuid,
            entity_uuid=request.entity_uuid,
            created_at=request.created_at,
        )

        logger.info(
            f"[link_entity_to_episode] Success: Created edge {edge.uuid} "
            f"({request.episodic_uuid} -> {request.entity_uuid})"
        )

        return LinkEntityEpisodeResponse(
            success=True,
            edge_uuid=edge.uuid,
            episodic_uuid=edge.source_node_uuid,
            entity_uuid=edge.target_node_uuid,
            created_at=edge.created_at,
            error=None,
        )

    except ValueError as e:
        # Handle node not found validation errors
        logger.error(f"[link_entity_to_episode] Validation error: {e}", exc_info=True)
        return LinkEntityEpisodeResponse(
            success=False,
            edge_uuid=None,
            episodic_uuid=None,
            entity_uuid=None,
            created_at=None,
            error=str(e),
        )
    except Exception as e:
        logger.error(f"[link_entity_to_episode] Error: {e}", exc_info=True)
        return LinkEntityEpisodeResponse(
            success=False,
            edge_uuid=None,
            episodic_uuid=None,
            entity_uuid=None,
            created_at=None,
            error=str(e),
        )


@router.post("/link-para-nodes", response_model=LinkParaNodesResponse)
async def link_para_nodes(request: LinkParaNodesRequest) -> LinkParaNodesResponse:
    """
    Create a BELONGS_TO relationship between two PARA Entity nodes.

    This endpoint creates hierarchical relationships between PARA entities
    for building organizational structures:
    - (Project)-[:BELONGS_TO]->(Area)
    - (Resource)-[:BELONGS_TO]->(Area)
    - (Area)-[:BELONGS_TO]->(Archive)

    Unlike /link-entity-episode (Episodic->Entity MENTIONS), this creates
    Entity->Entity BELONGS_TO relationships without Episodic constraints.

    Use this for:
    - Building PARA hierarchy (Projects nested in Areas, etc.)
    - Organizing knowledge graph into containers
    - Creating parent-child relationships between entities

    The BELONGS_TO edge uses MERGE semantics, making it idempotent
    (safe to call multiple times with same parameters).

    Example:
        POST /api/v1/dev/link-para-nodes
        {
            "source_entity_uuid": "550e8400-e29b-41d4-a716-446655440000",
            "target_entity_uuid": "660e8400-e29b-41d4-a716-446655440111"
        }

    Returns:
        LinkParaNodesResponse with created edge UUID and metadata
    """
    try:
        logger.info(
            f"[link_para_nodes] Creating BELONGS_TO: "
            f"{request.source_entity_uuid} -> {request.target_entity_uuid}"
        )

        # Get Graphiti instance
        graphiti = await get_graphiti()
        manager = PipGraphManager(graphiti)

        # Create BELONGS_TO relationship
        edge = await manager.link_para_nodes(
            source_entity_uuid=request.source_entity_uuid,
            target_entity_uuid=request.target_entity_uuid,
            created_at=request.created_at,
        )

        logger.info(
            f"[link_para_nodes] Success: Created edge {edge.uuid} "
            f"({request.source_entity_uuid} -> {request.target_entity_uuid})"
        )

        return LinkParaNodesResponse(
            success=True,
            edge_uuid=edge.uuid,
            source_entity_uuid=edge.source_node_uuid,
            target_entity_uuid=edge.target_node_uuid,
            created_at=edge.created_at,
            error=None,
        )

    except ValueError as e:
        # Handle entity not found validation errors
        logger.error(f"[link_para_nodes] Validation error: {e}", exc_info=True)
        return LinkParaNodesResponse(
            success=False,
            edge_uuid=None,
            source_entity_uuid=None,
            target_entity_uuid=None,
            created_at=None,
            error=str(e),
        )
    except Exception as e:
        logger.error(f"[link_para_nodes] Error: {e}", exc_info=True)
        return LinkParaNodesResponse(
            success=False,
            edge_uuid=None,
            source_entity_uuid=None,
            target_entity_uuid=None,
            created_at=None,
            error=str(e),
        )


@router.get("/para-entity/list", response_model=ListParaEntitiesResponse)
async def list_para_entities(
    request: Request,
    limit: int = Query(100, description="Maximum results (1-1000, default 100)", ge=1, le=1000),
    para_type: str | None = Query(None, description="Comma-separated PARA types (project,area,resource,archive)"),
) -> ListParaEntitiesResponse:
    """
    List PARA Entity nodes with flexible filtering.

    Lists nodes with composite labels (:Entity:Project, :Entity:Area, etc.)
    created via the /para-entity endpoint.

    Query Parameters:
    - limit: Maximum results (1-1000, default 100)
    - para_type: Comma-separated types (e.g., "project,area")
    - Any additional query params = property filters (e.g., ?status=active&priority=["high","medium"])

    Example:
        GET /api/v1/dev/para-entity/list?limit=50&para_type=project,area&status=active

    Returns:
        ListParaEntitiesResponse with entities and metadata
    """
    try:
        logger.info(f"[list_para_entities] Listing PARA entities (limit={limit}, para_type={para_type})")

        # Get Graphiti instance
        graphiti = await get_graphiti()
        manager = PipGraphManager(graphiti)

        # Extract property filters from query params (exclude known params)
        known_params = {"limit", "para_type"}
        property_filters = {}

        for key, value in request.query_params.items():
            if key not in known_params:
                # Handle array values: ?status=["active","on_hold"]
                if value.startswith("["):
                    try:
                        property_filters[key] = json.loads(value)
                    except json.JSONDecodeError:
                        property_filters[key] = value
                else:
                    property_filters[key] = value

        # Parse para_type filter (comma-separated, case-insensitive)
        para_types = []
        if para_type:
            para_types = [t.strip().lower() for t in para_type.split(",")]

        # Call manager method
        results = await manager.list_para_entities(
            limit=limit,
            para_types=para_types,
            property_filters=property_filters
        )

        logger.info(f"[list_para_entities] Found {len(results)} entities")

        return ListParaEntitiesResponse(
            success=True,
            entities=results,
            count=len(results),
            error=None
        )

    except ValueError as e:
        logger.error(f"[list_para_entities] Validation error: {e}", exc_info=True)
        return ListParaEntitiesResponse(
            success=False,
            entities=[],
            count=0,
            error=str(e)
        )
    except Exception as e:
        logger.error(f"[list_para_entities] Error: {e}", exc_info=True)
        return ListParaEntitiesResponse(
            success=False,
            entities=[],
            count=0,
            error=str(e)
        )


@router.patch("/para-entity/{entity_uuid}", response_model=UpdateParaEntityResponse)
async def update_para_entity(
    entity_uuid: str, request: UpdateParaEntityRequest
) -> UpdateParaEntityResponse:
    """
    Update mutable fields of an existing PARA Entity in place.

    Patches the entity identified by UUID, preserving all its edges (MENTIONS,
    BELONGS_TO, RELATES_TO) — unlike delete+recreate, which would drop them.

    Currently only ``summary`` is editable (S8 partial). The summary feeds the
    BM25 fulltext index used by /make-suggestions, so editing it directly
    affects which new notes get matched to this entity. The name embedding is
    not recomputed (it derives from ``name``, which is not editable here yet).

    Backs the Obsidian inspector's editable-summary field.

    Path Parameters:
    - entity_uuid: UUID of the PARA Entity to update.

    Example:
        PATCH /api/v1/dev/para-entity/660e8400-e29b-41d4-a716-446655440111
        { "summary": "Maintenance domain covering fitness, sleep, and nutrition." }

    Returns:
        UpdateParaEntityResponse with the updated entity, or an error.
    """
    try:
        logger.info(f"[update_para_entity] Updating entity: {entity_uuid}")

        graphiti = await get_graphiti()
        manager = PipGraphManager(graphiti)

        updated = await manager.update_para_entity(
            entity_uuid,
            summary=request.summary,
        )

        if updated is None:
            logger.warning(f"[update_para_entity] Entity not found: {entity_uuid}")
            return UpdateParaEntityResponse(
                success=False,
                entity=None,
                error=f"Entity not found: {entity_uuid}",
            )

        logger.info(f"[update_para_entity] Success: updated entity {entity_uuid}")
        return UpdateParaEntityResponse(
            success=True,
            entity=ParaEntityProperty(**updated),
            error=None,
        )

    except Exception as e:
        logger.error(f"[update_para_entity] Error: {e}", exc_info=True)
        return UpdateParaEntityResponse(
            success=False,
            entity=None,
            error=str(e),
        )


@router.post("/process-existing-episode", response_model=ProcessExistingEpisodeResponse)
async def process_existing_episode(
    request: ProcessExistingEpisodeRequest
) -> ProcessExistingEpisodeResponse:
    """
    Process an existing Episodic node with entity extraction.

    This endpoint processes an Episodic node that:
    - Already exists in the database
    - Is already linked to at least one PARA Entity via MENTIONS

    Unlike /process-note:
    - Does NOT create a new Episodic node
    - Updates summary of existing PARA entities linked via MENTIONS
    - Creates MENTIONS only for NEW entities (avoids duplicates)

    Use this for:
    - Processing notes after manual PARA entity assignment
    - Updating entity summaries with note content
    - Extracting additional entities from already-linked notes

    Example:
        POST /api/v1/dev/process-existing-episode
        {
            "episodic_uuid": "550e8400-e29b-41d4-a716-446655440000",
            "update_communities": false
        }

    Preconditions:
    - Episodic with given UUID must exist
    - Episodic must have at least one MENTIONS relationship to a PARA Entity

    Returns:
        ProcessExistingEpisodeResponse with processing results
    """
    try:
        logger.info(
            f"[process_existing_episode] Processing existing Episodic: {request.episodic_uuid}"
        )

        # Get Graphiti instance
        graphiti = await get_graphiti()
        manager = PipGraphManager(graphiti)

        # Process existing episode
        result = await manager.process_existing_episode(
            episodic_uuid=request.episodic_uuid,
            update_communities=request.update_communities,
        )

        # Extract results
        episode_uuid = result.episode.uuid if result.episode else None
        nodes_count = len(result.nodes) if result.nodes else 0
        edges_count = len(result.edges) if result.edges else 0
        episodic_edges_count = len(result.episodic_edges) if result.episodic_edges else 0

        # Get names of PARA entities whose summary was updated
        para_entities_updated = [
            n.name for n in result.nodes
            if hasattr(n, 'labels') and any(
                label in ('Project', 'Area', 'Resource', 'Archive')
                for label in (n.labels or [])
            )
        ]

        logger.info(
            f"[process_existing_episode] Success: episode={episode_uuid}, "
            f"nodes={nodes_count}, edges={edges_count}, "
            f"new_mentions={episodic_edges_count}, para_updated={para_entities_updated}"
        )

        return ProcessExistingEpisodeResponse(
            success=True,
            episode_uuid=episode_uuid,
            nodes_count=nodes_count,
            edges_count=edges_count,
            episodic_edges_count=episodic_edges_count,
            para_entities_updated=para_entities_updated,
            error=None,
        )

    except ValueError as e:
        # Handle validation errors (Episodic not found, no PARA entities)
        logger.error(f"[process_existing_episode] Validation error: {e}", exc_info=True)
        return ProcessExistingEpisodeResponse(
            success=False,
            episode_uuid=None,
            nodes_count=0,
            edges_count=0,
            episodic_edges_count=0,
            para_entities_updated=[],
            error=str(e),
        )
    except Exception as e:
        logger.error(f"[process_existing_episode] Error: {e}", exc_info=True)
        return ProcessExistingEpisodeResponse(
            success=False,
            episode_uuid=None,
            nodes_count=0,
            edges_count=0,
            episodic_edges_count=0,
            para_entities_updated=[],
            error=str(e),
        )


@router.post("/make-suggestions", response_model=MakeSuggestionsResponse)
async def make_suggestions(request: MakeSuggestionsRequest) -> MakeSuggestionsResponse:
    """
    Find relevant PARA entities for an episodic note using hybrid search.

    This endpoint analyzes the content of an existing episodic note and suggests
    relevant PARA entities (Projects, Areas, Resources) that the note might be
    related to. It uses Graphiti's hybrid search combining:
    - BM25 (fulltext search on entity name and summary)
    - Cosine similarity (vector search on entity name embeddings)
    - MMR reranking for result fusion

    Use this for:
    - Discovering which Projects/Areas a note might belong to
    - Auto-suggesting PARA classifications based on note content
    - Finding semantically similar entities to link to

    Example:
        POST /api/v1/dev/make-suggestions
        {
            "episodic_uuid": "550e8400-e29b-41d4-a716-446655440000",
            "limit": 10,
            "min_score": 0.5
        }

    Preconditions:
    - Episodic node with given UUID must exist in the database
    - At least one PARA entity should exist for meaningful suggestions

    Returns:
        MakeSuggestionsResponse with ranked list of relevant PARA entities
    """
    try:
        logger.info(
            f"[make_suggestions] Finding suggestions for episodic: {request.episodic_uuid} "
            f"(limit={request.limit}, min_score={request.min_score})"
        )

        # Get Graphiti instance
        graphiti = await get_graphiti()
        manager = PipGraphManager(graphiti)

        # Find relevant PARA entities
        episodic_uuid, suggestions_list = await manager.make_suggestions(
            episodic_uuid=request.episodic_uuid,
            limit=request.limit,
            min_score=request.min_score,
        )

        # Convert to Pydantic models
        suggestions = [ParaSuggestion(**s) for s in suggestions_list]

        logger.info(
            f"[make_suggestions] Success: found {len(suggestions)} suggestions "
            f"for episodic {episodic_uuid}"
        )

        return MakeSuggestionsResponse(
            success=True,
            episodic_uuid=episodic_uuid,
            suggestions=suggestions,
            count=len(suggestions),
            error=None,
        )

    except ValueError as e:
        # Handle Episodic not found validation error
        logger.error(f"[make_suggestions] Validation error: {e}", exc_info=True)
        return MakeSuggestionsResponse(
            success=False,
            episodic_uuid=None,
            suggestions=[],
            count=0,
            error=str(e),
        )
    except Exception as e:
        logger.error(f"[make_suggestions] Error: {e}", exc_info=True)
        return MakeSuggestionsResponse(
            success=False,
            episodic_uuid=None,
            suggestions=[],
            count=0,
            error=str(e),
        )


@router.delete("/node/{node_uuid}", response_model=DeleteNodeResponse)
async def delete_node(node_uuid: str) -> DeleteNodeResponse:
    """
    Delete a node (Episodic or Entity) by UUID.

    This endpoint automatically detects the node type (Episodic or Entity)
    and deletes it along with all its relationships using DETACH DELETE.

    Relationships deleted:
    - For Episodic: MENTIONS edges to entities
    - For Entity: MENTIONS edges from episodics, RELATES_TO edges to other entities

    Use cases:
    - Remove incorrectly created nodes
    - Clean up test data
    - Delete obsolete episodics or entities

    WARNING: This operation is irreversible. All relationships will be permanently deleted.

    Path Parameters:
    - node_uuid: UUID of the node to delete (Episodic or Entity)

    Example:
        DELETE /api/v1/dev/node/550e8400-e29b-41d4-a716-446655440000

    Returns:
        DeleteNodeResponse with deletion status and node type
    """
    try:
        logger.info(f"[delete_node] Deleting node: {node_uuid}")

        # Get Graphiti instance and manager
        graphiti = await get_graphiti()
        manager = PipGraphManager(graphiti)

        # Delete node (automatically detects type)
        success, node_type = await manager.delete_node(node_uuid)

        if success:
            logger.info(f"[delete_node] Successfully deleted {node_type} node: {node_uuid}")
            return DeleteNodeResponse(
                success=True,
                node_uuid=node_uuid,
                node_type=node_type,
                error=None,
            )
        else:
            logger.warning(f"[delete_node] Node not found: {node_uuid}")
            return DeleteNodeResponse(
                success=False,
                node_uuid=None,
                node_type=None,
                error=f"Node not found: {node_uuid}",
            )

    except Exception as e:
        logger.error(f"[delete_node] Error: {e}", exc_info=True)
        return DeleteNodeResponse(
            success=False,
            node_uuid=None,
            node_type=None,
            error=str(e),
        )


@router.delete("/para-entity/{entity_uuid}", response_model=DeleteParaEntityResponse)
async def delete_para_entity(entity_uuid: str) -> DeleteParaEntityResponse:
    """
    Delete a PARA Entity and cascade-delete its orphaned Episodics.

    Removes the Entity node (DETACH DELETE — MENTIONS and BELONGS_TO edges go
    with it) plus every Episodic whose *only* MENTIONS edge pointed at this
    Entity. Episodics that also mention another Entity survive, losing just
    this one edge.

    This backs the Obsidian folder-mirror flow (deleting a PARA folder removes
    notes that lived solely under it) and manual/debug cleanup.

    WARNING: Irreversible hard delete. A bi-temporal soft-invalidation model is
    the conceptual successor and is tracked separately.

    Path Parameters:
    - entity_uuid: UUID of the PARA Entity to delete.

    Example:
        DELETE /api/v1/dev/para-entity/660e8400-e29b-41d4-a716-446655440111

    Returns:
        DeleteParaEntityResponse with deletion status and orphan count.
    """
    try:
        logger.info(f"[delete_para_entity] Cascade-deleting entity: {entity_uuid}")

        graphiti = await get_graphiti()
        manager = PipGraphManager(graphiti)

        success, deleted_episodics = await manager.delete_para_entity_cascade(entity_uuid)

        if success:
            logger.info(
                f"[delete_para_entity] Deleted entity {entity_uuid} "
                f"+ {deleted_episodics} orphaned episodic(s)"
            )
            return DeleteParaEntityResponse(
                success=True,
                entity_uuid=entity_uuid,
                deleted_episodics_count=deleted_episodics,
                error=None,
            )
        else:
            logger.warning(f"[delete_para_entity] Entity not found: {entity_uuid}")
            return DeleteParaEntityResponse(
                success=False,
                entity_uuid=None,
                deleted_episodics_count=0,
                error=f"Entity not found: {entity_uuid}",
            )

    except Exception as e:
        logger.error(f"[delete_para_entity] Error: {e}", exc_info=True)
        return DeleteParaEntityResponse(
            success=False,
            entity_uuid=None,
            deleted_episodics_count=0,
            error=str(e),
        )


@router.get("/para-tree", response_model=GetParaTreeResponse)
async def get_para_tree() -> GetParaTreeResponse:
    """
    Get hierarchical PARA tree structure.

    Builds and returns a hierarchical tree of PARA entities (Projects, Areas,
    Resources, Archives) based on BELONGS_TO relationships. The tree reflects
    the organizational structure where:
    - Areas can contain Projects, Resources, or other Areas
    - Projects can contain Resources
    - Archives can contain any inactive containers

    The tree is built recursively, starting from root nodes (nodes without
    parents) and traversing down through BELONGS_TO relationships.

    Each node in the tree contains:
    - id: UUID of the entity
    - name: Entity name
    - type: PARA type (Project, Area, Resource, Archive)
    - children: List of nested child nodes (recursive structure)

    Use cases:
    - Displaying organizational hierarchy in UI
    - Navigating knowledge graph structure
    - Understanding PARA container relationships

    Example:
        GET /api/v1/dev/para-tree

    Returns:
        GetParaTreeResponse with tree structure and metadata
    """
    try:
        logger.info("[get_para_tree] Building PARA tree structure")

        # Get Graphiti instance (need driver for PARATreeBuilder)
        graphiti = await get_graphiti()
        driver = graphiti.driver

        # Build tree using PARATreeBuilder
        builder = PARATreeBuilder(driver)
        tree = await builder.build_tree()

        logger.info(f"[get_para_tree] Successfully built tree with {len(tree)} root nodes")

        return GetParaTreeResponse(
            success=True,
            tree=tree,
            count=len(tree),
            error=None,
        )

    except Exception as e:
        logger.error(f"[get_para_tree] Error building tree: {e}", exc_info=True)
        return GetParaTreeResponse(
            success=False,
            tree=[],
            count=0,
            error=str(e),
        )
