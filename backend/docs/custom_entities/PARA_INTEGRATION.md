# PARA Entity Types Integration Guide

## Overview

PipGraph now includes built-in support for the **PARA method** (Projects, Areas, Resources, Archive) through custom Graphiti entity types. These types enable automatic classification of notes and extraction of PARA-specific attributes using LLM.

## What is PARA?

PARA is a personal knowledge management system that organizes information into four categories:

- **Projects**: Time-bound initiatives with specific goals and deadlines
- **Areas**: Ongoing responsibilities requiring continuous attention
- **Resources**: Reference material and learning content
- **Archive**: Completed or inactive projects/areas/resources

## Quick Start

### Automatic PARA Classification

By default, all notes processed through PipGraph are automatically analyzed using PARA entity types:

```python
from app.services.pipgraph_manager import PipGraphManager
from app.services.llm_graphiti_client import get_graphiti

# PARA types are used automatically
graphiti = await get_graphiti()
manager = PipGraphManager(graphiti)

result = await manager.process_note(
    name="my-note.md",
    episode_body="Launch new product by Q4 2024...",
    source_description="Obsidian note",
    reference_time=datetime.now(timezone.utc)
)
# LLM automatically classifies this as a Project and extracts deadline
```

### Disabling PARA

To use default Graphiti behavior without PARA:

```python
result = await manager.process_note(
    name="my-note.md",
    episode_body="...",
    source_description="...",
    reference_time=datetime.now(timezone.utc),
    use_para_entities=False  # Disable PARA
)
```

## PARA Entity Types

### 1. Project

**When to use**: Note contains a specific goal with a deadline or clear completion criteria.

**Extracted attributes**:
- `name`: Project title
- `status`: active | completed | on_hold | cancelled | archived
- `deadline`: Target completion date
- `goal`: Specific objective or desired outcome
- `completion_criteria`: How to determine if done

**Example note**:
```markdown
# Q4 Marketing Campaign

Launch the new product marketing campaign by December 31, 2024.

**Goal**: Increase user signups by 20%

**Success criteria**: Reach 10,000 new signups
```

LLM extracts:
```python
Project(
    name="Q4 Marketing Campaign",
    status="active",
    deadline=datetime(2024, 12, 31),
    goal="Increase user signups by 20%",
    completion_criteria="Reach 10,000 new signups"
)
```

### 2. Area

**When to use**: Note represents ongoing responsibility or life domain without an endpoint.

**Extracted attributes**:
- `name`: Area title (domain/responsibility)
- `goal`: Desired standard or aspirational state
- `review_frequency`: How often to review
- `responsibilities`: List of ongoing duties
- `success_indicators`: Metrics/signals of health

**Example note**:
```markdown
# Personal Health & Fitness

**Aspirational state**: Maintain excellent physical fitness

**Review**: Weekly check-in every Monday

**Ongoing responsibilities**:
- Exercise 3x per week
- Track nutrition daily
- Get 7-8 hours sleep

**Success metrics**:
- Energy levels consistently high
- Weight stable around target
- No injuries
```

LLM extracts:
```python
Area(
    name="Personal Health & Fitness",
    goal="Maintain excellent physical fitness",
    review_frequency="weekly",
    responsibilities=["Exercise 3x per week", "Track nutrition daily", ...],
    success_indicators=["Energy levels consistently high", ...]
)
```

### 3. Resource

**When to use**: Note contains reference material, guides, or learning content.

**Extracted attributes**:
- `topic`: Subject or theme
- `description`: What this resource covers
- `category`: Type of resource (Tutorial, Reference, etc.)
- `tags`: Keywords for organization
- `source_type`: Medium (article, book, video, etc.)
- `last_reviewed`: When last updated

**Example note**:
```markdown
# Machine Learning Best Practices

A curated collection of ML engineering guides and patterns.

**Category**: Reference Guide
**Tags**: #python #machine-learning #engineering
**Source**: Curated collection from industry blogs
**Last reviewed**: 2024-10-01
```

LLM extracts:
```python
Resource(
    topic="Machine Learning Best Practices",
    description="Curated collection of ML engineering guides",
    category="Reference Guide",
    tags=["python", "machine-learning", "engineering"],
    source_type="curated collection",
    last_reviewed=datetime(2024, 10, 1)
)
```

### 4. Archive

**When to use**: Note explicitly marked as completed, finished, or no longer relevant.

**Extracted attributes**:
- `original_type`: What it was before archival (Project/Area/Resource)
- `original_name`: Original title
- `archived_at`: When archived
- `archival_reason`: Why archived
- `outcome`: What was achieved or learned
- `status`: Always "archived"

**Example note**:
```markdown
# [COMPLETED] Website Redesign 2023

**Status**: Archived on 2023-12-15
**Reason**: Project completed successfully

**Outcome**: New website launched with 30% better performance metrics.
Learned valuable lessons about responsive design.
```

LLM extracts:
```python
Archive(
    original_type="Project",
    original_name="Website Redesign 2023",
    archived_at=datetime(2023, 12, 15),
    archival_reason="Project completed successfully",
    outcome="New website launched with 30% better performance...",
    status="archived"
)
```

## PARA Relationships

Custom edge types define relationships between PARA entities:

### ContributesTo
**Pattern**: `(Project) -[:CONTRIBUTES_TO]-> (Area)`

Projects that advance goals in an area.

**Attributes**:
- `impact_description`: How the project contributes
- `completion_date`: When contribution completed

### SpawnedFrom
**Pattern**: `(Project) -[:SPAWNED_FROM]-> (Area)`

Projects created from areas of responsibility.

**Attributes**:
- `reason`: Why project was created
- `created_at`: When project originated

### UsesResource
**Pattern**: `(Project|Area) -[:USES]-> (Resource)`

Projects or areas utilizing resources for reference.

**Attributes**:
- `usage_type`: How resource is used (reference, learning, etc.)
- `relevance`: Why this resource is relevant

## Configuration

PARA configuration is centralized in `config/para_config.py`:

```python
from config.para_config import (
    PARA_ENTITY_TYPES,      # Dict of entity type models
    PARA_EDGE_TYPES,        # Dict of edge type models
    PARA_EDGE_TYPE_MAP,     # Allowed edge types between entity pairs
    get_para_config,        # Helper to get all configs
)
```

## Advanced Usage

### Custom Entity Types alongside PARA

You can add your own entity types in addition to PARA:

```python
from config.para_config import PARA_ENTITY_TYPES
from pydantic import BaseModel, Field

class Meeting(BaseModel):
    """A meeting entity"""
    date: datetime
    participants: list[str]

# Merge with PARA types
custom_types = {
    **PARA_ENTITY_TYPES,
    "Meeting": Meeting
}

result = await manager.process_note(
    entity_types=custom_types,
    ...
)
```

### Excluding Specific PARA Types

```python
result = await manager.process_note(
    entity_types=PARA_ENTITY_TYPES,
    excluded_entity_types=["Archive"],  # Don't extract Archive entities
    ...
)
```

### Search by PARA Type

```python
from graphiti_core.search.search_filters import SearchFilters

# Find all active projects
search_filter = SearchFilters(
    node_labels=["Project"]
)

results = await graphiti.search_(
    query="What projects am I working on?",
    search_filter=search_filter
)
```

## How LLM Classification Works

1. **LLM reads note content** with PARA entity type docstrings
2. **Analyzes identification criteria**:
   - Deadlines → Project
   - Ongoing responsibilities → Area
   - Reference material → Resource
   - Completion markers → Archive
3. **Extracts type-specific attributes** based on Field descriptions
4. **Creates entity node** in knowledge graph with extracted data

## Monitoring Classification

PipGraphManager logs PARA usage:

```
INFO: Using default PARA entity types (Project, Area, Resource, Archive)
INFO: Using default PARA edge types (ContributesTo, SpawnedFrom, UsesResource)
INFO: Using default PARA edge type map
```

## Best Practices

1. **Clear note titles**: Use specific, action-oriented titles for Projects
2. **Explicit markers**: Include deadlines, review frequencies, tags explicitly
3. **Consistent language**: Use PARA terminology in notes (e.g., "Goal:", "Review:")
4. **Structured format**: Use headers and lists for better extraction
5. **Retrospectives**: For Archive, include "Outcome:" or "Lessons learned:"

## Troubleshooting

### LLM misclassifies note type

**Solution**: Add explicit markers in note content:
```markdown
# Project: Launch Marketing Campaign
**Deadline**: 2024-12-31
```

### Missing extracted attributes

**Solution**: Use field description keywords:
```markdown
**Success criteria**: Reach 1000 users  # For Project.completion_criteria
**Review frequency**: Weekly            # For Area.review_frequency
```

### Note classified as multiple types

**Solution**: PARA is mutually exclusive. LLM chooses dominant type. Break complex notes into separate files if needed.

## Testing PARA Integration

Run the manual test:

```bash
cd backend/
PYTHONPATH=/home/anton/pipgraph/backend python tests/manual/test_para_models.py
```

Expected output:
```
✅ All PARA models created successfully!
🎉 All tests passed! PARA models are ready to use.
```

## References

- [PARA_ENTITY_DOCSTRINGS.md](../attend/PARA_ENTITY_DOCSTRINGS.md) - Full docstrings
- [PARA_TYPES_ARCHITECTURE.md](../attend/PARA_TYPES_ARCHITECTURE.md) - Architecture design
- [CUSTOM_ENTITIES_EXAMPLES.md](CUSTOM_ENTITIES_EXAMPLES.md) - Graphiti custom entities guide

## Migration from Pre-PARA

Existing notes in the graph are not affected. PARA types are only applied to new notes processed after integration.

To classify existing notes:
1. Re-ingest notes with PARA enabled
2. Or manually label existing entity nodes with PARA types in Neo4j
