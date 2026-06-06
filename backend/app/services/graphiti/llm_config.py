"""
Active LLM configuration: provider defaults (from settings) + runtime file overlay.

The Graphiti singleton (see ``setup_graphiti.get_graphiti``) is built from
``resolve_active_config()``. Defaults come from ``config/settings.py`` for the
selected ``LLM_PROVIDER``; an optional runtime overlay file
(``config/llm_config.json``, gitignored) overrides individual fields.

The overlay is written by the ``/dev/llm-config`` endpoints and applied on backend
**restart** — the running singleton is never rebuilt in place. To answer
"does a restart change anything?" honestly, ``get_graphiti`` snapshots the config it
actually built on (``snapshot_active_config``); comparing that snapshot to the current
``resolve_active_config()`` yields ``restart_required``.

Security: the overlay holds ``api_key`` in plaintext (gitignored), consistent with the
plaintext ``.env`` and the plugin's plaintext ``data.json``. Noted as a constraint,
not solved here.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from config.settings import settings

logger = logging.getLogger(__name__)

PROVIDERS = ("cloudru", "openrouter")

# Runtime overlay file (plaintext, gitignored). Absent => pure settings defaults.
# __file__ = backend/app/services/graphiti/llm_config.py -> parents[3] = backend
CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"
OVERLAY_PATH = CONFIG_DIR / "llm_config.json"

# Fields the overlay/endpoints may set (besides "provider").
_OVERLAY_FIELDS = ("base_url", "api_key", "main_model", "small_model", "embedding_model")


@dataclass(frozen=True)
class ActiveLLMConfig:
    provider: str
    base_url: str
    api_key: str
    main_model: str
    small_model: str
    embedding_model: str


def _provider_defaults(provider: str) -> dict:
    """Default base_url + api_key + models for a provider, drawn from settings."""
    if provider == "openrouter":
        return {
            "base_url": settings.OPENROUTER_BASE_URL,
            "api_key": settings.OPENROUTER_API_KEY,
            "main_model": settings.OPENROUTER_MAIN_MODEL,
            "small_model": settings.OPENROUTER_SMALL_MODEL,
            "embedding_model": settings.OPENROUTER_EMBEDDING_MODEL,
        }
    # default + explicit "cloudru"
    return {
        "base_url": settings.CLOUDRU_BASE_URL,
        "api_key": settings.CLOUDRU_API_KEY,
        "main_model": settings.CLOUDRU_MAIN_MODEL,
        "small_model": settings.CLOUDRU_SMALL_MODEL,
        "embedding_model": settings.CLOUDRU_EMBEDDING_MODEL,
    }


def provider_catalog() -> dict[str, dict]:
    """Public per-provider defaults (base_url + models) for clients to prefill.

    Excludes ``api_key`` — keys are never handed back to clients.
    """
    catalog: dict[str, dict] = {}
    for provider in PROVIDERS:
        defaults = _provider_defaults(provider)
        catalog[provider] = {
            "base_url": defaults["base_url"],
            "main_model": defaults["main_model"],
            "small_model": defaults["small_model"],
            "embedding_model": defaults["embedding_model"],
        }
    return catalog


def read_overlay() -> dict:
    """Read the runtime overlay file. Returns ``{}`` if absent or unreadable."""
    if not OVERLAY_PATH.exists():
        return {}
    try:
        with OVERLAY_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read LLM overlay %s: %s", OVERLAY_PATH, exc)
        return {}


def write_overlay(data: dict) -> None:
    """Atomically write the overlay file (temp file + ``os.replace``)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(CONFIG_DIR), prefix=".llm_config.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, OVERLAY_PATH)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def clear_overlay() -> bool:
    """Delete the overlay file. Returns ``True`` if a file was actually removed."""
    try:
        OVERLAY_PATH.unlink()
        return True
    except FileNotFoundError:
        return False


def resolve_active_config() -> ActiveLLMConfig:
    """Build the active config: provider defaults overlaid with the runtime file.

    Provider precedence: overlay ``provider`` → ``settings.LLM_PROVIDER``. Each field
    falls back to the *resolved provider's* default when the overlay omits it (or
    leaves it empty).
    """
    overlay = read_overlay()

    provider = overlay.get("provider") or settings.LLM_PROVIDER
    if provider not in PROVIDERS:
        fallback = settings.LLM_PROVIDER if settings.LLM_PROVIDER in PROVIDERS else "cloudru"
        logger.warning(
            "Unknown LLM provider %r; falling back to %r", provider, fallback
        )
        provider = fallback

    defaults = _provider_defaults(provider)

    def pick(key: str) -> str:
        value = overlay.get(key)
        return value if value else defaults[key]

    return ActiveLLMConfig(
        provider=provider,
        base_url=pick("base_url"),
        api_key=pick("api_key"),
        main_model=pick("main_model"),
        small_model=pick("small_model"),
        embedding_model=pick("embedding_model"),
    )


# --- Active-config snapshot (what the running singleton was actually built on) ---

_active_snapshot: Optional[ActiveLLMConfig] = None


def snapshot_active_config() -> ActiveLLMConfig:
    """Capture and store the config the singleton is being built on. Call once at build."""
    global _active_snapshot
    _active_snapshot = resolve_active_config()
    return _active_snapshot


def get_active_snapshot() -> Optional[ActiveLLMConfig]:
    """The config the running singleton was built on, or ``None`` before first build."""
    return _active_snapshot
