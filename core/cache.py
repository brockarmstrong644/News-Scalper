"""File-based cache. Every skill checks here FIRST before hitting an API.

Entries live in data/cache/<category>/<key>.json as
{"fetched_at": <unix ts>, "data": <payload>}.

TTLs are loaded from config/settings.json (cache_rules). A ttl of null/None
means the entry never expires (past earnings don't change).
"""

import json
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "data" / "cache"

# category -> settings key in cache_rules
_TTL_KEYS = {
    "earnings": "earnings_ttl_hours",
    "market": "market_ttl_hours",
    "fed": "fed_ttl_hours",
    "econ": "econ_ttl_hours",
}

_ttl_seconds = {}


def configure(cache_rules):
    """Call once at startup with settings['cache_rules']."""
    for category, key in _TTL_KEYS.items():
        hours = cache_rules.get(key)
        _ttl_seconds[category] = None if hours is None else hours * 3600


def _path(category, key):
    folder = CACHE_DIR / category
    folder.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)
    return folder / f"{safe}.json"


def get(category, key):
    """Return cached data, or None if missing/expired/corrupt."""
    p = _path(category, key)
    if not p.exists():
        return None
    try:
        entry = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    ttl = _ttl_seconds.get(category)
    if ttl is not None and time.time() - entry.get("fetched_at", 0) > ttl:
        return None
    return entry.get("data")


def put(category, key, data):
    p = _path(category, key)
    p.write_text(
        json.dumps({"fetched_at": time.time(), "data": data}, indent=2),
        encoding="utf-8",
    )
