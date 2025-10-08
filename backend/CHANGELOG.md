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

### Changed
- Migrated from pip to `uv` for dependency management
- Layered architecture (API/Services/CRUD) fully implemented
- Test configuration with pytest markers (unit, integration, e2e, slow)

### Fixed
- Neo4j connection timeout issues
- OpenRouter API integration with proper error handling

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
