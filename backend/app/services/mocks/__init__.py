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

__all__ = [
    "classify_note_para",
    "generate_para_proposal",
]
