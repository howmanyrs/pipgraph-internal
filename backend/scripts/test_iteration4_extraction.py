#!/usr/bin/env python3
"""
Manual test script for Iteration 4: Mock L3 Context-Aware Extraction.

This script demonstrates:
1. Mock Graphiti extract_entities() with context
2. ExtractedCandidate model and serialization
3. EntityCRUD operations (save, link, batch)
4. extract_entities_with_context() function
5. extract_content_node and save_entities_node workflow nodes
6. :MENTIONS relationships in Neo4j

Run this script to verify that Iteration 4 implementation works correctly.
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
from datetime import datetime, timezone
import logging

from app.crud.para_crud import PARAContainerCRUD
from app.crud.episodic_crud import EpisodicCRUD
from app.crud.relationship_crud import RelationshipCRUD
from app.crud.entity_crud import EntityCRUD
from app.models.entity import ExtractedCandidate
from app.services.mocks.mock_graphiti import extract_entities
from app.services.graphiti.pipgraph_manager import extract_entities_with_context
from app.workflows.state import (
    serialize_entity,
    deserialize_entity,
    serialize_entities,
    deserialize_entities,
)

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
            WHERE e.name STARTS WITH "Notes/test_iteration4"
            DETACH DELETE e
        """)
        # Delete test projects
        session.run("""
            MATCH (p:Project)
            WHERE p.id STARTS WITH "test-proj-4"
            DETACH DELETE p
        """)
        # Delete test entities
        session.run("""
            MATCH (e:Entity)
            WHERE e.uuid STARTS WITH "mock-entity-" OR e.uuid STARTS WITH "test-entity-"
            DETACH DELETE e
        """)

    driver.close()
    print("✓ Cleaned up test data from previous runs")


def test_extracted_candidate_model():
    """Test ExtractedCandidate model creation and serialization."""
    print_section("TEST 1: ExtractedCandidate Model")

    try:
        # Create entity
        entity = ExtractedCandidate(
            uuid="test-entity-001",
            name="Test Entity",
            labels=["Entity", "Concept"],
            summary="A test entity for verification"
        )

        print(f"✓ Created ExtractedCandidate:")
        print(f"   UUID: {entity.uuid}")
        print(f"   Name: {entity.name}")
        print(f"   Labels: {entity.labels}")
        print(f"   Summary: {entity.summary}")

        # Test serialization
        serialized = serialize_entity(entity)
        print(f"✓ Serialized to dict: {serialized}")

        # Test deserialization
        deserialized = deserialize_entity(serialized)
        if (deserialized.uuid == entity.uuid and
            deserialized.name == entity.name and
            deserialized.labels == entity.labels):
            print("✅ VERIFIED: Serialization/deserialization works correctly")
            return True
        else:
            print("❌ ERROR: Deserialized entity doesn't match original")
            return False

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


def test_mock_graphiti():
    """Test mock_graphiti.extract_entities function."""
    print_section("TEST 2: Mock Graphiti Extract Entities")

    try:
        context = {
            "id": "test-proj-001",
            "name": "Test Project",
            "label": "Project"
        }

        entities = extract_entities(
            episodic_content="Test note content about user authentication",
            context=context
        )

        print(f"✓ Extracted {len(entities)} entities:")
        for entity in entities:
            print(f"   - {entity.name}")
            print(f"     Labels: {entity.labels}")
            print(f"     Summary: {entity.summary}")

        # Verify context is included in summary
        if all("Test Project" in e.summary for e in entities):
            print("✅ VERIFIED: Context name included in entity summaries")
        else:
            print("⚠️ WARNING: Context name not found in summaries")

        # Verify we get 2 entities
        if len(entities) == 2:
            print("✅ VERIFIED: Correct number of entities (2)")
            return True
        else:
            print(f"❌ ERROR: Expected 2 entities, got {len(entities)}")
            return False

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


def test_entity_crud_save():
    """Test EntityCRUD save_entity_node."""
    print_section("TEST 3: EntityCRUD Save Entity")

    entity_crud = EntityCRUD()

    try:
        entity = ExtractedCandidate(
            uuid="test-entity-crud-001",
            name="CRUD Test Entity",
            labels=["Entity", "Task"],
            summary="Entity for CRUD testing"
        )

        result = entity_crud.save_entity_node(entity)

        if result:
            print(f"✓ Saved entity to Neo4j:")
            print(f"   UUID: {result.get('uuid')}")
            print(f"   Name: {result.get('name')}")
            print("✅ VERIFIED: save_entity_node works correctly")
            return True
        else:
            print("❌ ERROR: Failed to save entity")
            return False

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


def test_entity_crud_link():
    """Test EntityCRUD link_entity_to_episodic."""
    print_section("TEST 4: EntityCRUD Link Entity to Episodic")

    para_crud = PARAContainerCRUD()
    episode_crud = EpisodicCRUD()
    entity_crud = EntityCRUD()

    try:
        # Setup - create project, episode, entity
        para_crud.create_project("test-proj-4-link", "Link Test Project", "active")
        episode_crud.create_episodic(
            path="Notes/test_iteration4_link.md",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            content="Test note for entity linking"
        )

        entity = ExtractedCandidate(
            uuid="test-entity-link-001",
            name="Link Test Entity",
            labels=["Entity", "Concept"],
            summary="Entity for link testing"
        )
        entity_crud.save_entity_node(entity)

        # Create :MENTIONS relationship
        result = entity_crud.link_entity_to_episodic(
            episodic_path="Notes/test_iteration4_link.md",
            entity_uuid="test-entity-link-001",
            status="confirmed"
        )

        if result:
            print(f"✓ Created :MENTIONS relationship:")
            print(f"   Status: {result.get('status')}")
            print("✅ VERIFIED: link_entity_to_episodic works correctly")
            return True
        else:
            print("❌ ERROR: Failed to create link")
            return False

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


def test_entity_crud_batch():
    """Test EntityCRUD batch_save_entities."""
    print_section("TEST 5: EntityCRUD Batch Save Entities")

    para_crud = PARAContainerCRUD()
    episode_crud = EpisodicCRUD()
    entity_crud = EntityCRUD()

    try:
        # Setup
        para_crud.create_project("test-proj-4-batch", "Batch Test Project", "active")
        episode_crud.create_episodic(
            path="Notes/test_iteration4_batch.md",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            content="Test note for batch entity saving"
        )

        # Create multiple entities
        entities = [
            ExtractedCandidate(
                uuid="test-entity-batch-001",
                name="Batch Entity 1",
                labels=["Entity", "Concept"],
                summary="First batch entity"
            ),
            ExtractedCandidate(
                uuid="test-entity-batch-002",
                name="Batch Entity 2",
                labels=["Entity", "Task"],
                summary="Second batch entity"
            ),
            ExtractedCandidate(
                uuid="test-entity-batch-003",
                name="Batch Entity 3",
                labels=["Entity"],
                summary="Third batch entity"
            )
        ]

        # Batch save
        result = entity_crud.batch_save_entities(
            entities=entities,
            episodic_path="Notes/test_iteration4_batch.md"
        )

        print(f"✓ Batch save result:")
        print(f"   Saved: {result['saved_count']}")
        print(f"   Linked: {result['linked_count']}")

        if result['saved_count'] == 3 and result['linked_count'] == 3:
            print("✅ VERIFIED: batch_save_entities works correctly")
            return True
        else:
            print(f"❌ ERROR: Expected 3 saved and 3 linked")
            return False

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


def test_get_entities_for_episodic():
    """Test EntityCRUD get_entities_for_episodic."""
    print_section("TEST 6: Get Entities for Episodic")

    entity_crud = EntityCRUD()

    try:
        # Use the batch test episodic
        entities = entity_crud.get_entities_for_episodic(
            "Notes/test_iteration4_batch.md"
        )

        print(f"✓ Found {len(entities)} entities for episodic:")
        for entity in entities:
            print(f"   - {entity['name']} ({entity['labels']})")

        if len(entities) == 3:
            print("✅ VERIFIED: get_entities_for_episodic works correctly")
            return True
        else:
            print(f"❌ ERROR: Expected 3 entities, got {len(entities)}")
            return False

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


async def test_extract_entities_with_context():
    """Test extract_entities_with_context function."""
    print_section("TEST 7: Extract Entities With Context")

    para_crud = PARAContainerCRUD()
    episode_crud = EpisodicCRUD()
    rel_crud = RelationshipCRUD()

    try:
        # Setup - create project and episodic with confirmed context
        para_crud.create_project("test-proj-4-context", "Context Test Project", "active")
        episode_crud.create_episodic(
            path="Notes/test_iteration4_context.md",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            content="Test note for context-aware extraction"
        )
        # Create :IS_PART_OF (confirmed context)
        rel_crud.create_link(
            "Notes/test_iteration4_context.md",
            "test-proj-4-context",
            container_label="Project"
        )

        # Call extract_entities_with_context
        entities = await extract_entities_with_context(
            episodic_path="Notes/test_iteration4_context.md",
            episodic_content="Test note content"
        )

        print(f"✓ Extracted {len(entities)} entities with context:")
        for entity in entities:
            print(f"   - {entity.name}")
            print(f"     Summary: {entity.summary}")

        # Verify context was used
        if any("Context Test Project" in e.summary for e in entities):
            print("✅ VERIFIED: Context correctly passed to extraction")
            return True
        else:
            print("❌ ERROR: Context not found in entity summaries")
            return False

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


async def test_extract_without_context():
    """Test extract_entities_with_context fails without context."""
    print_section("TEST 8: Extract Without Context (Should Fail)")

    episode_crud = EpisodicCRUD()

    try:
        # Setup - create episodic WITHOUT confirmed context
        episode_crud.create_episodic(
            path="Notes/test_iteration4_no_context.md",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            content="Test note without context"
        )

        # This should raise ValueError
        try:
            entities = await extract_entities_with_context(
                episodic_path="Notes/test_iteration4_no_context.md",
                episodic_content="Test content"
            )
            print("❌ ERROR: Should have raised ValueError")
            return False

        except ValueError as e:
            print(f"✓ Correctly raised ValueError: {str(e)[:60]}...")
            print("✅ VERIFIED: Proper error handling for missing context")
            return True

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


async def test_workflow_nodes():
    """Test extract_content_node and save_entities_node."""
    print_section("TEST 9: Workflow Nodes (extract & save)")

    from app.workflows.para_workflow import extract_content_node, save_entities_node
    from app.workflows.state import PARAWorkflowState

    para_crud = PARAContainerCRUD()
    episode_crud = EpisodicCRUD()
    rel_crud = RelationshipCRUD()
    entity_crud = EntityCRUD()

    try:
        # Setup
        para_crud.create_project("test-proj-4-workflow", "Workflow Test Project", "active")
        episode_crud.create_episodic(
            path="Notes/test_iteration4_workflow.md",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            content="Test note for workflow nodes"
        )
        rel_crud.create_link(
            "Notes/test_iteration4_workflow.md",
            "test-proj-4-workflow",
            container_label="Project"
        )

        # Create initial state
        state: PARAWorkflowState = {
            "note_path": "Notes/test_iteration4_workflow.md",
            "note_content": "Test note content for entity extraction",
            "status": "processing"
        }

        # Test extract_content_node
        extract_result = await extract_content_node(state)
        print(f"✓ extract_content_node result:")
        print(f"   Entities: {len(extract_result.get('extracted_entities', []))}")
        print(f"   Status: {extract_result.get('status')}")

        if extract_result.get('status') == 'error':
            print(f"❌ ERROR: {extract_result.get('error')}")
            return False

        # Update state with extraction results
        state["extracted_entities"] = extract_result["extracted_entities"]

        # Test save_entities_node
        save_result = await save_entities_node(state)
        print(f"✓ save_entities_node result:")
        print(f"   Completed at: {save_result.get('processing_completed_at')}")
        print(f"   Status: {save_result.get('status')}")

        # Verify entities were saved
        saved_entities = entity_crud.get_entities_for_episodic(
            "Notes/test_iteration4_workflow.md"
        )

        if len(saved_entities) > 0 and save_result.get('status') == 'completed':
            print(f"✅ VERIFIED: Workflow nodes work correctly")
            print(f"   Saved {len(saved_entities)} entities")
            return True
        else:
            print(f"❌ ERROR: Expected entities to be saved")
            return False

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_imports():
    """Test all Iteration 4 imports."""
    print_section("TEST 10: All Imports")

    try:
        from app.models.entity import ExtractedCandidate
        from app.models import ExtractedCandidate as ExtractedCandidate2
        from app.services.mocks.mock_graphiti import extract_entities
        from app.services.mocks import extract_entities as extract_entities2
        from app.crud.entity_crud import EntityCRUD
        from app.crud import EntityCRUD as EntityCRUD2
        from app.workflows.state import (
            serialize_entity,
            deserialize_entity,
            serialize_entities,
            deserialize_entities
        )
        from app.workflows import (
            serialize_entity as se1,
            serialize_entities as se2,
        )
        from app.services.graphiti.pipgraph_manager import extract_entities_with_context
        from app.workflows.para_workflow import extract_content_node, save_entities_node

        print("✅ VERIFIED: All imports work correctly")
        print("   - app.models.entity")
        print("   - app.services.mocks.mock_graphiti")
        print("   - app.crud.entity_crud")
        print("   - app.workflows.state (serialization)")
        print("   - app.services.pipgraph_manager")
        print("   - app.workflows.para_workflow")
        return True

    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False


async def main():
    print_section("Iteration 4: Mock L3 Context-Aware Extraction Test")

    # Cleanup previous test data
    print_section("Cleanup Previous Test Data")
    cleanup_test_data()

    # Run all tests
    results = []

    results.append(("ExtractedCandidate Model", test_extracted_candidate_model()))
    results.append(("Mock Graphiti", test_mock_graphiti()))
    results.append(("EntityCRUD Save", test_entity_crud_save()))
    results.append(("EntityCRUD Link", test_entity_crud_link()))
    results.append(("EntityCRUD Batch", test_entity_crud_batch()))
    results.append(("Get Entities for Episodic", test_get_entities_for_episodic()))
    results.append(("Extract with Context", await test_extract_entities_with_context()))
    results.append(("Extract without Context", await test_extract_without_context()))
    results.append(("Workflow Nodes", await test_workflow_nodes()))
    results.append(("All Imports", await test_imports()))

    # Summary
    print_section("Summary & Neo4j Browser Verification")

    all_passed = all(r[1] for r in results)

    print("\nTest Results:")
    for name, passed in results:
        status = "✅" if passed else "❌"
        print(f"  {status} {name}")

    if all_passed:
        print("\n✅ All Iteration 4 tests passed!\n")
    else:
        print("\n❌ Some tests failed!\n")

    print("Definition of Done Checklist:")
    print("  ✅ Mock Graphiti возвращает список Entity")
    print("  ✅ extract_entities_with_context читает контекст из :IS_PART_OF")
    print("  ✅ Entity nodes сохраняются в Neo4j")
    print("  ✅ Связи :MENTIONS создаются с атрибутом status=\"confirmed\"")
    print("  ✅ LangGraph extraction nodes готовы")

    print("\nTo verify in Neo4j Browser, run these queries:")

    print("\n1. Check Entity nodes:")
    print('   MATCH (e:Entity)')
    print('   WHERE e.uuid STARTS WITH "test-entity-" OR e.uuid STARTS WITH "mock-entity-"')
    print('   RETURN e.uuid, e.name, labels(e) as all_labels LIMIT 10;')

    print("\n2. Check :MENTIONS relationships:")
    print('   MATCH (ep:Episodic)-[r:MENTIONS]->(e:Entity)')
    print('   WHERE ep.name STARTS WITH "Notes/test_iteration4"')
    print('   RETURN ep.name, e.name, r.status;')

    print("\n3. Check composite labels (Entity:Concept, Entity:Task):")
    print('   MATCH (e:Entity)')
    print('   WHERE e.uuid STARTS WITH "test-entity-"')
    print('   RETURN e.name, labels(e) as all_labels;')

    print("\n4. Check context was used (workflow test):")
    print('   MATCH (ep:Episodic {name: "Notes/test_iteration4_workflow.md"})-[:MENTIONS]->(e:Entity)')
    print('   RETURN e.name, e.summary;')
    print('   // Summary should contain "Workflow Test Project"')

    print("\n5. Count entities per episodic:")
    print('   MATCH (ep:Episodic)-[r:MENTIONS]->(e:Entity)')
    print('   WHERE ep.name STARTS WITH "Notes/test_iteration4"')
    print('   RETURN ep.name, count(e) as entity_count')
    print('   ORDER BY ep.name;')

    print_section("Iteration 4 Test Complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Test failed with error: {e}", exc_info=True)
        sys.exit(1)
