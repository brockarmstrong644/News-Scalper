# Earnings Agent

Interactive terminal agent that reports company earnings in a machine-readable
way for an algorithmic trading program. You type ticker symbols; it produces
one CSV row per symbol with the earnings surprise %, the report date, and
market / Fed / economic condition signals.

## File structure

```
NewsScalper/
├── agent.py                  entry point - the interactive prompt loop
├── run_agent.bat             double-click to open a cmd terminal and run it
├── requirements.txt
├── config/
│   ├── settings.json         API keys, selected Claude model, cache rules
│   └── symbols_watchlist.txt saved symbols (used by the "all" command)
├── skills/                   one module per data-finding job
│   ├── earnings_skill.py     EPS actual vs estimate -> surprise % (Finnhub)
│   ├── market_skill.py       SPY daily trend + symbol quote (Finnhub)
│   ├── fed_skill.py          fed funds rate direction (FRED)
│   └── econ_skill.py         inflation YoY + unemployment (FRED)
├── core/
│   ├── cache.py              checks data/cache FIRST before any API call
│   ├── llm.py                Claude writes the human-readable notes column
│   └── csv_writer.py         appends rows to the dated export CSV
├── data/
│   ├── cache/                raw fetched JSON, keyed by symbol/series
│   └── exports/              earnings_report_YYYYMMDD.csv
└── logs/                     one log file per day
```

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
2. Copy `config/settings.example.json` to `config/settings.json`
   (the real settings file is gitignored so keys never reach GitHub).
3. Get free API keys and put them in `config/settings.json`
   (or set them as environment variables - env vars win):
   - **Finnhub** (earnings + quotes): https://finnhub.io/register  -> `finnhub_api_key` / `FINNHUB_API_KEY`
   - **FRED** (fed + economy): https://fred.stlouisfed.org/docs/api/api_key.html -> `fred_api_key` / `FRED_API_KEY`
   - **Anthropic** (notes column): `anthropic_api_key` / `ANTHROPIC_API_KEY` — optional;
     without it the notes column falls back to a rule-based sentence.
4. Pick the Claude model in `settings.json` (`"model"`, default `claude-opus-4-8`).

## Run

Double-click `run_agent.bat`, or from a terminal:

```
python agent.py
```

Then at the prompt:

```
symbols> AAPL, MSFT      run specific tickers
symbols> all             run everything in config/symbols_watchlist.txt
symbols> list            show the watchlist
symbols> quit
```

## CSV output (for the trading program)

`data/exports/earnings_report_YYYYMMDD.csv`, one row per symbol per run:

| column | meaning |
|---|---|
| `symbol` | ticker |
| `earnings_date` | period end date of the latest reported quarter |
| `eps_actual`, `eps_estimate` | reported vs consensus EPS |
| `surprise_pct` | (actual − estimate) / \|estimate\| × 100 |
| `earnings_signal` | +1 beat (≥ +2%), 0 in-line, −1 miss (≤ −2%) |
| `market_signal` | +1/0/−1 from SPY's daily % move (±0.5% threshold) |
| `fed_signal` | +1 rates falling, 0 flat, −1 rising (FEDFUNDS) |
| `econ_signal` | +1 good (inflation ≤3%, jobs stable), −1 bad (inflation >4% or unemployment rising), else 0 |
| `composite_score` | weighted blend: earnings 0.50, market 0.20, fed 0.15, econ 0.15 → range −1..+1 |
| `notes` | Claude's 2–3 sentence interpretation (or rule-based fallback) |
| `generated_at` | UTC timestamp of the row |

All numeric signals are deterministic rule-based math — the LLM only writes
the `notes` text, so the trading program's inputs never vary between runs on
the same data.

## Central database (optional, via Cloudflare Tunnel)

Every report can also be mirrored to one central SQLite database so all
collected data ends up organized in one place (even from multiple PCs).

**On the machine behind your Cloudflare Tunnel:**

1. Copy the `server/` folder there (it only needs Python, no extra packages).
2. Copy `server/config.example.json` to `server/config.json` and set a long
   random `api_key`.
3. Start it: `python server/db_server.py` (or `run_server.bat`).
   It listens on port 8899 — point your tunnel's ingress at
   `http://localhost:8899`.

**On each machine running the agent** (`config/settings.json`):

```json
"sync_enabled": true,
"sync_url": "https://YOUR-TUNNEL-URL/ingest",
"sync_api_key": "<same secret as server/config.json>"
```

(Use `http://127.0.0.1:8899/ingest` when the agent runs on the same PC as
the server.)

Each processed symbol is then inserted into `server/newsscalper.db`:
`reports` table (the CSV rows + which PC sent them) and `raw_data` table
(the raw Finnhub/FRED JSON, so signals can be recomputed later with
different thresholds). Duplicate rows are ignored automatically. If the
server is unreachable, reports queue in `data/outbox/` and re-send the
next time the agent starts.

Get everything back out at any time:

- `https://YOUR-TUNNEL-URL/export.csv` (send the `X-Api-Key` header) — full CSV dump
- `https://YOUR-TUNNEL-URL/health` — row count / uptime check
- or open `server/newsscalper.db` with any SQLite tool and run SQL

## Caching ("reference already found data first")

Every skill checks `data/cache/` before calling an API:

- past **earnings** never expire (they don't change)
- **quotes/market** refresh after 24 h
- **fed / economy** series refresh after 7 days

TTLs are configurable in `settings.json` → `cache_rules` (hours; `null` = never
expires). Delete a file under `data/cache/` to force a refetch.
