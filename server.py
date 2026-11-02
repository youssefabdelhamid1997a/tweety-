"""Run with Python 3.10+; no third-party packages required."""

import argparse
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from coach.analysis import InputError, match_id, role_value
from coach.ai import coach_reply
from coach.client import APIError, OpenDota
from coach.demo import demo_report
from coach.service import CoachService

ROOT = Path(__file__).resolve().parent
MAX_BODY = 10_000_000


def make_handler(service):
    busy = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        server_version = "DotaAscent/1.0"

        def log_message(self, format, *args):
            # Do not log account input, imported data, or upstream response bodies.
            pass

        def safe_host(self):
            port = self.server.server_port
            return self.headers.get("Host") in {f"127.0.0.1:{port}", f"localhost:{port}"}

        def send(self, body, status=200, content_type="application/json; charset=utf-8"):
            if not isinstance(body, bytes):
                body = json.dumps(body, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            if not self.safe_host():
                return self.send({"error": "This is a local-only application. Use localhost or 127.0.0.1."}, 403)
            url = urlparse(self.path)
            files = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "application/javascript"), "/style.css": ("style.css", "text/css")}
            if url.path in files:
                name, mime = files[url.path]
                return self.send((ROOT / "static" / name).read_bytes(), content_type=mime + "; charset=utf-8")
            if url.path == "/api/health":
                return self.send({"status": "ok", "version": "1.0.0"})
            if url.path == "/api/demo":
                try:
                    role = role_value(parse_qs(url.query).get("role", ["carry"])[0])
                    return self.send(demo_report(role))
                except InputError as exc:
                    return self.send({"error": str(exc)}, 400)
            return self.send({"error": "Not found"}, 404)

        def do_POST(self):
            if not self.safe_host():
                return self.send({"error": "Invalid local host."}, 403)
            origin = self.headers.get("Origin")
            if origin and origin not in {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}:
                return self.send({"error": "Cross-origin requests are not allowed."}, 403)
            if self.headers.get_content_type() != "application/json":
                return self.send({"error": "Send application/json."}, 415)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAX_BODY:
                    return self.send({"error": "Request must be between 1 byte and 10 MB."}, 413)
                data = json.loads(self.rfile.read(length), parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
                if not isinstance(data, dict):
                    raise ValueError()
            except (ValueError, UnicodeDecodeError):
                return self.send({"error": "The request is not a valid JSON object."}, 400)
            if not busy.acquire(blocking=False):
                return self.send({"error": "Another analysis is running. Please wait for it to finish."}, 429)
            try:
                path = urlparse(self.path).path
                if path == "/api/analyze":
                    return self.send(service.analyze(data))
                if path == "/api/match":
                    return self.send(service.review(data))
                if path == "/api/import":
                    return self.send(service.review(data, imported=data.get("match", {})))
                if path == "/api/ask":
                    return self.send(coach_reply(data.get("report"), data.get("question")))
                if path == "/api/parse":
                    result = service.client.parse(match_id(data.get("match_id")))
                    job = result.get("job", {}).get("jobId") if isinstance(result, dict) and isinstance(result.get("job"), dict) else None
                    return self.send({"message": "OpenDota accepted the parse request. Wait several minutes, then use Refresh match. Old or unavailable replays may never become parseable.", "job_id": job})
                return self.send({"error": "Not found"}, 404)
            except InputError as exc:
                return self.send({"error": str(exc)}, 400)
            except APIError as exc:
                return self.send({"error": str(exc)}, exc.status)
            except Exception:
                # Never expose local paths, traces, or potentially personal upstream data in HTTP responses.
                return self.send({"error": "An unexpected error occurred. Restart the app and retry. Your files have not been changed."}, 500)
            finally:
                busy.release()

    return Handler


def create_server(port=8765, cache_dir=None, client=None):
    client = client or OpenDota(cache_dir or ROOT / ".local")
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(CoachService(client)))


def main():
    parser = argparse.ArgumentParser(description="Dota Ascent — your local, evidence-based Dota 2 coach")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="Open your default browser")
    args = parser.parse_args()
    try:
        server = create_server(args.port)
    except OSError:
        print("Could not start. Close any other copy of the coach or try: python server.py --port 8766 --open")
        return 1
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"Dota Ascent is running at {url}\nKeep this window open. Press Ctrl+C to stop.\nNo Steam password or paid API key is needed.", flush=True)
    if args.open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCoach stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
