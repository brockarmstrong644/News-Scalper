"""Skill: daily prices ("prc" export).

Daily OHLCV series from Yahoo Finance (yfinance) for any symbol - stocks,
ETFs, indexes, crypto, and futures. Plain futures roots are mapped
automatically: NQ -> NQ=F, ES -> ES=F, etc.

Columns produced per day (null on non-trading days):
  open, high, low, close, volume, change_pct, prc_signal
"""

from core import cache

try:
    import yfinance
except ImportError:
    yfinance = None

DAY_MOVE_PCT = 0.5  # daily % move below this is treated as flat

COLUMNS = ["open", "high", "low", "close", "volume", "change_pct", "prc_signal"]

KEY_LINES = [
    "open / high / low / close = daily trading prices (Yahoo Finance)",
    "volume = shares/contracts traded",
    "change_pct = percent change of close vs previous close",
    "prc_signal = +1 day up >= 0.5%, 0 flat, -1 day down <= -0.5%",
    "futures roots are mapped automatically (NQ -> NQ=F, ES -> ES=F)",
    "null = market closed / no trading that day",
]


def _candidates(symbol):
    """Ticker spellings to try, in order."""
    tickers = [symbol]
    if symbol.isalpha() and len(symbol) <= 3:
        tickers.append(f"{symbol}=F")   # futures root (NQ, ES, CL, GC ...)
    return tickers


def _download(ticker, start, end):
    """Return [[date, o, h, l, c, v], ...] or []. Raises on network errors."""
    frame = yfinance.Ticker(ticker).history(
        start=start, end=end, interval="1d", auto_adjust=False,
    )
    if frame is None or frame.empty:
        return []
    rows = []
    for ts, row in frame.iterrows():
        close = row.get("Close")
        if close is None or close != close:
            continue
        rows.append([
            ts.date().isoformat(),
            round(float(row["Open"]), 4),
            round(float(row["High"]), 4),
            round(float(row["Low"]), 4),
            round(float(close), 4),
            int(row.get("Volume") or 0),
        ])
    return rows


def fetch_range(symbol, start, end, settings):
    """Return ({date_str: {column: value}}, note)."""
    if yfinance is None:
        raise RuntimeError("yfinance is not installed - run: pip install -r requirements.txt")

    key = f"{symbol}_{start}_{end}"
    cached = cache.get("market", key)
    used = None
    if cached is not None:
        rows, used = cached.get("rows", []), cached.get("ticker")
    else:
        rows = []
        for ticker in _candidates(symbol):
            try:
                rows = _download(ticker, start, end)
            except Exception:
                rows = []
            if rows:
                used = ticker
                break
        cache.put("market", key, {"ticker": used, "rows": rows})

    days = {}
    prev_close = None
    for date, o, h, l, c, v in rows:
        change = None if prev_close is None else (c / prev_close - 1.0) * 100.0
        if change is None:
            signal = 0
        elif change >= DAY_MOVE_PCT:
            signal = 1
        elif change <= -DAY_MOVE_PCT:
            signal = -1
        else:
            signal = 0
        days[date] = {
            "open": o, "high": h, "low": l, "close": c, "volume": v,
            "change_pct": round(change, 2) if change is not None else 0.0,
            "prc_signal": signal,
        }
        prev_close = c

    if not days:
        note = (f"Yahoo has no price data for '{symbol}'"
                + (f" (also tried {symbol}=F)" if len(_candidates(symbol)) > 1 else "")
                + " - check the ticker spelling")
    elif used and used != symbol:
        note = f"mapped '{symbol}' to Yahoo ticker '{used}' (futures contract)"
    else:
        note = None
    return days, note
