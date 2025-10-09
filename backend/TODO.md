# TODO

Backend development tasks and roadmap for PipGraph.

## In Progress

- [ ] Complete Graphiti integration for entity extraction
- [ ] Implement full note processing pipeline with LLM

## High Priority

- [ ] Natural language search endpoint (`POST /api/v1/search`)
  - Convert natural language to Cypher queries
  - Return formatted search results
- [ ] Entity suggestions endpoint (`GET /api/v1/suggestions/{note_id}`)
  - Return entities with "pending review" status
  - Include confidence scores
- [ ] Add caching layer for LLM responses
  - Cache expensive LLM calls
  - Implement TTL and cache invalidation
- [ ] Error handling and logging improvements
  - Structured logging with context
  - Better error messages for clients

## Medium Priority

- [ ] Rate limiting for API endpoints
  - Per-user rate limits
  - Prevent abuse of LLM resources
- [ ] Batch note processing
  - Process multiple notes in one request
  - Optimize for bulk imports
- [ ] Background task queue (Celery/Redis)
  - Move long-running tasks out of WebSocket
  - Better scalability
- [ ] API authentication and authorization
  - API keys or JWT tokens
  - Role-based access control

## Low Priority / Future

- [ ] GraphQL API support
  - Alternative to REST for complex queries
- [ ] Multi-tenant support
  - Separate databases per tenant
  - Tenant isolation
- [ ] Metrics and monitoring
  - Prometheus metrics endpoint
  - Application performance monitoring
- [ ] Docker deployment
  - Multi-stage Docker builds
  - Docker Compose for dev environment
- [ ] CI/CD pipeline
  - Automated testing on PR
  - Deployment automation

## Research & Exploration

- [ ] Investigate Graphiti capabilities with LLM-only (no embedding model)
  - Test entity extraction quality without embeddings
  - Evaluate performance and accuracy tradeoffs
  - Document limitations and workarounds
- [ ] Evaluate alternative graph databases (MemGraph, ArangoDB)
- [ ] Investigate streaming LLM responses via WebSocket
- [ ] Explore vector similarity search for related notes
- [ ] Research graph visualization libraries for frontend

## Technical Debt

- [ ] Add more comprehensive integration tests
- [ ] Improve error handling in WebSocket connections
- [ ] Document all API endpoints with OpenAPI/Swagger
- [ ] Add type hints to all functions
- [ ] Set up pre-commit hooks (black, isort, mypy)
- [ ] Implement configuration for testing different OpenAI-generic provider sets
  - Support multiple provider profiles (OpenRouter, Cloud.ru, etc.)
  - Allow switching between providers via environment or test fixtures
  - Enable parallel testing with different LLM configurations
  - Support mixed provider configurations (e.g., LLM from OpenRouter + embeddings from Cloud.ru)
  - Allow independent provider selection for LLM, embeddings, and reranker

## Completed ✓

- [x] Basic FastAPI structure with WebSocket support
- [x] Layered architecture (API/Services/CRUD)
- [x] Pydantic models for data validation
- [x] Neo4j connection and basic operations
- [x] OpenRouter LLM integration
- [x] Test suite setup (pytest with markers)
- [x] Configuration management with pydantic-settings
- [x] CLI utilities for manual testing
