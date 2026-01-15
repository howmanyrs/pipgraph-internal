"""REST client for PipGraph backend API."""

from typing import Optional, Dict, Any

try:
    import httpx
except ImportError:
    raise ImportError("httpx library not installed. Run: pip install httpx")


class PipGraphClient:
    """REST client for PipGraph backend API."""

    def __init__(self, backend_url: str = "http://localhost:8000"):
        """
        Initialize PipGraph client.

        Args:
            backend_url: Base URL of backend server (without /api/v1 prefix)
        """
        # Support both http:// and legacy ws:// URLs
        self.http_base = backend_url.rstrip("/").replace("ws://", "http://").replace("wss://", "https://")

    async def start_workflow(self, file_path: str, content: str) -> Dict[str, Any]:
        """
        Start or restart a workflow for note processing.

        Args:
            file_path: Path to the note file (acts as unique ID)
            content: Content of the note

        Returns:
            dict with file_path, status

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

    async def get_workflow_status(self, file_path: str) -> Dict[str, Any]:
        """
        Get current status of a workflow by file path.

        Args:
            file_path: Path to the note file

        Returns:
            dict with file_path, status, pending_question, etc.

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.http_base}/api/v1/workflow/status",
                params={"file_path": file_path}
            )
            response.raise_for_status()
            return response.json()

    async def resume_workflow(self, file_path: str, answer: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resume a workflow with user's answer.

        Args:
            file_path: Path to the note file (identifies the workflow)
            answer: User's answer to the pending question (suggestion_id, action, etc.)

        Returns:
            dict with updated status, next_question, cascade_applied, etc.

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        async with httpx.AsyncClient(timeout=300.0) as client:  # 5 min for LLM processing
            response = await client.post(
                f"{self.http_base}/api/v1/workflow/resume",
                json={
                    "file_path": file_path,
                    "answer": answer
                }
            )
            response.raise_for_status()
            return response.json()

    async def get_suggestions(self, file_path: str) -> Dict[str, Any]:
        """
        Get suggestions for a specific note.

        Args:
            file_path: Path to the note file

        Returns:
            dict with file_path and list of suggestions

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.http_base}/api/v1/suggestions",
                params={"file_path": file_path}
            )
            response.raise_for_status()
            return response.json()

    async def submit_decision(
        self,
        suggestion_id: str,
        action: str,
        modified_value: Optional[str] = None,
        custom_container_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Submit a decision on a suggestion directly.
        (Usually called via resume_workflow in the CLI loop, but available for direct API usage).

        Args:
            suggestion_id: Suggestion identifier
            action: Decision action (confirm, dismiss, modify, create_custom)
            modified_value: New value for 'modify' action
            custom_container_name: Name for 'create_custom' action

        Returns:
            dict with success, file_path, cascade_applied

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

    async def get_inbox(self) -> Dict[str, Any]:
        """
        Get all pending suggestions from inbox.

        Returns:
            dict with suggestions list (containing note_path) and total_count

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.http_base}/api/v1/inbox/suggestions"
            )
            response.raise_for_status()
            return response.json()


async def test_connection(backend_url: str = "http://localhost:8000") -> bool:
    """
    Test connection to backend server.

    Args:
        backend_url: Backend HTTP URL

    Returns:
        True if connection successful, False otherwise
    """
    try:
        # Convert ws:// to http:// if needed (for backwards compatibility)
        http_url = backend_url.replace("ws://", "http://").replace("wss://", "https://")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{http_url}/docs") # Check docs or health if available
            return response.status_code == 200
    except Exception:
        return False