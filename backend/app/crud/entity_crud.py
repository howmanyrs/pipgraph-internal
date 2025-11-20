"""CRUD operations for Entity nodes extracted from Episodic content.

This module manages Entity nodes created during L3 Context-Aware Extraction:
- Save entities with composite labels (e.g., :Entity:Concept)
- Create :MENTIONS relationships to Episodic nodes
- Batch operations for efficiency

Note: Entity nodes are separate from PARA containers (Project, Area, Resource).
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from neo4j import GraphDatabase
from config.settings import settings
from app.models.entity import ExtractedCandidate
import logging

logger = logging.getLogger(__name__)


class EntityCRUD:
    """CRUD operations for Entity nodes and :MENTIONS relationships."""

    def __init__(self, driver=None):
        """Initialize with optional Neo4j driver.

        Args:
            driver: Neo4j driver instance. If None, creates new driver from settings.
        """
        self.driver = driver or GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )
        self._owns_driver = driver is None

    def __del__(self):
        """Close driver if we own it."""
        if self._owns_driver and self.driver:
            self.driver.close()

    def save_entity_node(self, entity: ExtractedCandidate) -> Dict[str, Any]:
        """Create or update an Entity node.

        Uses MERGE for idempotency - won't duplicate if entity already exists.
        Sets labels from entity.labels (e.g., ["Entity", "Concept"]).

        Args:
            entity: ExtractedCandidate with uuid, name, labels, summary

        Returns:
            Dict with entity node properties
        """
        # Build label string for Cypher (e.g., ":Entity:Concept")
        labels_str = ":".join(entity.labels)

        query = f"""
        MERGE (e:{labels_str} {{uuid: $uuid}})
        ON CREATE SET
            e.name = $name,
            e.summary = $summary,
            e.created_at = datetime()
        ON MATCH SET
            e.name = $name,
            e.summary = $summary,
            e.updated_at = datetime()
        RETURN e
        """

        with self.driver.session() as session:
            result = session.run(
                query,
                uuid=entity.uuid,
                name=entity.name,
                summary=entity.summary
            )
            record = result.single()

            if record:
                entity_data = dict(record["e"])
                logger.info(f"✓ Saved entity: {entity.name} (uuid: {entity.uuid[:8]}...)")
                return entity_data
            else:
                logger.error(f"✗ Failed to save entity: {entity.name}")
                return {}

    def link_entity_to_episodic(
        self,
        episodic_path: str,
        entity_uuid: str,
        status: str = "confirmed"
    ) -> Dict[str, Any]:
        """Create :MENTIONS relationship between Episodic and Entity.

        The :MENTIONS relationship indicates that the Episodic (note)
        mentions or contains information about this Entity.

        Args:
            episodic_path: Episodic name (file path)
            entity_uuid: UUID of the Entity node
            status: Relationship status ("pending" or "confirmed")

        Returns:
            Dict with relationship properties
        """
        query = """
        MATCH (ep:Episodic {name: $episodic_path})
        MATCH (e:Entity {uuid: $entity_uuid})
        MERGE (ep)-[r:MENTIONS]->(e)
        ON CREATE SET
            r.status = $status,
            r.created_at = datetime()
        ON MATCH SET
            r.status = $status,
            r.updated_at = datetime()
        RETURN r, e.name as entity_name
        """

        with self.driver.session() as session:
            result = session.run(
                query,
                episodic_path=episodic_path,
                entity_uuid=entity_uuid,
                status=status
            )
            record = result.single()

            if record:
                rel_data = dict(record["r"])
                entity_name = record["entity_name"]
                logger.info(
                    f"✓ Created :MENTIONS [{status}] "
                    f"{episodic_path} -> {entity_name}"
                )
                return rel_data
            else:
                logger.error(
                    f"✗ Failed to link entity: {episodic_path} -> {entity_uuid}"
                )
                return {}

    def batch_save_entities(
        self,
        entities: List[ExtractedCandidate],
        episodic_path: str
    ) -> Dict[str, Any]:
        """Save multiple entities and link them to Episodic.

        Combines save_entity_node() and link_entity_to_episodic()
        for batch efficiency.

        Args:
            entities: List of ExtractedCandidate objects
            episodic_path: Episodic name (file path)

        Returns:
            Dict with {"saved_count": int, "linked_count": int}
        """
        saved_count = 0
        linked_count = 0

        for entity in entities:
            # Save entity node
            entity_result = self.save_entity_node(entity)
            if entity_result:
                saved_count += 1

                # Link to Episodic
                link_result = self.link_entity_to_episodic(
                    episodic_path=episodic_path,
                    entity_uuid=entity.uuid,
                    status="confirmed"
                )
                if link_result:
                    linked_count += 1

        logger.info(
            f"✓ Batch save complete: {saved_count}/{len(entities)} entities saved, "
            f"{linked_count} linked to {episodic_path}"
        )

        return {
            "saved_count": saved_count,
            "linked_count": linked_count
        }

    def get_entities_for_episodic(self, episodic_path: str) -> List[Dict[str, Any]]:
        """Retrieve all Entity nodes linked to an Episodic via :MENTIONS.

        Args:
            episodic_path: Episodic name (file path)

        Returns:
            List of dicts with entity data and relationship status
        """
        query = """
        MATCH (ep:Episodic {name: $episodic_path})-[r:MENTIONS]->(e:Entity)
        RETURN
            e.uuid as uuid,
            e.name as name,
            e.summary as summary,
            labels(e) as labels,
            r.status as status
        ORDER BY e.name
        """

        with self.driver.session() as session:
            result = session.run(query, episodic_path=episodic_path)
            entities = [dict(record) for record in result]
            logger.info(f"Found {len(entities)} entities for: {episodic_path}")
            return entities

    def get_entity_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Retrieve an Entity node by its UUID.

        Args:
            uuid: Unique entity identifier

        Returns:
            Dict with entity properties or None if not found
        """
        query = """
        MATCH (e:Entity {uuid: $uuid})
        RETURN
            e.uuid as uuid,
            e.name as name,
            e.summary as summary,
            labels(e) as labels
        """

        with self.driver.session() as session:
            result = session.run(query, uuid=uuid)
            record = result.single()

            if record:
                return dict(record)
            else:
                logger.warning(f"Entity not found: {uuid}")
                return None

    def delete_entity(self, uuid: str) -> bool:
        """Delete an Entity node and its relationships.

        Args:
            uuid: Unique entity identifier

        Returns:
            True if deleted, False if not found
        """
        query = """
        MATCH (e:Entity {uuid: $uuid})
        DETACH DELETE e
        RETURN count(e) as deleted_count
        """

        with self.driver.session() as session:
            result = session.run(query, uuid=uuid)
            record = result.single()

            if record and record["deleted_count"] > 0:
                logger.info(f"✓ Deleted entity: {uuid}")
                return True
            else:
                logger.warning(f"Entity not found for deletion: {uuid}")
                return False
