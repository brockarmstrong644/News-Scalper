"""Skill: general economic conditions.

Scores the economy as +1 / 0 / -1 from two FRED series:
  - CPIAUCSL -> year-over-year inflation
  - UNRATE   -> unemployment rate and its direction

Heuristic: inflation <= 3% and unemployment not rising -> +1;
inflation > 4% or unemployment rising by >= 0.2pp -> -1; otherwise 0.
Refreshes weekly by default (see cache_rules in settings.json).
"""

import requests

from core import cache

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"

INFLATION_GOOD_MAX = 3.0
INFLATION_BAD_MIN = 4.0
UNEMPLOYMENT_RISE_BAD = 0.2  # percentage-point rise treated as deteriorating


def _series(series_id, api_key, limit):
    observations = cache.get("econ", series_id)
    from_cache = observations is not None
    if observations is None:
        resp = requests.get(
            FRED_URL,
            params={
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": limit,
            },
            timeout=15,
        )
        resp.raise_for_status()
        observations = resp.json().get("observations", [])
        if observations:
            cache.put("econ", series_id, observations)
    values = [o for o in (observations or []) if o.get("value") not in (None, ".")]
    return values, from_cache


def find(api_key):
    """Return economic context, or None if unavailable.

    {
      "inflation_yoy_pct": 2.7, "unemployment_pct": 4.1,
      "unemployment_change": 0.0, "signal": 1, "from_cache": bool
    }
    """
    cpi, cpi_cached = _series("CPIAUCSL", api_key, 13)
    unrate, un_cached = _series("UNRATE", api_key, 2)

    if len(cpi) < 13 or len(unrate) < 2:
        return None

    cpi_now = float(cpi[0]["value"])
    cpi_year_ago = float(cpi[12]["value"])
    inflation = (cpi_now / cpi_year_ago - 1.0) * 100.0

    unemployment = float(unrate[0]["value"])
    unemployment_change = unemployment - float(unrate[1]["value"])

    if inflation > INFLATION_BAD_MIN or unemployment_change >= UNEMPLOYMENT_RISE_BAD:
        signal = -1
    elif inflation <= INFLATION_GOOD_MAX and unemployment_change < UNEMPLOYMENT_RISE_BAD:
        signal = 1
    else:
        signal = 0

    return {
        "inflation_yoy_pct": round(inflation, 2),
        "unemployment_pct": unemployment,
        "unemployment_change": round(unemployment_change, 2),
        "signal": signal,
        "from_cache": cpi_cached and un_cached,
    }
