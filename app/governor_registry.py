"""Governor registry loader — fetches governors.json from GitHub (raw) with local cache.

The canonical governors.json is committed to the repo by the GitHub Actions workflow
``.github/workflows/refresh-governors.yml``.  The EC2 service fetches it via
``raw.githubusercontent.com`` and caches it in memory (with TTL) so auth checks
are fast and survive brief GitHub outages.

Environment:
    GOVERNORS_RAW_URL     — override the raw-GitHub URL
    GOVERNORS_CACHE_TTL   — cache TTL in seconds (default: 300)
    STATIC_GOVERNORS_JSON — local fallback file path (optional)
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx

from .config import settings

_DEFAULT_RAW_URL = (
    "https://raw.githubusercontent.com/TrueSightDAO/governor_chatbot_service/main/governors.json"
)
_CACHE_TTL_SECONDS = int(os.getenv("GOVERNORS_CACHE_TTL", "300"))

# In-memory cache
_cache: dict[str, any] = {
    "data": None,
    "fetched_at": 0.0,
    "url": None,
}


def _now() -> float:
    return time.time()


def _load_local(path: Path) -> dict | None:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _fetch_remote(url: str) -> dict:
    resp = httpx.get(url, timeout=15.0)
    resp.raise_for_status()
    return resp.json()


def load_governors(force_refresh: bool = False) -> dict:
    """Load the canonical governors.json with caching.

    Resolution order:
        1. In-memory cache (if TTL not expired and not forced)
        2. Remote raw-GitHub URL
        3. Local STATIC_GOVERNORS_JSON fallback
        4. Empty permissive fallback (dev mode)

    Returns a dict with keys: version, updated_at, source, spreadsheet_id, governors.
    """
    global _cache

    now = _now()
    cache_url = os.getenv("GOVERNORS_RAW_URL", _DEFAULT_RAW_URL)

    # 1. Memory cache hit
    if not force_refresh and _cache["data"] is not None:
        if _cache["url"] == cache_url and (now - _cache["fetched_at"]) < _CACHE_TTL_SECONDS:
            return _cache["data"]

    # 2. Try remote
    try:
        data = _fetch_remote(cache_url)
        _cache["data"] = data
        _cache["fetched_at"] = now
        _cache["url"] = cache_url
        return data
    except Exception as exc:
        # Log but don't crash — fall through to local fallback
        import logging
        logging.getLogger(__name__).warning("Failed to fetch remote governors.json: %s", exc)

    # 3. Local fallback
    local_path = settings.static_governors_json
    if local_path is not None:
        # Resolve relative to repo root
        if not local_path.is_absolute():
            repo_root = Path(__file__).resolve().parent.parent
            local_path = repo_root / local_path
        data = _load_local(local_path)
        if data is not None:
            _cache["data"] = data
            _cache["fetched_at"] = now
            _cache["url"] = str(local_path)
            return data

    # 4. Empty permissive fallback (dev)
    return {
        "version": 1,
        "updated_at": "",
        "source": "fallback",
        "spreadsheet_id": "",
        "governors": [],
    }


def is_governor(public_key_b64: str) -> bool:
    """Return True if the given SPKI public key is in the governor registry."""
    data = load_governors()
    governors = data.get("governors", [])
    if not governors:
        return True  # permissive in dev when list is empty
    for g in governors:
        if g.get("public_key") == public_key_b64:
            return True
    return False


def refresh_cache() -> dict:
    """Force a fresh fetch and return the new data."""
    return load_governors(force_refresh=True)
