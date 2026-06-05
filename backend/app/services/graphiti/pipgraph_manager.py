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

import json
import logging
import posixpath
from datetime import datetime
from time import time
from typing import Dict, Any, Optional, List, TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.models.nodes import PipGraphEpisodicNode, PipGraphEntityNode

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
from graphiti_core.search.search import search
from graphiti_core.search.search_config import (
    NodeReranker,
    NodeSearchConfig,
    NodeSearchMethod,
    SearchConfig,
)
from graphiti_core.search.search_filters import SearchFilters
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
# Import name generator for automatic episode naming
from app.services.graphiti.name_generator import generate_episode_name

logger = logging.getLogger(__name__)


class AddEpisodeResults(BaseModel):
    """Результаты обработки эпизода (копия из graphiti_core для совместимости)"""
    episode: EpisodicNode
    episodic_edges: list[EpisodicEdge]
    nodes: list[EntityNode]
    edges: list[EntityEdge]
    communities: list[CommunityNode]
    community_edges: list[CommunityEdge]


class CrossFolderFilePathError(Exception):
    """Raised by ``update_episodic_file_path`` when a patch would move an
    Episodic's ``file_path`` to a *different* folder.

    The narrow ``PATCH /episodic/{uuid}`` is a pure binding-setter — it does not
    touch ``MENTIONS`` edges. A cross-folder move is a *placement* change and
    belongs to the move+link operation (cluster decision E7), which sets
    ``file_path`` and ``MENTIONS`` together. Letting the bare setter silently
    move the path would leave the graph's placement out of sync, so the guard
    rejects it as an expected refusal (caller → ``200 {success:false}``), not a
    bug. See episodic-linking cluster decision E6.
    """


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

    @staticmethod
    def _guard_summaries(
        stage: str,
        summaries_before: dict[str, str],
        hydrated_nodes: list,
    ) -> None:
        """Guard against the empty-summary wipe (variant G).

        ``extract_attributes_from_nodes`` (graphiti) mutates each node in place via
        ``node.summary = summary_response.get('summary', '')``. A blank/failed LLM
        summary response therefore overwrites a previously-good summary with '', and
        the next bulk save persists the wipe — silently.

        This compares the pre-call snapshot against the hydrated nodes and, on any
        non-empty → empty transition, **restores the previous summary** in place
        before the bulk save sees it. ``node.summary`` has no derived embedding (only
        ``name`` is embedded), so the restore is safe. We mutate the same node objects
        that flow into ``add_nodes_and_edges_bulk``.

        "Better to warn and keep the old value than to write a regression." Pair with
        the ``[extract_summary]`` log in CloudRuPatchedClient for the raw LLM response.
        """
        for node in hydrated_nodes:
            before = summaries_before.get(node.uuid, "")
            after = node.summary or ""
            if before and not after:
                logger.warning(
                    f"[{stage}] SUMMARY WIPE BLOCKED: '{node.name}' (uuid={node.uuid}) "
                    f"— LLM returned empty summary; keeping previous (len={len(before)})"
                )
                node.summary = before
            elif not after:
                logger.info(
                    f"[{stage}] summary still empty for '{node.name}' (uuid={node.uuid})"
                )

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
            # Snapshot summaries before extract_attributes mutates nodes in place
            # (empty-summary bug — see _log_summary_changes).
            summaries_before = {n.uuid: (n.summary or "") for n in nodes}
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
            self._guard_summaries("process_note", summaries_before, hydrated_nodes)

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

    async def create_episode(
        self,
        content: str,
        source_description: str,
        reference_time: datetime,
        name: str | None = None,
        source: EpisodeType = EpisodeType.text,
        group_id: str | None = None,
        file_path: str | None = None,
        frontmatter: dict | None = None,
        uuid: str | None = None,
        status: str | None = None,
    ):
        """
        Create and save only an Episodic node without full processing pipeline.

        Unlike process_note(), this method:
        - Does NOT perform entity extraction (L3)
        - Does NOT create Entity nodes and edges
        - Does NOT update communities
        - Automatically generates meaningful name from content if not provided

        Use cases:
        - Fast note ingestion without LLM processing
        - Incremental loading of notes
        - Development and testing

        Args:
            content: Raw content of the note
            source_description: Description of the data source
            reference_time: When the note was created/modified
            name: Optional name for the episode. If None, will be auto-generated
                  from content using LLM. Auto-generated names are concise,
                  descriptive, and filesystem-compatible (suitable for .md files).
            source: Type of episode (default: text)
            group_id: Graph partition ID (defaults to provider default)
            file_path: Path to note in Obsidian vault
            frontmatter: YAML frontmatter from note
            uuid: Optional externally-supplied UUID (e.g. a client-generated
                  ``crypto.randomUUID()``). When provided, the node is saved with
                  this UUID; Graphiti's save query ``MERGE``es on it, so a retry
                  with the same UUID upserts the same node instead of duplicating
                  it (idempotent outbox delivery — see process-queue plan, OQ-1).
                  When ``None``, Pydantic's ``default_factory`` generates one.
            status: Optional transient status to stamp at creation
                  (e.g. ``"processing"`` when an async naming job is enqueued).

        Returns:
            PipGraphEpisodicNode: Created and saved episode node

        Example:
            >>> # Auto-generate name from content
            >>> episode = await manager.create_episode(
            ...     content="Today we discussed the new API architecture...",
            ...     source_description="Meeting notes"
            ... )
            >>> print(episode.name)  # "API Architecture Discussion"

            >>> # Or provide explicit name
            >>> episode = await manager.create_episode(
            ...     content="...",
            ...     name="Custom Episode Title",
            ...     source_description="Manual entry"
            ... )
        """
        from app.models.nodes import PipGraphEpisodicNode

        now = utc_now()

        validate_group_id(group_id)
        group_id = group_id or get_default_group_id(self.driver.provider)

        # Auto-generate name if not provided
        if not name:
            logger.info("[create_episode] Auto-generating episode name from content")
            name = await generate_episode_name(
                episode_body=content,
                llm_client=self.clients.llm_client
            )
            logger.info(f"[create_episode] Generated name: '{name}'")

        # Create PipGraph-extended episode. When `uuid` is supplied it is used as-is
        # (passed conditionally — an explicit `uuid=None` would override the
        # default_factory with None instead of letting it generate one).
        episode = PipGraphEpisodicNode(
            name=name,
            group_id=group_id,
            labels=[],
            source=source,
            content=content if self.store_raw_episode_content else '',
            source_description=source_description,
            created_at=now,
            valid_at=now,  # NOTE: Temporarily use current time as valid_at
            entity_edges=[],
            file_path=file_path,
            frontmatter=frontmatter or {},
            status=status,
            **({"uuid": uuid} if uuid else {}),
        )

        # Save to Neo4j using Graphiti's save mechanism
        await episode.save(self.driver)

        logger.info(f"Created episode: {episode.uuid} ({name})")

        return episode

    async def create_para_entity(
        self,
        para_type: str,
        name: str,
        summary: str = "",
        group_id: str | None = None,
        file_path: str | None = None,
        attributes: dict | None = None,
    ):
        """
        Create and save a PARA Entity node without full processing pipeline.

        Unlike process_note(), this method:
        - Does NOT extract entities from text
        - Does NOT create relationships
        - Computes name embedding for vector similarity search

        Use cases:
        - Manual PARA container creation
        - Reverse workflow (graph → Obsidian note)
        - Testing and development
        - Seeding initial graph structure

        Args:
            para_type: PARA classification ("Project", "Area", "Resource", "Archive")
            name: Entity display name
            summary: Description/summary of the entity (default: empty string)
            group_id: Graph partition ID (defaults to provider default)
            file_path: Optional path to source note in Obsidian vault
            attributes: Optional custom attributes dict (default: empty dict)

        Returns:
            PipGraphEntityNode: Created and saved entity node (UUID auto-generated)

        Raises:
            ValueError: If para_type is not valid PARA type

        Example:
            >>> entity = await manager.create_para_entity(
            ...     para_type="Project",
            ...     name="Website Redesign Q1 2024",
            ...     summary="Complete redesign of company website",
            ...     file_path="projects/website-redesign.md"
            ... )
        """
        from app.models.nodes import PipGraphEntityNode

        # Validate PARA type
        VALID_PARA_TYPES = ["Project", "Area", "Resource", "Archive"]
        if para_type not in VALID_PARA_TYPES:
            raise ValueError(
                f"Invalid para_type '{para_type}'. Must be one of: {VALID_PARA_TYPES}"
            )

        # Validate and set group_id
        validate_group_id(group_id)
        group_id = group_id or get_default_group_id(self.driver.provider)

        # Get current timestamp
        now = utc_now()

        # Prepare labels
        # CRITICAL: Only pass [para_type], Graphiti auto-adds "Entity"
        # Result: :Entity:Project composite label
        labels = [para_type]

        # Create PipGraphEntityNode instance (UUID auto-generated by Pydantic default_factory)
        entity = PipGraphEntityNode(
            name=name,
            group_id=group_id,
            labels=labels,  # ["Project"] → Graphiti saves as :Entity:Project
            created_at=now,
            summary=summary,
            name_embedding=None,  # Will be generated below
            attributes=attributes or {},
            para_type=para_type,  # PipGraph extension field
            file_path=file_path,  # PipGraph extension field
        )

        # Generate name embedding (required by Neo4j vector property)
        await entity.generate_name_embedding(self.embedder)

        # Save to Neo4j using Graphiti's save mechanism
        await entity.save(self.driver)

        logger.info(f"Created PARA entity: {para_type} '{name}' (uuid: {entity.uuid})")

        return entity

    async def update_para_entity(
        self,
        uuid: str,
        *,
        summary: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Update mutable fields of an existing PARA Entity in place.

        Patches only the fields passed (others stay untouched) while preserving
        the entity's UUID and all its MENTIONS / BELONGS_TO / RELATES_TO edges —
        unlike delete+recreate, which would drop them.

        Currently only ``summary`` is supported. It is the field the Obsidian
        inspector edits and the field BM25 fulltext search reads in
        ``make_suggestions``; updating the Neo4j property is enough for the
        fulltext index to pick it up. ``name_embedding`` is intentionally NOT
        recomputed — it is derived from ``name``, which this method does not
        change. Editing ``name`` / ``file_path`` is the remaining S8 work and is
        not handled here yet.

        Args:
            uuid: UUID of the PARA Entity to update.
            summary: New summary text. ``None`` = leave unchanged.

        Returns:
            Dict with the updated entity (same shape as ``list_para_entities``
            items), or ``None`` if no Entity with that UUID exists.
        """
        # Build the SET clause from the fields actually provided.
        set_clauses = []
        params: Dict[str, Any] = {"uuid": uuid}
        if summary is not None:
            set_clauses.append("n.summary = $summary")
            params["summary"] = summary

        if set_clauses:
            mutate_query = f"""
            MATCH (n:Entity {{uuid: $uuid}})
            SET {', '.join(set_clauses)}
            RETURN count(n) AS matched
            """
        else:
            # No-op patch — still verify the entity exists so the caller can
            # distinguish "found, nothing to change" from "not found".
            mutate_query = """
            MATCH (n:Entity {uuid: $uuid})
            RETURN count(n) AS matched
            """

        projection_query = """
        MATCH (n:Entity {uuid: $uuid})
        RETURN
            n.uuid as uuid,
            n.name as name,
            [label IN labels(n) WHERE label <> 'Entity'][0] as para_type,
            n.created_at as created_at,
            n.summary as summary,
            properties(n) as all_properties
        LIMIT 1
        """

        async with self.driver.session() as session:
            matched = await (await session.run(mutate_query, **params)).single()
            if not matched or matched["matched"] == 0:
                logger.warning(f"[update_para_entity] Entity not found: uuid={uuid}")
                return None

            record = await (await session.run(projection_query, uuid=uuid)).single()

        all_props = dict(record["all_properties"])
        system_fields = {"uuid", "name", "created_at", "summary", "name_embedding", "group_id", "labels"}
        attributes = {k: v for k, v in all_props.items() if k not in system_fields}

        logger.info(
            f"[update_para_entity] Updated entity {uuid} "
            f"(summary={'set' if summary is not None else 'unchanged'})"
        )

        return {
            "uuid": record["uuid"],
            "name": record["name"],
            "para_type": record["para_type"],
            "created_at": self._serialize_datetime(record["created_at"]),
            "summary": record["summary"],
            # file_path is a scalar in attributes; surface it top-level (R1).
            "file_path": all_props.get("file_path"),
            "attributes": attributes,
        }

    async def link_entity_to_episode(
        self,
        episodic_uuid: str,
        entity_uuid: str,
        created_at: datetime | None = None,
    ):
        """
        Create a MENTIONS relationship between existing Episodic and Entity nodes.

        Unlike process_note(), this method creates ONLY the relationship
        without entity extraction or LLM processing. This is useful for:
        - Linking manually created PARA entities to episodes
        - Retroactive relationship creation after manual node creation
        - Data migration and repair operations
        - Connecting entities created via create_para_entity() to episodes

        The MENTIONS edge is the only edge type that can originate from Episodic
        nodes (Graphiti architecture constraint). It represents a temporal reference:
        "Episode X mentioned Entity Y at time Z".

        This method uses Graphiti's EpisodicEdge.save() with MERGE semantics,
        making it idempotent (safe to call multiple times with same parameters).

        Args:
            episodic_uuid: UUID of existing Episodic node
            entity_uuid: UUID of existing Entity node
            created_at: Optional timestamp for the relationship (defaults to current time)

        Returns:
            EpisodicEdge: Created MENTIONS relationship object with properties:
                - uuid: Unique identifier for the edge
                - source_node_uuid: Episodic node UUID
                - target_node_uuid: Entity node UUID
                - group_id: Graph partition ID (inherited from entity)
                - created_at: Timestamp when relationship was created

        Raises:
            ValueError: If entity node not found in database
            ValueError: If episodic node not found in database

        Example:
            >>> # Create entity and episode first
            >>> entity = await manager.create_para_entity(
            ...     para_type="Project",
            ...     name="Website Redesign"
            ... )
            >>> episode = await manager.create_episode(
            ...     name="meeting-notes.md",
            ...     content="Discussed website redesign"
            ... )
            >>> # Link them together
            >>> edge = await manager.link_entity_to_episode(
            ...     episodic_uuid=episode.uuid,
            ...     entity_uuid=entity.uuid
            ... )
            >>> print(f"Created MENTIONS edge: {edge.uuid}")
        """
        from graphiti_core.edges import EpisodicEdge
        from graphiti_core.nodes import EntityNode, EpisodicNode
        from graphiti_core.utils.datetime_utils import utc_now

        # Set created_at to current time if not provided
        now = created_at or utc_now()

        # Fetch entity to get group_id (entities always have group_id)
        entity = await EntityNode.get_by_uuid(self.driver, entity_uuid)
        if not entity:
            raise ValueError(f"Entity not found: {entity_uuid}")

        # Verify episodic exists (strict validation for clear error messages)
        episodic = await EpisodicNode.get_by_uuid(self.driver, episodic_uuid)
        if not episodic:
            raise ValueError(f"Episodic not found: {episodic_uuid}")

        # Create EpisodicEdge object
        edge = EpisodicEdge(
            source_node_uuid=episodic_uuid,
            target_node_uuid=entity_uuid,
            created_at=now,
            group_id=entity.group_id,
        )

        # Save to Neo4j using Graphiti's MERGE query (idempotent)
        await edge.save(self.driver)

        logger.info(
            f"Created MENTIONS: {episodic.name} -> {entity.name} (edge_uuid: {edge.uuid})"
        )

        return edge

    async def link_para_nodes(
        self,
        source_entity_uuid: str,
        target_entity_uuid: str,
        created_at: datetime | None = None,
    ):
        """
        Create a BELONGS_TO relationship between two PARA Entity nodes.

        Unlike link_entity_to_episode() which creates Episodic->Entity MENTIONS,
        this method creates Entity->Entity BELONGS_TO relationships for building
        hierarchical PARA structures:
        - (Project)-[:BELONGS_TO]->(Area)
        - (Resource)-[:BELONGS_TO]->(Area)
        - (Area)-[:BELONGS_TO]->(Archive)

        This enables organizational hierarchies without Episodic constraints.
        Uses PipGraphBelongsToEdge with MERGE semantics, making it idempotent.

        Args:
            source_entity_uuid: UUID of source Entity (child node)
            target_entity_uuid: UUID of target Entity (parent node)
            created_at: Optional timestamp for the relationship (defaults to current time)

        Returns:
            PipGraphBelongsToEdge: Created BELONGS_TO relationship object with properties:
                - uuid: Unique identifier for the edge
                - source_node_uuid: Source Entity UUID
                - target_node_uuid: Target Entity UUID
                - group_id: Graph partition ID (inherited from source entity)
                - created_at: Timestamp when relationship was created

        Raises:
            ValueError: If source entity not found in database
            ValueError: If target entity not found in database

        Example:
            >>> # Create entities first
            >>> project = await manager.create_para_entity(
            ...     para_type="Project",
            ...     name="Website Redesign"
            ... )
            >>> area = await manager.create_para_entity(
            ...     para_type="Area",
            ...     name="Digital Marketing"
            ... )
            >>> # Link them: Project belongs to Area
            >>> edge = await manager.link_para_nodes(
            ...     source_entity_uuid=project.uuid,
            ...     target_entity_uuid=area.uuid
            ... )
            >>> print(f"Created BELONGS_TO edge: {edge.uuid}")
        """
        from graphiti_core.nodes import EntityNode
        from graphiti_core.utils.datetime_utils import utc_now
        from app.models.edges import PipGraphBelongsToEdge

        # Set created_at to current time if not provided
        now = created_at or utc_now()

        # Fetch source entity to get group_id (entities always have group_id)
        source_entity = await EntityNode.get_by_uuid(self.driver, source_entity_uuid)
        if not source_entity:
            raise ValueError(f"Source entity not found: {source_entity_uuid}")

        # Verify target entity exists (strict validation for clear error messages)
        target_entity = await EntityNode.get_by_uuid(self.driver, target_entity_uuid)
        if not target_entity:
            raise ValueError(f"Target entity not found: {target_entity_uuid}")

        # Create PipGraphBelongsToEdge object
        edge = PipGraphBelongsToEdge(
            source_node_uuid=source_entity_uuid,
            target_node_uuid=target_entity_uuid,
            created_at=now,
            group_id=source_entity.group_id,
        )

        # Save to Neo4j using MERGE query (idempotent)
        await edge.save(self.driver)

        logger.info(
            f"Created BELONGS_TO: {source_entity.name} -> {target_entity.name} (edge_uuid: {edge.uuid})"
        )

        return edge

    async def process_existing_episode(
        self,
        episodic_uuid: str,
        update_communities: bool = False,
        entity_types: dict[str, type[BaseModel]] | None = None,
        edge_types: dict[str, type[BaseModel]] | None = None,
        edge_type_map: dict[tuple[str, str], list[str]] | None = None,
    ) -> AddEpisodeResults:
        """
        Обработка существующего Episodic узла с извлечением сущностей.

        В отличие от process_note():
        - НЕ создаёт новый Episodic (использует существующий)
        - Обновляет summary у PARA Entity, уже связанных через MENTIONS
        - Создаёт MENTIONS только для НОВЫХ сущностей (избегает дубликатов)

        Алгоритм:
        1. Получить существующий Episodic по UUID
        2. Найти связанные PARA Entity через MENTIONS
        3. Извлечь сущности из контента (extract_nodes)
        4. Сопоставить с существующими (resolve_extracted_nodes)
        5. Добавить PARA Entity в nodes для обновления summary
        6. Разделить nodes: все для summary, только новые для MENTIONS
        7. Сохранить в БД

        Args:
            episodic_uuid: UUID существующего Episodic узла
            update_communities: Обновлять ли сообщества
            entity_types: Кастомные типы сущностей
            edge_types: Кастомные типы связей
            edge_type_map: Маппинг разрешённых связей

        Returns:
            AddEpisodeResults с обработанными данными

        Raises:
            ValueError: Если Episodic не найден или нет связанных PARA Entity
        """
        try:
            start = time()
            now = utc_now()

            # ШАГ 1: Получить существующий Episodic.
            # Load as PipGraphEpisodicNode (full properties) so file_path /
            # frontmatter / content_hash are kept in memory — the base
            # EpisodicNode.get_by_uuid projection omits them, and we need them to
            # re-apply after the bulk save (see ШАГ 10).
            episode = await self.get_episodic_by_uuid(episodic_uuid)
            if not episode:
                raise ValueError(f"Episodic not found: {episodic_uuid}")

            logger.info(f"[process_existing_episode] Processing Episodic: {episode.name} (uuid: {episodic_uuid})")

            # ШАГ 2: Найти связанные PARA Entity через MENTIONS
            existing_para_entities = await self._get_mentioned_para_entities(episodic_uuid)
            if not existing_para_entities:
                raise ValueError(f"No PARA entities linked to Episodic: {episodic_uuid}")

            existing_para_uuids = {e.uuid for e in existing_para_entities}
            logger.info(f"[process_existing_episode] Found {len(existing_para_entities)} existing PARA entities")

            # Подготовка контекста
            validate_group_id(episode.group_id)
            group_id = episode.group_id or get_default_group_id(self.driver.provider)

            # TODO: Важно добавить фильтрацию entity_types/excluded_entity_types по existing_para_entities, 
            # нам нужны релевантные заметки, а не просто недавние
            previous_episodes = await retrieve_episodes(
                self.driver,
                episode.valid_at,
                last_n=RELEVANT_SCHEMA_LIMIT,
                group_ids=[group_id],
                source=episode.source,
            )

            # Create default edge type map
            edge_type_map_default = (
                {('Entity', 'Entity'): list(edge_types.keys())}
                if edge_types is not None
                else {('Entity', 'Entity'): []}
            )

            # ШАГ 3: ИЗВЛЕЧЕНИЕ СЫРЫХ СУЩНОСТЕЙ
            extracted_nodes = await extract_nodes(
                self.clients, episode, previous_episodes,
                entity_types=entity_types,
                excluded_entity_types=None
            )
            logger.info(f"[process_existing_episode] Extracted {len(extracted_nodes)} raw nodes")

            # ШАГ 4: СОПОСТАВЛЕНИЕ С СУЩЕСТВУЮЩИМИ + ИЗВЛЕЧЕНИЕ СВЯЗЕЙ
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
            logger.info(f"[process_existing_episode] Resolved to {len(nodes)} nodes, {len(extracted_edges)} edges")

            # ШАГ 5: MERGE PARA ENTITIES (КЛЮЧЕВОЙ!)
            # Добавить PARA Entity в nodes для обновления их summary
            existing_node_uuids = {n.uuid for n in nodes}
            for para_entity in existing_para_entities:
                if para_entity.uuid not in existing_node_uuids:
                    nodes.append(para_entity)
                    logger.info(f"[process_existing_episode] Added existing PARA entity to nodes: {para_entity.name}")

            # ШАГ 6: РАЗДЕЛИТЬ НА ДВЕ ГРУППЫ
            # nodes_for_summary = все узлы (для extract_attributes_from_nodes)
            # nodes_for_mentions = только новые (для build_episodic_edges)
            nodes_for_summary = nodes
            nodes_for_mentions = [n for n in nodes if n.uuid not in existing_para_uuids]
            logger.info(
                f"[process_existing_episode] Split: {len(nodes_for_summary)} for summary, "
                f"{len(nodes_for_mentions)} for new MENTIONS"
            )

            # ШАГ 7: РАЗРЕШЕНИЕ УКАЗАТЕЛЕЙ НА РЁБРА
            edges = resolve_edge_pointers(extracted_edges, uuid_map)

            # ШАГ 8: ВАЛИДАЦИЯ СВЯЗЕЙ + ОБНОВЛЕНИЕ АТРИБУТОВ/SUMMARY
            # Snapshot summaries before extract_attributes mutates nodes in place.
            # This path is the prime suspect: existing PARA entities (with good
            # summaries) are merged into nodes_for_summary and re-summarised, so a
            # bad LLM response here wipes an established summary (empty-summary bug).
            summaries_before = {n.uuid: (n.summary or "") for n in nodes_for_summary}
            (resolved_edges, invalidated_edges), hydrated_nodes = await semaphore_gather(
                resolve_extracted_edges(
                    self.clients,
                    edges,
                    episode,
                    nodes_for_summary,
                    edge_types or {},
                    edge_type_map or edge_type_map_default,
                ),
                extract_attributes_from_nodes(
                    self.clients, nodes_for_summary, episode, previous_episodes, entity_types
                ),
                max_coroutines=self.max_coroutines,
            )
            self._guard_summaries(
                "process_existing_episode", summaries_before, hydrated_nodes
            )

            entity_edges = resolved_edges + invalidated_edges

            # ШАГ 9: СОЗДАНИЕ MENTIONS СВЯЗЕЙ (ТОЛЬКО ДЛЯ НОВЫХ УЗЛОВ!)
            episodic_edges = build_episodic_edges(nodes_for_mentions, episode.uuid, now)
            logger.info(f"[process_existing_episode] Built {len(episodic_edges)} new MENTIONS edges")

            episode.entity_edges = [edge.uuid for edge in entity_edges]

            if not self.store_raw_episode_content:
                episode.content = ''

            # ШАГ 10: СОХРАНЕНИЕ В БД
            await add_nodes_and_edges_bulk(
                self.driver, [episode], episodic_edges, hydrated_nodes, entity_edges, self.embedder
            )

            # add_nodes_and_edges_bulk saves the Episodic with a fixed
            # `SET n = {standard fields}` (Graphiti's bulk query), which REPLACES
            # the node's properties and wipes PipGraph extras (file_path,
            # frontmatter, content_hash, status). Re-apply them via the PipGraph
            # save override (`SET e += {extras}`) so they survive the round-trip.
            # `status` matters here specifically: when this op runs as a queued job
            # (P2), the node carries status="process_existing_episode" while it runs
            # (stamped by place_episode at enqueue time, cleared by the job on
            # success), and this save carries that flag past the bulk wipe — the
            # `episode` object loaded at ШАГ 1 still holds it (see nodes.py save()).
            # (Entity extras are carried by the bulk path itself — they live in
            # `attributes` — so only the Episodic needs this.)
            await episode.save(self.driver)

            communities = []
            community_edges = []

            # ШАГ 11: ОБНОВЛЕНИЕ СООБЩЕСТВ (опционально)
            if update_communities:
                communities, community_edges = await semaphore_gather(
                    *[
                        update_community(self.driver, self.clients.llm_client, self.embedder, node)
                        for node in nodes_for_summary
                    ],
                    max_coroutines=self.max_coroutines,
                )

            end = time()
            logger.info(f'[process_existing_episode] Completed in {(end - start) * 1000:.2f} ms')

            return AddEpisodeResults(
                episode=episode,
                episodic_edges=episodic_edges,
                nodes=hydrated_nodes,
                edges=entity_edges,
                communities=communities,
                community_edges=community_edges,
            )

        except Exception as e:
            logger.error(f"[process_existing_episode] Error: {e}", exc_info=True)
            raise

    async def list_para_entities(
        self,
        limit: int = 100,
        para_types: List[str] | None = None,
        property_filters: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        """
        List PARA Entity nodes with flexible filtering.

        Queries Neo4j for nodes with composite labels (:Entity:Project, etc.)
        created via create_para_entity endpoint.

        Args:
            limit: Maximum results (default 100, max 1000)
            para_types: Lowercase PARA types to filter (e.g., ["project", "area"])
                       Empty list = all types (OR logic)
            property_filters: Dict of property filters (e.g., {"status": "active"})
                             Supports single values or arrays

        Returns:
            List of dicts with entity properties

        Raises:
            ValueError: If invalid para_type or limit
        """
        # Validate inputs
        if not 1 <= limit <= 1000:
            raise ValueError(f"limit must be between 1 and 1000, got {limit}")

        # Validate and normalize para_types
        valid_types = {"project", "area", "resource", "archive"}
        if para_types:
            para_types = [t.lower() for t in para_types]
            invalid = [t for t in para_types if t not in valid_types]
            if invalid:
                raise ValueError(f"Invalid para_types: {invalid}. Must be one of: {valid_types}")
        else:
            para_types = list(valid_types)

        # Build WHERE clauses
        where_clauses = []
        params = {"limit": limit}

        # Map lowercase to proper case for Neo4j labels
        type_mapping = {
            "project": "Project",
            "area": "Area",
            "resource": "Resource",
            "archive": "Archive"
        }

        # PARA type filter: (n:Entity:Project OR n:Entity:Area OR ...)
        label_conditions = [f"n:{type_mapping[t]}" for t in para_types]
        where_clauses.append(f"({' OR '.join(label_conditions)})")

        # Property filters
        if property_filters:
            for prop_name, prop_value in property_filters.items():
                # Validate property name to prevent Cypher injection
                if not self._is_valid_property_name(prop_name):
                    logger.warning(f"Skipping invalid property name: {prop_name}")
                    continue

                # Build filter condition
                if isinstance(prop_value, list):
                    # Array filter: n.property IN ["value1", "value2"]
                    param_key = f"prop_{prop_name}"
                    where_clauses.append(f"n.{prop_name} IN ${param_key}")
                    params[param_key] = prop_value
                else:
                    # Single value filter: n.property = "value"
                    param_key = f"prop_{prop_name}"
                    where_clauses.append(f"n.{prop_name} = ${param_key}")
                    params[param_key] = prop_value

        # Build final query
        where_str = " AND ".join(where_clauses) if where_clauses else "n:Entity"

        query = f"""
        MATCH (n:Entity)
        WHERE {where_str}
        RETURN
            n.uuid as uuid,
            n.name as name,
            [label IN labels(n) WHERE label <> 'Entity'][0] as para_type,
            n.created_at as created_at,
            n.summary as summary,
            properties(n) as all_properties
        ORDER BY n.name ASC
        LIMIT $limit
        """

        logger.info(f"[list_para_entities] Query: {query}")
        logger.info(f"[list_para_entities] Params: {params}")

        try:
            async with self.driver.session() as session:
                result = await session.run(query, **params)
                entities = []

                async for record in result:
                    # Extract attributes (all properties except system ones)
                    all_props = dict(record["all_properties"])
                    system_fields = {"uuid", "name", "created_at", "summary", "name_embedding", "group_id", "labels"}
                    attributes = {k: v for k, v in all_props.items() if k not in system_fields}

                    entity = {
                        "uuid": record["uuid"],
                        "name": record["name"],
                        "para_type": record["para_type"],
                        "created_at": self._serialize_datetime(record["created_at"]),
                        "summary": record["summary"],
                        # file_path is a scalar in attributes (see PipGraphEntityNode);
                        # surface it as a top-level read-projection field (R1).
                        "file_path": all_props.get("file_path"),
                        "attributes": attributes
                    }
                    entities.append(entity)

                logger.info(f"[list_para_entities] Retrieved {len(entities)} entities")
                return entities

        except Exception as e:
            logger.error(f"[list_para_entities] Database error: {e}", exc_info=True)
            raise

    @staticmethod
    def _is_valid_property_name(name: str) -> bool:
        """
        Validate property name to prevent Cypher injection.

        Allows: alphanumeric + underscore (standard Neo4j property naming)
        Blocks: special characters, spaces, dots

        Args:
            name: Property name to validate

        Returns:
            True if valid, False otherwise
        """
        import re
        # Property names: [a-zA-Z_][a-zA-Z0-9_]*
        pattern = r"^[a-zA-Z_][a-zA-Z0-9_]*$"
        return bool(re.match(pattern, name))

    async def _get_mentioned_para_entities(
        self,
        episodic_uuid: str,
    ) -> List["PipGraphEntityNode"]:
        """
        Получить все PARA Entity связанные с Episodic через MENTIONS.

        Args:
            episodic_uuid: UUID существующего Episodic узла

        Returns:
            List[PipGraphEntityNode]: Список PARA Entity (Project, Area, Resource, Archive)
        """
        from app.models.nodes import PipGraphEntityNode

        # Step 1: find the UUIDs of PARA entities linked via MENTIONS.
        query = """
        MATCH (ep:Episodic {uuid: $uuid})-[:MENTIONS]->(e:Entity)
        WHERE e:Project OR e:Area OR e:Resource OR e:Archive
        RETURN e.uuid AS uuid
        """

        uuids: List[str] = []
        async with self.driver.session() as session:
            result = await session.run(query, uuid=episodic_uuid)
            async for record in result:
                uuids.append(record["uuid"])

        if not uuids:
            logger.info(f"Found 0 PARA entities linked to Episodic {episodic_uuid}")
            return []

        # Step 2: hydrate through Graphiti's loader. It maps the flat Neo4j
        # properties (file_path, para_type, …) back into `attributes` via
        # get_entity_node_from_record. A manual EntityNode(**dict(node)) would
        # silently drop those non-base fields, leaving `attributes` empty — and a
        # later bulk `SET n = node` would then wipe file_path/para_type from the
        # graph. Loading properly keeps them, so the bulk re-save preserves them.
        base_entities = await EntityNode.get_by_uuids(self.driver, uuids)
        entities = [PipGraphEntityNode.from_base(e) for e in base_entities]

        logger.info(f"Found {len(entities)} PARA entities linked to Episodic {episodic_uuid}")
        return entities

    @staticmethod
    def _serialize_datetime(value: Any) -> Optional[str]:
        """
        Serialize Neo4j DateTime to ISO format string.

        Args:
            value: Neo4j DateTime object or None

        Returns:
            ISO format string or None
        """
        from neo4j.time import DateTime as Neo4jDateTime

        if value is None:
            return None

        if isinstance(value, Neo4jDateTime):
            return value.iso_format()

        if isinstance(value, str):
            return value

        # Try to serialize as datetime
        try:
            if hasattr(value, 'isoformat'):
                return value.isoformat()
        except:
            pass

        return str(value)

    # ============================================================================
    # Episodic CRUD Methods
    # ============================================================================

    async def get_episodic_by_name(self, name: str) -> Optional["PipGraphEpisodicNode"]:
        """
        Retrieve an Episodic node by its name (file path).

        Args:
            name: File path (Episodic.name property)

        Returns:
            PipGraphEpisodicNode object or None if not found

        Example:
            >>> episodic = await manager.get_episodic_by_name("notes/meeting.md")
            >>> print(episodic.uuid, episodic.file_path)
        """
        from graphiti_core.helpers import parse_db_date
        from app.models.nodes import PipGraphEpisodicNode

        query = """
        MATCH (e:Episodic {name: $name})
        RETURN e
        """

        async with self.driver.session() as session:
            result = await session.run(query, name=name)
            record = await result.single()

            if record:
                node_data = dict(record["e"])

                # Parse datetime fields
                if "created_at" in node_data and node_data["created_at"]:
                    node_data["created_at"] = parse_db_date(node_data["created_at"])
                if "valid_at" in node_data and node_data["valid_at"]:
                    node_data["valid_at"] = parse_db_date(node_data["valid_at"])

                # Parse PipGraph-specific fields
                if "frontmatter" in node_data and node_data["frontmatter"]:
                    # Frontmatter is stored as JSON string
                    node_data["frontmatter"] = json.loads(node_data["frontmatter"])

                episodic = PipGraphEpisodicNode(**node_data)
                logger.info(f"[get_episodic_by_name] Found: {name} (uuid: {episodic.uuid})")
                return episodic
            else:
                logger.warning(f"[get_episodic_by_name] Not found: {name}")
                return None

    async def get_episodic_by_uuid(self, uuid: str) -> Optional["PipGraphEpisodicNode"]:
        """
        Retrieve an Episodic node by its UUID, preserving PipGraph fields.

        Reads the full node properties (not the base Graphiti projection, which
        omits file_path/frontmatter/content_hash) and reconstructs a
        PipGraphEpisodicNode. Use this instead of EpisodicNode.get_by_uuid when
        the custom fields must survive a subsequent save.

        Args:
            uuid: Episodic node UUID

        Returns:
            PipGraphEpisodicNode object or None if not found
        """
        from graphiti_core.helpers import parse_db_date
        from app.models.nodes import PipGraphEpisodicNode

        query = """
        MATCH (e:Episodic {uuid: $uuid})
        RETURN e
        """

        async with self.driver.session() as session:
            result = await session.run(query, uuid=uuid)
            record = await result.single()

            if not record:
                logger.warning(f"[get_episodic_by_uuid] Not found: {uuid}")
                return None

            node_data = dict(record["e"])

            # Parse datetime fields
            if "created_at" in node_data and node_data["created_at"]:
                node_data["created_at"] = parse_db_date(node_data["created_at"])
            if "valid_at" in node_data and node_data["valid_at"]:
                node_data["valid_at"] = parse_db_date(node_data["valid_at"])

            # Parse PipGraph-specific fields (frontmatter stored as JSON string)
            if "frontmatter" in node_data and node_data["frontmatter"]:
                node_data["frontmatter"] = json.loads(node_data["frontmatter"])

            episodic = PipGraphEpisodicNode(**node_data)
            logger.info(f"[get_episodic_by_uuid] Found: {uuid} (file_path={episodic.file_path})")
            return episodic

    async def list_episodics(self, limit: int = 100) -> List["PipGraphEpisodicNode"]:
        """
        List all Episodic nodes, ordered by creation date (newest first).

        Args:
            limit: Maximum number of nodes to return (default: 100, max: 1000)

        Returns:
            List of PipGraphEpisodicNode objects

        Raises:
            ValueError: If limit is out of range

        Example:
            >>> episodics = await manager.list_episodics(limit=50)
            >>> for ep in episodics:
            ...     print(ep.name, ep.file_path)
        """
        from graphiti_core.helpers import parse_db_date
        from app.models.nodes import PipGraphEpisodicNode

        if not 1 <= limit <= 1000:
            raise ValueError(f"limit must be between 1 and 1000, got {limit}")

        query = """
        MATCH (e:Episodic)
        RETURN e
        ORDER BY e.created_at DESC
        LIMIT $limit
        """

        episodics = []
        async with self.driver.session() as session:
            result = await session.run(query, limit=limit)

            async for record in result:
                node_data = dict(record["e"])

                # Parse datetime fields
                if "created_at" in node_data and node_data["created_at"]:
                    node_data["created_at"] = parse_db_date(node_data["created_at"])
                if "valid_at" in node_data and node_data["valid_at"]:
                    node_data["valid_at"] = parse_db_date(node_data["valid_at"])

                # Parse PipGraph-specific fields
                if "frontmatter" in node_data and node_data["frontmatter"]:
                    node_data["frontmatter"] = json.loads(node_data["frontmatter"])

                episodic = PipGraphEpisodicNode(**node_data)
                episodics.append(episodic)

        logger.info(f"[list_episodics] Retrieved {len(episodics)} episodic nodes")
        return episodics

    async def list_unlinked_episodics(self, limit: int = 100) -> List["PipGraphEpisodicNode"]:
        """
        List all Episodic nodes that do NOT have MENTIONS relationships to any PARA entities.

        Returns Episodic nodes that are not linked to Project, Area, Resource, or Archive
        entities via MENTIONS relationship. These are "orphaned" or "unclassified" notes
        that need to be categorized into the PARA system.

        Use cases:
        - Finding notes that need to be classified into PARA structure
        - Inbox-like view of uncategorized notes
        - Identifying notes that require user intervention

        Args:
            limit: Maximum number of nodes to return (default: 100, max: 1000)

        Returns:
            List of PipGraphEpisodicNode objects without PARA entity mentions

        Raises:
            ValueError: If limit is out of range

        Example:
            >>> unlinked = await manager.list_unlinked_episodics(limit=50)
            >>> for ep in unlinked:
            ...     print(f"Unlinked: {ep.name}")
        """
        from graphiti_core.helpers import parse_db_date
        from app.models.nodes import PipGraphEpisodicNode

        if not 1 <= limit <= 1000:
            raise ValueError(f"limit must be between 1 and 1000, got {limit}")

        # Cypher query: Find Episodics without MENTIONS to PARA entities
        # Uses NOT EXISTS with subquery to check for any PARA entity mentions
        query = """
        MATCH (ep:Episodic)
        WHERE NOT EXISTS {
            MATCH (ep)-[:MENTIONS]->(e:Entity)
            WHERE e:Project OR e:Area OR e:Resource OR e:Archive
        }
        RETURN ep
        ORDER BY ep.created_at DESC
        LIMIT $limit
        """

        episodics = []
        async with self.driver.session() as session:
            result = await session.run(query, limit=limit)

            async for record in result:
                node_data = dict(record["ep"])

                # Parse datetime fields from Neo4j format
                if "created_at" in node_data and node_data["created_at"]:
                    node_data["created_at"] = parse_db_date(node_data["created_at"])
                if "valid_at" in node_data and node_data["valid_at"]:
                    node_data["valid_at"] = parse_db_date(node_data["valid_at"])

                # Parse PipGraph-specific fields
                if "frontmatter" in node_data and node_data["frontmatter"]:
                    node_data["frontmatter"] = json.loads(node_data["frontmatter"])

                episodic = PipGraphEpisodicNode(**node_data)
                episodics.append(episodic)

        logger.info(
            f"[list_unlinked_episodics] Retrieved {len(episodics)} unlinked episodic nodes "
            f"(no MENTIONS to PARA entities)"
        )
        return episodics

    async def list_episodics_by_status(
        self,
        status: str,
        limit: int = 200,
    ) -> List["PipGraphEpisodicNode"]:
        """
        List Episodics carrying a given ``status`` value (exact match).

        The status taxonomy (:mod:`app.services.jobs.status`) makes this the
        "what async work is in flight" query: pass an active job key
        (``"process_existing_episode"``) to find in-flight nodes, or a
        ``"failed:<job>"`` value to find failures. Backs two consumers:

        - **Client reconcile** — on plugin start, seed the in-memory poll set with
          nodes still processing (so markers resume without a perpetual DB scan).
        - **Phase-3 server re-enqueue** — on backend start, re-queue stuck jobs.

        Args:
            status: Exact ``status`` value to match (non-null).
            limit: Maximum number of nodes to return (default: 200, max: 1000).

        Returns:
            List of PipGraphEpisodicNode objects, newest first.

        Raises:
            ValueError: If limit is out of range.
        """
        from graphiti_core.helpers import parse_db_date
        from app.models.nodes import PipGraphEpisodicNode

        if not 1 <= limit <= 1000:
            raise ValueError(f"limit must be between 1 and 1000, got {limit}")

        query = """
        MATCH (e:Episodic {status: $status})
        RETURN e
        ORDER BY e.created_at DESC
        LIMIT $limit
        """

        episodics = []
        async with self.driver.session() as session:
            result = await session.run(query, status=status, limit=limit)

            async for record in result:
                node_data = dict(record["e"])

                if "created_at" in node_data and node_data["created_at"]:
                    node_data["created_at"] = parse_db_date(node_data["created_at"])
                if "valid_at" in node_data and node_data["valid_at"]:
                    node_data["valid_at"] = parse_db_date(node_data["valid_at"])
                if "frontmatter" in node_data and node_data["frontmatter"]:
                    node_data["frontmatter"] = json.loads(node_data["frontmatter"])

                episodics.append(PipGraphEpisodicNode(**node_data))

        logger.info(
            f"[list_episodics_by_status] Retrieved {len(episodics)} episodics "
            f"with status='{status}'"
        )
        return episodics

    async def get_episodics_by_entity_uuid(
        self,
        entity_uuid: str,
        limit: int = 50
    ) -> List["PipGraphEpisodicNode"]:
        """
        Get all Episodic nodes that mention a specific Entity.

        Retrieves Episodic nodes that have a MENTIONS relationship to the
        specified Entity, ordered by creation date (newest first).

        Args:
            entity_uuid: UUID of the Entity node
            limit: Maximum number of episodics to return (default: 50, max: 500)

        Returns:
            List of PipGraphEpisodicNode objects that mention the entity

        Raises:
            ValueError: If limit is out of range or entity_uuid is invalid

        Example:
            >>> episodics = await manager.get_episodics_by_entity_uuid(
            ...     entity_uuid="660e8400-e29b-41d4-a716-446655440111",
            ...     limit=100
            ... )
            >>> for ep in episodics:
            ...     print(ep.name, ep.created_at)
        """
        from graphiti_core.helpers import parse_db_date
        from app.models.nodes import PipGraphEpisodicNode

        # Validate inputs
        if not entity_uuid or not entity_uuid.strip():
            raise ValueError("entity_uuid cannot be empty")

        if not 1 <= limit <= 500:
            raise ValueError(f"limit must be between 1 and 500, got {limit}")

        # Query: Find all Episodics that mention this Entity
        # This is the inverse of _get_mentioned_para_entities
        query = """
        MATCH (ep:Episodic)-[:MENTIONS]->(e:Entity {uuid: $entity_uuid})
        RETURN ep
        ORDER BY ep.created_at DESC
        LIMIT $limit
        """

        episodics = []
        async with self.driver.session() as session:
            result = await session.run(
                query,
                entity_uuid=entity_uuid,
                limit=limit
            )

            async for record in result:
                node_data = dict(record["ep"])

                # Parse datetime fields from Neo4j format
                if "created_at" in node_data and node_data["created_at"]:
                    node_data["created_at"] = parse_db_date(node_data["created_at"])
                if "valid_at" in node_data and node_data["valid_at"]:
                    node_data["valid_at"] = parse_db_date(node_data["valid_at"])

                # Parse PipGraph-specific fields
                if "frontmatter" in node_data and node_data["frontmatter"]:
                    node_data["frontmatter"] = json.loads(node_data["frontmatter"])

                # Create PipGraphEpisodicNode from data
                episodic = PipGraphEpisodicNode(**node_data)
                episodics.append(episodic)

        logger.info(
            f"[get_episodics_by_entity_uuid] Found {len(episodics)} episodics "
            f"mentioning entity {entity_uuid}"
        )
        return episodics

    async def update_episodic_timestamp(
        self,
        episodic_uuid: str,
        valid_at: datetime | None = None
    ) -> bool:
        """
        Update the valid_at timestamp of an Episodic node.

        Args:
            episodic_uuid: UUID of the Episodic node
            valid_at: New timestamp (defaults to current time)

        Returns:
            True if updated successfully, False if episodic not found

        Example:
            >>> success = await manager.update_episodic_timestamp(
            ...     episodic_uuid="550e8400-e29b-41d4-a716-446655440000",
            ...     valid_at=datetime.now(timezone.utc)
            ... )
        """
        from graphiti_core.utils.datetime_utils import utc_now

        timestamp = valid_at or utc_now()
        timestamp_str = timestamp.isoformat()

        query = """
        MATCH (e:Episodic {uuid: $uuid})
        SET e.valid_at = $valid_at
        RETURN e
        """

        async with self.driver.session() as session:
            result = await session.run(query, uuid=episodic_uuid, valid_at=timestamp_str)
            record = await result.single()

            if record:
                logger.info(f"[update_episodic_timestamp] Updated uuid={episodic_uuid}")
                return True
            else:
                logger.warning(f"[update_episodic_timestamp] Not found: uuid={episodic_uuid}")
                return False

    async def update_episodic_file_path(
        self,
        episodic_uuid: str,
        file_path: str | None = None,
    ) -> Optional["PipGraphEpisodicNode"]:
        """
        Update the file_path of an existing Episodic in place.

        Narrow by design — the Episodic mirror of the S1 ``file_path`` symmetry
        that S1 gave Entities. Patches only ``file_path`` (the client-owned
        binding written after the file is created, including name-collision
        suffixes); the UUID and all MENTIONS edges are preserved. No embeddings
        or fulltext indexes depend on this field, so nothing is recomputed.

        **Transition-guard (cluster decision E6).** This is a pure binding-setter
        that never touches ``MENTIONS``, so it only permits transitions that keep
        the placement folder stable:

        - ``current`` empty → allow (first-bind; the capture flow).
        - ``new is None`` or ``new == current`` → no-op.
        - same parent folder (POSIX ``dirname`` equal) → allow (pure rename).
        - **different parent folder → reject** with :class:`CrossFolderFilePathError`.

        A cross-folder change is a *placement* change (it should also re-point
        ``MENTIONS``); that belongs to the move+link operation (E7), not here.

        Args:
            episodic_uuid: UUID of the Episodic to update.
            file_path: New vault-relative POSIX path. ``None`` = leave unchanged.

        Returns:
            The updated PipGraphEpisodicNode, or ``None`` if no Episodic with
            that UUID exists.

        Raises:
            CrossFolderFilePathError: the patch would move ``file_path`` to a
                different folder (caller should surface ``200 {success:false}``).
        """
        from graphiti_core.helpers import parse_db_date
        from app.models.nodes import PipGraphEpisodicNode

        # Read current state first so we can guard the transition before writing.
        async with self.driver.session() as session:
            record = await (
                await session.run(
                    "MATCH (e:Episodic {uuid: $uuid}) RETURN e",
                    uuid=episodic_uuid,
                )
            ).single()

            if not record:
                logger.warning(f"[update_episodic_file_path] Not found: uuid={episodic_uuid}")
                return None

            current = record["e"].get("file_path")

            # Decide whether this is an allowed write. Anything that resolves to
            # "no change needed" short-circuits to a no-op (existence confirmed).
            will_write = file_path is not None and file_path != current
            if will_write:
                self._guard_file_path_transition(current, file_path)

                record = await (
                    await session.run(
                        """
                        MATCH (e:Episodic {uuid: $uuid})
                        SET e.file_path = $file_path
                        RETURN e
                        """,
                        uuid=episodic_uuid,
                        file_path=file_path,
                    )
                ).single()

        node_data = dict(record["e"])

        # Parse datetime fields
        if "created_at" in node_data and node_data["created_at"]:
            node_data["created_at"] = parse_db_date(node_data["created_at"])
        if "valid_at" in node_data and node_data["valid_at"]:
            node_data["valid_at"] = parse_db_date(node_data["valid_at"])

        # Parse PipGraph-specific fields
        if "frontmatter" in node_data and node_data["frontmatter"]:
            node_data["frontmatter"] = json.loads(node_data["frontmatter"])

        logger.info(
            f"[update_episodic_file_path] uuid={episodic_uuid} "
            f"(file_path={'set' if will_write else 'unchanged'})"
        )
        return PipGraphEpisodicNode(**node_data)

    async def finalize_episode_name(
        self,
        episodic_uuid: str,
        name: str,
    ) -> bool:
        """
        Set an Episodic's final name and clear its transient ``status`` in one act.

        Used by the job-runner's naming job: once the LLM has produced a name, the
        node's provisional (client-supplied) name is overwritten and the
        ``processing`` flag is removed, marking the episode settled.

        Narrow by design — touches only ``name`` and ``status``; UUID, edges, and
        all other properties are preserved. No embeddings/indexes depend on
        ``name`` for an Episodic, so nothing is recomputed.

        Args:
            episodic_uuid: UUID of the Episodic to finalize.
            name: Final name to set.

        Returns:
            True if a node was updated, False if no Episodic with that UUID exists.
        """
        async with self.driver.session() as session:
            record = await (
                await session.run(
                    """
                    MATCH (e:Episodic {uuid: $uuid})
                    SET e.name = $name
                    REMOVE e.status
                    RETURN e.uuid AS uuid
                    """,
                    uuid=episodic_uuid,
                    name=name,
                )
            ).single()

        if not record:
            logger.warning(f"[finalize_episode_name] Not found: uuid={episodic_uuid}")
            return False

        logger.info(f"[finalize_episode_name] uuid={episodic_uuid} name='{name}' (status cleared)")
        return True

    async def set_episodic_status(
        self,
        episodic_uuid: str,
        status: str,
    ) -> bool:
        """
        Set the transient ``status`` property on an Episodic.

        Used by the job-runner to mark an episode whose async work errored
        (``"failed:<job_type>"``) — see :mod:`app.services.jobs.status` for the
        value taxonomy. To *clear* status on success use
        :meth:`clear_episodic_status` (or :meth:`finalize_episode_name` for the
        naming job, which clears it as part of setting the final name).

        Args:
            episodic_uuid: UUID of the Episodic.
            status: Status value to set (non-null).

        Returns:
            True if a node was updated, False if no Episodic with that UUID exists.
        """
        async with self.driver.session() as session:
            record = await (
                await session.run(
                    """
                    MATCH (e:Episodic {uuid: $uuid})
                    SET e.status = $status
                    RETURN e.uuid AS uuid
                    """,
                    uuid=episodic_uuid,
                    status=status,
                )
            ).single()

        if not record:
            logger.warning(f"[set_episodic_status] Not found: uuid={episodic_uuid}")
            return False

        logger.info(f"[set_episodic_status] uuid={episodic_uuid} status='{status}'")
        return True

    async def clear_episodic_status(self, episodic_uuid: str) -> bool:
        """
        Remove the transient ``status`` property, marking an Episodic settled.

        Counterpart to :meth:`set_episodic_status`. Used by the job-runner when an
        async job completes successfully without changing ``name`` (the heavy
        ``process_existing_episode`` job; the naming job clears status via
        :meth:`finalize_episode_name` instead, since it also sets the final name).

        Args:
            episodic_uuid: UUID of the Episodic.

        Returns:
            True if a node was updated, False if no Episodic with that UUID exists.
        """
        async with self.driver.session() as session:
            record = await (
                await session.run(
                    """
                    MATCH (e:Episodic {uuid: $uuid})
                    REMOVE e.status
                    RETURN e.uuid AS uuid
                    """,
                    uuid=episodic_uuid,
                )
            ).single()

        if not record:
            logger.warning(f"[clear_episodic_status] Not found: uuid={episodic_uuid}")
            return False

        logger.info(f"[clear_episodic_status] uuid={episodic_uuid} (status cleared)")
        return True

    async def place_episode(
        self,
        episodic_uuid: str,
        entity_uuid: str,
        file_path: str,
        created_at: datetime | None = None,
        status: str | None = None,
    ) -> Optional[tuple["PipGraphEpisodicNode", str]]:
        """
        Place an Episodic into a PARA folder-entity in one act: set its
        ``file_path`` to the new (possibly cross-folder) location **and** MERGE
        the ``MENTIONS`` edge to the entity.

        This is the move+link operation (cluster decision E7). It deliberately
        does **not** route through ``update_episodic_file_path`` — that narrow
        setter rejects cross-folder moves (guard E6) precisely because changing
        the folder is a *placement* change that must also (re)point ``MENTIONS``.
        Here we do both, so the cross-folder ``SET`` is correct rather than a
        silent desync. The physical file move is the client's job (the backend
        has no vault access).

        Idempotent on the **(episode, entity) pair**: ``SET`` is deterministic
        and the ``MENTIONS`` edge is MERGEd on the *relationship pattern* (not on
        a fresh edge uuid), so re-placing the same note matches the existing edge
        instead of duplicating it. NB: this is why we do **not** use
        ``EpisodicEdge.save()`` here — Graphiti's ``EPISODIC_EDGE_SAVE`` MERGEs on
        ``{uuid: $uuid}`` with a uuid generated per call, which would mint a new
        edge on every repeat. The pair carries at most one ``MENTIONS``.

        Args:
            episodic_uuid: UUID of the Episodic being placed.
            entity_uuid: UUID of the PARA Entity (folder) it is filed under.
            file_path: New vault-relative POSIX path inside the entity's folder.
            created_at: Optional ``MENTIONS`` timestamp (defaults to now).
            status: Optional ``status`` to stamp in the **same** statement (P2). The
                drop-then-process flow passes ``"process_existing_episode"`` so the
                durable "in flight" record exists atomically with the link, before
                the heavy job is enqueued; ``None`` leaves ``status`` untouched.

        Returns:
            ``(updated PipGraphEpisodicNode, edge_uuid)`` on success, or ``None``
            if no Episodic with that UUID exists.

        Raises:
            ValueError: if the Entity does not exist.
        """
        from uuid import uuid4
        from graphiti_core.nodes import EntityNode
        from graphiti_core.helpers import parse_db_date
        from graphiti_core.utils.datetime_utils import utc_now
        from app.models.nodes import PipGraphEpisodicNode

        now = created_at or utc_now()

        # Validate the entity up front so we can return a clear "Entity not
        # found" rather than a silent empty result, and to borrow its group_id.
        entity = await EntityNode.get_by_uuid(self.driver, entity_uuid)
        if not entity:
            raise ValueError(f"Entity not found: {entity_uuid}")

        # SET file_path (cross-folder allowed — this IS the relink) + optionally
        # stamp status (P2 in-flight marker) + MERGE the MENTIONS edge on the
        # pattern (idempotent) — all in one statement so the placement, the link
        # and the durable "processing" record commit together.
        status_clause = ", e.status = $status" if status is not None else ""
        query = f"""
        MATCH (e:Episodic {{uuid: $episodic_uuid}})
        SET e.file_path = $file_path{status_clause}
        WITH e
        MATCH (n:Entity {{uuid: $entity_uuid}})
        MERGE (e)-[r:MENTIONS]->(n)
        ON CREATE SET r.uuid = $edge_uuid, r.group_id = $group_id, r.created_at = $created_at
        RETURN e AS episode, r.uuid AS edge_uuid
        """
        async with self.driver.session() as session:
            record = await (
                await session.run(
                    query,
                    episodic_uuid=episodic_uuid,
                    entity_uuid=entity_uuid,
                    file_path=file_path,
                    status=status,
                    edge_uuid=str(uuid4()),
                    group_id=entity.group_id,
                    created_at=now,
                )
            ).single()

        if not record:
            logger.warning(f"[place_episode] Episodic not found: {episodic_uuid}")
            return None

        edge_uuid = record["edge_uuid"]
        logger.info(
            f"[place_episode] Placed {episodic_uuid} -> {entity.name} "
            f"(file_path={file_path}, edge={edge_uuid})"
        )

        node_data = dict(record["episode"])
        if node_data.get("created_at"):
            node_data["created_at"] = parse_db_date(node_data["created_at"])
        if node_data.get("valid_at"):
            node_data["valid_at"] = parse_db_date(node_data["valid_at"])
        if node_data.get("frontmatter"):
            node_data["frontmatter"] = json.loads(node_data["frontmatter"])

        return PipGraphEpisodicNode(**node_data), edge_uuid

    @staticmethod
    def _guard_file_path_transition(current: str | None, new: str) -> None:
        """Enforce the E6 transition-guard for ``file_path`` patches.

        Allows first-bind (no current path) and same-folder renames; rejects a
        move to a different parent folder with :class:`CrossFolderFilePathError`.
        Paths are compared as vault-relative POSIX paths. Callers must only
        invoke this when an actual write is pending (``new != current``).
        """
        if not current:
            return  # first-bind — capture flow

        if posixpath.dirname(current) != posixpath.dirname(new):
            raise CrossFolderFilePathError(
                f"Refusing cross-folder file_path move ({current!r} → {new!r}): "
                "changing the placement folder must go through the move+link "
                "operation, not the narrow PATCH (cluster decision E6)."
            )

    async def delete_episodic(self, episodic_uuid: str) -> bool:
        """
        Delete an Episodic node and all its relationships.

        Args:
            episodic_uuid: UUID of the Episodic node to delete

        Returns:
            True if deleted successfully, False if not found

        Warning:
            This operation is irreversible. All relationships (MENTIONS edges)
            will also be deleted.

        Example:
            >>> success = await manager.delete_episodic(
            ...     episodic_uuid="550e8400-e29b-41d4-a716-446655440000"
            ... )
        """
        query = """
        MATCH (e:Episodic {uuid: $uuid})
        DETACH DELETE e
        RETURN count(e) as deleted_count
        """

        async with self.driver.session() as session:
            result = await session.run(query, uuid=episodic_uuid)
            record = await result.single()

            if record and record["deleted_count"] > 0:
                logger.info(f"[delete_episodic] Deleted uuid={episodic_uuid}")
                return True
            else:
                logger.warning(f"[delete_episodic] Not found: uuid={episodic_uuid}")
                return False

    async def delete_node(self, node_uuid: str) -> tuple[bool, str | None]:
        """
        Delete a node (Episodic or Entity) by UUID, automatically detecting its type.

        This is a universal deletion method that:
        1. Queries the node to determine its type (Episodic or Entity)
        2. Deletes the node and all its relationships using DETACH DELETE
        3. Returns success status and detected node type

        Args:
            node_uuid: UUID of the node to delete (Episodic or Entity)

        Returns:
            Tuple of (success: bool, node_type: str | None)
            - success: True if deleted, False if not found
            - node_type: "Episodic", "Entity", or None if not found

        Warning:
            This operation is irreversible. All relationships will be deleted via DETACH DELETE.

        Example:
            >>> success, node_type = await manager.delete_node(
            ...     node_uuid="550e8400-e29b-41d4-a716-446655440000"
            ... )
            >>> print(f"Deleted {node_type}: {success}")
        """
        # Query to detect node type and delete in one transaction
        # Checks for both Episodic and Entity labels
        query = """
        MATCH (n {uuid: $uuid})
        WHERE n:Episodic OR n:Entity
        WITH n,
             CASE
                WHEN n:Episodic THEN 'Episodic'
                WHEN n:Entity THEN 'Entity'
                ELSE NULL
             END as node_type
        DETACH DELETE n
        RETURN node_type, 1 as deleted_count
        """

        async with self.driver.session() as session:
            result = await session.run(query, uuid=node_uuid)
            record = await result.single()

            if record and record["deleted_count"] > 0:
                node_type = record["node_type"]
                logger.info(f"[delete_node] Deleted {node_type} node: uuid={node_uuid}")
                return True, node_type
            else:
                logger.warning(f"[delete_node] Node not found: uuid={node_uuid}")
                return False, None

    async def delete_para_entity_cascade(
        self, entity_uuid: str
    ) -> tuple[bool, int]:
        """
        Delete a PARA Entity and cascade-delete its "orphaned" Episodics.

        Deletes the Entity node (with DETACH DELETE, so its MENTIONS and
        BELONGS_TO edges go too) and, in addition, deletes every Episodic
        whose *only* MENTIONS edge pointed at this Entity. Episodics that
        also mention another Entity survive — they merely lose this one edge.

        This mirrors the folder-mirror semantics: removing a PARA folder
        removes the notes that existed solely under it, while notes that were
        cross-referenced elsewhere stay.

        NOTE: This is a hard delete, intended for the folder-mirror flow and
        manual/debug cleanup. A bi-temporal soft-invalidation model (Graphiti
        `expired_at`/`invalid_at`) is the conceptual successor and is tracked
        separately — do not assume this is the final deletion semantics.

        Args:
            entity_uuid: UUID of the PARA Entity to delete.

        Returns:
            Tuple of (success, deleted_episodics_count).
            - success: True if the entity existed and was deleted, False if
              no Entity with that UUID was found.
            - deleted_episodics_count: number of orphaned Episodics removed.
        """
        # Guard: only proceed if the node exists and is an Entity.
        check_query = """
        MATCH (e:Entity {uuid: $uuid})
        RETURN count(e) AS found
        """

        # Delete Episodics whose sole MENTIONS edge targets this Entity.
        # count(m) = 1 means the only entity it mentions is the one we delete.
        orphan_query = """
        MATCH (ep:Episodic)-[:MENTIONS]->(:Entity {uuid: $uuid})
        OPTIONAL MATCH (ep)-[m:MENTIONS]->(:Entity)
        WITH ep, count(m) AS mention_count
        WHERE mention_count = 1
        DETACH DELETE ep
        RETURN count(ep) AS deleted_episodics
        """

        # Delete the entity itself; DETACH DELETE removes remaining MENTIONS
        # (from surviving multi-mention Episodics) and BELONGS_TO edges.
        delete_query = """
        MATCH (e:Entity {uuid: $uuid})
        DETACH DELETE e
        RETURN count(e) AS deleted_count
        """

        async with self.driver.session() as session:
            check = await (await session.run(check_query, uuid=entity_uuid)).single()
            if not check or check["found"] == 0:
                logger.warning(
                    f"[delete_para_entity_cascade] Entity not found: uuid={entity_uuid}"
                )
                return False, 0

            orphan = await (await session.run(orphan_query, uuid=entity_uuid)).single()
            deleted_episodics = orphan["deleted_episodics"] if orphan else 0

            await session.run(delete_query, uuid=entity_uuid)

        logger.info(
            f"[delete_para_entity_cascade] Deleted entity {entity_uuid} "
            f"and {deleted_episodics} orphaned episodic(s)"
        )
        return True, deleted_episodics

    # ============================================================================
    # Entity CRUD Methods
    # ============================================================================

    async def get_para_entity_by_uuid(self, uuid: str) -> Optional["PipGraphEntityNode"]:
        """
        Retrieve a PARA Entity node by UUID.

        Args:
            uuid: UUID of the entity

        Returns:
            PipGraphEntityNode object or None if not found

        Example:
            >>> entity = await manager.get_para_entity_by_uuid(
            ...     "660e8400-e29b-41d4-a716-446655440111"
            ... )
            >>> print(entity.name, entity.para_type)
        """
        from app.models.nodes import PipGraphEntityNode

        try:
            base_entity = await EntityNode.get_by_uuid(self.driver, uuid)

            if base_entity:
                # Convert base EntityNode to PipGraphEntityNode
                # This extracts para_type from attributes or labels
                entity = PipGraphEntityNode.from_base(base_entity)
                logger.info(f"[get_para_entity_by_uuid] Found: {entity.name} (uuid: {uuid})")
                return entity
            else:
                logger.warning(f"[get_para_entity_by_uuid] Not found: uuid={uuid}")
                return None
        except Exception as e:
            logger.error(f"[get_para_entity_by_uuid] Error: {e}", exc_info=True)
            return None

    async def get_para_entity_by_name(
        self,
        name: str,
        para_type: str | None = None
    ) -> Optional["PipGraphEntityNode"]:
        """
        Retrieve a PARA Entity node by name, optionally filtered by type.

        Args:
            name: Entity name
            para_type: Optional PARA type filter ("Project", "Area", "Resource", "Archive")

        Returns:
            PipGraphEntityNode object or None if not found

        Example:
            >>> entity = await manager.get_para_entity_by_name(
            ...     name="Website Redesign",
            ...     para_type="Project"
            ... )
        """
        from graphiti_core.helpers import parse_db_date
        from app.models.nodes import PipGraphEntityNode

        # Build query with optional type filter
        if para_type:
            # Validate para_type
            valid_types = ["Project", "Area", "Resource", "Archive"]
            if para_type not in valid_types:
                raise ValueError(f"Invalid para_type '{para_type}'. Must be one of: {valid_types}")

            query = f"""
            MATCH (e:Entity:{para_type} {{name: $name}})
            RETURN e
            """
        else:
            query = """
            MATCH (e:Entity {name: $name})
            WHERE e:Project OR e:Area OR e:Resource OR e:Archive
            RETURN e
            """

        try:
            async with self.driver.session() as session:
                result = await session.run(query, name=name)
                record = await result.single()

                if record:
                    node_data = dict(record["e"])

                    # Parse datetime
                    if "created_at" in node_data and node_data["created_at"]:
                        node_data["created_at"] = parse_db_date(node_data["created_at"])

                    # Remove name_embedding (will be loaded separately if needed)
                    node_data.pop("name_embedding", None)

                    # Create base EntityNode first, then convert to PipGraphEntityNode
                    # This ensures proper extraction of para_type from attributes/labels
                    base_entity = EntityNode(**node_data)
                    entity = PipGraphEntityNode.from_base(base_entity)

                    logger.info(f"[get_para_entity_by_name] Found: {name} (uuid: {entity.uuid})")
                    return entity
                else:
                    logger.warning(f"[get_para_entity_by_name] Not found: name={name}, type={para_type}")
                    return None
        except Exception as e:
            logger.error(f"[get_para_entity_by_name] Error: {e}", exc_info=True)
            return None

    async def ensure_inbox_exists(self) -> "PipGraphEntityNode":
        """
        Ensure the default "Inbox" area exists, creating it if necessary.

        Creates an :Entity:Area node with name "Inbox" using the new Graphiti schema.
        Unlike the old CRUD version, this creates a proper Entity node with embeddings.

        Returns:
            PipGraphEntityNode: The Inbox area entity

        Example:
            >>> inbox = await manager.ensure_inbox_exists()
            >>> print(inbox.name)  # "Inbox"
            >>> print(inbox.para_type)  # "Area"
        """
        # First, try to find existing Inbox
        inbox = await self.get_para_entity_by_name(name="Inbox", para_type="Area")

        if inbox:
            logger.info(f"[ensure_inbox_exists] Inbox already exists (uuid: {inbox.uuid})")
            return inbox

        # Create new Inbox if not found
        # TODO: Создание такой ноды нам не нужно, будем искать ноды для инбокса - если у них нет связей или SUGGESTS,
        # то они в инбоксе и не нужно создавать отдельную ноду инбокса
        logger.info("[ensure_inbox_exists] Creating new Inbox area")
        inbox = await self.create_para_entity(
            para_type="Area",
            name="Inbox",
            summary="Default area for unclassified notes and suggestions",
        )

        logger.info(f"[ensure_inbox_exists] Created Inbox (uuid: {inbox.uuid})")
        return inbox

    async def make_suggestions(
        self,
        episodic_uuid: str,
        limit: int = 30,
        min_score: float = 0.0,
    ) -> tuple[str, list[dict]]:
        """
        Find relevant PARA entities for an episodic note using hybrid search.

        Uses Graphiti's hybrid search (BM25 + Cosine similarity + reranking)
        to find existing PARA entities (Project, Area, Resource) that are
        semantically related to the episodic note's content.

        This method:
        1. Retrieves the Episodic node by UUID using EpisodicNode.get_by_uuid
        2. Extracts content from the note
        3. Performs hybrid search using the content as query
        4. Filters results to include only PARA entities
        5. Returns ranked suggestions with relevance scores

        Args:
            episodic_uuid: UUID of the Episodic node
            limit: Maximum number of suggestions to return (default: 30)
            min_score: Minimum relevance score threshold (default: 0.0)

        Returns:
            Tuple of (episodic_uuid, suggestions_list)
            - episodic_uuid: UUID of the found Episodic node
            - suggestions_list: List of dicts with entity properties and scores

        Raises:
            ValueError: If Episodic node not found

        Example:
            >>> episodic_uuid, suggestions = await manager.make_suggestions(
            ...     episodic_uuid="550e8400-e29b-41d4-a716-446655440000",
            ...     limit=5,
            ...     min_score=0.5
            ... )
            >>> for suggestion in suggestions:
            ...     print(f"{suggestion['name']}: {suggestion['score']}")
        """
        try:
            logger.info(f"[make_suggestions] Finding suggestions for episodic UUID: {episodic_uuid}")

            # STEP 1: Get Episodic node by UUID using Graphiti's built-in method
            episodic = await EpisodicNode.get_by_uuid(self.driver, episodic_uuid)
            if not episodic:
                raise ValueError(f"Episodic not found: {episodic_uuid}")

            # STEP 2: Extract content for search query
            # Note: Episodic nodes may have empty content if store_raw_episode_content=False
            content = episodic.content or ""
            if not content:
                logger.warning(
                    f"[make_suggestions] Episodic {episodic.name} (uuid: {episodic_uuid}) has empty content, "
                    "using name as query"
                )
                query = episodic.name
            else:
                # Truncate content to avoid too long queries (Graphiti handles this, but good practice)
                # Use first 2000 characters for search query
                query = content[:2000]

            logger.info(f"[make_suggestions] Using query ({query})")
            logger.info(f"[make_suggestions] Using query (length={len(query)})")

            # STEP 3: Perform hybrid search using Graphiti's search
            # Configuration: BM25 (fulltext) only for now (cosine_similarity disabled for testing)
            # Override default limit (10) with user-provided limit
            custom_config = SearchConfig(
                node_config=NodeSearchConfig(
                    # search_methods=[NodeSearchMethod.bm25],  # Only BM25 for now
                    search_methods=[NodeSearchMethod.bm25, NodeSearchMethod.cosine_similarity],
                    reranker=NodeReranker.rrf, # Неверно выводит см. backend/.docs/about_graphiti/issues/rrf_reranker_positional_scores.md
                    # reranker=NodeReranker.mmr,
                ),
                limit=limit,  # Use limit from method parameter
            )

            # Filter search to only PARA entities (Project, Area, Resource, Archive)
            # This significantly improves search relevance by excluding generic Entity nodes
            para_filter = SearchFilters(
                node_labels=["Project", "Area", "Resource", "Archive"]
            )

            search_results = await search(
                clients=self.clients,
                query=query,
                group_ids=[episodic.group_id],
                config=custom_config,
                search_filter=para_filter,
            )

            logger.info(
                f"[make_suggestions] Search returned {len(search_results.nodes)} nodes, "
                f"scores: {search_results.node_reranker_scores[:10]}"
            )

            # Log first few results for debugging
            for i, node in enumerate(search_results.nodes[:5]):
                score = search_results.node_reranker_scores[i] if i < len(search_results.node_reranker_scores) else 0.0
                logger.info(
                    f"[make_suggestions] Result {i+1}: name={node.name}, "
                    f"labels={node.labels}, score={score:.4f}"
                )

            # STEP 4: Filter results to include only PARA entities
            # Check for composite labels: :Entity:Project, :Entity:Area, :Entity:Resource
            para_types = {"Project", "Area", "Resource", "Archive"}

            # First pass: collect ALL PARA entities with their scores
            all_para_candidates = []

            for i, node in enumerate(search_results.nodes):
                # Check if node has PARA labels
                node_labels = set(node.labels or [])
                para_labels = node_labels.intersection(para_types)

                if not para_labels:
                    # Not a PARA entity, skip
                    continue

                # Get score from reranker (if available)
                score = 0.0
                if i < len(search_results.node_reranker_scores):
                    score = search_results.node_reranker_scores[i]

                # Extract PARA type (first matching label)
                para_type = list(para_labels)[0]

                # Extract system fields for exclusion
                system_fields = {
                    "uuid", "name", "created_at", "summary",
                    "name_embedding", "group_id", "labels"
                }
                attributes = {
                    k: v for k, v in (node.attributes or {}).items()
                    if k not in system_fields
                }

                candidate = {
                    "uuid": node.uuid,
                    "name": node.name,
                    "para_type": para_type,
                    "summary": node.summary or "",
                    "score": score,
                    "attributes": attributes,
                }

                all_para_candidates.append(candidate)

            # ADAPTIVE FILTERING LOGIC:
            # Strategy: Always return top-N results (e.g., top-3), even if scores are low.
            # For remaining results, apply strict min_score threshold.
            # This ensures we never return nothing when there are at least some matches.

            MIN_GUARANTEED_RESULTS = 3  # Always return at least top-3 if available

            if not all_para_candidates:
                # No PARA entities found at all
                suggestions = []
                logger.info("[make_suggestions] No PARA entities found in search results.")
            elif len(all_para_candidates) <= MIN_GUARANTEED_RESULTS:
                # Few results: return all of them
                suggestions = all_para_candidates
                logger.info(
                    f"[make_suggestions] Found {len(all_para_candidates)} PARA entities. "
                    f"Returning all (below guaranteed minimum of {MIN_GUARANTEED_RESULTS})."
                )
            else:
                # Many results: guarantee top-N, then filter rest by min_score
                guaranteed = all_para_candidates[:MIN_GUARANTEED_RESULTS]
                remaining = all_para_candidates[MIN_GUARANTEED_RESULTS:]

                # Filter remaining by min_score
                filtered_remaining = [
                    candidate for candidate in remaining
                    if candidate["score"] >= min_score
                ]

                suggestions = guaranteed + filtered_remaining

                logger.info(
                    f"[make_suggestions] Found {len(all_para_candidates)} PARA entities. "
                    f"Guaranteed top-{MIN_GUARANTEED_RESULTS} + {len(filtered_remaining)} "
                    f"additional with score >= {min_score}."
                )

            # Limit to max number of results
            suggestions = suggestions[:limit]

            logger.info(
                f"[make_suggestions] Final result: {len(suggestions)} PARA entities "
                f"(adaptive filtering applied)"
            )

            # Sort by score descending (should already be sorted, but ensure)
            suggestions.sort(key=lambda x: x["score"], reverse=True)

            return episodic.uuid, suggestions

        except Exception as e:
            logger.error(f"[make_suggestions] Error: {e}", exc_info=True)
            raise
