"""
PipGraph Manager - Core Note Processing Wrapper

Обертка над Graphiti для пошаговой обработки заметок с возможностью интервенции.
Вместо использования graphiti.add_episode() как "черного ящика", этот класс
разбивает процесс на отдельные этапы, позволяя вклиниваться между ними.

Ключевые точки интервенции:
1. После extract_nodes - получили "сырые" сущности из текста
2. После resolve_extracted_nodes - сопоставили с существующими в графе (ГЛАВНАЯ ТОЧКА)
3. После extract_edges - извлекли связи между сущностями
4. После resolve_extracted_edges - валидировали связи
5. Перед add_nodes_and_edges_bulk - финальное сохранение

Архитектурная идея из backend/docs/attend/pipgraph_manager_discussion.md:
- Graphiti используется как toolkit, а не как монолит
- Внутренние функции вызываются явно и последовательно
- Между этапами можно добавлять пользовательский ввод, валидацию, обогащение данных

Пример использования:
    manager = PipGraphManager(graphiti_instance)
    result = await manager.process_note(
        name="note.md",
        episode_body="Vladimir Ivanov discussed the project",
        source_description="Obsidian note",
        reference_time=datetime.now(timezone.utc)
    )
"""

import logging
from datetime import datetime
from time import time
from typing import Dict, Any, Optional, List

from pydantic import BaseModel

from graphiti_core import Graphiti
from graphiti_core.edges import (
    CommunityEdge,
    EntityEdge,
    EpisodicEdge,
)
from graphiti_core.helpers import (
    get_default_group_id,
    semaphore_gather,
    validate_excluded_entity_types,
    validate_group_id,
)
from graphiti_core.nodes import (
    CommunityNode,
    EntityNode,
    EpisodeType,
    EpisodicNode,
)
from graphiti_core.search.search_utils import RELEVANT_SCHEMA_LIMIT
from graphiti_core.utils.bulk_utils import (
    add_nodes_and_edges_bulk,
    resolve_edge_pointers,
)
from graphiti_core.utils.datetime_utils import utc_now
from graphiti_core.utils.maintenance.community_operations import update_community
from graphiti_core.utils.maintenance.edge_operations import (
    build_episodic_edges,
    extract_edges,
    resolve_extracted_edges,
)
from graphiti_core.utils.maintenance.graph_data_operations import retrieve_episodes
from graphiti_core.utils.maintenance.node_operations import (
    extract_attributes_from_nodes,
    extract_nodes,
    resolve_extracted_nodes,
)
from graphiti_core.utils.ontology_utils.entity_types_utils import validate_entity_types

# Import PARA configuration
from config.para_config import (
    PARA_ENTITY_TYPES,
    PARA_EDGE_TYPES,
    PARA_EDGE_TYPE_MAP,
)

logger = logging.getLogger(__name__)


class AddEpisodeResults(BaseModel):
    """Результаты обработки эпизода (копия из graphiti_core для совместимости)"""
    episode: EpisodicNode
    episodic_edges: list[EpisodicEdge]
    nodes: list[EntityNode]
    edges: list[EntityEdge]
    communities: list[CommunityNode]
    community_edges: list[CommunityEdge]


class PipGraphManager:
    """
    Класс-обертка над Graphiti для контролируемой обработки заметок.

    Вместо вызова graphiti.add_episode(), разбивает процесс на этапы:
    1. Извлечение сущностей (extract_nodes)
    2. Сопоставление с существующими (resolve_extracted_nodes) ← ТОЧКА ИНТЕРВЕНЦИИ
    3. Извлечение связей (extract_edges)
    4. Валидация связей (resolve_extracted_edges)
    5. Сохранение (add_nodes_and_edges_bulk)
    """

    def __init__(self, graphiti: Graphiti):
        """
        Инициализация менеджера.

        Args:
            graphiti: Сконфигурированный экземпляр Graphiti
        """
        self.graphiti = graphiti
        self.clients = graphiti.clients
        self.driver = graphiti.driver
        self.embedder = graphiti.embedder
        self.max_coroutines = graphiti.max_coroutines
        self.store_raw_episode_content = graphiti.store_raw_episode_content

    async def process_note(
        self,
        name: str,
        episode_body: str,
        source_description: str,
        reference_time: datetime,
        source: EpisodeType = EpisodeType.message,
        group_id: str | None = None,
        uuid: str | None = None,
        update_communities: bool = False,
        entity_types: dict[str, type[BaseModel]] | None = None,
        excluded_entity_types: list[str] | None = None,
        previous_episode_uuids: list[str] | None = None,
        edge_types: dict[str, type[BaseModel]] | None = None,
        edge_type_map: dict[tuple[str, str], list[str]] | None = None,
        use_para_entities: bool = True,
    ) -> AddEpisodeResults:
        """
        Обработка заметки с пошаговым извлечением сущностей и связей.

        Это копия метода add_episode из graphiti_core.Graphiti (v0.3.x),
        адаптированная для использования в PipGraph. В будущем между этапами
        будут добавлены точки интервенции для взаимодействия с пользователем.

        Parameters
        ----------
        name : str
            The name of the episode.
        episode_body : str
            The content of the episode.
        source_description : str
            A description of the episode's source.
        reference_time : datetime
            The reference time for the episode.
        source : EpisodeType, optional
            The type of the episode. Defaults to EpisodeType.message.
        group_id : str | None
            An id for the graph partition the episode is a part of.
        uuid : str | None
            Optional uuid of the episode.
        update_communities : bool
            Optional. Whether to update communities with new node information
        entity_types : dict[str, BaseModel] | None
            Optional. Dictionary mapping entity type names to their Pydantic model definitions.
            If None and use_para_entities=True, defaults to PARA entity types.
        excluded_entity_types : list[str] | None
            Optional. List of entity type names to exclude from the graph. Entities classified
            into these types will not be added to the graph. Can include 'Entity' to exclude
            the default entity type.
        previous_episode_uuids : list[str] | None
            Optional.  list of episode uuids to use as the previous episodes. If this is not provided,
            the most recent episodes by created_at date will be used.
        edge_types : dict[str, BaseModel] | None
            Optional. Dictionary mapping edge type names to their Pydantic model definitions.
            If None and use_para_entities=True, defaults to PARA edge types.
        edge_type_map : dict[tuple[str, str], list[str]] | None
            Optional. Mapping of (source_entity_type, target_entity_type) to list of allowed edge types.
            If None and use_para_entities=True, defaults to PARA edge type map.
        use_para_entities : bool
            Optional. If True (default), automatically uses PARA entity types, edge types, and edge type map
            when custom types are not provided. Set to False to use default Graphiti behavior.

        Returns
        -------
        AddEpisodeResults
            Результаты обработки: эпизод, узлы, связи, сообщества

        Notes
        -----
        Оригинальный метод из graphiti_core/graphiti.py (lines 376-573).
        Сохранен для обратной совместимости и постепенной модификации.

        PARA INTEGRATION:
        По умолчанию использует PARA entity types (Project, Area, Resource, Archive)
        для автоматической классификации заметок. Для отключения передайте use_para_entities=False.

        ТОЧКИ ДЛЯ БУДУЩЕЙ ИНТЕРВЕНЦИИ:
        - После extract_nodes: добавить подтверждение найденных сущностей
        - После resolve_extracted_nodes: ГЛАВНАЯ ТОЧКА - спросить описание новых сущностей
        - После extract_edges: добавить ручное связывание "осиротевших" заметок
        """
        try:
            start = time()
            now = utc_now()

            # Dont use custom PARA types on this stage

            # Apply PARA defaults if use_para_entities is True and custom types not provided
            # if use_para_entities:
            #     if entity_types is None:
            #         entity_types = PARA_ENTITY_TYPES
            #         logger.info("Using default PARA entity types (Project, Area, Resource, Archive)")

            #     if edge_types is None:
            #         edge_types = PARA_EDGE_TYPES
            #         logger.info("Using default PARA edge types (ContributesTo, SpawnedFrom, UsesResource)")

            #     if edge_type_map is None:
            #         edge_type_map = PARA_EDGE_TYPE_MAP
            #         logger.info("Using default PARA edge type map")

            # validate_entity_types(entity_types)

            # validate_excluded_entity_types(excluded_entity_types, entity_types)

            validate_group_id(group_id)
            # if group_id is None, use the default group id by the provider
            group_id = group_id or get_default_group_id(self.driver.provider)

            previous_episodes = (
                await retrieve_episodes(
                    self.driver,
                    reference_time,
                    last_n=RELEVANT_SCHEMA_LIMIT,
                    group_ids=[group_id],
                    source=source,
                )
                if previous_episode_uuids is None
                else await EpisodicNode.get_by_uuids(self.driver, previous_episode_uuids)
            )

            episode = (
                await EpisodicNode.get_by_uuid(self.driver, uuid)
                if uuid is not None
                else EpisodicNode(
                    name=name,
                    group_id=group_id,
                    labels=[],
                    source=source,
                    content=episode_body,
                    source_description=source_description,
                    created_at=now,
                    valid_at=reference_time,
                )
            )

            # Create default edge type map
            edge_type_map_default = (
                {('Entity', 'Entity'): list(edge_types.keys())}
                if edge_types is not None
                else {('Entity', 'Entity'): []}
            )

            # не используем кастомные типы на этом этапе
            entity_types = None
            excluded_entity_types = None 

            # ЭТАП 1: ИЗВЛЕЧЕНИЕ СЫРЫХ СУЩНОСТЕЙ
            # Extract entities as nodes
            extracted_nodes = await extract_nodes(
                self.clients, episode, previous_episodes,
                entity_types= None,  # не используем кастомные типы на этом этапе
                excluded_entity_types = None 
            )

            # TODO: ТОЧКА ИНТЕРВЕНЦИИ 1 (optional)
            # Здесь можно показать пользователю список найденных сущностей
            # и дать возможность подтвердить/отклонить их

            # ЭТАП 2: СОПОСТАВЛЕНИЕ С СУЩЕСТВУЮЩИМИ УЗЛАМИ + ИЗВЛЕЧЕНИЕ СВЯЗЕЙ
            # Extract edges and resolve nodes
            (nodes, uuid_map, _), extracted_edges = await semaphore_gather(
                resolve_extracted_nodes(
                    self.clients,
                    extracted_nodes,
                    episode,
                    previous_episodes,
                    entity_types,
                ),
                extract_edges(
                    self.clients,
                    episode,
                    extracted_nodes,
                    previous_episodes,
                    edge_type_map or edge_type_map_default,
                    group_id,
                    edge_types,
                ),
                max_coroutines=self.max_coroutines,
            )

            # TODO: ТОЧКА ИНТЕРВЕНЦИИ 2 (ГЛАВНАЯ!)
            # После resolve_extracted_nodes мы знаем, какие узлы НОВЫЕ
            # Условие: если original_node.uuid == resolved_node.uuid, то это новая сущность
            # Здесь нужно спросить у пользователя описание новых сущностей:
            # for original_node in extracted_nodes:
            #     final_uuid = uuid_map.get(original_node.uuid)
            #     final_node = next((n for n in nodes if n.uuid == final_uuid), None)
            #     if original_node.uuid == final_node.uuid:
            #         # ЭТО НОВАЯ СУЩНОСТЬ!
            #         description = await ask_user_for_description(final_node.name)
            #         if description:
            #             final_node.attributes['user_description'] = description

            # ЭТАП 3: РАЗРЕШЕНИЕ УКАЗАТЕЛЕЙ НА РЕБРА
            edges = resolve_edge_pointers(extracted_edges, uuid_map)

            # ЭТАП 4: ВАЛИДАЦИЯ СВЯЗЕЙ И ИЗВЛЕЧЕНИЕ АТРИБУТОВ
            (resolved_edges, invalidated_edges), hydrated_nodes = await semaphore_gather(
                resolve_extracted_edges(
                    self.clients,
                    edges,
                    episode,
                    nodes,
                    edge_types or {},
                    edge_type_map or edge_type_map_default,
                ),
                extract_attributes_from_nodes(
                    self.clients, nodes, episode, previous_episodes, entity_types
                ),
                max_coroutines=self.max_coroutines,
            )

            entity_edges = resolved_edges + invalidated_edges

            # TODO: ТОЧКА ИНТЕРВЕНЦИИ 3 (optional)
            # После extract_edges можно проверить "осиротевшие" заметки
            # (заметки без связей с Person/Project) и предложить связать вручную

            # ЭТАП 5: СОЗДАНИЕ ЭПИЗОДИЧЕСКИХ СВЯЗЕЙ
            episodic_edges = build_episodic_edges(nodes, episode.uuid, now)

            episode.entity_edges = [edge.uuid for edge in entity_edges]

            if not self.store_raw_episode_content:
                episode.content = ''

            # ЭТАП 6: СОХРАНЕНИЕ В БД
            await add_nodes_and_edges_bulk(
                self.driver, [episode], episodic_edges, hydrated_nodes, entity_edges, self.embedder
            )

            communities = []
            community_edges = []

            # ЭТАП 7: ОБНОВЛЕНИЕ СООБЩЕСТВ (optional)
            # Update any communities
            if update_communities:
                communities, community_edges = await semaphore_gather(
                    *[
                        update_community(self.driver, self.clients.llm_client, self.embedder, node)
                        for node in nodes
                    ],
                    max_coroutines=self.max_coroutines,
                )
            end = time()
            logger.info(f'Completed process_note in {(end - start) * 1000} ms')

            return AddEpisodeResults(
                episode=episode,
                episodic_edges=episodic_edges,
                nodes=hydrated_nodes,
                edges=entity_edges,
                communities=communities,
                community_edges=community_edges,
            )

        except Exception as e:
            raise e


# ============================================================================
# Decision Processing (Iteration 3)
# ============================================================================

async def process_user_decision(
    episodic_path: str,
    user_decision,
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
        driver: Optional Neo4j driver (creates one if None)

    Returns:
        Dict with processing result:
        - action: The action that was performed
        - success: Boolean indicating success
        - details: Additional information about the result
    """
    from app.crud.relationship_crud import RelationshipCRUD
    from app.crud.para_crud import PARAContainerCRUD
    from uuid import uuid4

    relationship_crud = RelationshipCRUD(driver)
    para_crud = PARAContainerCRUD(driver)

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
                para_crud
            )

        elif action == "dismiss":
            result = await _handle_dismiss(
                episodic_path,
                suggestion_id,
                relationship_crud,
                para_crud
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
                para_crud
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
    para_crud
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
    para_crud
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
            # Ensure Inbox exists and link to it
            inbox = para_crud.ensure_inbox_exists()
            if inbox:
                relationship_crud.create_link(
                    episodic_path,
                    inbox["id"],
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
    para_crud
) -> Dict[str, Any]:
    """
    Handle create_custom action.

    Create new container, delete all suggestions, create :IS_PART_OF.
    """
    from uuid import uuid4

    if not custom_container_type or not custom_container_name:
        return {
            "action": "create_custom",
            "success": False,
            "details": {"error": "custom_container_type and custom_container_name are required"}
        }

    # Generate ID for new container
    new_id = f"{custom_container_type.lower()}-{str(uuid4())[:8]}"

    # Create the new container
    if custom_container_type == "Project":
        container = para_crud.create_project(new_id, custom_container_name)
    elif custom_container_type == "Area":
        container = para_crud.create_area(new_id, custom_container_name)
    elif custom_container_type == "Resource":
        container = para_crud.create_resource(new_id, custom_container_name)
    else:
        return {
            "action": "create_custom",
            "success": False,
            "details": {"error": f"Invalid container type: {custom_container_type}"}
        }

    if not container:
        return {
            "action": "create_custom",
            "success": False,
            "details": {"error": "Failed to create container"}
        }

    # Delete all suggestions
    deleted_count = relationship_crud.remove_all_suggestions(episodic_path)

    # Create link to new container
    link = relationship_crud.create_link(
        episodic_path,
        new_id,
        container_label=custom_container_type
    )

    logger.info(f"✓ Created custom {custom_container_type}: {custom_container_name}")

    return {
        "action": "create_custom",
        "success": True,
        "details": {
            "container_id": new_id,
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
