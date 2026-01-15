"""
OpenAI-Compatible LLM Provider Integration Tests

Tests for verifying OpenAI-compatible API connectivity and LLM functionality.
These tests make real API calls and consume credits.
Currently configured for Cloud.ru provider.
"""

import pytest
from openai import AsyncOpenAI
from config.settings import settings


@pytest.mark.integration
@pytest.mark.slow
def test_llm_provider_settings():
    """Verify LLM provider settings are configured."""
    assert settings.CLOUDRU_API_KEY is not None, "CLOUDRU_API_KEY not set"
    assert settings.CLOUDRU_BASE_URL is not None, "CLOUDRU_BASE_URL not set"
    assert settings.CLOUDRU_MAIN_MODEL is not None, "CLOUDRU_MAIN_MODEL not set"
    assert settings.CLOUDRU_SMALL_MODEL is not None, "CLOUDRU_SMALL_MODEL not set"
    assert settings.CLOUDRU_EMBEDDING_MODEL is not None, "CLOUDRU_EMBEDDING_MODEL not set"


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", [
    pytest.param("small", id="small_model"),
    pytest.param("main", id="main_model"),
])
async def test_llm_chat_completion(model_name):
    """Test basic LLM chat completion using native OpenAI client."""
    # Map model names to settings
    model_map = {
        "small": settings.CLOUDRU_SMALL_MODEL,
        "main": settings.CLOUDRU_MAIN_MODEL,
    }

    model = model_map[model_name]

    # Initialize OpenAI client with provider endpoint
    client = AsyncOpenAI(
        api_key=settings.CLOUDRU_API_KEY,
        base_url=settings.CLOUDRU_BASE_URL,
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

        # Verify response matches expected test word
        assert "test" in content.lower(), f"Expected 'test' in response, got: {content}"

        print(f"\n✅ LLM ({model_name}) response: {content}")

    except Exception as e:
        pytest.fail(f"LLM chat completion failed for {model_name}: {e}")


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_embedding_model():
    """Test embedding model connection through Cloud.ru provider."""
    client = AsyncOpenAI(
        api_key=settings.CLOUDRU_API_KEY,
        base_url=settings.CLOUDRU_BASE_URL
    )

    try:
        response = await client.embeddings.create(
            model=settings.CLOUDRU_EMBEDDING_MODEL,
            input=["Как написать хороший код?"]
        )

        assert response is not None
        assert len(response.data) > 0
        assert len(response.data[0].embedding) > 0

        print(f"\n✅ Embedding model response: vector dimension={len(response.data[0].embedding)}")

    except Exception as e:
        pytest.fail(f"Embedding model connection failed: {e}")


# @pytest.mark.integration
# @pytest.mark.slow
# @pytest.mark.asyncio
# async def test_graphiti_client_initialization():
#     """Test LLM provider connection through Graphiti client wrapper."""
#     from app.services.graphiti.setup_graphiti import get_graphiti

#     try:
#         graphiti = await get_graphiti()
#         assert graphiti is not None
#         assert graphiti.llm_client is not None

#         print(f"\n✅ Graphiti initialized with LLM client")

#     except Exception as e:
#         pytest.fail(f"Graphiti initialization failed: {e}")


# @pytest.mark.integration
# @pytest.mark.slow
# @pytest.mark.asyncio
# async def test_graphiti_llm_communication():
#     """Test that Graphiti framework can communicate with LLM provider."""
#     from app.services.graphiti.setup_graphiti import get_graphiti

#     try:
#         graphiti = await get_graphiti()

#         # Simple test prompt to verify communication
#         result = await graphiti.llm_client.chat.completions.create(
#             model=settings.CLOUDRU_SMALL_MODEL,
#             messages=[
#                 {
#                     "role": "user",
#                     "content": "Reply with just the word 'OK' and nothing else."
#                 }
#             ],
#             max_tokens=10
#         )

#         assert result is not None
#         assert len(result.choices) > 0
#         content = result.choices[0].message.content
#         assert content is not None
#         assert len(content) > 0

#         # Verify response matches expected test word
#         assert "ok" in content.lower(), f"Expected 'OK' in response, got: {content}"

#         print(f"\n✅ Graphiti-LLM communication successful: {content}")

#     except Exception as e:
#         pytest.fail(f"Graphiti-LLM communication failed: {e}")


@pytest.mark.integration
@pytest.mark.slow
def test_llm_models_configured():
    """Test that all required models are properly configured."""
    models = {
        "main": settings.CLOUDRU_MAIN_MODEL,
        "small": settings.CLOUDRU_SMALL_MODEL,
        "embedding": settings.CLOUDRU_EMBEDDING_MODEL,
    }

    for model_type, model_name in models.items():
        assert model_name is not None, f"{model_type} model not configured"
        assert len(model_name) > 0, f"{model_type} model is empty string"
        print(f"✅ {model_type.capitalize()} model: {model_name}")
