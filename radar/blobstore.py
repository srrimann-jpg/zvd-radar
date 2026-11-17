"""Vercel Blob storage backend, using only the standard library.

Vercel Functions run on a read-only filesystem, so once hosted the snapshots cannot live
in data/. They live in a Blob store instead, addressed by name ("latest.json",
"snapshots/2026-11-17.json") exactly like the local files, which keeps store.py unchanged
in shape.

This speaks the Blob REST API directly with urllib so the project keeps its
zero-dependency property. It is NOT verified against the live service yet - the first
deployment is the test. If reads fail, check that BLOB_READ_WRITE_TOKEN belongs to the
same store the writes went to.

Env:
    BLOB_READ_WRITE_TOKEN   set automatically when you connect a Blob store in Vercel
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://blob.vercel-storage.com"
TOKEN_ENV = "BLOB_READ_WRITE_TOKEN"
TIMEOUT = 20


class BlobError(RuntimeError):
    pass


class BlobBackend(object):
    """Name-addressed JSON storage. Mirrors the FileBackend interface in store.py."""

    label = "vercel-blob"

    def __init__(self, token=None, base=BASE):
        self.token = token or os.environ.get(TOKEN_ENV) or ""
        self.base = base.rstrip("/")
        if not self.token:
            raise BlobError("%s is not set" % TOKEN_ENV)

    # ---------- internals ----------
    def _request(self, method, url, data=None, headers=None):
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", "Bearer %s" % self.token)
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            body = error.read()[:300]
            raise BlobError("%s %s -> HTTP %s %s" % (method, url, error.code, body))
        except urllib.error.URLError as error:
            raise BlobError("%s %s -> %s" % (method, url, error.reason))

    def _url(self, name):
        return "%s/%s" % (self.base, urllib.parse.quote(name.lstrip("/")))

    # ---------- FileBackend interface ----------
    def get(self, name):
        try:
            body = self._request("GET", self._url(name))
        except BlobError as error:
            if "HTTP 404" in str(error):
                return None
            raise
        try:
            return json.loads(body.decode("utf-8"))
        except ValueError:
            return None

    def put(self, name, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        # x-add-random-suffix: 0 keeps the name predictable so get() can find it again;
        # without it every write lands at a new random pathname.
        self._request("PUT", self._url(name), data=body, headers={
            "x-content-type": "application/json",
            "x-add-random-suffix": "0",
            "x-cache-control-max-age": "60",
            "content-type": "application/json",
        })
        return True

    def names(self, prefix=""):
        query = urllib.parse.urlencode({"prefix": prefix}) if prefix else ""
        url = "%s%s" % (self.base, "?" + query if query else "")
        try:
            body = self._request("GET", url)
        except BlobError:
            return []
        try:
            payload = json.loads(body.decode("utf-8"))
        except ValueError:
            return []
        return [item.get("pathname", "") for item in payload.get("blobs", []) if item.get("pathname")]


def available():
    return bool(os.environ.get(TOKEN_ENV))
