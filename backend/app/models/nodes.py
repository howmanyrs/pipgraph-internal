"""
PipGraph Node Wrappers - Extensions to Graphiti nodes.

Provides PipGraph-specific extensions to base Graphiti node types:
- PipGraphEpisodicNode: Extended EpisodicNode with file metadata and content hash
- PipGraphEntityNode: Extended EntityNode with PARA type field

These wrappers enable:
- Adding custom fields without modifying Graphiti internals
- Future-proofing against Graphiti API changes
- Custom save/load logic when needed
"""

import hashlib
import json
from datetime import datetime
from typing import Any, Optional

from pydantic import Field, field_validator

from graphiti_core.nodes import EpisodicNode, EntityNode, EpisodeType
from graphiti_core.driver.driver import GraphDriver


class PipGraphEpisodicNode(EpisodicNode):
    """
    Extended EpisodicNode with PipGraph-specific fields.

    Inherits all fields from EpisodicNode:
    - uuid, name, group_id, labels, created_at (from Node)
    - source, source_description, content, valid_at, entity_edges

    Adds PipGraph-specific fields:
    - file_path: Path to source file (replaces obsidian_path)
    - frontmatter: YAML frontmatter metadata from the note
    - content_hash: SHA-256 hash of content for duplicate detection

    Note: PARA type is stored in labels (:Entity:Project), not as a separate field.
    """

    file_path: Optional[str] = Field(
        default=None,
        description="Path to source file (e.g., 'notes/meetings/2024-01-15.md')"
    )

    frontmatter: dict[str, Any] = Field(
        default_factory=dict,
        description="YAML frontmatter metadata from the note"
    )

    content_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 hash of content for duplicate detection"
    )

    status: Optional[str] = Field(
        default=None,
        description="Transient job-runner status. Active job → the job's type key "
                    "('generate_episode_name' / 'process_existing_episode'); failure "
                    "→ 'failed:<job_type>'; absent = settled. See the taxonomy in "
                    "app/services/jobs/status.py. Written around async work, cleared "
                    "on completion."
    )

    semantic_hints: list[str] = Field(
        default_factory=list,
        description="Keywords pre-extracted in the naming job (suggest-extra lever "
                    "B), incl. implied ones. Widen the make_suggestions query so a "
                    "folder matches even when the note lacks its words. NOT heavy "
                    "entity extraction (that produces :Entity nodes via MENTIONS) — "
                    "just hints on the Episodic. Stored natively as a Neo4j list "
                    "(no json.dumps, unlike frontmatter)."
    )

    def compute_content_hash(self) -> str:
        """
        Compute SHA-256 hash of episode content.

        Returns:
            Hex string of content hash (64 characters)

        Example:
            >>> episode.content = "Meeting notes..."
            >>> hash_value = episode.compute_content_hash()
            >>> episode.content_hash = hash_value
        """
        if not self.content:
            return hashlib.sha256(b"").hexdigest()
        return hashlib.sha256(self.content.encode('utf-8')).hexdigest()

    async def save(self, driver: GraphDriver):
        """
        Save node to Neo4j with PipGraph-specific fields.

        This override:
        1. Calls base EpisodicNode.save() to save standard Graphiti fields
        2. Adds PipGraph custom fields (file_path, frontmatter, content_hash) as Neo4j properties

        The custom fields are saved using SET += to avoid overwriting base fields.
        """
        # Step 1: Save base Episodic fields using Graphiti's save
        result = await super().save(driver)

        # Step 2: Add PipGraph-specific fields as additional properties
        updates = {}

        if self.file_path is not None:
            updates['file_path'] = self.file_path

        if self.frontmatter:
            # Store frontmatter as JSON string in Neo4j
            updates['frontmatter'] = json.dumps(self.frontmatter)

        if self.content_hash is not None:
            updates['content_hash'] = self.content_hash

        # `status` is a transient flag managed by the job-runner. It must survive
        # the bulk-save round-trip exactly like file_path/frontmatter: Graphiti's
        # `SET n = {...}` (in super().save() and in add_nodes_and_edges_bulk) omits
        # it, so we re-apply it here via `SET e += {...}`. This is NOT just for the
        # capture path — queued heavy-processing (process_existing_episode, P2)
        # marks the Episodic `status="process_existing_episode"` *while it runs*, and
        # the bulk save in the middle of that op would otherwise wipe the flag. The
        # re-apply in process_existing_episode (`episode.save()` after the bulk)
        # carries this through; see that method's ШАГ 10 note.
        if self.status is not None:
            updates['status'] = self.status

        # semantic_hints survives the same way as file_path/status — Graphiti's
        # `SET n = {...}` omits it, so we re-apply via `SET e += {...}`. Stored as
        # a native Neo4j list of strings (no json.dumps). Only written when
        # non-empty so an empty list never clobbers an existing one on re-save.
        if self.semantic_hints:
            updates['semantic_hints'] = self.semantic_hints

        # Only run UPDATE if we have custom fields to save
        if updates:
            query = """
            MATCH (e:Episodic {uuid: $uuid})
            SET e += $updates
            RETURN e.uuid as uuid
            """
            await driver.execute_query(query, uuid=self.uuid, updates=updates)

        return result

    @classmethod
    def from_base(
        cls,
        base_node: EpisodicNode,
        file_path: Optional[str] = None,
        frontmatter: Optional[dict[str, Any]] = None,
        content_hash: Optional[str] = None,
        status: Optional[str] = None,
        semantic_hints: Optional[list[str]] = None,
    ) -> "PipGraphEpisodicNode":
        """
        Create PipGraphEpisodicNode from base EpisodicNode.

        Utility method for converting existing Graphiti nodes to PipGraph nodes.

        Args:
            base_node: Existing EpisodicNode from Graphiti
            file_path: Optional path to source file
            frontmatter: Optional YAML frontmatter dict
            content_hash: Optional precomputed content hash
            status: Optional transient processing status (job-runner flag)
            semantic_hints: Optional pre-extracted keyword hints (lever B)

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
            file_path=file_path,
            frontmatter=frontmatter or {},
            content_hash=content_hash,
            status=status,
            semantic_hints=semantic_hints or [],
        )


class PipGraphEntityNode(EntityNode):
    """
    Extended EntityNode with PARA type field.

    Inherits all fields from EntityNode:
    - uuid, name, group_id, labels, created_at (from Node)
    - name_embedding, summary, attributes

    Adds PipGraph-specific field:
    - para_type: PARA classification (Project/Area/Resource/Archive)

    Note: EntityNode already has 'attributes' dict for custom data.
    Use attributes for flexible, type-specific properties:
    - Project: deadline, status, priority, etc.
    - Area: standard, review_frequency, etc.
    - Resource: url, category, tags, etc.
    - Archive: archived_at, original_type, etc.

    Benefits of this approach:
    - Maximum flexibility for rapid iteration
    - Easy migration between PARA types (old attributes preserved)
    - No schema constraints during MVP phase
    """

    para_type: Optional[str] = Field(
        default=None,
        description="PARA type: 'Project', 'Area', 'Resource', or 'Archive'"
    )

    file_path: Optional[str] = Field(
        default=None,
        description=(
            "Client-side filesystem binding (e.g. the vault folder that mirrors "
            "this entity). NOT identity (that is `uuid`), NOT structure (that is "
            "the BELONGS_TO hierarchy). The engine's algorithms never read it; it "
            "is an input/output for file-based clients only. Stored as a scalar in "
            "`attributes`, no UNIQUE constraint."
        )
    )

    @field_validator('para_type')
    @classmethod
    def validate_para_type(cls, v: Optional[str]) -> Optional[str]:
        """Validate para_type is a valid PARA classification."""
        if v is not None:
            valid_types = {'Project', 'Area', 'Resource', 'Archive'}
            if v not in valid_types:
                raise ValueError(
                    f"Invalid para_type '{v}'. Must be one of: {valid_types}"
                )
        return v

    async def save(self, driver: GraphDriver):
        """
        Save node to Neo4j with PipGraph-specific fields.

        This override:
        1. Merges para_type into attributes before saving
        2. Calls base EntityNode.save() which expands attributes into Neo4j properties
        3. Ensures composite labels (:Entity:Project) are preserved

        Note: EntityNode.save() already handles attributes expansion,
        so we just need to ensure para_type is in attributes.
        """
        # Merge para_type into attributes for storage
        if self.para_type:
            self.attributes['para_type'] = self.para_type

        # Merge file_path into attributes for storage (same pattern as para_type)
        if self.file_path:
            self.attributes['file_path'] = self.file_path

        # Base EntityNode.save() will expand attributes into Neo4j properties
        return await super().save(driver)

    @classmethod
    def from_base(
        cls,
        base_node: EntityNode,
        para_type: Optional[str] = None,
    ) -> "PipGraphEntityNode":
        """
        Create PipGraphEntityNode from base EntityNode.

        Utility method for converting existing Graphiti nodes to PipGraph nodes.

        Args:
            base_node: Existing EntityNode from Graphiti
            para_type: Optional PARA classification (if None, extracted from attributes or labels)

        Returns:
            PipGraphEntityNode with all base fields plus PipGraph extensions
        """
        # Extract para_type from attributes if not provided
        if para_type is None and 'para_type' in base_node.attributes:
            para_type = base_node.attributes['para_type']

        # Fallback: extract from labels (:Entity:Project -> "Project")
        if para_type is None and base_node.labels:
            valid_types = {'Project', 'Area', 'Resource', 'Archive'}
            para_labels = set(base_node.labels).intersection(valid_types)
            if para_labels:
                para_type = list(para_labels)[0]

        # Extract file_path from attributes (symmetric to para_type)
        file_path = base_node.attributes.get('file_path')

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
            file_path=file_path,
        )
