"""
Note Processor Integration Tests

Tests for the note processing pipeline with real Graphiti and Neo4j.
Adapted from app/services/test_note_processor_cli.py
"""

import pytest
from app.models.note import NotePayload
from app.services.note_processor import process_and_store_note


# @pytest.mark.integration
# @pytest.mark.asyncio
# async def test_process_simple_note(sample_note_payload):
#     """Test processing a simple note with basic content."""
#     result = await process_and_store_note(sample_note_payload)

#     assert result is not None
#     assert result.nodes is not None
#     assert len(result.nodes) > 0


# @pytest.mark.integration
# @pytest.mark.asyncio
# async def test_process_person_note():
#     """Test processing a note about a person."""
#     note = NotePayload(
#         file_path="notes/people/john_doe.md",
#         content="""# John Doe

# John Doe is a software engineer at TechCorp.
# He works on backend systems and has expertise in Python and FastAPI.
# John graduated from MIT in 2015 with a degree in Computer Science.
# """
#     )

#     result = await process_and_store_note(note)
#     assert result is not None
#     assert result.nodes is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_process_project_note():
    """Test processing a note about a project."""
    note = NotePayload(
        file_path="notes/projects/pipgraph.md",
        content="""# PipGraph Project

PipGraph is an Obsidian plugin that uses Neo4j graph database.
The project uses FastAPI for the backend and TypeScript for the frontend.
It integrates with Graphiti for entity extraction and knowledge graph building.
"""
    )

    result = await process_and_store_note(note)
    assert result is not None
    assert result.status in ["new", "duplicate", "updated"]
    assert result.episode_uuid is not None
    # For new notes, check processing_details exist
    if result.status == "new":
        assert result.processing_details is not None
        assert result.processing_details.nodes is not None


# @pytest.mark.integration
# @pytest.mark.asyncio
# async def test_process_meeting_note():
#     """Test processing a meeting note with multiple attendees."""
#     note = NotePayload(
#         file_path="notes/meetings/standup_2024_01_15.md",
#         content="""# Daily Standup - January 15, 2024

# Attendees: Alice, Bob, Charlie

# Alice:
# - Completed the authentication module
# - Working on user profile page

# Bob:
# - Fixed bugs in the payment system
# - Planning to start integration tests

# Charlie:
# - Researching graph database options
# - Meeting with the design team tomorrow
# """
#     )

#     result = await process_and_store_note(note)
#     assert result is not None
#     assert result.nodes is not None


# @pytest.mark.integration
# @pytest.mark.asyncio
# async def test_process_empty_note():
#     """Test that processing empty note handles gracefully."""
#     note = NotePayload(
#         file_path="notes/empty.md",
#         content=""
#     )

#     # Should not crash, but may return minimal graph data
#     result = await process_and_store_note(note)
#     assert result is not None



# @pytest.mark.integration
# @pytest.mark.asyncio
# @pytest.mark.slow
# async def test_process_multiple_notes_sequentially():
#     """Test processing multiple notes in sequence."""
#     notes = [
#         NotePayload(
#             file_path="notes/test1.md",
#             content="Test note 1 about Python programming."
#         ),
#         NotePayload(
#             file_path="notes/test2.md",
#             content="Test note 2 about FastAPI framework."
#         ),
#         NotePayload(
#             file_path="notes/test3.md",
#             content="Test note 3 about Neo4j database."
#         ),
#     ]

#     results = []
#     for note in notes:
#         result = await process_and_store_note(note)
#         results.append(result)

#     assert len(results) == 3
#     assert all(r is not None for r in results)
