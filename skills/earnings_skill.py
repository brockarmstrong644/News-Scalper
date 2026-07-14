"""Skill: earnings surprise ("sup" export).

Primary source: Yahoo Finance (yfinance) - years of quarterly history with
the ACTUAL report date (the day the market reacts), analyst EPS estimate,
reported EPS, and surprise %. Fallback: Finnhub /stock/earnings (last ~4
quarters, dated by quarter end) when Yahoo is unavailable.

The local cache works as a GROWING ARCHIVE: fresh quarters are merged into
everything collected before (refreshed daily), so history only deepens.

Columns produced (non-null only on earnings dates):
  eps_actual, eps_estimate, surprise_pct, sup_signal
"""

import requests

from core import cache

try:
    import yfinance
except ImportError:
    yfinance = None

FINNHUB_URL = "https://finnhub.io/api/v1/stock/earnings"
SURPRISE_THRESHOLD_PCT = 2.0  # |surprise| below this is treated as in-line

COLUMNS = ["eps_actual", "eps_estimate", "surprise_pct", "sup_signal"]

KEY_LINES = [
    "eps_actual = reported earnings per share for the quarter",
    "eps_estimate = analyst consensus EPS estimate",
    "surprise_pct = (actual - estimate) / |estimate| * 100",
    "sup_signal = +1 beat (>= +2%), 0 in-line, -1 miss (<= -2%)",
    "values appear on the earnings REPORT date (Yahoo source) or the quarter",
    "  period-end date (Finnhub fallback entries); all other days are null",
    "null = no earnings event on that day",
]


def _fetch_yahoo(symbol):
    """Return [{period, actual, estimate, surprisePercent, source}] from
    Yahoo, keyed by the actual report date. Raises on failure."""
    frame = yfinance.Ticker(symbol).get_earnings_dates(limit=60)
    if frame is None or frame.empty:
        return []
    quarters = []
    for ts, row in frame.iterrows():
        actual = row.get("Reported EPS")
        estimate = row.get("EPS Estimate")
        if actual is None or estimate is None:
            continue
        try:
            actual, estimate = float(actual), float(estimate)
        except (TypeError, ValueError):
            continue
        if actual != actual or estimate != estimate:  # NaN check
            continue
        surprise = row.get("Surprise(%)")
        try:
            surprise = float(surprise)
            if surprise != surprise:
                surprise = None
        except (TypeError, ValueError):
            surprise = None
        quarters.append({
            "period": ts.date().isoformat(),
            "actual": actual,
            "estimate": estimate,
            "surprisePercent": surprise,
            "source": "yahoo",
        })
    return quarters


def _fetch_finnhub(symbol, api_key):
    resp = requests.get(
        FINNHUB_URL,
        params={"symbol": symbol, "token": api_key},
        timeout=15,
    )
    resp.raise_for_status()
    quarters = []
    for q in resp.json() or []:
        if q.get("period"):
            quarters.append({**q, "source": "finnhub"})
    return quarters


def _load_quarters(symbol, settings):
    """Return (archive, source_note). Refreshes from Yahoo (primary) or
    Finnhub (fallback) when the cache TTL expires; fresh quarters are MERGED
    into the archive so history is never lost."""
    archive = cache.get("earnings", symbol, ignore_ttl=True) or []
    if cache.get("earnings", symbol) is not None:  # fresh enough
        return archive, "cache"

    fresh, source = [], None
    if yfinance is not None:
        try:
            fresh = _fetch_yahoo(symbol)
            source = "yahoo"
        except Exception:
            fresh = []
    if not fresh and settings.get("finnhub_api_key"):
        try:
            fresh = _fetch_finnhub(symbol, settings["finnhub_api_key"])
            source = "finnhub"
        except Exception:
            fresh = []

    if source == "yahoo":
        # Yahoo entries are dated by report date, Finnhub by quarter end -
        # keeping both would double-count quarters. Once Yahoo works, keep
        # only Yahoo-sourced history (it is deeper than Finnhub's anyway).
        archive = [q for q in archive if q.get("source") == "yahoo"]

    by_period = {q["period"]: q for q in archive if q.get("period")}
    for q in fresh:
        by_period[q["period"]] = q  # newest fetch wins for same date
    archive = sorted(by_period.values(), key=lambda q: q["period"], reverse=True)
    cache.put("earnings", symbol, archive)  # refresh clock even if empty
    return archive, source or "none"


def fetch_range(symbol, start, end, settings):
    """Return ({date_str: {column: value}}, note) for earnings in range."""
    quarters, source = _load_quarters(symbol, settings)

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
        note = (f"no earnings found for '{symbol}' - futures, crypto, indexes "
                f"and ETFs have no company earnings (use prc/fed/mac for those)")
    else:
        periods = sorted(q["period"] for q in quarters if q.get("period"))
        note = (f"archive holds {len(periods)} quarter(s): {periods[0]} .. "
                f"{periods[-1]}; {len(days)} inside your range")
        if source not in ("cache", "none"):
            note += f" (refreshed from {source})"
    return days, note
