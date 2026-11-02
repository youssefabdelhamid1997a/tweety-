"""Behavior checks for safe, repeatable desktop startup."""

import errno
import io
import json
import sqlite3
import threading
import unittest
from contextlib import contextmanager, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock, patch

from coach.startup import APP_ID, FALLBACK_PORTS, bind_server, is_coach_running
from server import create_server, main
from tests.test_coach import FixtureClient


@contextmanager
def endpoint(body, status=200, location=None):
    """A genuine unrelated local service, with configurable health output."""
    payload = body if isinstance(body, bytes) else json.dumps(body).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            if location:
                self.send_header("Location", location)
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@contextmanager
def running_coach():
    server = create_server(0, client=FixtureClient())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class ExistingInstanceTests(unittest.TestCase):
    def test_genuine_coach_is_recognized(self):
        with running_coach() as port:
            self.assertTrue(is_coach_running(port))

    def test_unrelated_healthy_service_is_not_reused(self):
        with endpoint({"status": "ok"}) as port:
            self.assertFalse(is_coach_running(port))

    def test_wrong_application_or_unhealthy_coach_is_not_reused(self):
        for body in ({"app": "other-app", "status": "ok"}, {"app": APP_ID, "status": "error"}):
            with self.subTest(body=body), endpoint(body) as port:
                self.assertFalse(is_coach_running(port))

    def test_invalid_or_oversized_health_response_is_not_reused(self):
        for body in (b"not json", {"app": APP_ID, "status": "ok", "extra": "x" * 5000}):
            with self.subTest(body_type=type(body).__name__), endpoint(body) as port:
                self.assertFalse(is_coach_running(port))

    def test_redirect_to_a_genuine_coach_is_not_followed(self):
        with running_coach() as genuine:
            with endpoint(b"", status=302, location=f"http://127.0.0.1:{genuine}/api/health") as redirect:
                self.assertFalse(is_coach_running(redirect))


class BindingTests(unittest.TestCase):
    def test_occupied_default_can_fall_back_to_another_loopback_port(self):
        occupied = create_server(0, client=FixtureClient())
        replacement = None
        try:
            port = occupied.server_port
            replacement = bind_server(lambda candidate: create_server(candidate, client=FixtureClient()), port, allow_fallback=True)
            self.assertEqual(replacement.server_address[0], "127.0.0.1")
            self.assertGreater(replacement.server_port, port)
            self.assertLessEqual(replacement.server_port, port + FALLBACK_PORTS)
        finally:
            if replacement:
                replacement.server_close()
            occupied.server_close()

    def test_explicit_occupied_port_does_not_fall_back(self):
        occupied = create_server(0, client=FixtureClient())
        try:
            with self.assertRaises(OSError) as caught:
                bind_server(lambda candidate: create_server(candidate, client=FixtureClient()), occupied.server_port)
            self.assertIn(caught.exception.errno, (errno.EADDRINUSE, 10048))
        finally:
            occupied.server_close()

    def test_fallback_stops_after_bounded_collisions(self):
        failure = OSError(errno.EADDRINUSE, "address occupied")
        factory = Mock(side_effect=failure)
        with self.assertRaises(OSError) as caught:
            bind_server(factory, 8765, allow_fallback=True)
        self.assertIs(caught.exception, failure)
        self.assertEqual(factory.call_count, FALLBACK_PORTS + 1)

    def test_permission_and_cache_failures_are_not_retried_as_port_conflicts(self):
        for failure in (PermissionError(errno.EACCES, "permission denied"), sqlite3.OperationalError("cache is read-only")):
            factory = Mock(side_effect=failure)
            with self.subTest(error=type(failure).__name__), self.assertRaises(type(failure)) as caught:
                bind_server(factory, 8765, allow_fallback=True)
            self.assertIs(caught.exception, failure)
            self.assertEqual(factory.call_count, 1)

    def test_windows_address_in_use_error_can_fall_back(self):
        bound = object()
        factory = Mock(side_effect=[OSError(10048, "address already in use"), bound])
        self.assertIs(bind_server(factory, 8765, allow_fallback=True), bound)
        self.assertEqual(factory.call_args.args, (8766,))

    def test_ephemeral_port_is_not_incremented(self):
        failure = OSError(errno.EADDRINUSE, "address occupied")
        factory = Mock(side_effect=failure)
        with self.assertRaises(OSError):
            bind_server(factory, 0, allow_fallback=True)
        self.assertEqual(factory.call_count, 1)


class LauncherTests(unittest.TestCase):
    def test_default_relaunch_finds_coach_on_a_fallback_port(self):
        with patch("sys.argv", ["server.py", "--open"]), \
                patch("server.is_coach_running", side_effect=lambda port: port == 8766), \
                patch("server.create_server", side_effect=AssertionError("must reuse the existing fallback instance")), \
                patch("server.webbrowser.open") as browser, redirect_stdout(io.StringIO()):
            self.assertEqual(main(), 0)
            browser.assert_called_once_with("http://127.0.0.1:8766")

    def test_open_reuses_genuine_running_coach_without_binding(self):
        with running_coach() as port:
            with patch("sys.argv", ["server.py", "--port", str(port), "--open"]), \
                    patch("server.create_server", side_effect=AssertionError("must not bind a second server")), \
                    patch("server.webbrowser.open") as browser, redirect_stdout(io.StringIO()):
                self.assertEqual(main(), 0)
                browser.assert_called_once_with(f"http://127.0.0.1:{port}")

    def test_explicit_port_occupied_by_unrelated_service_reports_failure(self):
        with endpoint({"status": "ok", "app": "another-app"}) as port:
            with patch("sys.argv", ["server.py", "--port", str(port), "--open"]), \
                    patch("server.create_server", side_effect=lambda requested: create_server(requested, client=FixtureClient())), \
                    patch("server.webbrowser.open") as browser, redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(), 1)
                self.assertIn("occupied", output.getvalue())
                browser.assert_not_called()


if __name__ == "__main__":
    unittest.main()
