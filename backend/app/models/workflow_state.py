"""
Workflow State Models для LangGraph MVP

Минимальные модели для демонстрации interrupt/resume механизма.
Состояние будет расширяться по мере добавления новых фич (L1, L2, L3).
"""

from typing import TypedDict, Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel

from graphiti_core.nodes import EntityNode


# ============================================================================
# LangGraph State (TypedDict для LangGraph)
# ============================================================================

class NoteWorkflowState(TypedDict, total=False):
    """
    Минимальное состояние обработки заметки для LangGraph MVP.

    Архитектура:
    - extract_entities → ask_user (INTERRUPT) → finalize

    В будущем расширится до L1 (PARA), L2 (containers), L3 (entities).
    """
    # === Входные данные ===
    file_path: str
    content: str

    # === Извлеченные данные ===
    entities: List[Dict[str, Any]]  # Сериализованные EntityNode
    episode_uuid: str  # UUID созданного эпизода

    # === Вопрос пользователю (MVP: один вопрос) ===
    needs_confirmation: bool
    pending_question: Optional[Dict[str, Any]]  # Структура вопроса
    user_answer: Optional[Dict[str, Any]]  # Ответ пользователя

    # === Метаданные ===
    processing_started_at: str  # ISO timestamp
    processing_completed_at: Optional[str]  # ISO timestamp
    status: str  # "processing" | "waiting_user" | "completed" | "error"
    error: Optional[str]  # Текст ошибки (если status = "error")


# ============================================================================
# Pydantic Models для API и валидации
# ============================================================================

class ClarificationQuestion(BaseModel):
    """Структура вопроса пользователю"""
    question_id: str  # Уникальный ID вопроса
    question_type: str  # "entity_confirmation" | "para_classification" | ...
    question_text: str  # Текст вопроса для UI
    entity_uuid: Optional[str] = None  # UUID сущности (если вопрос про сущность)
    entity_name: Optional[str] = None  # Имя сущности
    entity_type: Optional[str] = None  # Тип сущности (Person, Project, etc.)
    suggested_action: Optional[str] = None  # "confirm" | "modify" | "reject"
    confidence: Optional[float] = None  # Уверенность LLM (0.0 - 1.0)


class UserAnswer(BaseModel):
    """Ответ пользователя на вопрос"""
    question_id: str  # ID вопроса, на который отвечаем
    action: str  # "confirm" | "modify" | "reject" | "skip"
    modified_name: Optional[str] = None  # Если action = "modify"
    comment: Optional[str] = None  # Комментарий пользователя


class WorkflowStatus(BaseModel):
    """Статус workflow для API"""
    thread_id: str  # ID потока (обычно = file_path)
    status: str  # "processing" | "waiting_user" | "completed" | "error"
    file_path: str
    episode_uuid: Optional[str] = None
    pending_question: Optional[ClarificationQuestion] = None
    processing_started_at: datetime
    processing_completed_at: Optional[datetime] = None
    error: Optional[str] = None


# ============================================================================
# Утилиты для сериализации EntityNode
# ============================================================================

def serialize_entity(entity: EntityNode) -> Dict[str, Any]:
    """
    Сериализация EntityNode для хранения в LangGraph state.

    LangGraph сохраняет состояние в SQLite через pickle/json,
    поэтому нужно преобразовать EntityNode в простой dict.
    """
    return {
        "uuid": entity.uuid,
        "name": entity.name,
        "labels": entity.labels,
        "summary": entity.summary,
        "created_at": entity.created_at.isoformat() if entity.created_at else None,
    }


def deserialize_entity(data: Dict[str, Any]) -> EntityNode:
    """Десериализация EntityNode из LangGraph state"""
    from datetime import datetime

    return EntityNode(
        uuid=data["uuid"],
        name=data["name"],
        labels=data["labels"],
        summary=data.get("summary", ""),
        created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
    )
