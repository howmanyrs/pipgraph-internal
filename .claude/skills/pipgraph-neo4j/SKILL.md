---
name: pipgraph-neo4j
description: Guidelines for working with graph db Neo4j in PipGraph. Use this skill when writing Neo4j CRUD operations, encountering Neo4j type serialization errors (DateTime, Date, Point), or debugging Cypher query issues in the CRUD layer.
---

# Neo4j Integration Guide

## Purpose
This skill provides essential patterns and solutions for working with Neo4j in the PipGraph backend. Use it to avoid common pitfalls, ensure proper type handling, and write efficient Cypher queries.

**Note:** All file paths in this skill are relative to the `backend/` directory (e.g., `app/crud/` refers to `backend/app/crud/`).

## 1. Critical: Type Serialization

### Problem
Neo4j returns custom types (e.g., `neo4j.time.DateTime`) that **cannot be serialized to JSON** by Pydantic/FastAPI. This causes runtime errors:

```python
pydantic_core._pydantic_core.PydanticSerializationError:
Unable to serialize unknown type: <class 'neo4j.time.DateTime'>
```

### Solution: Serialize Before Returning
Always convert Neo4j types to standard Python types before returning data from CRUD methods.

**Implementation Pattern:**

```python
from neo4j.time import DateTime as Neo4jDateTime

def _serialize_node(node_dict: dict) -> dict:
    """Convert Neo4j types to JSON-serializable types."""
    serialized = {}
    for key, value in node_dict.items():
        if isinstance(value, Neo4jDateTime):
            # Convert to ISO format string
            serialized[key] = value.iso_format()
        else:
            serialized[key] = value
    return serialized
```

**Usage in CRUD:**

```python
def get_episodic(self, path: str) -> Optional[Dict[str, Any]]:
    query = "MATCH (e:Episodic {name: $path}) RETURN e"

    with self.driver.session() as session:
        result = session.run(query, path=path)
        record = result.single()

        if record:
            # ✅ Serialize before returning
            return _serialize_node(dict(record["e"]))
        return None
```

**Common Neo4j Types:**
- `neo4j.time.DateTime` → `value.iso_format()`
- `neo4j.time.Date` → `value.iso_format()`
- `neo4j.time.Time` → `value.iso_format()`
- `neo4j.spatial.Point` → `{"x": value.x, "y": value.y}`

**Reference:** `app/crud/episodic_crud.py:20-36`

## 2. Driver Management

### Initialization Pattern
CRUD classes should accept an optional driver to support testing and connection reuse.

```python
class EpisodicCRUD:
    def __init__(self, driver=None):
        """Initialize with optional Neo4j driver."""
        self.driver = driver or GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )
        self._owns_driver = driver is None

    def __del__(self):
        """Close driver if we own it."""
        if self._owns_driver and self.driver:
            self.driver.close()
```

**Why?**
- Allows dependency injection for testing
- Prevents multiple driver instances
- Ensures proper cleanup

## 3. Session Management

### Synchronous Sessions
Use context managers for automatic session cleanup:

```python
with self.driver.session() as session:
    result = session.run(query, **parameters)
    record = result.single()
```

### Async Sessions (Future)
When migrating to async Neo4j driver:

```python
async with self.driver.session() as session:
    result = await session.run(query, **parameters)
    record = await result.single()
```

**Note:** Current PipGraph implementation uses synchronous Neo4j driver despite async FastAPI endpoints. This is acceptable for now but consider migrating to `neo4j.AsyncDriver` for better performance.

## 4. Cypher Query Patterns

### Parameterized Queries (Always)
**Rule:** Never use string interpolation in Cypher queries.

```python
# ✅ Good: Parameterized
query = "MATCH (e:Episodic {name: $path}) RETURN e"
result = session.run(query, path=user_input)

# ❌ Bad: String interpolation (SQL injection risk)
query = f"MATCH (e:Episodic {{name: '{user_input}'}}) RETURN e"
```

## 5. Error Handling

### Handle Missing Records
```python
result = session.run(query, path=path)
record = result.single()

if record:
    logger.info(f"✓ Found episodic: {path}")
    return _serialize_node(dict(record["e"]))
else:
    logger.warning(f"Episodic not found: {path}")
    return None  # Not an error, just not found
```

### Handle Connection Errors
```python
try:
    with self.driver.session() as session:
        result = session.run(query)
except Exception as e:
    logger.error(f"Neo4j error: {e}", exc_info=True)
    raise  # Let FastAPI handle it
```

## 6. Schema Management

### Constraints and Indexes
**File:** `app/db/schema.py`

**Apply on startup or manually:**
```bash
python -m app.db.schema
```

**Example constraints:**
```python
# Unique constraint on Episodic.name
CREATE CONSTRAINT episodic_name_unique IF NOT EXISTS
FOR (e:Episodic) REQUIRE e.name IS UNIQUE

# Index on suggestion_id for fast lookups
CREATE INDEX suggestion_id_index IF NOT EXISTS
FOR (s:Suggestion) ON (s.suggestion_id)
```

## 7. Common Pitfalls

### ❌ Pitfall 1: Forgetting to Serialize
```python
# Bad: Returns Neo4j DateTime
def get_node(self):
    return dict(record["e"])  # ❌ Will fail in FastAPI response
```

### ❌ Pitfall 2: String Interpolation
```python
# Bad: SQL injection risk
query = f"MATCH (e {{name: '{name}'}}) RETURN e"
```

### ❌ Pitfall 3: Not Closing Sessions
```python
# Bad: Session leak
session = self.driver.session()
result = session.run(query)
# Forgot to close!
```

### ❌ Pitfall 4: Returning Raw Node Objects
```python
# Bad: Returns Neo4j Node object
return record["e"]  # ❌ Not JSON serializable

# Good: Convert to dict and serialize
return _serialize_node(dict(record["e"]))  # ✅
```

## 8. Performance Tips

1. **Use LIMIT in queries** - Always limit results when listing nodes
2. **Create indexes** - For frequently queried properties
3. **Use OPTIONAL MATCH** - Instead of multiple queries
4. **Batch operations** - Use `UNWIND` for bulk inserts
5. **Profile queries** - Use `EXPLAIN` and `PROFILE` in Neo4j Browser
