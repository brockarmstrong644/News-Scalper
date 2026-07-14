"""Skill: company earnings.

Finds the most recent quarterly EPS actual vs. estimate for a symbol
(Finnhub /stock/earnings) and scores the surprise as +1 / 0 / -1.
Cached data is used first; past earnings never expire.
"""

import requests

from core import cache

FINNHUB_URL = "https://finnhub.io/api/v1/stock/earnings"
SURPRISE_THRESHOLD_PCT = 2.0  # |surprise| below this is treated as neutral


def find(symbol, api_key):
    """Return the latest earnings report for symbol, or None if unavailable.

    {
      "earnings_date": "2026-03-31",
      "eps_actual": 1.52, "eps_estimate": 1.43,
      "surprise_pct": 6.29, "signal": 1,
      "from_cache": bool
    }
    """
    quarters = cache.get("earnings", symbol)
    from_cache = quarters is not None

    if quarters is None:
        resp = requests.get(
            FINNHUB_URL,
            params={"symbol": symbol, "token": api_key},
            timeout=15,
        )
        resp.raise_for_status()
        quarters = resp.json()
        if quarters:
            cache.put("earnings", symbol, quarters)

    if not quarters:
        return None

    latest = quarters[0]  # Finnhub returns most recent quarter first
    actual = latest.get("actual")
    estimate = latest.get("estimate")
    if actual is None or estimate is None:
        return None

    surprise_pct = latest.get("surprisePercent")
    if surprise_pct is None:
        if estimate == 0:
            surprise_pct = 0.0
        else:
            surprise_pct = (actual - estimate) / abs(estimate) * 100.0

    if surprise_pct >= SURPRISE_THRESHOLD_PCT:
        signal = 1
    elif surprise_pct <= -SURPRISE_THRESHOLD_PCT:
        signal = -1
    else:
        signal = 0

    return {
        "earnings_date": latest.get("period", ""),
        "eps_actual": actual,
        "eps_estimate": estimate,
        "surprise_pct": round(surprise_pct, 2),
        "signal": signal,
        "from_cache": from_cache,
    }
