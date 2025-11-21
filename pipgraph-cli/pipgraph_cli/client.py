"""WebSocket and REST client for PipGraph backend API."""

import asyncio
import json
from typing import Optional, Callable, Any
from dataclasses import dataclass

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
except ImportError:
    raise ImportError("websockets library not installed. Run: pip install websockets")

try:
    import httpx
except ImportError:
    raise ImportError("httpx library not installed. Run: pip install httpx")


@dataclass
class NotePayload:
    """Data model for note processing."""
    file_path: str
    content: str

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "content": self.content
        }


class PipGraphClient:
    """Client for interacting with PipGraph backend WebSocket and REST API."""

    def __init__(self, backend_url: str = "ws://localhost:8000"):
        """
        Initialize PipGraph client.

        Args:
            backend_url: Base URL of backend server (without /api/v1 prefix)
        """
        self.backend_url = backend_url.rstrip("/")
        self.ws_endpoint = f"{self.backend_url}/api/v1/ws/notes/process"
        # Convert WebSocket URL to HTTP for REST endpoints
        self.http_base = self.backend_url.replace("ws://", "http://").replace("wss://", "https://")

    async def process_note(
        self,
        note: NotePayload,
        on_status: Optional[Callable[[str, str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> Optional[dict]:
        """
        Send note to backend for processing via WebSocket.

        Args:
            note: Note payload with file_path and content
            on_status: Callback for status updates (status, message)
            on_error: Callback for errors (error_message)

        Returns:
            Processed result data or None if error occurred

        Raises:
            ConnectionError: If cannot connect to backend
            TimeoutError: If connection timeout
        """
        try:
            async with websockets.connect(
                self.ws_endpoint,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10,
            ) as websocket:
                # Send note payload
                await websocket.send(json.dumps(note.to_dict()))

                # Receive responses until done or error
                while True:
                    try:
                        response_raw = await asyncio.wait_for(
                            websocket.recv(),
                            timeout=300  # 5 minutes for LLM processing
                        )
                        response = json.loads(response_raw)

                        status = response.get("status")
                        message = response.get("message", "")

                        if status == "processing":
                            if on_status:
                                on_status("processing", message)

                        elif status == "done":
                            if on_status:
                                on_status("done", "Processing completed successfully")
                            return response.get("data")

                        elif status == "error":
                            error_msg = message or "Unknown error occurred"
                            if on_error:
                                on_error(error_msg)
                            return None

                        else:
                            # Unknown status, just log it
                            if on_status:
                                on_status(status, message)

                    except asyncio.TimeoutError:
                        error_msg = "Timeout waiting for backend response (5 min)"
                        if on_error:
                            on_error(error_msg)
                        raise TimeoutError(error_msg)

        except websockets.exceptions.WebSocketException as e:
            error_msg = f"WebSocket error: {e}"
            if on_error:
                on_error(error_msg)
            raise ConnectionError(error_msg)

        except ConnectionRefusedError:
            error_msg = f"Cannot connect to backend at {self.ws_endpoint}"
            if on_error:
                on_error(error_msg)
            raise ConnectionError(error_msg)

        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            if on_error:
                on_error(error_msg)
            raise

    # ========================================================================
    # REST API Methods for Workflow Management
    # ========================================================================

    async def start_workflow(self, file_path: str, content: str) -> dict:
        """
        Start a new workflow for note processing.

        Args:
            file_path: Path to the note file
            content: Content of the note

        Returns:
            dict with workflow_id, status, file_path

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.http_base}/api/v1/workflow/start",
                json={"file_path": file_path, "content": content}
            )
            response.raise_for_status()
            return response.json()

    async def get_workflow_status(self, workflow_id: str) -> dict:
        """
        Get current status of a workflow.

        Args:
            workflow_id: Workflow identifier

        Returns:
            dict with workflow_id, status, pending_question, etc.

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.http_base}/api/v1/workflow/{workflow_id}/status"
            )
            response.raise_for_status()
            return response.json()

    async def resume_workflow(self, workflow_id: str, answer: dict) -> dict:
        """
        Resume a workflow with user's answer.

        Args:
            workflow_id: Workflow identifier
            answer: User's answer to the pending question

        Returns:
            dict with updated status, next_question, etc.

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        async with httpx.AsyncClient(timeout=300.0) as client:  # 5 min for LLM
            response = await client.post(
                f"{self.http_base}/api/v1/workflow/{workflow_id}/resume",
                json={"answer": answer}
            )
            response.raise_for_status()
            return response.json()

    async def get_suggestions(self, workflow_id: str) -> dict:
        """
        Get suggestions for a workflow.

        Args:
            workflow_id: Workflow identifier

        Returns:
            dict with workflow_id and list of suggestions

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.http_base}/api/v1/workflow/{workflow_id}/suggestions"
            )
            response.raise_for_status()
            return response.json()

    async def submit_decision(
        self,
        suggestion_id: str,
        action: str,
        modified_value: Optional[str] = None,
        custom_container_name: Optional[str] = None
    ) -> dict:
        """
        Submit a decision on a suggestion.

        Args:
            suggestion_id: Suggestion identifier
            action: Decision action (confirm, dismiss, modify, create_custom)
            modified_value: New value for 'modify' action
            custom_container_name: Name for 'create_custom' action

        Returns:
            dict with success, workflow_id, cascade_applied

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        payload = {"action": action}
        if modified_value:
            payload["modified_value"] = modified_value
        if custom_container_name:
            payload["custom_container_name"] = custom_container_name

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.http_base}/api/v1/suggestion/{suggestion_id}/decision",
                json=payload
            )
            response.raise_for_status()
            return response.json()

    async def get_inbox(self) -> dict:
        """
        Get all pending suggestions from inbox.

        Returns:
            dict with suggestions list and total_count

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.http_base}/api/v1/inbox/suggestions"
            )
            response.raise_for_status()
            return response.json()


async def test_connection(backend_url: str = "ws://localhost:8000") -> bool:
    """
    Test connection to backend server.

    Args:
        backend_url: Backend WebSocket URL

    Returns:
        True if connection successful, False otherwise
    """
    try:
        client = PipGraphClient(backend_url)
        # Try to connect briefly
        async with websockets.connect(
            client.ws_endpoint,
            ping_interval=None,
            close_timeout=2,
        ):
            return True
    except Exception:
        return False
