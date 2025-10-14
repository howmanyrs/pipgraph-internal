# Changelog

All notable changes to the PipGraph backend will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Graphiti integration for LLM-based entity extraction
- WebSocket support for async note processing (`/api/v1/ws/notes/process`)
- Pydantic-based configuration management via `config/settings.py`
- Comprehensive test suite (unit, integration, e2e)
- OpenRouter integration for LLM access (main, small, embedding models)
- Neo4j connection and basic CRUD operations
- CLI utilities for manual testing (`scripts/`)
- **PipGraphManager class** (`app/services/pipgraph_manager.py`)
  - Wrapper over Graphiti for controlled step-by-step note processing
  - Exposes 7 processing stages with intervention points for user interaction
  - Copied original `add_episode` logic from graphiti_core with documented modification points
  - Enables gradual customization without modifying graphiti_core library
  - Based on architectural design from `docs/attend/pipgraph_manager_discussion.md`
- **CloudRuPatchedClient** (`app/services/cloudru_patched_client.py`)
  - Custom LLM client for Cloud.ru/Qwen models compatibility
  - Fixes JSON schema duplication issue in Qwen model responses
  - Modified prompt instruction: "return data only, not the schema"
  - Single-line patch maintains full compatibility with OpenAIGenericClient
- **Duplicate note detection task** added to TODO.md (High Priority)
  - Planned SHA-256 content hash verification for episode deduplication
  - Scenario 1: Skip processing if content unchanged (cost optimization)
  - Scenario 2: Handle modified note re-processing (requires design)
  - Includes `find_episode_by_name()` implementation plan
- Terminal frontend for manual testing and debugging
- Architecture documentation in `backend/docs/attend/` directory

### Changed
- Migrated from pip to `uv` for dependency management
- Layered architecture (API/Services/CRUD) fully implemented
- Test configuration with pytest markers (unit, integration, e2e, slow)
- **Note processor refactored to use PipGraphManager**
  - `process_and_store_note()` now uses `PipGraphManager.process_note()`
  - Enhanced logging with entity/edge counts from processing results
  - Maintains backward compatibility with existing API endpoints
- Documentation structure improved with architectural discussion documents

### Fixed
- Neo4j connection timeout issues
- OpenRouter API integration with proper error handling
- WebSocket endpoint closing issue for note processing connections

## [0.1.0] - 2025-09-26

### Added
- Initial FastAPI backend structure
- Basic WebSocket endpoint for note processing
- Pydantic models for notes and graph data
- Health check endpoint (`GET /`)
- Project documentation (README, CLAUDE.md)
- Development environment setup with `uv`

### Architecture Decisions
- Chose FastAPI for async WebSocket support
- Adopted layered architecture for testability
- Selected Neo4j as graph database
- WebSocket for long-running operations, REST for quick queries
