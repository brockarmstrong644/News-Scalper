"""Appends finished rows to a dated CSV in data/exports/.

Column order is fixed so the downstream trading program can rely on it.
Signals are +1 / 0 / -1; composite_score is a weighted float in [-1, 1].
"""

import csv
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPORT_DIR = PROJECT_ROOT / "data" / "exports"

COLUMNS = [
    "symbol",
    "earnings_date",
    "eps_actual",
    "eps_estimate",
    "surprise_pct",
    "earnings_signal",
    "market_signal",
    "fed_signal",
    "econ_signal",
    "composite_score",
    "notes",
    "generated_at",
]


def append_row(row):
    """Write one report row; returns the path of the CSV it went to."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / f"earnings_report_{datetime.now():%Y%m%d}.csv"
    is_new = not path.exists()

    row = dict(row)
    row["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        if is_new:
            writer.writeheader()
        writer.writerow(row)
    return path
