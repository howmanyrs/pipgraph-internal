"""
Pydantic модели для MVP системы многоуровневых подтверждений

Этот файл содержит готовые к использованию модели для:
- UserCheckStatus и связанные структуры
- PARA контейнеры (Project, Area, Resource)
- Специализированные модели для уровней (L1, L2)
- Состояние LangGraph workflow

Дата: 2025-11-17
Версия: 1.0

Использование:
    from app.models.user_check import UserCheckStatus, FieldModification
    from app.models.para_containers import Project, Area, Resource
"""

from typing import Optional, List, Literal, Dict, Any
from datetime import datetime, date
from pydantic import BaseModel, Field
from uuid import uuid4


# ============================================================================
# 1. USER CHECK MODELS
# ============================================================================

class FieldModification(BaseModel):
    """Описание изменения одного поля сущности"""

    field_name: str = Field(..., description="Название поля")
    original_value: Optional[str] = Field(None, description="Исходное значение")
    new_value: str = Field(..., description="Новое значение")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Время изменения")

    class Config:
        json_schema_extra = {
            "example": {
                "field_name": "name",
                "original_value": "John",
                "new_value": "John Smith",
                "timestamp": "2025-11-17T12:05:00Z"
            }
        }


class UserCheckStatus(BaseModel):
    """
    Базовая модель для UserCheckStatus node в Neo4j.

    Представляет одно событие подтверждения пользователя.
    Каждая нода - это snapshot состояния на момент действия.
    """

    # === Идентификация ===
    id: str = Field(default_factory=lambda: f"check_{uuid4().hex[:12]}", description="Уникальный ID проверки")

    # === Основной статус ===
    status: Literal[
        "pending",
        "confirmed",
        "modified",
        "rejected",
        "skipped",
        "auto_confirmed"
    ] = Field(..., description="Статус подтверждения")

    confirmation_level: Literal[
        "para_classification",
        "container_assignment",
        "entity",
        "attribute"
    ] = Field(..., description="Уровень подтверждения")

    # === Метаданные ===
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Уверенность системы")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Время создания")
    user_action: Optional[Literal["confirm", "modify", "reject", "skip", "defer"]] = Field(
        None, description="Действие пользователя"
    )

    # === Изменения (только для status="modified") ===
    modified_fields: Optional[List[str]] = Field(None, description="Список измененных полей")
    modifications: Optional[str] = Field(None, description="JSON-массив FieldModification объектов")

    # === Дополнительная информация ===
    user_comment: Optional[str] = Field(None, description="Комментарий пользователя")
    system_suggestion: Optional[str] = Field(None, description="Предложение системы")
    auto_confirmed: bool = Field(False, description="Автоматически подтверждено")

    # === Skip/Defer ===
    skip_count: int = Field(0, description="Количество пропусков")
    defer_until: Optional[datetime] = Field(None, description="Отложить до")
    defer_reason: Optional[str] = Field(None, description="Причина отсрочки")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "check_abc123",
                "status": "confirmed",
                "confirmation_level": "entity",
                "confidence": 0.85,
                "timestamp": "2025-11-17T12:00:00Z",
                "user_action": "confirm",
                "system_suggestion": "Person: John Smith",
                "auto_confirmed": False,
                "skip_count": 0
            }
        }


# ============================================================================
# 2. PARA CONTAINER MODELS
# ============================================================================

class Project(BaseModel):
    """PARA контейнер: Проект с дедлайном"""

    id: str = Field(default_factory=lambda: f"proj_{uuid4().hex[:8]}", description="Уникальный ID проекта")
    name: str = Field(..., description="Название проекта")
    status: Literal["active", "completed", "archived", "on_hold"] = Field("active", description="Статус проекта")
    deadline: Optional[date] = Field(None, description="Дедлайн проекта")
    goal: Optional[str] = Field(None, description="Цель проекта")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Дата создания")
    completed_at: Optional[datetime] = Field(None, description="Дата завершения")
    team: Optional[List[str]] = Field(None, description="UUID участников (Person nodes)")
    budget: Optional[float] = Field(None, description="Бюджет проекта")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "proj_abc123",
                "name": "Q4 Marketing Campaign",
                "status": "active",
                "deadline": "2024-12-31",
                "goal": "Increase signups by 20%",
                "created_at": "2024-10-01T00:00:00Z"
            }
        }


class Area(BaseModel):
    """PARA контейнер: Сфера ответственности без дедлайна"""

    id: str = Field(default_factory=lambda: f"area_{uuid4().hex[:8]}", description="Уникальный ID области")
    name: str = Field(..., description="Название области")
    goal: Optional[str] = Field(None, description="Цель области")
    review_frequency: Optional[Literal["weekly", "monthly", "quarterly"]] = Field(
        None, description="Частота пересмотра"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Дата создания")
    active: bool = Field(True, description="Активна ли область")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "area_xyz456",
                "name": "Team Management",
                "goal": "Maintain high team morale and productivity",
                "review_frequency": "monthly",
                "active": True
            }
        }


class Resource(BaseModel):
    """PARA контейнер: Справочный материал"""

    id: str = Field(default_factory=lambda: f"res_{uuid4().hex[:8]}", description="Уникальный ID ресурса")
    topic: str = Field(..., description="Тема ресурса")
    category: Optional[str] = Field(None, description="Категория")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Дата создания")
    tags: Optional[List[str]] = Field(None, description="Теги для поиска")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "res_def789",
                "topic": "API Design Best Practices",
                "category": "Programming",
                "tags": ["api", "rest", "design"]
            }
        }


# ============================================================================
# 3. SPECIALIZED MODELS FOR LEVELS
# ============================================================================

class PARAClassificationCheck(BaseModel):
    """User check для PARA классификации заметки (Level 1)"""

    status: Literal["pending", "confirmed", "modified"] = Field(..., description="Статус проверки")

    original_suggestion: Literal["Project", "Area", "Resource", "Archive"] = Field(
        ..., description="Предложение системы"
    )
    user_choice: Literal["Project", "Area", "Resource", "Archive"] = Field(
        ..., description="Выбор пользователя"
    )

    confidence: float = Field(..., ge=0.0, le=1.0, description="Уверенность системы")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Время проверки")

    reasoning: Optional[str] = Field(None, description="Обоснование выбора")
    changed: bool = Field(False, description="Изменено ли предложение системы")

    def model_post_init(self, __context):
        """Автоматически рассчитываем changed и status"""
        self.changed = self.original_suggestion != self.user_choice
        if self.changed:
            self.status = "modified"

    class Config:
        json_schema_extra = {
            "example": {
                "status": "modified",
                "original_suggestion": "Project",
                "user_choice": "Area",
                "confidence": 0.70,
                "reasoning": "This is ongoing responsibility, not a time-bound project",
                "changed": True
            }
        }


class ContainerAssignmentCheck(BaseModel):
    """User check для привязки к проекту/области (Level 2)"""

    status: Literal["pending", "confirmed", "created"] = Field(..., description="Статус проверки")

    action: Literal["create_new", "link_existing", "skip"] = Field(..., description="Действие пользователя")

    container_type: Literal["Project", "Area", "Resource"] = Field(..., description="Тип контейнера")
    container_id: str = Field(..., description="UUID контейнера")
    container_name: str = Field(..., description="Название контейнера")

    created_new: bool = Field(False, description="Создан ли новый контейнер")
    container_metadata: Optional[Dict[str, Any]] = Field(None, description="Метаданные контейнера")

    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Время проверки")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "created",
                "action": "create_new",
                "container_type": "Project",
                "container_id": "proj_new_123",
                "container_name": "Q4 Marketing Campaign 2024",
                "created_new": True,
                "container_metadata": {
                    "deadline": "2024-12-31",
                    "goal": "Increase signups by 20%"
                }
            }
        }


# ============================================================================
# 4. LANGGRAPH STATE
# ============================================================================

from typing_extensions import TypedDict  # For Python < 3.12

class NoteProcessingState(TypedDict):
    """
    Состояние обработки заметки в LangGraph workflow.

    Это TypedDict, а не Pydantic BaseModel, так как LangGraph
    работает с TypedDict для состояния.
    """

    # === Входные данные ===
    file_path: str
    content: str

    # === Извлеченные данные ===
    entities: List[Dict[str, Any]]  # EntityNode нельзя сериализовать напрямую
    para_suggestion: Optional[tuple]  # (type, confidence)
    container_suggestions: Optional[List[Dict]]

    # === Clarifications ===
    pending_clarifications: List[Dict]
    current_clarification: Optional[Dict]
    user_response: Optional[Dict]

    # === User Check Status ===
    para_classification_check: Optional[Dict]
    container_assignment_check: Optional[Dict]

    # === Настройки ===
    validate_attributes: bool
    skip_low_priority: bool

    # === Метаданные ===
    processing_started_at: str
    last_updated_at: str


# ============================================================================
# 5. HELPER FUNCTIONS
# ============================================================================

ENTITY_PRIORITY = {
    'Project': 1,
    'Area': 1,
    'Resource': 1,
    'Person': 2,
    'Organization': 2,
    'Decision': 3,
    'Task': 3,
    'Idea': 4,
    'Source': 4,
    'Question': 5
}


def should_auto_confirm(entity_type: str, confidence: float) -> bool:
    """
    Определяет нужно ли автоматически подтвердить сущность.

    Args:
        entity_type: Тип сущности (Person, Organization и т.д.)
        confidence: Уверенность системы (0.0-1.0)

    Returns:
        True если нужно автоподтверждение
    """
    priority = ENTITY_PRIORITY.get(entity_type, 5)

    # Очень высокая уверенность + низкий приоритет
    if confidence > 0.95 and priority >= 4:
        return True

    # Высокая уверенность + средний приоритет
    if confidence > 0.90 and priority >= 3:
        return True

    return False


def calculate_clarification_priority(clarification: Dict) -> float:
    """
    Рассчитывает приоритет вопроса для сортировки.

    Args:
        clarification: Словарь с данными вопроса

    Returns:
        Числовой приоритет (меньше = важнее)
    """
    level_weight = {
        "para_classification": 1,
        "container_assignment": 2,
        "entity": 10,
        "attribute": 20
    }

    score = level_weight.get(clarification.get("level"), 100)

    # Низкая уверенность → выше приоритет
    confidence = clarification.get("confidence", 0.5)
    score += (1.0 - confidence) * 10

    # Priority внутри уровня (для L3)
    if clarification.get("level") == "entity":
        entity_priority = ENTITY_PRIORITY.get(clarification.get("entity_type"), 5)
        score += entity_priority

    return score


# ============================================================================
# 6. EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    # === Пример 1: Создание UserCheckStatus ===
    check = UserCheckStatus(
        status="confirmed",
        confirmation_level="entity",
        confidence=0.85,
        user_action="confirm",
        system_suggestion="Person: John Smith"
    )
    print("UserCheckStatus:", check.model_dump_json(indent=2))

    # === Пример 2: Создание FieldModification ===
    mod = FieldModification(
        field_name="name",
        original_value="John",
        new_value="John Smith"
    )
    print("\nFieldModification:", mod.model_dump_json(indent=2))

    # === Пример 3: Создание Project ===
    project = Project(
        name="Q4 Marketing Campaign",
        status="active",
        deadline=date(2024, 12, 31),
        goal="Increase signups by 20%"
    )
    print("\nProject:", project.model_dump_json(indent=2))

    # === Пример 4: PARA Classification Check ===
    para_check = PARAClassificationCheck(
        original_suggestion="Project",
        user_choice="Area",
        confidence=0.70,
        status="pending"
    )
    print("\nPARAClassificationCheck:", para_check.model_dump_json(indent=2))
    print("Changed:", para_check.changed)  # True

    # === Пример 5: Auto-confirm логика ===
    print("\n=== Auto-confirm Logic ===")
    print(f"Source (0.96): {should_auto_confirm('Source', 0.96)}")  # True
    print(f"Person (0.85): {should_auto_confirm('Person', 0.85)}")  # False
    print(f"Task (0.92): {should_auto_confirm('Task', 0.92)}")     # True

    # === Пример 6: Приоритизация ===
    clarifications = [
        {"level": "entity", "entity_type": "Source", "confidence": 0.96},
        {"level": "para_classification", "confidence": 0.70},
        {"level": "entity", "entity_type": "Person", "confidence": 0.60},
        {"level": "container_assignment", "confidence": 0.80}
    ]

    sorted_clarifications = sorted(clarifications, key=calculate_clarification_priority)
    print("\n=== Sorted Clarifications ===")
    for c in sorted_clarifications:
        priority = calculate_clarification_priority(c)
        print(f"{c['level']} (priority: {priority:.1f})")
