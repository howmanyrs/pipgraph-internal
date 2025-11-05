# План Имплементации: Пошаговое Руководство

**Дата**: 2025-10-27
**Контекст**: [02_ARCHITECTURE_DECISION.md](./02_ARCHITECTURE_DECISION.md)

---

## Обзор Этапов

```
Phase 1: Core Classification (3-5 days)
  ├── Task 1.1: Create classify_note_as_para() method
  ├── Task 1.2: Modify EpisodicNode creation
  └── Task 1.3: Unit tests for classification

Phase 2: Edge Enrichment (2-3 days)
  ├── Task 2.1: Create extended edge types
  ├── Task 2.2: Build PARA edge prompts module
  └── Task 2.3: Integrate into extract_edges

Phase 3: Testing & Validation (2-3 days)
  ├── Task 3.1: Integration tests
  ├── Task 3.2: Performance benchmarking
  └── Task 3.3: Manual validation on real notes

Phase 4: Documentation & Deployment (1-2 days)
  ├── Task 4.1: Update API documentation
  ├── Task 4.2: Write migration guide
  └── Task 4.3: Deploy to staging/production
```

**Total Estimated Time**: 8-13 days

---

## Phase 1: Core Classification

### Task 1.1: Implement classify_note_as_para()

**File**: `backend/app/services/pipgraph_manager.py`

**Code to Add**:

```python
async def classify_note_as_para(
    self,
    episode_body: str,
    name: str,
    source_description: str | None = None,
    confidence_threshold: float = 0.6,
) -> tuple[str | None, dict, float]:
    """
    Classify entire note as PARA type using LLM.

    See: docs/attend/resolveflow/03_CLASSIFICATION_FLOW.md
    """

    # 1. Build classification prompt
    prompt = self._build_classification_prompt(episode_body, name, source_description)

    # 2. Call LLM
    try:
        response = await self.clients.llm_client.generate_response(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1000,
        )
        response_text = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        logger.error(f"PARA classification LLM error: {e}")
        return None, {}, 0.0

    # 3. Parse JSON response
    try:
        json_text = self._extract_json_from_response(response_text)
        result = json.loads(json_text)
        para_type = result.get("para_type")
        confidence = float(result.get("confidence", 0.0))
        attributes = result.get("attributes", {})
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse PARA classification: {e}")
        return None, {}, 0.0

    # 4. Validate confidence threshold
    if confidence < confidence_threshold:
        logger.info(f"PARA confidence {confidence:.2f} below threshold {confidence_threshold}")
        return None, {}, confidence

    # 5. Validate para_type
    if para_type not in ["Project", "Area", "Resource", "Archive", None]:
        logger.warning(f"Invalid para_type: {para_type}")
        return None, {}, confidence

    # 6. Clean attributes
    cleaned_attrs = self._validate_para_attributes(para_type, attributes)

    logger.info(f"Note classified as {para_type} (conf: {confidence:.2f})")
    return para_type, cleaned_attrs, confidence


def _build_classification_prompt(self, episode_body: str, name: str, source_description: str | None) -> str:
    """Build classification prompt with PARA docstrings."""

    from app.models.para_entities import Project, Area, Resource, Archive

    # Truncate long notes
    max_length = 4000
    if len(episode_body) > max_length:
        episode_body = episode_body[:3000] + "\n[...truncated...]\n" + episode_body[-1000:]

    prompt = f"""You are a PARA classification expert. Classify this note.

PARA Definitions:
{Project.__doc__}
{Area.__doc__}
{Resource.__doc__}
{Archive.__doc__}

Note Title: {name}
Source: {source_description or 'Unknown'}
Content:
{episode_body}

Return JSON:
{{
  "para_type": "Project"|"Area"|"Resource"|"Archive"|null,
  "confidence": 0.0-1.0,
  "reasoning": "...",
  "attributes": {{...}}
}}
"""
    return prompt


def _extract_json_from_response(self, response_text: str) -> str:
    """Extract JSON from markdown code blocks."""
    if "```json" in response_text:
        start = response_text.find("```json") + 7
        end = response_text.find("```", start)
        return response_text[start:end].strip()
    elif "```" in response_text:
        start = response_text.find("```") + 3
        end = response_text.find("```", start)
        return response_text[start:end].strip()
    return response_text.strip()


def _validate_para_attributes(self, para_type: str, attributes: dict) -> dict:
    """Validate attributes against Pydantic model."""
    from config.para_config import PARA_ENTITY_TYPES
    from datetime import datetime

    model = PARA_ENTITY_TYPES.get(para_type)
    if not model:
        return {}

    cleaned = {}
    for field_name, field_info in model.model_fields.items():
        value = attributes.get(field_name)
        if value is None:
            continue

        try:
            # Handle datetime
            if 'datetime' in str(field_info.annotation):
                if isinstance(value, str):
                    cleaned[field_name] = datetime.fromisoformat(value.replace('Z', '+00:00'))
                elif isinstance(value, datetime):
                    cleaned[field_name] = value

            # Handle list
            elif 'list' in str(field_info.annotation):
                if isinstance(value, list):
                    cleaned[field_name] = value
                elif isinstance(value, str):
                    cleaned[field_name] = [item.strip() for item in value.split(',')]

            # Handle string
            else:
                cleaned[field_name] = str(value) if value else None

        except Exception as e:
            logger.warning(f"Attribute validation error for {field_name}: {e}")

    return cleaned
```

**Testing**:
```bash
pytest tests/unit/test_para_classification.py -v
```

---

### Task 1.2: Modify EpisodicNode Creation

**File**: `backend/app/services/pipgraph_manager.py`

**Line**: ~241-254 (current EpisodicNode creation)

**Changes**:

```python
async def process_note(
    self,
    ...,
    enable_early_para_classification: bool = True,  # ← NEW parameter
) -> AddEpisodeResults:

    # ... existing validation code ...

    # ====== NEW: PARA Classification ======
    para_type = None
    para_attrs = {}

    if use_para_entities and enable_early_para_classification:
        para_type, para_attrs, confidence = await self.classify_note_as_para(
            episode_body=episode_body,
            name=name,
            source_description=source_description,
        )

        if para_type:
            logger.info(f"Note classified as PARA type: {para_type}")

    # ====== MODIFIED: EpisodicNode with PARA label ======
    episode = (
        await EpisodicNode.get_by_uuid(self.driver, uuid)
        if uuid is not None
        else EpisodicNode(
            name=name,
            group_id=group_id,
            labels=[para_type] if para_type else [],  # ← ADD PARA LABEL
            source=source,
            content=episode_body,
            source_description=source_description,
            created_at=now,
            valid_at=reference_time,
        )
    )

    # ... rest of process_note ...
```

---

### Task 1.3: Unit Tests for Classification

**File**: `backend/tests/unit/test_para_classification.py` (NEW)

```python
import pytest
from app.services.pipgraph_manager import PipGraphManager


class TestParaClassification:

    @pytest.mark.unit
    def test_build_classification_prompt(self, manager):
        """Test prompt building with PARA docstrings."""
        prompt = manager._build_classification_prompt(
            episode_body="Launch campaign by Q4",
            name="Marketing Campaign",
            source_description="Test"
        )

        assert "PARA" in prompt
        assert "Project" in prompt
        assert "Marketing Campaign" in prompt


    @pytest.mark.unit
    def test_extract_json_from_markdown(self, manager):
        """Test JSON extraction from markdown code blocks."""
        response = '''```json
        {"para_type": "Project", "confidence": 0.9}
        ```'''

        json_str = manager._extract_json_from_response(response)
        assert '"para_type"' in json_str
        assert '"Project"' in json_str


    @pytest.mark.unit
    def test_validate_para_attributes_project(self, manager):
        """Test attribute validation for Project type."""
        attrs = {
            "status": "active",
            "deadline": "2024-12-31",
            "goal": "Launch product"
        }

        cleaned = manager._validate_para_attributes("Project", attrs)

        assert cleaned["status"] == "active"
        assert isinstance(cleaned["deadline"], datetime)
        assert cleaned["goal"] == "Launch product"
```

**Run Tests**:
```bash
pytest tests/unit/test_para_classification.py -v
```

---

## Phase 2: Edge Enrichment

### Task 2.1: Create Extended Edge Types

**File**: `backend/config/para_config.py`

**Add** (see [04_EDGE_ENRICHMENT.md](./04_EDGE_ENRICHMENT.md) for full code):

```python
# Add Pydantic models
class AssignedTo(BaseModel):
    role: Optional[str] = None
    assigned_at: Optional[datetime] = None

class LeadBy(BaseModel):
    start_date: Optional[datetime] = None

# ... add all other edge type models ...

# Update dictionaries
PARA_EDGE_TYPES_EXTENDED = {
    "ContributesTo": ContributesTo,
    "SpawnedFrom": SpawnedFrom,
    "AssignedTo": AssignedTo,
    "LeadBy": LeadBy,
    # ... add all types
}

PARA_EDGE_TYPE_MAP_EXTENDED = {
    ("Project", "Person"): ["MENTIONS", "AssignedTo", "LeadBy"],
    ("Project", "Task"): ["Contains"],
    # ... add all mappings (see doc)
}
```

---

### Task 2.2: Build PARA Edge Prompts Module

**File**: `backend/app/services/para_edge_prompts.py` (NEW)

```python
"""PARA-specific edge extraction prompt builders."""

from typing import Optional


def build_para_edge_instructions(para_type: Optional[str]) -> str:
    """Build custom instructions for edge extraction."""

    if para_type == "Project":
        return _project_edge_instructions()
    elif para_type == "Area":
        return _area_edge_instructions()
    elif para_type == "Resource":
        return _resource_edge_instructions()
    else:
        return ""


def _project_edge_instructions() -> str:
    return """
PARA CONTEXT: This is a PROJECT note.

Prioritize these edges:
- AssignedTo, LeadBy for people
- Contains for tasks
- ContributesTo for areas
- UsesResource for references
"""


def _area_edge_instructions() -> str:
    return """
PARA CONTEXT: This is an AREA note.

Prioritize these edges:
- ManagedBy for ownership
- SpawnedFrom for projects
- Contains for tasks
"""


def _resource_edge_instructions() -> str:
    return """
PARA CONTEXT: This is a RESOURCE note.

Prioritize these edges:
- AuthoredBy for authors
- References for external sources
"""


def inject_para_context_into_episode(para_type: Optional[str], original_content: str) -> str:
    """Inject PARA instructions into episode content (HACK)."""

    instructions = build_para_edge_instructions(para_type)
    if not instructions:
        return original_content

    return f"{instructions}\n\n===== NOTE CONTENT =====\n\n{original_content}"
```

---

### Task 2.3: Integrate into extract_edges

**File**: `backend/app/services/pipgraph_manager.py`

**Modify** around line 283 (before extract_edges call):

```python
# PARA CONTEXT INJECTION (before extract_edges)
if para_type:
    from app.services.para_edge_prompts import inject_para_context_into_episode

    # Create episode variant with PARA instructions
    episode_with_context = EpisodicNode(
        **episode.model_dump(exclude={"content"}),
        content=inject_para_context_into_episode(para_type, episode.content)
    )
else:
    episode_with_context = episode


# Extract edges with PARA context
extracted_edges = await extract_edges(
    self.clients,
    episode_with_context,  # ← Use modified episode
    extracted_nodes,
    previous_episodes,
    PARA_EDGE_TYPE_MAP_EXTENDED,  # ← Use extended map
    group_id,
    PARA_EDGE_TYPES_EXTENDED,  # ← Use extended types
)
```

---

## Phase 3: Testing & Validation

### Task 3.1: Integration Tests

**File**: `backend/tests/integration/test_para_integration.py` (NEW)

```python
import pytest
from datetime import datetime, timezone
from app.services.pipgraph_manager import PipGraphManager


@pytest.mark.integration
class TestParaIntegration:

    async def test_project_note_creates_para_label(self, manager):
        """Test that project note gets Project label."""

        result = await manager.process_note(
            name="Q4 Campaign",
            episode_body="Launch product by Dec 31. PM: John Doe.",
            source_description="Test",
            reference_time=datetime.now(timezone.utc),
        )

        assert result.episode.labels == ["Project"]


    async def test_project_edges_are_typed(self, manager):
        """Test that project generates AssignedTo edges."""

        result = await manager.process_note(
            name="Product Launch",
            episode_body="Assigned to John Doe. Tasks: - Design UI",
            source_description="Test",
            reference_time=datetime.now(timezone.utc),
        )

        edge_names = [e.name for e in result.edges]
        assert any(name in ["AssignedTo", "LeadBy", "Contains"] for name in edge_names)
```

**Run**:
```bash
pytest tests/integration/test_para_integration.py -v -m integration
```

---

### Task 3.2: Performance Benchmarking

**Script**: `backend/tests/manual/benchmark_para.py` (NEW)

```python
"""Benchmark PARA classification performance."""

import asyncio
from time import time
from app.services.llm_graphiti_client import get_graphiti
from app.services.pipgraph_manager import PipGraphManager


async def benchmark():
    graphiti = await get_graphiti()
    manager = PipGraphManager(graphiti)

    # Test notes
    notes = [
        ("Project Note", "Launch campaign by Q4 2024. Goal: 10k signups."),
        ("Area Note", "Team Management. Weekly 1-on-1s. Continuous improvement."),
        ("Resource Note", "Python Async Guide. Tutorial collection. Tags: #python #async"),
    ]

    times = []

    for name, body in notes:
        start = time()
        para_type, attrs, conf = await manager.classify_note_as_para(body, name)
        elapsed = (time() - start) * 1000
        times.append(elapsed)
        print(f"{name}: {para_type} ({conf:.2f}) - {elapsed:.0f}ms")

    print(f"\nAverage: {sum(times) / len(times):.0f}ms")


if __name__ == "__main__":
    asyncio.run(benchmark())
```

**Target**: <1000ms per classification

---

## Phase 4: Documentation & Deployment

### Task 4.1: Update API Documentation

**Files to Update**:
- `backend/README.md`: Add section on PARA classification
- `backend/docs/ARCHITECTURE.md`: Document new flow
- `backend/CHANGELOG.md`: Add entry for this feature

---

### Task 4.2: Configuration Options

**File**: `backend/.env.example`

Add:
```bash
# PARA Classification
ENABLE_PARA_CLASSIFICATION=true
PARA_CONFIDENCE_THRESHOLD=0.6
PARA_CLASSIFICATION_MODEL=gpt-4o-mini  # Cheaper model for classification
```

---

### Task 4.3: Deploy to Staging

**Steps**:
1. Merge feature branch to `develop`
2. Run full test suite: `pytest -v`
3. Deploy to staging environment
4. Manual QA with real notes
5. Monitor logs for classification errors
6. Measure performance metrics
7. If stable, merge to `main`

---

## Rollback Plan

If issues arise in production:

1. **Quick Rollback**: Set `enable_early_para_classification=False` via env var
2. **Partial Rollback**: Keep classification but disable edge enrichment
3. **Full Rollback**: Revert Git commits

---

## Success Criteria

- [ ] All unit tests pass (≥95% coverage)
- [ ] All integration tests pass
- [ ] Performance: Classification adds <1s per note
- [ ] Accuracy: ≥85% correct classifications (manual validation)
- [ ] Edge enrichment: ≥60% typed edges (not RELATES_TO)
- [ ] No breaking changes to existing API
- [ ] Documentation complete

---

## Next Steps

See:
- [06_TESTING_STRATEGY.md](./06_TESTING_STRATEGY.md) - Detailed testing approach
- [07_MIGRATION_GUIDE.md](./07_MIGRATION_GUIDE.md) - For existing notes
