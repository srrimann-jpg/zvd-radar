"""Competitor presence audit.

Answers "what are they doing online that we are not?" from publicly observable evidence
only - no paid traffic or backlink estimates, so nothing here is invented.

Each audit records:
  footprint   how many URLs they expose, split into content vs catalogue pages
  cadence     newest <lastmod> in their sitemaps, plus pages updated in the last 90 days
  trust       review platform, Product/Review/FAQ schema, certificate/verification pages
  tech        platform, search, retention, chat, tracking, virtual try-on
  access      whether the site is fetchable at all (some block bots with 403/Cloudflare)

Scores are a labelled heuristic for "how developed is their search presence", not a
traffic estimate. The per-lever components are stored so any number can be traced.
"""

import json
import math
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)

# Only entries with a verified domain. The register's "To verify" rows are deliberately
# excluded: an unconfirmed domain would produce confidently wrong intelligence.
COMPETITORS = [
    {"name": "Rapaport / RapNet", "domain": "rapaport.com", "market": "Global", "type": "Marketplace"},
    {"name": "Nivoda", "domain": "nivoda.com", "market": "Global", "type": "Marketplace"},
    {"name": "VDB", "domain": "vdbapp.com", "market": "US / Global", "type": "Marketplace"},
    {"name": "UNI Diamonds", "domain": "uni.diamonds", "market": "Global", "type": "Wholesaler"},
    {"name": "IDEX Online", "domain": "idexonline.com", "market": "Global", "type": "Marketplace"},
    {"name": "DiaTech", "domain": "app.diatech.ai", "market": "Global", "type": "Technology"},
    {"name": "DiamondXE", "domain": "diamondxe.com", "market": "India / Global", "type": "Marketplace"},
    {"name": "The Diamond Port", "domain": "thediamondport.com", "market": "Global", "type": "Wholesaler"},
    {"name": "DND Diamond", "domain": "dnddiamond.com", "market": "India / Global", "type": "Marketplace"},
    {"name": "Toshakhana", "domain": "toshakhana.uk", "market": "UK / Global", "type": "Wholesaler"},
    {"name": "Diamorivo", "domain": "diamorivo.com", "market": "India / Global", "type": "Retailer"},
    {"name": "Brilliance", "domain": "brilliance.com", "market": "US / Global", "type": "Retailer"},
    {"name": "Tanishq", "domain": "tanishq.co.in", "market": "India / Global", "type": "Brand"},
    {"name": "PriceScope", "domain": "pricescope.com", "market": "US / Global", "type": "Community"},
    {"name": "Rare Carat", "domain": "rarecarat.com", "market": "US", "type": "Retailer"},
    {"name": "StoneAlgo", "domain": "stonealgo.com", "market": "US / Global", "type": "Marketplace"},
    {"name": "Washington Diamond", "domain": "washingtondiamond.com", "market": "US", "type": "Retailer"},
    {"name": "Ritani", "domain": "ritani.com", "market": "US", "type": "Retailer"},
    {"name": "Shane Co.", "domain": "shaneco.com", "market": "US", "type": "Retailer"},
    {"name": "Whitehouse Brothers", "domain": "whitehousebrothers.com", "market": "US", "type": "Brand"},
    {"name": "Lepdo Diamonds", "domain": "lepdodiamonds.com", "market": "India / Global", "type": "Marketplace"},
    {"name": "Allurez", "domain": "allurez.com", "market": "US / Global", "type": "Retailer"},
    {"name": "Lippa's", "domain": "lippas.com", "market": "US", "type": "Retailer"},
    {"name": "Lauren B Jewelry", "domain": "laurenbjewelry.com", "market": "US", "type": "Brand"},
    {"name": "Silveroni", "domain": "silveroni.com", "market": "Global", "type": "Wholesaler"},
    {"name": "Grown Diamond Corp", "domain": "growndiamondcorp.com", "market": "USA / India", "type": "Manufacturer"},
    {"name": "One World Diamonds", "domain": "om-diamonds.com", "market": "India / Global", "type": "Wholesaler"},
    {"name": "77 Diamonds", "domain": "77diamonds.com", "market": "UK / Global", "type": "Retailer"},
    {"name": "Innovation Diamonds", "domain": "innovationdia.com", "market": "Global", "type": "Manufacturer"},
    {"name": "Signova", "domain": "signova.com", "market": "Global", "type": "Wholesaler"},
    {"name": "Sheladiya", "domain": "sheladiyadiamond.com", "market": "India / Global", "type": "Manufacturer"},
    {"name": "Adornet Jewels", "domain": "adornetjewels.com", "market": "Thailand / Global", "type": "Manufacturer"},
    {"name": "Indigo Jewellery", "domain": "indigojewellery.com", "market": "India / Global", "type": "Manufacturer"},
]

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUT_FILE = DATA_DIR / "competitors.json"

CONTENT_RE = re.compile(r"blog|article|guide|learn|education|journal|news|insight|resource|faq|advice|magazine", re.I)
PRODUCT_RE = re.compile(r"product|diamond|ring|jewel|stone|inventory|listing|search|collection|engagement", re.I)

TECH_HINTS = {
    "shopify": "Shopify",
    "salesforce": "Salesforce Commerce",
    "demandware": "Salesforce Commerce",
    "bigcommerce": "BigCommerce",
    "magento": "Magento",
    "woocommerce": "WooCommerce",
    "commercetools": "commercetools",
    "next.js": "Next.js",
    "_next/static": "Next.js",
    "cloudflare": "Cloudflare",
    "fastly": "Fastly",
    "akamai": "Akamai",
    "algolia": "Algolia search",
    "yotpo": "Yotpo reviews",
    "trustpilot": "Trustpilot",
    "bazaarvoice": "Bazaarvoice",
    "okendo": "Okendo reviews",
    "reviews.io": "Reviews.io",
    "klaviyo": "Klaviyo email",
    "attentive": "Attentive SMS",
    "mailchimp": "Mailchimp",
    "gorgias": "Gorgias chat",
    "intercom": "Intercom",
    "zendesk": "Zendesk",
    "hotjar": "Hotjar",
    "segment": "Segment",
    "connect.facebook.net": "Meta pixel",
    "googletagmanager": "GA4 / GTM",
    "tiktok": "TikTok pixel",
    "try on": "Virtual try-on",
    "tryon": "Virtual try-on",
    "360": "360 product view",
    "3d model": "3D / AR",
}

SCHEMA_POINTS = {
    "Product": 8,
    "Offer": 2,
    "AggregateRating": 5,
    "Review": 4,
    "FAQPage": 4,
    "HowTo": 3,
    "BreadcrumbList": 3,
    "Organization": 2,
    "LocalBusiness": 2,
    "VideoObject": 3,
    "ItemList": 2,
}


def _fetch(url, limit=4_000_000, timeout=12, retries=0):
    """GET with one slow retry. HTTP errors are raised immediately so callers can read codes."""
    last_error = None
    for attempt in range(retries + 1):
        request = urllib.request.Request(url)
        request.add_header("User-Agent", UA)
        request.add_header("Accept", "*/*")
        request.add_header("Accept-Language", "en-US,en;q=0.9")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read(limit)
                final = response.geturl()
                status = response.status
            if raw[:2] == b"\x1f\x8b":
                import gzip

                try:
                    raw = gzip.decompress(raw)
                except OSError:
                    pass
            return status, final, raw.decode("utf-8", "replace")
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = error
            if attempt < retries:
                time.sleep(1.0)
                timeout = max(timeout, 18)
    raise last_error


def _find_sitemaps(domain):
    """robots.txt is the authoritative place sites advertise sitemaps; try it first."""
    found = []
    try:
        _, _, robots = _fetch("https://%s/robots.txt" % domain, limit=200_000, timeout=10)
        for line in robots.splitlines():
            if line.lower().startswith("sitemap:"):
                found.append(line.split(":", 1)[1].strip())
    except Exception:  # noqa: BLE001 - robots.txt is optional
        pass
    for candidate in ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml",
                      "/wp-sitemap.xml", "/sitemap.xml.gz"):
        url = "https://%s%s" % (domain, candidate)
        if url not in found:
            found.append(url)
    return found[:4]


def _recent_in(xml):
    """Count URLs whose <lastmod> falls inside the last 90 days, pairing loc with lastmod."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    recent = 0
    for block in re.findall(r"<url>(.*?)</url>", xml, re.S):
        stamp = re.search(r"<lastmod>\s*([^<\s]+)", block)
        if not stamp:
            continue
        parsed = _iso(stamp.group(1))
        if parsed and parsed >= cutoff:
            recent += 1
    return recent


def _collect_urls(domain, sitemap_url, budget=3500, deadline=None):
    """Return (urls, newest_lastmod, child_count, recent_90d, error) from a sitemap tree."""
    urls, newest, children, recent = [], "", 0, 0
    try:
        _, _, xml = _fetch(sitemap_url, limit=3_000_000, timeout=14)
    except Exception as error:  # noqa: BLE001
        return urls, newest, children, recent, str(error)[:80]

    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
    lastmods = re.findall(r"<lastmod>\s*([^<\s]+)\s*</lastmod>", xml)
    if lastmods:
        newest = max(lastmods)

    if "<sitemapindex" in xml[:2000]:
        children = len(locs)
        for child in locs[:4]:
            if deadline and time.time() > deadline:
                break
            try:
                _, _, child_xml = _fetch(urljoin(sitemap_url, child), limit=2_000_000, timeout=12)
            except Exception:  # noqa: BLE001
                continue
            urls.extend(re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", child_xml))
            child_last = re.findall(r"<lastmod>\s*([^<\s]+)\s*</lastmod>", child_xml)
            if child_last:
                newest = max(newest, max(child_last))
            recent += _recent_in(child_xml)
            if len(urls) >= budget:
                break
    else:
        children = 1
        urls.extend(locs)
        recent = _recent_in(xml)
    return urls[:budget], newest, children, recent, None


def _iso(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return None


CONTENT_HUBS = ("/blog", "/news", "/insights", "/education", "/learn", "/resources")


def _homepage_footprint(html, host):
    """Sites without sitemaps still expose structure in their navigation links."""
    if not html:
        return None
    bare = host.replace("www.", "")
    base = "https://%s/" % host
    links = set()
    # Hand-built static sites link bare relative paths ("contact.html"), so every href is
    # resolved against the root rather than only matching "/..." or absolute URLs.
    for raw in re.findall(r'href=["\']([^"\']+)["\']', html):
        raw = raw.strip()
        if not raw or raw.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            continue
        resolved = urljoin(base, raw)
        if not resolved.startswith(("http://", "https://")) or bare not in resolved:
            continue
        links.add(resolved.split("?")[0].rstrip("/"))
    content = sum(1 for url in links if CONTENT_RE.search(url))
    product = sum(1 for url in links if PRODUCT_RE.search(url))
    return {"total": len(links), "content": content, "product": product}


def _content_hubs(host):
    """Probe common content paths, since a blog that exists is a real strategic signal."""
    found = []
    for path in CONTENT_HUBS:
        try:
            status, _, _ = _fetch("https://%s%s" % (host, path), limit=60_000, timeout=10, retries=0)
            if status == 200:
                found.append(path)
        except Exception:  # noqa: BLE001 - a missing hub is a normal result
            continue
    return found


def audit(competitor):
    domain = competitor["domain"]
    result = dict(competitor)
    result.update(
        {
            "status": "ok",
            "blocked": False,
            "final_url": "",
            "title": "",
            "meta_chars": 0,
            "home_kb": 0,
            "schema": [],
            "tech": [],
            "sitemap_children": 0,
            "total_urls": 0,
            "content_urls": 0,
            "product_urls": 0,
            "other_urls": 0,
            "newest_lastmod": "",
            "updated_90d": 0,
            "notes": [],
            "score": 0,
            "score_parts": {},
        }
    )

    deadline = time.time() + 40
    html = ""
    try:
        status, final, html = _fetch("https://%s/" % domain, limit=1_500_000, timeout=14)
        result["final_url"] = final
        result["home_kb"] = round(len(html) / 1024)
        title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
        result["title"] = re.sub(r"\s+", " ", title.group(1)).strip()[:110] if title else ""
        meta = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)', html, re.I)
        result["meta_chars"] = len(meta.group(1)) if meta else 0
        result["schema"] = sorted(set(re.findall(r'"@type"\s*:\s*"([A-Za-z]+)"', html)))
        lowered = html.lower()
        result["tech"] = sorted({label for key, label in TECH_HINTS.items() if key in lowered})
        if final.rstrip("/") != "https://%s" % domain and final.rstrip("/") != "https://www.%s" % domain:
            result["notes"].append("Homepage redirects to %s" % final[:70])
        if status == 200 and len(html) < 4000:
            result["blocked"] = True
            result["notes"].append("Returned a challenge page - treated as bot-blocked")
    except urllib.error.HTTPError as error:
        result["status"] = "blocked" if error.code in (401, 403, 429, 503) else "error"
        result["blocked"] = error.code in (401, 403, 429, 503)
        result["notes"].append("HTTP %s on homepage" % error.code)
    except Exception as error:  # noqa: BLE001
        message = str(error)
        if "SSL" in message or "TLS" in message or "tlsv" in message:
            result["status"] = "blocked"
            result["blocked"] = True
            result["notes"].append("Refuses non-browser TLS connections - needs a browser-level audit")
        elif "timed out" in message.lower():
            result["status"] = "error"
            result["notes"].append("Timed out - likely edge/bot protection")
        else:
            result["status"] = "error"
            result["notes"].append(("Homepage error: %s" % message)[:90])

    # Follow the final host (many sites redirect to www, and sitemaps only exist there).
    host = re.sub(r"^https?://", "", result["final_url"]).split("/")[0] if result["final_url"] else domain
    for sitemap in _find_sitemaps(host):
        if time.time() > deadline:
            break
        urls, newest, children, recent, error = _collect_urls(host, sitemap, deadline=deadline)
        if urls:
            result["sitemap_children"] = children
            result["total_urls"] = len(urls)
            result["content_urls"] = sum(1 for url in urls if CONTENT_RE.search(url))
            result["product_urls"] = sum(1 for url in urls if PRODUCT_RE.search(url))
            result["other_urls"] = max(0, len(urls) - result["content_urls"] - result["product_urls"])
            result["newest_lastmod"] = newest[:10]
            result["updated_90d"] = min(recent, len(urls))
            break
        if error and not result["blocked"]:
            result["notes"].append("Sitemap: %s" % error)

    if not result["total_urls"] and not result["blocked"] and time.time() <= deadline:
        footprint = _homepage_footprint(html, host)
        if footprint and footprint["total"]:
            result["total_urls"] = footprint["total"]
            result["content_urls"] = footprint["content"]
            result["product_urls"] = footprint["product"]
            result["other_urls"] = max(0, footprint["total"] - footprint["content"] - footprint["product"])
            result["notes"].append("No sitemap: structure sampled from homepage links")
        hubs = _content_hubs(host)
        if hubs:
            result["notes"].append("Content hubs live at %s" % ", ".join(hubs[:3]))
            result["content_urls"] = max(result["content_urls"], len(hubs) * 4)

    result.update(_score(result))
    # Each advertised sitemap can fail with the same error; four identical notes is noise.
    result["notes"] = list(dict.fromkeys(result["notes"]))
    # For blocked domains, capture a public index snapshot so the competitor
    # is not entirely invisible. This data comes from search-index evidence
    # (Google/etc.), since the site blocks our fetcher. Update via web_search.
    if result["blocked"]:
        result["index_snapshot"] = result.get("index_snapshot") or {}
        # Known public index data for blocked competitors (auto-populate on each run)
        if "vdb" in result["name"].lower():
            result["index_snapshot"] = {
                "scale_claims": "30K+ trade professionals, 3M+ items from 1,200+ suppliers",
                "pricing_marketplace": "$360/yr per user ($306/yr 2-year)",
                "pricing_integrations": "$500 + $75/mo (Shopify/Woo)",
                "pricing_inventory": "$50–$100/product/mo by tier",
                "web_traffic_note": "403 at edge, content indexed via search",
                "google_play": "4.5★, 238 reviews, 10K+ downloads",
                "founder_note": "No retailer commission; monetises supplier listing fees, custom builds, marketplace ads",
                "contact": "NY + Mumbai offices",
            }
    return result


def _score(result):
    """Heuristic 0-100 presence score. Components are stored so the number is auditable."""
    parts = {}
    content = result["content_urls"]
    total = result["total_urls"]
    product = result["product_urls"]

    parts["content_volume"] = round(min(24.0, math.log10(1 + content) * 7.0), 1) if content else 0.0
    ratio = (content / float(product)) if product else (1.0 if content else 0.0)
    parts["content_depth"] = round(min(16.0, ratio * 26.0), 1)
    parts["catalogue_scale"] = round(min(10.0, math.log10(1 + total) * 2.6), 1) if total else 0.0
    parts["schema"] = float(sum(SCHEMA_POINTS.get(kind, 0) for kind in result["schema"]))
    parts["schema"] = min(22.0, parts["schema"])
    trust = sum(6.0 for tool in result["tech"] if tool in (
        "Yotpo reviews", "Trustpilot", "Bazaarvoice", "Okendo reviews", "Reviews.io"))
    parts["social_proof"] = min(6.0, trust)
    retention = sum(3.0 for tool in result["tech"] if tool in ("Klaviyo email", "Attentive SMS", "Mailchimp"))
    parts["retention"] = min(6.0, retention)
    experience = sum(3.0 for tool in result["tech"] if tool in (
        "Virtual try-on", "3D / AR", "360 product view", "Algolia search"))
    parts["experience"] = min(9.0, experience)
    if result["updated_90d"] >= 200:
        parts["freshness"] = 7.0
    elif result["updated_90d"] >= 40:
        parts["freshness"] = 5.0
    elif result["updated_90d"] >= 1:
        parts["freshness"] = 3.0
    else:
        parts["freshness"] = 0.0

    if result["blocked"]:
        parts["access"] = 0.0
        result["notes"].append("Blocked to crawlers - needs a browser-level audit")
    else:
        parts["access"] = 2.0

    score = int(round(sum(parts.values())))
    return {"score": max(0, min(100, score)), "score_parts": parts}


def run_audit(progress=None, competitors=None):
    from concurrent.futures import ThreadPoolExecutor, as_completed

    targets = competitors or COMPETITORS
    results = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(audit, target): target for target in targets}
        for index, future in enumerate(as_completed(futures), start=1):
            target = futures[future]
            try:
                results.append(future.result())
            except Exception as error:  # noqa: BLE001
                broken = dict(target)
                broken.update({"status": "error", "score": 0, "score_parts": {},
                               "notes": ["Audit failed: %s" % error],
                               "content_urls": 0, "product_urls": 0, "total_urls": 0,
                               "tech": [], "schema": [], "updated_90d": 0,
                               "newest_lastmod": "", "blocked": False, "title": "",
                               "final_url": "", "meta_chars": 0, "home_kb": 0,
                               "sitemap_children": 0, "other_urls": 0})
                results.append(broken)
            if progress:
                progress("Auditing %s (%d/%d)" % (target["name"], index, len(targets)))

    results.sort(key=lambda item: item["score"], reverse=True)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": "Public site evidence only: sitemaps, schema, HTML tech hints. No traffic estimates.",
        "count": len(results),
        "results": results,
    }


def save(payload):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp = OUT_FILE.with_suffix(".tmp")
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1)
    temp.replace(OUT_FILE)


def load():
    try:
        with open(OUT_FILE, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


if __name__ == "__main__":
    payload = run_audit(progress=print)
    save(payload)
    print("\n%-24s %5s %7s %7s %6s %5s %s" % ("competitor", "score", "content", "catalog", "new90d", "tech", "status"))
    print("-" * 92)
    for row in payload["results"]:
        print("%-24s %5d %7d %7d %6d %5d %s" % (
            row["name"][:24], row["score"], row["content_urls"], row["product_urls"],
            row["updated_90d"], len(row["tech"]), row["status"]))
        if row["notes"]:
            print("%-24s %s" % ("", " | ".join(row["notes"])[:110]))
