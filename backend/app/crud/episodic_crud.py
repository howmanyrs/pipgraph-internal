"""CRUD operations for Episode nodes (Episodic memory).

Episode nodes represent individual notes/documents in the system.
They follow the No-Cache Policy: context is determined through relationship traversal,
NOT stored in node properties (no project_id field).
"""

from typing import Optional, Dict, Any
from datetime import datetime
from neo4j import GraphDatabase
from config.settings import settings
import logging

logger = logging.getLogger(__name__)


class EpisodicCRUD:
    """CRUD operations for Episode nodes."""

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

    def create_episodic(
        self,
        path: str,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        content: Optional[str] = None,
        uuid: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new Episode node.

        IMPORTANT: No-Cache Policy - Episode does NOT contain project_id or any PARA context.
        Context is determined by traversing :IS_PART_OF relationships.

        Args:
            path: File path (serves as unique identifier via name property)
            created_at: Creation timestamp (defaults to now)
            updated_at: Last update timestamp (defaults to now)
            content: Optional note content
            uuid: Optional UUID (for Graphiti compatibility)

        Returns:
            Dict with created episode properties
        """
        now = datetime.utcnow().isoformat()
        created_at = created_at.isoformat() if created_at else now
        updated_at = updated_at.isoformat() if updated_at else now

        # Build properties dict (only include non-None values)
        properties = {
            "name": path,
            "created_at": created_at,
            "valid_at": updated_at,  # Graphiti uses valid_at for versioning
        }

        if content is not None:
            properties["content"] = content

        if uuid is not None:
            properties["uuid"] = uuid

        # Build query dynamically
        query = """
        CREATE (e:Episode)
        SET e = $properties
        RETURN e
        """

        with self.driver.session() as session:
            result = session.run(query, properties=properties)
            record = result.single()

            if record:
                episode = dict(record["e"])
                logger.info(f"✓ Created Episode: {path}")
                # Verify no project_id in the node
                if "project_id" in episode:
                    logger.error(f"⚠️ VIOLATION: Episode has project_id field! This breaks No-Cache Policy!")
                return episode
            else:
                logger.error(f"✗ Failed to create Episode: {path}")
                return {}

    def get_episodic(self, path: str) -> Optional[Dict[str, Any]]:
        """Retrieve an Episode by path (name).

        Args:
            path: File path (Episode.name)

        Returns:
            Dict with episode properties or None if not found
        """
        query = """
        MATCH (e:Episode {name: $path})
        RETURN e
        """

        with self.driver.session() as session:
            result = session.run(query, path=path)
            record = result.single()

            if record:
                episode = dict(record["e"])
                # Verify No-Cache Policy
                if "project_id" in episode:
                    logger.warning(f"⚠️ Episode {path} has project_id field (violates No-Cache Policy)")
                return episode
            else:
                logger.warning(f"Episode not found: {path}")
                return None

    def update_episodic_timestamp(
        self,
        path: str,
        updated_at: Optional[datetime] = None
    ) -> bool:
        """Update the timestamp of an Episode.

        Args:
            path: File path (Episode.name)
            updated_at: New timestamp (defaults to now)

        Returns:
            True if updated, False if episode not found
        """
        now = datetime.utcnow().isoformat()
        updated_at = updated_at.isoformat() if updated_at else now

        query = """
        MATCH (e:Episode {name: $path})
        SET e.valid_at = $updated_at
        RETURN e
        """

        with self.driver.session() as session:
            result = session.run(query, path=path, updated_at=updated_at)
            record = result.single()

            if record:
                logger.info(f"✓ Updated Episode timestamp: {path}")
                return True
            else:
                logger.warning(f"Episode not found for update: {path}")
                return False

    def delete_episodic(self, path: str) -> bool:
        """Delete an Episode and all its relationships.

        Args:
            path: File path (Episode.name)

        Returns:
            True if deleted, False if not found
        """
        query = """
        MATCH (e:Episode {name: $path})
        DETACH DELETE e
        RETURN count(e) as deleted_count
        """

        with self.driver.session() as session:
            result = session.run(query, path=path)
            record = result.single()

            if record and record["deleted_count"] > 0:
                logger.info(f"✓ Deleted Episode: {path}")
                return True
            else:
                logger.warning(f"Episode not found for deletion: {path}")
                return False
