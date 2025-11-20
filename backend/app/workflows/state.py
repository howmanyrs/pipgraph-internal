"""
PARA Workflow State для LangGraph

State для workflow обработки заметок с PARA идентификацией и
поддержкой множественных suggestions (Granular Suggestions).

Архитектура:
    identify_context → apply_proposal → [check_suggestions]
                                              ↓
                                    wait_for_decision (INTERRUPT)
                                              ↓
                                    process_decision
                                              ↓
                                    [check_suggestions] → extract_content → save_entities
"""

from typing import TypedDict, Optional, List, Dict, Any


class PARAWorkflowState(TypedDict, total=False):
    """
    State для PARA workflow с поддержкой множественных suggestions.

    Ключевая особенность: поддержка нескольких :SUGGESTS ребер между
    Episode и контейнером (link + property_update).

    Пользователь может атомарно принять/отклонить каждое предложение.
    """

    # === Входные данные ===
    note_path: str  # Путь к файлу (используется как Episode.name)
    note_content: str  # Содержимое заметки

    # === L1/L2 Processing ===
    para_type: str  # Результат классификации: "Project" | "Area" | "Resource"
    proposal: Optional[Dict[str, Any]]  # Сериализованный PARAProposal
    container_label: str  # Label контейнера для Neo4j queries

    # === Suggestions tracking ===
    pending_suggestions: List[str]  # Список suggestion_ids требующих решения
    current_suggestion_id: Optional[str]  # ID текущего suggestion для UI

    # === User interaction ===
    user_decision: Optional[Dict[str, Any]]  # Сериализованный UserDecisionPayload

    # === Context (после подтверждения) ===
    confirmed_context: Optional[Dict[str, Any]]  # Информация о контейнере после :IS_PART_OF

    # === L3 Extraction ===
    extracted_entities: List[Dict[str, Any]]  # Сериализованные ExtractedCandidate
    episode_uuid: str  # UUID созданного Episode

    # === Метаданные ===
    processing_started_at: str  # ISO timestamp
    processing_completed_at: Optional[str]  # ISO timestamp
    status: str  # "processing" | "waiting_user" | "completed" | "error"
    error: Optional[str]  # Текст ошибки


# ============================================================================
# Утилиты для сериализации
# ============================================================================

def serialize_proposal(proposal) -> Dict[str, Any]:
    """
    Сериализация PARAProposal для хранения в LangGraph state.

    Args:
        proposal: PARAProposal instance

    Returns:
        dict с сериализованными данными
    """
    return {
        "primary_candidate": _serialize_candidate(proposal.primary_candidate),
        "alternatives": [
            _serialize_candidate(alt) for alt in proposal.alternatives
        ]
    }


def _serialize_candidate(candidate) -> Dict[str, Any]:
    """Сериализация PARACandidate"""
    return {
        "container_id": candidate.container_id,
        "container_name": candidate.container_name,
        "confidence": candidate.confidence,
        "reasoning": candidate.reasoning,
        "suggestion_type": candidate.suggestion_type,
        "target_field": candidate.target_field,
        "suggested_value": candidate.suggested_value,
    }


def serialize_user_decision(decision) -> Dict[str, Any]:
    """
    Сериализация UserDecisionPayload для хранения в state.

    Args:
        decision: UserDecisionPayload instance

    Returns:
        dict с сериализованными данными
    """
    return {
        "suggestion_id": decision.suggestion_id,
        "action": decision.action,
        "selected_container_id": decision.selected_container_id,
        "custom_container_type": decision.custom_container_type,
        "custom_container_name": decision.custom_container_name,
    }


def deserialize_user_decision(data: Dict[str, Any]):
    """
    Десериализация UserDecisionPayload из state.

    Args:
        data: dict из state

    Returns:
        UserDecisionPayload instance
    """
    from app.models.proposal import UserDecisionPayload

    return UserDecisionPayload(
        suggestion_id=data["suggestion_id"],
        action=data["action"],
        selected_container_id=data.get("selected_container_id"),
        custom_container_type=data.get("custom_container_type"),
        custom_container_name=data.get("custom_container_name"),
    )
