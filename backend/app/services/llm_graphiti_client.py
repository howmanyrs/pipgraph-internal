"""
LLM Client Configuration Module

Provides configured Graphiti instance with OpenRouter integration.
Supports OpenAI-compatible services through OpenAIGenericClient.
"""

import os
from graphiti_core import Graphiti
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from config.settings import settings

# Disable telemetry
os.environ['GRAPHITI_TELEMETRY_ENABLED'] = 'false'

# Global Graphiti instance (initialized on first use)
_graphiti_instance = None


async def get_graphiti() -> Graphiti:
    """
    Get configured Graphiti instance with OpenRouter LLM client.

    Returns:
        Graphiti: Configured Graphiti instance with OpenRouter integration
    """
    global _graphiti_instance

    if _graphiti_instance is None:
        # Configure LLM client for main processing
        llm_config = LLMConfig(
            api_key=settings.OPENROUTER_API_KEY,
            model=settings.OPENROUTER_MAIN_MODEL,
            small_model=settings.OPENROUTER_SMALL_MODEL,
            base_url=settings.OPENROUTER_BASE_URL,
        )

        # Configure embedder for vector embeddings
        embedder_config = OpenAIEmbedderConfig(
            api_key=settings.OPENROUTER_API_KEY,
            embedding_model=settings.OPENROUTER_EMBEDDING_MODEL,
            base_url=settings.OPENROUTER_BASE_URL,
        )

        # Configure cross-encoder for reranking (uses small model for efficiency)
        reranker_config = LLMConfig(
            api_key=settings.OPENROUTER_API_KEY,
            model=settings.OPENROUTER_SMALL_MODEL,
            base_url=settings.OPENROUTER_BASE_URL,
        )

        # Initialize Graphiti with all components
        _graphiti_instance = Graphiti(
            settings.NEO4J_URI,
            settings.NEO4J_USER,
            settings.NEO4J_PASSWORD,
            llm_client=OpenAIGenericClient(config=llm_config),
            embedder=OpenAIEmbedder(config=embedder_config),
            cross_encoder=OpenAIRerankerClient(config=reranker_config),
        )

        # Build indices and constraints on first initialization
        await _graphiti_instance.build_indices_and_constraints()

    return _graphiti_instance
