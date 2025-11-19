#!/usr/bin/env python3
"""Cleanup test data from Neo4j database."""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from neo4j import GraphDatabase
from config.settings import settings

def cleanup():
    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )

    try:
        with driver.session() as session:
            # Delete test Episodic nodes
            session.run("MATCH (e:Episodic {name: 'Notes/test.md'}) DETACH DELETE e")
            # Delete test Episode nodes (old label)
            session.run("MATCH (e:Episode {name: 'Notes/test.md'}) DETACH DELETE e")
            # Delete test Project
            session.run("MATCH (p:Project {id: 'mock-project-alpha'}) DETACH DELETE p")

            print("✓ Cleaned up test data")
    finally:
        driver.close()

if __name__ == "__main__":
    cleanup()
