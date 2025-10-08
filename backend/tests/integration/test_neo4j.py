"""
Neo4j Database Connection Tests

Tests for verifying Neo4j connectivity and basic operations.
Migrated from app/crud/simple_neo4j_test.py
"""

import pytest
from neo4j import GraphDatabase
from config.settings import settings


@pytest.mark.integration
def test_neo4j_connection_with_driver():
    """Test Neo4j connection using driver directly."""
    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )

    try:
        with driver.session() as session:
            result = session.run("RETURN 'Hello Neo4j!' as message")
            message = result.single()["message"]
            assert message == "Hello Neo4j!"
    finally:
        driver.close()


@pytest.mark.integration
def test_neo4j_connection_with_fixture(neo4j_session):
    """Test Neo4j connection using pytest fixture."""
    result = neo4j_session.run("RETURN 1 as num")
    record = result.single()
    assert record["num"] == 1


@pytest.mark.integration
def test_neo4j_write_and_read(neo4j_session):
    """Test writing and reading data from Neo4j."""
    # Create a test node
    neo4j_session.run(
        "CREATE (n:TestNode {name: $name, value: $value})",
        name="test_node",
        value=42
    )

    # Read it back
    result = neo4j_session.run(
        "MATCH (n:TestNode {name: $name}) RETURN n.value as value",
        name="test_node"
    )
    record = result.single()
    assert record["value"] == 42

    # Cleanup
    neo4j_session.run("MATCH (n:TestNode {name: $name}) DELETE n", name="test_node")


@pytest.mark.integration
def test_neo4j_cypher_query(neo4j_session):
    """Test executing Cypher queries."""
    # Test arithmetic
    result = neo4j_session.run("RETURN 2 + 2 as sum")
    assert result.single()["sum"] == 4

    # Test string operations
    result = neo4j_session.run("RETURN 'Hello ' + 'World' as greeting")
    assert result.single()["greeting"] == "Hello World"


@pytest.mark.integration
def test_neo4j_connection_settings():
    """Verify that Neo4j settings are properly configured."""
    assert settings.NEO4J_URI is not None
    assert settings.NEO4J_USER is not None
    assert settings.NEO4J_PASSWORD is not None
    assert settings.NEO4J_URI.startswith("bolt://") or settings.NEO4J_URI.startswith("neo4j://")
