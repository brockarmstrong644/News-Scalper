"""Skill: earnings surprise ("sup" export).

Pulls quarterly EPS actual vs. estimate from Finnhub (/stock/earnings)
and places each quarter on its period-end date within the range.

Finnhub's free tier only returns the most recent ~4 quarters, so the
local cache works as a GROWING ARCHIVE: fresh quarters are merged into
everything collected before (refreshed daily), and nothing is ever
thrown away. The longer the agent runs, the deeper the history gets.

Columns produced (non-null only on earnings dates):
  eps_actual, eps_estimate, surprise_pct, sup_signal
"""

import requests

from core import cache

FINNHUB_URL = "https://finnhub.io/api/v1/stock/earnings"
SURPRISE_THRESHOLD_PCT = 2.0  # |surprise| below this is treated as in-line

COLUMNS = ["eps_actual", "eps_estimate", "surprise_pct", "sup_signal"]

KEY_LINES = [
    "eps_actual = reported earnings per share for the quarter",
    "eps_estimate = analyst consensus EPS estimate",
    "surprise_pct = (actual - estimate) / |estimate| * 100",
    "sup_signal = +1 beat (>= +2%), 0 in-line, -1 miss (<= -2%)",
    "values appear on the quarter period-end date; all other days are null",
    "null = no earnings event on that day",
]


def _load_quarters(symbol, api_key):
    """Return the accumulated quarter archive for symbol, refreshing from
    Finnhub when the cache is older than its TTL. Fresh quarters are MERGED
    into the archive (keyed by period) so history is never lost."""
    archive = cache.get("earnings", symbol, ignore_ttl=True) or []
    if cache.get("earnings", symbol) is None:  # missing or TTL expired
        resp = requests.get(
            FINNHUB_URL,
            params={"symbol": symbol, "token": api_key},
            timeout=15,
        )
        resp.raise_for_status()
        fresh = resp.json() or []
        by_period = {q["period"]: q for q in archive if q.get("period")}
        for q in fresh:
            if q.get("period"):
                by_period[q["period"]] = q  # newest fetch wins for same quarter
        archive = sorted(by_period.values(), key=lambda q: q["period"], reverse=True)
        cache.put("earnings", symbol, archive)  # refresh even if empty
    return archive


def fetch_range(symbol, start, end, settings):
    """Return ({date_str: {column: value}}, note) for earnings in range."""
    quarters = _load_quarters(symbol, settings["finnhub_api_key"])

    days = {}
    for q in quarters:
        period = q.get("period") or ""
        actual, estimate = q.get("actual"), q.get("estimate")
        if not (start <= period <= end) or actual is None or estimate is None:
            continue
        surprise = q.get("surprisePercent")
        if surprise is None:
            surprise = 0.0 if estimate == 0 else (actual - estimate) / abs(estimate) * 100.0
        if surprise >= SURPRISE_THRESHOLD_PCT:
            signal = 1
        elif surprise <= -SURPRISE_THRESHOLD_PCT:
            signal = -1
        else:
            signal = 0
        days[period] = {
            "eps_actual": actual,
            "eps_estimate": estimate,
            "surprise_pct": round(surprise, 2),
            "sup_signal": signal,
        }

    if not quarters:
        note = (f"Finnhub has no earnings for '{symbol}' - futures, crypto, "
                f"indexes and ETFs have no company earnings (use fed/mac for those)")
    else:
        periods = sorted(q["period"] for q in quarters if q.get("period"))
        note = (f"archive holds {len(periods)} quarter(s): {periods[0]} .. {periods[-1]}; "
                f"{len(days)} inside your range")
        if not days:
            note += (" - Finnhub's free tier only serves ~4 recent quarters; "
                     "the local archive grows each quarter the agent keeps running")
    return days, note
