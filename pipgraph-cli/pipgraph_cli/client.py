"""WebSocket client for PipGraph backend API."""

import asyncio
import json
from typing import Optional, Callable, Any
from dataclasses import dataclass

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
except ImportError:
    raise ImportError("websockets library not installed. Run: pip install websockets")


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
    """Client for interacting with PipGraph backend WebSocket API."""

    def __init__(self, backend_url: str = "ws://localhost:8000"):
        """
        Initialize PipGraph client.

        Args:
            backend_url: Base URL of backend server (without /api/v1 prefix)
        """
        self.backend_url = backend_url.rstrip("/")
        self.ws_endpoint = f"{self.backend_url}/api/v1/ws/notes/process"

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
