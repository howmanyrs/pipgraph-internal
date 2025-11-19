"""CRUD operations for PARA containers (Project, Area, Resource, Archive).

These operations manage the PARA methodology containers in Neo4j.
Containers are the organizational units that Episodes link to via :IS_PART_OF relationships.
"""

from typing import Optional, List, Dict, Any
from neo4j import GraphDatabase
from config.settings import settings
import logging

logger = logging.getLogger(__name__)


class PARAContainerCRUD:
    """CRUD operations for PARA methodology containers."""

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

    def create_project(
        self,
        project_id: str,
        name: str,
        status: str = "active"
    ) -> Dict[str, Any]:
        """Create a new Project container.

        Args:
            project_id: Unique identifier for the project
            name: Project name
            status: Project status (default: "active")

        Returns:
            Dict with created project properties
        """
        query = """
        CREATE (p:Project {
            id: $project_id,
            name: $name,
            status: $status
        })
        RETURN p
        """

        with self.driver.session() as session:
            result = session.run(
                query,
                project_id=project_id,
                name=name,
                status=status
            )
            record = result.single()

            if record:
                project = dict(record["p"])
                logger.info(f"✓ Created Project: {name} (id: {project_id})")
                return project
            else:
                logger.error(f"✗ Failed to create Project: {name}")
                return {}

    def create_area(
        self,
        area_id: str,
        name: str
    ) -> Dict[str, Any]:
        """Create a new Area container.

        Args:
            area_id: Unique identifier for the area
            name: Area name

        Returns:
            Dict with created area properties
        """
        query = """
        CREATE (a:Area {
            id: $area_id,
            name: $name
        })
        RETURN a
        """

        with self.driver.session() as session:
            result = session.run(
                query,
                area_id=area_id,
                name=name
            )
            record = result.single()

            if record:
                area = dict(record["a"])
                logger.info(f"✓ Created Area: {name} (id: {area_id})")
                return area
            else:
                logger.error(f"✗ Failed to create Area: {name}")
                return {}

    def create_resource(
        self,
        resource_id: str,
        name: str
    ) -> Dict[str, Any]:
        """Create a new Resource container.

        Args:
            resource_id: Unique identifier for the resource
            name: Resource name

        Returns:
            Dict with created resource properties
        """
        query = """
        CREATE (r:Resource {
            id: $resource_id,
            name: $name
        })
        RETURN r
        """

        with self.driver.session() as session:
            result = session.run(
                query,
                resource_id=resource_id,
                name=name
            )
            record = result.single()

            if record:
                resource = dict(record["r"])
                logger.info(f"✓ Created Resource: {name} (id: {resource_id})")
                return resource
            else:
                logger.error(f"✗ Failed to create Resource: {name}")
                return {}

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a project by ID.

        Args:
            project_id: Project identifier

        Returns:
            Dict with project properties or None if not found
        """
        query = """
        MATCH (p:Project {id: $project_id})
        RETURN p
        """

        with self.driver.session() as session:
            result = session.run(query, project_id=project_id)
            record = result.single()

            if record:
                return dict(record["p"])
            else:
                logger.warning(f"Project not found: {project_id}")
                return None

    def list_projects(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all projects, optionally filtered by status.

        Args:
            status: Optional status filter ("active", "completed", etc.)

        Returns:
            List of project dictionaries
        """
        if status:
            query = """
            MATCH (p:Project {status: $status})
            RETURN p
            ORDER BY p.name
            """
            params = {"status": status}
        else:
            query = """
            MATCH (p:Project)
            RETURN p
            ORDER BY p.name
            """
            params = {}

        with self.driver.session() as session:
            result = session.run(query, **params)
            projects = [dict(record["p"]) for record in result]
            logger.info(f"Found {len(projects)} projects" + (f" with status={status}" if status else ""))
            return projects

    def ensure_inbox_exists(self) -> Dict[str, Any]:
        """Ensure the default "Inbox" area exists.

        Creates an Inbox area if it doesn't exist, or returns existing one.
        Inbox is used as the default destination for notes without clear PARA context.

        Returns:
            Dict with Inbox area properties
        """
        query = """
        MERGE (a:Area {name: "Inbox"})
        ON CREATE SET a.id = "inbox-default"
        RETURN a
        """

        with self.driver.session() as session:
            result = session.run(query)
            record = result.single()

            if record:
                inbox = dict(record["a"])
                logger.info(f"✓ Inbox area ready: {inbox.get('id')}")
                return inbox
            else:
                logger.error("✗ Failed to create/retrieve Inbox")
                return {}
