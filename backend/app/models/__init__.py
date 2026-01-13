"""
Models package for PipGraph backend.

Exports all Pydantic models for:
- PARA entity types (Projects, Areas, Resources, Archive)
- Graphiti node wrappers (PipGraphEpisodicNode, PipGraphEntityNode)
"""

from app.models.para_entities import Project, Area, Resource, Archive
from app.models.entity import ExtractedCandidate
from app.models.nodes import PipGraphEpisodicNode, PipGraphEntityNode

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
]
