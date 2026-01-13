---
name: pipgraph-workflows
description: Detailed logic of the LangGraph processing pipeline, the 6-node state machine, Human-in-the-Loop (HITL) interrupts, and the Graphiti integration strategies. Use this skill when modifying workflow steps, debugging state transitions, or working on entity extraction logic.
---

# Workflows & Graphiti Logic

## Purpose
This skill defines the core processing pipeline orchestrated by LangGraph and the custom Graphiti integration logic. The system uses a state machine to manage the lifecycle of a note from ingestion to final storage, including Human-in-the-Loop (HITL) interruptions.

**Note:** All file paths in this skill are relative to the `backend/` directory (e.g., `app/workflows/` refers to `backend/app/workflows/`).

## The PARA Workflow Engine

The workflow is defined in `app/workflows/langgraph_service.py` and consists of 6 distinct nodes.

### Flow Diagram
```text
[START]
   ↓
(identify_context)  -> L1/L2 Analysis (Classify + Propose)
   ↓
(apply_proposal)    -> Writes :SUGGESTS edges to Neo4j
   ↓
<check_suggestion_status> (Condition)
   ├─[Has Pending Suggestions]→ (wait_for_decision) -> INTERRUPT (Stops execution)
   │                                   ↓
   │                              (process_decision) -> User Action (Confirm/Dismiss)
   │                                   ↓
   └──────────────────────────<should_continue>
                                       │
   ┌─[No Pending / Context Confirmed]──┘
   ↓
(extract_content)   -> L3 Entity Extraction (Context-Aware)
   ↓
(save_entities)     -> Writes Entity nodes & :MENTIONS
   ↓
 [END]
```

### Node Logic Breakdown

1.  **`identify_context_node`**
    *   **Input**: Note content.
    *   **Action**: Calls `services.para.classify_note_para` (L1) and `generate_para_proposal` (L2).
    *   **Output**: A `PARAProposal` object containing candidates (links or property updates).

2.  **`apply_proposal_node`**
    *   **Action**: Converts the proposal into Neo4j relationships.
    *   **Logic**:
        *   Confidence > 0.95 (Link type) → Create `:IS_PART_OF` (Auto-confirm).
        *   Otherwise → Create `:SUGGESTS` edge (Pending user review).

3.  **`wait_for_decision_node` (The Interrupt)**
    *   **Action**: Checks for pending suggestions in the DB.
    *   **Behavior**: If pending items exist, it raises `langgraph.types.interrupt`. The workflow **halts** and persists state to the checkpointer (SQLite/Memory).
    *   **API Interaction**: The REST API sees the status `waiting_user`. The frontend must fetch suggestions via `GET /suggestions`.

4.  **`process_decision_node`**
    *   **Trigger**: Resumed via `POST /resume` with `UserDecisionPayload`.
    *   **Action**: Calls `pipgraph_manager.process_user_decision`.
    *   **Logic**:
        *   *Confirm*: Convert `:SUGGESTS` to `:IS_PART_OF`.
        *   *Dismiss*: Delete `:SUGGESTS`.
        *   *Cascade*: If confirmed, trigger `CascadeService` to auto-resolve similar suggestions.

5.  **`extract_content_node`**
    *   **Prerequisite**: A confirmed `:IS_PART_OF` relationship must exist (unless in Inbox).
    *   **Action**: Calls `pipgraph_manager.extract_entities_with_context`.
    *   **Nuance**: Uses the *confirmed* container name (e.g., "Project Alpha") in the prompt to help the LLM extract more relevant entities.

6.  **`save_entities_node`**
    *   **Action**: Batches writes of Entities and `:MENTIONS` edges to Neo4j using `EntityCRUD`.

## Graphiti Integration (`PipGraphManager`)

We do not use `graphiti.add_episode()` directly as a black box. Instead, `app/services/graphiti/pipgraph_manager.py` wraps the logic to allow intervention.

### Key Concepts

*   **Episodic Nodes**: Represent the *Note* file. They adhere to the **No-Cache Policy**: they *never* store `project_id` or context properties directly. Context is derived strictly by traversing `:IS_PART_OF` edges.
*   **Granular Suggestions**: A suggestion is a reified relationship (`:SUGGESTS`) with a `suggestion_id`. This allows atomic decisions (Accept/Reject) on specific links without reprocessing the whole note.
*   **Context-Aware Extraction**: L3 extraction (Entities) happens *after* L2 context confirmation. This improves quality (e.g., extracting "Authentication" as a Task because we know we are in the "Login System" project).

## The Cascade Service

Located in `app/services/cascade_service.py`.

*   **Trigger**: User confirms a "Link" suggestion.
*   **Action**: Finds all other notes with pending suggestions pointing to the *same* container.
*   **Threshold**: If confidence > `0.85` (default), they are auto-confirmed.
*   **Goal**: Reduce user fatigue by handling bulk approvals implicitly.

## State Management (`PARAWorkflowState`)

The state `app/workflows/state.py` is the source of truth during execution.
*   **Persistence**: Handled by `AsyncSqliteSaver` in production (`langgraph_service.get_compiled_app`).
*   **Serialization**: Complex objects (Proposals, Entities) are serialized to dicts before storage to ensure JSON compatibility.
