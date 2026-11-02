"""OpenDota's public HTTPS API, with local caching and conservative rate limits."""

import json
import hashlib
import socket
import sqlite3
import ssl
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from .config import load_api_key, validate_api_key


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def urlopen(request, timeout, context):
    """Keep TLS verification and never forward an API key through a redirect."""
    return build_opener(HTTPSHandler(context=context), _NoRedirect()).open(request, timeout=timeout)


class APIError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


class OpenDota:
    BASE = "https://api.opendota.com/api"

    def __init__(self, cache_dir, api_key=None):
        self._api_key = load_api_key(cache_dir) if api_key is None else validate_api_key(api_key)
        self._cache_scope = "key:" + hashlib.sha256(self._api_key.encode()).hexdigest() if self._api_key else "public"
        self.path = Path(cache_dir) / "opendota.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, saved REAL, body TEXT)")
        self.lock = threading.Lock()
        self.last_call = 0
        self.context = ssl.create_default_context()

    @property
    def has_api_key(self):
        return bool(self._api_key)

    def _cache_key(self, resource):
        return self._cache_scope + ":" + resource

    def request(self, path, params=None, ttl=300, method="GET"):
        query = urlencode(params or [], doseq=True)
        resource = path + ("?" + query if query else "")
        key = self._cache_key(resource)
        if method == "GET":
            with sqlite3.connect(self.path) as db:
                entry = db.execute("SELECT saved, body FROM cache WHERE key = ?", (key,)).fetchone()
            if entry and time.time() - entry[0] < ttl:
                return json.loads(entry[1])
        with self.lock:
            time.sleep(max(0, 1.1 - (time.monotonic() - self.last_call)))
            self.last_call = time.monotonic()
            headers = {"Accept": "application/json", "User-Agent": "DotaAscentCoach/1.0.2 (local personal coach)"}
            if self._api_key:
                headers["Authorization"] = "Bearer " + self._api_key
            request = Request(self.BASE + resource, method=method, data=b"" if method == "POST" else None, headers=headers)
            try:
                with urlopen(request, timeout=12, context=self.context) as response:
                    body = response.read(12_000_001)
                    if len(body) > 12_000_000:
                        raise APIError("OpenDota returned an unexpectedly large response. Try a different match.")
                    result = json.loads(body)
            except HTTPError as exc:
                if exc.code == 429:
                    raise APIError("OpenDota's rate limit was reached. Wait a minute and try again. Cached results need no additional calls.", 429) from exc
                if exc.code == 404:
                    raise APIError("OpenDota could not find this player or match. Check the ID and public match-data setting.", 404) from exc
                if exc.code == 401 and self.has_api_key:
                    raise APIError("OpenDota rejected the configured API key. Run set-api-key.bat with an active replacement key, then restart the coach.", 502) from exc
                if exc.code == 403 and self.has_api_key:
                    raise APIError("OpenDota denied the request. Check that your API key and plan are active, and that your network permits api.opendota.com.", 502) from exc
                if exc.code in (401, 403):
                    raise APIError("Access to OpenDota was denied. Check your connection or allow api.opendota.com in the cloud environment's network settings.", 502) from exc
                if 300 <= exc.code < 400:
                    raise APIError("OpenDota returned an unexpected redirect. The coach did not forward your API key. Please try again later.") from exc
                raise APIError(f"OpenDota is unavailable (HTTP {exc.code}). Please try again later.") from exc
            except (URLError, TimeoutError, socket.timeout, OSError) as exc:
                raise APIError("Could not reach OpenDota securely. Check your Internet connection and access to api.opendota.com. No sample data has been substituted.") from exc
            except (ValueError, UnicodeDecodeError) as exc:
                raise APIError("OpenDota returned an unreadable response. Please try again later.") from exc
        if method == "GET":
            with sqlite3.connect(self.path) as db:
                db.execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?)", (key, time.time(), json.dumps(result)))
        return result

    def profile(self, account, refresh=False):
        return self.request(f"/players/{account}", ttl=0 if refresh else 300)

    def matches(self, account, limit, refresh=False):
        fields = ["hero_id", "start_time", "duration", "game_mode", "lobby_type", "version", "kills", "deaths", "assists",
                  "leaver_status", "gold_per_min", "xp_per_min", "last_hits", "tower_damage", "lane_role", "is_roaming"]
        return self.request(f"/players/{account}/matches", [("lobby_type", 7), ("limit", limit), ("project", fields)], ttl=0 if refresh else 300)

    def recent_matches(self, account, refresh=False):
        return self.request(f"/players/{account}/recentMatches", ttl=0 if refresh else 300)

    def match(self, match):
        return self.request(f"/matches/{match}", ttl=86400)

    def parse(self, match):
        # Only called after an explicit user click; there is no automatic parse submission.
        result = self.request(f"/request/{match}", method="POST")
        if not isinstance(result, dict) or not isinstance(result.get("job"), dict) or not result["job"].get("jobId"):
            raise APIError("OpenDota did not confirm a replay-parse job. Please try again later; no parsing success has been assumed.")
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM cache WHERE key = ?", (self._cache_key(f"/matches/{match}"),))
        return result

    def refresh_match(self, match):
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM cache WHERE key = ?", (self._cache_key(f"/matches/{match}"),))
        return self.match(match)
