"""
OpenRouter LLM Integration Tests

Tests for verifying OpenRouter API connectivity and LLM functionality.
These tests make real API calls and consume credits.
"""

import pytest
from openai import AsyncOpenAI
from config.settings import settings


@pytest.mark.integration
@pytest.mark.slow
def test_openrouter_settings():
    """Verify OpenRouter settings are configured."""
    assert settings.OPENROUTER_API_KEY is not None, "OPENROUTER_API_KEY not set"
    assert settings.OPENROUTER_BASE_URL is not None, "OPENROUTER_BASE_URL not set"
    assert settings.OPENROUTER_MAIN_MODEL is not None, "OPENROUTER_MAIN_MODEL not set"
    assert settings.OPENROUTER_SMALL_MODEL is not None, "OPENROUTER_SMALL_MODEL not set"
    assert settings.OPENROUTER_EMBEDDING_MODEL is not None, "OPENROUTER_EMBEDDING_MODEL not set"


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", [
    pytest.param("small", id="small_model"),
    pytest.param("main", id="main_model"),
])
async def test_openrouter_llm_connection(model_name):
    """Test basic LLM connection through OpenRouter using native OpenAI client."""
    # Map model names to settings
    model_map = {
        "small": settings.OPENROUTER_SMALL_MODEL,
        "main": settings.OPENROUTER_MAIN_MODEL,
    }

    model = model_map[model_name]

    # Initialize OpenAI client with OpenRouter endpoint
    client = AsyncOpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
    )

    # Simple test prompt
    messages = [
        {"role": "user", "content": "Reply with just the word 'test' and nothing else."}
    ]

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=10
        )

        assert response is not None
        assert len(response.choices) > 0
        content = response.choices[0].message.content
        assert content is not None
        assert len(content) > 0

        print(f"\n✅ OpenRouter LLM ({model_name}) response: {content}")

    except Exception as e:
        pytest.fail(f"OpenRouter LLM connection failed for {model_name}: {e}")


# NOTE: OpenRouter does not support embeddings API endpoint as of 2025.
# Embedding models need to be accessed directly through provider APIs (e.g., OpenAI).
# For embedding tests, see Graphiti integration tests which use embeddings internally.


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_openrouter_with_graphiti_client():
    """Test OpenRouter connection through Graphiti client wrapper."""
    from app.services.llm_graphiti_client import get_graphiti

    try:
        graphiti = await get_graphiti()
        assert graphiti is not None
        assert graphiti.llm_client is not None

        print(f"\n✅ Graphiti initialized with LLM client")

    except Exception as e:
        pytest.fail(f"Graphiti initialization with OpenRouter failed: {e}")


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_openrouter_entity_extraction():
    """Test entity extraction capability through OpenRouter."""
    from app.services.llm_graphiti_client import get_graphiti

    try:
        graphiti = await get_graphiti()

        # Simple test text
        test_text = "Alice works at Google as a software engineer."

        # Use Graphiti's extract_entities (if available) or similar method
        # This is a placeholder - adjust based on actual Graphiti API
        result = await graphiti.llm_client.chat.completions.create(
            model=settings.OPENROUTER_SMALL_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": f"Extract entities from this text: {test_text}. Reply with JSON."
                }
            ],
            max_tokens=200
        )

        assert result is not None
        print(f"\n✅ Entity extraction response received")

    except Exception as e:
        pytest.fail(f"Entity extraction through OpenRouter failed: {e}")


@pytest.mark.integration
@pytest.mark.slow
def test_openrouter_models_configured():
    """Test that all required models are properly configured."""
    models = {
        "main": settings.OPENROUTER_MAIN_MODEL,
        "small": settings.OPENROUTER_SMALL_MODEL,
        "embedding": settings.OPENROUTER_EMBEDDING_MODEL,
    }

    for model_type, model_name in models.items():
        assert model_name is not None, f"{model_type} model not configured"
        assert len(model_name) > 0, f"{model_type} model is empty string"
        print(f"✅ {model_type.capitalize()} model: {model_name}")
