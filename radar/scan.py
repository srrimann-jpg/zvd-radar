"""One scan = collect signals, score themes, generate topics, briefs and brand watch."""

import time
from datetime import datetime, timezone

from . import analyze, sources, store
from .taxonomy import COMPETITORS, THEME_BY_ID, THEMES


def _friendly_error(message):
    """Source errors are shown in the UI, so keep them readable rather than raw tracebacks."""
    if "429" in message:
        return message.split(":")[0] + ": rate-limited by the source, skipped this run"
    if "timed out" in message.lower() or "timeout" in message.lower():
        return message.split(":")[0] + ": timed out, skipped this run"
    return message[:160]


def _dedupe(signals):
    seen_urls, seen_titles, unique = set(), set(), []
    for signal in signals:
        url = (signal.get("url") or "").split("?")[0]
        title_key = analyze.fingerprint(signal.get("title", "").lower()[:90])
        if url in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url)
        seen_titles.add(title_key)
        unique.append(signal)
    return unique


def _theme_signals(signals):
    grouped = {}
    for signal in signals:
        if signal.get("theme"):
            grouped.setdefault(signal["theme"], []).append(signal)
    return grouped


def _rank_signals(signals, limit=5):
    ordered = sorted(
        signals,
        key=lambda item: (item.get("weight") or 0, item.get("published") or ""),
        reverse=True,
    )
    picked, per_source = [], {}
    for signal in ordered:
        source = signal["source"]
        if per_source.get(source, 0) >= 2:
            continue
        per_source[source] = per_source.get(source, 0) + 1
        picked.append(
            {
                "title": signal["title"],
                "url": signal["url"],
                "outlet": signal["source"],
                "type": signal["type"],
                "published": signal.get("published"),
            }
        )
        if len(picked) >= limit:
            break
    return picked


def build_snapshot(progress=None):
    started = time.time()
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()

    def report(message):
        if progress:
            progress(message)

    report("Collecting sources")
    raw_signals, news_errors = sources.collect_news(progress)
    report("Reading search suggestions")
    raw_intents, intent_errors = sources.collect_intents(progress)
    report("Checking brand and competitors")
    brand_raw, brand_errors = sources.collect_brand_watch(progress)

    report("Scoring signals")
    signals = [analyze.normalize_signal(signal, now) for signal in raw_signals]
    signals = _dedupe(signals)
    relevant = [signal for signal in signals if signal.get("theme")]
    # General-interest subreddits carry a lot of off-topic chatter: keep only diamond talk.
    relevant = [
        signal for signal in relevant
        if signal["type"] != "community"
        or analyze.is_core_relevant(signal.get("title", "") + " " + signal.get("snippet", ""))
    ]
    relevant.sort(key=lambda item: (item.get("weight") or 0, item.get("published") or ""), reverse=True)

    grouped = _theme_signals(relevant)

    queries = []
    seen_queries = set()
    for intent in raw_intents:
        query = intent["query"]
        if query in seen_queries or analyze.is_noise_query(query):
            continue
        classified = analyze.classify_query(query)
        if not classified["theme"]:
            continue
        seen_queries.add(query)
        queries.append(classified)

    previous_counts = store.previous_theme_counts(today)
    theme_queries = {}
    for query in queries:
        theme_queries.setdefault(query["theme"], []).append(query)
    for bucket in theme_queries.values():
        bucket.sort(key=lambda item: item["score"], reverse=True)

    # Raw interest per theme, then one relative scale so scores are comparable and readable.
    candidates = []
    for theme in THEMES:
        theme_id = theme["id"]
        members = grouped.get(theme_id, [])
        related = theme_queries.get(theme_id, [])
        if len(members) < 2 and len(related) < 6:
            continue
        weighted_volume = sum(signal.get("weight") or 0 for signal in members)
        outlets = len({signal["source"] for signal in members})
        raw = (
            4.0 * math_log(weighted_volume)
            + 2.2 * math_log(outlets)
            + 2.4 * math_log(len(related))
            + theme["weight"] * 0.55
        )
        candidates.append((raw, theme_id, members, related))

    high = max((item[0] for item in candidates), default=0)
    low = min((item[0] for item in candidates), default=0)

    topics = []
    for raw, theme_id, members, related in candidates:
        theme = THEME_BY_ID[theme_id]
        span = (high - low) or 1
        score = int(round(42 + 57 * (raw - low) / span))
        headline, primary = analyze.headline_for(theme_id, related)
        audience_votes = {}
        for signal in members[:20]:
            audience_votes[signal["audience"]] = audience_votes.get(signal["audience"], 0) + 1
        audience = max(audience_votes, key=audience_votes.get) if audience_votes else "Both"
        momentum, change = analyze.momentum_for(len(members), previous_counts.get(theme_id))
        topics.append(
            {
                "id": "%s-%s" % (theme_id, today),
                "theme": theme_id,
                "theme_label": theme["label"],
                "title": headline,
                "audience": audience,
                "score": score,
                "momentum": momentum,
                "change_pct": change,
                "signal_count": len(members),
                "outlet_count": len({signal["source"] for signal in members}),
                "query_count": len(related),
                "why_now": analyze.why_now(theme, members),
                "keywords": [
                    {"query": item["query"], "stage": item["stage"], "score": item["score"]}
                    for item in related[:6]
                ],
                "brief": analyze.build_brief(theme_id, primary, audience),
                "signals": _rank_signals(members),
            }
        )
    topics.sort(key=lambda item: item["score"], reverse=True)

    brand_entries = brand_raw.get("brand") or []
    competitor_entries = brand_raw.get("competitor") or []
    competitor_entries.sort(key=lambda item: item["count"], reverse=True)
    brand_total = sum(item["count"] for item in brand_entries)
    competitor_total = sum(item["count"] for item in competitor_entries)
    share = round(brand_total / float(brand_total + competitor_total) * 100, 1) if (brand_total + competitor_total) else 0.0

    top_outlets = []
    outlet_counts = {}
    for signal in relevant:
        if signal["type"] != "news":
            continue
        outlet_counts[signal["source"]] = outlet_counts.get(signal["source"], 0) + 1
    for outlet, count in sorted(outlet_counts.items(), key=lambda item: item[1], reverse=True)[:5]:
        top_outlets.append({"outlet": outlet, "stories": count})

    themes_summary = []
    for theme in THEMES:
        count = len(grouped.get(theme["id"], []))
        if count:
            themes_summary.append({"id": theme["id"], "label": theme["label"], "count": count})
    themes_summary.sort(key=lambda item: item["count"], reverse=True)

    stats = {
        "signals": len(relevant),
        "news_signals": sum(1 for signal in relevant if signal["type"] == "news"),
        "community_signals": sum(1 for signal in relevant if signal["type"] == "community"),
        "queries": len(queries),
        "themes": len(themes_summary),
        "outlets": len(outlet_counts),
        "raw_items": len(raw_signals),
        "errors": [_friendly_error(error) for error in (news_errors + intent_errors + brand_errors)][:12],
        "error_count": len(news_errors) + len(intent_errors) + len(brand_errors),
    }

    snapshot = {
        "app": "ZVD Radar",
        "site": "zvdapp.com",
        "date": today,
        "generated_at": now.isoformat(timespec="seconds"),
        "scan_seconds": round(time.time() - started, 1),
        "window_days": 7,
        "stats": stats,
        "themes": themes_summary,
        "topics": topics,
        "keywords": sorted(queries, key=lambda item: item["score"], reverse=True)[:80],
        "signals": [
            {
                "title": signal["title"],
                "url": signal["url"],
                "outlet": signal["source"],
                "type": signal["type"],
                "published": signal.get("published"),
                "theme": signal.get("theme"),
                "theme_label": signal.get("theme_label"),
                "audience": signal.get("audience"),
            }
            for signal in relevant[:60]
        ],
        "brand": {
            "total_mentions": brand_total,
            "competitor_mentions": competitor_total,
            "share_of_voice": share,
            "entries": brand_entries,
            "competitors": competitor_entries,
            "terms": list(COMPETITORS),
            "top_outlets": top_outlets,
            "verdict": (
                "No earned-media coverage found for ZVDapp in this window - discovery is currently "
                "100% paid or word of mouth. Every competitor below is being written about, which is "
                "a free list of publications to pitch."
                if brand_total == 0
                else "ZVDapp appeared %d times in this window. Read the mentions, then pitch the "
                     "outlets covering your competitors." % brand_total
            ),
        },
    }
    return snapshot


def math_log(value):
    """log1p with a floor, so an empty bucket still scores."""
    import math

    return math.log1p(max(0.0, float(value)))


def run_and_save(progress=None):
    snapshot = build_snapshot(progress)
    store.save(snapshot)
    return snapshot


if __name__ == "__main__":
    result = run_and_save(print)
    print("\n=== %s | %s ===" % (result["date"], result["site"]))
    print("signals:%s queries:%s themes:%s seconds:%s" % (
        result["stats"]["signals"], result["stats"]["queries"],
        result["stats"]["themes"], result["scan_seconds"]))
    if result["stats"]["errors"]:
        print("source errors:", len(result["stats"]["errors"]))
    print("\nTop topics:")
    for index, topic in enumerate(result["topics"], start=1):
        print(" %2d. [%s] %s (%s) - %d signals / %d queries - %s" % (
            index, topic["score"], topic["title"], topic["audience"],
            topic["signal_count"], topic["query_count"], topic["momentum"]))
    print("\nBrand mentions: %s | competitors: %s" % (
        result["brand"]["total_mentions"], result["brand"]["competitor_mentions"]))
