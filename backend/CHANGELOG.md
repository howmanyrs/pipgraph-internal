# Changelog

All notable changes to the PipGraph backend will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **[BREAKING]** Migrated all CRUD operations to `PipGraphManager`
  - Removed `EpisodicCRUD` class from `app/crud/episodic_crud.py`
  - Removed `PARAContainerCRUD` class from `app/crud/para_crud.py`
  - All database operations now use `PipGraphManager` from `app.services.graphiti`
  - Old sync CRUD methods replaced with async manager methods

### Added

- **PipGraphManager** new methods for episodic operations:
  - `get_episodic_by_name(name)` - Retrieve episodic by file path
  - `list_episodics(limit)` - List all episodic nodes
  - `update_episodic_timestamp(uuid, valid_at)` - Update episodic timestamp
  - `delete_episodic(uuid)` - Delete episodic and relationships

- **PipGraphManager** new methods for entity operations:
  - `get_para_entity_by_uuid(uuid)` - Retrieve entity by UUID
  - `get_para_entity_by_name(name, para_type)` - Retrieve entity by name
  - `ensure_inbox_exists()` - Ensure Inbox area exists (creates if missing)

### Removed

- **[BREAKING]** Deleted `backend/app/crud/episodic_crud.py`
- **[BREAKING]** Deleted `backend/app/crud/para_crud.py`
- Removed old CRUD imports from `app/crud/__init__.py`

### Migration Guide

**Before:**
```python
from app.crud.episodic_crud import EpisodicCRUD
crud = EpisodicCRUD()
episodic = crud.get_episodic("path/to/note.md")  # Returns dict
```

**After:**
```python
from app.services.graphiti import get_graphiti, PipGraphManager

graphiti = await get_graphiti()
manager = PipGraphManager(graphiti)
episodic = await manager.get_episodic_by_name("path/to/note.md")  # Returns EpisodicNode
```

**Key Differences:**
- All methods are now **async** (use `await`)
- Methods return **Graphiti objects** (EpisodicNode, EntityNode) instead of dicts
- Uses **UUID** as primary identifier instead of string IDs
- New nodes use Graphiti schema (`:Entity:Project` with embeddings) instead of simple labels (`:Project`)

**Decision Processing Functions:**
- `process_user_decision()` now requires `manager: PipGraphManager` parameter
- `_handle_confirm()`, `_handle_dismiss()`, `_handle_create_custom()` refactored to use manager

**API Endpoints:**
- `/dev/episodic` - Updated to use PipGraphManager
- `/dev/episodic/list` - Updated to use PipGraphManager
