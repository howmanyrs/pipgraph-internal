"""
Mock L2 Proposal Generator

Мок-реализация генератора предложений по связыванию заметки с PARA контейнером.
Возвращает детерминированный PARAProposal с link + property_update кандидатами.

После проверки архитектуры заменить на реальную LLM реализацию
в app/services/llm/real_proposal_generator.py
"""

from app.models.proposal import PARAProposal, PARACandidate


def generate_para_proposal(note_content: str) -> PARAProposal:
    """
    Mock L2: Генерирует предложение по связыванию заметки с PARA контейнером.

    TODO: In future, pass para_type to guide proposal generation
    смотри сопуствующий метод classify_note_para - есть нюансы по очередности, 
    когда их надо находить


    В реальной реализации будет использовать:
    - Embeddings для поиска похожих контейнеров
    - LLM для генерации reasoning и suggestions

    Mock версия возвращает фиксированный набор предложений:
    - primary: link к "Mock Project Alpha" (confidence: 0.80)
    - alternative: property_update - переименование в "Mock Project Alpha v2" (confidence: 0.75)

    Args:
        note_content: Текстовое содержимое заметки

    Returns:
        PARAProposal: Комплексное предложение с кандидатами
    """
    return PARAProposal(
        primary_candidate=PARACandidate(
            container_id="mock-project-alpha",
            container_name="Mock Project Alpha",
            confidence=0.80,
            reasoning="Mock: content matches project context based on keywords and structure",
            suggestion_type="link"
        ),
        alternatives=[
            PARACandidate(
                container_id="mock-project-alpha",
                container_name="Mock Project Alpha v2",
                confidence=0.75,
                reasoning="Mock: note content suggests project should be renamed to reflect new scope",
                suggestion_type="property_update",
                target_field="name",
                suggested_value="Mock Project Alpha v2"
            )
        ]
    )
