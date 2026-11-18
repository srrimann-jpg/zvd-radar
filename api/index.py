"""Hosted entry point: the same radar, served as a WSGI app on Vercel.

Vercel Functions run on a read-only filesystem and have no long-lived process, so the two
things the local server does are handled differently here:

  * storage  -> Vercel Blob when BLOB_READ_WRITE_TOKEN is set, otherwise the read-only
                snapshots committed under data/ (enough to serve the site on day one)
  * schedule -> a Vercel Cron Job calls /api/cron/scan once a day

Everything in radar/ is unchanged and shared with the local server.

Local check:
    pip install -r requirements.txt
    python3 -m api.index          # http://127.0.0.1:8091
"""

import json
import os
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flask import Flask, jsonify, request, send_from_directory  # noqa: E402

from radar import battlecards as battle_audit  # noqa: E402
from radar import blobstore, competitors as comp_audit, demand  # noqa: E402
from radar import publishing as pub_job  # noqa: E402
from radar import scan as scan_job, store  # noqa: E402

PUBLIC = os.path.join(ROOT, "public")

# Pick the storage backend once, at import. A read-only filesystem would fail on the
# first save, so surfaced here rather than in the middle of a cron run.
STORAGE_MODE = "files"
if blobstore.available():
    try:
        store.set_backend(blobstore.BlobBackend())
        STORAGE_MODE = "vercel-blob"
    except blobstore.BlobError as error:  # pragma: no cover - config problem
        sys.stderr.write("blob backend unavailable: %s\n" % error)

app = Flask(__name__, static_folder=None)

STATE = {
    "running": False,
    "step": "idle",
    "error": None,
    "started_at": None,
    "finished_at": None,
    "seconds": None,
}


def _routes(path):
    """Register under /api/<x> and also bare /<x>, so the app works whichever prefix
    Vercel hands the WSGI app."""
    def decorate(function):
        app.route(path, methods=["GET", "POST"])(function)
        if path.startswith("/api/"):
            app.route(path[4:], methods=["GET", "POST"])(function)
        return function
    return decorate


def _has_today():
    return store.load_date(datetime.now().date().isoformat()) is not None


def _state_payload():
    return {
        "running": STATE["running"],
        "step": STATE["step"],
        "error": STATE["error"],
        "started_at": STATE["started_at"],
        "finished_at": STATE["finished_at"],
        "seconds": STATE["seconds"],
        "has_today": _has_today(),
        "storage": STORAGE_MODE,
        "writable": STORAGE_MODE != "files",
    }


def _run_scan():
    """Run one scan synchronously and persist it. Returns the snapshot."""
    STATE.update(running=True, step="Collecting sources", error=None, started_at=time.time())
    started = time.time()
    try:
        snapshot = scan_job.build_snapshot(lambda message: STATE.update(step=message))
        store.save(snapshot)
        STATE.update(step="Done", error=None, seconds=round(time.time() - started, 1))
        return snapshot
    except Exception as error:  # noqa: BLE001 - report, never crash the function
        STATE.update(step="Failed", error="%s: %s" % (type(error).__name__, error))
        raise
    finally:
        STATE.update(running=False, finished_at=time.time())


@_routes("/api/health")
def health():
    return jsonify({"ok": True, "time": datetime.now().isoformat(timespec="seconds"),
                    "storage": STORAGE_MODE})


@_routes("/api/state")
def state():
    return jsonify(_state_payload())


@_routes("/api/radar")
def radar():
    day = (request.args.get("date") or "").strip()
    snapshot = store.load_date(day) if day else store.load_latest()

    # A brand new deployment with nothing stored yet: build the first snapshot inline
    # rather than showing an empty dashboard. The cron does this from then on.
    if snapshot is None and not day:
        try:
            snapshot = _run_scan()
        except Exception:  # noqa: BLE001 - fall through to the empty payload
            snapshot = None

    snapshot = demand.enrich_snapshot(snapshot)
    payload = {
        "snapshot": snapshot,
        "state": _state_payload(),
        "dates": store.list_dates()[:60],
        "history": store.history()[-30:],
    }
    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store"
    return response


@_routes("/api/competitors")
def competitors():
    try:
        data = comp_audit.load()
    except Exception as error:  # noqa: BLE001
        data = {"error": "%s: %s" % (type(error).__name__, error)}
    return jsonify({"data": data, "state": {"mode": "read-only" if STORAGE_MODE == "files"
                                            else STORAGE_MODE}})


@_routes("/api/storage/selftest")
def storage_selftest():
    backend = store.backend()
    if hasattr(backend, "selftest"):
        return jsonify(backend.selftest())
    return jsonify({"storage": STORAGE_MODE, "write": "ok (local disk)",
                    "read": "ok (local disk)", "list": "ok (local disk)",
                    "access": "n/a", "store_id": "n/a", "error": None})


@_routes("/api/battlecards")
def battlecards():
    payload = battle_audit.build()
    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store"
    return response


@_routes("/api/cron/scan")
def cron_scan():
    """Vercel Cron target. Vercel sends `Authorization: Bearer $CRON_SECRET` when that
    env var is set, so a stranger cannot force repeated scans."""
    secret = os.environ.get("CRON_SECRET")
    if secret:
        header = request.headers.get("Authorization") or ""
        if header != "Bearer %s" % secret:
            return jsonify({"error": "unauthorized"}), 401
    if STORAGE_MODE == "files":
        return jsonify({"error": "no writable storage configured; set BLOB_READ_WRITE_TOKEN"}), 503
    try:
        snapshot = _run_scan()
    except Exception as error:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(error)}), 500
    return jsonify({"ok": True, "date": snapshot["date"], "signals": snapshot["stats"]["signals"],
                    "seconds": snapshot["scan_seconds"]})


@_routes("/api/scan")
def manual_scan():
    secret = os.environ.get("SCAN_SECRET")
    if secret and (request.args.get("key") or "") != secret:
        return jsonify({"error": "unauthorized"}), 401
    if STORAGE_MODE == "files":
        return jsonify({"error": "no writable storage configured"}), 503
    try:
        snapshot = _run_scan()
    except Exception as error:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(error)}), 500
    return jsonify({"ok": True, "date": snapshot["date"], "state": _state_payload()})


@_routes("/api/publishing")
def publishing():
    if request.method == "POST":
        return jsonify({"error": "publishing refresh runs from the local server only",
                        "hint": "python3 -m radar.publishing"}), 503
    return jsonify({"data": pub_job.load(),
                    "state": {"mode": "read-only" if STORAGE_MODE == "files" else STORAGE_MODE}})


@_routes("/api/competitors/audit")
def competitor_audit():
    # The 22-site audit takes about a minute and needs a writable store; run it locally.
    return jsonify({"error": "competitor audit runs from the local server only",
                    "hint": "python3 -m radar.competitors"}), 503


@app.route("/")
def index():
    return send_from_directory(PUBLIC, "index.html")


@app.route("/<path:filename>")
def assets(filename):
    return send_from_directory(PUBLIC, filename)


if __name__ == "__main__":
    # Deliberately not PORT: runners and hosts export it for their own use, and binding
    # to it silently moves the dev server somewhere unexpected.
    port = int(os.environ.get("ZVD_WEB_PORT") or 8091)
    app.run(host="127.0.0.1", port=port, debug=False)
