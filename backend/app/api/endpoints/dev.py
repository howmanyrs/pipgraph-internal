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
    CreateEpisodeRequest,
    CreateEpisodeResponse,
    CreateParaEntityRequest,
    CreateParaEntityResponse,
    LinkEntityEpisodeRequest,
    LinkEntityEpisodeResponse,
    ParaEntityProperty,
    ListParaEntitiesResponse,
    ProcessExistingEpisodeRequest,
    ProcessExistingEpisodeResponse,
    MakeSuggestionsRequest,
    MakeSuggestionsResponse,
    ParaSuggestion,
)
from app.services.graphiti import get_graphiti, PipGraphManager

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


@router.post("/episode", response_model=CreateEpisodeResponse)
async def create_episode(request: CreateEpisodeRequest) -> CreateEpisodeResponse:
    """
    Create an Episodic node without full processing pipeline.

    This endpoint creates only the Episodic node in Neo4j without:
    - Entity extraction (L3)
    - Edge creation
    - Community updates

    Use this for:
    - Fast note ingestion without LLM processing
    - Incremental loading of notes
    - Development and testing

    Example:
        POST /api/v1/dev/episode
        {
            "name": "Meeting Notes",
            "content": "Discussed project timeline...",
            "source_description": "Obsidian note",
            "file_path": "notes/meetings/2024-01-15.md"
        }

    Returns:
        CreateEpisodeResponse with created episode UUID and timestamp
    """
    try:
        logger.info(f"[create_episode] Creating episode: {request.name}")

        # Get Graphiti instance
        graphiti = await get_graphiti()
        manager = PipGraphManager(graphiti)

        # Use current time if not provided
        ref_time = request.reference_time or datetime.now(timezone.utc)

        # Create episode without full processing
        episode = await manager.create_episode(
            name=request.name,
            content=request.content,
            source_description=request.source_description or "Obsidian note",
            reference_time=ref_time,
            file_path=request.file_path,
            frontmatter=request.frontmatter,
        )

        logger.info(f"[create_episode] Success: uuid={episode.uuid}")

        return CreateEpisodeResponse(
            success=True,
            uuid=episode.uuid,
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
    - RRF reranking for result fusion

    Use this for:
    - Discovering which Projects/Areas a note might belong to
    - Auto-suggesting PARA classifications based on note content
    - Finding semantically similar entities to link to

    Example:
        POST /api/v1/dev/make-suggestions
        {
            "episodic_name": "notes/meeting-2024-01-15.md",
            "limit": 10,
            "min_score": 0.5
        }

    Preconditions:
    - Episodic node with given name must exist in the database
    - At least one PARA entity should exist for meaningful suggestions

    Returns:
        MakeSuggestionsResponse with ranked list of relevant PARA entities
    """
    try:
        logger.info(
            f"[make_suggestions] Finding suggestions for: {request.episodic_name} "
            f"(limit={request.limit}, min_score={request.min_score})"
        )

        # Get Graphiti instance
        graphiti = await get_graphiti()
        manager = PipGraphManager(graphiti)

        # Find relevant PARA entities
        episodic_uuid, suggestions_list = await manager.make_suggestions(
            episodic_name=request.episodic_name,
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
