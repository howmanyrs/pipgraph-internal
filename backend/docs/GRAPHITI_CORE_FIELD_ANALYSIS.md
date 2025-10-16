# Graphiti Core Field Definitions Analysis

## Executive Summary

This document provides a comprehensive analysis of how graphiti_core defines, stores, and manages fields across Node and Edge types. It focuses on understanding Pydantic field patterns, custom/metadata field mechanisms, and practical implementation patterns for adding hash/checksum fields for duplicate detection.

---

## 1. Field Definition Patterns

### 1.1 Base Node Class Structure

**Location**: `graphiti_core/nodes.py` (lines 91-97)

```python
class Node(BaseModel, ABC):
    uuid: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Field(description='name of the node')
    group_id: str = Field(description='partition of the graph')
    labels: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: utc_now())
```

**Key Characteristics**:
- Uses **Pydantic v2** with `BaseModel` inheritance
- All fields use `Field()` descriptor for metadata
- Descriptions are included for all fields
- Factory functions used for defaults (UUID, timestamp)
- No explicit validators (v2 pattern)

---

## 2. Node Type Field Specifications

### 2.1 EpisodicNode (Episode/Document Node)

**Location**: `graphiti_core/nodes.py` (lines 353-363)

```python
class EpisodicNode(Node):
    source: EpisodeType = Field(description='source type')
    source_description: str = Field(description='description of the data source')
    content: str = Field(description='raw episode data')
    valid_at: datetime = Field(description='datetime of when the original document was created')
    entity_edges: list[str] = Field(
        description='list of entity edges referenced in this episode',
        default_factory=list,
    )
```

**Field Mapping to Neo4j Properties**:
- `uuid` → Neo4j property (indexed)
- `name` → Neo4j property
- `group_id` → Neo4j property (partition key)
- `created_at` → Neo4j property (datetime)
- `source` → Neo4j property (stored as `.value` string)
- `source_description` → Neo4j property
- `content` → Neo4j property (full text)
- `valid_at` → Neo4j property (datetime)
- `entity_edges` → Neo4j property (list stored as array)

**Database Query Pattern** (from `node_db_queries.py` lines 26-57):
```cypher
MERGE (n:Episodic {uuid: $uuid})
SET n = {
    uuid: $uuid,
    name: $name,
    group_id: $group_id,
    source_description: $source_description,
    source: $source,
    content: $content,
    entity_edges: $entity_edges,
    created_at: $created_at,
    valid_at: $valid_at
}
RETURN n.uuid AS uuid
```

### 2.2 EntityNode (Entity/Knowledge Node)

**Location**: `graphiti_core/nodes.py` (lines 496-501)

```python
class EntityNode(Node):
    name_embedding: list[float] | None = Field(
        default=None,
        description='embedding of the name'
    )
    summary: str = Field(
        description='regional summary of surrounding edges',
        default_factory=str
    )
    attributes: dict[str, Any] = Field(
        default={},
        description='Additional attributes of the node. Dependent on node labels'
    )
```

**Key Insight: Attributes Field**
- `attributes` is a **free-form dictionary** for custom/dynamic fields
- No schema validation on attributes values
- Used for **label-dependent metadata** (pattern matching on labels)
- Stored as individual Neo4j properties (for Neo4j/Neptune) or JSON (for Kuzu)

**How Attributes Are Stored**:

For **Neo4j** (lines 568 in nodes.py):
```python
entity_data.update(self.attributes or {})  # Merge into flat property map
```

For **Kuzu** (line 561):
```python
entity_data['attributes'] = json.dumps(self.attributes)  # Store as JSON string
```

**Retrieval Pattern** (lines 827-843 in nodes.py):
```python
def get_entity_node_from_record(record: Any, provider: GraphProvider) -> EntityNode:
    if provider == GraphProvider.KUZU:
        attributes = json.loads(record['attributes']) if record['attributes'] else {}
    else:
        # For Neo4j: extract all properties EXCEPT known fields
        attributes = record['attributes']  # properties(e) returns all
        # Remove known fields from attributes dict
        attributes.pop('uuid', None)
        attributes.pop('name', None)
        attributes.pop('group_id', None)
        attributes.pop('name_embedding', None)
        attributes.pop('summary', None)
        attributes.pop('created_at', None)
        attributes.pop('labels', None)
```

### 2.3 EntityEdge (Relationship)

**Location**: `graphiti_core/edges.py` (lines 228-247)

```python
class EntityEdge(Edge):
    name: str = Field(description='name of the edge, relation name')
    fact: str = Field(description='fact representing the edge and nodes')
    fact_embedding: list[float] | None = Field(default=None, description='embedding')
    episodes: list[str] = Field(default=[], description='list of episode ids')
    expired_at: datetime | None = Field(default=None, description='when invalidated')
    valid_at: datetime | None = Field(default=None, description='when became true')
    invalid_at: datetime | None = Field(default=None, description='when stopped being true')
    attributes: dict[str, Any] = Field(
        default={},
        description='Additional attributes. Dependent on edge name'
    )
```

**Same Pattern**: Free-form `attributes` dict for label/relationship-dependent custom fields.

### 2.4 CommunityNode

**Location**: `graphiti_core/nodes.py` (lines 664-666)

```python
class CommunityNode(Node):
    name_embedding: list[float] | None = Field(default=None, ...)
    summary: str = Field(description='region summary of member nodes', default_factory=str)
```

**Note**: Communities do NOT have custom `attributes` field (simpler structure).

---

## 3. Neo4j Storage and Query Patterns

### 3.1 Property Name Constraints

Neo4j **does not** have schema-level field validation. Properties are created dynamically:
- Single-label queries: `properties(n)` returns all properties as a dict
- Multi-label support via node labels: `labels(n)` returns labels array
- Constraints created per database, not per node class

### 3.2 Special Properties and Indices

**Standard Node Indices** (from driver initialization):
- `Entity` nodes indexed on `uuid` and `group_id`
- `Episodic` nodes indexed on `uuid` and `group_id`
- `Community` nodes indexed on `uuid`

**Vector Properties** (Neo4j 5.x+):
```cypher
WITH n CALL db.create.setNodeVectorProperty(n, "name_embedding", $embedding)
```

### 3.3 Multi-Provider Support

The code supports **4 different graph databases**:
1. **Neo4j** - Native property storage
2. **Kuzu** - JSON string storage for complex types
3. **Neptune** - Comma-delimited string storage for arrays/embeddings
4. **FalkorDB** - Property storage with vector functions

This explains the `attributes` pattern: **it's provider-agnostic**.

---

## 4. Extension Points for Custom Fields

### 4.1 Pattern: Entity Type Definitions

**Location**: `graphiti_core/graphiti.py` lines 416-417

```python
entity_types: dict[str, type[BaseModel]] | None = None
```

**Usage Pattern**:
```python
class PersonEntity(BaseModel):
    name: str
    role: str  # Custom field

entity_types = {'Person': PersonEntity}
await graphiti.add_episode(..., entity_types=entity_types)
```

This allows **schema-validated custom attributes** per entity type!

### 4.2 Pattern: Edge Type Definitions

**Location**: `graphiti_core/graphiti.py` lines 389-390

```python
edge_types: dict[str, type[BaseModel]] | None = None
```

Same principle for edges.

### 4.3 Pattern: Attributes Dictionary

For **unvalidated custom fields**, use the `attributes` dict directly:

```python
node = EntityNode(
    name='John Doe',
    group_id='default',
    labels=['Person'],
    attributes={
        'department': 'Engineering',
        'hire_date': '2020-01-15',
        'custom_field': 'value'
    }
)
```

---

## 5. Hash/Checksum Field Implementation Strategy

### 5.1 For EpisodicNode (Duplicate Detection)

**Best Approach**: Add as standard field in Node class extension

```python
class EpisodicNode(Node):
    # ... existing fields ...
    content_hash: str = Field(
        default='',
        description='SHA-256 hash of episode content for duplicate detection'
    )
```

**Storage**:
- Stored as direct Neo4j property
- Can be indexed for fast lookup
- Retrieved with standard node query

**Cypher Pattern**:
```cypher
MATCH (e:Episodic {content_hash: $hash, group_id: $group_id})
RETURN e
```

### 5.2 For EntityNode (Optional Integrity Check)

**If needed for custom implementations**, use `attributes`:

```python
node = EntityNode(
    name='John Doe',
    group_id='default',
    attributes={
        'integrity_hash': 'sha256_of_attributes',
        'source_checksum': 'checksum_of_source'
    }
)
```

### 5.3 Database Migration Pattern

Since graphiti_core uses MERGE queries, new fields are backwards-compatible:

```cypher
MERGE (n:Episodic {uuid: $uuid})
SET n = {...existing fields...}
SET n.content_hash = $content_hash  # New field added safely
```

---

## 6. Validation and Schema Enforcement

### 6.1 Pydantic v2 Features Used

- **Field descriptors** with `description` metadata
- **Type hints** for validation (str, int, list, dict, datetime)
- **Default factories** for mutable defaults
- **No custom validators** in base classes (validation deferred to LLM layer)

### 6.2 No Built-in Validation

- graphiti_core **does not validate field values**
- Validation happens in LLM extraction layer (outside graphiti_core)
- Focus is on **data structure**, not **data quality**

---

## 7. Practical Implementation Examples

### 7.1 Adding Content Hash to EpisodicNode

**Modification Required**:

1. **Option A: Minimal (Recommended for PipGraph)**
   
   Create wrapper in `pipgraph_manager.py`:
   ```python
   import hashlib
   
   async def create_episode_with_hash(
       name: str,
       content: str,
       source_description: str,
       reference_time: datetime,
       group_id: str,
   ) -> EpisodicNode:
       content_hash = hashlib.sha256(content.encode()).hexdigest()
       episode = EpisodicNode(
           name=name,
           group_id=group_id,
           content=content,
           source_description=source_description,
           valid_at=reference_time,
           created_at=utc_now(),
           entity_edges=[],
       )
       # Store hash in attributes or as separate tracking
       return episode
   ```

2. **Option B: Extend EpisodicNode (Invasive)**
   
   Would require forking graphiti_core (not recommended).

### 7.2 Duplicate Detection Query

```cypher
MATCH (e:Episodic {group_id: $group_id})
WHERE e.content_hash = $new_hash
RETURN e LIMIT 1
```

### 7.3 Storing Hash in Attributes (Current Approach)

```python
episode = EpisodicNode(
    name=name,
    group_id=group_id,
    content=content,
    source_description=source_description,
    valid_at=reference_time,
    entity_edges=[],
)
# Add hash tracking separately in a service layer
episode_hash = {
    'episode_uuid': episode.uuid,
    'content_hash': hashlib.sha256(content.encode()).hexdigest(),
    'group_id': group_id,
}
```

---

## 8. Field Serialization and Deserialization

### 8.1 Save Flow

```
Pydantic Model → Type Conversion → Neo4j Query → Database
```

**Example** (from `nodes.py` lines 550-577):
```python
async def save(self, driver: GraphDriver):
    entity_data: dict[str, Any] = {
        'uuid': self.uuid,
        'name': self.name,
        'name_embedding': self.name_embedding,
        'group_id': self.group_id,
        'summary': self.summary,
        'created_at': self.created_at,
    }
    
    if driver.provider == GraphProvider.KUZU:
        entity_data['attributes'] = json.dumps(self.attributes)
    else:
        entity_data.update(self.attributes or {})  # Flatten attributes
    
    # Save to database
    await driver.execute_query(...)
```

### 8.2 Load Flow

```
Database Query → Type Reconstruction → Pydantic Model
```

**Example** (from `nodes.py` lines 827-856):
```python
def get_entity_node_from_record(record: Any, provider: GraphProvider) -> EntityNode:
    attributes = record['attributes']
    # Filter out known fields
    for field in ['uuid', 'name', 'group_id', ...]:
        attributes.pop(field, None)
    
    return EntityNode(
        uuid=record['uuid'],
        name=record['name'],
        attributes=attributes,
        # ... other fields ...
    )
```

---

## 9. Comparison: EpisodicNode vs EntityNode Fields

| Aspect | EpisodicNode | EntityNode | Purpose |
|--------|--------------|-----------|---------|
| Custom Fields | None (fixed schema) | `attributes: dict` | Metadata flexibility |
| Embeddings | No | `name_embedding: list[float]` | Vector search |
| Summary | No | `summary: str` | Node description |
| Content | `content: str` | No | Raw episode data |
| Episodes Ref | `entity_edges: list[str]` | No | Backwards reference |
| Extensibility | Low (fixed) | High (via attributes) | Design choice |

---

## 10. Recommendations for PipGraph Implementation

### 10.1 For Duplicate Detection (TODO Item)

**Current State**: No hash field implementation

**Recommended Approach**:

1. **Store hash outside the node model** (simplest):
   - Create separate `EpisodeMetadata` table/collection
   - Track: `episode_uuid`, `content_hash`, `created_at`
   - Query by group_id + hash

2. **Store hash in EpisodicNode.attributes**:
   - Add during episode creation in `pipgraph_manager.py`
   - Minimal changes to graphiti_core usage
   - Queryable via Cypher: `WHERE e.content_hash = $hash`

3. **Full node extension** (not recommended):
   - Fork graphiti_core or subclass
   - Requires database schema updates
   - Harder to maintain upstream compatibility

### 10.2 Implementation Checklist

- [ ] Add content hash calculation in `pipgraph_manager.process_note()`
- [ ] Store hash in episode.attributes or separate tracking
- [ ] Implement `find_episode_by_name_and_hash()` Cypher query
- [ ] Add hash comparison before `extract_nodes()`
- [ ] Handle two scenarios:
  - Scenario 1: Skip if hash matches
  - Scenario 2: Handle modified content (requires design)
- [ ] Test with duplicate notes (same content, different timestamps)

### 10.3 Storage Decision

**Recommended**: Use `attributes` dict approach
- Minimal code changes
- Works with all graph providers
- Queryable with Cypher
- Backwards compatible

```python
async def find_episode_by_content_hash(
    driver: GraphDriver,
    content_hash: str,
    group_id: str,
) -> EpisodicNode | None:
    records, _, _ = await driver.execute_query(
        """
        MATCH (e:Episodic {group_id: $group_id})
        WHERE e.content_hash = $hash OR properties(e).content_hash = $hash
        RETURN e.uuid, e.name, e.group_id, ...
        LIMIT 1
        """,
        hash=content_hash,
        group_id=group_id,
    )
```

---

## 11. Summary

### Key Findings:

1. **Pydantic v2 with Field descriptors** - No built-in validation
2. **Free-form `attributes` dict** - For custom/extensible fields
3. **Entity/Edge type definitions** - Schema-based custom fields via dict
4. **Multi-provider compatibility** - JSON serialization for complex types
5. **MERGE-based persistence** - Backwards compatible schema evolution
6. **No validators in nodes** - Validation deferred to LLM layer

### For Duplicate Detection:

- **Best approach**: Store hash in `attributes` or separate tracking
- **Query pattern**: Cypher WHERE clause on properties
- **Implementation**: 30 lines of code in `pipgraph_manager.py`
- **No database schema changes** needed (backwards compatible)

### Extension Points:

1. Custom entity types via `entity_types` dict
2. Custom edge types via `edge_types` dict
3. Free-form `attributes` on EntityNode/EntityEdge
4. Wrapper classes in PipGraphManager for specialized behavior

---

## Appendix: File References

- **Node definitions**: `graphiti_core/nodes.py` (lines 91-880)
- **Edge definitions**: `graphiti_core/edges.py` (lines 45-654)
- **Database queries**: `graphiti_core/models/nodes/node_db_queries.py`
- **Database edge queries**: `graphiti_core/models/edges/edge_db_queries.py`
- **PipGraph wrapper**: `app/services/pipgraph_manager.py`
- **Configuration**: `config/settings.py`
- **Test fixtures**: `tests/conftest.py`
