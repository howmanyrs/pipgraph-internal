"""
Mock Services для Mock-First Development

Этот пакет содержит mock-реализации LLM сервисов для быстрой
проверки архитектуры без реальных API вызовов.

Mock-методы возвращают детерминированные данные, что позволяет:
- Быстро итерировать без задержек на LLM
- Проверять схему данных в Neo4j Browser
- Отлаживать CRUD операции

После проверки архитектуры моки заменяются реальными LLM вызовами
через изменение импортов в app/services/para/__init__.py
"""

from app.services.mocks.mock_classifier import classify_note_para
from app.services.mocks.mock_proposal_generator import generate_para_proposal
from app.services.mocks.mock_graphiti import extract_entities
from app.services.mocks.mock_cascade import (
    mock_find_cascade_candidates,
    mock_apply_cascade,
    get_mock_cascade_test_data,
)

__all__ = [
    "classify_note_para",
    "generate_para_proposal",
    "extract_entities",
    "mock_find_cascade_candidates",
    "mock_apply_cascade",
    "get_mock_cascade_test_data",
]
