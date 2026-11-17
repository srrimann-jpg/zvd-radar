"""Import Google Keyword Planner exports into data/keywords.json.

The Keyword Planner "Keyword Stats" export is a UTF-16, tab-delimited file with two
preamble lines (a title and a date range) above the real header. This module reads it,
records every number with its provenance, and never upgrades a bucket to a hard number.

Important honesty rule: Keyword Planner reports average monthly searches as *buckets*
(e.g. 10K-100K) and the CSV encodes each bucket as its midpoint (50000). Those midpoints
must never be presented as exact volume, so every record carries `type: "range"` and the
bucket label alongside the midpoint.

Run:
    python3 -m radar.keywords import "data/keywords/Keyword Stats ....csv" --country IN
    python3 -m radar.keywords show
"""

import argparse
import csv
import glob
import io
import json
import os
import sys
from datetime import date, datetime, timezone

from .store import DATA_DIR

STORE_PATH = os.path.join(DATA_DIR, "keywords.json")

# Google's buckets and the midpoint each one is exported as. Left-to-right ascending.
BUCKETS = [
    (10, "10 - 100", 50),
    (100, "100 - 1K", 500),
    (1000, "1K - 10K", 5000),
    (10000, "10K - 100K", 50000),
    (100000, "100K - 1M", 500000),
    (1000000, "1M - 10M", 5000000),
]
MIDPOINT_TO_BUCKET = {mid: label for _low, label, mid in BUCKETS}

REQUIRED_HEADER = "Avg. monthly searches"


def _decode(path):
    """Keyword Planner writes UTF-16LE with a BOM; accept UTF-8 too."""
    with open(path, "rb") as handle:
        raw = handle.read()
    for encoding in ("utf-16", "utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("latin-1", "replace")


def _split_rows(text):
    """Return the data rows, skipping the title and date-range preamble."""
    cleaned = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line for line in cleaned.split("\n") if line.strip()]
    header_index = None
    for index, line in enumerate(lines):
        if "Keyword" in line and REQUIRED_HEADER in line:
            header_index = index
            break
    if header_index is None:
        raise ValueError("no Keyword Stats header found - is this a Keyword Planner export?")
    # The dateline (e.g. "November 1, 2025 - October 31, 2026") sits just above the header.
    dateline = lines[header_index - 1] if header_index >= 1 else ""
    reader = csv.DictReader(io.StringIO("\n".join(lines[header_index:])), delimiter="\t")
    return reader, dateline


def _clean(value):
    if value is None:
        return None
    text = str(value).replace("\x00", "").strip()
    return text or None


def _number(value):
    text = _clean(value)
    if text is None:
        return None
    text = text.replace(",", "").replace("%", "").strip()
    try:
        return float(text) if "." in text else int(text)
    except ValueError:
        return None


def _percent(value):
    """'0%'/'-90%'/'900%' -> -0.9/9.0 style floats, kept as reported percent."""
    number = _number(value)
    return number


def month_from_dateline(dateline):
    """'November 1, 2025 - October 31, 2026' -> '2026-10' (the end month of the window)."""
    # The dateline arrives quoted: '"November 1, 2025 - October 31, 2026"'.
    cleaned = dateline.strip().strip('"').strip()
    tail = cleaned.split("-")[-1].strip() if "-" in cleaned else cleaned
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%B %Y", "%b %Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(tail, fmt).strftime("%Y-%m")
        except ValueError:
            continue
    return None


def bucket_label(value):
    """Return (label, type) for a reported average-monthly-searches figure.

    Keyword Planner reports 0 (or blanks the cell) when a term is too rare to estimate.
    That is *absence of data*, not zero demand, so it gets its own type rather than
    being read as a real 0.
    """
    if value is None or value == 0:
        return None, "no_data"
    if value in MIDPOINT_TO_BUCKET:
        return MIDPOINT_TO_BUCKET[value], "range"
    return None, "reported"


def parse_export(path):
    """Yield (keyword, record) for every row in a Keyword Stats export."""
    reader, dateline = _split_rows(_decode(path))
    month = month_from_dateline(dateline)
    for row in reader:
        keyword = _clean(row.get("Keyword"))
        if not keyword:
            continue
        average = _number(row.get("Avg. monthly searches"))
        label, value_type = bucket_label(average)
        monthly = {}
        for key, raw in row.items():
            if not key or not key.lower().startswith("searches:"):
                continue
            stamp = key.split(":", 1)[1].strip()
            amount = _number(raw)
            if amount is not None:
                monthly[stamp] = amount
        yield keyword, {
            "value": average,
            "type": value_type,
            "range": label,
            "three_month_change": _percent(row.get("Three month change")),
            "yoy_change": _percent(row.get("YoY change")),
            "competition": _clean(row.get("Competition")),
            "competition_index": _number(row.get("Competition (indexed value)")),
            "bid_low": _number(row.get("Top of page bid (low range)")),
            "bid_high": _number(row.get("Top of page bid (high range)")),
            "currency": _clean(row.get("Currency")),
            "in_account": _clean(row.get("In account?")),
            "monthly": monthly,
        }, month


def load_store(path=STORE_PATH):
    try:
        with io.open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {"generated_at": None, "countries": [], "keywords": {}}


def save_store(store, path=STORE_PATH):
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    store["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with io.open(path, "w", encoding="utf-8") as handle:
        json.dump(store, handle, indent=1, sort_keys=True)
        handle.write("\n")


def import_file(path, country, store_path=STORE_PATH, fetched=None):
    """Merge one export into the store. Returns a small summary dict."""
    fetched = fetched or date.today().isoformat()
    store = load_store(store_path)
    country = (country or "??").upper()
    if country not in store.setdefault("countries", []):
        store["countries"].append(country)
        store["countries"].sort()

    imported = 0
    buckets = 0
    total_searches = 0
    for keyword, record, month in parse_export(path):
        record["source"] = "keyword_planner"
        record["fetched_at"] = fetched
        record["country"] = country
        slot = store["keywords"].setdefault(keyword, {}).setdefault(country, {})
        slot[month or "unknown"] = record
        imported += 1
        if record["type"] == "range":
            buckets += 1
        if isinstance(record["value"], int):
            total_searches += record["value"]
    save_store(store, store_path)
    return {
        "file": os.path.basename(path),
        "country": country,
        "month": month if imported else None,
        "rows": imported,
        "ranges": buckets,
        "midpoint_total": total_searches,
        "keywords_in_store": len(store["keywords"]),
    }


LIST_PATH = os.path.join(DATA_DIR, "keywords", "zvd-keywords.csv")
COVERAGE_PATH = os.path.join(DATA_DIR, "keywords", "coverage.json")


def _norm(keyword):
    return " ".join(str(keyword).lower().split())


def coverage(store_path=STORE_PATH, list_path=LIST_PATH, country=None):
    """Did the export actually measure the keywords we asked for?

    This is the guard against the most expensive mistake here: running the *ideas*
    view, which returns thousands of generated variants, and believing it measured the
    curated list. Anything below ~90% matched means the wrong flow was used.
    """
    store = load_store(store_path)
    have = {_norm(keyword) for keyword in store.get("keywords", {})}
    wanted = []
    try:
        with io.open(list_path, encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("keyword"):
                    wanted.append((row["keyword"].strip(), row.get("theme") or "core"))
    except OSError:
        return None

    matched, missing = [], []
    for keyword, theme in wanted:
        if _norm(keyword) in have:
            matched.append((keyword, theme))
        else:
            missing.append((keyword, theme))

    by_theme = {}
    for keyword, theme in missing:
        by_theme.setdefault(theme, []).append(keyword)

    return {
        "wanted": len(wanted),
        "matched": len(matched),
        "missing": len(missing),
        "match_rate": round(100.0 * len(matched) / len(wanted), 1) if wanted else 0.0,
        "missing_by_theme": by_theme,
    }


def summary(store=None, country=None, limit=25):
    store = store or load_store()
    rows = []
    for keyword, by_country in store.get("keywords", {}).items():
        for code, by_month in by_country.items():
            if country and code != country.upper():
                continue
            for month, record in by_month.items():
                rows.append((keyword, code, month, record))
    rows.sort(key=lambda row: (row[3].get("value") or 0), reverse=True)
    return rows[:limit]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Import Keyword Planner exports.")
    sub = parser.add_subparsers(dest="command")

    imp = sub.add_parser("import", help="import a Keyword Stats CSV")
    imp.add_argument("files", nargs="+", help="path(s) to exported CSV files")
    imp.add_argument("--country", default="IN", help="market code for these numbers (default IN)")
    imp.add_argument("--store", default=STORE_PATH)

    show = sub.add_parser("show", help="print the top keywords already imported")
    show.add_argument("--country", default=None)
    show.add_argument("--limit", type=int, default=25)
    show.add_argument("--store", default=STORE_PATH)

    cov = sub.add_parser("coverage", help="how much of the curated list this export measured")
    cov.add_argument("--store", default=STORE_PATH)
    cov.add_argument("--list", default=LIST_PATH)

    args = parser.parse_args(argv)
    if args.command == "import":
        for pattern in args.files:
            for path in sorted(glob.glob(pattern)):
                result = import_file(path, args.country, args.store)
                print(
                    "%s: %d rows (%d bucketed) for %s / %s"
                    % (result["file"], result["rows"], result["ranges"], result["country"],
                       result["month"])
                )
        return 0
    if args.command == "coverage":
        result = coverage(args.store, args.list)
        if result is None:
            print("no curated list found at %s" % args.list)
            return 1
        print("wanted %d, matched %d, missing %d (%.1f%%)"
              % (result["wanted"], result["matched"], result["missing"], result["match_rate"]))
        for theme, keywords in sorted(result["missing_by_theme"].items()):
            print("  %-18s %3d missing" % (theme, len(keywords)))
        save_store({**result, "generated_at": None}, COVERAGE_PATH)
        return 0
    if args.command == "show":
        for keyword, code, month, record in summary(load_store(args.store), country=args.country,
                                                   limit=args.limit):
            print("%-45s %-3s %-8s %-12s %s"
                  % (keyword[:45], code, month, record.get("range") or record.get("value"),
                     record.get("competition") or ""))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
