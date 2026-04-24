"""Governor registry loader — reads dao_members.json from treasury-cache (GitHub raw).

Primary source:
    https://raw.githubusercontent.com/TrueSightDAO/treasury-cache/main/dao_members.json

This file is auto-published by dao_members_cache_publisher.gs on every
[EMAIL VERIFICATION EVENT] activation + daily cron.  It contains every
ACTIVE public key for every DAO contributor.

The chatbot restricts access to a hardcoded list of governor names (env var
GOVERNOR_NAMES, default: "Gary Teh").  Only contributors whose name is in that
list AND whose public key has status ACTIVE are allowed.

Environment:
    DAO_MEMBERS_RAW_URL  — override the raw-GitHub URL
    GOVERNORS_CACHE_TTL  — cache TTL in seconds (default: 300)
    GOVERNOR_NAMES       — comma-separated display names (default: "Gary Teh")
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx

from .config import settings

_DEFAULT_MEMBERS_URL = (
    "https://raw.githubusercontent.com/TrueSightDAO/treasury-cache/main/dao_members.json"
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


def _governor_names() -> set[str]:
    """Return the set of authorized governor display names."""
    raw = os.getenv("GOVERNOR_NAMES", "Gary Teh")
    return {name.strip() for name in raw.split(",") if name.strip()}


def _extract_governor_keys(members_data: dict) -> list[dict]:
    """Scan dao_members.json and return governor records for allowed names."""
    allowed = _governor_names()
    governors: list[dict] = []
    for contributor in members_data.get("contributors", []):
        name = contributor.get("name", "").strip()
        if name not in allowed:
            continue
        for key_entry in contributor.get("public_keys", []):
            if key_entry.get("status", "").upper() != "ACTIVE":
                continue
            governors.append({
                "public_key": key_entry["public_key"],
                "name": name,
                "email": contributor.get("email", ""),
                "status": "Governor",
                "key_created_at": key_entry.get("created_at", ""),
                "key_last_active_at": key_entry.get("last_active_at", ""),
            })
    return governors


def load_governors(force_refresh: bool = False) -> dict:
    """Load the canonical governor registry with caching.

    Resolution order:
        1. In-memory cache (if TTL not expired and not forced)
        2. Remote raw-GitHub URL (dao_members.json)
        3. Local STATIC_GOVERNORS_JSON fallback
        4. Empty list (deny-all; no permissive dev fallback)

    Returns a dict with keys: version, updated_at, source, governors.
    """
    global _cache

    now = _now()
    cache_url = os.getenv("GOVERNORS_RAW_URL", _DEFAULT_MEMBERS_URL)

    # 1. Memory cache hit
    if not force_refresh and _cache["data"] is not None:
        if _cache["url"] == cache_url and (now - _cache["fetched_at"]) < _CACHE_TTL_SECONDS:
            return _cache["data"]

    # 2. Try remote
    try:
        members_data = _fetch_remote(cache_url)
        governors = _extract_governor_keys(members_data)
        data = {
            "version": 2,
            "updated_at": members_data.get("generated_at", ""),
            "source": cache_url,
            "governors": governors,
        }
        _cache["data"] = data
        _cache["fetched_at"] = now
        _cache["url"] = cache_url
        return data
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Failed to fetch remote dao_members.json: %s", exc)

    # 3. Local fallback
    local_path = settings.static_governors_json
    if local_path is not None:
        if not local_path.is_absolute():
            repo_root = Path(__file__).resolve().parent.parent
            local_path = repo_root / local_path
        data = _load_local(local_path)
        if data is not None:
            _cache["data"] = data
            _cache["fetched_at"] = now
            _cache["url"] = str(local_path)
            return data

    # 4. Deny-all fallback (never permissive)
    return {
        "version": 2,
        "updated_at": "",
        "source": "deny-all",
        "governors": [],
    }


def is_governor(public_key_b64: str) -> bool:
    """Return True if the given SPKI public key belongs to an authorized governor."""
    data = load_governors()
    governors = data.get("governors", [])
    for g in governors:
        if g.get("public_key") == public_key_b64:
            return True
    return False


def refresh_cache() -> dict:
    """Force a fresh fetch and return the new data."""
    return load_governors(force_refresh=True)
