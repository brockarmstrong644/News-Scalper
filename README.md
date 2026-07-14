# NewsScalper

Interactive terminal agent that exports **purely mechanical market signals**
as daily CSV time series for an algorithmic trading program. No AI-written
text in the data — every column is deterministic math a fixed program can
parse.

You give it: ticker symbol(s), a signal type, and a date range.
It gives you: one CSV per symbol with **one row for every calendar day** in
the range (`null` wherever no data/news exists), plus a KEY block at the head
of the file explaining every column.

## Output files

Files are written to a folder created on your **Desktop** on first run,
organized by equity (new symbol folders are added automatically):

```
Desktop/NewsScalper Data/
├── AAPL/
│   ├── AAPL-03-2025-01-2026-fed.csv
│   ├── AAPL-03-2025-01-2026-sup.csv
│   └── AAPL-03-2025-01-2026-mac.csv
├── MSFT/ ...
└── (sample folders: AAPL MSFT NVDA TSLA AMZN SPY)
```

Filename format: `SYMBOL-MM-YYYY-MM-YYYY-type.csv` (symbol, start month,
end month, signal type).

### Signal types

| type | contents | columns |
|---|---|---|
| `sup` | earnings surprise | `eps_actual, eps_estimate, surprise_pct, sup_signal` — values on quarter period-end dates, null all other days |
| `fed` | Federal Reserve | `fed_funds_rate, rate_change, fed_signal` — daily effective fed funds rate (FRED DFF) |
| `mac` | macroeconomic | `djia_close, djia_change_pct, dow_signal, cpi_yoy_pct, unemployment_pct, econ_state` |

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

## File structure

```
NewsScalper/
├── agent.py                  entry point - the interactive prompt loop
├── run_agent.bat             double-click to open a cmd terminal and run it
├── requirements.txt
├── config/
│   ├── settings.json         API keys + sync + cache rules (gitignored)
│   ├── settings.example.json copy this to settings.json
│   └── symbols_watchlist.txt sample equities (used by the "all" command)
├── skills/                   one module per data-finding job
│   ├── earnings_skill.py     sup: EPS actual vs estimate (Finnhub)
│   ├── fed_skill.py          fed: daily fed funds rate (FRED DFF)
│   └── econ_skill.py         mac: Dow + CPI + unemployment + econ_state (FRED)
├── core/
│   ├── cache.py              checks data/cache FIRST before any API call
│   ├── fred.py               shared FRED range fetcher
│   ├── csv_writer.py         daily-row CSV exporter + Desktop folder logic
│   └── sync.py               uploads finished files to the central database
├── server/                   central database receiver (Cloudflare Tunnel)
├── data/cache/               raw fetched JSON (auto-managed)
└── logs/
```

## Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Copy `config/settings.example.json` to `config/settings.json`
   (the real settings file is gitignored so keys never reach GitHub).
3. Get free API keys and put them in `config/settings.json`
   (environment variables `FINNHUB_API_KEY` / `FRED_API_KEY` also work):
   - **Finnhub** (earnings): https://finnhub.io/register
   - **FRED** (fed + macro): https://fred.stlouisfed.org/docs/api/api_key.html

## Run

Double-click `run_agent.bat`, or `python agent.py`. The agent prompts for:

```
symbols (AAPL, MSFT | all | quit) >  AAPL
signal  (sup | fed | mac)         >  fed
start   (MMYYYY)                  >  03-2025   <- dash appears automatically as you type
end     (MMYYYY)                  >  01-2026
```

Date entry is digits-only — type `032025` and it displays `03-2025`.
Ranges ending in the future are capped at today. `all` runs every symbol in
the watchlist.

Notes on data coverage: Finnhub's free tier returns roughly the last four
reported quarters, so `sup` files for old ranges may be sparse. Futures
symbols (NQ, ES) have no company earnings — use `fed`/`mac` for those.

## Central database (optional, via Cloudflare Tunnel)

Every export can also be uploaded to one central SQLite database so all
collected data ends up organized in one place (even from multiple PCs).

**On the machine behind your Cloudflare Tunnel:**

1. Copy the `server/` folder there (needs only Python, no extra packages).
2. Copy `server/config.example.json` to `server/config.json`, set a long
   random `api_key`.
3. Start it: `python server/db_server.py` (or `run_server.bat`). It listens
   on port 8899 — point your tunnel's ingress at `http://localhost:8899`.

**On each machine running the agent** (`config/settings.json`):

```json
"sync_enabled": true,
"sync_url": "https://YOUR-TUNNEL-URL/ingest-file",
"sync_api_key": "<same secret as server/config.json>"
```

(Use `http://127.0.0.1:8899/ingest-file` when the agent runs on the same PC.)

Each finished CSV is stored whole in `server/newsscalper.db` (re-exporting
the same filename replaces the old version). If the server is unreachable,
exports queue in `data/outbox/` and re-send on the next agent start.

Getting data back out (send the `X-Api-Key` header):

- `GET /files` — JSON list of every stored export
- `GET /download/<filename>` — the stored CSV
- `GET /health` — export count / uptime check
- or open `server/newsscalper.db` with any SQLite tool

## Caching ("reference already found data first")

Every skill checks `data/cache/` before calling an API. Past earnings never
expire; FRED series refresh after 7 days; Dow data after 24 h. TTLs are
configurable in `settings.json` → `cache_rules` (hours; `null` = never).
Delete a file under `data/cache/` to force a refetch.
