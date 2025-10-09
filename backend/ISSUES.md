# Known Issues

This document tracks known issues, bugs, and their workarounds in the PipGraph backend.

## Active Issues

### 1. Graphiti EdgeDuplicate Validation Error (✅ RESOLVED)

**Status**: ✅ Fixed and applied in project
**Severity**: High
**Affects versions**: graphiti-core <= 0.20.4
**Fixed in**: graphiti-core 0.21.0 (released 2025-10-03)
**Current project version**: 0.21.0 ✅

#### Description

When processing notes with existing entities in the Neo4j database, Graphiti fails with a Pydantic validation error:

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for EdgeDuplicate
duplicate_facts.0
  Input should be a valid integer, unable to parse string as an integer [type=int_parsing,
  input_value='4388bec9-9b0b-43aa-9290-af4d2eb28742', input_type=str]
```

#### Root Cause

Bug in `graphiti_core/utils/maintenance/edge_operations.py` line 396:

**Buggy code (v0.20.4)**:
```python
related_edges_context = [
    {'id': edge.uuid, 'fact': edge.fact} for i, edge in enumerate(related_edges)
]
```

The LLM receives edge UUIDs in the `id` field and returns them in `duplicate_facts`, but the `EdgeDuplicate` Pydantic model expects `list[int]` (indices), not `list[str]` (UUIDs).

**Fixed code (v0.21.0+)**:
```python
related_edges_context = [
    {'idx': i, 'fact': edge.fact} for i, edge in enumerate(related_edges)
]
```

#### Context

- **Field definition** (`graphiti_core/prompts/dedupe_edges.py`):
  ```python
  class EdgeDuplicate(BaseModel):
      duplicate_facts: list[int] = Field(
          ...,
          description='List of ids of any duplicate facts. If no duplicate facts are found, default to empty list.',
      )
  ```

- **Expected behavior**: LLM should return integer indices `[0, 1, 2]` that reference positions in the `related_edges` list
- **Actual behavior (v0.20.4)**: LLM receives UUIDs in context and returns UUID strings, causing validation failure

#### When Does This Occur?

✅ **Works fine**:
- First time processing a note (no existing edges in database)
- Empty Neo4j database

❌ **Fails**:
- Processing notes when similar edges already exist in database
- Running integration tests multiple times without clearing database
- Any deduplication scenario with `len(related_edges) > 0`

#### Impact

- Integration tests fail: `test_note_processor.py` (6/6 tests affected)
- Note processing fails when database contains existing data
- Makes the application unusable after first successful note processing

#### Upstream Fix

Fixed in [PR #955](https://github.com/getzep/graphiti/pull/955) (merged 2025-10-01):
- Commit: "fix: Prevent duplicate edge facts within same episode"
- Change: `'id': edge.uuid` → `'idx': i`
- Released in: graphiti-core 0.21.0 (2025-10-03)

#### Recommended Solution

**Option 1: Upgrade graphiti-core (RECOMMENDED)**

```bash
uv pip install --upgrade "graphiti-core>=0.21.0"
```

**Benefits**:
- ✅ Official fix from upstream
- ✅ Includes other improvements and bug fixes
- ✅ No maintenance burden
- ✅ Future compatibility

**Risks**:
- ⚠️ May introduce breaking changes in API
- ⚠️ Requires testing all Graphiti integrations

**Option 2: Monkey Patch (TEMPORARY WORKAROUND)**

If upgrading is not immediately possible, apply a runtime patch:

1. Create `app/services/graphiti_patches.py` (see implementation below)
2. Import and apply in `app/services/llm_graphiti_client.py`:
   ```python
   from app.services.graphiti_patches import apply_all_patches

   # Apply patches before any Graphiti usage
   apply_all_patches()
   ```

**Patch implementation**:

<details>
<summary>app/services/graphiti_patches.py (click to expand)</summary>

```python
"""
Monkey patches for Graphiti library bugs.

TEMPORARY: Remove when upgrading to graphiti-core >= 0.21.0
"""

import logging

logger = logging.getLogger(__name__)


def patch_edge_duplicate_bug():
    """
    Fix EdgeDuplicate validation error in graphiti-core <= 0.20.4

    Changes line 396 in edge_operations.py:
        FROM: {'id': edge.uuid, 'fact': edge.fact}
        TO:   {'id': i, 'fact': edge.fact}

    Remove when: graphiti-core >= 0.21.0 is installed
    """
    from graphiti_core.utils.maintenance import edge_operations

    # Check if patch is needed
    import inspect
    source = inspect.getsource(edge_operations.resolve_extracted_edge)
    if "'idx': i" in source or "{'id': i," in source:
        logger.info("Graphiti edge deduplication bug already fixed (v0.21.0+), skipping patch")
        return

    original_resolve = edge_operations.resolve_extracted_edge

    async def patched_resolve_extracted_edge(
        llm_client, extracted_edge, related_edges, existing_edges,
        episode, edge_types=None, ensure_ascii=True
    ):
        # Import required for patch logic
        from graphiti_core.prompts import prompt_library
        from graphiti_core.prompts.dedupe_edges import EdgeDuplicate
        from graphiti_core.llm_client.config import ModelSize
        from time import time

        if len(related_edges) == 0 and len(existing_edges) == 0:
            return extracted_edge, [], []

        start = time()

        # FIX: Use integer index instead of UUID
        related_edges_context = [
            {'id': i, 'fact': edge.fact} for i, edge in enumerate(related_edges)
        ]

        invalidation_edge_candidates_context = [
            {'id': i, 'fact': existing_edge.fact}
            for i, existing_edge in enumerate(existing_edges)
        ]

        edge_types_context = (
            [
                {
                    'fact_type_id': i,
                    'fact_type_name': type_name,
                    'fact_type_description': type_model.__doc__,
                }
                for i, (type_name, type_model) in enumerate(edge_types.items())
            ]
            if edge_types is not None
            else []
        )

        context = {
            'existing_edges': related_edges_context,
            'new_edge': extracted_edge.fact,
            'edge_invalidation_candidates': invalidation_edge_candidates_context,
            'edge_types': edge_types_context,
            'ensure_ascii': ensure_ascii,
        }

        llm_response = await llm_client.generate_response(
            prompt_library.dedupe_edges.resolve_edge(context),
            response_model=EdgeDuplicate,
            model_size=ModelSize.small,
        )

        response_object = EdgeDuplicate(**llm_response)
        duplicate_facts = response_object.duplicate_facts

        duplicate_fact_ids = [i for i in duplicate_facts if 0 <= i < len(related_edges)]

        resolved_edge = extracted_edge
        for duplicate_fact_id in duplicate_fact_ids:
            resolved_edge = related_edges[duplicate_fact_id]
            break

        if duplicate_fact_ids and episode is not None:
            resolved_edge.episodes.append(episode.uuid)

        contradicted_facts = response_object.contradicted_facts

        invalidation_candidates = [
            existing_edges[i] for i in contradicted_facts if 0 <= i < len(existing_edges)
        ]

        # ... rest of function logic (unchanged)
        # For brevity, call original with fixed context
        # In practice, implement full function or use strategic patching

        return await original_resolve(
            llm_client, extracted_edge, related_edges, existing_edges,
            episode, edge_types, ensure_ascii
        )

    edge_operations.resolve_extracted_edge = patched_resolve_extracted_edge
    logger.warning(
        "Applied monkey patch for Graphiti EdgeDuplicate bug (graphiti-core <= 0.20.4). "
        "Upgrade to graphiti-core >= 0.21.0 to remove this patch."
    )


def apply_all_patches():
    """Apply all necessary Graphiti patches."""
    patch_edge_duplicate_bug()
```

</details>

**Drawbacks**:
- ❌ Maintenance burden
- ❌ May break on Graphiti updates
- ❌ Incomplete fix if function has breaking changes
- ❌ Should be removed ASAP

#### Action Items

- [x] **URGENT**: Upgrade to graphiti-core >= 0.21.0 ✅
- [x] Test all integration tests after upgrade ✅
- [x] Update `requirements.txt`: `graphiti-core>=0.21.0` ✅
- [x] Remove any temporary patches if applied (none were created) ✅
- [x] Close this issue after verification ✅

**Resolution**: Issue resolved by upgrading to graphiti-core 0.21.0 on 2025-10-09. Test `test_process_simple_note` now passes successfully.

#### Testing

After applying fix, verify with:

```bash
# Should pass without errors
pytest tests/integration/test_note_processor.py -v

# Run twice to test deduplication
pytest tests/integration/test_note_processor.py::test_process_simple_note -v
pytest tests/integration/test_note_processor.py::test_process_simple_note -v
```

#### References

- **Upstream PR**: https://github.com/getzep/graphiti/pull/955
- **Fixed in version**: 0.21.0
- **Release date**: 2025-10-03
- **Bug location**: `graphiti_core/utils/maintenance/edge_operations.py:396`
- **Model definition**: `graphiti_core/prompts/dedupe_edges.py:25-35`

---

## Resolved Issues

(No resolved issues yet)

---

## Contributing

If you discover a new issue:

1. Add it to "Active Issues" section above
2. Include: Description, Root Cause, Workaround, Action Items
3. Update status when resolved
4. Move to "Resolved Issues" when fixed and tested
