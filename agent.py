"""NewsScalper export agent.

Interactive terminal agent that exports purely mechanical market signals
as daily CSV time series for an algorithmic trading program.

Flow per export:
  symbol(s) -> signal type (sup / fed / mac) -> date range (MM-YYYY..MM-YYYY)
  -> one CSV per symbol, one row per calendar day ('null' where no data),
     with a KEY block at the head of the file explaining every column.

Files land on the Desktop:  NewsScalper Data/<SYMBOL>/
  <SYMBOL>-<MM-YYYY>-<MM-YYYY>-<sup|fed|mac>.csv

Run:  python agent.py      (or double-click run_agent.bat)
"""

import calendar
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

try:
    import msvcrt  # Windows-only: used for the auto-dash date input
except ImportError:
    msvcrt = None

from core import cache, csv_writer, sync
from skills import earnings_skill, fed_skill, econ_skill

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_ROOT / "config" / "settings.json"
WATCHLIST_PATH = PROJECT_ROOT / "config" / "symbols_watchlist.txt"
LOG_DIR = PROJECT_ROOT / "logs"

SKILLS = {
    "sup": ("Earnings surprise", earnings_skill),
    "fed": ("Federal Reserve", fed_skill),
    "mac": ("Macroeconomic", econ_skill),
}

# ── ANSI styling ────────────────────────────────────────────────────────────
os.system("")  # enables ANSI escape codes in the Windows console
try:  # keep box-drawing characters from crashing legacy-codepage pipes
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
CYAN, GREEN, YELLOW, RED, DIM, BOLD, RESET = (
    "\033[96m", "\033[92m", "\033[93m", "\033[91m", "\033[2m", "\033[1m", "\033[0m",
)


def banner(root):
    line = "─" * 62
    print(f"""
{CYAN}┌{line}┐
│{BOLD}                N E W S S C A L P E R   ·   v2                {RESET}{CYAN}│
│{RESET}         Mechanical market signals -> daily CSV export        {CYAN}│
├{line}┤{RESET}
{DIM}  Signals   sup = earnings surprise   fed = Federal Reserve
            mac = macroeconomic (Dow, inflation, jobs, econ_state)
  Output    {root}
  Commands  type symbols (AAPL, MSFT), 'all' = watchlist, 'quit'{RESET}
{CYAN}├{line}┤{RESET}
  {YELLOW}Bored while data loads?  Play Flappy Bird:{RESET} {BOLD}https://qdcode.us/flappy{RESET}
  {DIM}Data pool - browse ALL collected data at{RESET} https://qdcode.us {YELLOW}(coming soon){RESET}
{CYAN}└{line}┘{RESET}""")


def setup_logging():
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        filename=LOG_DIR / f"agent_{datetime.now():%Y%m%d}.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def load_settings():
    settings = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    settings["finnhub_api_key"] = os.environ.get("FINNHUB_API_KEY") or settings.get("finnhub_api_key", "")
    settings["fred_api_key"] = os.environ.get("FRED_API_KEY") or settings.get("fred_api_key", "")
    return settings


def load_watchlist():
    if not WATCHLIST_PATH.exists():
        return []
    lines = WATCHLIST_PATH.read_text(encoding="utf-8").splitlines()
    return [ln.strip().upper() for ln in lines if ln.strip() and not ln.strip().startswith("#")]


# ── Prompts ─────────────────────────────────────────────────────────────────

def prompt_symbols():
    while True:
        entry = input(f"{CYAN}  symbols{RESET} {DIM}(AAPL, MSFT | all | quit){RESET} > ").lstrip("﻿").strip()
        if not entry:
            continue
        lower = entry.lower()
        if lower in ("quit", "exit", "q"):
            return None
        if lower == "all":
            symbols = load_watchlist()
            if not symbols:
                print(f"  {YELLOW}watchlist is empty (config/symbols_watchlist.txt){RESET}")
                continue
            return symbols
        return [s.strip().upper() for s in entry.replace(";", ",").split(",") if s.strip()]


def prompt_signal():
    while True:
        entry = input(f"{CYAN}  signal {RESET} {DIM}(sup | fed | mac){RESET} > ").strip().lower()
        aliases = {"1": "sup", "2": "fed", "3": "mac",
                   "earnings": "sup", "surprise": "sup", "macro": "mac"}
        entry = aliases.get(entry, entry)
        if entry in SKILLS:
            return entry
        print(f"  {YELLOW}pick one of: sup, fed, mac{RESET}")


def _read_month_windows(label):
    """Digit-only month input; the dash is inserted automatically as you
    type, e.g. typing 032025 displays 03-2025."""
    digits = ""
    while True:
        shown = digits[:2] + ("-" + digits[2:] if len(digits) > 2 else "")
        sys.stdout.write(f"\r\033[K{CYAN}  {label:<8}{RESET} {DIM}(MMYYYY){RESET} > {shown}")
        sys.stdout.flush()
        ch = msvcrt.getwch()
        if ch in ("\r", "\n"):
            if len(digits) == 6 and 1 <= int(digits[:2]) <= 12:
                sys.stdout.write("\n")
                return f"{digits[:2]}-{digits[2:]}"
        elif ch == "\b":
            digits = digits[:-1]
        elif ch == "\x03":
            raise KeyboardInterrupt
        elif ch.isdigit() and len(digits) < 6:
            digits += ch


def _read_month_fallback(label):
    while True:
        raw = input(f"  {label} (MMYYYY) > ").strip().replace("-", "").replace("/", "")
        if len(raw) == 6 and raw.isdigit() and 1 <= int(raw[:2]) <= 12:
            return f"{raw[:2]}-{raw[2:]}"
        print(f"  {YELLOW}enter six digits, month then year, e.g. 032025{RESET}")


def prompt_month(label):
    # live auto-dash input needs a real console; piped input uses the fallback
    if msvcrt and sys.stdin.isatty():
        return _read_month_windows(label)
    return _read_month_fallback(label)


def prompt_range():
    """Ask for start and end months; returns (start_iso, end_iso) full days."""
    while True:
        start_mm = prompt_month("start")
        end_mm = prompt_month("end")
        start = f"{start_mm[3:]}-{start_mm[:2]}-01"
        end_y, end_m = int(end_mm[3:]), int(end_mm[:2])
        end = f"{end_y:04d}-{end_m:02d}-{calendar.monthrange(end_y, end_m)[1]:02d}"
        today = date.today().isoformat()
        if end > today:
            end = today  # future days would be all-null; cap at today
        if start <= end:
            return start, end
        print(f"  {YELLOW}start month must not be after end month{RESET}")


# ── Export ──────────────────────────────────────────────────────────────────

def run_export(symbol, dtype, start, end, settings):
    name, skill = SKILLS[dtype]
    print(f"\n  {BOLD}{symbol}{RESET}  {DIM}{name} · {start} .. {end}{RESET}")
    try:
        day_data, note = skill.fetch_range(symbol, start, end, settings)
    except Exception as exc:
        print(f"  {RED}data fetch failed: {exc}{RESET}")
        logging.error("%s %s: %s", dtype, symbol, exc)
        return

    path = csv_writer.write_export(
        symbol, dtype, start, end, skill.COLUMNS, skill.KEY_LINES, day_data
    )
    total_days = sum(1 for _ in csv_writer._daterange(start, end))
    status_color = GREEN if day_data else YELLOW
    print(f"  {status_color}exported{RESET} {path.name}  "
          f"{DIM}({total_days} days, {len(day_data)} with data){RESET}")
    if note:
        print(f"  {YELLOW}note: {note}{RESET}")
    print(f"  {DIM}saved to {path.parent}{RESET}")

    status = sync.send_export(path, symbol, dtype, start, end, settings)
    if status == "synced":
        print(f"  {GREEN}database: synced to central db{RESET}")
    elif status == "queued":
        print(f"  {YELLOW}database: unreachable - queued for retry{RESET}")
    logging.info("exported %s %s %s..%s (%d data days)", symbol, dtype, start, end, len(day_data))


def main():
    setup_logging()
    settings = load_settings()
    cache.configure(settings.get("cache_rules", {}))

    root, created = csv_writer.ensure_data_root()
    banner(root)
    if created:
        print(f"  {GREEN}first run: created {root}{RESET}")
        print(f"  {DIM}sample equity folders: {', '.join(csv_writer.SAMPLE_EQUITIES)}{RESET}\n")

    sent, remaining = sync.flush_outbox(settings)
    if sent:
        print(f"  {GREEN}synced {sent} queued export(s) to the central database{RESET}")
    if remaining:
        print(f"  {YELLOW}{remaining} export(s) still queued - database unreachable{RESET}")

    missing = [k for k in ("finnhub_api_key", "fred_api_key") if not settings.get(k)]
    if missing:
        print(f"  {RED}WARNING: missing {', '.join(missing)} in config/settings.json{RESET}\n")

    while True:
        try:
            symbols = prompt_symbols()
            if symbols is None:
                break
            dtype = prompt_signal()
            start, end = prompt_range()
            for symbol in symbols:
                run_export(symbol, dtype, start, end, settings)
            print()
        except KeyboardInterrupt:
            print()
            break

    print(f"  {DIM}done.{RESET}")


if __name__ == "__main__":
    sys.exit(main())
