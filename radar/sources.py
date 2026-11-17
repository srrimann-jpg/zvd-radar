"""Collectors. Every source here is public and key-less, so the radar runs on day one.

Each collector returns plain dicts and never raises: a dead source is reported in
`stats["errors"]` instead of taking the daily scan down with it.
"""

import json
import re
import time
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from . import fetch
from .taxonomy import AUTOCOMPLETE_SEEDS, COMMUNITY_QUERY, COMMUNITY_SUBS, NEWS_QUERIES

TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")

GOOGLE_NEWS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
BING_NEWS = "https://www.bing.com/news/search?q={q}&format=RSS"
REDDIT_TOP = "https://www.reddit.com/r/{sub}/top/.rss?t=week&limit=40"
REDDIT_SEARCH = "https://www.reddit.com/search.rss?q={q}&sort=top&t=week&limit=50"
REDDIT_MULTI = "https://www.reddit.com/r/{subs}/top/.rss?t=week&limit=50"
AUTOCOMPLETE = "https://suggestqueries.google.com/complete/search?client=firefox&hl=en&gl=us&q={q}"


def strip_html(text):
    if not text:
        return ""
    return SPACE_RE.sub(" ", TAG_RE.sub(" ", text)).strip()


def parse_date(value):
    """RFC-822 (RSS) or ISO-8601 (Atom) -> aware datetime, or None."""
    if not value:
        return None
    value = value.strip()
    try:
        from email.utils import parsedate_to_datetime

        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError):
        pass
    try:
        cleaned = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _google_news_items(xml_text, seed_query):
    root = ET.fromstring(xml_text)
    items = []
    for node in root.iter("item"):
        title = strip_html(node.findtext("title"))
        link = (node.findtext("link") or "").strip()
        if not title or not link:
            continue
        source_node = node.find("source")
        outlet = strip_html(source_node.text) if source_node is not None else ""
        # Google appends " - Outlet" to every headline.
        if outlet and title.endswith(" - " + outlet):
            title = title[: -(len(outlet) + 3)]
        elif " - " in title:
            head, _, tail = title.rpartition(" - ")
            if 2 < len(tail) < 40:
                title, outlet = head, (outlet or tail)
        published = parse_date(node.findtext("pubDate"))
        items.append(
            {
                "type": "news",
                "source": outlet or "Google News",
                "title": title,
                "url": link,
                "snippet": strip_html(node.findtext("description"))[:400],
                "published": published.isoformat() if published else None,
                "query": seed_query,
            }
        )
    return items


def google_news(query):
    url = GOOGLE_NEWS.format(q=urllib.parse.quote_plus(query))
    return _google_news_items(fetch.fetch_text(url, timeout=15), query)


def bing_news(query):
    url = BING_NEWS.format(q=urllib.parse.quote_plus(query))
    root = ET.fromstring(fetch.fetch_text(url, timeout=15))
    items = []
    for node in root.iter("item"):
        title = strip_html(node.findtext("title"))
        link = (node.findtext("link") or "").strip()
        if not title or not link:
            continue
        published = parse_date(node.findtext("pubDate"))
        items.append(
            {
                "type": "news",
                "source": "Bing News",
                "title": title,
                "url": link,
                "snippet": strip_html(node.findtext("description"))[:400],
                "published": published.isoformat() if published else None,
                "query": query,
            }
        )
    return items


def reddit_feed(subreddit, label):
    """Reddit exposes public Atom feeds that need no OAuth."""
    url = REDDIT_TOP.format(sub=subreddit)
    root = ET.fromstring(fetch.fetch_text(url, timeout=15))
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = []
    for entry in root.findall("atom:entry", ns):
        title = strip_html(entry.findtext("atom:title", default="", namespaces=ns))
        link_node = entry.find("atom:link", ns)
        link = link_node.get("href") if link_node is not None else ""
        if not title or not link:
            continue
        published = parse_date(entry.findtext("atom:updated", default="", namespaces=ns))
        content = strip_html(entry.findtext("atom:content", default="", namespaces=ns))
        items.append(
            {
                "type": "community",
                "source": label,
                "title": title,
                "url": link,
                "snippet": content[:400],
                "published": published.isoformat() if published else None,
                "query": label,
            }
        )
    return items


def reddit_search(query, url=None):
    """One request covers all relevant subreddits. Keeps us under Reddit's feed rate limit."""
    url = url or REDDIT_SEARCH.format(q=urllib.parse.quote_plus(query))
    root = ET.fromstring(fetch.fetch_text(url, timeout=12))
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = []
    for entry in root.findall("atom:entry", ns):
        title = strip_html(entry.findtext("atom:title", default="", namespaces=ns))
        link_node = entry.find("atom:link", ns)
        link = link_node.get("href") if link_node is not None else ""
        if not title or not link:
            continue
        published = parse_date(entry.findtext("atom:updated", default="", namespaces=ns))
        content = strip_html(entry.findtext("atom:content", default="", namespaces=ns))
        category = entry.find("atom:category", ns)
        subreddit = (category.get("term") or "") if category is not None else ""
        items.append(
            {
                "type": "community",
                "source": ("r/" + subreddit) if subreddit else "Reddit",
                "title": title,
                "url": link,
                "snippet": content[:400],
                "published": published.isoformat() if published else None,
                "query": query,
            }
        )
    return items


def suggest(seed):
    url = AUTOCOMPLETE.format(q=urllib.parse.quote_plus(seed))
    payload = json.loads(fetch.fetch_text(url, timeout=10))
    if isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], list):
        return [entry for entry in payload[1] if isinstance(entry, str)]
    return []


def collect_news(progress=None):
    """Fan out the news queries, then read community feeds one at a time.

    Reddit 429s a parallel burst of feed requests, so its feeds are paced and retried
    instead of being thrown into the same pool as the news feeds.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    items, errors = [], []
    jobs = [(query, "google") for query in NEWS_QUERIES]
    jobs += [(query, "bing") for query in NEWS_QUERIES[:6]]

    def run(job):
        query, kind = job
        return google_news(query) if kind == "google" else bing_news(query)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(run, job): job for job in jobs}
        for index, future in enumerate(as_completed(futures), start=1):
            job = futures[future]
            try:
                items.extend(future.result())
            except Exception as error:  # noqa: BLE001 - a source failure must not stop the scan
                errors.append("%s: %s: %s" % (job[1], job[0], error))
            if progress:
                progress("Reading news (%d/%d)" % (index, len(jobs)))

    # Multi-subreddit top feed first (richest), then the site search feed as a fallback.
    community_urls = [
        REDDIT_MULTI.format(subs=COMMUNITY_SUBS),
        REDDIT_SEARCH.format(q=urllib.parse.quote_plus(COMMUNITY_QUERY)),
    ]
    for index, url in enumerate(community_urls):
        try:
            items.extend(reddit_search(COMMUNITY_QUERY, url))
            break
        except urllib.error.HTTPError as error:
            if error.code == 429 and index + 1 < len(community_urls):
                time.sleep(6)
                continue
            errors.append("reddit: HTTP %s" % error.code)
            break
        except Exception as error:  # noqa: BLE001
            errors.append("reddit: %s" % error)
            break
    if progress:
        progress("Reading community threads")
    return items, errors


def collect_intents(progress=None):
    """Google autocomplete = what people actually type, grouped by seed."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results, errors = [], []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(suggest, seed): seed for seed in AUTOCOMPLETE_SEEDS}
        for index, future in enumerate(as_completed(futures), start=1):
            seed = futures[future]
            try:
                for query in future.result():
                    results.append({"query": query.strip().lower(), "seed": seed})
            except Exception as error:  # noqa: BLE001
                errors.append("autocomplete %s: %s" % (seed, error))
            if progress:
                progress("Reading search suggestions (%d/%d)" % (index, len(futures)))
    return results, errors


def collect_brand_watch(progress=None):
    """Brand + competitor mention counts from news search."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from .taxonomy import BRAND_TERMS, COMPETITORS

    terms = [(term, "brand") for term in BRAND_TERMS] + [(name, "competitor") for name in COMPETITORS]
    found, errors = {}, []

    def run(term):
        return google_news('"%s"' % term)

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(run, term): (term, kind) for term, kind in terms}
        for future in as_completed(futures):
            term, kind = futures[future]
            try:
                hits = future.result()
            except Exception as error:  # noqa: BLE001
                errors.append("brand %s: %s" % (term, error))
                continue
            found.setdefault(kind, []).append(
                {
                    "term": term,
                    "count": len(hits),
                    "headlines": [
                        {"title": hit["title"], "url": hit["url"], "source": hit["source"],
                         "published": hit["published"]}
                        for hit in hits[:3]
                    ],
                }
            )
    if progress:
        progress("Checking brand and competitors")
    return found, errors
