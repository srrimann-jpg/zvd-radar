"""Rank the imported Keyword Planner data into a shortlist with visible evidence.

The point of this file is that every row can be justified by the columns next to it.
No volume is invented: Keyword Planner reported buckets, so a bucket is what gets shown.

Close variants are collapsed. Google reports identical volume and identical bid ranges
for synonyms that it treats as one close-variant group (all eight spellings of
"lab grown diamond" come back as 100K-1M at bid 118.37-679.91). Publishing eight pages
for those would mean eight pages competing with each other, so the file keeps one row per
group and records how many siblings were folded into it.

Run:
    python3 -m radar.topkeywords            # writes data/keywords/top-keywords.csv
    python3 -m radar.topkeywords --limit 20 # also prints the top rows
"""

import argparse
import csv
import io
import os
import sys

from .analyze import assign_themes
from .keywords import LIST_PATH, STORE_PATH, _norm, load_store
from .store import DATA_DIR
from .taxonomy import RETAILER_BRANDS

OUT_PATH = os.path.join(DATA_DIR, "keywords", "top-keywords.csv")

# Demand tier -> points. Ordered strongest first.
VOLUME_POINTS = [
    ("100K - 1M", 50),
    ("10K - 100K", 40),
    ("1K - 10K", 25),
    ("100 - 1K", 10),
    ("10 - 100", 2),
]
VOLUME_RANK = {label: index for index, (label, _p) in enumerate(VOLUME_POINTS)}

COMPETITION_POINTS = {"Low": 15, "Medium": 10, "High": 0, "Unknown": 0}

TIERS = [
    ("A", 70),
    ("B", 50),
    ("C", 30),
    ("D", 0),
]

FIELDS = [
    "rank", "tier", "keyword", "cluster_size", "theme", "competitor_brand",
    "in_curated_list",
    "avg_monthly_searches", "bucket_low", "bucket_high", "volume_type",
    "competition", "competition_index", "bid_low_inr", "bid_high_inr",
    "score", "evidence", "country", "period", "source", "fetched_at",
]

BUCKET_BOUNDS = {
    "10 - 100": (10, 100),
    "100 - 1K": (100, 1000),
    "1K - 10K": (1000, 10000),
    "10K - 100K": (10000, 100000),
    "100K - 1M": (100000, 1000000),
    "1M - 10M": (1000000, 10000000),
}


def _curated_map(list_path=LIST_PATH):
    mapping = {}
    try:
        with io.open(list_path, encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                keyword = row.get("keyword")
                if keyword:
                    mapping[_norm(keyword)] = row.get("theme") or "core"
    except OSError:
        pass
    return mapping


def _theme_for(keyword, curated):
    theme = curated.get(_norm(keyword))
    if theme:
        return theme
    themes = assign_themes(keyword)
    return themes[0] if themes else "core"


def _score(record):
    volume = dict(VOLUME_POINTS).get(record["range"], 0)
    competition = COMPETITION_POINTS.get(record["competition"] or "Unknown", 0)
    bid = record.get("bid_high") or 0
    # A high top-of-page bid is the clearest evidence that advertisers value the term.
    bid_points = min(25.0, float(bid) / 40.0)
    return round(volume + competition + bid_points, 1)


def _brand(keyword):
    """Flag retailer/brand terms - useful traffic, but not ZVDapp's own content."""
    lowered = " %s " % _norm(keyword)
    for brand in RETAILER_BRANDS:
        if brand in lowered:
            return brand
    return ""


def _tier(score):
    for name, floor in TIERS:
        if score >= floor:
            return name
    return "D"


def _evidence(record, cluster_size):
    parts = [
        "%s searches/month" % record["range"],
        "%s competition (index %s)" % (record["competition"] or "unknown",
                                      record["competition_index"]),
    ]
    if record.get("bid_high"):
        parts.append("top-of-page bid INR %s-%s" % (record["bid_low"], record["bid_high"]))
    if cluster_size > 1:
        parts.append("%d close variants folded in" % cluster_size)
    return "; ".join(parts)


def build(store_path=STORE_PATH, list_path=LIST_PATH, min_bucket="1K - 10K"):
    """Return ranked rows. `min_bucket` keeps buckets at least this large."""
    store = load_store(store_path)
    curated = _curated_map(list_path)
    floor = VOLUME_RANK.get(min_bucket, 0)

    candidates = []
    for keyword, by_country in store.get("keywords", {}).items():
        for country, by_month in by_country.items():
            for period, record in by_month.items():
                label = record.get("range")
                if label not in VOLUME_RANK:
                    continue
                if VOLUME_RANK[label] > floor:
                    continue
                candidates.append((keyword, country, period, record))

    # Group by Google's close-variant fingerprint: same bucket, same bids, same competition.
    groups = {}
    for keyword, country, period, record in candidates:
        if record.get("bid_low") is not None and record.get("bid_high") is not None:
            key = (record["range"], record["bid_low"], record["bid_high"],
                   record["competition"], country)
        else:
            key = ("solo", keyword, country)
        groups.setdefault(key, []).append((keyword, country, period, record))

    rows = []
    for members in groups.values():
        # Canonical row: prefer a keyword from the curated list (that is the phrasing we
        # chose to target), then the shortest, then alphabetical.
        members.sort(key=lambda item: (0 if _norm(item[0]) in curated else 1,
                                       len(item[0]), item[0]))
        keyword, country, period, record = members[0]
        cluster_size = len(members)
        score = _score(record)
        low, high = BUCKET_BOUNDS.get(record["range"], (None, None))
        rows.append({
            "tier": _tier(score),
            "keyword": keyword,
            "cluster_size": cluster_size,
            "theme": _theme_for(keyword, curated),
            "competitor_brand": _brand(keyword),
            "in_curated_list": "yes" if _norm(keyword) in curated else "no",
            "avg_monthly_searches": record["range"],
            "bucket_low": low,
            "bucket_high": high,
            "volume_type": "range",
            "competition": record.get("competition"),
            "competition_index": record.get("competition_index"),
            "bid_low_inr": record.get("bid_low"),
            "bid_high_inr": record.get("bid_high"),
            "score": score,
            "evidence": _evidence(record, cluster_size),
            "country": country,
            "period": period,
            "source": record.get("source"),
            "fetched_at": record.get("fetched_at"),
        })

    rows.sort(key=lambda row: (-row["score"], row["keyword"]))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def save(rows, path=OUT_PATH):
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    # utf-8-sig so Excel opens the INR values and any non-ASCII without mojibake.
    with io.open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rank top-performing keywords from the store.")
    parser.add_argument("--store", default=STORE_PATH)
    parser.add_argument("--list", default=LIST_PATH)
    parser.add_argument("--min-bucket", default="1K - 10K")
    parser.add_argument("--limit", type=int, default=15)
    args = parser.parse_args(argv)

    rows = build(args.store, args.list, args.min_bucket)
    path = save(rows)
    tiers = {}
    for row in rows:
        tiers[row["tier"]] = tiers.get(row["tier"], 0) + 1
    print("%d rows -> %s" % (len(rows), path))
    print("tiers: %s" % ", ".join("%s=%d" % (k, tiers[k]) for k in sorted(tiers)))
    print()
    for row in rows[:args.limit]:
        print("%3d %-1s %-42s %-11s comp=%-6s bid=%s-%s"
              % (row["rank"], row["tier"], row["keyword"][:42], row["avg_monthly_searches"],
                 row["competition"], row["bid_low_inr"], row["bid_high_inr"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
