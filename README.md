# NewsScalper

Interactive terminal agent that scalps **purely mechanical market signals**
into daily CSV time series for algorithmic trading programs. No AI-written
text in the data — every column is deterministic math a fixed program can
parse.

You give it: ticker symbol(s), a signal type, and a date range.
It gives you: one CSV per symbol with **one row for every calendar day** in
the range (`null` wherever no data/news exists), plus a KEY block at the head
of the file explaining every column. Finished exports are also reported back
to the central NewsScalper data pool automatically.

🐤 Waiting on data? Play Flappy Bird: **https://qdcode.us/flappy**
📊 Data pool — browse all collected data at https://qdcode.us *(coming soon)*

## Output files

Files are written to a folder created on your **Desktop** on first run,
organized by equity (new symbol folders are added automatically):

```
Desktop/NewsScalper Data/
├── AAPL/
│   ├── AAPL-03-2025-01-2026-sup.csv
│   ├── AAPL-03-2025-01-2026-fed.csv
│   └── AAPL-03-2025-01-2026-mac.csv
├── NQ/
│   └── NQ-06-2025-01-2026-prc.csv
└── (sample folders: AAPL MSFT NVDA TSLA AMZN SPY)
```

Filename format: `SYMBOL-MM-YYYY-MM-YYYY-type.csv` (symbol, start month,
end month, signal type).

### Signal types

| type | contents | columns |
|---|---|---|
| `sup` | earnings surprise | `eps_actual, eps_estimate, surprise_pct, sup_signal` — values on the earnings **report date**, null all other days. Years of history via Yahoo Finance (Finnhub fallback). |
| `fed` | Federal Reserve | `fed_funds_rate, rate_change, fed_signal` — daily effective fed funds rate (FRED DFF) |
| `mac` | macroeconomic | `djia_close, djia_change_pct, dow_signal, cpi_yoy_pct, unemployment_pct, econ_state` |
| `prc` | daily prices | `open, high, low, close, volume, change_pct, prc_signal` — any stock/ETF/index/crypto/futures symbol (NQ and ES map automatically to NQ=F / ES=F) |

All signals are −1 / 0 / +1 except `econ_state`, which is a **bucket from 1
(strong economy) to 5 (weak)**, recomputed every day from the latest known
inflation band, unemployment direction, and Dow 30-day trend. Exact
thresholds are printed in each file's `# KEY:` header.

### File layout

```
# AAPL | fed | 2025-03-01 to 2026-01-31 | one row per calendar day
# KEY: date = calendar day, YYYY-MM-DD
# KEY: fed_funds_rate = effective federal funds rate, percent (FRED series DFF)
# KEY: fed_signal = +1 rate fell (easing), 0 unchanged, -1 rate rose (tightening)
# lines starting with '#' are comments; data begins at the header row below
date,fed_funds_rate,rate_change,fed_signal
2025-03-01,4.33,0.0,0
...
```

A consuming program should skip lines starting with `#` and treat the string
`null` as missing data.

## Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Copy `config/settings.example.json` to `config/settings.json`
   (the real settings file is gitignored so keys never reach GitHub).
3. Fill in `config/settings.json`:
   - **FRED key** (free, for fed + macro): https://fred.stlouisfed.org/docs/api/api_key.html
   - **Finnhub key** (free, optional earnings fallback): https://finnhub.io/register
   - **`sync_api_key`** — the pool key that lets your exports report back to
     the central data pool. Ask the maintainer for it. Without it the agent
     still works; exports just stay local.

## Run

Double-click `run_agent.bat`, or `python agent.py`. The agent prompts for:

```
symbols (AAPL, MSFT | all | quit) >  AAPL
signal  (sup | fed | mac | prc)   >  sup
start   (MMYYYY)                  >  03-2025   <- dash appears automatically as you type
end     (MMYYYY)                  >  01-2026
```

Date entry is digits-only — type `032025` and it displays `03-2025`.
Ranges ending in the future are capped at today. `all` runs every symbol in
the watchlist (`config/symbols_watchlist.txt`).

After every export the agent prints a **coverage note** telling you exactly
what was found (archive depth, events inside the range, ticker mappings), so
a sparse file always explains itself.

## Reporting back to the data pool

With `sync_enabled` on, every finished CSV is automatically uploaded to the
central NewsScalper pool at `scalper.qdcode.us`, where all collected data is
organized in one place. If the pool is unreachable, exports queue in
`data/outbox/` and re-send the next time the agent starts. Re-exporting the
same filename replaces the old version in the pool.

## Data sources & caching

- **Earnings** — Yahoo Finance (years of history, real report dates), with
  Finnhub as automatic fallback. The local cache is a **growing archive**:
  refreshed daily, but new quarters are merged in and old ones kept forever.
- **Fed / macro** — FRED (official Federal Reserve data), refreshed weekly.
- **Prices** — Yahoo Finance daily OHLCV, refreshed daily.

Every skill checks `data/cache/` before calling any API — already-found data
is never refetched. TTLs are configurable in `settings.json` → `cache_rules`
(hours; `null` = never expire). Delete a file under `data/cache/` to force a
refetch. Futures symbols (NQ, ES) have no company earnings — use `prc`,
`fed`, or `mac` for those.
