"""CRUD operations for Episodic nodes (Episodic memory).

Episodic nodes represent individual notes/documents in the system.
They follow the No-Cache Policy: context is determined through relationship traversal,
NOT stored in node properties (no project_id field).

Note: Uses 'Episodic' label to match Graphiti conventions.
"""

from typing import Optional, Dict, Any
from datetime import datetime
from neo4j import GraphDatabase
from config.settings import settings
import logging

logger = logging.getLogger(__name__)


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

    def create_episodic(
        self,
        path: str,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        content: Optional[str] = None,
        uuid: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new Episodic node.

        IMPORTANT: No-Cache Policy - Episodic does NOT contain project_id or any PARA context.
        Context is determined by traversing :IS_PART_OF relationships.

        Args:
            path: File path (serves as unique identifier via name property)
            created_at: Creation timestamp (defaults to now)
            updated_at: Last update timestamp (defaults to now)
            content: Optional note content
            uuid: Optional UUID (for Graphiti compatibility)

        Returns:
            Dict with created episodic node properties
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
        CREATE (e:Episodic)
        SET e = $properties
        RETURN e
        """

        with self.driver.session() as session:
            result = session.run(query, properties=properties)
            record = result.single()

            if record:
                episodic = dict(record["e"])
                logger.info(f"✓ Created Episodic: {path}")
                # Verify no project_id in the node
                if "project_id" in episodic:
                    logger.error("⚠️ VIOLATION: Episodic has project_id field! This breaks No-Cache Policy!")
                return episodic
            else:
                logger.error(f"✗ Failed to create Episodic: {path}")
                return {}

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
                episodic = dict(record["e"])
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
        now = datetime.utcnow().isoformat()
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
