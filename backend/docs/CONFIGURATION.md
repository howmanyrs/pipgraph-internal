# Configuration Guide

Comprehensive guide to configuring the PipGraph backend using environment variables and pydantic-settings.

## Overview

The backend uses [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) for type-safe configuration management through:
- Environment variables
- `.env` files
- System environment
- Runtime configuration

Configuration is defined in `config/settings.py` and available globally via:

```python
from config.settings import settings

# Usage
openai_key = settings.OPENAI_API_KEY
neo4j_uri = settings.NEO4J_URI
```

## Required Variables

### OpenRouter API Configuration

```bash
# OpenRouter API for LLM processing
OPENROUTER_API_KEY=sk-or-v1-xxxxx...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Model selection
OPENROUTER_MAIN_MODEL=anthropic/claude-3.5-sonnet
OPENROUTER_SMALL_MODEL=anthropic/claude-3-haiku
OPENROUTER_EMBEDDING_MODEL=openai/text-embedding-3-small
```

**Notes:**
- Get API key from [openrouter.ai](https://openrouter.ai/)
- Main model: complex reasoning tasks
- Small model: fast, cheap operations
- Embedding model: Used by Graphiti (accessed directly via provider, not through OpenRouter)

### Neo4j Database Configuration

```bash
# Neo4j connection
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_secure_password
```

**Notes:**
- Default port: 7687 for Bolt protocol
- Use `neo4j://` for routing (cluster), `bolt://` for direct connection
- For cloud deployments (Aura), use provided connection string

### Optional Variables

```bash
# Server configuration
HOST=0.0.0.0
PORT=8000
DEBUG=false

# Logging
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR

# CORS (for web prototype)
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

## Configuration Methods

### Method 1: .env File (Recommended for Development)

Create `.env` file in `backend/` directory:

```bash
cd backend/
cat > .env << 'EOF'
# OpenRouter
OPENROUTER_API_KEY=sk-or-v1-xxxxx...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MAIN_MODEL=anthropic/claude-3.5-sonnet
OPENROUTER_SMALL_MODEL=anthropic/claude-3-haiku
OPENROUTER_EMBEDDING_MODEL=openai/text-embedding-3-small

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
EOF
```

**Security:**
- Add `.env` to `.gitignore` (already configured)
- Never commit `.env` files to version control
- Use different `.env` files for dev/staging/prod

### Method 2: System Environment Variables

**Linux/macOS:**
```bash
export OPENROUTER_API_KEY="sk-or-v1-xxxxx..."
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your_password"
```

Add to `~/.bashrc` or `~/.zshrc` for persistence.

**Windows (PowerShell):**
```powershell
$env:OPENROUTER_API_KEY="sk-or-v1-xxxxx..."
$env:NEO4J_URI="bolt://localhost:7687"
```

**Windows (CMD):**
```cmd
set OPENROUTER_API_KEY=sk-or-v1-xxxxx...
set NEO4J_URI=bolt://localhost:7687
```

### Method 3: Runtime Configuration

Pass variables when starting the server:

```bash
OPENROUTER_API_KEY=xxx NEO4J_URI=bolt://localhost:7687 \
NEO4J_USER=neo4j NEO4J_PASSWORD=xxx \
uvicorn app.api.main:app --reload
```

### Method 4: Docker Environment

In `docker-compose.yml`:

```yaml
services:
  backend:
    image: pipgraph-backend
    environment:
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
      - NEO4J_URI=bolt://neo4j:7687
      - NEO4J_USER=neo4j
      - NEO4J_PASSWORD=${NEO4J_PASSWORD}
```

Use with `.env` file in the same directory.

## Configuration Validation

The settings are validated on application startup using Pydantic:

```python
# config/settings.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    OPENROUTER_API_KEY: str  # Required
    NEO4J_URI: str = "bolt://localhost:7687"  # Default value

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True
    )
```

**Missing required variables will cause startup failure** with clear error messages.

## Environment-Specific Configuration

### Development

```bash
# .env.development
DEBUG=true
LOG_LEVEL=DEBUG
NEO4J_URI=bolt://localhost:7687
OPENROUTER_MAIN_MODEL=anthropic/claude-3-haiku  # Cheaper for dev
```

### Testing

```bash
# .env.test
NEO4J_URI=bolt://localhost:7688  # Separate test DB
OPENROUTER_MAIN_MODEL=anthropic/claude-3-haiku
```

Load specific env file:

```python
from pydantic_settings import SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.test"  # Override default
    )
```

### Production

**DO NOT use .env files in production.**

Use system environment variables or secrets management:
- Docker secrets
- Kubernetes secrets
- AWS Secrets Manager
- Azure Key Vault
- HashiCorp Vault

## Neo4j Connection Patterns

### Local Development

```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=local_dev_password
```

### Docker Compose

```bash
NEO4J_URI=bolt://neo4j:7687  # Service name as hostname
NEO4J_USER=neo4j
NEO4J_PASSWORD=${NEO4J_PASSWORD}
```

### Neo4j Aura (Cloud)

```bash
NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=generated_password
```

**Note:** Use `neo4j+s://` for secure TLS connection.

### Connection Pooling

Configure connection pool in code:

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    settings.NEO4J_URI,
    auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    max_connection_lifetime=3600,
    max_connection_pool_size=50,
    connection_acquisition_timeout=120
)
```

## OpenRouter Configuration

### Model Selection

Choose models based on your needs:

**Main Model (complex reasoning):**
- `anthropic/claude-3.5-sonnet` - Best quality
- `anthropic/claude-3-opus` - Most capable
- `openai/gpt-4-turbo` - Alternative

**Small Model (fast operations):**
- `anthropic/claude-3-haiku` - Fast, cheap
- `openai/gpt-3.5-turbo` - Alternative
- `google/gemini-flash` - Very fast

**Embedding Model:**
- `openai/text-embedding-3-small` - Good balance
- `openai/text-embedding-3-large` - Higher quality
- `openai/text-embedding-ada-002` - Legacy

### Cost Optimization

```bash
# Use cheaper models for development
OPENROUTER_MAIN_MODEL=anthropic/claude-3-haiku
OPENROUTER_SMALL_MODEL=anthropic/claude-3-haiku
```

### API Headers (Optional)

For tracking usage per application:

```python
headers = {
    "HTTP-Referer": "https://your-app.com",
    "X-Title": "PipGraph",
}
```

## Troubleshooting

### Error: "OPENROUTER_API_KEY not set"

**Solution:**
1. Check `.env` file exists in `backend/` directory
2. Verify variable name is exactly `OPENROUTER_API_KEY` (case-sensitive)
3. Ensure no spaces around `=` in `.env` file
4. Restart the server after changing `.env`

### Error: "Could not connect to Neo4j"

**Solution:**
1. Check Neo4j is running: `docker ps` or `neo4j status`
2. Verify `NEO4J_URI` format: `bolt://host:port`
3. Test connection with Neo4j Browser: http://localhost:7474
4. Check credentials are correct

### Error: "Settings validation error"

**Solution:**
Check the error message for which field failed validation:

```
ValidationError: 1 validation error for Settings
NEO4J_URI
  field required (type=value_error.missing)
```

Add the missing variable to your `.env` file.

### `.env` file not loading

**Solution:**
1. File must be named exactly `.env` (not `.env.txt`)
2. Must be in `backend/` directory (where you run uvicorn)
3. Check file encoding is UTF-8
4. Verify no BOM (Byte Order Mark) in file

## Security Best Practices

### DO

✅ Use `.env` files for local development
✅ Add `.env` to `.gitignore`
✅ Use environment variables in production
✅ Rotate API keys regularly
✅ Use different credentials for dev/staging/prod
✅ Store production secrets in secure vaults

### DON'T

❌ Commit `.env` files to Git
❌ Share `.env` files via email/Slack
❌ Use production credentials in development
❌ Hardcode secrets in source code
❌ Use weak or default passwords
❌ Log sensitive configuration values

## Example Configurations

### Complete Development Setup

```bash
# backend/.env

# OpenRouter (development)
OPENROUTER_API_KEY=sk-or-v1-xxxxx...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MAIN_MODEL=anthropic/claude-3-haiku
OPENROUTER_SMALL_MODEL=anthropic/claude-3-haiku
OPENROUTER_EMBEDDING_MODEL=openai/text-embedding-3-small

# Neo4j (local)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=dev_password

# Server
HOST=0.0.0.0
PORT=8000
DEBUG=true
LOG_LEVEL=DEBUG

# CORS (for web prototype)
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

### Minimal Production Setup

```bash
# System environment variables only (no .env file)

OPENROUTER_API_KEY=<from-secrets-manager>
NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=<from-secrets-manager>
LOG_LEVEL=WARNING
```

## Related Documentation

- [Testing Configuration](TESTING.md#конфигурация-окружения) - Test-specific settings
- [Architecture](ARCHITECTURE.md) - How configuration fits into the system
- [Backend README](../README.md) - General setup instructions
