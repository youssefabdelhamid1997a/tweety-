"""Small, loopback-only startup checks for the desktop launcher."""

import errno
import json
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

APP_ID = "dota-ascent"
APP_VERSION = "1.1.0"
DEFAULT_PORT = 8765
FALLBACK_PORTS = 10


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def is_coach_running(port):
    """Recognize this app without following a redirect or using an egress proxy."""
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
            body = response.read(4097)
            if len(body) > 4096:
                return False
            result = json.loads(body)
            return isinstance(result, dict) and result.get("app") == APP_ID and result.get("status") == "ok" and result.get("version") == APP_VERSION
    except (HTTPError, URLError, OSError, ValueError):
        return False


def is_address_in_use(error):
    return error.errno in (errno.EADDRINUSE, 10048) or getattr(error, "winerror", None) == 10048


def bind_server(factory, port, allow_fallback=False):
    """Bind the requested port; only retry genuine address collisions.

    ``factory`` takes a port and returns a bound server. Permission, cache, and
    other startup errors propagate immediately. Fallback is intentionally bounded.
    """
    last_port = min(port + FALLBACK_PORTS, 65535) if allow_fallback and port else port
    for candidate in range(port, last_port + 1):
        try:
            return factory(candidate)
        except OSError as error:
            if not is_address_in_use(error) or candidate == last_port:
                raise
