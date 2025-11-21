"""CRUD operations for relationships between Episodic nodes and PARA containers.

This module implements the "Granular Suggestions" approach:
- Multiple :SUGGESTS edges can exist between same Episodic and container
- Each suggestion has unique suggestion_id for atomic decision processing
- Supports both "link" and "property_update" suggestion types

Note: Uses 'Episodic' label to match Graphiti conventions.
"""

from typing import Optional, List, Dict, Any
from uuid import uuid4
from neo4j import GraphDatabase
from config.settings import settings
import logging

logger = logging.getLogger(__name__)


class RelationshipCRUD:
    """CRUD operations for Episodic-PARA relationships and suggestions."""

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

    def create_suggestion(
        self,
        episodic_path: str,
        container_id: str,
        suggestion_id: Optional[str] = None,
        confidence: float = 0.0,
        reasoning: str = "",
        suggestion_type: str = "link",
        target_field: Optional[str] = None,
        suggested_value: Optional[str] = None,
        container_label: str = "Project"
    ) -> Dict[str, Any]:
        """Create a detailed :SUGGESTS relationship.

        This creates a suggestion edge with full metadata. Multiple suggestions
        can exist between the same Episodic and container, each with unique suggestion_id.

        Args:
            episodic_path: Episodic name (file path)
            container_id: Target PARA container ID
            suggestion_id: Unique UUID for this suggestion (auto-generated if None)
            confidence: LLM confidence score (0.0-1.0)
            reasoning: Explanation for this suggestion
            suggestion_type: "link" or "property_update"
            target_field: Field to update (required for property_update)
            suggested_value: New value for field (required for property_update)
            container_label: Node label (Project, Area, Resource)

        Returns:
            Dict with suggestion relationship properties
        """
        suggestion_id = suggestion_id or str(uuid4())

        # Build relationship properties
        rel_props = {
            "suggestion_id": suggestion_id,
            "confidence": confidence,
            "reasoning": reasoning,
            "suggestion_type": suggestion_type,
        }

        # Add property_update specific fields
        if suggestion_type == "property_update":
            if target_field is None or suggested_value is None:
                raise ValueError("target_field and suggested_value required for property_update suggestions")
            rel_props["target_field"] = target_field
            rel_props["suggested_value"] = suggested_value

        query = f"""
        MATCH (e:Episodic {{name: $episodic_path}})
        MATCH (c:{container_label} {{id: $container_id}})
        CREATE (e)-[r:SUGGESTS]->(c)
        SET r = $rel_props
        RETURN r, c.name as container_name
        """

        with self.driver.session() as session:
            result = session.run(
                query,
                episodic_path=episodic_path,
                container_id=container_id,
                rel_props=rel_props
            )
            record = result.single()

            if record:
                suggestion = dict(record["r"])
                container_name = record["container_name"]
                logger.info(
                    f"✓ Created :SUGGESTS [{suggestion_type}] "
                    f"{episodic_path} -> {container_name} "
                    f"(id: {suggestion_id[:8]}...)"
                )
                return suggestion
            else:
                logger.error(f"✗ Failed to create suggestion: {episodic_path} -> {container_id}")
                return {}

    def get_suggestions(self, episodic_path: str) -> List[Dict[str, Any]]:
        """Retrieve all :SUGGESTS relationships for an Episodic node.

        Returns all active suggestions that require user decision.

        Args:
            episodic_path: Episodic name (file path)

        Returns:
            List of dicts with suggestion data (includes container info)
        """
        query = """
        MATCH (e:Episodic {name: $episodic_path})-[r:SUGGESTS]->(c)
        RETURN
            r.suggestion_id as suggestion_id,
            r.confidence as confidence,
            r.reasoning as reasoning,
            r.suggestion_type as suggestion_type,
            r.target_field as target_field,
            r.suggested_value as suggested_value,
            c.id as container_id,
            c.name as container_name,
            labels(c)[0] as container_type
        ORDER BY r.confidence DESC
        """

        with self.driver.session() as session:
            result = session.run(query, episodic_path=episodic_path)
            suggestions = [dict(record) for record in result]
            logger.info(f"Found {len(suggestions)} suggestions for: {episodic_path}")
            return suggestions

    def get_suggestion_by_id(self, suggestion_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific suggestion by its UUID.

        Args:
            suggestion_id: Unique suggestion identifier

        Returns:
            Dict with suggestion data or None if not found
        """
        query = """
        MATCH (e:Episodic)-[r:SUGGESTS {suggestion_id: $suggestion_id}]->(c)
        RETURN
            e.name as episodic_path,
            r.suggestion_id as suggestion_id,
            r.confidence as confidence,
            r.reasoning as reasoning,
            r.suggestion_type as suggestion_type,
            r.target_field as target_field,
            r.suggested_value as suggested_value,
            c.id as container_id,
            c.name as container_name,
            labels(c)[0] as container_type
        """

        with self.driver.session() as session:
            result = session.run(query, suggestion_id=suggestion_id)
            record = result.single()

            if record:
                return dict(record)
            else:
                logger.warning(f"Suggestion not found: {suggestion_id}")
                return None

    def remove_suggestion(self, suggestion_id: str) -> bool:
        """Delete a specific :SUGGESTS relationship by its UUID.

        This enables atomic decision processing - user can dismiss/confirm
        individual suggestions without affecting others.

        Args:
            suggestion_id: Unique suggestion identifier

        Returns:
            True if deleted, False if not found
        """
        query = """
        MATCH ()-[r:SUGGESTS {suggestion_id: $suggestion_id}]->()
        DELETE r
        RETURN count(r) as deleted_count
        """

        with self.driver.session() as session:
            result = session.run(query, suggestion_id=suggestion_id)
            record = result.single()

            if record and record["deleted_count"] > 0:
                logger.info(f"✓ Removed suggestion: {suggestion_id[:8]}...")
                return True
            else:
                logger.warning(f"Suggestion not found for removal: {suggestion_id}")
                return False

    def create_link(
        self,
        episodic_path: str,
        container_id: str,
        container_label: str = "Project"
    ) -> Dict[str, Any]:
        """Create a confirmed :IS_PART_OF relationship.

        This represents a finalized decision - the Episodic is now linked to a PARA container.

        Args:
            episodic_path: Episodic name (file path)
            container_id: Target PARA container ID
            container_label: Node label (Project, Area, Resource)

        Returns:
            Dict with relationship properties
        """
        query = f"""
        MATCH (e:Episodic {{name: $episodic_path}})
        MATCH (c:{container_label} {{id: $container_id}})
        MERGE (e)-[r:IS_PART_OF]->(c)
        RETURN r, c.name as container_name
        """

        with self.driver.session() as session:
            result = session.run(
                query,
                episodic_path=episodic_path,
                container_id=container_id
            )
            record = result.single()

            if record:
                link = dict(record["r"])
                container_name = record["container_name"]
                logger.info(f"✓ Created :IS_PART_OF link: {episodic_path} -> {container_name}")
                return link
            else:
                logger.error(f"✗ Failed to create link: {episodic_path} -> {container_id}")
                return {}

    def get_episodic_para_context(self, episodic_path: str) -> Optional[Dict[str, Any]]:
        """Retrieve the PARA context for an Episodic via :IS_PART_OF relationship.

        IMPORTANT: This ignores :SUGGESTS relationships and only returns confirmed context.
        This is used to determine if an Episodic has finalized its PARA assignment.

        Args:
            episodic_path: Episodic name (file path)

        Returns:
            Dict with container info or None if no confirmed link exists
        """
        query = """
        MATCH (e:Episodic {name: $episodic_path})-[:IS_PART_OF]->(c)
        RETURN
            c.id as container_id,
            c.name as container_name,
            labels(c)[0] as container_type
        """

        with self.driver.session() as session:
            result = session.run(query, episodic_path=episodic_path)
            record = result.single()

            if record:
                context = dict(record)
                logger.info(f"Found PARA context: {episodic_path} -> {context['container_name']}")
                return context
            else:
                logger.info(f"No PARA context (no :IS_PART_OF): {episodic_path}")
                return None

    def remove_all_suggestions(self, episodic_path: str) -> int:
        """Remove all :SUGGESTS relationships for an Episodic node.

        Useful when user selects an alternative or creates a custom container.

        Args:
            episodic_path: Episodic name (file path)

        Returns:
            Number of suggestions removed
        """
        query = """
        MATCH (e:Episodic {name: $episodic_path})-[r:SUGGESTS]->()
        DELETE r
        RETURN count(r) as deleted_count
        """

        with self.driver.session() as session:
            result = session.run(query, episodic_path=episodic_path)
            record = result.single()
            count = record["deleted_count"] if record else 0
            logger.info(f"✓ Removed {count} suggestions for: {episodic_path}")
            return count

    # =============================================================================
    # Cascade Support Methods
    # =============================================================================

    def get_suggestions_by_container(self, container_id: str) -> List[Dict[str, Any]]:
        """Get all :SUGGESTS relationships pointing to a specific container.

        Used for cascade feature - find all suggestions to the same container
        when user confirms one suggestion.

        Args:
            container_id: Target PARA container ID

        Returns:
            List of dicts with episodic_path, confidence, suggestion_id
        """
        query = """
        MATCH (e:Episodic)-[r:SUGGESTS]->(c {id: $container_id})
        RETURN
            e.name as episodic_path,
            r.suggestion_id as suggestion_id,
            r.confidence as confidence,
            r.reasoning as reasoning,
            r.suggestion_type as suggestion_type,
            c.name as container_name,
            labels(c)[0] as container_type
        ORDER BY r.confidence DESC
        """

        with self.driver.session() as session:
            result = session.run(query, container_id=container_id)
            suggestions = [dict(record) for record in result]
            logger.info(f"Found {len(suggestions)} suggestions for container: {container_id[:8]}...")
            return suggestions

    def get_all_pending_suggestions(self) -> List[Dict[str, Any]]:
        """Get all :SUGGESTS relationships in the graph.

        Used for Inbox endpoint - returns all pending suggestions
        across all notes that require user decisions.

        Returns:
            List of dicts with note_path, container info, confidence
        """
        query = """
        MATCH (e:Episodic)-[r:SUGGESTS]->(c)
        RETURN
            e.name as note_path,
            r.suggestion_id as suggestion_id,
            r.confidence as confidence,
            r.reasoning as reasoning,
            r.suggestion_type as suggestion_type,
            c.id as container_id,
            c.name as container_name,
            labels(c)[0] as container_type
        ORDER BY r.confidence DESC
        """

        with self.driver.session() as session:
            result = session.run(query)
            suggestions = [dict(record) for record in result]
            logger.info(f"Found {len(suggestions)} total pending suggestions in graph")
            return suggestions

    def find_episodics_for_container(self, container_id: str) -> List[str]:
        """Find all Episodic nodes with :IS_PART_OF to a container.

        Used to get context for cascade - which notes are already
        confirmed as part of this container.

        Args:
            container_id: Target PARA container ID

        Returns:
            List of episodic paths (note names)
        """
        query = """
        MATCH (e:Episodic)-[:IS_PART_OF]->(c {id: $container_id})
        RETURN e.name as episodic_path
        ORDER BY e.name
        """

        with self.driver.session() as session:
            result = session.run(query, container_id=container_id)
            episodics = [record["episodic_path"] for record in result]
            logger.info(f"Found {len(episodics)} episodics linked to container: {container_id[:8]}...")
            return episodics

    def batch_resolve_suggestions(
        self,
        suggestion_ids: List[str],
        container_id: str,
        container_label: str = "Project"
    ) -> Dict[str, Any]:
        """Batch resolve multiple suggestions - delete :SUGGESTS and create :IS_PART_OF.

        Used for cascade feature - efficiently resolve multiple suggestions
        in a single transaction.

        Args:
            suggestion_ids: List of suggestion UUIDs to resolve
            container_id: Target container for :IS_PART_OF links
            container_label: Node label (Project, Area, Resource)

        Returns:
            Dict with resolved_count and created_links
        """
        if not suggestion_ids:
            return {"resolved_count": 0, "created_links": []}

        # Transaction: delete suggestions and create links
        query = f"""
        UNWIND $suggestion_ids as sid
        MATCH (e:Episodic)-[r:SUGGESTS {{suggestion_id: sid}}]->(c:{container_label} {{id: $container_id}})
        WITH e, r, c
        DELETE r
        WITH e, c
        MERGE (e)-[link:IS_PART_OF]->(c)
        RETURN e.name as episodic_path, c.name as container_name
        """

        with self.driver.session() as session:
            result = session.run(
                query,
                suggestion_ids=suggestion_ids,
                container_id=container_id
            )
            records = list(result)
            created_links = [
                {"episodic_path": r["episodic_path"], "container_name": r["container_name"]}
                for r in records
            ]

            logger.info(
                f"✓ Batch resolved {len(created_links)} suggestions -> "
                f"container {container_id[:8]}..."
            )

            return {
                "resolved_count": len(created_links),
                "created_links": created_links
            }
