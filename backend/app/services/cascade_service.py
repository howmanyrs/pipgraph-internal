"""
Cascade Service for automatic resolution of similar suggestions.

When user confirms a suggestion, this service finds and auto-resolves
other suggestions pointing to the same container (if confidence > threshold).
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import logging

from app.crud.relationship_crud import RelationshipCRUD
from app.models.proposal import UserDecisionPayload
from config.settings import settings

logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Models for Cascade
# =============================================================================

class CascadeCandidate(BaseModel):
    """A suggestion candidate for cascade auto-resolution."""

    suggestion_id: str = Field(..., description="UUID of the suggestion")
    episodic_path: str = Field(..., description="Path of the note (Episodic name)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    reasoning: Optional[str] = Field(None, description="Reasoning for the suggestion")
    suggestion_type: str = Field(default="link", description="Type: link or property_update")

    class Config:
        json_schema_extra = {
            "example": {
                "suggestion_id": "uuid-123",
                "episodic_path": "note_b.md",
                "confidence": 0.92,
                "reasoning": "Similar content to confirmed note",
                "suggestion_type": "link"
            }
        }


class CascadeResult(BaseModel):
    """Result of cascade operation."""

    applied: List[CascadeCandidate] = Field(
        default_factory=list,
        description="Candidates that were auto-resolved (confidence >= threshold)"
    )
    skipped: List[CascadeCandidate] = Field(
        default_factory=list,
        description="Candidates that were skipped (confidence < threshold)"
    )
    threshold: float = Field(..., description="Threshold used for filtering")

    @property
    def applied_count(self) -> int:
        return len(self.applied)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

    class Config:
        json_schema_extra = {
            "example": {
                "applied": [
                    {
                        "suggestion_id": "uuid-123",
                        "episodic_path": "note_b.md",
                        "confidence": 0.92,
                        "suggestion_type": "link"
                    }
                ],
                "skipped": [
                    {
                        "suggestion_id": "uuid-456",
                        "episodic_path": "note_c.md",
                        "confidence": 0.73,
                        "suggestion_type": "link"
                    }
                ],
                "threshold": 0.85
            }
        }


class DecisionWithCascadeResult(BaseModel):
    """Combined result of user decision processing with cascade."""

    decision_result: Dict[str, Any] = Field(
        ...,
        description="Result of the primary decision processing"
    )
    cascade_result: Optional[CascadeResult] = Field(
        None,
        description="Result of cascade operation (None if no cascade)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "decision_result": {
                    "action": "confirm",
                    "success": True,
                    "container_id": "uuid-container"
                },
                "cascade_result": {
                    "applied": [{"suggestion_id": "uuid-123", "episodic_path": "note_b.md", "confidence": 0.92}],
                    "skipped": [{"suggestion_id": "uuid-456", "episodic_path": "note_c.md", "confidence": 0.73}],
                    "threshold": 0.85
                }
            }
        }


# =============================================================================
# Cascade Service
# =============================================================================

class CascadeService:
    """Service for cascade auto-resolution of similar suggestions."""

    def __init__(
        self,
        relationship_crud: Optional[RelationshipCRUD] = None,
        cascade_threshold: float = 0.85
    ):
        """Initialize CascadeService.

        Args:
            relationship_crud: CRUD instance for database operations
            cascade_threshold: Minimum confidence for auto-resolution (default 0.85)
        """
        self.relationship_crud = relationship_crud or RelationshipCRUD()
        self.cascade_threshold = cascade_threshold

    def find_cascade_candidates(
        self,
        container_id: str,
        exclude_suggestion_id: str
    ) -> List[CascadeCandidate]:
        """Find all suggestions to the same container (excluding the current one).

        Args:
            container_id: Target container ID
            exclude_suggestion_id: Suggestion ID to exclude (the one being processed)

        Returns:
            List of CascadeCandidate objects
        """
        # Get all suggestions to this container
        suggestions = self.relationship_crud.get_suggestions_by_container(container_id)

        # Filter out the current suggestion and convert to CascadeCandidate
        candidates = []
        for s in suggestions:
            if s["suggestion_id"] != exclude_suggestion_id:
                # Only include "link" type suggestions for cascade
                if s.get("suggestion_type", "link") == "link":
                    candidates.append(CascadeCandidate(
                        suggestion_id=s["suggestion_id"],
                        episodic_path=s["episodic_path"],
                        confidence=s["confidence"],
                        reasoning=s.get("reasoning"),
                        suggestion_type=s.get("suggestion_type", "link")
                    ))

        logger.info(
            f"Found {len(candidates)} cascade candidates for container "
            f"{container_id[:8]}... (excluding {exclude_suggestion_id[:8]}...)"
        )

        return candidates

    def apply_cascade(
        self,
        container_id: str,
        container_label: str,
        candidates: List[CascadeCandidate]
    ) -> CascadeResult:
        """Apply cascade to candidates based on threshold.

        Args:
            container_id: Target container ID
            container_label: Container label (Project, Area, Resource)
            candidates: List of cascade candidates

        Returns:
            CascadeResult with applied and skipped lists
        """
        # Split by threshold
        applied = []
        skipped = []

        for candidate in candidates:
            if candidate.confidence >= self.cascade_threshold:
                applied.append(candidate)
            else:
                skipped.append(candidate)

        # Batch resolve high-confidence suggestions
        if applied:
            suggestion_ids = [c.suggestion_id for c in applied]
            self.relationship_crud.batch_resolve_suggestions(
                suggestion_ids=suggestion_ids,
                container_id=container_id,
                container_label=container_label
            )

            logger.info(
                f"Cascade applied: {len(applied)} auto-resolved, "
                f"{len(skipped)} skipped (threshold: {self.cascade_threshold})"
            )
        else:
            logger.info(f"Cascade: no candidates above threshold {self.cascade_threshold}")

        return CascadeResult(
            applied=applied,
            skipped=skipped,
            threshold=self.cascade_threshold
        )

    def process_decision_with_cascade(
        self,
        suggestion_id: str,
        decision: UserDecisionPayload,
        decision_result: Dict[str, Any]
    ) -> DecisionWithCascadeResult:
        """Process user decision and apply cascade if applicable.

        This is the main entry point for cascade processing.
        Should be called after process_user_decision completes.

        Args:
            suggestion_id: ID of the processed suggestion
            decision: User decision payload
            decision_result: Result from process_user_decision

        Returns:
            DecisionWithCascadeResult with decision and cascade results
        """
        cascade_result = None

        # Only cascade on "confirm" action for "link" type suggestions
        if decision.action == "confirm" and decision_result.get("success"):
            container_id = decision_result.get("details", {}).get("container_id")
            container_label = decision_result.get("details", {}).get("container_label", "Project")

            if container_id:
                # Find candidates
                candidates = self.find_cascade_candidates(
                    container_id=container_id,
                    exclude_suggestion_id=suggestion_id
                )

                # Apply cascade if there are candidates
                if candidates:
                    cascade_result = self.apply_cascade(
                        container_id=container_id,
                        container_label=container_label,
                        candidates=candidates
                    )
                else:
                    logger.info("No cascade candidates found")
            else:
                logger.warning("No container_id in decision result, skipping cascade")

        return DecisionWithCascadeResult(
            decision_result=decision_result,
            cascade_result=cascade_result
        )
