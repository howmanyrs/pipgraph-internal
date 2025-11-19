"""Neo4j schema setup: constraints and indexes for PipGraph database.

This module creates the database schema required for:
- PARA containers (Project, Area, Resource, Archive)
- Episodic nodes (Episode)
- Entity nodes
- Detailed suggestion relationships
"""

from neo4j import GraphDatabase
from config.settings import settings
import logging

logger = logging.getLogger(__name__)


def create_constraints(driver):
    """Create uniqueness constraints for node identifiers.

    Constraints ensure data integrity and improve query performance.
    """
    constraints = [
        # Episodic constraint (name = file path, must be unique)
        "CREATE CONSTRAINT episodic_name_unique IF NOT EXISTS FOR (e:Episodic) REQUIRE e.name IS UNIQUE",

        # PARA container constraints (each container type has unique ID)
        "CREATE CONSTRAINT project_id_unique IF NOT EXISTS FOR (p:Project) REQUIRE p.id IS UNIQUE",
        "CREATE CONSTRAINT area_id_unique IF NOT EXISTS FOR (a:Area) REQUIRE a.id IS UNIQUE",
        "CREATE CONSTRAINT resource_id_unique IF NOT EXISTS FOR (r:Resource) REQUIRE r.id IS UNIQUE",
        "CREATE CONSTRAINT archive_id_unique IF NOT EXISTS FOR (ar:Archive) REQUIRE ar.id IS UNIQUE",
    ]

    with driver.session() as session:
        for constraint in constraints:
            try:
                session.run(constraint)
                logger.info(f"✓ Created constraint: {constraint.split('FOR')[1].split('REQUIRE')[0].strip()}")
            except Exception as e:
                logger.warning(f"Constraint already exists or error: {e}")


def create_indexes(driver):
    """Create indexes for frequently queried fields.

    Indexes improve query performance for:
    - Entity UUID lookups
    - Suggestion ID lookups (critical for granular decision processing)
    """
    indexes = [
        # Entity UUID index (for fast entity lookups)
        "CREATE INDEX entity_uuid_index IF NOT EXISTS FOR (e:Entity) ON (e.uuid)",

        # CRITICAL: Index for SUGGESTS.suggestion_id
        # Enables fast lookup of specific suggestions for user decisions
        "CREATE INDEX suggests_suggestion_id_index IF NOT EXISTS FOR ()-[r:SUGGESTS]-() ON (r.suggestion_id)",
    ]

    with driver.session() as session:
        for index in indexes:
            try:
                session.run(index)
                logger.info(f"✓ Created index: {index.split('FOR')[1].split('ON')[0].strip()}")
            except Exception as e:
                logger.warning(f"Index already exists or error: {e}")


def verify_schema(driver) -> dict:
    """Verify that all constraints and indexes are created.

    Returns:
        dict with 'constraints' and 'indexes' lists
    """
    result = {"constraints": [], "indexes": []}

    with driver.session() as session:
        # Get constraints
        constraints_result = session.run("SHOW CONSTRAINTS")
        result["constraints"] = [
            {
                "name": record.get("name"),
                "type": record.get("type"),
                "entityType": record.get("entityType"),
                "labelsOrTypes": record.get("labelsOrTypes"),
                "properties": record.get("properties"),
            }
            for record in constraints_result
        ]

        # Get indexes
        indexes_result = session.run("SHOW INDEXES")
        result["indexes"] = [
            {
                "name": record.get("name"),
                "type": record.get("type"),
                "entityType": record.get("entityType"),
                "labelsOrTypes": record.get("labelsOrTypes"),
                "properties": record.get("properties"),
            }
            for record in indexes_result
        ]

    return result


def setup_schema():
    """Main function to setup complete Neo4j schema.

    Creates all constraints and indexes, then verifies the setup.
    """
    logger.info("=== Starting Neo4j Schema Setup ===")

    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )

    try:
        # Create constraints
        logger.info("\n1. Creating constraints...")
        create_constraints(driver)

        # Create indexes
        logger.info("\n2. Creating indexes...")
        create_indexes(driver)

        # Verify setup
        logger.info("\n3. Verifying schema...")
        schema_info = verify_schema(driver)

        logger.info(f"\n✅ Schema setup complete!")
        logger.info(f"   - Constraints: {len(schema_info['constraints'])}")
        logger.info(f"   - Indexes: {len(schema_info['indexes'])}")

        return schema_info

    finally:
        driver.close()


if __name__ == "__main__":
    # CLI runner for direct execution
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s'
    )

    print("\n" + "="*60)
    print("  Neo4j Schema Setup for PipGraph")
    print("="*60 + "\n")

    schema_info = setup_schema()

    print("\n" + "="*60)
    print("  Constraints Created:")
    print("="*60)
    for constraint in schema_info["constraints"]:
        print(f"  • {constraint['name']}")
        print(f"    Type: {constraint['type']}")
        print(f"    Labels: {constraint['labelsOrTypes']}")
        print(f"    Properties: {constraint['properties']}\n")

    print("="*60)
    print("  Indexes Created:")
    print("="*60)
    for index in schema_info["indexes"]:
        print(f"  • {index['name']}")
        print(f"    Type: {index['type']}")
        print(f"    Labels/Types: {index['labelsOrTypes']}")
        print(f"    Properties: {index['properties']}\n")

    print("="*60)
    print("  ✅ Schema is ready for use!")
    print("="*60 + "\n")
