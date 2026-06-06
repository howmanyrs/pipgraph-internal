"""
Graphiti integration layer.

Модули для работы с graphiti_core:
- setup_graphiti: инициализация Graphiti клиента
- patched_client: общий патч-клиент LLM для всех провайдеров
- pipgraph_manager: бизнес-логика работы с графом
"""

from app.services.graphiti.setup_graphiti import get_graphiti
from app.services.graphiti.patched_client import PatchedLLMClient
from app.services.graphiti.pipgraph_manager import (
    PipGraphManager,
    AddEpisodeResults,
    CrossFolderFilePathError,
)

__all__ = [
    # Client
    "get_graphiti",
    "PatchedLLMClient",
    # Manager
    "PipGraphManager",
    "AddEpisodeResults",
    "CrossFolderFilePathError",
]
