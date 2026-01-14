"""
Models package for PipGraph backend.

Exports all Pydantic models for:
- PARA entity types (Projects, Areas, Resources, Archive)
- Graphiti node wrappers (PipGraphEpisodicNode, PipGraphEntityNode)
- Graphiti edge wrappers (PipGraphBelongsToEdge)
"""

from app.models.para_entities import Project, Area, Resource, Archive
from app.models.entity import ExtractedCandidate
from app.models.nodes import PipGraphEpisodicNode, PipGraphEntityNode
from app.models.edges import PipGraphBelongsToEdge

__all__ = [
    # PARA entities
    "Project",
    "Area",
    "Resource",
    "Archive",
    # Extracted entities
    "ExtractedCandidate",
    # Graphiti node wrappers
    "PipGraphEpisodicNode",
    "PipGraphEntityNode",
    # Graphiti edge wrappers
    "PipGraphBelongsToEdge",
]
