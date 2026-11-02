"""OpenDota's public HTTPS API, with local caching and conservative rate limits."""

import json
import socket
import sqlite3
import ssl
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class APIError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


class OpenDota:
    BASE = "https://api.opendota.com/api"

    def __init__(self, cache_dir):
        self.path = Path(cache_dir) / "opendota.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, saved REAL, body TEXT)")
        self.lock = threading.Lock()
        self.last_call = 0
        self.context = ssl.create_default_context()

    def request(self, path, params=None, ttl=300, method="GET"):
        query = urlencode(params or [], doseq=True)
        key = path + ("?" + query if query else "")
        if method == "GET":
            with sqlite3.connect(self.path) as db:
                entry = db.execute("SELECT saved, body FROM cache WHERE key = ?", (key,)).fetchone()
            if entry and time.time() - entry[0] < ttl:
                return json.loads(entry[1])
        with self.lock:
            time.sleep(max(0, 1.1 - (time.monotonic() - self.last_call)))
            self.last_call = time.monotonic()
            request = Request(self.BASE + key, method=method, data=b"" if method == "POST" else None,
                              headers={"Accept": "application/json", "User-Agent": "DotaAscentCoach/1.0 (local personal coach)"})
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
                if exc.code in (401, 403):
                    raise APIError("Access to OpenDota was denied. Check your connection or allow api.opendota.com in the cloud environment's network settings.", 502) from exc
                raise APIError(f"OpenDota is unavailable (HTTP {exc.code}). Please try again later.") from exc
            except (URLError, TimeoutError, socket.timeout, OSError) as exc:
                raise APIError("Could not reach OpenDota securely. Check your Internet connection and access to api.opendota.com. No sample data has been substituted.") from exc
            except (ValueError, UnicodeDecodeError) as exc:
                raise APIError("OpenDota returned an unreadable response. Please try again later.") from exc
        if method == "GET":
            with sqlite3.connect(self.path) as db:
                db.execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?)", (key, time.time(), json.dumps(result)))
        return result

    def profile(self, account):
        return self.request(f"/players/{account}")

    def matches(self, account, limit):
        fields = ["hero_id", "start_time", "duration", "game_mode", "lobby_type", "version", "kills", "deaths", "assists",
                  "leaver_status", "gold_per_min", "xp_per_min", "last_hits", "tower_damage", "lane_role", "is_roaming"]
        return self.request(f"/players/{account}/matches", [("lobby_type", 7), ("limit", limit), ("project", fields)])

    def match(self, match):
        return self.request(f"/matches/{match}", ttl=86400)

    def parse(self, match):
        # Only called after an explicit user click; there is no automatic parse submission.
        result = self.request(f"/request/{match}", method="POST")
        if not isinstance(result, dict) or not isinstance(result.get("job"), dict) or not result["job"].get("jobId"):
            raise APIError("OpenDota did not confirm a replay-parse job. Please try again later; no parsing success has been assumed.")
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM cache WHERE key = ?", (f"/matches/{match}",))
        return result

    def refresh_match(self, match):
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM cache WHERE key = ?", (f"/matches/{match}",))
        return self.match(match)
