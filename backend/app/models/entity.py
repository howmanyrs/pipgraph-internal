"""
Entity models for extracted entities from Graphiti.

These models represent entities extracted from note content
during the L3 Context-Aware Extraction phase.
"""

from pydantic import BaseModel
from typing import Optional, List


class ExtractedCandidate(BaseModel):
    """
    Entity extracted by Graphiti (or mock).

    Represents a single entity extracted from note content,
    with labels for Neo4j node creation.

    Attributes:
        uuid: Unique identifier for the entity
        name: Display name of the entity
        labels: Neo4j labels (e.g., ["Entity", "Concept"])
        summary: Brief description of the entity
    """
    uuid: str
    name: str
    labels: List[str] = ["Entity"]
    summary: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "uuid": "entity-001",
                "name": "User Authentication",
                "labels": ["Entity", "Concept"],
                "summary": "Authentication system for user login"
            }
        }
