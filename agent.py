"""Earnings reporting agent.

Interactive terminal agent: ask it for ticker symbols and it builds one
CSV row per symbol - earnings surprise %, date, and market / Fed / economy
signals - formatted for an algorithmic trading program.

Data flow per symbol:
  cached data first (data/cache/) -> fetch only what's missing ->
  rule-based signals -> LLM writes the notes column -> append to
  data/exports/earnings_report_YYYYMMDD.csv

Run:  python agent.py      (or double-click run_agent.bat)
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from core import cache, csv_writer, llm
from skills import earnings_skill, market_skill, fed_skill, econ_skill

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_ROOT / "config" / "settings.json"
WATCHLIST_PATH = PROJECT_ROOT / "config" / "symbols_watchlist.txt"
LOG_DIR = PROJECT_ROOT / "logs"

# How much each signal contributes to composite_score
WEIGHTS = {"earnings": 0.5, "market": 0.2, "fed": 0.15, "econ": 0.15}

BANNER = """
==============================================================
  Earnings Agent - reports earnings + macro signals to CSV
==============================================================
  Enter ticker symbols (comma-separated), e.g.:  AAPL, MSFT
  Commands:  all   = run every symbol in the watchlist
             list  = show the watchlist
             quit  = exit
  Output: data\\exports\\earnings_report_YYYYMMDD.csv
==============================================================
"""


def setup_logging():
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        filename=LOG_DIR / f"agent_{datetime.now():%Y%m%d}.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def load_settings():
    settings = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    # Environment variables win over settings.json so keys can stay out of the file
    settings["anthropic_api_key"] = os.environ.get("ANTHROPIC_API_KEY") or settings.get("anthropic_api_key", "")
    settings["finnhub_api_key"] = os.environ.get("FINNHUB_API_KEY") or settings.get("finnhub_api_key", "")
    settings["fred_api_key"] = os.environ.get("FRED_API_KEY") or settings.get("fred_api_key", "")
    return settings


def load_watchlist():
    if not WATCHLIST_PATH.exists():
        return []
    lines = WATCHLIST_PATH.read_text(encoding="utf-8").splitlines()
    return [ln.strip().upper() for ln in lines if ln.strip() and not ln.strip().startswith("#")]


def cache_tag(from_cache):
    return "cache" if from_cache else "fetched"


def process_symbol(symbol, settings):
    """Build, print, and export one report row. Returns the row or None."""
    print(f"\n--- {symbol} ---")
    logging.info("processing %s", symbol)

    try:
        earnings = earnings_skill.find(symbol, settings["finnhub_api_key"])
    except Exception as exc:
        print(f"  earnings lookup failed: {exc}")
        logging.error("earnings %s: %s", symbol, exc)
        return None
    if earnings is None:
        print("  no earnings data available for this symbol - skipped.")
        return None
    print(f"  earnings [{cache_tag(earnings['from_cache'])}]: "
          f"{earnings['earnings_date']}  actual {earnings['eps_actual']} "
          f"vs est {earnings['eps_estimate']}  -> surprise {earnings['surprise_pct']}%")

    market = fed = econ = None
    try:
        market = market_skill.find(symbol, settings["finnhub_api_key"])
        if market:
            print(f"  market   [{cache_tag(market['from_cache'])}]: "
                  f"SPY {market['market_change_pct']:+}%")
    except Exception as exc:
        print(f"  market lookup failed: {exc}")
        logging.error("market %s: %s", symbol, exc)

    if settings["fred_api_key"]:
        try:
            fed = fed_skill.find(settings["fred_api_key"])
            if fed:
                print(f"  fed      [{cache_tag(fed['from_cache'])}]: "
                      f"funds rate {fed['fed_funds_rate']}% "
                      f"({fed['rate_change']:+}pp vs prior month)")
            econ = econ_skill.find(settings["fred_api_key"])
            if econ:
                print(f"  economy  [{cache_tag(econ['from_cache'])}]: "
                      f"inflation {econ['inflation_yoy_pct']}% YoY, "
                      f"unemployment {econ['unemployment_pct']}%")
        except Exception as exc:
            print(f"  FRED lookup failed: {exc}")
            logging.error("fred/econ: %s", exc)
    else:
        print("  fed/econ skipped (no FRED api key in config/settings.json)")

    signals = {
        "earnings": earnings["signal"],
        "market": market["signal"] if market else 0,
        "fed": fed["signal"] if fed else 0,
        "econ": econ["signal"] if econ else 0,
    }
    composite = round(sum(WEIGHTS[k] * v for k, v in signals.items()), 3)

    row = {
        "symbol": symbol,
        "earnings_date": earnings["earnings_date"],
        "eps_actual": earnings["eps_actual"],
        "eps_estimate": earnings["eps_estimate"],
        "surprise_pct": earnings["surprise_pct"],
        "earnings_signal": signals["earnings"],
        "market_signal": signals["market"],
        "fed_signal": signals["fed"],
        "econ_signal": signals["econ"],
        "composite_score": composite,
    }

    raw_context = {"earnings": earnings, "market": market, "fed": fed, "econ": econ}
    row["notes"] = llm.write_notes(row, raw_context, settings)

    path = csv_writer.append_row(row)
    print(f"  signals: earnings {signals['earnings']:+d}  market {signals['market']:+d}  "
          f"fed {signals['fed']:+d}  econ {signals['econ']:+d}  "
          f"-> composite {composite:+.3f}")
    print(f"  notes: {row['notes']}")
    print(f"  saved -> {path.relative_to(PROJECT_ROOT)}")
    logging.info("exported %s composite=%s", symbol, composite)
    return row


def main():
    setup_logging()
    settings = load_settings()
    cache.configure(settings.get("cache_rules", {}))

    print(BANNER)
    if not settings["finnhub_api_key"]:
        print("WARNING: no Finnhub API key set (config/settings.json or FINNHUB_API_KEY).")
        print("         Earnings and market lookups will fail until one is added.\n")

    while True:
        try:
            # lstrip("﻿") drops the BOM some Windows shells prepend to piped input
            entry = input("symbols> ").lstrip("﻿").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not entry:
            continue

        command = entry.lower()
        if command in ("quit", "exit", "q"):
            break
        if command == "list":
            watchlist = load_watchlist()
            print("  watchlist: " + (", ".join(watchlist) if watchlist else "(empty)"))
            continue
        if command == "all":
            symbols = load_watchlist()
            if not symbols:
                print("  watchlist is empty (config/symbols_watchlist.txt)")
                continue
        else:
            symbols = [s.strip().upper() for s in entry.replace(";", ",").split(",") if s.strip()]

        for symbol in symbols:
            process_symbol(symbol, settings)

    print("done.")


if __name__ == "__main__":
    sys.exit(main())
