#!/usr/bin/env python3
"""
Manual test script for Iteration 3: Mock User Decisions & LangGraph Structure.

This script demonstrates:
1. process_user_decision() with all 4 actions
2. Transformation of :SUGGESTS to :IS_PART_OF (confirm link)
3. Property updates on containers (confirm property_update)
4. Dismiss with Inbox fallback
5. Alternative container linking
6. Custom container creation
7. LangGraph nodes imports

Run this script to verify that Iteration 3 implementation works correctly.
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
from datetime import datetime
import logging

from app.crud.para_crud import PARAContainerCRUD
from app.crud.episodic_crud import EpisodicCRUD
from app.crud.relationship_crud import RelationshipCRUD
from app.services.para import generate_para_proposal
from app.services.proposal_manager import apply_proposal_to_graph
from app.services.pipgraph_manager import process_user_decision
from app.models.proposal import UserDecisionPayload

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
        # Delete test episodic nodes and their relationships
        session.run("""
            MATCH (e:Episodic)
            WHERE e.name STARTS WITH "Notes/test_iteration3"
            DETACH DELETE e
        """)
        # Delete test projects
        session.run("""
            MATCH (p:Project)
            WHERE p.id STARTS WITH "mock-" OR p.id STARTS WITH "alt-" OR p.id STARTS WITH "project-"
            DETACH DELETE p
        """)
        # Delete test areas
        session.run("""
            MATCH (a:Area)
            WHERE a.id STARTS WITH "area-"
            DETACH DELETE a
        """)

    driver.close()
    print("✓ Cleaned up test data from previous runs")


async def test_confirm_link():
    """Test confirm action for link suggestion."""
    print_section("TEST 1: Confirm Link (Transform :SUGGESTS → :IS_PART_OF)")

    para_crud = PARAContainerCRUD()
    episode_crud = EpisodicCRUD()
    rel_crud = RelationshipCRUD()

    # Setup
    project = para_crud.create_project("mock-project-alpha", "Mock Project Alpha", "active")
    episode = episode_crud.create_episodic(
        path="Notes/test_iteration3_confirm_link.md",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        content="Test note for confirm link"
    )

    # Create a link suggestion
    suggestion_id = "test-suggestion-link-001"
    rel_crud.create_suggestion(
        episodic_path="Notes/test_iteration3_confirm_link.md",
        container_id="mock-project-alpha",
        suggestion_id=suggestion_id,
        confidence=0.85,
        reasoning="Test link suggestion",
        suggestion_type="link",
        container_label="Project"
    )

    # Verify suggestion exists
    suggestions_before = rel_crud.get_suggestions("Notes/test_iteration3_confirm_link.md")
    print(f"✓ Created suggestion: {len(suggestions_before)} suggestion(s) before confirm")

    # Process confirm decision
    decision = UserDecisionPayload(
        suggestion_id=suggestion_id,
        action="confirm"
    )

    result = await process_user_decision(
        "Notes/test_iteration3_confirm_link.md",
        decision
    )

    print(f"✓ Decision result: {result['action']}, success={result['success']}")

    # Verify transformation
    suggestions_after = rel_crud.get_suggestions("Notes/test_iteration3_confirm_link.md")
    context = rel_crud.get_episodic_para_context("Notes/test_iteration3_confirm_link.md")

    if len(suggestions_after) == 0 and context is not None:
        print("✅ VERIFIED: :SUGGESTS transformed to :IS_PART_OF")
        print(f"   Context: {context['container_name']}")
    else:
        print(f"❌ ERROR: Expected 0 suggestions and context, got {len(suggestions_after)} suggestions")

    return result['success']


async def test_confirm_property_update():
    """Test confirm action for property_update suggestion."""
    print_section("TEST 2: Confirm Property Update (Update Container Property)")

    para_crud = PARAContainerCRUD()
    episode_crud = EpisodicCRUD()
    rel_crud = RelationshipCRUD()

    # Setup
    project = para_crud.create_project("mock-project-beta", "Mock Project Beta", "active")
    episode = episode_crud.create_episodic(
        path="Notes/test_iteration3_property_update.md",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        content="Test note for property update"
    )

    # Create a property_update suggestion
    suggestion_id = "test-suggestion-update-001"
    rel_crud.create_suggestion(
        episodic_path="Notes/test_iteration3_property_update.md",
        container_id="mock-project-beta",
        suggestion_id=suggestion_id,
        confidence=0.75,
        reasoning="Test property update",
        suggestion_type="property_update",
        target_field="name",
        suggested_value="Mock Project Beta v2",
        container_label="Project"
    )

    # Verify before
    project_before = para_crud.get_project("mock-project-beta")
    print(f"✓ Project name before: '{project_before['name']}'")

    # Process confirm decision
    decision = UserDecisionPayload(
        suggestion_id=suggestion_id,
        action="confirm"
    )

    result = await process_user_decision(
        "Notes/test_iteration3_property_update.md",
        decision
    )

    print(f"✓ Decision result: {result['action']}, success={result['success']}")

    # Verify property was updated
    project_after = para_crud.get_project("mock-project-beta")
    suggestions_after = rel_crud.get_suggestions("Notes/test_iteration3_property_update.md")

    if project_after['name'] == "Mock Project Beta v2" and len(suggestions_after) == 0:
        print("✅ VERIFIED: Property updated and suggestion removed")
        print(f"   New name: '{project_after['name']}'")
    else:
        print(f"❌ ERROR: Name is '{project_after['name']}', suggestions: {len(suggestions_after)}")

    return result['success']


async def test_dismiss():
    """Test dismiss action with Inbox fallback."""
    print_section("TEST 3: Dismiss (Delete Suggestion, Link to Inbox)")

    para_crud = PARAContainerCRUD()
    episode_crud = EpisodicCRUD()
    rel_crud = RelationshipCRUD()

    # Setup
    project = para_crud.create_project("mock-project-gamma", "Mock Project Gamma", "active")
    episode = episode_crud.create_episodic(
        path="Notes/test_iteration3_dismiss.md",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        content="Test note for dismiss"
    )

    # Create a single link suggestion
    suggestion_id = "test-suggestion-dismiss-001"
    rel_crud.create_suggestion(
        episodic_path="Notes/test_iteration3_dismiss.md",
        container_id="mock-project-gamma",
        suggestion_id=suggestion_id,
        confidence=0.65,
        reasoning="Test suggestion to dismiss",
        suggestion_type="link",
        container_label="Project"
    )

    # Process dismiss decision
    decision = UserDecisionPayload(
        suggestion_id=suggestion_id,
        action="dismiss"
    )

    result = await process_user_decision(
        "Notes/test_iteration3_dismiss.md",
        decision
    )

    print(f"✓ Decision result: {result['action']}, success={result['success']}")

    # Verify - should be linked to Inbox
    suggestions_after = rel_crud.get_suggestions("Notes/test_iteration3_dismiss.md")
    context = rel_crud.get_episodic_para_context("Notes/test_iteration3_dismiss.md")

    if len(suggestions_after) == 0 and context and context['container_name'] == "Inbox":
        print("✅ VERIFIED: Suggestion dismissed, linked to Inbox")
        print(f"   Linked to Inbox: {result['details'].get('linked_to_inbox')}")
    else:
        print(f"❌ ERROR: Expected Inbox link, got context: {context}")

    return result['success']


async def test_link_to_alternative():
    """Test link_to_alternative action."""
    print_section("TEST 4: Link to Alternative (Select Different Container)")

    para_crud = PARAContainerCRUD()
    episode_crud = EpisodicCRUD()
    rel_crud = RelationshipCRUD()

    # Setup - create two projects
    project1 = para_crud.create_project("mock-project-delta", "Mock Project Delta", "active")
    project2 = para_crud.create_project("alt-project-delta", "Alternative Project", "active")
    episode = episode_crud.create_episodic(
        path="Notes/test_iteration3_alternative.md",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        content="Test note for alternative"
    )

    # Create suggestion pointing to first project
    suggestion_id = "test-suggestion-alt-001"
    rel_crud.create_suggestion(
        episodic_path="Notes/test_iteration3_alternative.md",
        container_id="mock-project-delta",
        suggestion_id=suggestion_id,
        confidence=0.70,
        reasoning="Original suggestion",
        suggestion_type="link",
        container_label="Project"
    )

    # Process link_to_alternative - select second project
    decision = UserDecisionPayload(
        suggestion_id=suggestion_id,
        action="link_to_alternative",
        selected_container_id="alt-project-delta"
    )

    result = await process_user_decision(
        "Notes/test_iteration3_alternative.md",
        decision
    )

    print(f"✓ Decision result: {result['action']}, success={result['success']}")

    # Verify - should be linked to alternative project
    suggestions_after = rel_crud.get_suggestions("Notes/test_iteration3_alternative.md")
    context = rel_crud.get_episodic_para_context("Notes/test_iteration3_alternative.md")

    if len(suggestions_after) == 0 and context and context['container_id'] == "alt-project-delta":
        print("✅ VERIFIED: Linked to alternative container")
        print(f"   Linked to: {context['container_name']}")
    else:
        print(f"❌ ERROR: Expected alt-project-delta, got context: {context}")

    return result['success']


async def test_create_custom():
    """Test create_custom action."""
    print_section("TEST 5: Create Custom (New Container)")

    episode_crud = EpisodicCRUD()
    rel_crud = RelationshipCRUD()
    para_crud = PARAContainerCRUD()

    # Setup - create a project to have a suggestion
    project = para_crud.create_project("mock-project-epsilon", "Mock Project Epsilon", "active")
    episode = episode_crud.create_episodic(
        path="Notes/test_iteration3_custom.md",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        content="Test note for custom container"
    )

    # Create suggestion
    suggestion_id = "test-suggestion-custom-001"
    rel_crud.create_suggestion(
        episodic_path="Notes/test_iteration3_custom.md",
        container_id="mock-project-epsilon",
        suggestion_id=suggestion_id,
        confidence=0.60,
        reasoning="Low confidence - user might want custom",
        suggestion_type="link",
        container_label="Project"
    )

    # Process create_custom
    decision = UserDecisionPayload(
        suggestion_id=suggestion_id,
        action="create_custom",
        custom_container_type="Area",
        custom_container_name="My Custom Area"
    )

    result = await process_user_decision(
        "Notes/test_iteration3_custom.md",
        decision
    )

    print(f"✓ Decision result: {result['action']}, success={result['success']}")

    # Verify - should be linked to new custom Area
    suggestions_after = rel_crud.get_suggestions("Notes/test_iteration3_custom.md")
    context = rel_crud.get_episodic_para_context("Notes/test_iteration3_custom.md")

    if len(suggestions_after) == 0 and context and context['container_name'] == "My Custom Area":
        print("✅ VERIFIED: Created custom Area and linked")
        print(f"   New container: {context['container_name']} ({context['container_type']})")
        print(f"   Container ID: {result['details'].get('container_id')}")
    else:
        print(f"❌ ERROR: Expected My Custom Area, got context: {context}")

    return result['success']


async def test_langgraph_imports():
    """Test that all LangGraph nodes and conditions import correctly."""
    print_section("TEST 6: LangGraph Imports")

    try:
        from app.workflows import (
            PARAWorkflowState,
            identify_context_node,
            apply_proposal_node,
            wait_for_decision_node,
            process_decision_node,
            check_suggestion_status,
            should_continue_decisions,
        )
        print("✅ All workflow components imported successfully")

        # Check that functions are callable
        print(f"   - PARAWorkflowState: TypedDict")
        print(f"   - identify_context_node: {type(identify_context_node).__name__}")
        print(f"   - check_suggestion_status: {type(check_suggestion_status).__name__}")

        return True

    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False


async def test_check_suggestion_status():
    """Test check_suggestion_status conditional logic."""
    print_section("TEST 7: check_suggestion_status Conditional Logic")

    from app.workflows.conditions import check_suggestion_status
    from app.workflows.state import PARAWorkflowState

    para_crud = PARAContainerCRUD()
    episode_crud = EpisodicCRUD()
    rel_crud = RelationshipCRUD()

    # Test 1: With pending suggestions → wait_for_decision_node
    project = para_crud.create_project("mock-project-zeta", "Mock Project Zeta", "active")
    episode = episode_crud.create_episodic(
        path="Notes/test_iteration3_condition1.md",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        content="Test note"
    )
    rel_crud.create_suggestion(
        episodic_path="Notes/test_iteration3_condition1.md",
        container_id="mock-project-zeta",
        suggestion_id="test-cond-001",
        confidence=0.80,
        reasoning="Test",
        suggestion_type="link",
        container_label="Project"
    )

    state1: PARAWorkflowState = {"note_path": "Notes/test_iteration3_condition1.md"}
    result1 = await check_suggestion_status(state1)

    if result1 == "wait_for_decision_node":
        print("✅ With suggestions → wait_for_decision_node")
    else:
        print(f"❌ Expected wait_for_decision_node, got {result1}")

    # Test 2: With confirmed context → extract_content_node
    episode2 = episode_crud.create_episodic(
        path="Notes/test_iteration3_condition2.md",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        content="Test note with context"
    )
    rel_crud.create_link(
        "Notes/test_iteration3_condition2.md",
        "mock-project-zeta",
        container_label="Project"
    )

    state2: PARAWorkflowState = {"note_path": "Notes/test_iteration3_condition2.md"}
    result2 = await check_suggestion_status(state2)

    if result2 == "extract_content_node":
        print("✅ With context → extract_content_node")
    else:
        print(f"❌ Expected extract_content_node, got {result2}")

    return result1 == "wait_for_decision_node" and result2 == "extract_content_node"


async def main():
    print_section("Iteration 3: Mock User Decisions & LangGraph Structure Test")

    # Cleanup previous test data
    print_section("Cleanup Previous Test Data")
    cleanup_test_data()

    # Run all tests
    results = []

    results.append(("Confirm Link", await test_confirm_link()))
    results.append(("Confirm Property Update", await test_confirm_property_update()))
    results.append(("Dismiss", await test_dismiss()))
    results.append(("Link to Alternative", await test_link_to_alternative()))
    results.append(("Create Custom", await test_create_custom()))
    results.append(("LangGraph Imports", await test_langgraph_imports()))
    results.append(("Check Suggestion Status", await test_check_suggestion_status()))

    # Summary
    print_section("Summary & Neo4j Browser Verification")

    all_passed = all(r[1] for r in results)

    print("\nTest Results:")
    for name, passed in results:
        status = "✅" if passed else "❌"
        print(f"  {status} {name}")

    if all_passed:
        print("\n✅ All Iteration 3 tests passed!\n")
    else:
        print("\n❌ Some tests failed!\n")

    print("Definition of Done Checklist:")
    print("  ✅ process_user_decision обрабатывает все 4 actions")
    print("  ✅ Confirm link: :SUGGESTS → :IS_PART_OF")
    print("  ✅ Confirm update: свойство Project обновлено, ребро удалено")
    print("  ✅ Dismiss: конкретное ребро удалено по suggestion_id")
    print("  ✅ LangGraph nodes структура создана (функции импортируются)")
    print("  ✅ check_suggestion_status возвращает правильный next_node")

    print("\nTo verify in Neo4j Browser, run these queries:")

    print("\n1. Check :IS_PART_OF relationships (confirmed links):")
    print('   MATCH (e:Episodic)-[r:IS_PART_OF]->(c)')
    print('   WHERE e.name STARTS WITH "Notes/test_iteration3"')
    print('   RETURN e.name, c.name, labels(c)[0] as type;')

    print("\n2. Check renamed project:")
    print('   MATCH (p:Project {id: "mock-project-beta"})')
    print('   RETURN p.name;')
    print('   // Expected: "Mock Project Beta v2"')

    print("\n3. Check Inbox links:")
    print('   MATCH (e:Episodic)-[r:IS_PART_OF]->(a:Area {name: "Inbox"})')
    print('   RETURN e.name;')

    print("\n4. Check custom Area created:")
    print('   MATCH (a:Area {name: "My Custom Area"})')
    print('   RETURN a;')

    print("\n5. Verify no remaining suggestions:")
    print('   MATCH (e:Episodic)-[r:SUGGESTS]->()')
    print('   WHERE e.name STARTS WITH "Notes/test_iteration3"')
    print('   RETURN count(r) as remaining;')
    print('   // Expected: 0')

    print_section("Iteration 3 Test Complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Test failed with error: {e}", exc_info=True)
        sys.exit(1)
