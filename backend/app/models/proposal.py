"""
Proposal Models для PARA Context Identification

Модели для представления предложений по связыванию заметок с PARA контейнерами.
Используются в L1/L2 логике идентификации контекста.
"""

from typing import Optional, Literal, List
from pydantic import BaseModel, Field


class PARACandidate(BaseModel):
    """
    Кандидат на связывание заметки с PARA контейнером.

    Представляет одно атомарное предложение:
    - "link": связать заметку с контейнером
    - "property_update": обновить свойство контейнера

    Каждый кандидат становится отдельным ребром :SUGGESTS в графе.
    """
    container_id: str = Field(..., description="ID целевого PARA контейнера")
    container_name: str = Field(..., description="Имя контейнера для отображения")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Уверенность AI (0.0-1.0)")
    reasoning: str = Field(..., description="Объяснение предложения")
    suggestion_type: Literal["link", "property_update"] = Field(
        ...,
        description="Тип предложения: link для связывания, property_update для обновления свойства"
    )

    # Поля для property_update
    target_field: Optional[str] = Field(
        None,
        description="Поле контейнера для обновления (например, 'name')"
    )
    suggested_value: Optional[str] = Field(
        None,
        description="Предлагаемое новое значение для поля"
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "container_id": "proj-001",
                    "container_name": "My Project",
                    "confidence": 0.85,
                    "reasoning": "Note mentions project deliverables",
                    "suggestion_type": "link",
                    "target_field": None,
                    "suggested_value": None
                },
                {
                    "container_id": "proj-001",
                    "container_name": "My Project v2",
                    "confidence": 0.75,
                    "reasoning": "Note suggests project should be renamed",
                    "suggestion_type": "property_update",
                    "target_field": "name",
                    "suggested_value": "My Project v2"
                }
            ]
        }


class PARAProposal(BaseModel):
    """
    Комплексное предложение по контексту заметки.

    Содержит primary candidate (основное предложение) и список альтернатив.
    Все кандидаты будут преобразованы в ребра :SUGGESTS для атомарной обработки.

    Пример использования:
    - primary: связать с Project "Alpha" (link)
    - alternatives: переименовать Project "Alpha" в "Beta" (property_update)

    Пользователь может подтвердить link, но отклонить переименование.
    """
    primary_candidate: PARACandidate = Field(
        ...,
        description="Основной кандидат (обычно link с высокой уверенностью)"
    )
    alternatives: List[PARACandidate] = Field(
        default_factory=list,
        description="Альтернативные кандидаты (другие link или property_update)"
    )

    def all_candidates(self) -> List[PARACandidate]:
        """Возвращает все кандидаты (primary + alternatives)"""
        return [self.primary_candidate] + self.alternatives

    class Config:
        json_schema_extra = {
            "example": {
                "primary_candidate": {
                    "container_id": "mock-project-alpha",
                    "container_name": "Mock Project Alpha",
                    "confidence": 0.80,
                    "reasoning": "Content matches project context",
                    "suggestion_type": "link"
                },
                "alternatives": [
                    {
                        "container_id": "mock-project-alpha",
                        "container_name": "Mock Project Alpha v2",
                        "confidence": 0.75,
                        "reasoning": "Note suggests project renaming",
                        "suggestion_type": "property_update",
                        "target_field": "name",
                        "suggested_value": "Mock Project Alpha v2"
                    }
                ]
            }
        }


class UserDecisionPayload(BaseModel):
    """
    Решение пользователя по конкретному предложению.

    Используется для атомарной обработки решений по suggestion_id.
    """
    suggestion_id: str = Field(..., description="UUID конкретного ребра :SUGGESTS")
    action: Literal["confirm", "dismiss", "link_to_alternative", "create_custom"] = Field(
        ...,
        description="Действие пользователя"
    )

    # Для action="link_to_alternative"
    selected_container_id: Optional[str] = Field(
        None,
        description="ID выбранного альтернативного контейнера"
    )

    # Для action="create_custom"
    custom_container_type: Optional[Literal["Project", "Area", "Resource"]] = Field(
        None,
        description="Тип нового контейнера"
    )
    custom_container_name: Optional[str] = Field(
        None,
        description="Имя нового контейнера"
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "suggestion_id": "uuid-123",
                    "action": "confirm"
                },
                {
                    "suggestion_id": "uuid-456",
                    "action": "dismiss"
                },
                {
                    "suggestion_id": "uuid-789",
                    "action": "create_custom",
                    "custom_container_type": "Project",
                    "custom_container_name": "New Project"
                }
            ]
        }
