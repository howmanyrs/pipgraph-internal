"""
LLM Client Configuration Module

Provides a configured Graphiti instance for the active LLM provider.
Supports OpenAI-compatible services through PatchedLLMClient.
"""

import os

# IMPORTANT: Import patch BEFORE importing Graphiti
# This fixes lucene_sanitize() bug that breaks search for words with capital letters
from app.services.graphiti.lucene_sanitize_patch import apply_patch
from app.services.graphiti.prompt_registry import apply_prompt_overrides

from graphiti_core import Graphiti
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from config.settings import settings
from app.services.graphiti.patched_client import PatchedLLMClient
from app.services.graphiti.llm_config import resolve_active_config, snapshot_active_config

# Ensure patch is applied after Graphiti import (idempotent, safe to call multiple times)
apply_patch()

# Override selected graphiti prompts with PipGraph's editable domain blocks (surface A).
# Idempotent; reads prompt_library at call time so in-memory edits apply live.
apply_prompt_overrides()

# Disable telemetry
os.environ['GRAPHITI_TELEMETRY_ENABLED'] = 'false'

# Global Graphiti instance (initialized on first use)
_graphiti_instance = None


async def get_graphiti() -> Graphiti:
    """
    Get the configured Graphiti instance for the active LLM provider.

    The active provider/keys/models come from ``resolve_active_config()``
    (settings defaults + optional runtime overlay). The config the singleton is
    built on is snapshotted so ``/dev/llm-config`` can report ``restart_required``.

    Returns:
        Graphiti: Configured Graphiti instance for the active provider
    """
    global _graphiti_instance

    if _graphiti_instance is None:
        # Resolve the active provider config and snapshot exactly what we build on.
        active = snapshot_active_config()

        # Configure LLM client for main processing
        llm_config = LLMConfig(
            api_key=active.api_key,
            model=active.main_model,
            small_model=active.small_model,
            base_url=active.base_url,
        )

        # Initialize Graphiti with all components
        # Using PatchedLLMClient (example-instead-of-schema) for all providers
        _graphiti_instance = Graphiti(
            settings.NEO4J_URI,
            settings.NEO4J_USER,
            settings.NEO4J_PASSWORD,
            llm_client=PatchedLLMClient(config=llm_config),
            embedder=OpenAIEmbedder(
                config=OpenAIEmbedderConfig(
                    api_key=active.api_key,
                    embedding_model=active.embedding_model,
                    base_url=active.base_url,
                )
            ),
            cross_encoder=OpenAIRerankerClient(
                config=LLMConfig(
                    api_key=active.api_key,
                    model=active.small_model,
                    base_url=active.base_url,
                )
            ),
        )

        # Build indices and constraints on first initialization
        await _graphiti_instance.build_indices_and_constraints()

    return _graphiti_instance
