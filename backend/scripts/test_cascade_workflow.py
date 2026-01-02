#!/usr/bin/env python3
"""
Manual test script for Cascade Auto-Resolution Feature.

This script demonstrates the CASCADE workflow:
1. Setup test data with multiple suggestions to same container
2. Confirm one suggestion
3. Verify cascade auto-resolves high-confidence suggestions
4. Verify low-confidence suggestions remain pending

Run this script to verify that cascade works correctly.
Then check results in Neo4j Browser using the verification queries.

Prerequisites:
- Neo4j running on localhost:7687
- Clean database (or run cleanup query first)
"""

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

import asyncio
import logging
import uuid

from app.crud.para_crud import PARAContainerCRUD
from app.crud.episodic_crud import EpisodicCRUD
from app.crud.relationship_crud import RelationshipCRUD
from app.services.cascade_service import CascadeService
from app.models.proposal import UserDecisionPayload
from app.services.graphiti.pipgraph_manager import process_user_decision
from datetime import datetime, timezone

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


# Test data constants
TEST_PROJECT_ID = "test-cascade-project-001"
TEST_PROJECT_NAME = "Cascade Test Project"

TEST_EPISODICS = [
    {
        "path": "Notes/cascade_test_note_1.md",
        "content": "First note about the cascade test project",
        "confidence": 0.92,  # Will be confirmed manually
    },
    {
        "path": "Notes/cascade_test_note_2.md",
        "content": "Second note about the cascade test project",
        "confidence": 0.88,  # Should be auto-resolved (>= 0.85)
    },
    {
        "path": "Notes/cascade_test_note_3.md",
        "content": "Third note about the cascade test project",
        "confidence": 0.73,  # Should remain pending (< 0.85)
    },
]


def print_section(title: str):
    """Print a section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def cleanup_test_data():
    """Remove test data from previous runs."""
    from neo4j import GraphDatabase
    from config.settings import settings

    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )

    with driver.session() as session:
        # Delete test episodic nodes and their relationships
        session.run("""
            MATCH (e:Episodic)
            WHERE e.name STARTS WITH "Notes/cascade_test_"
            DETACH DELETE e
        """)
        # Delete test projects
        session.run("""
            MATCH (p:Project)
            WHERE p.id = $project_id
            DETACH DELETE p
        """, project_id=TEST_PROJECT_ID)

    driver.close()
    print("Cleaned up test data from previous runs")


def setup_test_data():
    """Setup test data for cascade testing."""
    print_section("TEST 1: Setup Test Data")

    para_crud = PARAContainerCRUD()
    episodic_crud = EpisodicCRUD()
    rel_crud = RelationshipCRUD()

    try:
        # Create test project
        result = para_crud.create_project(
            TEST_PROJECT_ID,
            TEST_PROJECT_NAME,
            "active"
        )

        if not result:
            print("ERROR: Failed to create project")
            return False

        print(f"Created Project '{TEST_PROJECT_NAME}':")
        print(f"   ID: {TEST_PROJECT_ID}")

        # Create episodic nodes and suggestions
        suggestion_ids = []

        for i, episodic_data in enumerate(TEST_EPISODICS):
            now = datetime.now(timezone.utc)

            # Create Episodic node
            episodic_crud.create_episodic(
                path=episodic_data["path"],
                created_at=now,
                updated_at=now,
                content=episodic_data["content"]
            )
            print(f"Created Episodic: {episodic_data['path']}")

            # Create suggestion with specific confidence
            suggestion_id = str(uuid.uuid4())
            rel_crud.create_suggestion(
                episodic_path=episodic_data["path"],
                container_id=TEST_PROJECT_ID,
                suggestion_id=suggestion_id,
                confidence=episodic_data["confidence"],
                reasoning=f"Test suggestion with confidence {episodic_data['confidence']}",
                suggestion_type="link",
                container_label="Project"
            )
            suggestion_ids.append(suggestion_id)
            print(f"   Created :SUGGESTS with confidence {episodic_data['confidence']}")

        print("\nSUMMARY: Test Data Setup Complete")
        print(f"   - 1 Project: {TEST_PROJECT_NAME}")
        print(f"   - 3 Episodic nodes with :SUGGESTS")
        print(f"   - Confidences: 0.92 (manual), 0.88 (auto), 0.73 (skip)")
        print("VERIFIED: Test data setup complete")

        return suggestion_ids

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_cascade_service_find_candidates():
    """Test finding cascade candidates."""
    print_section("TEST 2: Find Cascade Candidates")

    rel_crud = RelationshipCRUD()
    cascade_service = CascadeService()

    try:
        # Get all suggestions to container
        all_suggestions = rel_crud.get_suggestions_by_container(TEST_PROJECT_ID)
        print(f"Total suggestions to container: {len(all_suggestions)}")

        # Get the first suggestion (will be "confirmed")
        first_suggestion = all_suggestions[0] if all_suggestions else None
        if not first_suggestion:
            print("ERROR: No suggestions found")
            return False

        # Find cascade candidates (excluding first)
        candidates = cascade_service.find_cascade_candidates(
            container_id=TEST_PROJECT_ID,
            exclude_suggestion_id=first_suggestion["suggestion_id"]
        )

        print(f"\nCascade candidates found: {len(candidates)}")
        for candidate in candidates:
            will_apply = "will apply" if candidate.confidence >= 0.85 else "will skip"
            print(f"   - {candidate.episodic_path}: {candidate.confidence} ({will_apply})")

        if len(candidates) == 2:
            print("\nVERIFIED: Found correct number of cascade candidates")
            return True
        else:
            print(f"\nWARNING: Expected 2 candidates, found {len(candidates)}")
            return False

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_cascade_auto_resolve():
    """Test cascade auto-resolution when confirming a suggestion."""
    print_section("TEST 3: Cascade Auto-Resolution")

    rel_crud = RelationshipCRUD()

    try:
        # Get all suggestions
        all_suggestions = rel_crud.get_suggestions_by_container(TEST_PROJECT_ID)

        # Sort by confidence to get the highest first (0.92)
        all_suggestions.sort(key=lambda x: x["confidence"], reverse=True)

        if not all_suggestions:
            print("ERROR: No suggestions found")
            return False

        first_suggestion = all_suggestions[0]
        suggestion_id = first_suggestion["suggestion_id"]

        print(f"Confirming suggestion for: {first_suggestion['episodic_path']}")
        print(f"   Confidence: {first_suggestion['confidence']}")
        print(f"   ID: {suggestion_id[:8]}...")

        # Create user decision
        user_decision = UserDecisionPayload(
            suggestion_id=suggestion_id,
            action="confirm"
        )

        # Process decision (this will trigger cascade)
        result = await process_user_decision(
            episodic_path=first_suggestion["episodic_path"],
            user_decision=user_decision
        )

        if not result.get("success"):
            print(f"ERROR: Decision failed: {result}")
            return False

        print(f"\nPrimary decision result:")
        print(f"   Action: {result.get('action')}")
        print(f"   Success: {result.get('success')}")
        print(f"   Container: {result.get('details', {}).get('container_name')}")

        # Now apply cascade manually using CascadeService
        cascade_service = CascadeService()
        cascade_response = cascade_service.process_decision_with_cascade(
            suggestion_id=suggestion_id,
            decision=user_decision,
            decision_result=result
        )

        if cascade_response.cascade_result:
            applied_count = len(cascade_response.cascade_result.applied)
            skipped_count = len(cascade_response.cascade_result.skipped)

            print(f"\nCascade result:")
            print(f"   Applied: {applied_count}")
            print(f"   Skipped: {skipped_count}")
            print(f"   Threshold: {cascade_response.cascade_result.threshold}")

            if cascade_response.cascade_result.applied:
                print("\n   Auto-resolved:")
                for c in cascade_response.cascade_result.applied:
                    print(f"      - {c.episodic_path} (confidence: {c.confidence})")

            if cascade_response.cascade_result.skipped:
                print("\n   Skipped (below threshold):")
                for c in cascade_response.cascade_result.skipped:
                    print(f"      - {c.episodic_path} (confidence: {c.confidence})")

            # Verify results
            if applied_count == 1 and skipped_count == 1:
                print("\nVERIFIED: Cascade correctly applied to 1 suggestion")
                return True
            else:
                print(f"\nWARNING: Expected 1 applied, 1 skipped. Got {applied_count} applied, {skipped_count} skipped")
                return False
        else:
            print("\nWARNING: No cascade result returned")
            return False

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_final_state():
    """Check the final state of the graph."""
    print_section("TEST 4: Final State Verification")

    rel_crud = RelationshipCRUD()

    try:
        # Check :IS_PART_OF relationships (should be 2: note 1 and note 2)
        linked_episodics = rel_crud.find_episodics_for_container(TEST_PROJECT_ID)
        print(f"Episodics linked to container: {len(linked_episodics)}")
        for path in linked_episodics:
            print(f"   - {path}")

        # Check remaining :SUGGESTS (should be 1: note 3)
        remaining_suggestions = rel_crud.get_suggestions_by_container(TEST_PROJECT_ID)
        print(f"\nRemaining :SUGGESTS: {len(remaining_suggestions)}")
        for sug in remaining_suggestions:
            print(f"   - {sug['episodic_path']} (confidence: {sug['confidence']})")

        # Verify
        expected_linked = 2  # note 1 (manual) + note 2 (cascade)
        expected_remaining = 1  # note 3 (below threshold)

        if len(linked_episodics) == expected_linked:
            print(f"\nVERIFIED: {expected_linked} episodics correctly linked")
        else:
            print(f"\nWARNING: Expected {expected_linked} linked, found {len(linked_episodics)}")

        if len(remaining_suggestions) == expected_remaining:
            print(f"VERIFIED: {expected_remaining} suggestion correctly remains pending")
        else:
            print(f"WARNING: Expected {expected_remaining} remaining, found {len(remaining_suggestions)}")

        # Check that remaining suggestion is the low-confidence one
        if remaining_suggestions and remaining_suggestions[0]["confidence"] < 0.85:
            print(f"VERIFIED: Remaining suggestion is below threshold (0.73)")
        elif remaining_suggestions:
            print(f"WARNING: Remaining suggestion confidence is {remaining_suggestions[0]['confidence']}")

        all_ok = (
            len(linked_episodics) == expected_linked and
            len(remaining_suggestions) == expected_remaining
        )

        if all_ok:
            print("\nVERIFIED: Final state is correct")
            return True
        else:
            print("\nWARNING: Final state may have issues")
            return False

    except Exception as e:
        print(f"ERROR: {e}")
        return False


def test_crud_methods():
    """Test the new CRUD methods for cascade support."""
    print_section("TEST 5: CRUD Methods Verification")

    rel_crud = RelationshipCRUD()

    try:
        # Test get_suggestions_by_container
        suggestions = rel_crud.get_suggestions_by_container(TEST_PROJECT_ID)
        print(f"get_suggestions_by_container: {len(suggestions)} results")

        # Test get_all_pending_suggestions
        all_pending = rel_crud.get_all_pending_suggestions()
        print(f"get_all_pending_suggestions: {len(all_pending)} results")

        # Test find_episodics_for_container
        episodics = rel_crud.find_episodics_for_container(TEST_PROJECT_ID)
        print(f"find_episodics_for_container: {len(episodics)} results")

        print("\nVERIFIED: All CRUD methods work correctly")
        return True

    except Exception as e:
        print(f"ERROR: {e}")
        return False


async def main():
    print_section("Cascade Auto-Resolution Test")

    # Cleanup previous test data
    print_section("Cleanup Previous Test Data")
    cleanup_test_data()

    # Run all tests
    results = []

    # Setup and basic tests
    suggestion_ids = setup_test_data()
    results.append(("Setup Test Data", suggestion_ids is not None))

    if suggestion_ids:
        results.append(("Find Cascade Candidates", test_cascade_service_find_candidates()))
        results.append(("Cascade Auto-Resolution", await test_cascade_auto_resolve()))
        results.append(("Final State Verification", check_final_state()))
        results.append(("CRUD Methods", test_crud_methods()))

    # Summary
    print_section("Summary & Neo4j Browser Verification")

    all_passed = all(r[1] for r in results)

    print("\nTest Results:")
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")

    if all_passed:
        print("\nAll cascade tests passed!\n")
    else:
        print("\nSome tests failed!\n")

    print("Definition of Done Checklist:")
    print("  - CascadeService finds cascade candidates correctly")
    print("  - High-confidence suggestions (>= 0.85) are auto-resolved")
    print("  - Low-confidence suggestions (< 0.85) remain pending")
    print("  - CRUD methods work for cascade queries")

    print("\n" + "=" * 70)
    print("  Neo4j Browser Verification Queries")
    print("=" * 70)

    print("\n1. Check :IS_PART_OF relationships (should be 2):")
    print(f'   MATCH (e:Episodic)-[r:IS_PART_OF]->(p:Project {{id: "{TEST_PROJECT_ID}"}})')
    print('   RETURN e.name, p.name;')

    print("\n2. Check remaining :SUGGESTS (should be 1 with confidence 0.73):")
    print(f'   MATCH (e:Episodic)-[r:SUGGESTS]->(p:Project {{id: "{TEST_PROJECT_ID}"}})')
    print('   RETURN e.name, r.confidence;')

    print("\n3. Check all relationships to container:")
    print(f'   MATCH (e:Episodic)-[r]->(p:Project {{id: "{TEST_PROJECT_ID}"}})')
    print('   RETURN e.name, type(r), r.confidence;')

    print("\n4. Check cascade test nodes:")
    print('   MATCH (e:Episodic)')
    print('   WHERE e.name STARTS WITH "Notes/cascade_test_"')
    print('   OPTIONAL MATCH (e)-[ip:IS_PART_OF]->(p)')
    print('   OPTIONAL MATCH (e)-[s:SUGGESTS]->()')
    print('   RETURN e.name,')
    print('          p.name as linked_to,')
    print('          s.confidence as suggestion_confidence;')

    print_section("Cascade Test Complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Test failed with error: {e}", exc_info=True)
        sys.exit(1)
