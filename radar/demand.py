"""Join Keyword Planner demand onto the search intents a scan collects.

The scan produces intents from Google autocomplete: real queries, scored by a heuristic.
This module attaches what Google Ads actually reports for those queries - volume bucket,
competition and top-of-page bid - and keeps the two things separate on purpose:

  * a query with no imported record gets `demand: null`, not a zero
  * a volume is a range ("10K - 100K"), never a hard number

Coverage is surfaced in the payload as `demand_summary` so the dashboard can say how much
of the list is actually backed by data instead of implying all of it is.
"""

from . import keywords as keyword_store

DEFAULT_COUNTRY = "IN"

# Same weighting as the shortlist exporter: demand tier, then competition, then bid.
VOLUME_POINTS = [
    ("100K - 1M", 50),
    ("10K - 100K", 40),
    ("1K - 10K", 25),
    ("100 - 1K", 10),
    ("10 - 100", 2),
]
COMPETITION_POINTS = {"Low": 15, "Medium": 10, "High": 0}


def load(country=DEFAULT_COUNTRY, store_path=None):
    """Return {query_lower: record} for the most recent month we have."""
    store = keyword_store.load_store(store_path) if store_path else keyword_store.load_store()
    index = {}
    for query, by_country in (store.get("keywords") or {}).items():
        months = by_country.get(country.upper()) or {}
        if not months:
            continue
        period = sorted(months)[-1]
        record = months[period]
        index[" ".join(str(query).lower().split())] = dict(record, period=period)
    return index


def value_score(record):
    """Commercial value of one keyword, 0-90. Missing data scores 0, never an average."""
    if not record:
        return 0.0
    volume = dict(VOLUME_POINTS).get(record.get("range"), 0)
    competition = COMPETITION_POINTS.get(record.get("competition") or "", 0)
    bid = record.get("bid_high") or 0
    return round(volume + competition + min(25.0, float(bid) / 40.0), 1)


def _demand(record):
    if not record:
        return None
    return {
        "volume": record.get("range"),
        "bucket_low": None if record.get("range") is None else _bounds(record["range"])[0],
        "bucket_high": None if record.get("range") is None else _bounds(record["range"])[1],
        "competition": record.get("competition"),
        "competition_index": record.get("competition_index"),
        "bid_low": record.get("bid_low"),
        "bid_high": record.get("bid_high"),
        "currency": record.get("currency"),
        "type": record.get("type"),
        "period": record.get("period"),
    }


BUCKET_BOUNDS = {
    "10 - 100": (10, 100),
    "100 - 1K": (100, 1000),
    "1K - 10K": (1000, 10000),
    "10K - 100K": (10000, 100000),
    "100K - 1M": (100000, 1000000),
    "1M - 10M": (1000000, 10000000),
}


def _bounds(label):
    return BUCKET_BOUNDS.get(label, (None, None))


def enrich_queries(queries, index):
    """Attach `demand` and `demand_score` to each query dict in place."""
    matched = 0
    for query in queries:
        key = " ".join(str(query.get("query", "")).lower().split())
        record = index.get(key)
        query["demand"] = _demand(record)
        query["demand_score"] = value_score(record)
        if record:
            matched += 1
    return matched


def summary(queries):
    buckets = {}
    with_data = 0
    for query in queries:
        demand = query.get("demand")
        if not demand:
            continue
        with_data += 1
        label = demand.get("volume") or "no data"
        buckets[label] = buckets.get(label, 0) + 1
    return {
        "total": len(queries),
        "with_data": with_data,
        "without_data": len(queries) - with_data,
        "buckets": buckets,
    }


def enrich_snapshot(snapshot, index=None, country=DEFAULT_COUNTRY):
    """Return the snapshot with demand attached. Safe to call on an already-enriched one."""
    if not snapshot:
        return snapshot
    index = index if index is not None else load(country)
    queries = snapshot.get("keywords") or []
    matched = enrich_queries(queries, index)
    result = summary(queries)
    result["country"] = country.upper()
    result["matched_by_exact_name"] = matched
    snapshot["demand_summary"] = result
    return snapshot
