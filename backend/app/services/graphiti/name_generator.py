"""
Episode Name Generator

Generates meaningful, filesystem-compatible names for Episodic nodes using LLM.
Names are suitable for use as markdown filenames in Obsidian vaults.

Usage:
    name = await generate_episode_name(
        episode_body="Meeting notes about website redesign...",
        llm_client=client
    )
    # Returns: "Meeting About Website Redesign"
"""

import logging
import re
from typing import Optional

from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.prompts.models import Message
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class EpisodeName(BaseModel):
    """
    Response model for episode name generation.

    The name should be:
    - Concise (3-8 words ideally)
    - Descriptive of the note's main topic
    - Suitable for use as a filename
    - In title case or sentence case

    ``semantic_hints`` is a cheap pre-extraction layer riding the same LLM call
    (suggest-extra lever B): 5–12 keywords for the note — *including implied
    ones* — that later widen the ``make_suggestions`` query so a folder can match
    even when the note never spells out its words. This is NOT the heavy Graphiti
    entity extraction (that runs later, in the process pipeline, and produces
    :Entity nodes via MENTIONS) — just hints, hence the name.
    """
    name: str = Field(
        description="A concise, descriptive name for the episode that can be used as a filename"
    )
    reasoning: str = Field(
        description="Brief explanation of why this name was chosen"
    )
    semantic_hints: list[str] = Field(
        default_factory=list,
        description=(
            "5–12 keywords for the note, in the note's own language, including "
            "IMPLIED ones (synonyms, common names, the class/purpose/domain a term "
            "belongs to) — the words by which someone would search for this note "
            "even if the text doesn't contain them."
        ),
    )


def create_name_generation_prompt(episode_body: str) -> list[Message]:
    """
    Create prompt messages for episode name generation.

    Args:
        episode_body: The full content of the note/episode

    Returns:
        List of Message objects for LLM prompt
    """
    # Truncate content if too long (use first 1500 chars for name generation)
    truncated_content = episode_body[:1500]
    if len(episode_body) > 1500:
        truncated_content += "..."

    return [
        Message(
            role='system',
            content='''You are an expert at generating concise, descriptive titles for notes and documents.

Your task is to generate a SHORT, MEANINGFUL name that:
- Captures the main topic or purpose of the note
- Is 3-8 words long (ideally 3-5 words)
- Uses title case (capitalize first letter of each major word)
- Avoids special characters that are problematic for filenames
- Is specific enough to be distinguishable from other notes
- Does NOT include file extensions (no .md, .txt, etc.)
- MUST be in the SAME LANGUAGE as the note content (detect language automatically)

Examples of GOOD names:
- "Project Planning Session Notes" (English note)
- "Стратегия Миграции API" (Russian note)
- "Interview with John Smith" (English note)
- "Еженедельный Стендап Команды" (Russian note)
- "Budget Review Q1 2024" (English note)

Examples of BAD names (too long, too vague, or problematic):
- "Some random thoughts I had today about various topics" (too long)
- "Notes" (too vague)
- "Meeting/Discussion: API|Backend" (problematic characters)
- "note_2024_01_14.md" (includes extension, too technical)
- "Project Zadachi" (mixing languages - NEVER do this!)

Besides the name, also return 5-12 KEYWORDS for the note, in the note's own
language, by which someone would later search for it. Include IMPLIED keywords,
not only words literally present in the text. Strategy — go from the specific to
the general: for each concrete term in the note, also add its synonyms, common
names, and the class, purpose and domain it belongs to. Example: a note about the
`mc` hotkeys should yield keywords like "файловый менеджер", "CLI", "терминал",
"горячие клавиши" even though those exact words may be absent. The goal is that a
future note similar in meaning matches by words, not only by literal occurrence.
'''
        ),
        Message(
            role='user',
            content=f'''Generate a concise, descriptive name for this note:

<NOTE_CONTENT>
{truncated_content}
</NOTE_CONTENT>

IMPORTANT: Detect the language of the note content above and generate the name in THE SAME LANGUAGE.
If the note is in Russian, the name MUST be in Russian.
If the note is in English, the name MUST be in English.
NEVER mix languages in the name.

Return a JSON object with:
- "name": The generated name (3-8 words, title case, no special characters, in the SAME language as the note)
- "reasoning": Brief explanation of why you chose this name (1 sentence)
- "semantic_hints": A list of 5-12 keywords (in the SAME language as the note), including IMPLIED ones — synonyms, common names, and the class/purpose/domain of the note's terms — the words by which someone would search for this note even if they are not in the text
'''
        ),
    ]


def sanitize_filename(name: str, max_length: int = 100) -> str:
    """
    Sanitize a name to make it safe for use as a filename.

    Removes or replaces characters that are problematic for filesystems:
    - Windows: < > : " / \\ | ? *
    - Unix: / (also avoid leading .)
    - macOS: : (colon)

    Also:
    - Limits length to max_length characters
    - Strips leading/trailing whitespace
    - Collapses multiple spaces
    - Removes leading/trailing dots

    Args:
        name: The raw name to sanitize
        max_length: Maximum length for the filename (default: 100)

    Returns:
        Sanitized filename safe for all major operating systems

    Examples:
        >>> sanitize_filename("Meeting: API/Backend Design")
        'Meeting - API Backend Design'
        >>> sanitize_filename("Project | Phase 1 * Draft")
        'Project - Phase 1 - Draft'
    """
    # Replace problematic characters with dash or remove them
    # : | / \\ < > * ? " → dash (for readability)
    name = re.sub(r'[:|/\\<>*?"]+', '-', name)

    # Collapse multiple dashes/spaces
    name = re.sub(r'[-\s]+', ' ', name)

    # Strip leading/trailing whitespace and dots
    name = name.strip(' .')

    # Limit length (leaving room for .md extension)
    if len(name) > max_length:
        name = name[:max_length].rsplit(' ', 1)[0]  # Cut at word boundary

    # Final safety: ensure not empty
    if not name:
        name = "Untitled Note"

    return name


async def generate_episode_name(
    episode_body: str,
    llm_client: OpenAIGenericClient,
    max_length: int = 100
) -> tuple[str, list[str], bool]:
    """
    Generate a meaningful, filesystem-compatible name for an episode.

    Uses LLM to analyze the episode content and generate a concise,
    descriptive title suitable for use as a markdown filename in Obsidian.

    Process:
    1. Send episode content to LLM with name generation prompt
    2. LLM returns structured response with name and reasoning
    3. Sanitize the name for filesystem compatibility
    4. Return sanitized name

    This routine **never raises** for an LLM failure — it falls back to a name
    derived from the first words of the content (``_generate_fallback_name``).
    The last tuple element reports *which* path produced the name so callers
    can surface the difference (the async naming job keeps the node marked
    ``failed:generate_episode_name`` on a fallback instead of masking it; the
    sync ``create_episode`` path ignores the flag).

    Alongside the name it returns ``semantic_hints`` — keywords (including implied
    ones) used downstream to widen the ``make_suggestions`` query (suggest-extra
    lever B). On the fallback path the hints are empty (the LLM call is what
    produces them).

    Args:
        episode_body: Full content of the note/episode
        llm_client: Configured Graphiti LLM client (e.g., PatchedLLMClient)
        max_length: Maximum length for filename (default: 100 chars)

    Returns:
        ``(name, semantic_hints, used_fallback)`` — the sanitized name, the
        keyword hints (empty on fallback), and ``True`` when the LLM call failed
        and the name is a text-derived fallback.

    Example:
        >>> from app.services.graphiti.setup_graphiti import get_graphiti
        >>> graphiti = await get_graphiti()
        >>> name, hints, used_fallback = await generate_episode_name(
        ...     episode_body="Today we discussed the new API architecture...",
        ...     llm_client=graphiti.clients.llm_client
        ... )
        >>> print(name)  # "API Architecture Discussion"
    """
    try:
        logger.info("[generate_episode_name] Generating name from episode content")

        # Create prompt
        messages = create_name_generation_prompt(episode_body)

        # Call LLM
        response = await llm_client.generate_response(
            messages,
            response_model=EpisodeName
        )

        # Validate response
        result = EpisodeName(**response)

        logger.info(
            f"[generate_episode_name] LLM generated: '{result.name}' "
            f"(reasoning: {result.reasoning})"
        )

        # Sanitize for filesystem
        sanitized_name = sanitize_filename(result.name, max_length=max_length)

        if sanitized_name != result.name:
            logger.info(
                f"[generate_episode_name] Sanitized: '{result.name}' → '{sanitized_name}'"
            )

        # Normalize hints: strip blanks, drop empties (cheap, defensive — small
        # models occasionally emit padding entries).
        hints = [h.strip() for h in (result.semantic_hints or []) if h and h.strip()]
        logger.info(f"[generate_episode_name] semantic_hints ({len(hints)}): {hints}")

        return sanitized_name, hints, False

    except Exception as e:
        logger.error(f"[generate_episode_name] Error generating name: {e}", exc_info=True)
        # Fallback: use first few words of content. No hints — the LLM call that
        # would produce them is exactly what failed.
        fallback_name = _generate_fallback_name(episode_body)
        logger.warning(f"[generate_episode_name] Using fallback name: '{fallback_name}'")
        return fallback_name, [], True


def _generate_fallback_name(episode_body: str, max_words: int = 5) -> str:
    """
    Generate a fallback name from episode content when LLM fails.

    Takes first few words of the content and sanitizes them.

    Args:
        episode_body: Episode content
        max_words: Maximum number of words to use (default: 5)

    Returns:
        Sanitized fallback name
    """
    # Take first line or first max_words words
    first_line = episode_body.split('\n')[0].strip()

    # Remove markdown syntax
    first_line = re.sub(r'[#*`\[\]]+', '', first_line)

    # Take first N words
    words = first_line.split()[:max_words]
    fallback = ' '.join(words)

    # Sanitize
    if fallback:
        return sanitize_filename(fallback, max_length=50)
    else:
        return "Untitled Note"
