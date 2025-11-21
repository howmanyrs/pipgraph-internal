"""
Tests for workflow API endpoints.

Tests cover:
- POST /workflow/start
- GET /workflow/{id}/status
- POST /workflow/{id}/resume
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from app.api.main import app


@pytest.fixture
def client():
    """Provide test client for API."""
    return TestClient(app)


@pytest.fixture
def mock_workflow_state():
    """Mock workflow state returned by LangGraph."""
    return {
        "status": "waiting_user",
        "file_path": "test/note.md",
        "pending_question": {
            "question_id": "q_123",
            "question_type": "entity_confirmation",
            "entity_name": "Test Entity",
            "entity_type": "Project",
            "confidence": 0.85,
        },
        "episode_uuid": None,
        "error": None,
    }


@pytest.fixture
def mock_completed_state():
    """Mock completed workflow state."""
    return {
        "status": "completed",
        "file_path": "test/note.md",
        "pending_question": None,
        "episode_uuid": "ep_abc123",
        "error": None,
        "cascade_result": {
            "applied": [
                {"suggestion_id": "sug_456", "note_path": "other.md", "confidence": 0.88}
            ],
            "skipped": [],
        },
    }


class TestWorkflowStart:
    """Tests for POST /workflow/start endpoint."""

    @pytest.mark.unit
    def test_start_workflow_success(self, client, mock_workflow_state):
        """Test successful workflow start."""
        with patch("app.api.endpoints.workflow.start_langgraph_workflow", new_callable=AsyncMock) as mock_start:
            with patch("app.api.endpoints.workflow.get_langgraph_status", new_callable=AsyncMock) as mock_status:
                mock_start.return_value = "note:test/note.md"
                mock_status.return_value = mock_workflow_state

                response = client.post(
                    "/api/v1/workflow/start",
                    json={
                        "file_path": "test/note.md",
                        "content": "# Test Note\n\nContent here.",
                    },
                )

                assert response.status_code == 200
                data = response.json()
                assert "workflow_id" in data
                assert data["workflow_id"].startswith("wf_")
                assert data["status"] == "waiting_user"
                assert data["file_path"] == "test/note.md"

    @pytest.mark.unit
    def test_start_workflow_invalid_request(self, client):
        """Test workflow start with invalid request (missing fields)."""
        response = client.post(
            "/api/v1/workflow/start",
            json={"file_path": "test.md"},  # Missing content
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.unit
    def test_start_workflow_error(self, client):
        """Test workflow start when LangGraph fails."""
        with patch("app.api.endpoints.workflow.start_langgraph_workflow", new_callable=AsyncMock) as mock_start:
            mock_start.side_effect = Exception("LangGraph error")

            response = client.post(
                "/api/v1/workflow/start",
                json={
                    "file_path": "test/note.md",
                    "content": "Content",
                },
            )

            assert response.status_code == 500
            assert "LangGraph error" in response.json()["detail"]


class TestWorkflowStatus:
    """Tests for GET /workflow/{id}/status endpoint."""

    @pytest.mark.unit
    def test_get_status_existing_workflow(self, client, mock_workflow_state):
        """Test getting status of existing workflow."""
        # First create a workflow
        with patch("app.api.endpoints.workflow.start_langgraph_workflow", new_callable=AsyncMock) as mock_start:
            with patch("app.api.endpoints.workflow.get_langgraph_status", new_callable=AsyncMock) as mock_status:
                mock_start.return_value = "note:test/note.md"
                mock_status.return_value = mock_workflow_state

                # Start workflow
                start_response = client.post(
                    "/api/v1/workflow/start",
                    json={"file_path": "test/note.md", "content": "Content"},
                )
                workflow_id = start_response.json()["workflow_id"]

                # Get status
                response = client.get(f"/api/v1/workflow/{workflow_id}/status")

                assert response.status_code == 200
                data = response.json()
                assert data["workflow_id"] == workflow_id
                assert data["status"] == "waiting_user"
                assert data["pending_question"] is not None

    @pytest.mark.unit
    def test_get_status_nonexistent_workflow(self, client):
        """Test getting status of non-existent workflow."""
        response = client.get("/api/v1/workflow/wf_nonexistent/status")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


class TestWorkflowResume:
    """Tests for POST /workflow/{id}/resume endpoint."""

    @pytest.mark.unit
    def test_resume_workflow_success(self, client, mock_workflow_state, mock_completed_state):
        """Test successful workflow resume."""
        with patch("app.api.endpoints.workflow.start_langgraph_workflow", new_callable=AsyncMock) as mock_start:
            with patch("app.api.endpoints.workflow.get_langgraph_status", new_callable=AsyncMock) as mock_status:
                with patch("app.api.endpoints.workflow.resume_langgraph_workflow", new_callable=AsyncMock) as mock_resume:
                    mock_start.return_value = "note:test/note.md"
                    mock_status.return_value = mock_workflow_state
                    mock_resume.return_value = mock_completed_state

                    # Start workflow
                    start_response = client.post(
                        "/api/v1/workflow/start",
                        json={"file_path": "test/note.md", "content": "Content"},
                    )
                    workflow_id = start_response.json()["workflow_id"]

                    # Resume workflow
                    response = client.post(
                        f"/api/v1/workflow/{workflow_id}/resume",
                        json={
                            "answer": {"question_id": "q_123", "action": "confirm"}
                        },
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert data["workflow_id"] == workflow_id
                    assert data["status"] == "completed"
                    assert data["episode_uuid"] == "ep_abc123"
                    assert len(data["cascade_applied"]) == 1

    @pytest.mark.unit
    def test_resume_nonexistent_workflow(self, client):
        """Test resuming non-existent workflow."""
        response = client.post(
            "/api/v1/workflow/wf_nonexistent/resume",
            json={"answer": {"action": "confirm"}},
        )

        assert response.status_code == 404


class TestWorkflowIdFormat:
    """Tests for workflow ID format."""

    @pytest.mark.unit
    def test_workflow_id_is_url_safe(self, client, mock_workflow_state):
        """Test that generated workflow_id is URL-safe."""
        with patch("app.api.endpoints.workflow.start_langgraph_workflow", new_callable=AsyncMock) as mock_start:
            with patch("app.api.endpoints.workflow.get_langgraph_status", new_callable=AsyncMock) as mock_status:
                mock_start.return_value = "note:test/note.md"
                mock_status.return_value = mock_workflow_state

                response = client.post(
                    "/api/v1/workflow/start",
                    json={"file_path": "test/note.md", "content": "Content"},
                )

                workflow_id = response.json()["workflow_id"]

                # Check format: wf_{hex}
                assert workflow_id.startswith("wf_")
                assert len(workflow_id) == 11  # wf_ + 8 hex chars

                # Check no special characters
                assert ":" not in workflow_id
                assert "/" not in workflow_id
                assert " " not in workflow_id
