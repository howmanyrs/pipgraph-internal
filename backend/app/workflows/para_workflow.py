"""
PARA Workflow - LangGraph nodes for note processing with PARA identification

Этот модуль содержит nodes для workflow обработки заметок:
1. identify_context_node - L1/L2 классификация и генерация предложений
2. apply_proposal_node - применение предложений к графу
3. wait_for_decision_node - точка прерывания для ожидания решения пользователя
4. process_decision_node - обработка решения пользователя

Архитектура:
    identify_context → apply_proposal → [check_suggestions]
                                              ↓
                                    wait_for_decision (INTERRUPT)
                                              ↓
                                    process_decision
                                              ↓
                                    [check_suggestions] → extract_content
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any

from langgraph.types import interrupt

from app.workflows.state import (
    PARAWorkflowState,
    serialize_proposal,
    deserialize_user_decision,
    serialize_entities,
    deserialize_entities,
)
from app.services.para import classify_note_para, generate_para_proposal
from app.services.proposal_manager import apply_proposal_to_graph
from app.services.pipgraph_manager import process_user_decision, extract_entities_with_context
from app.crud.relationship_crud import RelationshipCRUD
from app.crud.entity_crud import EntityCRUD

logger = logging.getLogger(__name__)


# ============================================================================
# Workflow Nodes
# ============================================================================

async def identify_context_node(state: PARAWorkflowState) -> dict:
    """
    Node 1: L1/L2 PARA Context Identification.

    Классифицирует заметку по типу PARA (L1) и генерирует предложения (L2).

    Uses mock implementations from app.services.para:
    - classify_note_para() - возвращает PARA тип
    - generate_para_proposal() - возвращает PARAProposal с кандидатами

    Returns:
        dict с полями:
        - para_type: str - классифицированный тип ("Project", "Area", "Resource")
        - proposal: dict - сериализованное предложение
        - container_label: str - label для Neo4j queries
        - status: str - "processing"
    """
    note_path = state["note_path"]
    note_content = state["note_content"]

    logger.info(f"[identify_context_node] Processing: {note_path}")

    try:
        # L1: Classify note PARA type
        para_type = classify_note_para(note_content)
        logger.info(f"[identify_context_node] L1 Classification: {para_type}")

        # L2: Generate proposal with candidates
        # TODO: In future, pass para_type to guide proposal generation
        """
        # TODO: Надо уточнить где делать поиск уже существующих узлов с подходящим типом.
        в методе classify_note_para мы уже можем искать возможные релевантные узлы,
        т.е. кандидаты уже становятся известны
        """
        proposal = generate_para_proposal(note_content)
        logger.info(
            f"[identify_context_node] L2 Generated proposal with "
            f"{len(proposal.all_candidates())} candidates"
        )

        # Serialize proposal for state persistence
        serialized_proposal = serialize_proposal(proposal)

        return {
            "para_type": para_type,
            "proposal": serialized_proposal,
            "container_label": para_type,  # Use para_type as container label
            "status": "processing",
        }

    except Exception as e:
        logger.error(f"[identify_context_node] Error: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "para_type": "",
            "proposal": None,
        }


async def apply_proposal_node(state: PARAWorkflowState) -> dict:
    """
    Node 2: Apply Proposal to Graph.

    Применяет предложение к графу Neo4j, создавая :SUGGESTS или :IS_PART_OF связи.

    Uses proposal_manager.apply_proposal_to_graph() which:
    - Creates :IS_PART_OF for high-confidence links (> 0.95)
    - Creates :SUGGESTS for lower confidence proposals

    Returns:
        dict с полями:
        - pending_suggestions: list[str] - IDs созданных suggestions
        - status: str - "processing"
    """
    note_path = state["note_path"]
    proposal_data = state.get("proposal")
    container_label = state.get("container_label", "Project")

    logger.info(f"[apply_proposal_node] Applying proposal for: {note_path}")

    if not proposal_data:
        logger.warning("[apply_proposal_node] No proposal to apply")
        return {
            "pending_suggestions": [],
            "status": "processing",
        }

    try:
        # Reconstruct PARAProposal from serialized data
        from app.models.proposal import PARAProposal, PARACandidate

        primary = PARACandidate(**proposal_data["primary_candidate"])
        alternatives = [
            PARACandidate(**alt) for alt in proposal_data.get("alternatives", [])
        ]
        proposal = PARAProposal(
            primary_candidate=primary,
            alternatives=alternatives
        )

        # Apply proposal to graph
        result = apply_proposal_to_graph(
            episodic_path=note_path,
            proposal=proposal,
            container_label=container_label
        )

        pending_suggestions = result.get("created_suggestions", [])

        logger.info(
            f"[apply_proposal_node] Created {len(pending_suggestions)} suggestions, "
            f"{len(result.get('created_links', []))} auto-links"
        )

        return {
            "pending_suggestions": pending_suggestions,
            "status": "processing",
        }

    except Exception as e:
        logger.error(f"[apply_proposal_node] Error: {e}", exc_info=True)
        return {
            "pending_suggestions": [],
            "status": "error",
            "error": str(e),
        }


async def wait_for_decision_node(state: PARAWorkflowState) -> dict:
    """
    Node 3: Wait for User Decision (INTERRUPT).

    Точка прерывания workflow для ожидания решения пользователя.
    Возвращает текущие pending suggestions для UI.

    The workflow will pause here until resume is called with user decision.

    Returns:
        dict с полями:
        - current_suggestion_id: str - ID первого pending suggestion (для UI)
        - user_decision: dict - решение пользователя (заполняется после resume)
        - status: str - "waiting_user"
    """
    note_path = state["note_path"]
    pending_suggestions = state.get("pending_suggestions", [])

    logger.info(f"[wait_for_decision_node] Waiting for user decision on: {note_path}")

    if not pending_suggestions:
        logger.info("[wait_for_decision_node] No pending suggestions, skipping interrupt")
        return {
            "current_suggestion_id": None,
            "user_decision": None,
            "status": "processing",
        }

    # Get full suggestion details for UI
    relationship_crud = RelationshipCRUD()
    suggestions_data = relationship_crud.get_suggestions(note_path)

    # Prepare data for client
    interrupt_data = {
        "note_path": note_path,
        "suggestions": suggestions_data,
        "first_suggestion_id": pending_suggestions[0] if pending_suggestions else None,
    }

    logger.info(
        f"[wait_for_decision_node] Interrupting with {len(suggestions_data)} suggestions"
    )

    # === INTERRUPT: workflow stops here ===
    # Returns suggestions to client and waits for user decision
    user_decision = interrupt(interrupt_data)

    logger.info(f"[wait_for_decision_node] Received decision: {user_decision}")

    return {
        "current_suggestion_id": pending_suggestions[0] if pending_suggestions else None,
        "user_decision": user_decision,
        "status": "processing",
    }


async def process_decision_node(state: PARAWorkflowState) -> dict:
    """
    Node 4: Process User Decision.

    Обрабатывает решение пользователя по конкретному suggestion.
    Использует process_user_decision() из pipgraph_manager.

    Handles actions:
    - confirm: Transform :SUGGESTS to :IS_PART_OF or update property
    - dismiss: Delete suggestion, link to Inbox if no links remain
    - link_to_alternative: Link to different container
    - create_custom: Create new container and link

    Returns:
        dict с полями:
        - pending_suggestions: list[str] - обновленный список pending suggestions
        - confirmed_context: dict - информация о контексте после подтверждения
        - status: str - "processing"
    """
    note_path = state["note_path"]
    user_decision_data = state.get("user_decision")

    logger.info(f"[process_decision_node] Processing decision for: {note_path}")

    if not user_decision_data:
        logger.warning("[process_decision_node] No user decision to process")
        return {
            "pending_suggestions": state.get("pending_suggestions", []),
            "status": "processing",
        }

    try:
        # Deserialize user decision
        user_decision = deserialize_user_decision(user_decision_data)

        # Process the decision
        result = await process_user_decision(
            episodic_path=note_path,
            user_decision=user_decision
        )

        if not result.get("success"):
            error = result.get("details", {}).get("error", "Unknown error")
            logger.error(f"[process_decision_node] Decision failed: {error}")
            return {
                "pending_suggestions": state.get("pending_suggestions", []),
                "status": "error",
                "error": error,
            }

        # Update pending suggestions list
        # Remove processed suggestion from pending list
        pending = state.get("pending_suggestions", [])
        processed_id = user_decision.suggestion_id
        if processed_id in pending:
            pending.remove(processed_id)

        # Get updated context if link was created
        confirmed_context = None
        relationship_crud = RelationshipCRUD()
        context = relationship_crud.get_episodic_para_context(note_path)
        if context:
            confirmed_context = context

        logger.info(
            f"[process_decision_node] Decision processed: {result.get('action')}, "
            f"remaining suggestions: {len(pending)}"
        )

        return {
            "pending_suggestions": pending,
            "confirmed_context": confirmed_context,
            "user_decision": None,  # Clear for next iteration
            "status": "processing",
        }

    except Exception as e:
        logger.error(f"[process_decision_node] Error: {e}", exc_info=True)
        return {
            "pending_suggestions": state.get("pending_suggestions", []),
            "status": "error",
            "error": str(e),
        }


# ============================================================================
# Future Nodes (Iteration 4)
# ============================================================================

async def extract_content_node(state: PARAWorkflowState) -> dict:
    """
    Node 5: L3 Context-Aware Entity Extraction.

    Извлекает сущности с учетом PARA контекста.
    Uses extract_entities_with_context() from pipgraph_manager.

    Returns:
        dict с полями:
        - extracted_entities: list[dict] - сериализованные извлеченные сущности
        - status: str - "processing"
    """
    note_path = state["note_path"]
    note_content = state["note_content"]

    logger.info(f"[extract_content_node] Extracting entities for: {note_path}")

    try:
        # Extract entities using context from confirmed :IS_PART_OF
        entities = await extract_entities_with_context(
            episodic_path=note_path,
            episodic_content=note_content
        )

        # Serialize entities for state persistence
        serialized_entities = serialize_entities(entities)

        logger.info(
            f"[extract_content_node] Extracted {len(entities)} entities for: {note_path}"
        )

        return {
            "extracted_entities": serialized_entities,
            "status": "processing",
        }

    except ValueError as e:
        # No context available - this is expected if no :IS_PART_OF exists
        logger.error(f"[extract_content_node] Context error: {e}")
        return {
            "extracted_entities": [],
            "status": "error",
            "error": str(e),
        }

    except Exception as e:
        logger.error(f"[extract_content_node] Error: {e}", exc_info=True)
        return {
            "extracted_entities": [],
            "status": "error",
            "error": str(e),
        }


async def save_entities_node(state: PARAWorkflowState) -> dict:
    """
    Node 6: Save Extracted Entities.

    Сохраняет извлеченные сущности в Neo4j с созданием :MENTIONS связей.
    Uses EntityCRUD.batch_save_entities().

    Returns:
        dict с полями:
        - processing_completed_at: str - ISO timestamp
        - status: str - "completed"
    """
    note_path = state["note_path"]
    extracted_entities_data = state.get("extracted_entities", [])

    logger.info(f"[save_entities_node] Saving {len(extracted_entities_data)} entities for: {note_path}")

    if not extracted_entities_data:
        logger.info("[save_entities_node] No entities to save")
        completed_at = datetime.now(timezone.utc).isoformat()
        return {
            "processing_completed_at": completed_at,
            "status": "completed",
        }

    try:
        # Deserialize entities from state
        entities = deserialize_entities(extracted_entities_data)

        # Save entities and create :MENTIONS relationships
        entity_crud = EntityCRUD()
        result = entity_crud.batch_save_entities(
            entities=entities,
            episodic_path=note_path
        )

        logger.info(
            f"[save_entities_node] Saved {result['saved_count']} entities, "
            f"linked {result['linked_count']} to {note_path}"
        )

        completed_at = datetime.now(timezone.utc).isoformat()

        return {
            "processing_completed_at": completed_at,
            "status": "completed",
        }

    except Exception as e:
        logger.error(f"[save_entities_node] Error: {e}", exc_info=True)
        return {
            "processing_completed_at": None,
            "status": "error",
            "error": str(e),
        }
