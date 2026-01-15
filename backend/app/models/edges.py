"""
PipGraph Edge Models - Custom relationship types for PARA hierarchy.

Provides PipGraph-specific edge types that extend beyond Graphiti's base edges:
- PipGraphBelongsToEdge: BELONGS_TO relationship for PARA hierarchy (Entity -> Entity)

These edges enable:
- Building nested PARA structures (Project belongs to Area, etc.)
- Organizing knowledge graph into hierarchical containers
- Querying entity relationships without Episodic constraints
"""

import logging
from abc import ABC
from datetime import datetime
from typing import ClassVar
from uuid import uuid4

from pydantic import BaseModel, Field
from graphiti_core.edges import Edge
from graphiti_core.driver.driver import GraphDriver
from graphiti_core.errors import EdgeNotFoundError

logger = logging.getLogger(__name__)


class PipGraphBelongsToEdge(Edge):
    """
    BELONGS_TO relationship between PARA entities.

    Represents hierarchical containment in PARA methodology:
    - (Project)-[:BELONGS_TO]->(Area)
    - (Area)-[:BELONGS_TO]->(Archive)
    - (Resource)-[:BELONGS_TO]->(Area)

    Unlike Graphiti's EpisodicEdge (Episodic -> Entity), this edge connects
    Entity -> Entity, allowing flexible organizational structures.

    Inherits from graphiti_core.edges.Edge:
    - uuid: Unique identifier
    - group_id: Graph partition ID
    - source_node_uuid: UUID of source Entity (child)
    - target_node_uuid: UUID of target Entity (parent)
    - created_at: Timestamp when relationship was created

    Usage:
        >>> # Create relationship: Project belongs to Area
        >>> edge = PipGraphBelongsToEdge(
        ...     source_node_uuid=project.uuid,
        ...     target_node_uuid=area.uuid,
        ...     group_id=project.group_id,
        ...     created_at=datetime.now(timezone.utc)
        ... )
        >>> await edge.save(driver)
    """

    async def save(self, driver: GraphDriver):
        """
        Save BELONGS_TO relationship to Neo4j.

        Uses MERGE semantics for idempotency (safe to call multiple times).
        Creates relationship between two Entity nodes with PARA labels.

        Cypher query structure:
        - MATCH both source and target entities
        - MERGE relationship with uuid (idempotent)
        - SET relationship properties

        Args:
            driver: Neo4j driver instance

        Returns:
            Query result from Neo4j

        Raises:
            Neo4jError: If either entity doesn't exist or query fails
        """
        query = """
        MATCH (source:Entity {uuid: $source_uuid})
        MATCH (target:Entity {uuid: $target_uuid})
        MERGE (source)-[r:BELONGS_TO {uuid: $uuid}]->(target)
        SET r.group_id = $group_id,
            r.created_at = $created_at
        RETURN r.uuid as uuid
        """

        result = await driver.execute_query(
            query,
            source_uuid=self.source_node_uuid,
            target_uuid=self.target_node_uuid,
            uuid=self.uuid,
            group_id=self.group_id,
            created_at=self.created_at,
        )

        logger.debug(f'Saved BELONGS_TO edge to Graph: {self.uuid}')

        return result

    @classmethod
    async def get_by_uuid(cls, driver: GraphDriver, uuid: str):
        """
        Retrieve BELONGS_TO edge by UUID.

        Args:
            driver: Neo4j driver instance
            uuid: Edge UUID to retrieve

        Returns:
            PipGraphBelongsToEdge instance

        Raises:
            EdgeNotFoundError: If edge with given UUID doesn't exist
        """
        records, _, _ = await driver.execute_query(
            """
            MATCH (source:Entity)-[r:BELONGS_TO {uuid: $uuid}]->(target:Entity)
            RETURN r.uuid as uuid,
                   r.group_id as group_id,
                   r.created_at as created_at,
                   source.uuid as source_node_uuid,
                   target.uuid as target_node_uuid
            """,
            uuid=uuid,
            routing_='r',
        )

        if not records:
            raise EdgeNotFoundError(uuid)

        record = records[0]
        return cls(
            uuid=record['uuid'],
            group_id=record['group_id'],
            source_node_uuid=record['source_node_uuid'],
            target_node_uuid=record['target_node_uuid'],
            created_at=record['created_at'],
        )

    @classmethod
    async def get_by_uuids(cls, driver: GraphDriver, uuids: list[str]):
        """
        Retrieve multiple BELONGS_TO edges by UUIDs.

        Args:
            driver: Neo4j driver instance
            uuids: List of edge UUIDs to retrieve

        Returns:
            List of PipGraphBelongsToEdge instances

        Raises:
            EdgeNotFoundError: If no edges found with given UUIDs
        """
        records, _, _ = await driver.execute_query(
            """
            MATCH (source:Entity)-[r:BELONGS_TO]->(target:Entity)
            WHERE r.uuid IN $uuids
            RETURN r.uuid as uuid,
                   r.group_id as group_id,
                   r.created_at as created_at,
                   source.uuid as source_node_uuid,
                   target.uuid as target_node_uuid
            """,
            uuids=uuids,
            routing_='r',
        )

        if not records:
            raise EdgeNotFoundError(uuids[0])

        edges = [
            cls(
                uuid=record['uuid'],
                group_id=record['group_id'],
                source_node_uuid=record['source_node_uuid'],
                target_node_uuid=record['target_node_uuid'],
                created_at=record['created_at'],
            )
            for record in records
        ]

        return edges

    async def delete(self, driver: GraphDriver):
        """
        Delete BELONGS_TO relationship from Neo4j.

        Args:
            driver: Neo4j driver instance
        """
        await driver.execute_query(
            """
            MATCH (source)-[r:BELONGS_TO {uuid: $uuid}]->(target)
            DELETE r
            """,
            uuid=self.uuid,
        )

        logger.debug(f'Deleted BELONGS_TO edge: {self.uuid}')

    @classmethod
    async def delete_by_uuids(cls, driver: GraphDriver, uuids: list[str]):
        """
        Delete multiple BELONGS_TO relationships by UUIDs.

        Args:
            driver: Neo4j driver instance
            uuids: List of edge UUIDs to delete
        """
        await driver.execute_query(
            """
            MATCH (source)-[r:BELONGS_TO]->(target)
            WHERE r.uuid IN $uuids
            DELETE r
            """,
            uuids=uuids,
        )

        logger.debug(f'Deleted BELONGS_TO edges: {uuids}')
