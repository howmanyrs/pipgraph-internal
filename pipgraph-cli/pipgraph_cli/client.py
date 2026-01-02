"""REST client for PipGraph backend API."""

from typing import Optional

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
            response = await client.get(f"{http_url}/")
            return response.status_code == 200
    except Exception:
        return False
