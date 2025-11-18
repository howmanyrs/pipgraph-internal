"""
LangGraph Workflow для обработки заметок (MVP)

Минимальный workflow с демонстрацией interrupt/resume:
1. extract_entities - извлекает сущности через PipGraphManager
2. ask_user - задает ОДИН вопрос пользователю (INTERRUPT)
3. finalize - сохраняет результат

Архитектура:
    START → extract_entities → check_needs_question → ask_user (INTERRUPT) → finalize → END
                                      ↓
                                  (если вопросов нет)
                                      ↓
                                   finalize → END
"""

import logging
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.aiosqlite import AsyncSqliteSaver
from langgraph.types import interrupt

from app.models.workflow_state import (
    NoteWorkflowState,
    ClarificationQuestion,
    serialize_entity,
)
from app.services.llm_graphiti_client import get_graphiti
from app.services.pipgraph_manager import PipGraphManager
from graphiti_core.nodes import EpisodeType

logger = logging.getLogger(__name__)


# ============================================================================
# Workflow Nodes
# ============================================================================

async def extract_entities_node(state: NoteWorkflowState) -> dict:
    """
    Узел 1: Извлечение сущностей через PipGraphManager.

    Использует существующий PipGraphManager.process_note() для
    извлечения сущностей из текста заметки.

    Returns:
        dict с полями:
        - entities: List[Dict] - сериализованные сущности
        - episode_uuid: str - UUID созданного эпизода
        - needs_confirmation: bool - нужно ли подтверждение
        - status: str - "processing"
    """
    logger.info(f"[extract_entities_node] Processing: {state['file_path']}")

    try:
        # Создаем PipGraphManager
        graphiti = await get_graphiti()
        pipgraph = PipGraphManager(graphiti)

        # Обрабатываем заметку (существующая логика)
        result = await pipgraph.process_note(
            name=state["file_path"],
            episode_body=state["content"],
            source=EpisodeType.text,
            source_description=f"Obsidian note from {state['file_path']}",
            reference_time=datetime.now(timezone.utc),
        )

        # Сериализуем сущности для хранения в state
        serialized_entities = [serialize_entity(entity) for entity in result.nodes]

        logger.info(f"[extract_entities_node] Extracted {len(result.nodes)} entities")

        # Для MVP: если есть хотя бы одна сущность → спрашиваем
        needs_confirmation = len(result.nodes) > 0

        return {
            "entities": serialized_entities,
            "episode_uuid": result.episode.uuid,
            "needs_confirmation": needs_confirmation,
            "status": "processing",
        }

    except Exception as e:
        logger.error(f"[extract_entities_node] Error: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "entities": [],
            "needs_confirmation": False,
        }


async def ask_user_node(state: NoteWorkflowState) -> dict:
    """
    Узел 2: Запрос подтверждения у пользователя (INTERRUPT).

    MVP версия: задаем вопрос про ПЕРВУЮ сущность.
    В будущем: приоритизация, множественные вопросы (L1, L2, L3).

    Returns:
        dict с полями:
        - pending_question: ClarificationQuestion - вопрос пользователю
        - user_answer: Dict - ответ пользователя (заполняется после resume)
        - status: str - "waiting_user"
    """
    logger.info("[ask_user_node] Preparing question for user")

    # Берем первую сущность для демонстрации
    first_entity = state["entities"][0] if state["entities"] else None

    if not first_entity:
        logger.info("[ask_user_node] No entities to confirm, skipping")
        return {
            "pending_question": None,
            "user_answer": {"action": "skip"},
            "status": "processing",
        }

    # Формируем вопрос
    question = ClarificationQuestion(
        question_id=str(uuid4()),
        question_type="entity_confirmation",
        question_text=f"Подтвердите сущность: {first_entity['name']} ({first_entity['labels'][0]})?",
        entity_uuid=first_entity["uuid"],
        entity_name=first_entity["name"],
        entity_type=first_entity["labels"][0],
        suggested_action="confirm",
        confidence=0.85,  # TODO: получать из LLM
    )

    logger.info(f"[ask_user_node] Interrupting with question: {question.question_text}")

    # === INTERRUPT: workflow останавливается здесь ===
    # Возвращаем вопрос клиенту и ждем ответа
    user_answer = interrupt(question.model_dump())

    logger.info(f"[ask_user_node] Received answer: {user_answer}")

    return {
        "pending_question": question.model_dump(),
        "user_answer": user_answer,
        "status": "processing",
    }


async def finalize_node(state: NoteWorkflowState) -> dict:
    """
    Узел 3: Финализация обработки.

    В MVP: просто логируем результат и завершаем.
    В будущем: сохранение UserCheckStatus nodes, обновление графа.

    Returns:
        dict с полями:
        - processing_completed_at: str - ISO timestamp
        - status: str - "completed"
    """
    logger.info("[finalize_node] Finalizing workflow")

    user_action = state.get("user_answer", {}).get("action", "unknown")
    logger.info(f"[finalize_node] User action: {user_action}")

    # TODO: Сохранить UserCheckStatus node в Neo4j
    # TODO: Обновить сущность, если action = "modify"

    completed_at = datetime.now(timezone.utc).isoformat()

    logger.info(f"[finalize_node] Workflow completed for {state['file_path']}")

    return {
        "processing_completed_at": completed_at,
        "status": "completed",
    }


# ============================================================================
# Conditional Logic
# ============================================================================

def should_ask_user(state: NoteWorkflowState) -> Literal["ask_user", "finalize"]:
    """
    Условная логика: нужно ли спрашивать пользователя?

    Returns:
        "ask_user" - если needs_confirmation = True
        "finalize" - если вопросов нет или произошла ошибка
    """
    if state.get("status") == "error":
        logger.info("[should_ask_user] Error status, skipping to finalize")
        return "finalize"

    if state.get("needs_confirmation", False):
        logger.info("[should_ask_user] Confirmation needed, going to ask_user")
        return "ask_user"

    logger.info("[should_ask_user] No confirmation needed, going to finalize")
    return "finalize"


# ============================================================================
# Workflow Graph Construction
# ============================================================================

def create_workflow() -> StateGraph:
    """
    Создание LangGraph workflow.

    Структура:
        START → extract_entities → should_ask_user? → ask_user (INTERRUPT) → finalize → END
                                          ↓
                                      (no questions)
                                          ↓
                                      finalize → END
    """
    workflow = StateGraph(NoteWorkflowState)

    # Добавляем узлы
    workflow.add_node("extract_entities", extract_entities_node)
    workflow.add_node("ask_user", ask_user_node)
    workflow.add_node("finalize", finalize_node)

    # Начальная точка
    workflow.set_entry_point("extract_entities")

    # Условная связь: extract → ask_user или finalize
    workflow.add_conditional_edges(
        "extract_entities",
        should_ask_user,
        {
            "ask_user": "ask_user",
            "finalize": "finalize",
        },
    )

    # ask_user → finalize
    workflow.add_edge("ask_user", "finalize")

    # finalize → END
    workflow.add_edge("finalize", END)

    return workflow


# ============================================================================
# Compiled Application
# ============================================================================

# Создаем checkpointer для сохранения состояния
# Используем файл для персистентности (состояние сохраняется между перезапусками)
_checkpointer = AsyncSqliteSaver.from_conn_string("workflow_checkpoints.db")

# Компилируем workflow
_workflow = create_workflow()
app = _workflow.compile(checkpointer=_checkpointer)


# ============================================================================
# Helper Functions
# ============================================================================

async def start_workflow(file_path: str, content: str) -> str:
    """
    Запуск нового workflow для заметки.

    Args:
        file_path: Путь к заметке
        content: Содержимое заметки

    Returns:
        thread_id: ID потока для отслеживания
    """
    thread_id = f"note:{file_path}"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state: NoteWorkflowState = {
        "file_path": file_path,
        "content": content,
        "entities": [],
        "needs_confirmation": False,
        "pending_question": None,
        "user_answer": None,
        "processing_started_at": datetime.now(timezone.utc).isoformat(),
        "status": "processing",
        "episode_uuid": "",
    }

    logger.info(f"[start_workflow] Starting workflow for {file_path}")

    # Запускаем workflow (до первого interrupt)
    await app.ainvoke(initial_state, config)

    return thread_id


async def resume_workflow(thread_id: str, user_answer: dict) -> dict:
    """
    Возобновление workflow после ответа пользователя.

    Args:
        thread_id: ID потока
        user_answer: Ответ пользователя (dict)

    Returns:
        dict с финальным состоянием
    """
    from langgraph.types import Command

    config = {"configurable": {"thread_id": thread_id}}

    logger.info(f"[resume_workflow] Resuming workflow {thread_id}")

    # Возобновляем workflow с ответом пользователя
    result = await app.ainvoke(Command(resume=user_answer), config)

    return result


async def get_workflow_status(thread_id: str) -> dict:
    """
    Получить текущее состояние workflow.

    Args:
        thread_id: ID потока

    Returns:
        dict с текущим состоянием
    """
    config = {"configurable": {"thread_id": thread_id}}

    # Получаем последнее состояние из checkpointer
    state = await app.aget_state(config)

    return state.values if state else {}
