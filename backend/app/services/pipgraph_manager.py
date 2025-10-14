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
        excluded_entity_types : list[str] | None
            Optional. List of entity type names to exclude from the graph. Entities classified
            into these types will not be added to the graph. Can include 'Entity' to exclude
            the default entity type.
        previous_episode_uuids : list[str] | None
            Optional.  list of episode uuids to use as the previous episodes. If this is not provided,
            the most recent episodes by created_at date will be used.

        Returns
        -------
        AddEpisodeResults
            Результаты обработки: эпизод, узлы, связи, сообщества

        Notes
        -----
        Оригинальный метод из graphiti_core/graphiti.py (lines 376-573).
        Сохранен для обратной совместимости и постепенной модификации.

        ТОЧКИ ДЛЯ БУДУЩЕЙ ИНТЕРВЕНЦИИ:
        - После extract_nodes: добавить подтверждение найденных сущностей
        - После resolve_extracted_nodes: ГЛАВНАЯ ТОЧКА - спросить описание новых сущностей
        - После extract_edges: добавить ручное связывание "осиротевших" заметок
        """
        try:
            start = time()
            now = utc_now()

            validate_entity_types(entity_types)

            validate_excluded_entity_types(excluded_entity_types, entity_types)
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

            # ЭТАП 1: ИЗВЛЕЧЕНИЕ СЫРЫХ СУЩНОСТЕЙ
            # Extract entities as nodes
            extracted_nodes = await extract_nodes(
                self.clients, episode, previous_episodes, entity_types, excluded_entity_types
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
