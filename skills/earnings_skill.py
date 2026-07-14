"""Skill: earnings surprise ("sup" export).

Pulls quarterly EPS actual vs. estimate from Finnhub (/stock/earnings)
and places each quarter on its period-end date within the range.

Columns produced (non-null only on earnings dates):
  eps_actual, eps_estimate, surprise_pct, sup_signal

Note: Finnhub's free tier returns roughly the last four reported
quarters, so very old date ranges may have empty files.
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


def fetch_range(symbol, start, end, settings):
    """Return {date_str: {column: value}} for earnings events in range."""
    quarters = cache.get("earnings", symbol)
    if quarters is None:
        resp = requests.get(
            FINNHUB_URL,
            params={"symbol": symbol, "token": settings["finnhub_api_key"]},
            timeout=15,
        )
        resp.raise_for_status()
        quarters = resp.json()
        if quarters:
            cache.put("earnings", symbol, quarters)

    days = {}
    for q in quarters or []:
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
    return days
