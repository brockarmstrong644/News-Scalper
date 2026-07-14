"""Writes range exports as CSV files organized by equity.

Output location: <Desktop>/NewsScalper Data/<SYMBOL>/
Filename:        <SYMBOL>-<MM-YYYY>-<MM-YYYY>-<type>.csv
                 e.g. AAPL-03-2025-01-2026-fed.csv

File layout:
  # KEY: ...          <- explanation of every column (machine-skippable:
  # KEY: ...             any line starting with '#' is a comment)
  date,col1,col2,...  <- header row
  2025-03-01,...      <- one row for EVERY calendar day in the range;
                         'null' wherever no data/news exists for that day
"""

import csv
import ctypes
import ctypes.wintypes
from datetime import date, timedelta
from pathlib import Path

FOLDER_NAME = "NewsScalper Data"
SAMPLE_EQUITIES = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "SPY"]


def desktop_path():
    """Resolve the real Windows Desktop folder (handles OneDrive redirect)."""
    try:
        CSIDL_DESKTOPDIRECTORY = 0x10
        buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_DESKTOPDIRECTORY, None, 0, buf)
        if buf.value:
            return Path(buf.value)
    except Exception:
        pass
    onedrive = Path.home() / "OneDrive" / "Desktop"
    return onedrive if onedrive.exists() else Path.home() / "Desktop"


def data_root():
    return desktop_path() / FOLDER_NAME


def ensure_data_root():
    """Create the Desktop data folder (with sample equity folders) on first
    startup. Returns (root_path, created_now)."""
    root = data_root()
    created = not root.exists()
    root.mkdir(parents=True, exist_ok=True)
    if created:
        for sym in SAMPLE_EQUITIES:
            (root / sym).mkdir(exist_ok=True)
    return root, created


def _daterange(start, end):
    cursor = date.fromisoformat(start)
    stop = date.fromisoformat(end)
    while cursor <= stop:
        yield cursor.isoformat()
        cursor += timedelta(days=1)


def write_export(symbol, dtype, start, end, columns, key_lines, day_data):
    """Write one export file and return its Path.

    symbol   - ticker, used for the per-equity folder
    dtype    - 'sup' | 'fed' | 'mac'
    start/end- 'YYYY-MM-DD' (full range; one row per calendar day)
    columns  - data column names (date is added automatically)
    key_lines- human/machine key text placed at the head of the file
    day_data - {date_str: {column: value}} from the skill
    """
    folder = data_root() / symbol.upper()
    folder.mkdir(parents=True, exist_ok=True)

    start_tag = f"{start[5:7]}-{start[:4]}"
    end_tag = f"{end[5:7]}-{end[:4]}"
    path = folder / f"{symbol.upper()}-{start_tag}-{end_tag}-{dtype}.csv"

    with path.open("w", newline="", encoding="utf-8") as f:
        f.write(f"# {symbol.upper()} | {dtype} | {start} to {end} | one row per calendar day\n")
        f.write("# KEY: date = calendar day, YYYY-MM-DD\n")
        for line in key_lines:
            f.write(f"# KEY: {line}\n")
        f.write("# lines starting with '#' are comments; data begins at the header row below\n")
        writer = csv.writer(f)
        writer.writerow(["date"] + columns)
        for day in _daterange(start, end):
            row_data = day_data.get(day, {})
            writer.writerow(
                [day] + [row_data.get(c, "null") if row_data.get(c) is not None else "null"
                         for c in columns]
            )
    return path
