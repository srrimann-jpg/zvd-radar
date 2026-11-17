"""Snapshot storage: one JSON document per day, plus a rolling history for momentum.

The public API is unchanged from the local-only version. What is new is the *backend*:
on this machine snapshots are files under data/, while on Vercel the filesystem is
read-only, so the hosted entry point swaps in a Blob backend (see radar/blobstore.py)
before anything is saved. Names are identical either way.

    store.set_backend(FileBackend())   # default
    store.set_backend(BlobBackend())   # hosted
"""

import json
import os
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
LATEST = DATA_DIR / "latest.json"
HISTORY = DATA_DIR / "history.json"

LATEST_NAME = "latest.json"
HISTORY_NAME = "history.json"
SNAPSHOT_PREFIX = "snapshots/"


class FileBackend(object):
    """Default backend: JSON files under data/, atomic writes, no dependencies."""

    label = "files"

    def __init__(self, directory=None):
        self.directory = Path(directory or DATA_DIR)

    def _path(self, name):
        return self.directory / name

    def get(self, name):
        try:
            with open(self._path(name), "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return None

    def put(self, name, payload):
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=1)
        os.replace(temp, path)
        return True

    def names(self, prefix=""):
        folder = self._path(prefix.rstrip("/") or ".")
        if not folder.is_dir():
            return []
        return sorted(
            [path.stem for path in folder.glob("*.json") if path.is_file()],
            reverse=True,
        )


BACKEND = FileBackend()


def set_backend(backend):
    """Hosted entry points call this once at import time."""
    global BACKEND
    BACKEND = backend
    return BACKEND


def backend():
    return BACKEND


def _snapshot_name(day):
    return "%s%s.json" % (SNAPSHOT_PREFIX, day)


def save(snapshot):
    BACKEND.put(_snapshot_name(snapshot["date"]), snapshot)
    BACKEND.put(LATEST_NAME, snapshot)
    _append_history(snapshot)


def _append_history(snapshot):
    history = BACKEND.get(HISTORY_NAME) or {"entries": []}
    entry = {
        "date": snapshot["date"],
        "generated_at": snapshot["generated_at"],
        "signals": snapshot["stats"]["signals"],
        "themes": {theme["id"]: theme["count"] for theme in snapshot["themes"]},
        "brand_mentions": snapshot["brand"]["total_mentions"],
    }
    entries = [item for item in history["entries"] if item.get("date") != snapshot["date"]]
    entries.append(entry)
    entries.sort(key=lambda item: item.get("date", ""))
    history["entries"] = entries[-90:]
    BACKEND.put(HISTORY_NAME, history)


def load_latest():
    return BACKEND.get(LATEST_NAME)


def load_date(day):
    return BACKEND.get(_snapshot_name(day))


def list_dates():
    names = BACKEND.names(SNAPSHOT_PREFIX)
    days = []
    for name in names:
        stem = name.split("/")[-1]
        if stem.endswith(".json"):
            days.append(stem[:-5])
        elif stem:
            days.append(stem)
    return sorted(set(days), reverse=True)


def history():
    return (BACKEND.get(HISTORY_NAME) or {"entries": []})["entries"]


def previous_theme_counts(before_date):
    """Theme counts from the most recent scan older than `before_date`."""
    for entry in reversed(history()):
        if entry.get("date", "") < before_date:
            return entry.get("themes") or {}
    return {}
