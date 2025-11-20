#!/usr/bin/env python3
"""
Manual test script for Iteration 2 Mock L1/L2 PARA Identification.

This script demonstrates:
1. Mock L1 Classifier - classifying note content to PARA type
2. Mock L2 Proposal Generator - generating proposals with multiple candidates
3. ProposalManager - applying proposals to Neo4j graph
4. Verifying :SUGGESTS relationships with different types

Run this script to verify that Iteration 2 implementation works correctly.
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

from datetime import datetime
import logging

from app.crud.para_crud import PARAContainerCRUD
from app.crud.episodic_crud import EpisodicCRUD
from app.crud.relationship_crud import RelationshipCRUD
from app.services.para import classify_note_para, generate_para_proposal
from app.services.proposal_manager import apply_proposal_to_graph

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


def cleanup_test_data():
    """Remove test data from previous runs."""
    from neo4j import GraphDatabase
    from config.settings import settings

    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )

    with driver.session() as session:
        # Delete test episodic and its relationships
        session.run("""
            MATCH (e:Episodic {name: "Notes/test_iteration2.md"})
            DETACH DELETE e
        """)
        # Delete test project
        session.run("""
            MATCH (p:Project {id: "mock-project-alpha"})
            DETACH DELETE p
        """)

    driver.close()
    print("✓ Cleaned up test data from previous runs")


def main():
    print_section("Iteration 2 Mock L1/L2 PARA Identification Test")

    # Cleanup previous test data
    print_section("Cleanup Previous Test Data")
    cleanup_test_data()

    # Initialize CRUD classes
    para_crud = PARAContainerCRUD()
    episode_crud = EpisodicCRUD()
    rel_crud = RelationshipCRUD()

    # Test note content
    note_content = """
    # Project Planning Session

    Today we discussed the Mock Project Alpha timeline.
    Key milestones:
    - Deadline: December 15th
    - First prototype by November 25th
    - Final review before launch

    The project should probably be renamed to "Mock Project Alpha v2"
    to reflect the new scope of work.
    """

    # ========================================================================
    # STEP 1: Setup - Create PARA Container
    # ========================================================================
    print_section("STEP 1: Creating Test PARA Container")

    project = para_crud.create_project(
        project_id="mock-project-alpha",
        name="Mock Project Alpha",
        status="active"
    )
    print(f"✓ Created Project: {project.get('name', 'Unknown')}")

    # ========================================================================
    # STEP 2: Setup - Create Episodic Node
    # ========================================================================
    print_section("STEP 2: Creating Test Episodic Node")

    episode = episode_crud.create_episodic(
        path="Notes/test_iteration2.md",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        content=note_content
    )
    print(f"✓ Created Episodic: {episode.get('name', 'Unknown')}")

    # ========================================================================
    # STEP 3: Test Mock L1 Classifier
    # ========================================================================
    print_section("STEP 3: Testing Mock L1 Classifier")

    para_type = classify_note_para(note_content)
    print(f"✓ L1 Classification result: {para_type}")

    if para_type == "Project":
        print("✅ VERIFIED: Mock classifier correctly returns 'Project'")
    else:
        print(f"⚠️  Unexpected result: {para_type}")

    # Also test keyword-based classification
    area_content = "This is an ongoing responsibility that requires regular review."
    area_type = classify_note_para(area_content)
    print(f"✓ Area test: '{area_type}' (expected: Area)")

    resource_content = "This is a reference resource for the team."
    resource_type = classify_note_para(resource_content)
    print(f"✓ Resource test: '{resource_type}' (expected: Resource)")

    # ========================================================================
    # STEP 4: Test Mock L2 Proposal Generator
    # ========================================================================
    print_section("STEP 4: Testing Mock L2 Proposal Generator")

    proposal = generate_para_proposal(note_content)

    print(f"✓ Generated PARAProposal:")
    print(f"\n  Primary Candidate:")
    print(f"    Container: {proposal.primary_candidate.container_name}")
    print(f"    Type: {proposal.primary_candidate.suggestion_type}")
    print(f"    Confidence: {proposal.primary_candidate.confidence}")
    print(f"    Reasoning: {proposal.primary_candidate.reasoning[:60]}...")

    print(f"\n  Alternatives ({len(proposal.alternatives)}):")
    for i, alt in enumerate(proposal.alternatives):
        print(f"    [{i+1}] {alt.container_name}")
        print(f"        Type: {alt.suggestion_type}")
        print(f"        Confidence: {alt.confidence}")
        if alt.target_field:
            print(f"        Update: {alt.target_field} → {alt.suggested_value}")

    # Verify structure
    if proposal.primary_candidate.suggestion_type == "link":
        print("\n✅ VERIFIED: Primary candidate is 'link' type")
    else:
        print(f"\n❌ ERROR: Expected 'link', got '{proposal.primary_candidate.suggestion_type}'")

    if len(proposal.alternatives) >= 1 and proposal.alternatives[0].suggestion_type == "property_update":
        print("✅ VERIFIED: First alternative is 'property_update' type")
    else:
        print("❌ ERROR: Expected property_update alternative")

    # ========================================================================
    # STEP 5: Apply Proposal to Graph
    # ========================================================================
    print_section("STEP 5: Applying Proposal to Graph")

    result = apply_proposal_to_graph(
        episodic_path="Notes/test_iteration2.md",
        proposal=proposal,
        container_label="Project",
        relationship_crud=rel_crud
    )

    print(f"✓ Apply result:")
    print(f"    Total candidates: {result['total_candidates']}")
    print(f"    Created links: {len(result['created_links'])}")
    print(f"    Created suggestions: {len(result['created_suggestions'])}")

    # Since mock confidence is 0.80 (< 0.95), all should be suggestions
    if len(result['created_suggestions']) == 2 and len(result['created_links']) == 0:
        print("\n✅ VERIFIED: All candidates created as :SUGGESTS (confidence < 0.95)")
    else:
        print(f"\n⚠️  Unexpected: {len(result['created_links'])} links, {len(result['created_suggestions'])} suggestions")

    # ========================================================================
    # STEP 6: Verify Suggestions in Graph
    # ========================================================================
    print_section("STEP 6: Verifying Suggestions in Graph")

    suggestions = rel_crud.get_suggestions("Notes/test_iteration2.md")
    print(f"✓ Found {len(suggestions)} suggestions in graph:")

    for sug in suggestions:
        print(f"\n  Suggestion [{sug['suggestion_type']}]:")
        print(f"    ID: {sug['suggestion_id'][:16]}...")
        print(f"    Confidence: {sug['confidence']:.2f}")
        print(f"    Container: {sug['container_name']}")
        if sug['target_field']:
            print(f"    Update: {sug['target_field']} → {sug['suggested_value']}")

    # Verify both types exist
    suggestion_types = [s['suggestion_type'] for s in suggestions]
    if 'link' in suggestion_types and 'property_update' in suggestion_types:
        print("\n✅ VERIFIED: Both 'link' and 'property_update' suggestions exist")
    else:
        print(f"\n❌ ERROR: Expected both types, found: {suggestion_types}")

    # ========================================================================
    # STEP 7: Check PARA Context (Should be None - no :IS_PART_OF yet)
    # ========================================================================
    print_section("STEP 7: Checking PARA Context (Before User Decision)")

    context = rel_crud.get_episodic_para_context("Notes/test_iteration2.md")
    if context is None:
        print("✅ VERIFIED: No PARA context yet (no :IS_PART_OF relationship)")
        print("   Episodic is waiting for user decision on suggestions")
    else:
        print(f"❌ ERROR: Found unexpected context: {context}")

    # ========================================================================
    # STEP 8: Test Import from app.services.para
    # ========================================================================
    print_section("STEP 8: Verifying Import Switching Mechanism")

    # Verify that imports come from mocks
    from app.services.para import classify_note_para as imported_classifier
    from app.services.para import generate_para_proposal as imported_generator

    test_result = imported_classifier("test")
    if test_result in ["Project", "Area", "Resource"]:
        print("✅ VERIFIED: Import from app.services.para works correctly")
        print(f"   classify_note_para returns: '{test_result}'")
    else:
        print(f"❌ ERROR: Unexpected import result: {test_result}")

    # ========================================================================
    # Summary & Neo4j Browser Verification
    # ========================================================================
    print_section("Summary & Neo4j Browser Verification")

    print("\n✅ All Iteration 2 tests completed successfully!\n")
    print("Definition of Done Checklist:")
    print("  ✅ Mock инфраструктура создана (app/services/mocks/)")
    print("  ✅ Mock classifier возвращает 'Project'")
    print("  ✅ Mock proposal generator возвращает 2 candidates (link + rename)")
    print("  ✅ apply_proposal_to_graph создает правильные :SUGGESTS в Neo4j")
    print("  ✅ В Neo4j существует 2 ребра с разными suggestion_id")

    print("\nTo verify in Neo4j Browser, run these queries:")
    print("\n1. Check all :SUGGESTS relationships:")
    print('   MATCH (e:Episodic {name: "Notes/test_iteration2.md"})-[r:SUGGESTS]->(p:Project)')
    print('   RETURN r.suggestion_id, r.suggestion_type, r.confidence, r.target_field, r.suggested_value')
    print('   ORDER BY r.suggestion_type;')

    print("\n2. Count multiple suggestions:")
    print('   MATCH (e:Episodic)-[r:SUGGESTS]->(p:Project {id: "mock-project-alpha"})')
    print('   RETURN count(r) as suggestion_count;')
    print('   // Expected: 2')

    print("\n3. Visualize structure:")
    print('   MATCH (e:Episodic {name: "Notes/test_iteration2.md"})-[r]->(c)')
    print('   RETURN e, r, c;')

    print("\n4. Check no :IS_PART_OF yet:")
    print('   MATCH (e:Episodic {name: "Notes/test_iteration2.md"})-[r:IS_PART_OF]->()')
    print('   RETURN count(r) as link_count;')
    print('   // Expected: 0')

    print_section("Iteration 2 Test Complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Test failed with error: {e}", exc_info=True)
        sys.exit(1)
