"""Skill: Federal Reserve policy.

Scores Fed policy direction as +1 / 0 / -1 from the effective federal
funds rate (FRED series FEDFUNDS): falling rates = +1 (easing, generally
bullish), rising = -1 (tightening), flat = 0.
Refreshes weekly by default (see cache_rules in settings.json).
"""

import requests

from core import cache

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
SERIES = "FEDFUNDS"
FLAT_THRESHOLD = 0.01  # percentage-point change treated as unchanged


def find(api_key):
    """Return Fed context, or None if unavailable.

    {
      "fed_funds_rate": 4.33, "prev_rate": 4.58,
      "rate_change": -0.25, "signal": 1, "as_of": "2026-06-01",
      "from_cache": bool
    }
    """
    observations = cache.get("fed", SERIES)
    from_cache = observations is not None

    if observations is None:
        resp = requests.get(
            FRED_URL,
            params={
                "series_id": SERIES,
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 3,
            },
            timeout=15,
        )
        resp.raise_for_status()
        observations = resp.json().get("observations", [])
        if observations:
            cache.put("fed", SERIES, observations)

    values = [o for o in (observations or []) if o.get("value") not in (None, ".")]
    if len(values) < 2:
        return None

    latest, prev = float(values[0]["value"]), float(values[1]["value"])
    change = latest - prev

    if change <= -FLAT_THRESHOLD:
        signal = 1
    elif change >= FLAT_THRESHOLD:
        signal = -1
    else:
        signal = 0

    return {
        "fed_funds_rate": latest,
        "prev_rate": prev,
        "rate_change": round(change, 2),
        "signal": signal,
        "as_of": values[0].get("date", ""),
        "from_cache": from_cache,
    }
