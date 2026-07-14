"""Skill: Federal Reserve data ("fed" export).

Builds a daily series of the effective federal funds rate (FRED series
DFF, published for every calendar day) across a date range.

Columns produced per day:
  fed_funds_rate  - DFF value that day (percent)
  rate_change     - change vs the previous published day (percentage points)
  fed_signal      - +1 rate fell, 0 unchanged, -1 rate rose

Days with no published observation are left as null by the exporter.
"""

from core import fred

FLAT_THRESHOLD = 0.01  # percentage-point change treated as unchanged

COLUMNS = ["fed_funds_rate", "rate_change", "fed_signal"]

KEY_LINES = [
    "fed_funds_rate = effective federal funds rate, percent (FRED series DFF)",
    "rate_change = change vs previous published day, percentage points",
    "fed_signal = +1 rate fell (easing), 0 unchanged, -1 rate rose (tightening)",
    "null = no observation published for that day",
]


def fetch_range(symbol, start, end, settings):
    """Return ({date_str: {column: value}}, note) for the range. symbol is
    unused (fed data is market-wide) but kept for a uniform skill interface."""
    observations = fred.series_range(
        "DFF", start, end, settings["fred_api_key"], category="fed"
    )
    days = {}
    prev = None
    for date, value in observations:
        change = None if prev is None else round(value - prev, 2)
        if change is None:
            signal = 0
        elif change <= -FLAT_THRESHOLD:
            signal = 1
        elif change >= FLAT_THRESHOLD:
            signal = -1
        else:
            signal = 0
        days[date] = {
            "fed_funds_rate": value,
            "rate_change": change if change is not None else 0.0,
            "fed_signal": signal,
        }
        prev = value

    note = None
    if not days:
        note = ("FRED returned no fed funds observations - check the "
                "fred_api_key and that the range is not in the future")
    return days, note
