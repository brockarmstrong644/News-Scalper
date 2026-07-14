"""Shared FRED range fetcher with caching.

Returns observations for a series between two dates, cached under
data/cache/<category>/ keyed by series + range so repeated exports of the
same window never refetch.
"""

import requests

from core import cache

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"


def series_range(series_id, start, end, api_key, category="econ"):
    """Return [(date_str, float_value), ...] for series between start/end.

    start/end are 'YYYY-MM-DD' strings. Observations FRED reports as '.'
    (not yet released) are dropped.
    """
    key = f"{series_id}_{start}_{end}"
    observations = cache.get(category, key)
    if observations is None:
        resp = requests.get(
            FRED_URL,
            params={
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "observation_start": start,
                "observation_end": end,
            },
            timeout=20,
        )
        resp.raise_for_status()
        observations = resp.json().get("observations", [])
        if observations:
            cache.put(category, key, observations)

    return [
        (o["date"], float(o["value"]))
        for o in (observations or [])
        if o.get("value") not in (None, ".")
    ]
