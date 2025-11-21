"""
Mock Cascade Functions for Testing

Deterministic mock functions for cascade feature testing.
Returns fixed data to enable predictable tests without real similarity search.

Mock data:
- 2 cascade candidates with confidence 0.92 and 0.73
- Only 0.92 passes the default threshold (0.85)
"""

from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# Mock Constants
# =============================================================================

# Mock suggestion IDs for deterministic testing
MOCK_CASCADE_SUGGESTION_1 = "mock-cascade-suggestion-001"
MOCK_CASCADE_SUGGESTION_2 = "mock-cascade-suggestion-002"

# Mock episodic paths
MOCK_CASCADE_EPISODIC_1 = "mock_note_cascade_1.md"
MOCK_CASCADE_EPISODIC_2 = "mock_note_cascade_2.md"


def mock_find_cascade_candidates(container_id: str) -> List[Dict[str, Any]]:
    """
    Returns fixed cascade candidates for testing.

    Always returns 2 candidates:
    - First with confidence 0.92 (passes threshold 0.85)
    - Second with confidence 0.73 (below threshold)

    Args:
        container_id: Target container ID (used for logging only)

    Returns:
        List of candidate dicts with deterministic data
    """
    candidates = [
        {
            "suggestion_id": MOCK_CASCADE_SUGGESTION_1,
            "episodic_path": MOCK_CASCADE_EPISODIC_1,
            "confidence": 0.92,
            "reasoning": "Mock cascade candidate - high confidence",
            "suggestion_type": "link",
            "container_id": container_id,
        },
        {
            "suggestion_id": MOCK_CASCADE_SUGGESTION_2,
            "episodic_path": MOCK_CASCADE_EPISODIC_2,
            "confidence": 0.73,
            "reasoning": "Mock cascade candidate - low confidence",
            "suggestion_type": "link",
            "container_id": container_id,
        }
    ]

    logger.info(
        f"[MOCK] Found {len(candidates)} cascade candidates for container "
        f"{container_id[:8] if len(container_id) > 8 else container_id}..."
    )

    return candidates


def mock_apply_cascade(
    candidates: List[Dict[str, Any]],
    threshold: float = 0.85
) -> Dict[str, Any]:
    """
    Deterministically filter candidates by threshold.

    Args:
        candidates: List of candidate dicts with confidence
        threshold: Minimum confidence for auto-resolution

    Returns:
        Dict with applied and skipped lists
    """
    applied = []
    skipped = []

    for candidate in candidates:
        confidence = candidate.get("confidence", 0)
        if confidence >= threshold:
            applied.append(candidate)
        else:
            skipped.append(candidate)

    result = {
        "applied": applied,
        "skipped": skipped,
        "applied_count": len(applied),
        "skipped_count": len(skipped),
        "threshold": threshold
    }

    logger.info(
        f"[MOCK] Cascade result: {len(applied)} applied, "
        f"{len(skipped)} skipped (threshold: {threshold})"
    )

    return result


def get_mock_cascade_test_data() -> Dict[str, Any]:
    """
    Returns complete mock data for cascade testing setup.

    Useful for test scripts that need to create test data in Neo4j.

    Returns:
        Dict with all mock IDs and expected results
    """
    return {
        "suggestions": [
            {
                "suggestion_id": MOCK_CASCADE_SUGGESTION_1,
                "episodic_path": MOCK_CASCADE_EPISODIC_1,
                "confidence": 0.92,
                "should_apply": True,  # >= 0.85
            },
            {
                "suggestion_id": MOCK_CASCADE_SUGGESTION_2,
                "episodic_path": MOCK_CASCADE_EPISODIC_2,
                "confidence": 0.73,
                "should_apply": False,  # < 0.85
            }
        ],
        "threshold": 0.85,
        "expected_applied_count": 1,
        "expected_skipped_count": 1,
    }
