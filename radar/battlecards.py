"""One-page battlecards built only from what the audit actually measured.

No positioning copy is written here: a card carries the competitor's real status, score
and URL counts, its audit notes, and (where the site blocks crawlers) the index snapshot
captured from search evidence. Strategy fields the audit cannot know stay absent rather
than invented, and the dashboard renders them as "not captured".
"""

from radar import competitors as comp_audit

CARDS = (
    ("vdb", "vdbapp.com"),
    ("dnd", "dnddiamond.com"),
    ("lepdo", "lepdodiamonds.com"),
)


def build():
    data = comp_audit.load() or {}
    by_domain = {row.get("domain"): row for row in data.get("results") or []}
    cards = {}
    for key, domain in CARDS:
        row = by_domain.get(domain)
        if not row:
            continue
        cards[key] = {
            "name": row.get("name"),
            "domain": row.get("domain"),
            "market": row.get("market"),
            "type": row.get("type"),
            "status": row.get("status"),
            "score": row.get("score"),
            "total_urls": row.get("total_urls"),
            "content_urls": row.get("content_urls"),
            "product_urls": row.get("product_urls"),
            "other_urls": row.get("other_urls"),
            "notes": row.get("notes") or [],
            "index_snapshot": row.get("index_snapshot") or {},
        }
    return {"cards": cards, "generated_at": data.get("generated_at")}
