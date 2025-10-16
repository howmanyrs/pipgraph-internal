## Key Findings on Field Schema Standardization

### How Graphiti Fields Work

**Pattern**: All fields use **Pydantic v2** with `Field()` descriptors:
```python
class Node(BaseModel, ABC):
    uuid: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Field(description='name of the node')
    group_id: str = Field(description='partition of the graph')
    created_at: datetime = Field(default_factory=lambda: utc_now())
```

**Important characteristics**:
-  Type hints for basic validation
-  `Field()` with descriptions
-  Default factories for auto-generated values
- [ ] **No custom validators** (validation happens in LLM layer)
- [ ] **No schema enforcement** in database

### Current EpisodicNode Fields

```python
class EpisodicNode(Node):
    # Inherited from Node
    uuid: str
    name: str
    group_id: str
    labels: list[str]
    created_at: datetime

    # EpisodicNode specific
    source: EpisodeType              # 'message', 'json', 'text'
    source_description: str          # "Obsidian note"
    content: str                     # Raw content
    valid_at: datetime               # When document was created
    entity_edges: list[str]          # Referenced entity UUIDs
```

**Note**: EpisodicNode has **no `attributes` dict** (unlike EntityNode/EntityEdge) - it's a fixed schema.

---

## Three Options for Adding `content_hash`

### Option 1: Store in Metadata Table (Recommended )

**Pros**:
- No changes to graphiti_core
- Clean separation of concerns
- Easy to query and maintain
- Backwards compatible

**Implementation**:
```python
# In pipgraph_manager.py
import hashlib

async def find_duplicate_episode(
    driver: GraphDriver,
    content: str,
    group_id: str
) -> str | None:
    """Returns episode UUID if duplicate found"""
    content_hash = hashlib.sha256(content.encode()).hexdigest()

    records, _, _ = await driver.execute_query(
        """
        MATCH (m:EpisodeMetadata {group_id: $group_id, content_hash: $hash})
        RETURN m.episode_uuid AS uuid
        LIMIT 1
        """,
        hash=content_hash,
        group_id=group_id,
    )
    return records[0]['uuid'] if records else None

async def save_episode_hash(
    driver: GraphDriver,
    episode_uuid: str,
    content: str,
    group_id: str
):
    """Store hash for later duplicate detection"""
    content_hash = hashlib.sha256(content.encode()).hexdigest()

    await driver.execute_query(
        """
        MERGE (m:EpisodeMetadata {episode_uuid: $uuid})
        SET m.content_hash = $hash,
            m.group_id = $group_id,
            m.created_at = datetime()
        """,
        uuid=episode_uuid,
        hash=content_hash,
        group_id=group_id,
    )
```

### Option 2: Store in Episode Properties (Simple)

**Pros**:
- Single query for episode + hash
- No separate metadata node

**Cons**:
- Modifies graphiti_core usage pattern
- Hash stored but not part of EpisodicNode model

**Implementation**:
```python
async def save_episode_with_hash(episode: EpisodicNode, driver: GraphDriver):
    """Save episode with additional content_hash property"""
    content_hash = hashlib.sha256(episode.content.encode()).hexdigest()

    # First save the episode normally
    await episode.save(driver)

    # Then add the hash property
    await driver.execute_query(
        """
        MATCH (e:Episodic {uuid: $uuid})
        SET e.content_hash = $hash
        """,
        uuid=episode.uuid,
        hash=content_hash,
    )

async def find_episode_by_hash(driver, content, group_id):
    content_hash = hashlib.sha256(content.encode()).hexdigest()

    records, _, _ = await driver.execute_query(
        """
        MATCH (e:Episodic {group_id: $group_id})
        WHERE properties(e).content_hash = $hash
        RETURN e
        LIMIT 1
        """,
        hash=content_hash,
        group_id=group_id,
    )
    return get_episodic_node_from_record(records[0]) if records else None
```

### Option 3: Fork/Extend EpisodicNode (Not Recommended L)

Would require maintaining a fork of graphiti_core - too complex for this use case.

---

## Recommendation for PipGraph

**Use Option 1 (Metadata Table)** because:

1. **Clean separation**: Hash tracking is application logic, not part of the graph model
2. **Queryable**: Fast lookups with indexed `group_id + content_hash`
3. **Flexible**: Easy to add more metadata later (processing status, retry count, etc.)
4. **Compatible**: Works with all graph providers (Neo4j, Kuzu, Neptune, FalkorDB)
5. **Maintainable**: No changes to graphiti_core integration

### Database Schema
```cypher
# Create constraint for fast lookups
CREATE CONSTRAINT episode_metadata_uuid IF NOT EXISTS
FOR (m:EpisodeMetadata)
REQUIRE m.episode_uuid IS UNIQUE;

CREATE INDEX episode_metadata_lookup IF NOT EXISTS
FOR (m:EpisodeMetadata)
ON (m.group_id, m.content_hash);
```

---

## Documentation Created

I've generated three detailed reference documents in [backend/docs/](backend/docs/):

1. **[GRAPHITI_QUICK_REFERENCE.md](backend/docs/GRAPHITI_QUICK_REFERENCE.md)** - Quick lookup for field types and patterns
2. **[GRAPHITI_CORE_FIELD_ANALYSIS.md](backend/docs/GRAPHITI_CORE_FIELD_ANALYSIS.md)** - Deep dive into field definitions
3. **[GRAPHITI_EXPLORATION_REPORT.md](backend/docs/GRAPHITI_EXPLORATION_REPORT.md)** - Executive summary and implementation roadmap

These contain code examples, Cypher queries, and detailed analysis of how graphiti_core handles fields across all supported databases.
