"""
PARA Context Identification Services

Этот модуль экспортирует функции для идентификации контекста заметки.
Переключение между mock и реальными LLM реализациями происходит
через изменение импортов в этом файле.

Использование:
    from app.services.para import classify_note_para, generate_para_proposal

    # L1: Определить тип PARA
    para_type = classify_note_para(note_content)

    # L2: Сгенерировать предложение
    proposal = generate_para_proposal(note_content)
"""

# ============================================================================
# Текущая конфигурация: MOCK реализации
# ============================================================================

from app.services.mocks.mock_classifier import classify_note_para
from app.services.mocks.mock_proposal_generator import generate_para_proposal

# ============================================================================
# Для перехода на реальные LLM - раскомментировать и закомментировать выше:
# ============================================================================

# from app.services.llm.real_classifier import classify_note_para
# from app.services.llm.real_proposal_generator import generate_para_proposal

__all__ = [
    "classify_note_para",
    "generate_para_proposal",
]
