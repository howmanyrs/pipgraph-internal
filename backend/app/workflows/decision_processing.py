"""
Decision Processing Helpers for Workflow.

This module contains helper functions for processing user decisions
and entity extraction in the context of PARA workflows.

Functions are organized into three sections:
1. Decision Processing (Iteration 3): Handle user decisions on suggestions
2. Helper Functions: Support functions for decision processing
3. Entity Extraction (L3): Extract entities with PARA context awareness
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Decision Processing (Iteration 3)
# ============================================================================

async def process_user_decision(
    episodic_path: str,
    user_decision,
    manager,
    driver=None
) -> Dict[str, Any]:
    """
    Process user decision on a specific suggestion.

    Handles 4 action types:
    - confirm: Transform :SUGGESTS to :IS_PART_OF (link) or update property (property_update)
    - dismiss: Delete specific :SUGGESTS, link to Inbox if no link remains
    - link_to_alternative: Delete all suggestions, create :IS_PART_OF to selected container
    - create_custom: Create new container, delete all suggestions, create :IS_PART_OF

    Args:
        episodic_path: Path to the Episodic node (file path)
        user_decision: UserDecisionPayload with action and parameters
        manager: PipGraphManager instance for DB operations
        driver: Optional Neo4j driver (creates one if None)

    Returns:
        Dict with processing result:
        - action: The action that was performed
        - success: Boolean indicating success
        - details: Additional information about the result
    """
    from app.crud.relationship_crud import RelationshipCRUD

    relationship_crud = RelationshipCRUD(driver)

    action = user_decision.action
    suggestion_id = user_decision.suggestion_id

    logger.info(f"[process_user_decision] Processing action={action} for suggestion={suggestion_id[:8]}...")

    result = {
        "action": action,
        "success": False,
        "details": {}
    }

    try:
        if action == "confirm":
            result = await _handle_confirm(
                episodic_path,
                suggestion_id,
                relationship_crud,
                manager
            )

        elif action == "dismiss":
            result = await _handle_dismiss(
                episodic_path,
                suggestion_id,
                relationship_crud,
                manager
            )

        elif action == "link_to_alternative":
            result = await _handle_link_to_alternative(
                episodic_path,
                suggestion_id,
                user_decision.selected_container_id,
                relationship_crud
            )

        elif action == "create_custom":
            result = await _handle_create_custom(
                episodic_path,
                user_decision.custom_container_type,
                user_decision.custom_container_name,
                relationship_crud,
                manager
            )

        else:
            logger.error(f"Unknown action: {action}")
            result = {
                "action": action,
                "success": False,
                "details": {"error": f"Unknown action: {action}"}
            }

        return result

    except Exception as e:
        logger.error(f"[process_user_decision] Error: {e}", exc_info=True)
        return {
            "action": action,
            "success": False,
            "details": {"error": str(e)}
        }


async def _handle_confirm(
    episodic_path: str,
    suggestion_id: str,
    relationship_crud,
    manager
) -> Dict[str, Any]:
    """
    Handle confirm action.

    For link: Transform :SUGGESTS to :IS_PART_OF
    For property_update: Update container property, delete :SUGGESTS
    """
    # Get the suggestion details
    suggestion = relationship_crud.get_suggestion_by_id(suggestion_id)

    if not suggestion:
        return {
            "action": "confirm",
            "success": False,
            "details": {"error": f"Suggestion not found: {suggestion_id}"}
        }

    suggestion_type = suggestion["suggestion_type"]
    container_id = suggestion["container_id"]
    container_type = suggestion["container_type"]

    if suggestion_type == "link":
        # Delete :SUGGESTS and create :IS_PART_OF
        relationship_crud.remove_suggestion(suggestion_id)
        link = relationship_crud.create_link(
            episodic_path,
            container_id,
            container_label=container_type
        )

        logger.info(f"✓ Confirmed link: {episodic_path} -> {suggestion['container_name']}")

        return {
            "action": "confirm",
            "success": True,
            "details": {
                "type": "link",
                "container_id": container_id,
                "container_name": suggestion["container_name"],
                "container_label": container_type,
                "link_created": bool(link)
            }
        }

    elif suggestion_type == "property_update":
        # Update the container property
        target_field = suggestion["target_field"]
        suggested_value = suggestion["suggested_value"]

        # Execute property update
        updated = _update_container_property(
            relationship_crud.driver,
            container_id,
            container_type,
            target_field,
            suggested_value
        )

        # Delete the suggestion
        relationship_crud.remove_suggestion(suggestion_id)

        logger.info(f"✓ Confirmed property update: {container_type}.{target_field} = {suggested_value}")

        return {
            "action": "confirm",
            "success": True,
            "details": {
                "type": "property_update",
                "container_id": container_id,
                "target_field": target_field,
                "new_value": suggested_value,
                "updated": updated
            }
        }

    else:
        return {
            "action": "confirm",
            "success": False,
            "details": {"error": f"Unknown suggestion_type: {suggestion_type}"}
        }


async def _handle_dismiss(
    episodic_path: str,
    suggestion_id: str,
    relationship_crud,
    manager
) -> Dict[str, Any]:
    """
    Handle dismiss action.

    Delete specific :SUGGESTS.
    If no link suggestions remain, create :IS_PART_OF to Inbox.
    """
    # Get suggestion info before deleting
    suggestion = relationship_crud.get_suggestion_by_id(suggestion_id)

    if not suggestion:
        return {
            "action": "dismiss",
            "success": False,
            "details": {"error": f"Suggestion not found: {suggestion_id}"}
        }

    # Delete the dismissed suggestion
    deleted = relationship_crud.remove_suggestion(suggestion_id)

    if not deleted:
        return {
            "action": "dismiss",
            "success": False,
            "details": {"error": "Failed to delete suggestion"}
        }

    # Check if there are remaining link suggestions
    remaining_suggestions = relationship_crud.get_suggestions(episodic_path)
    remaining_links = [s for s in remaining_suggestions if s["suggestion_type"] == "link"]

    linked_to_inbox = False

    # If no link suggestions remain and no existing :IS_PART_OF, link to Inbox
    if not remaining_links:
        existing_context = relationship_crud.get_episodic_para_context(episodic_path)

        if not existing_context:
            # Ensure Inbox exists and link to it (new manager method returns EntityNode)
            inbox = await manager.ensure_inbox_exists()
            if inbox:
                relationship_crud.create_link(
                    episodic_path,
                    inbox.uuid,  # Use UUID from EntityNode (new schema)
                    container_label="Area"
                )
                linked_to_inbox = True
                logger.info(f"✓ No links remaining, linked to Inbox: {episodic_path}")

    logger.info(f"✓ Dismissed suggestion: {suggestion_id[:8]}...")

    return {
        "action": "dismiss",
        "success": True,
        "details": {
            "dismissed_suggestion_id": suggestion_id,
            "remaining_suggestions": len(remaining_suggestions),
            "linked_to_inbox": linked_to_inbox
        }
    }


async def _handle_link_to_alternative(
    episodic_path: str,
    suggestion_id: str,
    selected_container_id: str,
    relationship_crud
) -> Dict[str, Any]:
    """
    Handle link_to_alternative action.

    Delete all suggestions and create :IS_PART_OF to selected container.
    """
    if not selected_container_id:
        return {
            "action": "link_to_alternative",
            "success": False,
            "details": {"error": "selected_container_id is required"}
        }

    # Get container info to determine label
    # First try to find it in any PARA type
    container_info = _get_container_info(relationship_crud.driver, selected_container_id)

    if not container_info:
        return {
            "action": "link_to_alternative",
            "success": False,
            "details": {"error": f"Container not found: {selected_container_id}"}
        }

    # Delete all suggestions for this episodic
    deleted_count = relationship_crud.remove_all_suggestions(episodic_path)

    # Create link to selected container
    link = relationship_crud.create_link(
        episodic_path,
        selected_container_id,
        container_label=container_info["label"]
    )

    logger.info(f"✓ Linked to alternative: {episodic_path} -> {container_info['name']}")

    return {
        "action": "link_to_alternative",
        "success": True,
        "details": {
            "container_id": selected_container_id,
            "container_name": container_info["name"],
            "container_type": container_info["label"],
            "deleted_suggestions": deleted_count,
            "link_created": bool(link)
        }
    }


async def _handle_create_custom(
    episodic_path: str,
    custom_container_type: str,
    custom_container_name: str,
    relationship_crud,
    manager
) -> Dict[str, Any]:
    """
    Handle create_custom action.

    Create new container, delete all suggestions, create :IS_PART_OF.
    """
    if not custom_container_type or not custom_container_name:
        return {
            "action": "create_custom",
            "success": False,
            "details": {"error": "custom_container_type and custom_container_name are required"}
        }

    # Validate container type
    valid_types = ["Project", "Area", "Resource"]
    if custom_container_type not in valid_types:
        return {
            "action": "create_custom",
            "success": False,
            "details": {"error": f"Invalid container type: {custom_container_type}. Must be one of: {valid_types}"}
        }

    # Create the new container using PipGraphManager (new schema with embeddings)
    try:
        container = await manager.create_para_entity(
            para_type=custom_container_type,
            name=custom_container_name,
            summary=f"Custom {custom_container_type} created by user"
        )
    except Exception as e:
        logger.error(f"[_handle_create_custom] Failed to create entity: {e}", exc_info=True)
        return {
            "action": "create_custom",
            "success": False,
            "details": {"error": f"Failed to create container: {str(e)}"}
        }

    # Delete all suggestions
    deleted_count = relationship_crud.remove_all_suggestions(episodic_path)

    # Create link to new container (use UUID from EntityNode)
    link = relationship_crud.create_link(
        episodic_path,
        container.uuid,  # EntityNode.uuid (new schema)
        container_label=custom_container_type
    )

    logger.info(f"✓ Created custom {custom_container_type}: {custom_container_name} (uuid: {container.uuid})")

    return {
        "action": "create_custom",
        "success": True,
        "details": {
            "container_id": container.uuid,  # Return UUID for consistency
            "container_name": custom_container_name,
            "container_type": custom_container_type,
            "deleted_suggestions": deleted_count,
            "link_created": bool(link)
        }
    }


# ============================================================================
# Helper Functions for Decision Processing
# ============================================================================

def _update_container_property(
    driver,
    container_id: str,
    container_type: str,
    target_field: str,
    new_value: str
) -> bool:
    """
    Update a property on a PARA container.

    Args:
        driver: Neo4j driver
        container_id: Container identifier
        container_type: Container label (Project, Area, Resource)
        target_field: Field name to update
        new_value: New value for the field

    Returns:
        True if updated, False otherwise
    """
    # Validate field name to prevent injection
    allowed_fields = {"name", "status", "goal", "description"}
    if target_field not in allowed_fields:
        logger.error(f"Invalid target_field: {target_field}")
        return False

    query = f"""
    MATCH (c:{container_type} {{id: $container_id}})
    SET c.{target_field} = $new_value
    RETURN c
    """

    with driver.session() as session:
        result = session.run(
            query,
            container_id=container_id,
            new_value=new_value
        )
        record = result.single()

        if record:
            logger.info(f"✓ Updated {container_type}.{target_field} = {new_value}")
            return True
        else:
            logger.error(f"✗ Failed to update property: {container_id}.{target_field}")
            return False


def _get_container_info(driver, container_id: str) -> Optional[Dict[str, str]]:
    """
    Get container info by ID from any PARA type.

    Args:
        driver: Neo4j driver
        container_id: Container identifier

    Returns:
        Dict with 'id', 'name', 'label' or None if not found
    """
    query = """
    MATCH (c {id: $container_id})
    WHERE c:Project OR c:Area OR c:Resource
    RETURN c.id as id, c.name as name, labels(c)[0] as label
    """

    with driver.session() as session:
        result = session.run(query, container_id=container_id)
        record = result.single()

        if record:
            return {
                "id": record["id"],
                "name": record["name"],
                "label": record["label"]
            }
        return None


def _check_remaining_link_suggestions(relationship_crud, episodic_path: str) -> List[Dict]:
    """
    Check for remaining link-type suggestions.

    Args:
        relationship_crud: RelationshipCRUD instance
        episodic_path: Path to the Episodic node

    Returns:
        List of remaining link suggestions
    """
    suggestions = relationship_crud.get_suggestions(episodic_path)
    return [s for s in suggestions if s["suggestion_type"] == "link"]


# ============================================================================
# L3 Entity Extraction (Iteration 4)
# ============================================================================

async def extract_entities_with_context(
    episodic_path: str,
    episodic_content: str,
    driver=None
) -> List:
    """
    Extract entities from note content with PARA context awareness.

    This function:
    1. Retrieves the confirmed PARA context (via :IS_PART_OF)
    2. Calls the entity extraction (mock or real Graphiti)
    3. Returns the extracted entities

    The context is used to inform entity extraction - for example,
    entities extracted from a Project note will use the project name
    in their prompts.

    Args:
        episodic_path: Path to the Episodic node (file path)
        episodic_content: Text content of the note
        driver: Optional Neo4j driver (creates one if None)

    Returns:
        List of ExtractedCandidate objects

    Raises:
        ValueError: If no confirmed PARA context exists
    """
    from app.crud.relationship_crud import RelationshipCRUD
    from app.services.mocks.mock_graphiti import extract_entities
    from app.models.entity import ExtractedCandidate

    relationship_crud = RelationshipCRUD(driver)

    # Step 1: Get confirmed context
    context = relationship_crud.get_episodic_para_context(episodic_path)

    if not context:
        error_msg = f"No confirmed PARA context for: {episodic_path}. Cannot extract entities without context."
        logger.error(f"✗ {error_msg}")
        raise ValueError(error_msg)

    logger.info(
        f"[extract_entities_with_context] Using context: "
        f"{context['container_type']} '{context['container_name']}'"
    )

    # Step 2: Prepare context dict for extraction
    extraction_context = {
        "id": context["container_id"],
        "name": context["container_name"],
        "label": context["container_type"]
    }

    # Step 3: Call entity extraction (mock or real)
    entities = extract_entities(episodic_content, extraction_context)

    logger.info(
        f"✓ Extracted {len(entities)} entities for: {episodic_path} "
        f"(context: {context['container_name']})"
    )

    return entities
