"""
Unit Tests for Pydantic Models

Fast tests without external dependencies.
"""

import pytest
from app.models.graph import GraphData, Node, Relationship


@pytest.mark.unit
def test_node_creation():
    """Test Node model creation."""
    node = Node(
        id="node1",
        label="Person",
        properties={"name": "John", "age": 30}
    )

    assert node.id == "node1"
    assert node.label == "Person"
    assert node.properties["name"] == "John"
    assert node.properties["age"] == 30


@pytest.mark.unit
def test_relationship_creation():
    """Test Relationship model creation."""
    rel = Relationship(
        source="node1",
        target="node2",
        type="WORKS_AT",
        properties={"since": 2020}
    )

    assert rel.source == "node1"
    assert rel.target == "node2"
    assert rel.type == "WORKS_AT"
    assert rel.properties["since"] == 2020


@pytest.mark.unit
def test_graph_data_creation():
    """Test GraphData model creation."""
    nodes = [
        Node(id="n1", label="Person", properties={"name": "Alice"}),
        Node(id="n2", label="Company", properties={"name": "TechCorp"}),
    ]

    relationships = [
        Relationship(source="n1", target="n2", type="WORKS_AT", properties={})
    ]

    graph = GraphData(nodes=nodes, relationships=relationships)

    assert len(graph.nodes) == 2
    assert len(graph.relationships) == 1
    assert graph.nodes[0].properties["name"] == "Alice"


@pytest.mark.unit
def test_graph_data_empty():
    """Test GraphData with empty nodes and relationships."""
    graph = GraphData(nodes=[], relationships=[])

    assert graph.nodes == []
    assert graph.relationships == []
