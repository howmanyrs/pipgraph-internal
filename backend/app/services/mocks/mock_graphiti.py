"""
Mock L3 Graphiti Entity Extraction

Мок-реализация извлечения сущностей из заметки с учётом PARA контекста.
Возвращает детерминированный список ExtractedCandidate объектов.

После проверки архитектуры заменить на реальную Graphiti интеграцию
в app/services/graphiti/real_graphiti.py

📌 Entity labels:
- Graphiti с entity_types создаёт composite labels: :Entity:Concept, :Entity:Task
- PARA контейнеры (:Project, :Area, :Resource) - это отдельные узлы, НЕ Entity
- В mock реализации используем простые labels
"""

import uuid
from typing import Any

from app.models.entity import ExtractedCandidate


def extract_entities(episodic_content: str, context: dict[str, Any]) -> list[ExtractedCandidate]:
    """
    Mock L3: Извлекает сущности из заметки с учётом контекста проекта.

    В реальной реализации будет использовать:
    - Graphiti SDK для извлечения entities
    - Контекст проекта в промпте для context-aware extraction
    - entity_types для создания composite labels

    Mock версия возвращает фиксированный набор сущностей:
    - Entity "User Authentication" (Concept)
    - Entity "Implement Login" (Task)

    Args:
        episodic_content: Текстовое содержимое заметки
        context: Словарь с информацией о контейнере:
            - id: ID контейнера (project/area/resource)
            - name: Название контейнера
            - label: Тип контейнера (Project/Area/Resource)

    Returns:
        list[ExtractedCandidate]: Список извлечённых сущностей
    """
    # Генерируем уникальные UUID для каждого вызова
    # (но можно использовать фиксированные для детерминизма в тестах)
    entity_1_uuid = f"mock-entity-{uuid.uuid4().hex[:8]}"
    entity_2_uuid = f"mock-entity-{uuid.uuid4().hex[:8]}"

    # Используем контекст в summary для демонстрации context-awareness
    context_name = context.get("name", "Unknown Context")

    return [
        ExtractedCandidate(
            uuid=entity_1_uuid,
            name="Mock Concept: User Authentication",
            labels=["Entity", "Concept"],
            summary=f"Authentication system mentioned in note (context: {context_name})"
        ),
        ExtractedCandidate(
            uuid=entity_2_uuid,
            name="Mock Task: Implement Login",
            labels=["Entity", "Task"],
            summary=f"Task to implement login feature (context: {context_name})"
        )
    ]
