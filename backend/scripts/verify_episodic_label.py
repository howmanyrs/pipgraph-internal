#!/usr/bin/env python3
"""Verify that Episodic label is used correctly in Neo4j."""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from neo4j import GraphDatabase
from config.settings import settings

def verify():
    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )

    try:
        with driver.session() as session:
            # Check for Episodic nodes
            result = session.run("MATCH (e:Episodic) RETURN count(e) as count, collect(e.name)[0..5] as names")
            record = result.single()
            print(f"✅ Episodic nodes: {record['count']}")
            if record['names']:
                print(f"   Examples: {record['names']}")

            # Check for old Episode nodes
            result = session.run("MATCH (e:Episode) RETURN count(e) as count")
            record = result.single()
            if record['count'] > 0:
                print(f"⚠️ Old Episode nodes still exist: {record['count']}")
            else:
                print(f"✅ No old Episode nodes (good!)")

            # Check specific test node
            result = session.run("MATCH (e:Episodic {name: 'Notes/test.md'}) RETURN labels(e) as labels, properties(e) as props")
            record = result.single()
            if record:
                print(f"\n✅ Test node exists with label: {record['labels']}")
                print(f"   Properties: {list(record['props'].keys())}")
                if 'project_id' in record['props']:
                    print("   ❌ ERROR: has project_id field!")
                else:
                    print("   ✅ No project_id field (No-Cache Policy intact)")

    finally:
        driver.close()

if __name__ == "__main__":
    verify()
