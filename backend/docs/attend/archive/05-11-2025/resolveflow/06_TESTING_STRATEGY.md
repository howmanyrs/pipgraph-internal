# Стратегия Тестирования PARA Classification

**Дата**: 2025-10-27
**Контекст**: [05_IMPLEMENTATION_PLAN.md](./05_IMPLEMENTATION_PLAN.md)

---

## Тестовые Уровни

```
Unit Tests (Fast, Isolated)
  ├── Classification prompt building
  ├── JSON parsing and validation
  ├── Attribute cleaning
  └── Edge instruction generation

Integration Tests (Database + LLM)
  ├── Full classification flow
  ├── EpisodicNode with PARA labels
  ├── Edge extraction with PARA context
  └── End-to-end note processing

Manual Tests (Real-world Validation)
  ├── Classification accuracy on sample notes
  ├── Edge quality inspection
  └── Performance measurements

Regression Tests
  └── Backward compatibility checks
```

---

## Unit Tests

### Test Classification Logic

**File**: `tests/unit/test_para_classification.py`

```python
import pytest
from app.services.pipgraph_manager import PipGraphManager


class TestClassificationPrompt:

    def test_prompt_contains_para_docstrings(self, manager):
        """Verify prompt includes PARA type definitions."""
        prompt = manager._build_classification_prompt(
            "Test content",
            "Test Note",
            None
        )
        assert "Project" in prompt
        assert "Area" in prompt
        assert "Resource" in prompt


    def test_prompt_truncates_long_notes(self, manager):
        """Long notes should be truncated."""
        long_body = "A" * 10000
        prompt = manager._build_classification_prompt(long_body, "Test", None)
        assert len(prompt) < 8000  # Truncated


class TestJSONParsing:

    @pytest.mark.parametrize("response,expected", [
        ('{"para_type": "Project"}', "Project"),
        ('```json\n{"para_type": "Area"}\n```', "Area"),
        ('```\n{"para_type": "Resource"}\n```', "Resource"),
    ])
    def test_extract_json_from_various_formats(self, manager, response, expected):
        """Test JSON extraction from markdown."""
        json_str = manager._extract_json_from_response(response)
        import json
        data = json.loads(json_str)
        assert data["para_type"] == expected


class TestAttributeValidation:

    def test_validate_project_attributes(self, manager):
        """Test Project attribute validation."""
        attrs = {
            "status": "active",
            "deadline": "2024-12-31",
            "goal": "Launch product",
            "invalid_field": "should be ignored"
        }

        cleaned = manager._validate_para_attributes("Project", attrs)

        assert cleaned["status"] == "active"
        assert "invalid_field" not in cleaned


    def test_datetime_parsing(self, manager):
        """Test datetime field conversion."""
        attrs = {"deadline": "2024-12-31"}
        cleaned = manager._validate_para_attributes("Project", attrs)

        from datetime import datetime
        assert isinstance(cleaned["deadline"], datetime)


    def test_list_parsing(self, manager):
        """Test list field conversion."""
        attrs = {"responsibilities": ["Task 1", "Task 2"]}
        cleaned = manager._validate_para_attributes("Area", attrs)

        assert isinstance(cleaned["responsibilities"], list)
        assert len(cleaned["responsibilities"]) == 2
```

---

### Test Edge Prompt Generation

**File**: `tests/unit/test_para_edge_prompts.py`

```python
import pytest
from app.services.para_edge_prompts import build_para_edge_instructions


class TestEdgeInstructions:

    @pytest.mark.parametrize("para_type,expected_keywords", [
        ("Project", ["AssignedTo", "LeadBy", "Contains"]),
        ("Area", ["ManagedBy", "SpawnedFrom"]),
        ("Resource", ["AuthoredBy", "References"]),
        (None, []),  # No instructions for unclassified
    ])
    def test_instructions_contain_expected_edges(self, para_type, expected_keywords):
        """Test each PARA type mentions relevant edge types."""
        instructions = build_para_edge_instructions(para_type)

        if expected_keywords:
            for keyword in expected_keywords:
                assert keyword in instructions
        else:
            assert instructions == ""
```

---

## Integration Tests

### Test Full Classification Flow

**File**: `tests/integration/test_para_classification_integration.py`

```python
import pytest
from datetime import datetime, timezone
from app.services.pipgraph_manager import PipGraphManager
from app.services.llm_graphiti_client import get_graphiti


@pytest.fixture
async def manager():
    """Fixture for PipGraphManager with real Graphiti."""
    graphiti = await get_graphiti()
    return PipGraphManager(graphiti)


@pytest.mark.integration
@pytest.mark.asyncio
class TestClassificationIntegration:

    async def test_classify_clear_project(self, manager):
        """Test classification of clear project note."""
        body = """
        # Q4 Campaign
        Launch new product by December 31, 2024.
        Goal: 10,000 signups.
        """

        para_type, attrs, conf = await manager.classify_note_as_para(
            body, "Q4 Campaign", None
        )

        assert para_type == "Project"
        assert conf >= 0.7
        assert "deadline" in attrs or "goal" in attrs


    async def test_classify_clear_area(self, manager):
        """Test classification of clear area note."""
        body = """
        # Team Management
        Ongoing responsibility. Weekly 1-on-1s.
        Review: Every Monday.
        """

        para_type, attrs, conf = await manager.classify_note_as_para(
            body, "Team Management", None
        )

        assert para_type == "Area"
        assert conf >= 0.7


    async def test_classify_ambiguous_note(self, manager):
        """Test that ambiguous notes return null."""
        body = "Quick meeting notes. Discussed API design."

        para_type, attrs, conf = await manager.classify_note_as_para(
            body, "Meeting Notes", None
        )

        # Either null or low confidence
        assert para_type is None or conf < 0.6


### Test End-to-End Note Processing

@pytest.mark.integration
@pytest.mark.asyncio
class TestParaEndToEnd:

    async def test_project_note_has_para_label(self, manager):
        """Test that processed project note has Project label."""
        result = await manager.process_note(
            name="Product Launch",
            episode_body="Launch by Q4. PM: John Doe.",
            source_description="Test",
            reference_time=datetime.now(timezone.utc),
        )

        assert "Project" in result.episode.labels


    async def test_project_generates_typed_edges(self, manager):
        """Test that project note generates AssignedTo edges."""
        result = await manager.process_note(
            name="Campaign",
            episode_body="Owner: Sarah Johnson. Tasks: - Design materials",
            source_description="Test",
            reference_time=datetime.now(timezone.utc),
        )

        edge_names = {e.name for e in result.edges}
        typed_edges = {"AssignedTo", "LeadBy", "Contains"} & edge_names

        assert len(typed_edges) > 0, "Should have at least one typed PARA edge"
```

---

## Manual Testing

### Test Dataset

Create `tests/manual/sample_notes.py`:

```python
"""Sample notes for manual PARA classification testing."""

TEST_NOTES = [
    {
        "name": "Q4 Marketing Campaign",
        "body": """
        Launch new product marketing campaign by December 31, 2024.

        **Goal**: Achieve 10,000 signups
        **Success Criteria**: Conversion rate > 5%

        ## Tasks
        - [ ] Design marketing materials
        - [ ] Set up ad campaigns
        - [ ] Launch landing page
        """,
        "expected_type": "Project",
        "expected_confidence": "> 0.85",
    },
    {
        "name": "Personal Health",
        "body": """
        Ongoing responsibility for maintaining physical and mental health.

        **Review**: Weekly on Mondays
        **Responsibilities**:
        - Exercise 3x per week
        - Track nutrition daily
        - Get 7-8 hours sleep

        **Success Indicators**:
        - Energy levels consistently high
        - Weight stable
        """,
        "expected_type": "Area",
        "expected_confidence": "> 0.80",
    },
    {
        "name": "Python Async Programming",
        "body": """
        Collection of asyncio tutorials and best practices.

        **Category**: Tutorial
        **Tags**: #python #async #concurrency

        ## Resources
        - https://docs.python.org/3/library/asyncio.html
        - Real Python async guide
        """,
        "expected_type": "Resource",
        "expected_confidence": "> 0.85",
    },
]
```

### Manual Test Script

**File**: `tests/manual/test_classification_accuracy.py`

```python
"""Manual test script for classification accuracy."""

import asyncio
from app.services.llm_graphiti_client import get_graphiti
from app.services.pipgraph_manager import PipGraphManager
from tests.manual.sample_notes import TEST_NOTES


async def test_classification_accuracy():
    graphiti = await get_graphiti()
    manager = PipGraphManager(graphiti)

    results = []
    correct = 0

    for note in TEST_NOTES:
        para_type, attrs, conf = await manager.classify_note_as_para(
            note["body"],
            note["name"],
            None
        )

        is_correct = (para_type == note["expected_type"])
        if is_correct:
            correct += 1

        results.append({
            "name": note["name"],
            "expected": note["expected_type"],
            "actual": para_type,
            "confidence": conf,
            "correct": is_correct,
        })

        print(f"{'✅' if is_correct else '❌'} {note['name']}")
        print(f"   Expected: {note['expected_type']}, Got: {para_type} ({conf:.2f})")
        print()

    accuracy = correct / len(TEST_NOTES)
    print(f"\n📊 Accuracy: {accuracy:.1%} ({correct}/{len(TEST_NOTES)})")

    return accuracy >= 0.85  # Target: 85% accuracy


if __name__ == "__main__":
    success = asyncio.run(test_classification_accuracy())
    exit(0 if success else 1)
```

**Run**:
```bash
cd backend/
PYTHONPATH=/home/anton/pipgraph/backend python tests/manual/test_classification_accuracy.py
```

---

## Performance Testing

### Benchmark Script

**File**: `tests/manual/benchmark_classification.py`

```python
import asyncio
from time import time
from app.services.llm_graphiti_client import get_graphiti
from app.services.pipgraph_manager import PipGraphManager


async def benchmark():
    graphiti = await get_graphiti()
    manager = PipGraphManager(graphiti)

    # Various note lengths
    notes = [
        ("Short", "Launch campaign by Q4."),
        ("Medium", "Launch campaign by Q4. " + "Details. " * 50),
        ("Long", "Launch campaign by Q4. " + "Details. " * 500),
    ]

    for name, body in notes:
        times = []

        # Run 5 times to average
        for _ in range(5):
            start = time()
            await manager.classify_note_as_para(body, name)
            elapsed = (time() - start) * 1000
            times.append(elapsed)

        avg_time = sum(times) / len(times)
        print(f"{name:10} note: {avg_time:6.0f}ms (avg of 5 runs)")

    print(f"\nTarget: <1000ms per classification")


if __name__ == "__main__":
    asyncio.run(benchmark())
```

**Target**: All notes <1000ms

---

## Regression Testing

### Backward Compatibility

**File**: `tests/integration/test_backward_compatibility.py`

```python
@pytest.mark.integration
class TestBackwardCompatibility:

    async def test_old_behavior_with_flag_disabled(self, manager):
        """Test old PARA behavior when early classification disabled."""
        result = await manager.process_note(
            name="Test Note",
            episode_body="Some content",
            source_description="Test",
            reference_time=datetime.now(timezone.utc),
            enable_early_para_classification=False,  # ← OLD behavior
        )

        # Should still work, just without PARA label on episode
        assert result.episode is not None


    async def test_no_para_mode_still_works(self, manager):
        """Test disabling PARA entirely."""
        result = await manager.process_note(
            name="Test Note",
            episode_body="Some content",
            source_description="Test",
            reference_time=datetime.now(timezone.utc),
            use_para_entities=False,  # ← No PARA
        )

        assert result.episode.labels == []
```

---

## Test Coverage Requirements

```
Unit Tests:            ≥ 95% coverage
Integration Tests:     ≥ 80% coverage
Manual Tests:          ≥ 85% accuracy
Performance:           < 1000ms per classification
Backward Compat:       100% (all old tests pass)
```

---

## Continuous Testing

### GitHub Actions (CI/CD)

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          cd backend
          uv pip install -r requirements.txt

      - name: Run unit tests
        run: |
          cd backend
          pytest tests/unit/ -v --cov=app

      - name: Run integration tests
        env:
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
          NEO4J_URI: ${{ secrets.NEO4J_URI }}
        run: |
          cd backend
          pytest tests/integration/ -v -m integration
```

---

## Test Data Management

### Fixtures for Tests

**File**: `tests/conftest.py`

```python
import pytest
from app.services.llm_graphiti_client import get_graphiti
from app.services.pipgraph_manager import PipGraphManager


@pytest.fixture
async def graphiti():
    """Provide Graphiti instance."""
    return await get_graphiti()


@pytest.fixture
async def manager(graphiti):
    """Provide PipGraphManager instance."""
    return PipGraphManager(graphiti)


@pytest.fixture
def sample_project_note():
    """Sample project note for testing."""
    return {
        "name": "Q4 Campaign",
        "body": "Launch by Dec 31. Goal: 10k signups.",
    }
```

---

## Success Criteria Summary

- [ ] Unit tests pass (≥95% coverage)
- [ ] Integration tests pass (≥80% coverage)
- [ ] Manual tests show ≥85% accuracy
- [ ] Performance <1000ms per classification
- [ ] Backward compatibility maintained
- [ ] CI/CD pipeline green

---

## Next Steps

See [07_MIGRATION_GUIDE.md](./07_MIGRATION_GUIDE.md) for migrating existing notes.
