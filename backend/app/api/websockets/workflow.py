"""
WebSocket endpoint для LangGraph workflow

Обеспечивает real-time коммуникацию между клиентом и workflow:
1. Клиент отправляет заметку для обработки
2. Сервер запускает workflow
3. При interrupt сервер отправляет вопрос клиенту
4. Клиент отвечает
5. Workflow возобновляется и завершается

Протокол:
- Клиент → Сервер: {"type": "start", "file_path": "...", "content": "..."}
- Сервер → Клиент: {"type": "question", "data": {...}}
- Клиент → Сервер: {"type": "answer", "thread_id": "...", "data": {...}}
- Сервер → Клиент: {"type": "completed", "data": {...}}
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError

from app.services.note_workflow import (
    start_workflow,
    resume_workflow,
    get_workflow_status,
    app as workflow_app,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# WebSocket Message Models
# ============================================================================

class StartWorkflowMessage(BaseModel):
    """Сообщение для запуска workflow"""
    type: str = "start"
    file_path: str
    content: str


class AnswerMessage(BaseModel):
    """Сообщение с ответом пользователя"""
    type: str = "answer"
    thread_id: str
    data: Dict[str, Any]  # UserAnswer


class StatusMessage(BaseModel):
    """Запрос статуса workflow"""
    type: str = "status"
    thread_id: str


# ============================================================================
# WebSocket Endpoint
# ============================================================================

@router.websocket("/ws/workflow")
async def workflow_websocket(websocket: WebSocket):
    """
    WebSocket endpoint для workflow обработки заметок.

    Поддерживает:
    - start: Запуск нового workflow
    - answer: Ответ на вопрос (resume workflow)
    - status: Получить текущий статус workflow

    Пример использования (JavaScript):
        const ws = new WebSocket("ws://localhost:8000/ws/workflow");

        // Запустить обработку
        ws.send(JSON.stringify({
            type: "start",
            file_path: "meetings/sync.md",
            content: "# Meeting with John Smith..."
        }));

        // Получить вопрос
        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            if (msg.type === "question") {
                // Показать вопрос пользователю
                const answer = { action: "confirm" };
                // Отправить ответ
                ws.send(JSON.stringify({
                    type: "answer",
                    thread_id: msg.thread_id,
                    data: answer
                }));
            }
        };
    """
    await websocket.accept()
    logger.info("[WebSocket] Client connected")

    try:
        async for message in websocket.iter_json():
            msg_type = message.get("type")
            logger.info(f"[WebSocket] Received message type: {msg_type}")

            # ================================================================
            # START: Запуск нового workflow
            # ================================================================
            if msg_type == "start":
                try:
                    start_msg = StartWorkflowMessage(**message)
                    logger.info(f"[WebSocket] Starting workflow for {start_msg.file_path}")

                    # Запускаем workflow
                    thread_id = await start_workflow(
                        file_path=start_msg.file_path,
                        content=start_msg.content,
                    )

                    # Проверяем состояние (workflow может сразу завершиться или прерваться)
                    state = await get_workflow_status(thread_id)

                    # Если есть вопрос (status = "waiting_user" или pending_question)
                    if state.get("pending_question"):
                        logger.info("[WebSocket] Workflow interrupted, sending question")
                        await websocket.send_json({
                            "type": "question",
                            "thread_id": thread_id,
                            "data": state["pending_question"],
                        })

                    # Если workflow завершился сразу (без вопросов)
                    elif state.get("status") == "completed":
                        logger.info("[WebSocket] Workflow completed without questions")
                        await websocket.send_json({
                            "type": "completed",
                            "thread_id": thread_id,
                            "data": {
                                "episode_uuid": state.get("episode_uuid"),
                                "entities": state.get("entities", []),
                            },
                        })

                    # Если произошла ошибка
                    elif state.get("status") == "error":
                        logger.error(f"[WebSocket] Workflow error: {state.get('error')}")
                        await websocket.send_json({
                            "type": "error",
                            "thread_id": thread_id,
                            "error": state.get("error"),
                        })

                except ValidationError as e:
                    logger.error(f"[WebSocket] Invalid message format: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "error": f"Invalid message format: {str(e)}",
                    })

                except Exception as e:
                    logger.error(f"[WebSocket] Error starting workflow: {e}", exc_info=True)
                    await websocket.send_json({
                        "type": "error",
                        "error": str(e),
                    })

            # ================================================================
            # ANSWER: Ответ на вопрос (resume workflow)
            # ================================================================
            elif msg_type == "answer":
                try:
                    answer_msg = AnswerMessage(**message)
                    logger.info(f"[WebSocket] Resuming workflow {answer_msg.thread_id}")

                    # Возобновляем workflow с ответом пользователя
                    final_state = await resume_workflow(
                        thread_id=answer_msg.thread_id,
                        user_answer=answer_msg.data,
                    )

                    # Проверяем, есть ли еще вопросы или workflow завершился
                    if final_state.get("pending_question") and final_state.get("status") != "completed":
                        logger.info("[WebSocket] Workflow has another question")
                        await websocket.send_json({
                            "type": "question",
                            "thread_id": answer_msg.thread_id,
                            "data": final_state["pending_question"],
                        })

                    elif final_state.get("status") == "completed":
                        logger.info("[WebSocket] Workflow completed")
                        await websocket.send_json({
                            "type": "completed",
                            "thread_id": answer_msg.thread_id,
                            "data": {
                                "episode_uuid": final_state.get("episode_uuid"),
                                "entities": final_state.get("entities", []),
                                "user_answer": final_state.get("user_answer"),
                            },
                        })

                    elif final_state.get("status") == "error":
                        logger.error(f"[WebSocket] Workflow error: {final_state.get('error')}")
                        await websocket.send_json({
                            "type": "error",
                            "thread_id": answer_msg.thread_id,
                            "error": final_state.get("error"),
                        })

                except ValidationError as e:
                    logger.error(f"[WebSocket] Invalid message format: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "error": f"Invalid message format: {str(e)}",
                    })

                except Exception as e:
                    logger.error(f"[WebSocket] Error resuming workflow: {e}", exc_info=True)
                    await websocket.send_json({
                        "type": "error",
                        "error": str(e),
                    })

            # ================================================================
            # STATUS: Получить текущий статус workflow
            # ================================================================
            elif msg_type == "status":
                try:
                    status_msg = StatusMessage(**message)
                    logger.info(f"[WebSocket] Getting status for {status_msg.thread_id}")

                    state = await get_workflow_status(status_msg.thread_id)

                    await websocket.send_json({
                        "type": "status",
                        "thread_id": status_msg.thread_id,
                        "data": state,
                    })

                except ValidationError as e:
                    logger.error(f"[WebSocket] Invalid message format: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "error": f"Invalid message format: {str(e)}",
                    })

                except Exception as e:
                    logger.error(f"[WebSocket] Error getting status: {e}", exc_info=True)
                    await websocket.send_json({
                        "type": "error",
                        "error": str(e),
                    })

            # ================================================================
            # Unknown message type
            # ================================================================
            else:
                logger.warning(f"[WebSocket] Unknown message type: {msg_type}")
                await websocket.send_json({
                    "type": "error",
                    "error": f"Unknown message type: {msg_type}",
                })

    except WebSocketDisconnect:
        logger.info("[WebSocket] Client disconnected")

    except Exception as e:
        logger.error(f"[WebSocket] Unexpected error: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "error": str(e),
            })
        except:
            pass  # Connection may be closed
