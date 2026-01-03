"""
Proposal Manager - Apply PARA proposals to Neo4j graph

Этот модуль управляет применением предложений (PARAProposal) к графу.
Каждый кандидат из предложения становится ребром :SUGGESTS или :IS_PART_OF
в зависимости от confidence и типа.

Правила применения:
- Если confidence > 0.95 И suggestion_type == "link" → создать :IS_PART_OF (автоматическое связывание)
- Иначе → создать :SUGGESTS (требует подтверждения пользователя)
"""

import logging
from uuid import uuid4
from typing import List, Dict, Any

from app.models.proposal import PARAProposal, PARACandidate
from app.crud import relationship_crud as rel_crud_module

logger = logging.getLogger(__name__)

# Порог уверенности для автоматического связывания
AUTO_LINK_CONFIDENCE_THRESHOLD = 0.95


class ProposalManager:
    """Управление применением PARA предложений к графу."""

    def __init__(self, relationship_crud: "rel_crud_module.RelationshipCRUD" = None):
        """
        Инициализация менеджера.

        Args:
            relationship_crud: CRUD для работы со связями. Если None, создает новый.
        """
        self.relationship_crud = relationship_crud or rel_crud_module.RelationshipCRUD()

    def apply_proposal_to_graph(
        self,
        episodic_path: str,
        proposal: PARAProposal,
        container_label: str = "Project"
    ) -> Dict[str, Any]:
        """
        Применяет PARAProposal к графу, создавая соответствующие связи.

        Для каждого кандидата в предложении:
        - Генерирует уникальный suggestion_id
        - Создает :IS_PART_OF если confidence > 0.95 И type == "link"
        - Иначе создает :SUGGESTS с полными метаданными

        Args:
            episodic_path: Путь к Episodic узлу (file path)
            proposal: Предложение с кандидатами
            container_label: Метка контейнера (Project, Area, Resource)

        Returns:
            Dict с результатами:
            - created_links: list[str] - ID созданных :IS_PART_OF
            - created_suggestions: list[str] - ID созданных :SUGGESTS
            - total_candidates: int - общее число обработанных кандидатов
        """
        created_links: List[str] = []
        created_suggestions: List[str] = []

        # Обрабатываем все кандидаты (primary + alternatives)
        all_candidates = proposal.all_candidates()

        logger.info(
            f"Applying proposal with {len(all_candidates)} candidates "
            f"to {episodic_path}"
        )

        for candidate in all_candidates:
            suggestion_id = str(uuid4())

            # Решаем: автоматический link или suggestion для подтверждения
            should_auto_link = (
                candidate.confidence > AUTO_LINK_CONFIDENCE_THRESHOLD
                and candidate.suggestion_type == "link"
            )

            if should_auto_link:
                # Высокая уверенность - создаем подтвержденную связь
                result = self.relationship_crud.create_link(
                    episodic_path=episodic_path,
                    container_id=candidate.container_id,
                    container_label=container_label
                )
                if result:
                    created_links.append(candidate.container_id)
                    logger.info(
                        f"✓ Auto-linked (confidence={candidate.confidence:.2f}): "
                        f"{episodic_path} -> {candidate.container_name}"
                    )
            else:
                # Создаем предложение для подтверждения пользователем
                result = self.relationship_crud.create_suggestion(
                    episodic_path=episodic_path,
                    container_id=candidate.container_id,
                    suggestion_id=suggestion_id,
                    confidence=candidate.confidence,
                    reasoning=candidate.reasoning,
                    suggestion_type=candidate.suggestion_type,
                    target_field=candidate.target_field,
                    suggested_value=candidate.suggested_value,
                    container_label=container_label
                )
                if result:
                    created_suggestions.append(suggestion_id)
                    logger.info(
                        f"✓ Created suggestion [{candidate.suggestion_type}]: "
                        f"{episodic_path} -> {candidate.container_name} "
                        f"(id: {suggestion_id[:8]}..., confidence={candidate.confidence:.2f})"
                    )

        result_summary = {
            "created_links": created_links,
            "created_suggestions": created_suggestions,
            "total_candidates": len(all_candidates)
        }

        logger.info(
            f"Proposal applied: {len(created_links)} links, "
            f"{len(created_suggestions)} suggestions"
        )

        return result_summary


# Convenience function for direct usage
def apply_proposal_to_graph(
    episodic_path: str,
    proposal: PARAProposal,
    container_label: str = "Project",
    relationship_crud: "rel_crud_module.RelationshipCRUD" = None
) -> Dict[str, Any]:
    """
    Применяет PARAProposal к графу (функциональный интерфейс).

    Обертка над ProposalManager для удобного использования без создания экземпляра.

    Args:
        episodic_path: Путь к Episodic узлу
        proposal: Предложение с кандидатами
        container_label: Метка контейнера
        relationship_crud: Опциональный CRUD instance

    Returns:
        Dict с результатами применения
    """
    manager = ProposalManager(relationship_crud)
    return manager.apply_proposal_to_graph(episodic_path, proposal, container_label)
