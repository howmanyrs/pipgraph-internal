# PipGraph Backend — Conceptual Manifest

## Project Overview
PipGraph is an intelligent backend engine designed to bridge unstructured Markdown notes (Obsidian) with a structured Knowledge Graph (Neo4j). It acts as a "second brain" processor that structures, links, and classifies information while strictly adhering to a **Human-in-the-Loop** philosophy.

The system does not modify the body of user notes. Instead, it builds an external graph layer and syncs metadata back to the note's YAML frontmatter.

## Core Philosophy

1.  **Non-Destructive Processing**: The text content of notes is sacred. The system reads notes but only writes to a dedicated metadata section (YAML) or the external database.
2.  **Human-in-the-Loop (HITL)**: AI is a proposer, not a decider. The system classifies notes and suggests links with confidence scores. High-confidence actions may be automated, but ambiguous ones require explicit user confirmation via an "Inbox" workflow.
3.  **Graph-First Structure**: Information is stored as nodes (Episodes, Entities, PARA Containers) and edges (Relationships), enabling complex semantic queries that flat file searches cannot handle.
4.  **Mock-First Development**: The architecture supports swapping real AI services with deterministic mocks to ensure logical stability and rapid testing before incurring LLM costs.

## Business Logic & Methodology

### 1. The PARA Method
The system organizes knowledge based on the PARA methodology by Tiago Forte. Every note (Episode) is evaluated for context:
-   **Projects**: Short-term efforts with goals and deadlines.
-   **Areas**: Long-term responsibilities with standards to maintain.
-   **Resources**: Topics or themes of ongoing interest.
-   **Archives**: Inactive items from the above categories.
-   **Inbox**: The default holding area for unclassified content.

### 2. The Processing Pipeline
Data flows through a multi-stage pipeline:
1.  **Ingestion**: A note is received as an "Episode" (an event in time).
2.  **L1 Classification**: The system determines the note type (e.g., Meeting Note, Idea, Fact) and PARA context.
3.  **L2 Proposal Generation**: AI suggests links to existing containers (e.g., "Link to Project Alpha") or property updates (e.g., "Rename Project Alpha").
4.  **User Decision (Intervention)**:
    *   High confidence (>95%) -> Auto-link.
    *   Low confidence -> Create a "Suggestion" in the Inbox.
    *   **Cascade Effect**: If a user confirms a suggestion, similar pending suggestions for other notes are auto-resolved.
5.  **L3 Entity Extraction**: Once context is confirmed, the system extracts granular entities (Tasks, Concepts, Persons) from the text, using the confirmed context to improve accuracy.

### 3. Granular Suggestions
Unlike systems that make binary choices, PipGraph generates atomic suggestions. A single note might generate:
-   A suggestion to link to a Project.
-   A suggestion to update the Project's status.
-   A suggestion to extract a specific task.
The user can accept or reject these individually.

## Key Features

### Natural Language Search
The system converts natural language questions (e.g., "What tasks did we discuss regarding the API migration last week?") into formal graph queries (Cypher), allowing users to interrogate their knowledge base without learning query languages.

### No-Cache Policy (Episodic Memory)
The "Episodic" nodes (the notes) do not store context permanently in their own properties. Context is derived dynamically by traversing relationships (`:IS_PART_OF`) in the graph. This ensures that if a Project is renamed or moved, the historical notes linked to it remain valid without needing bulk updates.

## Documentation Structure
For technical implementation details, refer to the `.claude/skills/` directory:
-   **Architecture & Navigation**: Folder structure, layers, and key components.
-   **Workflows**: Deep dive into LangGraph state machines and decision logic.
-   **Coding Standards**: Testing, configuration, and patterns.