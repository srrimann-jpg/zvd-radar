"""Tiny HTTP helpers. Stdlib only, with a browser user agent so public feeds respond."""

import gzip
import time
import urllib.error
import urllib.request

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)


def fetch_text(url, timeout=12, retries=1, headers=None):
    """Fetch a URL as text. Raises on total failure so callers can record the source error."""
    last_error = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url)
            request.add_header("User-Agent", UA)
            request.add_header("Accept", "*/*")
            request.add_header("Accept-Language", "en-US,en;q=0.9")
            for key, value in (headers or {}).items():
                request.add_header(key, value)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
            return raw.decode("utf-8", "replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as error:
            last_error = error
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
    raise last_error
