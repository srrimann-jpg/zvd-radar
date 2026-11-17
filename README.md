# ZVD Radar

A daily listener for the diamond and jewellery industry. It reads public news, community
and search-suggestion sources, scores them against an 11-theme domain model, and produces
ranked content topics with briefs — plus a competitor audit and a Keyword Planner
enrichment layer.

Built for **zvdapp.com**. No API keys needed for the core scan; everything is stdlib
Python except the hosted entry point.

## Run locally

```bash
python3 server.py            # http://127.0.0.1:8090
ZVD_PORT=9000 python3 server.py
```

A scan runs on start if today has none, and a background thread re-checks every minute so
the dashboard refreshes itself once a day while the app is open.

Other entry points:

```bash
python3 -m radar.scan                       # one scan, printed summary
python3 -m radar.competitors                # 22-domain competitor audit (~60s)
python3 -m radar.keywordlist                # regenerate the Keyword Planner paste list
python3 -m radar.keywords import <csv> --country IN
python3 -m radar.keywords coverage          # did the export measure our list?
python3 -m radar.topkeywords                # ranked shortlist CSV with evidence
```

## What is where

| Path | Purpose |
|---|---|
| `radar/taxonomy.py` | themes, seeds, news queries, competitor list — edit vocabulary here |
| `radar/sources.py` | Google News RSS, Bing News RSS, Reddit Atom, Google autocomplete |
| `radar/analyze.py` | scoring, intent classification, brief generation |
| `radar/scan.py` | one scan = collect, score, rank, assemble the snapshot |
| `radar/store.py` | snapshot storage (file backend locally, Blob backend when hosted) |
| `radar/blobstore.py` | Vercel Blob backend, stdlib HTTP only |
| `radar/keywords.py` | Keyword Planner importer with bucket/range provenance |
| `radar/demand.py` | joins that demand data onto scan intents (volume, competition, bids) |
| `radar/topkeywords.py` | ranked shortlist export with evidence columns |
| `radar/competitors.py` | website/content audit across verified COMPETITORS |
| `server.py` | local HTTP server + API + dashboard |
| `api/index.py` | hosted WSGI app (Vercel) |
| `public/` | dashboard: `index.html`, `app.js`, `styles.css` |

## Deploy to Vercel

The local server uses `http.server` and a writable disk. Vercel has neither, so the hosted
path is `api/index.py` (WSGI) plus a Blob store for snapshots. Both share `radar/`
unchanged.

1. **Push this repo to GitHub**, then in Vercel: *Add New → Project → Import* the repo.
   Framework preset: **Other**. No build command is needed.
2. **Create a Blob store**: project → *Storage → Create → Blob*. This injects
   `BLOB_READ_WRITE_TOKEN` into the project's environment automatically.
3. **Add `CRON_SECRET`** (any long random string) under *Settings → Environment Variables*.
   Vercel sends it as `Authorization: Bearer …` on cron invocations, and the app rejects
   the request without it.
4. **Redeploy** so the new env vars are picked up.
5. The cron in `vercel.json` (`0 4 * * *`, UTC) hits `/api/cron/scan` once a day. On the
   Hobby plan a cron fires within its chosen hour and never retries, so a missed day shows
   the previous snapshot rather than breaking the site.

`data/` is committed deliberately: it seeds the first deployment so the dashboard has
something to show before the first cron run.

## Known limits

- **Volumes are buckets, not numbers.** Keyword Planner reports ranges (`1K – 10K`) on a
  no-spend account and encodes them as a midpoint (`5000`). `radar/keywords.py` stores both
  the midpoint and the range label, and never treats a midpoint as exact.
- **No monthly trend data** on this account tier: the `Searches: <month>` columns export
  empty.
- **Competitor audit is local-only.** It takes about a minute and writes a large JSON file;
  the hosted route returns 503. Run `python3 -m radar.competitors` locally.
- **The Blob backend is unverified against the live service.** It speaks the documented
  REST API with stdlib `urllib`; the first real deployment is the test. If reads fail,
  confirm `BLOB_READ_WRITE_TOKEN` belongs to the store the writes went to.
- **Google autocomplete may rate-limit** harder from cloud IPs than from a home
  connection. The scan degrades gracefully and reports skipped sources.
