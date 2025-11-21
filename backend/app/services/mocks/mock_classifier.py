"""
Mock L1 Classifier

Мок-реализация классификатора PARA типа заметки.
Всегда возвращает "Project" для простоты тестирования.

После проверки архитектуры заменить на реальную LLM реализацию
в app/services/llm/real_classifier.py
"""


def classify_note_para(note_content: str) -> str:
    """
    Mock L1: Классифицирует заметку по типу PARA.

    В реальной реализации будет использовать LLM для анализа контента.
    Mock версия всегда возвращает "Project".

    TODO: На будущее. Если у заметки плохо определятся принадлежность
    к para типу, возможны такие сценарии:
     - Векторизуем содержание заметки и ещем близкие узлы PARA типов.
     - Более замороченно - выделяем предварительные сущности или ключевые
       слова - находим похожие сущности в базе и смотрим к какми PARA 
       они принадлежат.

    Args:
        note_content: Текстовое содержимое заметки

    Returns:
        str: Тип PARA контейнера ("Project" | "Area" | "Resource" | "Archive")
    """
    # Mock: простая логика на основе ключевых слов (опционально)
    # Можно расширить для более реалистичного тестирования
    content_lower = note_content.lower()

    if "deadline" in content_lower or "milestone" in content_lower:
        return "Project"
    elif "responsibility" in content_lower or "ongoing" in content_lower:
        return "Area"
    elif "reference" in content_lower or "resource" in content_lower:
        return "Resource"

    # По умолчанию возвращаем Project
    return "Project"
