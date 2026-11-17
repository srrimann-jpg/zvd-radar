"""What competitors are publishing, from public evidence only.

Two keyless signals, both verified to work before this module was written:

  sitemap diff   we already download each competitor's sitemap with <lastmod> dates.
                 Keep the URL set per domain, diff it each run, and the new entries are
                 literally the pages they published since last time.
  link crawl     sites with no sitemap at all are walked from their navigation instead,
                 so a hand-built static site is tracked rather than called unreachable.
  RSS            only 5 of the 22 domains expose a working feed (nivoda, thediamondport,
                 stonealgo, allurez, lippas), so feeds are a bonus, not the backbone.

Honesty rules baked in:
  * the first run has nothing to diff against, so it reports `first_run` and shows the
    most recently modified pages instead of claiming everything is new
  * a site that blocks us is marked blocked/unreachable, never scored as zero output
  * titles are fetched for a few pages only; a missing title stays empty rather than
    being replaced with a guess derived from the URL

Run:
    python3 -m radar.publishing
"""

import concurrent.futures
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from html import unescape

from . import store
from .competitors import (
    COMPETITORS,
    CONTENT_RE,
    PRODUCT_RE,
    _fetch,
    _find_sitemaps,
)

STORE_NAME = "publishing.json"
URL_BUDGET = 3000
TITLE_LIMIT = 6
WORKERS = 8
DEADLINE_SECONDS = 420
CRAWL_BUDGET = 400
CRAWL_FETCH_LIMIT = 60

# Verified working, path discovered by probing /feed, /rss, /feed.xml, /blog/feed.
FEEDS = {
    "nivoda.com": "/feed",
    "thediamondport.com": "/blog/feed",
    "stonealgo.com": "/blog/feed",
    "allurez.com": "/blog/feed",
    "lippas.com": "/feed",
}

TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
LINK_RE = re.compile(r'href=["\']([^"\'#]+)["\']', re.I)
NON_PAGE_RE = re.compile(
    r"\.(png|jpe?g|gif|svg|webp|ico|css|js|pdf|zip|gz|mp4|webm|woff2?|ttf|xml|txt)(\?|$)", re.I)


def _clean(text, limit=160):
    value = unescape(re.sub(r"\s+", " ", text or "")).strip()
    return value[:limit]


def page_title(url):
    try:
        _, _, html = _fetch(url, limit=120_000, timeout=8)
    except Exception:  # noqa: BLE001
        return ""
    match = TITLE_RE.search(html)
    if not match:
        return ""
    title = _clean(match.group(1))
    # Strip the trailing " | Site Name" that most templates append.
    for separator in (" | ", " - ", " — "):
        if separator in title and len(title.split(separator)[0]) > 18:
            title = title.split(separator)[0]
            break
    return title[:120]


def classify(url):
    path = urllib.parse.urlparse(url).path
    if CONTENT_RE.search(path):
        return "content"
    if PRODUCT_RE.search(path):
        return "catalogue"
    return "other"


def sitemap_pairs(domain, deadline=None):
    """Return ([(url, lastmod)], error). Falls back through the advertised sitemaps."""
    last = "no sitemap found"
    for sitemap in _find_sitemaps(domain):
        if deadline and time.time() > deadline:
            return [], "deadline reached"
        try:
            _, _, xml = _fetch(sitemap, limit=3_000_000, timeout=14)
        except Exception as error:  # noqa: BLE001
            last = str(error)[:80]
            continue
        pairs = _walk(xml, 0, deadline)
        if pairs:
            return pairs[:URL_BUDGET], None
        last = "no urls in sitemap"
    return [], last


def _host(url):
    return re.sub(r"^www\.", "", (urllib.parse.urlparse(url).netloc or "").lower())


def _links(html, base):
    out = []
    for raw in LINK_RE.findall(html or ""):
        raw = raw.strip()
        if not raw or raw.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            continue
        absolute = urllib.parse.urljoin(base, raw)
        if not absolute.startswith(("http://", "https://")):
            continue
        out.append(absolute.split("#")[0])
    return out


def _child_links(url):
    try:
        _, final, html = _fetch(url, limit=400_000, timeout=8)
    except Exception:  # noqa: BLE001
        return []
    return _links(html, final or url)


def crawl_pages(domain, deadline=None, budget=CRAWL_BUDGET):
    """Fallback for sites that publish no sitemap: walk internal links from the homepage.

    Some trade suppliers ship a hand-built static site with no sitemap and no feed
    (toshakhana.uk is one). Their pages are still public, so they are discovered from the
    navigation rather than the domain being reported as unreachable.
    """
    root = "https://%s/" % domain
    try:
        _, final, html = _fetch(root, limit=600_000, timeout=14)
    except Exception as error:  # noqa: BLE001
        return [], str(error)[:80]

    host = _host(final or root)
    seen = []
    seen_keys = set()

    def remember(url):
        clean = url.split("#")[0].rstrip("/") or url.split("#")[0]
        if _host(clean) != host or NON_PAGE_RE.search(clean):
            return False
        key = clean.lower()
        if key in seen_keys:
            return False
        seen_keys.add(key)
        seen.append(clean)
        return True

    remember(root)
    frontier = [url for url in _links(html, final or root) if remember(url)]
    depth = 0
    while frontier and depth < 2 and len(seen) < budget:
        if deadline and time.time() > deadline:
            break
        batch = frontier[:CRAWL_FETCH_LIMIT]
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
            results = list(pool.map(_child_links, batch))
        following = []
        for links in results:
            if len(seen) >= budget:
                break
            for link in links:
                if remember(link):
                    following.append(link)
        frontier = following
        depth += 1
    return [(url, "") for url in seen[:budget]], None


def _is_sitemap(url):
    return url.lower().split("?")[0].endswith((".xml", ".xml.gz", ".txt"))


def _walk(xml, depth, deadline, budget=URL_BUDGET):
    """Descend through nested sitemap indexes and keep only real page URLs.

    Some sites nest an index inside an index; without this, the 'newest pages' come back
    as a list of sitemap files, which is not publishing activity.
    """
    pairs = []
    if "<sitemapindex" in xml[:3000] and depth < 2:
        for child in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)[:8]:
            if deadline and time.time() > deadline:
                break
            try:
                _, _, child_xml = _fetch(child, limit=2_000_000, timeout=12)
            except Exception:  # noqa: BLE001
                continue
            pairs.extend(_walk(child_xml, depth + 1, deadline, budget))
            if len(pairs) >= budget:
                break
    else:
        pairs = _pairs_from(xml)
    return [pair for pair in pairs if not _is_sitemap(pair[0])]


def _pairs_from(xml):
    """Pair <loc> with the <lastmod> that follows it, per <url> block."""
    pairs = []
    for block in re.findall(r"<url>(.*?)</url>", xml, re.S):
        loc = re.search(r"<loc>\s*([^<\s]+)\s*</loc>", block)
        if not loc:
            continue
        stamp = re.search(r"<lastmod>\s*([^<\s]+)", block)
        pairs.append((loc.group(1), stamp.group(1)[:10] if stamp else ""))
    if not pairs:  # some sitemaps omit <url> wrappers entirely
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
        pairs = [(loc, "") for loc in locs]
    return pairs


def rss_items(domain, limit=12):
    path = FEEDS.get(domain)
    if not path:
        return [], None
    url = "https://%s%s" % (domain, path)
    try:
        _, _, xml = _fetch(url, limit=400_000, timeout=12)
    except Exception as error:  # noqa: BLE001
        return [], str(error)[:80]
    items = []
    for block in re.findall(r"<item>(.*?)</item>", xml, re.S) + \
            re.findall(r"<entry>(.*?)</entry>", xml, re.S):
        title = re.search(r"<title[^>]*>(.*?)</title>", block, re.S)
        link = re.search(r"<link[^>]*href=\"([^\"]+)\"", block) or \
            re.search(r"<link>\s*([^<\s]+)\s*</link>", block)
        date = re.search(r"<pubDate>\s*([^<]+)</pubDate>", block) or \
            re.search(r"<updated>\s*([^<]+)</updated>", block)
        if not (title and link):
            continue
        items.append({
            "title": _clean(title.group(1), 140),
            "url": link.group(1).strip(),
            "published": _clean(date.group(1), 40) if date else "",
        })
        if len(items) >= limit:
            break
    return items, None


def _entry(competitor, pairs, previous, new_feeds, error, source="sitemap"):
    domain = competitor["domain"]
    urls = [pair[0] for pair in pairs]
    first_run = not previous

    if first_run:
        ranked = sorted(pairs, key=lambda pair: pair[1], reverse=True)[:10]
        new = [{"url": url, "lastmod": stamp, "kind": classify(url), "title": ""}
               for url, stamp in ranked]
    else:
        fresh = [(url, stamp) for url, stamp in pairs if url not in previous]
        fresh.sort(key=lambda pair: pair[1], reverse=True)
        new = [{"url": url, "lastmod": stamp, "kind": classify(url), "title": ""}
               for url, stamp in fresh[:20]]

    titles = {}
    targets = [item["url"] for item in new if item["kind"] == "content"][:TITLE_LIMIT]
    if len(targets) < TITLE_LIMIT:
        targets += [item["url"] for item in new if item["kind"] != "content"][
            :TITLE_LIMIT - len(targets)]
    if targets:
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for url, title in zip(targets, pool.map(page_title, targets)):
                titles[url] = title
    for item in new:
        item["title"] = titles.get(item["url"], "")

    kinds = {}
    for url in urls:
        kind = classify(url)
        kinds[kind] = kinds.get(kind, 0) + 1

    return {
        "name": competitor["name"],
        "domain": domain,
        "type": competitor["type"],
        "market": competitor["market"],
        "status": "ok" if urls else ("blocked" if error else "empty"),
        "source": source,
        "error": error,
        "total_urls": len(urls),
        "content_urls": kinds.get("content", 0),
        "catalogue_urls": kinds.get("catalogue", 0),
        "first_run": first_run,
        "new_count": len(new),
        "new": new,
        "rss": new_feeds,
    }, urls


def run(progress=None):
    """Collect the publishing comparison. Returns the payload that gets stored."""
    started = time.time()
    deadline = started + DEADLINE_SECONDS
    previous_payload = store.backend().get(STORE_NAME) or {}
    previous_index = previous_payload.get("index") or {}

    def report(message):
        if progress:
            progress(message)

    entries = []
    index = {}
    for competitor in COMPETITORS:
        if time.time() > deadline:
            report("Deadline reached — keeping the competitors collected so far")
            break
        domain = competitor["domain"]
        report("Reading %s" % competitor["name"])
        pairs, error = sitemap_pairs(domain, deadline)
        source = "sitemap"
        if not pairs:
            crawled, crawl_error = crawl_pages(domain, deadline)
            if crawled:
                pairs, error, source = crawled, None, "crawl"
            elif crawl_error and not error:
                error = crawl_error
        feeds, feed_error = rss_items(domain)
        entry, urls = _entry(
            competitor, pairs, previous_index.get(domain) or [], feeds, error, source)
        if feed_error:
            entry["rss_error"] = feed_error
        entries.append(entry)
        if urls:
            index[domain] = urls

    # A run can hit its time limit before every domain is read. The dropped domains must
    # still appear and must keep their URL set, or next run would call their whole
    # back catalogue "new".
    collected = {entry["domain"] for entry in entries}
    for competitor in COMPETITORS:
        domain = competitor["domain"]
        if domain in collected:
            continue
        prior = next((item for item in (previous_payload.get("domains") or [])
                      if item.get("domain") == domain), {})
        entries.append({
            "name": competitor["name"],
            "domain": domain,
            "type": competitor["type"],
            "market": competitor["market"],
            "status": "deferred",
            "source": prior.get("source", "sitemap"),
            "error": None,
            "total_urls": prior.get("total_urls", 0),
            "content_urls": prior.get("content_urls", 0),
            "catalogue_urls": prior.get("catalogue_urls", 0),
            "first_run": False,
            "new_count": 0,
            "new": [],
            "rss": [],
            "note": "Not read this run - the run reached its time limit. Previous page set kept.",
        })
        if previous_index.get(domain):
            index[domain] = previous_index[domain]

    entries.sort(key=lambda item: (-item["new_count"], item["name"]))
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seconds": round(time.time() - started, 1),
        "baseline": not previous_index,
        "count": len(entries),
        "reachable": sum(1 for entry in entries if entry["status"] == "ok"),
        "total_new": sum(entry["new_count"] for entry in entries if not entry["first_run"]),
        "domains": entries,
        "index": index,
    }
    return payload


def save(payload):
    store.backend().put(STORE_NAME, payload)


def load():
    return store.backend().get(STORE_NAME)


def run_and_save(progress=None):
    payload = run(progress)
    save(payload)
    return payload


if __name__ == "__main__":
    result = run_and_save(print)
    print("\n=== publishing snapshot: %s (%ss) ===" % (result["generated_at"], result["seconds"]))
    print("reachable %d of %d · first run: %s"
          % (result["reachable"], result["count"], result["baseline"]))
    for entry in result["domains"]:
        print(" %-22s %-8s urls=%-5s new=%-3s rss=%s"
              % (entry["name"][:22], entry["status"], entry["total_urls"],
                 entry["new_count"], len(entry["rss"])))
        for item in entry["new"][:3]:
            print("     - [%s] %s" % (item["kind"], item["title"] or item["url"][-60:]))
    sys.exit(0)
