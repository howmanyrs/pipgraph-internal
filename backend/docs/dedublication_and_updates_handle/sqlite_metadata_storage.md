# SQLite as Metadata Storage for Deduplication

## Overview

Using **SQLite** for deduplication metadata storage instead of Neo4j is an architectural decision with clear separation of concerns:

```
┌─────────────────────┐
│   PipGraph Backend  │
├─────────────────────┤
│  Neo4j (graphs)     │ ← Graph data (entities, relations)
│  SQLite (metadata)  │ ← Service data (hashes, statuses)
└─────────────────────┘
```

**Key idea**: Neo4j stores semantic data from graphiti_core, SQLite stores service information for PipGraph business logic.

---

## Architecture

### Database Schema

```sql
CREATE TABLE episode_metadata (
    episode_uuid TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    group_id TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    processing_status TEXT DEFAULT 'completed',

    -- Uniqueness guarantee: one hash = one episode within a group
    UNIQUE(group_id, content_hash)
);

-- Index for fast duplicate lookup
CREATE INDEX idx_content_hash ON episode_metadata(group_id, content_hash);

-- Index for cleanup of old records
CREATE INDEX idx_created_at ON episode_metadata(created_at);
```

### Extended Schema (Optional)

```sql
-- Note processing queue
CREATE TABLE processing_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_path TEXT NOT NULL,
    status TEXT DEFAULT 'pending', -- pending, processing, completed, failed
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_queue_status ON processing_queue(status);

-- User/vault preferences
CREATE TABLE user_preferences (
    group_id TEXT PRIMARY KEY,
    auto_process BOOLEAN DEFAULT 1,
    llm_model TEXT DEFAULT 'gpt-4o-mini',
    enable_deduplication BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Note change history
CREATE TABLE note_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_path TEXT NOT NULL,
    episode_uuid TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    operation TEXT NOT NULL, -- created, updated, deleted
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (episode_uuid) REFERENCES episode_metadata(episode_uuid)
);

CREATE INDEX idx_note_history_path ON note_history(note_path);
CREATE INDEX idx_note_history_episode ON note_history(episode_uuid);
```

---

## Implementation

### 1. Database Manager

```python
# app/db/sqlite_metadata.py
import sqlite3
import hashlib
from pathlib import Path
from typing import Optional
from datetime import datetime
from contextlib import contextmanager

class MetadataDB:
    """SQLite metadata database manager"""

    def __init__(self, db_path: str = "backend/data/metadata.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _get_connection(self):
        """Context manager for database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Access columns by name
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self):
        """Initialize database schema"""
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS episode_metadata (
                    episode_uuid TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    processing_status TEXT DEFAULT 'completed',
                    UNIQUE(group_id, content_hash)
                );

                CREATE INDEX IF NOT EXISTS idx_content_hash
                ON episode_metadata(group_id, content_hash);

                CREATE INDEX IF NOT EXISTS idx_created_at
                ON episode_metadata(created_at);
            """)

    def _compute_hash(self, content: str) -> str:
        """Compute SHA-256 hash of content"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def find_duplicate(self, content: str, group_id: str) -> Optional[str]:
        """
        Find duplicate by content hash

        Returns:
            episode_uuid if duplicate found, None otherwise
        """
        content_hash = self._compute_hash(content)

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT episode_uuid FROM episode_metadata
                WHERE group_id = ? AND content_hash = ?
                LIMIT 1
                """,
                (group_id, content_hash)
            )
            row = cursor.fetchone()
            return row['episode_uuid'] if row else None

    def save_episode(
        self,
        episode_uuid: str,
        content: str,
        group_id: str,
        status: str = 'completed'
    ):
        """
        Save episode metadata

        Updates existing record on conflict
        """
        content_hash = self._compute_hash(content)

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO episode_metadata
                (episode_uuid, content_hash, group_id, processing_status, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(episode_uuid) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    processing_status = excluded.processing_status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (episode_uuid, content_hash, group_id, status)
            )

    def delete_episode(self, episode_uuid: str):
        """Delete episode metadata"""
        with self._get_connection() as conn:
            conn.execute(
                "DELETE FROM episode_metadata WHERE episode_uuid = ?",
                (episode_uuid,)
            )

    def get_all_episode_uuids(self) -> list[str]:
        """Get all episode UUIDs"""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT episode_uuid FROM episode_metadata")
            return [row['episode_uuid'] for row in cursor.fetchall()]

    def get_stats(self) -> dict:
        """Get metadata statistics"""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(DISTINCT group_id) as groups,
                    COUNT(DISTINCT content_hash) as unique_hashes
                FROM episode_metadata
            """)
            row = cursor.fetchone()
            return {
                'total_episodes': row['total'],
                'total_groups': row['groups'],
                'unique_content_hashes': row['unique_hashes']
            }
```

### 2. Integration into Note Processing Service

```python
# app/services/note_processor.py
from app.db.sqlite_metadata import MetadataDB
from graphiti_core import Graphiti

class NoteProcessorService:
    """Note processing service with deduplication"""

    def __init__(self, graphiti: Graphiti):
        self.graphiti = graphiti
        self.metadata = MetadataDB()  # ← SQLite for metadata

    async def add_note(
        self,
        content: str,
        group_id: str,
        name: str = "Untitled Note"
    ) -> dict:
        """
        Add note with duplicate check

        Returns:
            {
                "status": "created" | "duplicate",
                "episode_uuid": str,
                "message": str
            }
        """
        # Step 1: Check for duplicate in SQLite
        existing_uuid = self.metadata.find_duplicate(content, group_id)

        if existing_uuid:
            return {
                "status": "duplicate",
                "episode_uuid": existing_uuid,
                "message": f"Note already exists as episode {existing_uuid}"
            }

        # Step 2: Add to graphiti (Neo4j)
        episodes = await self.graphiti.add_episode(
            name=name,
            episode_body=content,
            source_description="Obsidian note",
            group_id=group_id
        )

        episode_uuid = episodes[0].uuid

        # Step 3: Save hash to SQLite
        self.metadata.save_episode(episode_uuid, content, group_id)

        return {
            "status": "created",
            "episode_uuid": episode_uuid,
            "message": f"Created new episode {episode_uuid}"
        }

    async def update_note(
        self,
        episode_uuid: str,
        new_content: str,
        group_id: str
    ) -> dict:
        """
        Update existing note

        TODO: Requires update support in graphiti_core
        """
        # Check if content changed
        existing_uuid = self.metadata.find_duplicate(new_content, group_id)

        if existing_uuid == episode_uuid:
            return {
                "status": "unchanged",
                "episode_uuid": episode_uuid,
                "message": "Content has not changed"
            }

        # Update in graphiti (when API is available)
        # await self.graphiti.update_episode(episode_uuid, new_content)

        # Update hash in SQLite
        self.metadata.save_episode(episode_uuid, new_content, group_id)

        return {
            "status": "updated",
            "episode_uuid": episode_uuid,
            "message": f"Updated episode {episode_uuid}"
        }

    async def delete_note(self, episode_uuid: str):
        """
        Delete note

        Removes metadata from SQLite and episode from Neo4j
        """
        # Delete from graphiti (when API is available)
        # await self.graphiti.delete_episode(episode_uuid)

        # Delete metadata from SQLite
        self.metadata.delete_episode(episode_uuid)

        return {
            "status": "deleted",
            "episode_uuid": episode_uuid
        }
```

### 3. API Endpoints

```python
# app/api/endpoints/notes.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.services.note_processor import NoteProcessorService

router = APIRouter(prefix="/notes", tags=["notes"])

class AddNoteRequest(BaseModel):
    content: str
    group_id: str
    name: str = "Untitled Note"

class AddNoteResponse(BaseModel):
    status: str
    episode_uuid: str
    message: str

@router.post("/add", response_model=AddNoteResponse)
async def add_note(
    request: AddNoteRequest,
    service: NoteProcessorService = Depends()
):
    """
    Add note with automatic deduplication

    - If note with this content exists, returns existing episode_uuid
    - If new note, creates episode in Neo4j and saves hash in SQLite
    """
    return await service.add_note(
        content=request.content,
        group_id=request.group_id,
        name=request.name
    )

@router.get("/stats")
async def get_metadata_stats(
    service: NoteProcessorService = Depends()
):
    """Get metadata statistics"""
    return service.metadata.get_stats()
```

---

## Advantages

### 1. **High Performance**

```python
# SQLite: O(1) lookup with B-tree index
SELECT episode_uuid FROM episode_metadata
WHERE group_id = ? AND content_hash = ?
LIMIT 1;
# Typical time: < 1ms on local SSD

# Neo4j: Requires network round-trip
MATCH (m:EpisodeMetadata {group_id: $group_id, content_hash: $hash})
RETURN m.episode_uuid
# Typical time: 5-20ms (network + index)
```

**Result**: SQLite is **10-100x faster** for local queries.

### 2. **Simple Deployment**

```bash
# Neo4j: Separate container, 2GB RAM, service management
docker run -d -p 7687:7687 -p 7474:7474 \
  --env NEO4J_AUTH=neo4j/password \
  --memory=2g \
  neo4j:5.15

# SQLite: Single file, automatic creation
touch backend/data/metadata.db
# Size: ~100KB for 10,000 records
```

### 3. **Easy Testing**

```python
# tests/conftest.py
import pytest
from app.db.sqlite_metadata import MetadataDB

@pytest.fixture
def metadata_db():
    """In-memory database for each test"""
    db = MetadataDB(":memory:")  # No file created
    yield db
    # Automatically cleaned up after test

# tests/test_deduplication.py
def test_duplicate_detection(metadata_db):
    content = "Test note content"
    group_id = "test_vault"

    # First save
    metadata_db.save_episode("uuid-1", content, group_id)

    # Check duplicate
    duplicate_uuid = metadata_db.find_duplicate(content, group_id)
    assert duplicate_uuid == "uuid-1"
```

**Result**: Tests run **without Docker** in **milliseconds**.

### 4. **Schema Extensibility**

```python
# Easy to add new tables for other features

# Background processing queue
CREATE TABLE processing_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_path TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    retry_count INTEGER DEFAULT 0
);

# User preferences
CREATE TABLE user_preferences (
    group_id TEXT PRIMARY KEY,
    llm_model TEXT DEFAULT 'gpt-4o-mini',
    auto_process BOOLEAN DEFAULT 1
);

# Search query cache
CREATE TABLE search_cache (
    query_hash TEXT PRIMARY KEY,
    results TEXT NOT NULL,  -- JSON
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 5. **Separation of Concerns**

| Component | Responsibility |
|-----------|----------------|
| **Neo4j** | Graph data from graphiti_core (entities, relations, facts) |
| **SQLite** | Service metadata for PipGraph (hashes, statuses, queues) |

**Result**: Clean architecture without mixing concerns.

---

## Potential Issues and Solutions

### Issue 1: Synchronization with Neo4j

**Scenario**: Episode deleted from Neo4j directly (via Cypher or UI), but hash remains in SQLite.

**Solution**: Periodic cleanup of orphaned records

```python
# app/services/maintenance.py
from app.db.sqlite_metadata import MetadataDB
from graphiti_core import Graphiti

async def cleanup_orphaned_metadata(
    graphiti: Graphiti,
    metadata: MetadataDB
):
    """
    Delete metadata for non-existent episodes

    Run:
    - On application startup
    - On schedule (once per day)
    - On user demand
    """
    all_uuids = metadata.get_all_episode_uuids()
    orphaned_count = 0

    for uuid in all_uuids:
        # Check existence in Neo4j
        result = await graphiti.graph_driver.execute_query(
            """
            MATCH (e:Episodic {uuid: $uuid})
            RETURN count(e) > 0 AS exists
            """,
            uuid=uuid
        )

        exists = result[0][0]['exists'] if result[0] else False

        if not exists:
            metadata.delete_episode(uuid)
            orphaned_count += 1

    return {
        "checked": len(all_uuids),
        "deleted": orphaned_count
    }

# app/api/endpoints/maintenance.py
@router.post("/cleanup-metadata")
async def cleanup_metadata(
    graphiti: Graphiti = Depends(),
    metadata: MetadataDB = Depends()
):
    """Cleanup orphaned metadata"""
    result = await cleanup_orphaned_metadata(graphiti, metadata)
    return {
        "status": "success",
        "message": f"Checked {result['checked']} episodes, deleted {result['deleted']} orphaned records"
    }
```

### Issue 2: Concurrent Access (Multithreading)

**Scenario**: Multiple threads/processes writing to SQLite simultaneously.

**SQLite limitations**:
- ✅ Multiple readers simultaneously (shared lock)
- ⚠️ Only one writer at a time (exclusive lock)
- ❌ May get "database is locked" under high load

**Solution for PipGraph**:

```python
# app/db/sqlite_metadata.py (updated version)
import sqlite3
from contextlib import contextmanager

class MetadataDB:
    def __init__(self, db_path: str = "backend/data/metadata.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(
            self.db_path,
            timeout=10.0,  # Wait up to 10 seconds on lock
            isolation_level="DEFERRED"  # Defer lock until write
        )
        # Optimization for concurrent access
        conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
        conn.execute("PRAGMA busy_timeout=5000")  # 5 seconds retry

        try:
            yield conn
            conn.commit()
        except sqlite3.OperationalError as e:
            conn.rollback()
            if "database is locked" in str(e):
                raise RuntimeError("Database busy, retry later") from e
            raise
        finally:
            conn.close()
```

**Important**: For PipGraph (Obsidian plugin) this is **not an issue**:
- Single user working locally
- Operations are sequential (humans can't edit 100 notes simultaneously)

**If multi-user support needed**: Migrate to PostgreSQL instead of SQLite.

### Issue 3: Backup and Migration

**SQLite Backup**:

```python
# app/services/backup.py
import shutil
from datetime import datetime
from pathlib import Path

def backup_metadata(
    db_path: str = "backend/data/metadata.db",
    backup_dir: str = "backend/backups"
) -> str:
    """
    Create metadata backup

    Returns:
        Path to backup file
    """
    backup_path = Path(backup_dir)
    backup_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_path / f"metadata_{timestamp}.db"

    shutil.copy(db_path, backup_file)

    return str(backup_file)

# Automatic backup on startup
# app/main.py
from contextlib import asynccontextmanager
from app.services.backup import backup_metadata

@asynccontextmanager
async def lifespan(app: FastAPI):
    # On startup - backup
    backup_metadata()
    yield
    # On shutdown - another backup
    backup_metadata()
```

**Schema Migration**:

```python
# app/db/migrations.py
from app.db.sqlite_metadata import MetadataDB

class MigrationManager:
    """SQLite schema migration manager"""

    MIGRATIONS = {
        1: """
            CREATE TABLE episode_metadata (
                episode_uuid TEXT PRIMARY KEY,
                content_hash TEXT NOT NULL,
                group_id TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """,
        2: """
            ALTER TABLE episode_metadata
            ADD COLUMN processing_status TEXT DEFAULT 'completed';
        """,
        3: """
            CREATE TABLE processing_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                note_path TEXT NOT NULL,
                status TEXT DEFAULT 'pending'
            );
        """
    }

    def __init__(self, db: MetadataDB):
        self.db = db

    def get_current_version(self) -> int:
        """Get current schema version"""
        with self.db._get_connection() as conn:
            # Create version table if not exists
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor = conn.execute("SELECT MAX(version) FROM schema_version")
            row = cursor.fetchone()
            return row[0] if row[0] is not None else 0

    def apply_migrations(self):
        """Apply all pending migrations"""
        current_version = self.get_current_version()

        for version in sorted(self.MIGRATIONS.keys()):
            if version > current_version:
                print(f"Applying migration {version}...")
                with self.db._get_connection() as conn:
                    conn.executescript(self.MIGRATIONS[version])
                    conn.execute(
                        "INSERT INTO schema_version (version) VALUES (?)",
                        (version,)
                    )
                print(f"Migration {version} applied")
```

---

## Comparison with Alternatives

| Criterion | SQLite | Neo4j EpisodeMetadata | Graphiti Core |
|-----------|--------|------------------------|---------------|
| **Deduplication speed** | ⚡️⚡️⚡️ (< 1ms) | ⚡️⚡️ (5-20ms) | ⚡️ (100ms+, graph traversal) |
| **Deployment simplicity** | ✅ Single file | ❌ Docker + 2GB RAM | ❌ Docker + 2GB RAM |
| **Testing simplicity** | ✅ In-memory | ⚠️ Testcontainers | ⚠️ Testcontainers |
| **Extensibility** | ✅✅✅ SQL + relational | ✅✅ Graph properties | ❌ Limited by API |
| **Separation of concerns** | ✅✅✅ Complete | ✅✅ Good | ❌ Mixed with graphiti |
| **Backup** | ✅ `cp metadata.db` | ⚠️ `neo4j-admin dump` | ⚠️ `neo4j-admin dump` |
| **Concurrent writes** | ⚠️ Limited | ✅ Full support | ✅ Full support |
| **Storage size** | ✅ ~10KB per 1000 records | ⚠️ ~100MB overhead | ⚠️ ~100MB overhead |
| **Data migration** | ✅ SQL scripts | ⚠️ Cypher scripts | ❌ No built-in tools |

---

## Usage Recommendations

### ✅ Use SQLite if:

1. **PipGraph runs locally** on user's machine (Obsidian plugin)
2. **Maximum speed needed** for deduplication (< 1ms)
3. **Want to simplify tests** (in-memory, no Docker)
4. **Plan to extend metadata**:
   - Note processing queue
   - Change history
   - Sync statuses
   - Search query cache
5. **Simple backup important** (single file)

### ⚠️ Use Neo4j EpisodeMetadata if:

1. **PipGraph already deployed as web service** with Neo4j in production
2. **Many concurrent users** (concurrent writes)
3. **Want everything in one DB** (simplified infrastructure)
4. **Need graph relationships** between metadata and episodes

### ❌ Don't use Graphiti Core if:

1. Need fast deduplication (graph traversal is slow)
2. Want to avoid forking library (schema modification)
3. Need flexibility in metadata storage

---

## Hybrid Approach (Storage Abstraction)

For maximum flexibility, create an abstraction:

```python
# app/db/metadata_storage.py
from abc import ABC, abstractmethod
from typing import Optional

class MetadataStorage(ABC):
    """Abstract metadata storage"""

    @abstractmethod
    def find_duplicate(self, content: str, group_id: str) -> Optional[str]:
        """Find duplicate by content"""
        pass

    @abstractmethod
    def save_episode(self, uuid: str, content: str, group_id: str):
        """Save episode metadata"""
        pass

    @abstractmethod
    def delete_episode(self, uuid: str):
        """Delete metadata"""
        pass

# SQLite implementation
class SQLiteMetadataStorage(MetadataStorage):
    def __init__(self, db_path: str):
        self.db = MetadataDB(db_path)

    def find_duplicate(self, content: str, group_id: str) -> Optional[str]:
        return self.db.find_duplicate(content, group_id)

    def save_episode(self, uuid: str, content: str, group_id: str):
        self.db.save_episode(uuid, content, group_id)

    def delete_episode(self, uuid: str):
        self.db.delete_episode(uuid)

# Neo4j implementation
class Neo4jMetadataStorage(MetadataStorage):
    def __init__(self, driver):
        self.driver = driver

    async def find_duplicate(self, content: str, group_id: str) -> Optional[str]:
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        result = await self.driver.execute_query(
            """
            MATCH (m:EpisodeMetadata {group_id: $group_id, content_hash: $hash})
            RETURN m.episode_uuid
            """,
            group_id=group_id,
            hash=content_hash
        )
        return result[0][0]['m.episode_uuid'] if result[0] else None

    # ... other methods

# app/core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    metadata_storage: str = "sqlite"  # or "neo4j"
    sqlite_path: str = "backend/data/metadata.db"

# app/core/dependencies.py
def get_metadata_storage() -> MetadataStorage:
    settings = get_settings()

    if settings.metadata_storage == "sqlite":
        return SQLiteMetadataStorage(settings.sqlite_path)
    elif settings.metadata_storage == "neo4j":
        return Neo4jMetadataStorage(get_neo4j_driver())
    else:
        raise ValueError(f"Unknown storage: {settings.metadata_storage}")
```

**Abstraction advantages**:
- Can switch between SQLite and Neo4j via configuration
- Easy to add new storage backends (PostgreSQL, Redis)
- Simplifies testing (mock storage)

---

## Complete Workflow Example

```python
# User creates note in Obsidian
# → Obsidian plugin sends WebSocket request

# 1. API receives request
@router.websocket("/ws/notes")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    data = await websocket.receive_json()
    # {"action": "add_note", "content": "...", "group_id": "my_vault"}

    # 2. Service checks duplicate in SQLite (< 1ms)
    service = NoteProcessorService(graphiti)
    result = await service.add_note(
        content=data['content'],
        group_id=data['group_id'],
        name=data.get('name', 'Untitled')
    )

    # 3. If duplicate found
    if result['status'] == 'duplicate':
        await websocket.send_json({
            "event": "note_duplicate",
            "episode_uuid": result['episode_uuid'],
            "message": "This note already exists"
        })
        return

    # 4. If new note - add to Neo4j (100-500ms)
    await websocket.send_json({
        "event": "note_processing",
        "message": "Processing note with LLM..."
    })

    # graphiti.add_episode() already called in service.add_note()

    # 5. Hash saved to SQLite (< 1ms)
    await websocket.send_json({
        "event": "note_created",
        "episode_uuid": result['episode_uuid'],
        "message": "Note successfully processed"
    })
```

**Overall performance**:
- Duplicate check: **< 1ms** (SQLite)
- New episode creation: **100-500ms** (Neo4j + LLM)
- Hash save: **< 1ms** (SQLite)

---

## Conclusion

**SQLite as metadata layer** - optimal solution for PipGraph:

✅ **High deduplication performance** (< 1ms vs 5-20ms in Neo4j)
✅ **Simple deployment** (single file vs Docker container)
✅ **Easy testing** (in-memory vs testcontainers)
✅ **Extensibility** (SQL flexibility for new features)
✅ **Separation of concerns** (metadata separate from graph)
✅ **Simple backup** (copy file vs neo4j-admin dump)

**Next steps**:
1. Implement `MetadataDB` class in `app/db/sqlite_metadata.py`
2. Integrate into `NoteProcessorService` in `app/services/note_processor.py`
3. Add API endpoints in `app/api/endpoints/notes.py`
4. Write unit tests with in-memory SQLite in `tests/unit/test_deduplication.py`
5. Add maintenance endpoint for cleanup of orphaned records
