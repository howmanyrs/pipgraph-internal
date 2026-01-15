"""
PARA Configuration Module

Provides centralized configuration for PARA entity types to be used with Graphiti.
This module exports entity type dictionaries and edge type mappings for the PARA method
(Projects, Areas, Resources, Archive).

Based on:
- backend/.docs/custom_entities/PARA_ENTITY_DOCSTRINGS.md
- backend/.docs/custom_entities/PARA_TYPES_ARCHITECTURE.md
- backend/.docs/custom_entities/CUSTOM_ENTITIES_EXAMPLES.md

Usage:
    from config.para_config import PARA_ENTITY_TYPES, PARA_EDGE_TYPE_MAP

    # In PipGraphManager or service layer
    await manager.process_note(
        name="note.md",
        episode_body=content,
        entity_types=PARA_ENTITY_TYPES,
        edge_type_map=PARA_EDGE_TYPE_MAP,
        ...
    )
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

from app.models.para_entities import Project, Area, Resource, Archive


# Entity Types Dictionary
# Maps entity type names (as strings) to their Pydantic model classes
PARA_ENTITY_TYPES: dict[str, type[BaseModel]] = {
    "Project": Project,
    "Area": Area,
    "Resource": Resource,
    "Archive": Archive,
}


# Optional: Custom Edge Types for PARA relationships
# These define structured relationships between PARA entities
class ContributesTo(BaseModel):
    """
    Relationship: (Project) -[:CONTRIBUTES_TO]-> (Area)

    Indicates that a project contributes to or advances goals in a specific area.
    When a project completes, learnings and outcomes flow back to the parent Area.
    """
    impact_description: Optional[str] = Field(
        None,
        description="How this project contributes to the area. Extract from phrases like 'supports', 'advances', 'improves'."
    )
    completion_date: Optional[datetime] = Field(
        None,
        description="When the project completed its contribution to the area."
    )


class SpawnedFrom(BaseModel):
    """
    Relationship: (Project) -[:SPAWNED_FROM]-> (Area)

    Indicates that a project originated from an area of responsibility.
    Areas often generate projects to achieve specific goals within that domain.
    """
    reason: Optional[str] = Field(
        None,
        description="Why this project was created from the area. Look for: 'needed', 'identified gap', 'opportunity'."
    )
    created_at: Optional[datetime] = Field(
        None,
        description="When the project was created from the area."
    )


class UsesResource(BaseModel):
    """
    Relationship: (Project) -[:USES]-> (Resource) or (Area) -[:USES]-> (Resource)

    Indicates that a project or area utilizes a resource for reference or learning.
    Resources provide knowledge and context for active work.
    """
    usage_type: Optional[str] = Field(
        None,
        description="How the resource is used. Examples: 'reference material', 'learning guide', 'best practices', 'inspiration'."
    )
    relevance: Optional[str] = Field(
        None,
        description="Why this resource is relevant. Extract specific connections mentioned."
    )


# Edge Types Dictionary
# Maps edge type names to their Pydantic model classes
PARA_EDGE_TYPES: dict[str, type[BaseModel]] = {
    "ContributesTo": ContributesTo,
    "SpawnedFrom": SpawnedFrom,
    "UsesResource": UsesResource,
}


# Edge Type Map
# Defines which edge types can exist between which entity type pairs
# Format: (source_entity_type, target_entity_type): [list of allowed edge types]
PARA_EDGE_TYPE_MAP: dict[tuple[str, str], list[str]] = {
    # Project relationships
    ("Project", "Area"): ["ContributesTo", "SpawnedFrom"],
    ("Project", "Resource"): ["UsesResource"],

    # Area relationships
    ("Area", "Resource"): ["UsesResource"],
    ("Area", "Project"): ["SpawnedFrom"],  # Inverse of Project -> Area

    # Archive relationships (archived items can relate to any active type)
    ("Archive", "Project"): ["RELATES_TO"],
    ("Archive", "Area"): ["RELATES_TO"],
    ("Archive", "Resource"): ["RELATES_TO"],

    # Generic fallback for any unexpected entity pair
    ("Entity", "Entity"): ["RELATES_TO"],
}


# Helper function to get full PARA configuration
def get_para_config() -> dict:
    """
    Get complete PARA configuration for Graphiti.

    Returns:
        dict: Configuration dictionary containing entity_types, edge_types, and edge_type_map
    """
    return {
        "entity_types": PARA_ENTITY_TYPES,
        "edge_types": PARA_EDGE_TYPES,
        "edge_type_map": PARA_EDGE_TYPE_MAP,
    }
