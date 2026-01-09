"""
LLM Client Configuration Module

Provides configured Graphiti instance with Cloud.ru integration.
Supports OpenAI-compatible services through CloudRuPatchedClient.
"""

import os

# IMPORTANT: Import patch BEFORE importing Graphiti
# This fixes lucene_sanitize() bug that breaks search for words with capital letters
import app.services.graphiti.lucene_sanitize_patch  # noqa: F401 (applies patch on import)

from graphiti_core import Graphiti
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from config.settings import settings
from app.services.graphiti.patched_client import CloudRuPatchedClient

# Disable telemetry
os.environ['GRAPHITI_TELEMETRY_ENABLED'] = 'false'

# Global Graphiti instance (initialized on first use)
_graphiti_instance = None


async def get_graphiti() -> Graphiti:
    """
    Get configured Graphiti instance with Cloud.ru LLM client.

    Returns:
        Graphiti: Configured Graphiti instance with Cloud.ru integration
    """
    global _graphiti_instance

    if _graphiti_instance is None:
        # Configure LLM client for main processing
        llm_config = LLMConfig(
            api_key=settings.CLOUDRU_API_KEY,
            model=settings.CLOUDRU_MAIN_MODEL,
            small_model=settings.CLOUDRU_SMALL_MODEL,
            base_url=settings.CLOUDRU_BASE_URL,
        )

        # Initialize Graphiti with all components
        # Using CloudRuPatchedClient for Qwen-compatible JSON schema instructions
        _graphiti_instance = Graphiti(
            settings.NEO4J_URI,
            settings.NEO4J_USER,
            settings.NEO4J_PASSWORD,
            llm_client=CloudRuPatchedClient(config=llm_config),
            embedder=OpenAIEmbedder(
                config=OpenAIEmbedderConfig(
                    api_key=settings.CLOUDRU_API_KEY,
                    embedding_model=settings.CLOUDRU_EMBEDDING_MODEL,
                    base_url=settings.CLOUDRU_BASE_URL,
                )
            ),
            cross_encoder=OpenAIRerankerClient(
                config=LLMConfig(
                    api_key=settings.CLOUDRU_API_KEY,
                    model=settings.CLOUDRU_SMALL_MODEL,
                    base_url=settings.CLOUDRU_BASE_URL,
                )
            ),
        )

        # Build indices and constraints on first initialization
        await _graphiti_instance.build_indices_and_constraints()

    return _graphiti_instance
