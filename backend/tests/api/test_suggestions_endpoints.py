"""
Tests for suggestions API endpoints.

Tests cover:
- GET /workflow/{id}/suggestions
- POST /suggestion/{id}/decision
- GET /inbox/suggestions
- GET /inbox/count
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
def mock_workflow_state_with_suggestion():
    """Mock workflow state with pending suggestion."""
    return {
        "status": "waiting_user",
        "file_path": "test/note.md",
        "pending_question": {
            "question_id": "q_123",
            "question_type": "para_link",
            "entity_name": "Project Alpha",
            "entity_type": "Project",
            "confidence": 0.92,
            "alternatives": [
                {"container_name": "Project Beta", "confidence": 0.75}
            ],
        },
        "episode_uuid": None,
        "error": None,
        "processing_started_at": "2024-01-15T10:30:00+00:00",
    }


@pytest.fixture
def mock_completed_state():
    """Mock completed workflow state after decision."""
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


class TestGetSuggestions:
    """Tests for GET /workflow/{id}/suggestions endpoint."""

    @pytest.mark.unit
    def test_get_suggestions_with_pending(self, client, mock_workflow_state_with_suggestion):
        """Test getting suggestions when there's a pending question."""
        with patch("app.api.endpoints.workflow.start_langgraph_workflow", new_callable=AsyncMock) as mock_start:
            with patch("app.api.endpoints.workflow.get_langgraph_status", new_callable=AsyncMock) as mock_status:
                with patch("app.api.endpoints.suggestions.get_langgraph_status", new_callable=AsyncMock) as mock_sug_status:
                    mock_start.return_value = "note:test/note.md"
                    mock_status.return_value = mock_workflow_state_with_suggestion
                    mock_sug_status.return_value = mock_workflow_state_with_suggestion

                    # Start workflow
                    start_response = client.post(
                        "/api/v1/workflow/start",
                        json={"file_path": "test/note.md", "content": "Content"},
                    )
                    workflow_id = start_response.json()["workflow_id"]

                    # Get suggestions
                    response = client.get(f"/api/v1/workflow/{workflow_id}/suggestions")

                    assert response.status_code == 200
                    data = response.json()
                    assert data["workflow_id"] == workflow_id
                    assert len(data["suggestions"]) == 1

                    suggestion = data["suggestions"][0]
                    assert suggestion["suggestion_id"] == "q_123"
                    assert suggestion["suggestion_type"] == "para_link"
                    assert suggestion["container_name"] == "Project Alpha"
                    assert suggestion["confidence"] == 0.92
                    assert len(suggestion["alternatives"]) == 1

    @pytest.mark.unit
    def test_get_suggestions_empty(self, client):
        """Test getting suggestions when there are none."""
        empty_state = {
            "status": "completed",
            "file_path": "test/note.md",
            "pending_question": None,
            "episode_uuid": "ep_123",
        }

        with patch("app.api.endpoints.workflow.start_langgraph_workflow", new_callable=AsyncMock) as mock_start:
            with patch("app.api.endpoints.workflow.get_langgraph_status", new_callable=AsyncMock) as mock_status:
                with patch("app.api.endpoints.suggestions.get_langgraph_status", new_callable=AsyncMock) as mock_sug_status:
                    mock_start.return_value = "note:test/note.md"
                    mock_status.return_value = empty_state
                    mock_sug_status.return_value = empty_state

                    # Start workflow
                    start_response = client.post(
                        "/api/v1/workflow/start",
                        json={"file_path": "test/note.md", "content": "Content"},
                    )
                    workflow_id = start_response.json()["workflow_id"]

                    # Get suggestions
                    response = client.get(f"/api/v1/workflow/{workflow_id}/suggestions")

                    assert response.status_code == 200
                    data = response.json()
                    assert len(data["suggestions"]) == 0


class TestSubmitDecision:
    """Tests for POST /suggestion/{id}/decision endpoint."""

    @pytest.mark.unit
    def test_submit_decision_confirm(self, client, mock_workflow_state_with_suggestion, mock_completed_state):
        """Test confirming a suggestion."""
        with patch("app.api.endpoints.workflow.start_langgraph_workflow", new_callable=AsyncMock) as mock_start:
            with patch("app.api.endpoints.workflow.get_langgraph_status", new_callable=AsyncMock) as mock_status:
                with patch("app.api.endpoints.suggestions.get_langgraph_status", new_callable=AsyncMock) as mock_sug_status:
                    with patch("app.api.endpoints.suggestions.resume_langgraph_workflow", new_callable=AsyncMock) as mock_resume:
                        mock_start.return_value = "note:test/note.md"
                        mock_status.return_value = mock_workflow_state_with_suggestion
                        mock_sug_status.return_value = mock_workflow_state_with_suggestion
                        mock_resume.return_value = mock_completed_state

                        # Start workflow
                        start_response = client.post(
                            "/api/v1/workflow/start",
                            json={"file_path": "test/note.md", "content": "Content"},
                        )

                        # Submit decision
                        response = client.post(
                            "/api/v1/suggestion/q_123/decision",
                            json={"action": "confirm"},
                        )

                        assert response.status_code == 200
                        data = response.json()
                        assert data["success"] is True
                        assert data["suggestion_id"] == "q_123"
                        assert data["action"] == "confirm"
                        assert len(data["cascade_applied"]) == 1

    @pytest.mark.unit
    def test_submit_decision_invalid_action(self, client, mock_workflow_state_with_suggestion):
        """Test submitting invalid action."""
        with patch("app.api.endpoints.workflow.start_langgraph_workflow", new_callable=AsyncMock) as mock_start:
            with patch("app.api.endpoints.workflow.get_langgraph_status", new_callable=AsyncMock) as mock_status:
                with patch("app.api.endpoints.suggestions.get_langgraph_status", new_callable=AsyncMock) as mock_sug_status:
                    mock_start.return_value = "note:test/note.md"
                    mock_status.return_value = mock_workflow_state_with_suggestion
                    mock_sug_status.return_value = mock_workflow_state_with_suggestion

                    # Start workflow
                    client.post(
                        "/api/v1/workflow/start",
                        json={"file_path": "test/note.md", "content": "Content"},
                    )

                    # Submit invalid action
                    response = client.post(
                        "/api/v1/suggestion/q_123/decision",
                        json={"action": "invalid_action"},
                    )

                    assert response.status_code == 400
                    assert "Invalid action" in response.json()["detail"]

    @pytest.mark.unit
    def test_submit_decision_nonexistent_suggestion(self, client):
        """Test decision for non-existent suggestion."""
        response = client.post(
            "/api/v1/suggestion/nonexistent/decision",
            json={"action": "confirm"},
        )

        assert response.status_code == 404

    @pytest.mark.unit
    def test_submit_decision_modify(self, client, mock_workflow_state_with_suggestion, mock_completed_state):
        """Test modifying a suggestion."""
        with patch("app.api.endpoints.workflow.start_langgraph_workflow", new_callable=AsyncMock) as mock_start:
            with patch("app.api.endpoints.workflow.get_langgraph_status", new_callable=AsyncMock) as mock_status:
                with patch("app.api.endpoints.suggestions.get_langgraph_status", new_callable=AsyncMock) as mock_sug_status:
                    with patch("app.api.endpoints.suggestions.resume_langgraph_workflow", new_callable=AsyncMock) as mock_resume:
                        mock_start.return_value = "note:test/note.md"
                        mock_status.return_value = mock_workflow_state_with_suggestion
                        mock_sug_status.return_value = mock_workflow_state_with_suggestion
                        mock_resume.return_value = mock_completed_state

                        # Start workflow
                        client.post(
                            "/api/v1/workflow/start",
                            json={"file_path": "test/note.md", "content": "Content"},
                        )

                        # Submit modify decision
                        response = client.post(
                            "/api/v1/suggestion/q_123/decision",
                            json={
                                "action": "modify",
                                "modified_value": "Project Beta",
                            },
                        )

                        assert response.status_code == 200
                        data = response.json()
                        assert data["success"] is True
                        assert data["action"] == "modify"


class TestInbox:
    """Tests for inbox endpoints."""

    @pytest.mark.unit
    def test_get_inbox_with_suggestions(self, client, mock_workflow_state_with_suggestion):
        """Test getting inbox with pending suggestions."""
        with patch("app.api.endpoints.workflow.start_langgraph_workflow", new_callable=AsyncMock) as mock_start:
            with patch("app.api.endpoints.workflow.get_langgraph_status", new_callable=AsyncMock) as mock_status:
                with patch("app.api.endpoints.suggestions.get_langgraph_status", new_callable=AsyncMock) as mock_sug_status:
                    mock_start.return_value = "note:test/note.md"
                    mock_status.return_value = mock_workflow_state_with_suggestion
                    mock_sug_status.return_value = mock_workflow_state_with_suggestion

                    # Start workflow
                    client.post(
                        "/api/v1/workflow/start",
                        json={"file_path": "test/note.md", "content": "Content"},
                    )

                    # Get inbox
                    response = client.get("/api/v1/inbox/suggestions")

                    assert response.status_code == 200
                    data = response.json()
                    assert data["total_count"] == 1
                    assert len(data["suggestions"]) == 1

                    suggestion = data["suggestions"][0]
                    assert suggestion["suggestion_id"] == "q_123"
                    assert suggestion["note_path"] == "test/note.md"
                    assert "created_at" in suggestion

    @pytest.mark.unit
    def test_get_inbox_empty(self, client):
        """Test getting empty inbox."""
        response = client.get("/api/v1/inbox/suggestions")

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 0
        assert len(data["suggestions"]) == 0

    @pytest.mark.unit
    def test_get_inbox_count(self, client, mock_workflow_state_with_suggestion):
        """Test getting inbox count."""
        with patch("app.api.endpoints.workflow.start_langgraph_workflow", new_callable=AsyncMock) as mock_start:
            with patch("app.api.endpoints.workflow.get_langgraph_status", new_callable=AsyncMock) as mock_status:
                with patch("app.api.endpoints.suggestions.get_langgraph_status", new_callable=AsyncMock) as mock_sug_status:
                    mock_start.return_value = "note:test/note.md"
                    mock_status.return_value = mock_workflow_state_with_suggestion
                    mock_sug_status.return_value = mock_workflow_state_with_suggestion

                    # Start workflow
                    client.post(
                        "/api/v1/workflow/start",
                        json={"file_path": "test/note.md", "content": "Content"},
                    )

                    # Get count
                    response = client.get("/api/v1/inbox/count")

                    assert response.status_code == 200
                    data = response.json()
                    assert data["count"] == 1
