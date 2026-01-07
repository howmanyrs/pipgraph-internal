"""CRUD operations for Episodic nodes (Episodic memory).

Episodic nodes represent individual notes/documents in the system.
They follow the No-Cache Policy: context is determined through relationship traversal,
NOT stored in node properties (no project_id field).

IMPORTANT: For creating Episodic nodes, use PipGraphManager.create_episode() from Service Layer.
This CRUD class provides read/update/delete operations only.

Note: Uses 'Episodic' label to match Graphiti conventions.
"""

from typing import Optional, Dict, Any
from datetime import datetime, timezone
from neo4j import GraphDatabase
from neo4j.time import DateTime as Neo4jDateTime
from config.settings import settings
import logging

logger = logging.getLogger(__name__)


def _serialize_node(node_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Neo4j types to JSON-serializable types.

    Args:
        node_dict: Dictionary with node properties from Neo4j

    Returns:
        Dictionary with serialized values
    """
    serialized = {}
    for key, value in node_dict.items():
        if isinstance(value, Neo4jDateTime):
            # Convert Neo4j DateTime to ISO format string
            serialized[key] = value.iso_format()
        else:
            serialized[key] = value
    return serialized


class EpisodicCRUD:
    """CRUD operations for Episodic nodes."""

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

    def get_episodic(self, path: str) -> Optional[Dict[str, Any]]:
        """Retrieve an Episodic by path (name).

        Args:
            path: File path (Episodic.name)

        Returns:
            Dict with episodic properties or None if not found
        """
        query = """
        MATCH (e:Episodic {name: $path})
        RETURN e
        """

        with self.driver.session() as session:
            result = session.run(query, path=path)
            record = result.single()

            if record:
                episodic = _serialize_node(dict(record["e"]))
                # Verify No-Cache Policy
                if "project_id" in episodic:
                    logger.warning(f"⚠️ Episodic {path} has project_id field (violates No-Cache Policy)")
                return episodic
            else:
                logger.warning(f"Episodic not found: {path}")
                return None

    def update_episodic_timestamp(
        self,
        path: str,
        updated_at: Optional[datetime] = None
    ) -> bool:
        """Update the timestamp of an Episodic node.

        Args:
            path: File path (Episodic.name)
            updated_at: New timestamp (defaults to now)

        Returns:
            True if updated, False if episodic not found
        """
        now = datetime.now(timezone.utc).isoformat()
        updated_at = updated_at.isoformat() if updated_at else now

        query = """
        MATCH (e:Episodic {name: $path})
        SET e.valid_at = $updated_at
        RETURN e
        """

        with self.driver.session() as session:
            result = session.run(query, path=path, updated_at=updated_at)
            record = result.single()

            if record:
                logger.info(f"✓ Updated Episodic timestamp: {path}")
                return True
            else:
                logger.warning(f"Episodic not found for update: {path}")
                return False

    def list_all_episodic(self, limit: int = 100) -> list[Dict[str, Any]]:
        """List all Episodic nodes.

        Args:
            limit: Maximum number of nodes to return (default: 100)

        Returns:
            List of dicts with episodic properties
        """
        query = """
        MATCH (e:Episodic)
        RETURN e
        ORDER BY e.created_at DESC
        LIMIT $limit
        """

        with self.driver.session() as session:
            result = session.run(query, limit=limit)
            episodics = [_serialize_node(dict(record["e"])) for record in result]
            logger.info(f"✓ Found {len(episodics)} Episodic nodes")
            return episodics

    def delete_episodic(self, path: str) -> bool:
        """Delete an Episodic node and all its relationships.

        Args:
            path: File path (Episodic.name)

        Returns:
            True if deleted, False if not found
        """
        query = """
        MATCH (e:Episodic {name: $path})
        DETACH DELETE e
        RETURN count(e) as deleted_count
        """

        with self.driver.session() as session:
            result = session.run(query, path=path)
            record = result.single()

            if record and record["deleted_count"] > 0:
                logger.info(f"✓ Deleted Episodic: {path}")
                return True
            else:
                logger.warning(f"Episodic not found for deletion: {path}")
                return False
