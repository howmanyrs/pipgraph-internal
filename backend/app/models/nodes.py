"""
PipGraph Node Wrappers - Extensions to Graphiti nodes.

Provides PipGraph-specific extensions to base Graphiti node types:
- PipGraphEpisodicNode: Extended EpisodicNode with Obsidian-specific fields
- PipGraphEntityNode: Extended EntityNode with PARA context fields

These wrappers enable:
- Adding custom fields without modifying Graphiti internals
- Future-proofing against Graphiti API changes
- Custom save/load logic when needed
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import Field

from graphiti_core.nodes import EpisodicNode, EntityNode, EpisodeType
from graphiti_core.driver.driver import GraphDriver


class PipGraphEpisodicNode(EpisodicNode):
    """
    Extended EpisodicNode with PipGraph-specific fields.

    Inherits all fields from EpisodicNode:
    - uuid, name, group_id, labels, created_at (from Node)
    - source, source_description, content, valid_at, entity_edges

    Adds PipGraph-specific fields:
    - obsidian_path: Full path to note in Obsidian vault
    - frontmatter: YAML frontmatter metadata from the note
    - para_context: Cached PARA context (transient, not persisted)

    IMPORTANT: para_context is NOT saved to database (No-Cache Policy).
    Context is determined dynamically via :IS_PART_OF relationships.
    """

    obsidian_path: Optional[str] = Field(
        default=None,
        description="Full path to note in Obsidian vault (e.g., 'notes/meetings/2024-01-15.md')"
    )

    frontmatter: dict[str, Any] = Field(
        default_factory=dict,
        description="YAML frontmatter metadata from the note"
    )

    # Transient field - not persisted to database
    para_context: Optional[dict[str, Any]] = Field(
        default=None,
        description="Cached PARA context (not persisted). Determined via :IS_PART_OF traversal."
    )

    async def save(self, driver: GraphDriver):
        """
        Save node to Neo4j.

        Currently uses base implementation. Override point for future customization:
        - Saving obsidian_path and frontmatter as node properties
        - Custom validation logic
        - Automatic relationship creation

        Note: para_context is NOT saved (No-Cache Policy).
        """
        return await super().save(driver)

    @classmethod
    def from_base(
        cls,
        base_node: EpisodicNode,
        obsidian_path: Optional[str] = None,
        frontmatter: Optional[dict[str, Any]] = None
    ) -> "PipGraphEpisodicNode":
        """
        Create PipGraphEpisodicNode from base EpisodicNode.

        Utility method for converting existing Graphiti nodes to PipGraph nodes.

        Args:
            base_node: Existing EpisodicNode from Graphiti
            obsidian_path: Optional path to source note
            frontmatter: Optional YAML frontmatter dict

        Returns:
            PipGraphEpisodicNode with all base fields plus PipGraph extensions
        """
        return cls(
            uuid=base_node.uuid,
            name=base_node.name,
            group_id=base_node.group_id,
            labels=base_node.labels,
            created_at=base_node.created_at,
            source=base_node.source,
            source_description=base_node.source_description,
            content=base_node.content,
            valid_at=base_node.valid_at,
            entity_edges=base_node.entity_edges,
            obsidian_path=obsidian_path,
            frontmatter=frontmatter or {},
        )


class PipGraphEntityNode(EntityNode):
    """
    Extended EntityNode with PipGraph-specific fields.

    Inherits all fields from EntityNode:
    - uuid, name, group_id, labels, created_at (from Node)
    - name_embedding, summary, attributes

    Adds PipGraph-specific fields:
    - para_type: PARA classification (Project/Area/Resource/Archive)
    - obsidian_path: Source note path if entity was extracted from a note

    Note: EntityNode already has 'attributes' dict for custom data.
    These explicit fields provide type safety and documentation.
    """

    para_type: Optional[str] = Field(
        default=None,
        description="PARA type: 'Project', 'Area', 'Resource', or 'Archive'"
    )

    obsidian_path: Optional[str] = Field(
        default=None,
        description="Source note path if entity was extracted from a note"
    )

    async def save(self, driver: GraphDriver):
        """
        Save node to Neo4j.

        Currently uses base implementation. Override point for future customization:
        - Auto-setting labels based on para_type
        - Validation of PARA type values
        - Custom indexing logic
        """
        return await super().save(driver)

    @classmethod
    def from_base(
        cls,
        base_node: EntityNode,
        para_type: Optional[str] = None,
        obsidian_path: Optional[str] = None
    ) -> "PipGraphEntityNode":
        """
        Create PipGraphEntityNode from base EntityNode.

        Utility method for converting existing Graphiti nodes to PipGraph nodes.

        Args:
            base_node: Existing EntityNode from Graphiti
            para_type: Optional PARA classification
            obsidian_path: Optional source note path

        Returns:
            PipGraphEntityNode with all base fields plus PipGraph extensions
        """
        return cls(
            uuid=base_node.uuid,
            name=base_node.name,
            group_id=base_node.group_id,
            labels=base_node.labels,
            created_at=base_node.created_at,
            name_embedding=base_node.name_embedding,
            summary=base_node.summary,
            attributes=base_node.attributes,
            para_type=para_type,
            obsidian_path=obsidian_path,
        )
