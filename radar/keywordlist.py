"""Build a paste-ready Google Keyword Planner keyword list.

Why this exists: Keyword Planner's "Get search volume and forecasts" takes a pasted list.
Handing it 300 focused terms returns volume for the queries ZVDapp actually wants to own,
instead of whatever Google thinks is adjacent.

Two sources are merged:
  1. SEEDS - curated head terms per theme. These are the phrases that carry commercial
     weight for a diamond marketplace and are stable month to month.
  2. The live scan's stored autocomplete queries (data/latest.json -> keywords). These are
     real demand signals: what Google was actively suggesting this week.

Run:
    python3 -m radar.keywordlist                 # writes data/keywords/
    python3 -m radar.keywordlist --stdout        # just print the list

Then paste data/keywords/zvd-keywords.txt into Keyword Planner, choose the location, and
download the CSV. See radar/keywords.py for the importer.
"""

import argparse
import io
import json
import os
import sys
from datetime import date

from .analyze import is_noise_query
from .store import DATA_DIR

OUT_DIR = os.path.join(DATA_DIR, "keywords")
TXT_NAME = "zvd-keywords.txt"
CSV_NAME = "zvd-keywords.csv"

# Curated head terms. One entry per line makes the diff readable when the list changes.
# Deliberately excluded: "near me" (local intent a national marketplace cannot serve),
# competitor brand names (we already audit those separately), and trivia/"meaning of"
# phrases that autocomplete drags in.
SEEDS = {
    "lab-grown": [
        "lab grown diamond",
        "lab grown diamonds",
        "lab grown diamond ring",
        "lab grown diamond engagement ring",
        "lab grown diamond earrings",
        "lab grown diamond stud earrings",
        "lab grown diamond necklace",
        "lab grown diamond tennis bracelet",
        "lab grown diamond price",
        "lab grown diamond price per carat",
        "lab created diamond",
        "cvd diamond",
        "hpht diamond",
        "1 carat lab grown diamond price",
        "2 carat lab grown diamond price",
        "are lab grown diamonds real",
        "lab grown diamond resale value",
        "lab grown diamond wholesale",
        "lab grown diamond supplier",
        "igi certified lab grown diamond",
        "lab grown diamond wedding ring",
        "lab grown vs natural diamond",
    ],
    "natural-diamond": [
        "natural diamond",
        "natural diamonds",
        "natural diamond ring",
        "natural diamond engagement ring",
        "natural diamond earrings",
        "natural diamond stud earrings",
        "natural diamond tennis bracelet",
        "natural diamond necklace",
        "natural diamond price",
        "earth mined diamond",
        "mined diamond",
        "rough diamond",
        "rough diamond price",
        "loose natural diamond",
        "natural diamond wholesale",
        "natural diamonds for sale",
        "1 carat natural diamond price",
    ],
    "diamond-prices": [
        "diamond price",
        "diamond prices",
        "diamond price per carat",
        "diamond price per gram",
        "diamond price chart",
        "diamond price index",
        "1 carat diamond price",
        "2 carat diamond price",
        "3 carat diamond price",
        "0.5 carat diamond price",
        "diamond cost calculator",
        "how much is a 1 carat diamond",
        "diamond price drop",
        "rapaport price list",
        "diamond price per carat by shape",
        "round diamond price",
        "oval diamond price",
        "emerald cut diamond price",
        "pear shaped diamond price",
        "cushion cut diamond price",
        "princess cut diamond price",
        "diamond wholesale price",
        "diamond retail markup",
    ],
    "engagement-rings": [
        "engagement ring",
        "engagement rings",
        "diamond engagement ring",
        "engagement ring styles",
        "engagement ring styles 2026",
        "solitaire engagement ring",
        "halo engagement ring",
        "oval engagement ring",
        "emerald cut engagement ring",
        "pear shaped engagement ring",
        "cushion cut engagement ring",
        "three stone engagement ring",
        "bezel engagement ring",
        "hidden halo engagement ring",
        "vintage engagement ring",
        "custom engagement ring",
        "engagement ring cost",
        "engagement ring budget",
        "how much should an engagement ring cost",
        "engagement ring size chart",
        "engagement ring settings",
        "diamond wedding band",
        "wedding rings for women",
    ],
    "grading-certs": [
        "gia certified diamond",
        "gia diamond certificate",
        "gia certificate check",
        "igi certified diamond",
        "igi certificate check",
        "gia vs igi",
        "diamond certificate",
        "diamond certification",
        "diamond grading",
        "4cs of diamonds",
        "diamond clarity chart",
        "diamond color chart",
        "diamond cut grade",
        "diamond carat weight",
        "diamond fluorescence",
        "diamond appraisal",
        "how to read a diamond certificate",
    ],
    "jewelry-retail": [
        "diamond jewelry",
        "fine jewelry",
        "jewelry store",
        "jewelry brands",
        "affordable fine jewelry",
        "lab grown jewelry",
        "jewelry sale",
        "pandora jewelry",
        "tiffany jewelry",
        "cartier jewelry",
    ],
    "wholesale-b2b": [
        "diamond wholesale",
        "diamond wholesale supplier",
        "loose diamond supplier",
        "loose diamonds wholesale",
        "diamond dealer",
        "diamond bourse",
        "diamond exchange",
        "jewelry wholesale",
        "jewelry wholesale supplier",
        "jewelry manufacturer",
        "diamond manufacturer",
        "diamond sourcing",
        "diamond supplier india",
        "diamond parcel",
        "memo diamonds",
        "diamond trade show",
        "jck las vegas",
        "hong kong jewelry show",
        "vicenzaoro",
        "diamond tender",
        "b2b diamond marketplace",
        "diamond trading platform",
    ],
    "sustainability": [
        "conflict free diamonds",
        "ethical diamonds",
        "ethical jewelry",
        "traceable diamonds",
        "diamond traceability",
        "lab grown diamond sustainability",
        "recycled gold jewelry",
        "kimberley process",
        "sustainable jewelry",
        "diamond provenance",
    ],
    "jewelry-trends": [
        "jewelry trends 2026",
        "jewelry trends",
        "engagement ring trends 2026",
        "diamond jewelry trends",
        "yellow gold jewelry",
        "stacking rings",
        "tennis bracelet",
        "diamond tennis bracelet",
        "diamond stud earrings",
        "diamond pendant",
        "diamond necklace",
        "mens diamond ring",
        "mens jewelry",
        "jewelry gift guide",
        "jewelry gifts for her",
        "anniversary gifts for her",
        "diamond earrings for women",
    ],
    "jewelry-tech": [
        "online jewelry store",
        "buy diamonds online",
        "online diamond jewelry",
        "virtual try on jewelry",
        "jewelry ecommerce",
        "jewelry marketplace",
        "live selling jewelry",
        "tiktok jewelry",
        "ai jewelry design",
        "3d printed jewelry",
    ],
    "diamond-investment": [
        "diamond investment",
        "invest in diamonds",
        "are diamonds a good investment",
        "diamond resale value",
        "do diamonds hold their value",
        "how to sell a diamond",
        "sell diamond ring",
        "diamond auction",
        "pre owned diamond ring",
        "second hand diamond rings",
        "lab grown diamond investment",
    ],
}

# Cross-cutting terms that do not belong to a single theme but matter to a marketplace.
EXTRA = {
    "core": [
        "diamond",
        "diamonds for sale",
        "loose diamonds",
        "loose diamond",
        "buy diamond online",
        "certified diamonds",
        "diamond ring",
        "moissanite vs diamond",
        "diamond vs cubic zirconia",
    ],
}


def _load_scan_queries():
    """Stored autocomplete queries from the latest scan, as (query, theme) pairs."""
    path = os.path.join(DATA_DIR, "latest.json")
    try:
        with io.open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return []
    rows = []
    for item in payload.get("keywords") or []:
        query = (item.get("query") or "").strip()
        if query:
            rows.append((query, item.get("theme") or "core"))
    return rows


def _clean(query):
    return " ".join(str(query).lower().split()).strip(" .,")


def build():
    """Return [(keyword, theme, source)] deduped on the keyword, curated seeds first."""
    seen = set()
    rows = []

    def add(query, theme, source):
        keyword = _clean(query)
        if not keyword or keyword in seen:
            return
        if is_noise_query(keyword):
            return
        seen.add(keyword)
        rows.append((keyword, theme, source))

    for theme, terms in SEEDS.items():
        for term in terms:
            add(term, theme, "curated")
    for theme, terms in EXTRA.items():
        for term in terms:
            add(term, theme, "curated")
    # Live demand last, so curated head terms keep the top of the paste list.
    for query, theme in _load_scan_queries():
        add(query, theme, "scan")

    return rows


def save(rows, target_dir=OUT_DIR, today=None):
    today = today or date.today().isoformat()
    if not os.path.isdir(target_dir):
        os.makedirs(target_dir)

    txt_path = os.path.join(target_dir, TXT_NAME)
    csv_path = os.path.join(target_dir, CSV_NAME)
    stamp_path = os.path.join(target_dir, "generated.txt")

    with io.open(txt_path, "w", encoding="utf-8", newline="\n") as handle:
        for keyword, _theme, _source in rows:
            handle.write(keyword + "\n")

    with io.open(csv_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("keyword,theme,source\n")
        for keyword, theme, source in rows:
            cells = [keyword, theme, source]
            handle.write(",".join('"%s"' % c.replace('"', '""') for c in cells) + "\n")

    with io.open(stamp_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("%s\n%d keywords\n" % (today, len(rows)))

    return txt_path, csv_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build a Keyword Planner paste list.")
    parser.add_argument("--stdout", action="store_true", help="print the list, write nothing")
    args = parser.parse_args(argv)

    rows = build()
    if args.stdout:
        for keyword, _theme, _source in rows:
            print(keyword)
        return 0

    txt_path, csv_path = save(rows)
    curated = sum(1 for row in rows if row[2] == "curated")
    print("%d keywords (%d curated, %d from scan)" % (len(rows), curated, len(rows) - curated))
    print("paste list: %s" % txt_path)
    print("index:      %s" % csv_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
