#!/usr/bin/env python3
"""Minimal Neo4j connection test using app settings."""

from neo4j import GraphDatabase
from config.settings import settings


def main():
    """Test Neo4j connection with settings from config."""
    print("Testing Neo4j connection...")

    try:
        driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )

        with driver.session() as session:
            result = session.run("RETURN 'Hello Neo4j!' as message")
            message = result.single()["message"]
            print(f"✅ {message}")

        driver.close()
        return True

    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


if __name__ == "__main__":
    main()
