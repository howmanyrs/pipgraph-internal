"""
Graphiti integration layer.

Модули для работы с graphiti_core:
- setup_graphiti: инициализация Graphiti клиента
- patched_client: патчи для специфичных провайдеров (Cloud.ru/Qwen)
- pipgraph_manager: бизнес-логика работы с графом
"""

from app.services.graphiti.setup_graphiti import get_graphiti
from app.services.graphiti.patched_client import CloudRuPatchedClient
from app.services.graphiti.pipgraph_manager import (
    PipGraphManager,
    AddEpisodeResults,
)

__all__ = [
    # Client
    "get_graphiti",
    "CloudRuPatchedClient",
    # Manager
    "PipGraphManager",
    "AddEpisodeResults",
]
