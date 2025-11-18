# Graphiti Core - Quick Reference Guide

## EpisodicNode Fields

```python
class EpisodicNode(Node):
    # From Node base class
    uuid: str                              # auto-generated UUID
    name: str                              # episode name/filename
    group_id: str                          # partition key
    labels: list[str]                      # default: []
    created_at: datetime                   # auto-generated timestamp
    
    # EpisodicNode specific
    source: EpisodeType                    # 'message', 'json', 'text'
    source_description: str                # "Obsidian note", "Email", etc.
    content: str                           # Raw episode content
    valid_at: datetime                     # When the original document was created
    entity_edges: list[str]                # UUIDs of entity edges referenced
```

**Storage**: All fields stored as direct Neo4j properties.

---

## EntityNode Fields

```python
class EntityNode(Node):
    # From Node base class
    uuid: str
    name: str
    group_id: str
    labels: list[str]
    created_at: datetime
    
    # EntityNode specific
    name_embedding: list[float] | None    # Vector for semantic search
    summary: str                           # Contextual summary from graph
    attributes: dict[str, Any]            # FREE-FORM custom fields
```

**Key Pattern**: `attributes` dict is where custom/dynamic fields go.

---

## EntityEdge Fields

```python
class EntityEdge(Edge):
    # From Edge base class
    uuid: str
    group_id: str
    source_node_uuid: str
    target_node_uuid: str
    created_at: datetime
    
    # EntityEdge specific
    name: str                              # Relationship name (e.g., "WORKS_AT")
    fact: str                              # Natural language fact
    fact_embedding: list[float] | None    # Vector for semantic search
    episodes: list[str]                    # Episode UUIDs that mention this edge
    expired_at: datetime | None            # When edge became invalid
    valid_at: datetime | None              # When edge became true
    invalid_at: datetime | None            # When edge stopped being true
    attributes: dict[str, Any]            # FREE-FORM custom fields
```

---

## Custom Fields Pattern

### Option 1: Using Entity Type Definitions (Schema-Validated)

```python
from pydantic import BaseModel

class PersonEntity(BaseModel):
    """Custom Person entity with additional fields"""
    role: str
    department: str
    hire_date: str

entity_types = {'Person': PersonEntity}
result = await graphiti.add_episode(
    name="note.md",
    episode_body="John works in Engineering",
    source_description="Obsidian note",
    reference_time=datetime.now(),
    entity_types=entity_types  # Enable custom validation
)
```

### Option 2: Using Attributes Dict (Unvalidated)

```python
node = EntityNode(
    name='John Doe',
    group_id='default',
    labels=['Person'],
    attributes={
        'department': 'Engineering',
        'hire_date': '2020-01-15',
        'manager': 'Jane Smith',
    }
)
```

### Option 3: Wrapper Class (For Special Processing)

```python
# In pipgraph_manager.py
async def create_episode_with_hash(
    name: str,
    content: str,
    reference_time: datetime,
    group_id: str,
) -> EpisodicNode:
    import hashlib
    
    episode = EpisodicNode(
        name=name,
        group_id=group_id,
        content=content,
        source_description="Obsidian note",
        valid_at=reference_time,
        entity_edges=[],
    )
    # Store hash tracking in attributes or separate table
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    return episode, content_hash
```

---

## Neo4j Storage Details

### Direct Properties (Stored as-is)
- All scalar fields: `uuid`, `name`, `group_id`, etc.
- Datetime fields: `created_at`, `valid_at`, `valid_at`, `invalid_at`
- Lists: `entity_edges`, `episodes` (stored as Neo4j arrays)
- Enums: `source` (stored as `.value` string)

### Attributes Dict Storage
- **Neo4j/Neptune**: Flattened into node properties
  ```cypher
  SET n = {...properties...}
  SET n.custom_field1 = $value1
  SET n.custom_field2 = $value2
  ```

- **Kuzu**: Stored as JSON string
  ```cypher
  SET n.attributes = $json_string
  ```

### Retrieval in Python

```python
def get_entity_node_from_record(record, provider):
    if provider == GraphProvider.KUZU:
        attributes = json.loads(record['attributes'])
    else:
        # For Neo4j: properties(e) returns all properties
        attributes = record['attributes']
        # Remove known fields to get only custom attrs
        for field in ['uuid', 'name', 'group_id', ...]:
            attributes.pop(field, None)
    
    return EntityNode(..., attributes=attributes)
```

---

## Duplicate Detection Implementation

### Scenario: Add Content Hash to Episodes

**Recommended Approach**: Store in attributes dict

```python
import hashlib

async def find_duplicate_episode(driver, content, group_id):
    """Check if episode with same content already exists"""
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    
    records, _, _ = await driver.execute_query(
        """
        MATCH (e:Episodic {group_id: $group_id})
        WHERE properties(e).content_hash = $hash
        RETURN e.uuid, e.name
        LIMIT 1
        """,
        hash=content_hash,
        group_id=group_id,
    )
    
    return records[0] if records else None


async def process_note_with_dedup(
    graphiti: Graphiti,
    name: str,
    content: str,
    reference_time: datetime,
):
    """Process note only if content is new"""
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    
    # Check for duplicates
    existing = await find_duplicate_episode(
        graphiti.driver,
        content,
        group_id='default'
    )
    
    if existing:
        logger.info(f"Duplicate found: {existing[0]['uuid']}")
        return {"status": "skipped", "reason": "duplicate"}
    
    # Process new episode
    episode = EpisodicNode(
        name=name,
        group_id='default',
        content=content,
        source_description='Obsidian note',
        valid_at=reference_time,
        entity_edges=[],
    )
    
    # Save hash for future lookups
    # (Store in database separately or in attributes)
    
    result = await graphiti.add_episode(...)
    return result
```

---

## Field Type Support by Provider

| Type | Neo4j | Kuzu | Neptune | FalkorDB |
|------|-------|------|---------|----------|
| String | native | native | native | native |
| Integer | native | native | native | native |
| Float | native | native | native | native |
| List[T] | native | native | comma-delimited | native |
| Dict | flattened | JSON | properties() | flattened |
| Datetime | native | native | native | native |
| Vector | db.create.setNodeVectorProperty | native | comma-delimited | vecf32() |

---

## Validation in graphiti_core

**Important**: graphiti_core does NOT validate field values!

- Field definitions use Pydantic for TYPE hints only
- No custom validators on Node/Edge classes
- Validation happens in the LLM extraction layer (outside graphiti_core)
- Focus is on data structure, not data quality

---

## Common Queries

### Find episode by UUID
```cypher
MATCH (e:Episodic {uuid: $uuid})
RETURN e
```

### Find episodes by group
```cypher
MATCH (e:Episodic {group_id: $group_id})
RETURN e
ORDER BY e.created_at DESC
```

### Find episode by content hash (custom field)
```cypher
MATCH (e:Episodic {group_id: $group_id})
WHERE properties(e).content_hash = $hash
RETURN e
LIMIT 1
```

### Find entity by name
```cypher
MATCH (n:Entity {uuid: $uuid})
RETURN n
```

### Find entities with custom attributes
```cypher
MATCH (n:Entity {group_id: $group_id})
WHERE properties(n).department = $dept
RETURN n
```

---

## See Also

- **Full analysis**: `docs/GRAPHITI_CORE_FIELD_ANALYSIS.md`
- **PipGraph manager**: `app/services/pipgraph_manager.py`
- **Node tests**: `tests/integration/test_nodes.py`
