"""Scoring, intent classification and content-brief generation.

No model calls: everything here is deterministic so a scan is reproducible, free and fast.
Swap in an LLM later by replacing build_brief() / why_now() - nothing else needs to change.
"""

import hashlib
import re
from datetime import datetime, timezone

from .taxonomy import (
    CORE_TERMS,
    FALLBACK_TITLES,
    NOISE_QUERY_PARTS,
    RETAILER_BRANDS,
    STAGE_RULES,
    THEME_BY_ID,
    THEMES,
)

AUDIENCE_B2B = [
    "wholesale", "retailer", "dealer", "trade ", "supplier", "manufacturer", "bourse",
    "margin", "inventory", "tender", "memo", "market share", "earnings", "b2b",
    "sourcing", "distributor", "stock", "category growth", "assortment", "parcel",
    "sightholder", "buying plan", "list price",
]
AUDIENCE_B2C = [
    "gift", "bride", "wedding", "how much", "worth", "buy", "shop", "ring", "earrings",
    "necklace", "bracelet", "near me", "for her", "budget", "anniversary", "proposal",
    "she said", "style", "outfit", "self purchase", "my boyfriend", "my fiance",
]

STAGE_BONUS = {
    "Compare": 18,
    "Price / commercial": 22,
    "Trade": 16,
    "Research": 10,
    "Browse": 12,
}

PAGE_TYPE = {
    "Compare": "Comparison page",
    "Price / commercial": "Pricing / category page",
    "Trade": "B2B landing page + price sheet",
    "Research": "Explainer / FAQ article",
    "Browse": "Collection or gifting page",
}

SMALL_WORDS = {"a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "of",
               "on", "or", "the", "to", "vs", "with", "your"}

ACRONYMS = {"gia", "igi", "cvd", "hpht", "4cs", "b2b", "b2c", "uk", "usa", "us", "ai",
            "dna", "led", "ar"}


def title_case(text):
    words = []
    for index, word in enumerate(text.split()):
        lowered = word.lower().strip(".,")
        if lowered in ACRONYMS:
            words.append(lowered.upper())
        elif index > 0 and lowered in SMALL_WORDS:
            words.append(lowered)
        else:
            words.append(word[:1].upper() + word[1:])
    return " ".join(words)


def fingerprint(text):
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:16]


_PATTERN_CACHE = {}


def _pattern(terms):
    """Word-boundary matcher for a term list.

    Boundaries matter: plain substring matching let short terms like "ai" or "app" fire
    inside "said" and "appraisal", which inflated whole themes.
    """
    key = tuple(sorted(terms))
    compiled = _PATTERN_CACHE.get(key)
    if compiled is None:
        joined = "|".join(re.escape(term) for term in sorted(terms, key=len, reverse=True))
        compiled = re.compile(r"(?<![a-z0-9])(?:" + joined + r")(?![a-z0-9])")
        _PATTERN_CACHE[key] = compiled
    return compiled


CORE_PATTERN = _pattern(CORE_TERMS)


def assign_themes(text):
    """Rank every theme the text touches: most matched terms first, then commercial weight."""
    lowered = " " + text.lower() + " "
    scored = []
    for theme in THEMES:
        hits = len(_pattern(theme["terms"]).findall(lowered))
        if hits:
            scored.append((hits, theme["weight"], theme["id"]))
    scored.sort(reverse=True)
    return [theme_id for _, _, theme_id in scored]


def is_core_relevant(text):
    return bool(CORE_PATTERN.search(" " + text.lower() + " "))


def is_noise_query(query):
    lowered = " " + query.lower() + " "
    return any(part in lowered for part in NOISE_QUERY_PARTS)


def headline_for(theme_id, queries):
    """Pick the best query to headline a topic: strong demand, but not a retailer name."""
    def rank(item):
        lowered = item["query"].lower()
        penalty = sum(45 for brand in RETAILER_BRANDS if brand in lowered)
        if "near me" in lowered:
            penalty += 14
        words = len(lowered.split())
        if words < 3:
            penalty += 12
        elif words > 6:
            penalty += 5
        return item["score"] - penalty

    ordered = sorted(queries, key=rank, reverse=True)
    if ordered and rank(ordered[0]) >= 55:
        return title_case(ordered[0]["query"]), ordered[0]["query"]
    primary = ordered[0]["query"] if ordered else THEME_BY_ID[theme_id]["label"].lower()
    return FALLBACK_TITLES.get(theme_id, THEME_BY_ID[theme_id]["label"]), primary


def classify_audience(text, theme_id):
    """B2B vs B2C from vocabulary, with a sane default per theme."""
    lowered = " " + text.lower() + " "
    b2b_hits = sum(1 for term in AUDIENCE_B2B if term in lowered)
    b2c_hits = sum(1 for term in AUDIENCE_B2C if term in lowered)
    if theme_id == "wholesale-b2b":
        b2b_hits += 2
    if theme_id in ("engagement-rings", "jewelry-trends"):
        b2c_hits += 2
    if b2b_hits >= b2c_hits + 2:
        return "B2B"
    if b2c_hits >= b2b_hits + 2:
        return "B2C"
    return "Both"


def stage_of(query):
    lowered = " %s " % query.lower()
    for stage, tokens in STAGE_RULES:
        for token in tokens:
            if token in lowered:
                return stage
    return "Research"


def recency_weight(published_iso, now=None):
    now = now or datetime.now(timezone.utc)
    if not published_iso:
        return 0.35
    try:
        published = datetime.fromisoformat(published_iso)
    except ValueError:
        return 0.35
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - published).total_seconds() / 86400.0)
    if age_days <= 2:
        return 1.0
    if age_days <= 7:
        return 0.8
    if age_days <= 14:
        return 0.5
    if age_days <= 30:
        return 0.25
    return 0.1


def normalize_signal(signal, now=None):
    text = "%s %s" % (signal.get("title", ""), signal.get("snippet", ""))
    themes = assign_themes(text)
    signal["themes"] = themes
    signal["theme"] = themes[0] if themes else None
    signal["theme_label"] = THEME_BY_ID[themes[0]]["label"] if themes else "Other"
    signal["audience"] = classify_audience(text, themes[0]) if themes else "Both"
    signal["weight"] = round(recency_weight(signal.get("published"), now), 2)
    signal["id"] = fingerprint(signal.get("url") or signal.get("title", ""))
    return signal


def opportunity(query, theme_id):
    """How much a search query is worth owning, 0-98."""
    theme = THEME_BY_ID.get(theme_id)
    stage = stage_of(query)
    score = 40 + (theme["weight"] * 4 if theme else 8) + STAGE_BONUS.get(stage, 10)
    if len(query.split()) >= 4:
        score += 6
    if any(word in query for word in ("2026", "2027", "under", "cheap")):
        score += 4
    if "near me" in query:
        score -= 8  # local intent, weak for a national marketplace page
    return max(20, min(98, score)), stage


def classify_query(query):
    themes = assign_themes(query)
    theme_id = themes[0] if themes else None
    score, stage = opportunity(query, theme_id)
    note = ""
    lowered = query.lower()
    if any(brand in lowered for brand in RETAILER_BRANDS):
        note = "Retailer comparison - win this with an honest, priced comparison page."
        score = min(98, score + 4)
    return {
        "query": query,
        "theme": theme_id,
        "theme_label": THEME_BY_ID[theme_id]["label"] if theme_id else "Other",
        "stage": stage,
        "audience": classify_audience(query, theme_id) if theme_id else "Both",
        "score": score,
        "page_type": PAGE_TYPE.get(stage, "Article"),
        "title": title_case(query),
        "note": note,
    }


def build_brief(theme_id, primary_keyword, audience):
    theme = THEME_BY_ID[theme_id]
    outline = [line.replace("{kw}", "'%s'" % primary_keyword) for line in theme["outline"]]
    return {
        "format": theme["formats"],
        "hook": theme["hook"],
        "angle": theme["angle"],
        "outline": outline,
        "cta": theme["cta"] if audience != "B2B" else theme["cta"],
        "words": "1,200-1,800 words" if theme["weight"] >= 4 else "900-1,200 words",
    }


def momentum_for(current, previous):
    if previous is None or previous == 0:
        return "New", None
    change = round((current - previous) / float(previous) * 100)
    if change >= 20:
        return "Rising", change
    if change <= -20:
        return "Cooling", change
    return "Steady", change


def why_now(theme, signals, gap_days=7):
    news = [signal for signal in signals if signal["type"] == "news"]
    community = [signal for signal in signals if signal["type"] == "community"]
    outlets = len({signal["source"] for signal in signals})
    fresh = sum(1 for signal in news if (signal.get("weight") or 0) >= 0.8)
    parts = []
    parts.append("%d news stories from %d outlets in the last %d days" % (len(news), outlets, gap_days))
    if community:
        parts.append("%d community threads asking related questions" % len(community))
    if fresh:
        parts.append("of which %d broke in the last 48 hours" % fresh)
    return "; ".join(parts[:1]) + (", " + ", ".join(parts[1:]) if parts[1:] else "") + "."
