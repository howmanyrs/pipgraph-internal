"""
Development/testing endpoints.

Provides direct access to core functionality for development and testing purposes.
Bypasses the workflow system for immediate processing.
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Query

from app.api.schemas.dev import (
    ProcessNoteRequest,
    ProcessNoteResponse,
    GetEpisodicResponse,
    ListEpisodicResponse,
    CreateEpisodeRequest,
    CreateEpisodeResponse,
    CreateParaEntityRequest,
    CreateParaEntityResponse,
)
from app.services.graphiti import get_graphiti, PipGraphManager
from app.crud import episodic_crud

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

        # Initialize CRUD
        crud = episodic_crud.EpisodicCRUD()

        # Get episodic from database
        episodic = crud.get_episodic(note_path)

        if episodic:
            logger.info(f"[get_episodic_by_path] Found episodic: {note_path}")
            return GetEpisodicResponse(
                success=True,
                episodic=episodic,
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

        # Initialize CRUD
        crud = episodic_crud.EpisodicCRUD()

        # Get all episodics from database
        episodics = crud.list_all_episodic(limit=limit)

        logger.info(f"[list_all_episodic] Found {len(episodics)} episodic nodes")

        # Log all names for debugging
        if episodics:
            names = [e.get("name") for e in episodics]
            logger.info(f"[list_all_episodic] Names: {names}")

        return ListEpisodicResponse(
            success=True,
            episodics=episodics,
            count=len(episodics),
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
            "obsidian_path": "notes/meetings/2024-01-15.md"
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
            obsidian_path=request.obsidian_path,
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
            "obsidian_path": "projects/website-redesign.md",
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
            uuid=request.uuid,
            group_id=request.group_id,
            obsidian_path=request.obsidian_path,
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
