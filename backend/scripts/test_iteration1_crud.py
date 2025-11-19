#!/usr/bin/env python3
"""
Manual test script for Iteration 1 CRUD operations.

This script demonstrates:
1. Creating PARA containers (Project, Area)
2. Creating Episode nodes
3. Creating multiple :SUGGESTS relationships with different types
4. Querying and removing specific suggestions by ID
5. Creating confirmed :IS_PART_OF links
6. Retrieving PARA context

Run this script to verify that Iteration 1 implementation works correctly.
Then check results in Neo4j Browser using the verification queries.
"""

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.crud.para_crud import PARAContainerCRUD
from app.crud.episodic_crud import EpisodicCRUD
from app.crud.relationship_crud import RelationshipCRUD
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


def print_section(title: str):
    """Print a section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def main():
    print_section("Iteration 1 CRUD Operations Test")

    # Initialize CRUD classes
    para_crud = PARAContainerCRUD()
    episode_crud = EpisodicCRUD()
    rel_crud = RelationshipCRUD()

    # ========================================================================
    # STEP 1: Create PARA Containers
    # ========================================================================
    print_section("STEP 1: Creating PARA Containers")

    project = para_crud.create_project(
        project_id="mock-project-alpha",
        name="Mock Project Alpha",
        status="active"
    )
    print(f"✓ Created Project: {project}")

    inbox = para_crud.ensure_inbox_exists()
    print(f"✓ Ensured Inbox exists: {inbox}")

    # ========================================================================
    # STEP 2: Create Episode Node
    # ========================================================================
    print_section("STEP 2: Creating Episode Node")

    episode = episode_crud.create_episodic(
        path="Notes/test.md",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        content="This is a test note for Mock Project Alpha"
    )
    print(f"✓ Created Episode: {episode}")

    # Verify No-Cache Policy (no project_id field)
    if "project_id" in episode:
        print("❌ ERROR: Episode has project_id field (violates No-Cache Policy)!")
    else:
        print("✅ VERIFIED: Episode has no project_id field (No-Cache Policy)")

    # ========================================================================
    # STEP 3: Create Multiple :SUGGESTS Relationships
    # ========================================================================
    print_section("STEP 3: Creating Multiple :SUGGESTS Relationships")

    # Suggestion 1: Link suggestion
    suggestion_link = rel_crud.create_suggestion(
        episodic_path="Notes/test.md",
        container_id="mock-project-alpha",
        confidence=0.80,
        reasoning="Mock: content matches project context",
        suggestion_type="link",
        container_label="Project"
    )
    print(f"✓ Created LINK suggestion: {suggestion_link['suggestion_id'][:8]}...")

    # Suggestion 2: Property update suggestion
    suggestion_update = rel_crud.create_suggestion(
        episodic_path="Notes/test.md",
        container_id="mock-project-alpha",
        confidence=0.75,
        reasoning="Mock: note suggests project renaming",
        suggestion_type="property_update",
        target_field="name",
        suggested_value="Mock Project Alpha v2",
        container_label="Project"
    )
    print(f"✓ Created PROPERTY_UPDATE suggestion: {suggestion_update['suggestion_id'][:8]}...")

    # ========================================================================
    # STEP 4: Query All Suggestions
    # ========================================================================
    print_section("STEP 4: Querying All Suggestions")

    suggestions = rel_crud.get_suggestions("Notes/test.md")
    print(f"✓ Found {len(suggestions)} suggestions:")
    for sug in suggestions:
        print(f"  - [{sug['suggestion_type']}] confidence={sug['confidence']:.2f}")
        print(f"    ID: {sug['suggestion_id'][:16]}...")
        print(f"    Reasoning: {sug['reasoning']}")
        if sug['suggestion_type'] == 'property_update':
            print(f"    Update: {sug['target_field']} → {sug['suggested_value']}")
        print()

    # ========================================================================
    # STEP 5: Get Specific Suggestion by ID
    # ========================================================================
    print_section("STEP 5: Getting Specific Suggestion by ID")

    link_suggestion_id = suggestion_link['suggestion_id']
    specific_sug = rel_crud.get_suggestion_by_id(link_suggestion_id)
    print(f"✓ Retrieved suggestion by ID:")
    print(f"  Type: {specific_sug['suggestion_type']}")
    print(f"  Confidence: {specific_sug['confidence']}")
    print(f"  Container: {specific_sug['container_name']}")

    # ========================================================================
    # STEP 6: Check PARA Context (Should be None - no :IS_PART_OF yet)
    # ========================================================================
    print_section("STEP 6: Checking PARA Context (Before Link)")

    context = rel_crud.get_episodic_para_context("Notes/test.md")
    if context is None:
        print("✅ VERIFIED: No PARA context yet (no :IS_PART_OF relationship)")
    else:
        print(f"❌ ERROR: Found unexpected context: {context}")

    # ========================================================================
    # STEP 7: Simulate User Decision - Confirm Link Suggestion
    # ========================================================================
    print_section("STEP 7: Simulating User Decision - Confirm Link")

    # Remove the link suggestion
    removed = rel_crud.remove_suggestion(link_suggestion_id)
    print(f"✓ Removed link suggestion: {removed}")

    # Create confirmed :IS_PART_OF link
    link = rel_crud.create_link(
        episodic_path="Notes/test.md",
        container_id="mock-project-alpha",
        container_label="Project"
    )
    print(f"✓ Created :IS_PART_OF link: {link}")

    # ========================================================================
    # STEP 8: Check PARA Context (Should exist now)
    # ========================================================================
    print_section("STEP 8: Checking PARA Context (After Link)")

    context = rel_crud.get_episodic_para_context("Notes/test.md")
    if context:
        print(f"✅ VERIFIED: Episode has PARA context:")
        print(f"  Container: {context['container_name']}")
        print(f"  Type: {context['container_type']}")
        print(f"  ID: {context['container_id']}")
    else:
        print("❌ ERROR: No context found after creating link!")

    # ========================================================================
    # STEP 9: Check Remaining Suggestions
    # ========================================================================
    print_section("STEP 9: Checking Remaining Suggestions")

    remaining = rel_crud.get_suggestions("Notes/test.md")
    print(f"✓ Remaining suggestions: {len(remaining)}")
    if len(remaining) == 1:
        print(f"✅ VERIFIED: Only property_update suggestion remains")
        print(f"  Type: {remaining[0]['suggestion_type']}")
        print(f"  Target field: {remaining[0]['target_field']}")
        print(f"  Suggested value: {remaining[0]['suggested_value']}")
    else:
        print(f"❌ ERROR: Expected 1 suggestion, found {len(remaining)}")

    # ========================================================================
    # STEP 10: Cleanup Verification
    # ========================================================================
    print_section("STEP 10: Summary & Neo4j Browser Verification")

    print("\n✅ All CRUD operations completed successfully!\n")
    print("To verify in Neo4j Browser, run these queries:")
    print("\n1. Check Episode structure (no project_id):")
    print('   MATCH (e:Episode {name: "Notes/test.md"}) RETURN properties(e);')
    print("\n2. Check :IS_PART_OF relationship:")
    print('   MATCH (e:Episode {name: "Notes/test.md"})-[r:IS_PART_OF]->(p:Project)')
    print('   RETURN e.name, p.name;')
    print("\n3. Check remaining :SUGGESTS:")
    print('   MATCH (e:Episode {name: "Notes/test.md"})-[r:SUGGESTS]->(p:Project)')
    print('   RETURN r.suggestion_id, r.suggestion_type, r.target_field, r.suggested_value;')
    print("\n4. Visualize full structure:")
    print('   MATCH (e:Episode {name: "Notes/test.md"})-[r]->(c)')
    print('   RETURN e, r, c;')

    print_section("Test Complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Test failed with error: {e}", exc_info=True)
        sys.exit(1)
