"""PipGraph prompt registry — domain overrides over graphiti prompts (surface A).

This module owns the *editable text* of selected graphiti prompts. graphiti's own
prompt builders live in ``graphiti_core/prompts/*.py`` and are assembled into the
mutable global ``prompt_library`` (``prompts/lib.py``). Each operations module reads
that global **at call time**, so replacing an attribute's underlying function
propagates to the whole pipeline — the vendor files are never edited (same technique
as ``lucene_sanitize_patch``).

Two surfaces exist (see the plugin's ``.docs/plans/prompt-tuning/00-overview.md``):
  * **A. prompt text** — *this* module, applied via ``apply_prompt_overrides()``.
  * **B. response format** — ``patched_client.generate_response`` (example, not schema).

One wrapper ``_wrap(original, key)`` carries three modes per registry key:
  * ``passthrough`` — vendor prompt untouched (default for keys not in REGISTRY);
  * ``append``      — vendor prompt + our domain block tacked onto the last message;
  * ``replace``     — vendor prompt discarded, our ``build(context, block)`` runs instead.

The editable text is ``PromptEntry.block`` (``domain_block`` or ``default_domain_block``).
The **same** block feeds both ``append`` (tail) and ``replace`` (into the builder), so
the plugin's edit surface is identical regardless of mode.

Live-apply: the closure reads ``REGISTRY[key].block`` *at LLM call time*, so editing
``domain_block`` in memory (via ``PATCH /dev/prompts/{key}``) takes effect on the next
note processing **without a backend restart**. Persistence (so an edit survives a
restart) is layered on separately — see ``prompt-tuning`` Step 2.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from graphiti_core.prompts.models import Message
from graphiti_core.prompts.prompt_helpers import to_prompt_json

from app.services.graphiti.llm_config import CONFIG_DIR

logger = logging.getLogger(__name__)

# Runtime overlay (plaintext, gitignored), sibling of llm_config.json. Maps each
# user-edited key → its domain_block. Absent/empty ⇒ pure code defaults (today's
# behaviour). Only keys whose domain_block is set (not None) are persisted; a reset
# drops the key. ``mode`` is NOT persisted this iteration (fixed in code).
OVERRIDES_PATH = CONFIG_DIR / "prompt_overrides.json"


class Mode(str, Enum):
    """What ``_wrap`` does with a registry key. ``str`` mix-in keeps it JSON-friendly."""

    PASSTHROUGH = "passthrough"  # vendor prompt as-is
    APPEND = "append"  # vendor prompt + our domain block appended to the tail
    REPLACE = "replace"  # vendor prompt discarded; our builder produces the messages


@dataclass
class PromptEntry:
    """One tunable prompt.

    ``default_domain_block`` lives in code (always available for reset); ``domain_block``
    is the only persistent/editable state (``None`` ⇒ use the default). ``block`` resolves
    the two. ``build`` is the replace-mode skeleton builder (``None`` for append/passthrough).
    """

    key: str
    title: str
    description: str
    mode: Mode
    default_domain_block: str
    domain_block: Optional[str] = None
    build: Optional[Callable[[dict, str], list[Message]]] = None
    response_model: Optional[str] = None
    editable: bool = True

    @property
    def block(self) -> str:
        """The text that feeds ``_wrap`` — user edit if present, else the code default."""
        return self.domain_block if self.domain_block is not None else self.default_domain_block


# --- Replace-mode builders (skeleton in code, meaning in `block`) ----------------


def build_extract_summary(context: dict, block: str) -> list[Message]:
    """Replace-mode builder for ``extract_nodes.extract_summary``.

    The *skeleton* (message roles, ``<MESSAGES>`` framing, ``context`` placeholders)
    lives here and is read-only; the *domain meaning* (language, length, PARA accent,
    non-destructive re-summary) arrives in ``block`` and is what the user edits.

    Reads the same ``context`` keys graphiti passes to the vendor ``extract_summary``
    (``node``/``episode_content``/``previous_episodes`` — see
    ``node_operations.extract_attributes_from_node``); a vendor rename of those keys
    makes this fail *loudly*, which is the intended trade-off vs. a silent append drift.
    """
    node = context["node"]  # {'name', 'summary', 'entity_types', 'attributes'}
    ensure_ascii = context.get("ensure_ascii", False)
    return [
        Message(
            role="system",
            content=(
                "Ты составляешь summary PARA-сущности на основе MESSAGES.\n"
                f"{block}"
            ),
        ),
        Message(
            role="user",
            content=f"""
<MESSAGES>
{to_prompt_json(context["previous_episodes"], ensure_ascii=ensure_ascii, indent=2)}
{to_prompt_json(context["episode_content"], ensure_ascii=ensure_ascii, indent=2)}
</MESSAGES>

Сущность: «{node["name"]}» (роль PARA: {node["entity_types"]}).
Текущее summary (обнови, сохранив важное; если пусто — составь с нуля):
{node["summary"] or "—"}
""",
        ),
    ]


# --- Default domain blocks (editable text, code-owned source of truth for reset) --

_DEFAULT_EXTRACT_SUMMARY = (
    "Пиши на языке заметки. Не выдумывай факты вне MESSAGES. "
    "Верни не более 250 слов. Для роли PARA подчеркни её назначение "
    "(Project — что делается, Area — что поддерживается, Resource — о чём справка, "
    "Archive — что завершено). Это ре-суммаризация: обнови summary, сохранив важное "
    "из текущего, не затирая его пустым."
)

_DEFAULT_EXTRACT_TEXT = (
    "Считай сущностью-тегом значимые концепты, темы, проекты, людей и инструменты, "
    "о которых заметка реально говорит, — не служебную болтовень и не общие слова. "
    "Имена сущностей давай на языке заметки. Не извлекай даты/время и отношения как "
    "сущности."
)


# --- The registry ----------------------------------------------------------------

REGISTRY: dict[str, PromptEntry] = {
    "extract_nodes.extract_summary": PromptEntry(
        key="extract_nodes.extract_summary",
        title="Сводка сущности",
        description=(
            "Составляет summary PARA-сущности по тексту заметок (видно в Entity Inspector). "
            "Полная замена вендорного промпта под PARA."
        ),
        mode=Mode.REPLACE,
        default_domain_block=_DEFAULT_EXTRACT_SUMMARY,
        build=build_extract_summary,
        response_model="EntitySummary",
    ),
    "extract_nodes.extract_text": PromptEntry(
        key="extract_nodes.extract_text",
        title="Извлечение сущностей из текста",
        description=(
            "Решает, что в прозе заметки считать сущностью-тегом. Доменный блок "
            "дописывается в хвост вендорного промпта (append)."
        ),
        mode=Mode.APPEND,
        default_domain_block=_DEFAULT_EXTRACT_TEXT,
        build=None,
        response_model="ExtractedEntities",
    ),
}


# --- Persistence (overlay file, mirrors llm_config.py) ---------------------------


def read_overrides() -> dict:
    """Read the overlay file. Returns ``{}`` if absent or unreadable."""
    if not OVERRIDES_PATH.exists():
        return {}
    try:
        with OVERRIDES_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read prompt overrides %s: %s", OVERRIDES_PATH, exc)
        return {}


def write_overrides(data: dict) -> None:
    """Atomically write the overlay file (temp file + ``os.replace``)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(CONFIG_DIR), prefix=".prompt_overrides.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, OVERRIDES_PATH)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _persist() -> None:
    """Write every user-set (``domain_block is not None``) entry to the overlay file.

    A reset (``domain_block = None``) makes the key disappear from the file ⇒ default on
    next load. An explicit empty string is a deliberate "empty block" and *is* stored.
    """
    data = {k: e.domain_block for k, e in REGISTRY.items() if e.domain_block is not None}
    write_overrides(data)


def load_persisted_overrides() -> None:
    """Apply the overlay file into ``REGISTRY[*].domain_block``.

    Keys present in the file get their stored block; keys absent fall back to ``None``
    (the code default). Unknown keys in the file are ignored (vendor/registry drift).
    """
    data = read_overrides()
    for key, entry in REGISTRY.items():
        stored = data.get(key)
        entry.domain_block = stored if isinstance(stored, str) else None


def set_domain_block(key: str, block: str) -> None:
    """Set a key's editable block in memory (live) and persist it. Raises ``KeyError``.

    If the file write fails, the in-memory change is rolled back so the live state never
    diverges from what's persisted (no silent apply-with-error).
    """
    entry = REGISTRY[key]
    previous = entry.domain_block
    entry.domain_block = block
    try:
        _persist()
    except Exception:
        entry.domain_block = previous
        raise


def reset_domain_block(key: str) -> None:
    """Reset a key to its code default (``domain_block = None``) and persist. ``KeyError``.

    Rolls back the in-memory change if the file write fails (see ``set_domain_block``).
    """
    entry = REGISTRY[key]
    previous = entry.domain_block
    entry.domain_block = None
    try:
        _persist()
    except Exception:
        entry.domain_block = previous
        raise


# --- The wrapper + application ----------------------------------------------------


def _wrap(original: Callable[[dict], list[Message]], key: str) -> Callable[[dict], list[Message]]:
    """Wrap a vendor prompt builder with the registry's mode for ``key``.

    Reads ``REGISTRY[key]`` (and its ``block``) on every call → edits to the in-memory
    entry apply live, without rebuilding anything.
    """

    def fn(context: dict) -> list[Message]:
        spec = REGISTRY.get(key)
        if spec is None or spec.mode is Mode.PASSTHROUGH:
            return original(context)  # vendor untouched
        if spec.mode is Mode.REPLACE:
            if spec.build is None:  # defensive: replace without a builder ⇒ vendor
                logger.warning("prompt %r is REPLACE but has no builder; passing through", key)
                return original(context)
            return spec.build(context, spec.block)
        # APPEND
        messages = original(context)
        messages[-1].content += (
            f"\n\n<ADDITIONAL GUIDELINES>\n{spec.block}\n</ADDITIONAL GUIDELINES>"
        )
        return messages

    return fn


_applied = False


def apply_prompt_overrides() -> None:
    """Monkeypatch ``prompt_library`` for the registry keys. Idempotent.

    Wraps the *underlying* function (``VersionWrapper.func``), so graphiti's
    ``DO_NOT_ESCAPE_UNICODE`` post-processing still runs around our output. Call once at
    import time from ``setup_graphiti``, next to ``apply_patch()``.
    """
    global _applied
    if _applied:
        return

    # Hydrate REGISTRY from the persisted overlay so edits survive restarts.
    load_persisted_overrides()

    import graphiti_core.prompts.lib as lib

    pl = lib.prompt_library
    pl.extract_nodes.extract_summary.func = _wrap(
        pl.extract_nodes.extract_summary.func, "extract_nodes.extract_summary"
    )
    pl.extract_nodes.extract_text.func = _wrap(
        pl.extract_nodes.extract_text.func, "extract_nodes.extract_text"
    )

    _applied = True
    logger.info("PipGraph prompt overrides applied: %s", ", ".join(REGISTRY))
