#!/usr/bin/env python3
"""
Тестовый скрипт для проверки LangGraph workflow MVP

Демонстрирует:
1. Запуск workflow через REST API
2. Получение вопроса от системы (interrupt)
3. Ответ пользователя
4. Завершение workflow

Использование:
    python test_workflow_mvp.py
"""

import asyncio
import httpx
from typing import Dict, Any


BASE_URL = "http://localhost:8000/api/v1"


async def test_workflow_rest_api():
    """
    Тест workflow через REST API.

    Этапы:
    1. POST /notes/workflow/start - запускаем обработку
    2. Получаем pending_question (если есть)
    3. POST /notes/workflow/resume - отвечаем на вопрос
    4. GET /notes/workflow/status - проверяем статус
    """
    print("=" * 80)
    print("Testing LangGraph Workflow MVP via REST API")
    print("=" * 80)

    async with httpx.AsyncClient(timeout=60.0) as client:

        # ====================================================================
        # Шаг 1: Запуск workflow
        # ====================================================================
        print("\n[1] Starting workflow...")

        start_response = await client.post(
            f"{BASE_URL}/notes/workflow/start",
            json={
                "file_path": "test/workflow_mvp.md",
                "content": """# Test Note for Workflow MVP

This is a test note to demonstrate LangGraph workflow with interrupt/resume.

I met with John Smith yesterday to discuss the Q4 Marketing Campaign project.
We also talked about reaching out to Sarah Johnson from TechCorp.
"""
            }
        )

        if start_response.status_code != 200:
            print(f"❌ Error: {start_response.status_code}")
            print(start_response.text)
            return

        start_data = start_response.json()
        thread_id = start_data["thread_id"]

        print(f"✅ Workflow started!")
        print(f"   Thread ID: {thread_id}")
        print(f"   Status: {start_data['status']}")

        # ====================================================================
        # Шаг 2: Проверяем, есть ли вопрос
        # ====================================================================
        if start_data.get("pending_question"):
            question = start_data["pending_question"]
            print(f"\n[2] Question received:")
            print(f"   Type: {question.get('question_type')}")
            print(f"   Text: {question.get('question_text')}")
            print(f"   Entity: {question.get('entity_name')} ({question.get('entity_type')})")
            print(f"   Suggested action: {question.get('suggested_action')}")
            print(f"   Confidence: {question.get('confidence')}")

            # ================================================================
            # Шаг 3: Отвечаем на вопрос
            # ================================================================
            print(f"\n[3] Sending answer...")

            # Симулируем ответ пользователя: confirm
            answer = {
                "question_id": question.get("question_id"),
                "action": "confirm",  # или "modify", "reject", "skip"
            }

            resume_response = await client.post(
                f"{BASE_URL}/notes/workflow/resume",
                json={
                    "thread_id": thread_id,
                    "answer": answer
                }
            )

            if resume_response.status_code != 200:
                print(f"❌ Error: {resume_response.status_code}")
                print(resume_response.text)
                return

            resume_data = resume_response.json()

            print(f"✅ Answer sent!")
            print(f"   Status: {resume_data['status']}")

            if resume_data.get("episode_uuid"):
                print(f"   Episode UUID: {resume_data['episode_uuid']}")

            # ================================================================
            # Шаг 4: Проверяем финальный статус
            # ================================================================
            print(f"\n[4] Checking final status...")

            status_response = await client.get(
                f"{BASE_URL}/notes/workflow/status/{thread_id}"
            )

            if status_response.status_code != 200:
                print(f"❌ Error: {status_response.status_code}")
                print(status_response.text)
                return

            status_data = status_response.json()

            print(f"✅ Final status:")
            print(f"   Status: {status_data['status']}")
            print(f"   Episode UUID: {status_data.get('episode_uuid')}")

            if status_data.get("error"):
                print(f"   Error: {status_data['error']}")

        else:
            print(f"\n[2] No questions - workflow completed immediately")
            print(f"   Episode UUID: {start_data.get('episode_uuid')}")

    print("\n" + "=" * 80)
    print("✅ Test completed successfully!")
    print("=" * 80)


async def test_workflow_websocket():
    """
    Тест workflow через WebSocket.

    TODO: Реализовать для полной демонстрации
    """
    print("\n⚠️  WebSocket test not implemented yet")
    print("   Use REST API test for now")


if __name__ == "__main__":
    print("LangGraph Workflow MVP Test\n")

    print("Testing via REST API...")
    asyncio.run(test_workflow_rest_api())

    # print("\nTesting via WebSocket...")
    # asyncio.run(test_workflow_websocket())
