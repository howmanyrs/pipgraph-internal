"""Demo examples for PipGraph CLI."""

from typing import List, Dict


def get_demo_examples() -> List[Dict[str, str]]:
    """
    Get demo note examples.

    Returns:
        List of demo examples with file_path and content
    """
    return [
        {
            "file_path": "notes/people/john_doe.md",
            "content": """# John Doe

John Doe is a software engineer at TechCorp.
He works on backend systems and has expertise in Python and FastAPI.
John graduated from MIT in 2015 with a degree in Computer Science.
"""
        },
        {
            "file_path": "notes/projects/pipgraph.md",
            "content": """# PipGraph Project

PipGraph is an Obsidian plugin that uses Neo4j graph database.
The project uses FastAPI for the backend and TypeScript for the frontend.
It integrates with Graphiti for entity extraction and knowledge graph building.
"""
        },
        {
            "file_path": "notes/meetings/standup_2024_01_15.md",
            "content": """# Daily Standup - January 15, 2024

Attendees: Alice, Bob, Charlie

Alice:
- Completed the authentication module
- Working on user profile page

Bob:
- Fixed bugs in the payment system
- Planning to start integration tests

Charlie:
- Researching graph database options
- Meeting with the design team tomorrow
"""
        }
    ]
