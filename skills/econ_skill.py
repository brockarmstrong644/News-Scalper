"""Skill: macroeconomic data ("mac" export).

Builds a daily macro picture from FRED:
  DJIA      - Dow Jones Industrial Average close (trading days)
  CPIAUCSL  - CPI, converted to year-over-year inflation (monthly)
  UNRATE    - unemployment rate (monthly)

Columns produced per day:
  djia_close       - Dow close (null on non-trading days)
  djia_change_pct  - % change vs previous close
  dow_signal       - +1 up >= 0.5%, 0 flat, -1 down <= -0.5%
  cpi_yoy_pct      - inflation YoY, only on the monthly observation date
  unemployment_pct - unemployment rate, only on the monthly observation date
  econ_state       - bucket 1..5 (1 = strong economy, 5 = weak), computed
                     every day from the latest known values:
                       inflation score:   +1 if <= 3%, -1 if > 4%, else 0
                       unemployment:      +1 falling, -1 rising >= 0.2pp, else 0
                       dow 30-day trend:  +1 if close > 30-day avg +1%,
                                          -1 if < 30-day avg -1%, else 0
                     sum >= 2 -> 1, sum 1 -> 2, sum 0 -> 3,
                     sum -1 -> 4, sum <= -2 -> 5
"""

from datetime import date, timedelta

from core import fred

DOW_TREND_PCT = 1.0     # % away from the 30-day average counted as a trend
DOW_DAY_PCT = 0.5       # daily % move below this is flat
INFLATION_GOOD_MAX = 3.0
INFLATION_BAD_MIN = 4.0
UNEMPLOYMENT_RISE_BAD = 0.2

COLUMNS = [
    "djia_close", "djia_change_pct", "dow_signal",
    "cpi_yoy_pct", "unemployment_pct", "econ_state",
]

KEY_LINES = [
    "djia_close = Dow Jones Industrial Average close (FRED DJIA); null on non-trading days",
    "djia_change_pct = percent change vs previous close",
    "dow_signal = +1 day up >= 0.5%, 0 flat, -1 day down <= -0.5%",
    "cpi_yoy_pct = inflation, CPI year-over-year percent; appears on monthly observation dates only",
    "unemployment_pct = unemployment rate percent; appears on monthly observation dates only",
    "econ_state = economic-state bucket from 1 (strong) to 5 (weak), updated daily from",
    "  latest known data: inflation band + unemployment direction + Dow 30-day trend",
    "  1 = strong, 2 = good, 3 = neutral, 4 = weak, 5 = bad",
    "null = no data published for that day (econ_state is null until enough history is known)",
]


def _shift_iso(date_str, days):
    d = date.fromisoformat(date_str)
    return (d + timedelta(days=days)).isoformat()


def _year_ago(date_str):
    return f"{int(date_str[:4]) - 1}{date_str[4:]}"


def fetch_range(symbol, start, end, settings):
    """Return ({date_str: {column: value}}, note). symbol unused (macro is
    market-wide)."""
    api_key = settings["fred_api_key"]

    # Fetch extra history: 45 days of Dow for the 30-day trend and 14 months
    # of CPI so YoY inflation can be computed from the first month of range.
    dow = fred.series_range("DJIA", _shift_iso(start, -45), end, api_key, "market")
    cpi = fred.series_range("CPIAUCSL", _shift_iso(start, -430), end, api_key, "econ")
    unrate = fred.series_range("UNRATE", _shift_iso(start, -70), end, api_key, "econ")

    cpi_by_date = dict(cpi)
    days = {}

    # ── Dow: daily values + rolling 30-day trend state ─────────────────────
    window = []
    prev_close = None
    dow_trend = {}  # date -> +1/0/-1, last-known
    for d, close in dow:
        change = None if prev_close is None else (close / prev_close - 1.0) * 100.0
        window.append(close)
        if len(window) > 30:
            window.pop(0)
        avg = sum(window) / len(window)
        if close > avg * (1 + DOW_TREND_PCT / 100):
            trend = 1
        elif close < avg * (1 - DOW_TREND_PCT / 100):
            trend = -1
        else:
            trend = 0
        dow_trend[d] = trend
        if d >= start:
            if change is None:
                day_sig = 0
            elif change >= DOW_DAY_PCT:
                day_sig = 1
            elif change <= -DOW_DAY_PCT:
                day_sig = -1
            else:
                day_sig = 0
            days[d] = {
                "djia_close": close,
                "djia_change_pct": round(change, 2) if change is not None else 0.0,
                "dow_signal": day_sig,
            }
        prev_close = close

    # ── Monthly CPI (as YoY inflation) and unemployment ────────────────────
    inflation_events = []  # (date, yoy_pct)
    for d, value in cpi:
        year_ago = cpi_by_date.get(_year_ago(d))
        if year_ago and d >= start:
            yoy = round((value / year_ago - 1.0) * 100.0, 2)
            inflation_events.append((d, yoy))
            days.setdefault(d, {})["cpi_yoy_pct"] = yoy

    unemployment_events = []  # (date, rate, change_vs_prev)
    prev_rate = None
    for d, rate in unrate:
        if prev_rate is not None and d >= start:
            unemployment_events.append((d, rate, round(rate - prev_rate, 2)))
            days.setdefault(d, {})["unemployment_pct"] = rate
        prev_rate = rate

    # ── econ_state bucket, walked forward day by day ───────────────────────
    latest_inflation = None
    latest_unemp_change = None
    latest_trend = None
    infl_iter, unemp_iter = iter(inflation_events), iter(unemployment_events)
    next_infl, next_unemp = next(infl_iter, None), next(unemp_iter, None)

    cursor = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    while cursor <= end_d:
        d = cursor.isoformat()
        while next_infl and next_infl[0] <= d:
            latest_inflation = next_infl[1]
            next_infl = next(infl_iter, None)
        while next_unemp and next_unemp[0] <= d:
            latest_unemp_change = next_unemp[2]
            next_unemp = next(unemp_iter, None)
        if d in dow_trend:
            latest_trend = dow_trend[d]

        if latest_inflation is not None and latest_unemp_change is not None and latest_trend is not None:
            score = 0
            score += 1 if latest_inflation <= INFLATION_GOOD_MAX else (-1 if latest_inflation > INFLATION_BAD_MIN else 0)
            score += 1 if latest_unemp_change < 0 else (-1 if latest_unemp_change >= UNEMPLOYMENT_RISE_BAD else 0)
            score += latest_trend
            if score >= 2:
                bucket = 1
            elif score == 1:
                bucket = 2
            elif score == 0:
                bucket = 3
            elif score == -1:
                bucket = 4
            else:
                bucket = 5
            days.setdefault(d, {})["econ_state"] = bucket
        cursor += timedelta(days=1)

    note = None
    if not dow:
        note = ("FRED returned no Dow data for this range (DJIA covers "
                "roughly the last 10 years) - dow columns and econ_state "
                "will be sparse")
    return days, note
