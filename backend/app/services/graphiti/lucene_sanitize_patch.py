"""
Patches for Graphiti bugs.

PROBLEM 1: lucene_sanitize() bug
Graphiti's lucene_sanitize() escapes capital letters O, R, N, T, A, D
to prevent interpretation as Lucene operators (OR, AND, NOT).
This breaks search for words like "Test", "Project", "Alpha":
  "Test Project Alpha" → "\\Test Project \\Alpha"

SOLUTION 1:
Replace lucene_sanitize with fixed version that only escapes
actual Lucene operators (case-insensitive matching):
  "OR" → "\\OR"
  "AND" → "\\AND"
  "NOT" → "\\NOT"

PROBLEM 2: Empty group_id causes search failures
Graphiti's get_default_group_id() returns empty string "" for Neo4j provider.
Neo4j fulltext search cannot filter by empty group_id, returning 0 results.

SOLUTION 2:
Replace get_default_group_id() to return "default" instead of "".

USAGE:
Import this module early in application startup to apply patches:
  from app.services.graphiti.lucene_sanitize_patch import apply_patch
  apply_patch()

SEE ALSO:
- backend/.docs/about_graphiti/issues/lucene_sanitize_bug.md
- backend/.docs/about_graphiti/issues/empty_group_id_bug.md
- https://github.com/getzep/graphiti/issues/XXX (to be filed)
"""

import re
import logging

logger = logging.getLogger(__name__)


def fixed_lucene_sanitize(query: str) -> str:
    """
    Fixed version of lucene_sanitize that doesn't break search.

    Escapes special Lucene characters and operators, but doesn't
    escape standalone capital letters O, R, N, T, A, D.

    Args:
        query: Raw search query

    Returns:
        Sanitized query safe for Lucene fulltext search
    """
    # Escape special Lucene characters
    # + - && || ! ( ) { } [ ] ^ " ~ * ? : \ /
    escape_map = str.maketrans({
        '+': r'\+',
        '-': r'\-',
        '&': r'\&',
        '|': r'\|',
        '!': r'\!',
        '(': r'\(',
        ')': r'\)',
        '{': r'\{',
        '}': r'\}',
        '[': r'\[',
        ']': r'\]',
        '^': r'\^',
        '"': r'\"',
        '~': r'\~',
        '*': r'\*',
        '?': r'\?',
        ':': r'\:',
        '\\': r'\\',
        '/': r'\/',
    })

    sanitized = query.translate(escape_map)

    # Escape Lucene operators (case-insensitive word boundaries)
    # \b(OR|AND|NOT)\b → \\\1
    sanitized = re.sub(r'\b(OR|AND|NOT)\b', r'\\\1', sanitized, flags=re.IGNORECASE)

    return sanitized


def fixed_get_default_group_id(provider):
    """
    Fixed version of get_default_group_id that returns non-empty string.

    Graphiti's get_default_group_id() returns "" for Neo4j provider,
    which breaks fulltext search filtering.

    Args:
        provider: GraphProvider enum value

    Returns:
        "default" instead of empty string
    """
    return "default"


def apply_patch():
    """
    Apply patches to Graphiti functions.

    This replaces:
    1. graphiti_core.helpers.lucene_sanitize
    2. graphiti_core.helpers.get_default_group_id
    """
    try:
        import graphiti_core.helpers as helpers
        import graphiti_core.search.search_utils as search_utils

        # Save original functions for debugging
        if not hasattr(helpers, '_original_lucene_sanitize'):
            helpers._original_lucene_sanitize = helpers.lucene_sanitize

        if not hasattr(helpers, '_original_get_default_group_id'):
            helpers._original_get_default_group_id = helpers.get_default_group_id

        if not hasattr(search_utils, '_original_fulltext_query'):
            search_utils._original_fulltext_query = search_utils.fulltext_query

        # PATCH 1: Fix lucene_sanitize
        helpers.lucene_sanitize = fixed_lucene_sanitize
        search_utils.lucene_sanitize = fixed_lucene_sanitize

        # PATCH 2: Fix get_default_group_id
        helpers.get_default_group_id = fixed_get_default_group_id

        # PATCH 3: Add logging to fulltext_query (debugging)
        original_fulltext_query = search_utils._original_fulltext_query

        def fulltext_query_with_logging(query, group_ids, driver):
            result = original_fulltext_query(query, group_ids, driver)
            logger.info(
                f"[fulltext_query] input='{query[:100]}', group_ids={group_ids}, "
                f"output='{result[:100] if result else result}'"
            )
            return result

        search_utils.fulltext_query = fulltext_query_with_logging

        logger.info(
            "[graphiti_patches] Successfully patched lucene_sanitize, "
            "get_default_group_id, and fulltext_query"
        )

    except Exception as e:
        logger.error(
            f"[graphiti_patches] Failed to apply patches: {e}",
            exc_info=True
        )
        raise


# Auto-apply patch on module import
# This ensures patch is applied as early as possible
apply_patch()
