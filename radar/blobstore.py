"""Vercel Blob storage backend, standard library only.

Vercel Functions run on a read-only filesystem, so once hosted the snapshots cannot live
in data/. They live in a Blob store instead, addressed by name ("latest.json",
"snapshots/2026-11-18.json") exactly like the local files, which keeps store.py unchanged
in shape.

This speaks the same REST API the official SDK uses (API version 13), so the project
keeps its zero-dependency property:

    upload   PUT  https://blob.vercel-storage.com/?pathname=<name>
                  x-vercel-blob-access, x-content-type, x-add-random-suffix,
                  x-allow-overwrite, x-cache-control-max-age, x-api-version
    download GET  https://<store-id>.<public|private>.blob.vercel-storage.com/<name>
    list     GET  https://blob.vercel-storage.com?prefix=<name>&limit=<n>

The store id comes from BLOB_STORE_ID when Vercel sets it, otherwise it is read out of
the read-write token. When neither yields one, a download falls back to resolving the
blob's URL through the list endpoint, which always returns the authoritative URL.

Env:
    BLOB_READ_WRITE_TOKEN   set automatically when you connect a Blob store in Vercel
    BLOB_STORE_ID           optional; Vercel sets it when OIDC is in use
    BLOB_ACCESS             optional; "public" (default) or "private"
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

API = "https://blob.vercel-storage.com"
API_VERSION = "13"
TOKEN_ENV = "BLOB_READ_WRITE_TOKEN"
ACCESS_ENV = "BLOB_ACCESS"
STORE_ENV = "BLOB_STORE_ID"
TOKEN_PREFIX = "vercel_blob_rw_"
TIMEOUT = 30


class BlobError(RuntimeError):
    pass


def _store_id_from_token(token):
    """Read-write tokens look like vercel_blob_rw_<store-id>_<secret>."""
    if not token.startswith(TOKEN_PREFIX):
        return ""
    rest = token[len(TOKEN_PREFIX):]
    parts = rest.split("_")
    if len(parts) >= 2 and parts[0] == "store":
        return "store_%s" % parts[1]
    return parts[0] if parts else ""


class BlobBackend(object):
    """Name-addressed JSON storage. Mirrors the FileBackend interface in store.py."""

    label = "vercel-blob"

    def __init__(self, token=None, access=None, store_id=None, api=API):
        self.token = token or os.environ.get(TOKEN_ENV) or ""
        if not self.token:
            raise BlobError("%s is not set" % TOKEN_ENV)
        self.access = (access or os.environ.get(ACCESS_ENV) or "public").lower()
        if self.access not in ("public", "private"):
            self.access = "public"
        self.store_id = store_id or os.environ.get(STORE_ENV) or _store_id_from_token(self.token)
        self.api = api.rstrip("/")
        self._urls = {}

    # ---------- internals ----------
    def _auth_headers(self, headers=None):
        merged = {
            "authorization": "Bearer %s" % self.token,
            "x-api-version": API_VERSION,
        }
        if self.store_id:
            merged["x-vercel-blob-store-id"] = self.store_id
        for key, value in (headers or {}).items():
            merged[key] = value
        return merged

    def _request(self, method, url, data=None, headers=None):
        request = urllib.request.Request(url, data=data, method=method)
        for key, value in self._auth_headers(headers).items():
            request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            body = error.read()[:300].decode("utf-8", "replace")
            raise BlobError("%s %s -> HTTP %s %s" % (method, url, error.code, body))
        except urllib.error.URLError as error:
            raise BlobError("%s %s -> %s" % (method, url, error.reason))

    def _public_url(self, name):
        if not self.store_id:
            return ""
        return "https://%s.%s.blob.vercel-storage.com/%s" % (
            self.store_id,
            self.access,
            urllib.parse.quote(name.lstrip("/")),
        )

    def _list(self, prefix="", limit=1000):
        query = {"limit": str(limit)}
        if prefix:
            query["prefix"] = prefix
        url = "%s?%s" % (self.api, urllib.parse.urlencode(query))
        body = self._request("GET", url)
        try:
            payload = json.loads(body.decode("utf-8"))
        except ValueError:
            return []
        return payload.get("blobs") or []

    def _url_from_listing(self, name):
        """Where the store says this blob actually lives (authoritative)."""
        try:
            for item in self._list(prefix=name):
                if item.get("pathname") == name and item.get("url"):
                    return item["url"]
        except BlobError:
            return ""
        return ""

    def _candidates(self, name):
        urls = []
        cached = self._urls.get(name)
        if cached:
            urls.append(cached)
        constructed = self._public_url(name)
        if constructed and constructed not in urls:
            urls.append(constructed)
        return urls

    # ---------- FileBackend interface ----------
    def get(self, name):
        name = name.lstrip("/")
        tried = set()
        pending = list(self._candidates(name))
        while pending:
            url = pending.pop(0)
            if url in tried:
                continue
            tried.add(url)
            try:
                body = self._request("GET", url)
            except BlobError as error:
                text = str(error)
                # A predictable URL can be wrong (older store ids, private access); the
                # listing below is the fallback rather than an error.
                if "HTTP 404" in text or "HTTP 403" in text:
                    continue
                raise
            self._urls[name] = url
            try:
                return json.loads(body.decode("utf-8"))
            except ValueError:
                return None
        resolved = self._url_from_listing(name)
        if not resolved or resolved in tried:
            return None
        self._urls[name] = resolved
        try:
            body = self._request("GET", resolved)
        except BlobError as error:
            if "HTTP 404" in str(error):
                return None
            raise
        try:
            return json.loads(body.decode("utf-8"))
        except ValueError:
            return None

    def put(self, name, payload):
        name = name.lstrip("/")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        url = "%s/?%s" % (self.api, urllib.parse.urlencode({"pathname": name}))
        raw = self._request("PUT", url, data=body, headers={
            "x-vercel-blob-access": self.access,
            "x-content-type": "application/json",
            "x-add-random-suffix": "0",
            "x-allow-overwrite": "1",
            "x-cache-control-max-age": "60",
            "content-type": "application/json",
        })
        try:
            created = json.loads(raw.decode("utf-8"))
        except ValueError:
            created = {}
        if created.get("url"):
            self._urls[name] = created["url"]
        return True

    def names(self, prefix=""):
        try:
            blobs = self._list(prefix=prefix)
        except BlobError:
            return []
        pathnames = []
        for item in blobs:
            name = item.get("pathname") or ""
            if name:
                pathnames.append(name)
        return sorted(pathnames, reverse=True)

    # ---------- diagnostics ----------
    def selftest(self):
        """Write, read back and list one probe key, so a misconfigured store reports
        exactly which call failed instead of silently serving nothing."""
        name = "_diagnostics/probe.json"
        report = {"storage": self.label, "access": self.access,
                  "store_id": self.store_id or "(not resolved)", "write": None,
                  "read": None, "list": None, "error": None}
        marker = {"probe": "zvd-radar", "api_version": API_VERSION}
        try:
            self.put(name, marker)
            report["write"] = "ok"
        except BlobError as error:
            report["error"] = "write: %s" % error
            return report
        try:
            read_back = self.get(name)
            report["read"] = "ok" if read_back == marker else "mismatch: %r" % (read_back,)
        except BlobError as error:
            report["error"] = "read: %s" % error
        try:
            names = self.names(prefix="_diagnostics/")
            report["list"] = "ok (%d)" % len(names) if name in names else "missing probe in listing"
        except BlobError as error:
            report["error"] = report["error"] or "list: %s" % error
        return report


def available():
    return bool(os.environ.get(TOKEN_ENV))
