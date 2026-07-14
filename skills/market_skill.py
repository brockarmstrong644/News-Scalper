"""Skill: general market conditions.

Scores the broad market as +1 / 0 / -1 using SPY's daily percent change
(Finnhub /quote). Also fetches the symbol's own quote for context.
Quotes refresh daily by default (see cache_rules in settings.json).
"""

import requests

from core import cache

FINNHUB_URL = "https://finnhub.io/api/v1/quote"
MARKET_PROXY = "SPY"
TREND_THRESHOLD_PCT = 0.5  # daily % move below this is treated as flat


def _quote(symbol, api_key):
    key = f"{symbol}_quote"
    data = cache.get("market", key)
    from_cache = data is not None
    if data is None:
        resp = requests.get(
            FINNHUB_URL,
            params={"symbol": symbol, "token": api_key},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        # Finnhub returns all-zero quotes for unknown symbols
        if data and data.get("c"):
            cache.put("market", key, data)
    return data, from_cache


def find(symbol, api_key):
    """Return market context, or None if unavailable.

    {
      "market_change_pct": 0.82, "signal": 1,
      "symbol_price": 231.4, "symbol_change_pct": -1.1,
      "from_cache": bool
    }
    """
    spy, spy_cached = _quote(MARKET_PROXY, api_key)
    if not spy or not spy.get("c"):
        return None

    change_pct = spy.get("dp") or 0.0
    if change_pct >= TREND_THRESHOLD_PCT:
        signal = 1
    elif change_pct <= -TREND_THRESHOLD_PCT:
        signal = -1
    else:
        signal = 0

    result = {
        "market_change_pct": round(change_pct, 2),
        "signal": signal,
        "symbol_price": None,
        "symbol_change_pct": None,
        "from_cache": spy_cached,
    }

    sym_quote, _ = _quote(symbol, api_key)
    if sym_quote and sym_quote.get("c"):
        result["symbol_price"] = sym_quote.get("c")
        result["symbol_change_pct"] = round(sym_quote.get("dp") or 0.0, 2)

    return result
