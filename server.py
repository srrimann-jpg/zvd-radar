"""ZVD Radar local service: API + dashboard, stdlib only.

    python3 server.py            # http://127.0.0.1:8090
    PORT=9000 python3 server.py

A scan runs automatically on start if today has none yet, and a background thread re-checks
every minute so the listener refreshes itself once a day while the app is running.
"""

import json
import mimetypes
import os
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from radar import competitors as comp_audit
from radar import scan as scan_job
from radar import store

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
HOST = os.environ.get("ZVD_HOST") or "127.0.0.1"


def _resolve_port():
    """ZVD_PORT wins. A bare PORT is honoured only when it is a real port: process runners
    sometimes export PORT=0 and binding to that hands the app a random port."""
    for key in ("ZVD_PORT", "PORT"):
        value = (os.environ.get(key) or "").strip()
        if value.isdigit() and 0 < int(value) < 65536:
            return int(value)
    return 8090


PORT = _resolve_port()

STATE = {
    "running": False,
    "step": "idle",
    "error": None,
    "started_at": None,
    "finished_at": None,
    "seconds": None,
}
STATE_LOCK = threading.Lock()

COMP_STATE = {"running": False, "error": None, "finished_at": None, "seconds": None}
COMP_LOCK = threading.Lock()


def run_competitor_audit():
    with COMP_LOCK:
        if COMP_STATE["running"]:
            return False
        COMP_STATE.update(running=True, error=None)
    started = time.time()
    try:
        comp_audit.save(comp_audit.run_audit())
        COMP_STATE.update(seconds=round(time.time() - started, 1))
    except Exception as error:  # noqa: BLE001
        COMP_STATE.update(error="%s: %s" % (type(error).__name__, error))
    finally:
        COMP_STATE.update(running=False, finished_at=time.time())
    return True


def start_competitor_audit():
    threading.Thread(target=run_competitor_audit, daemon=True).start()


def run_scan(progress=None):
    with STATE_LOCK:
        if STATE["running"]:
            return False
        STATE.update(running=True, step="Starting scan", error=None, started_at=time.time())
    started = time.time()

    def report(message):
        STATE["step"] = message

    try:
        snapshot = scan_job.build_snapshot(progress or report)
        store.save(snapshot)
        STATE.update(error=None, seconds=round(time.time() - started, 1), step="Done")
    except Exception as error:  # noqa: BLE001 - surface it in the UI instead of dying
        STATE.update(error="%s: %s" % (type(error).__name__, error), step="Failed")
    finally:
        STATE.update(running=False, finished_at=time.time())
    return True


def start_scan_async():
    threading.Thread(target=run_scan, daemon=True).start()


def has_today():
    return store.load_date(datetime.now().date().isoformat()) is not None


def scheduler():
    while True:
        try:
            if not STATE["running"] and not has_today():
                start_scan_async()
        except Exception:  # noqa: BLE001
            pass
        time.sleep(60)


class Handler(BaseHTTPRequestHandler):
    server_version = "ZVDRadar/1.0"

    def log_message(self, fmt, *args):
        if self.path.startswith("/api/"):
            print("[api] %s" % (fmt % args))

    # ---------- helpers ----------
    def _json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path):
        try:
            resolved = path.resolve()
            if not str(resolved).startswith(str(PUBLIC.resolve())):
                self._json({"error": "not found"}, 404)
                return
            if not resolved.is_file():
                self._json({"error": "not found"}, 404)
                return
            body = resolved.read_bytes()
        except OSError:
            self._json({"error": "not found"}, 404)
            return
        mime, _ = mimetypes.guess_type(str(resolved))
        self.send_response(200)
        self.send_header("Content-Type", (mime or "application/octet-stream") + (
            "; charset=utf-8" if (mime or "").startswith(("text/", "application/javascript")) else ""))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _state_payload(self):
        return {
            "running": STATE["running"],
            "step": STATE["step"],
            "error": STATE["error"],
            "started_at": STATE["started_at"],
            "finished_at": STATE["finished_at"],
            "seconds": STATE["seconds"],
            "has_today": has_today(),
        }

    # ---------- routes ----------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            self._file(PUBLIC / "index.html")
            return
        if path == "/api/radar":
            params = parse_qs(parsed.query)
            day = (params.get("date") or [""])[0]
            snapshot = store.load_date(day) if day else store.load_latest()
            self._json({
                "snapshot": snapshot,
                "state": self._state_payload(),
                "dates": store.list_dates()[:60],
                "history": store.history()[-30:],
            })
            return
        if path == "/api/state":
            self._json(self._state_payload())
            return
        if path == "/api/competitors":
            self._json({"data": comp_audit.load(), "state": COMP_STATE})
            return
        if path == "/api/health":
            self._json({"ok": True, "time": datetime.now().isoformat(timespec="seconds")})
            return
        self._file(PUBLIC / path.lstrip("/"))

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        if parsed.path == "/api/scan":
            if STATE["running"]:
                self._json({"started": False, "state": self._state_payload()}, 202)
                return
            start_scan_async()
            self._json({"started": True, "state": self._state_payload()}, 202)
            return
        if parsed.path == "/api/competitors/audit":
            if COMP_STATE["running"]:
                self._json({"started": False, "state": COMP_STATE}, 202)
                return
            start_competitor_audit()
            self._json({"started": True, "state": COMP_STATE}, 202)
            return
        self._json({"error": "not found"}, 404)


def main():
    if not has_today() and not STATE["running"]:
        print("No snapshot for today - starting first scan in the background.")
        start_scan_async()
    threading.Thread(target=scheduler, daemon=True).start()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    print("ZVD Radar listening on http://%s:%d  (Ctrl+C to stop)" % (HOST, PORT))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping ZVD Radar.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
