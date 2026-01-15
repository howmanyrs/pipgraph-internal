"""
Pytest Configuration and Shared Fixtures

This module provides fixtures for testing the PipGraph backend:
- Database connections (Neo4j)
- LLM client mocks and real instances
- Test data generators
"""

import pytest
import asyncio
from typing import AsyncGenerator
from neo4j import GraphDatabase
from config.settings import settings


# ============================================================================
# Session and Event Loop Configuration
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for the entire test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Neo4j Database Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def neo4j_driver():
    """
    Provide Neo4j driver for the entire test session.

    Uses settings from config. Tests should use test database.
    """
    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )
    yield driver
    driver.close()


@pytest.fixture
async def neo4j_session(neo4j_driver):
    """
    Provide Neo4j session for a single test.

    Automatically cleans up test data after each test.
    """
    session = neo4j_driver.session()
    yield session
    # Cleanup: optionally clear test data
    # session.run("MATCH (n:TestNode) DETACH DELETE n")
    session.close()


@pytest.fixture
async def clean_neo4j_db(neo4j_driver):
    """
    Clean Neo4j database before test.

    WARNING: Use with caution! Only for integration tests with test DB.
    """
    with neo4j_driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    yield
    # Optionally cleanup after as well
    with neo4j_driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")


# ============================================================================
# LLM Client Fixtures
# ============================================================================

@pytest.fixture
async def graphiti_instance():
    """
    Provide real Graphiti instance for integration tests.

    Use this fixture for tests that need actual LLM processing.
    Mark such tests with @pytest.mark.integration
    """
    from app.services.graphiti.setup_graphiti import get_graphiti
    instance = await get_graphiti()
    return instance


@pytest.fixture
def mock_llm_response():
    """
    Provide mock LLM response for unit tests.

    Returns a function that generates mock responses.
    """
    def _generate_mock(content: str = "Test response", **kwargs):
        return {
            "content": content,
            "model": "mock-model",
            **kwargs
        }
    return _generate_mock


# ============================================================================
# Test Data Fixtures
# ============================================================================

# ============================================================================
# Pytest Markers
# ============================================================================

def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests (fast, no external dependencies)"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests (require Neo4j, LLM services)"
    )
    config.addinivalue_line(
        "markers", "e2e: End-to-end tests (full application flow)"
    )
    config.addinivalue_line(
        "markers", "slow: Tests that take significant time to run"
    )
