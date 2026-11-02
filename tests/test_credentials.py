"""Credential transport checks use deliberately fictitious API keys only."""

import io
import json
import sqlite3
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request
from unittest.mock import patch

from coach.client import APIError, OpenDota, urlopen
from coach.config import ConfigError
from server import create_server, main


class CredentialTransportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.sleep = patch("coach.client.time.sleep")
        self.sleep.start()
        self.addCleanup(self.sleep.stop)
        self.key = "fictitious-test-key-not-an-actual-credential"

    def test_key_goes_in_header_not_url_or_cache(self):
        client = OpenDota(self.directory.name, api_key=self.key)
        seen = []
        def respond(request, **kwargs):
            seen.append(request)
            self.assertEqual(request.get_header("Authorization"), "Bearer " + self.key)
            self.assertNotIn(self.key, request.full_url)
            self.assertNotIn("api_key=", request.full_url)
            self.assertTrue(kwargs["context"].check_hostname)
            return io.BytesIO(b'{"profile":{}}')
        with patch("coach.client.urlopen", side_effect=respond):
            client.profile(314758455)
        with sqlite3.connect(client.path) as db:
            serialized = json.dumps(db.execute("SELECT * FROM cache").fetchall())
        self.assertNotIn(self.key, serialized)
        self.assertTrue(client.has_api_key)

    def test_public_access_has_no_authorization_header(self):
        with patch("coach.client.load_api_key", return_value=None):
            client = OpenDota(self.directory.name)
        def respond(request, **kwargs):
            self.assertIsNone(request.get_header("Authorization"))
            return io.BytesIO(b'[]')
        with patch("coach.client.urlopen", side_effect=respond):
            client.matches(314758455, 10)
        self.assertFalse(client.has_api_key)

    def test_different_keys_and_public_mode_do_not_share_cache(self):
        one = OpenDota(self.directory.name, api_key=self.key)
        two = OpenDota(self.directory.name, api_key="another-fictitious-test-key")
        with patch("coach.client.load_api_key", return_value=None):
            public = OpenDota(self.directory.name)
        with patch("coach.client.urlopen", side_effect=[io.BytesIO(b'{"marker":1}'), io.BytesIO(b'{"marker":2}'), io.BytesIO(b'{"marker":3}')]) as remote:
            self.assertEqual(one.profile(123)["marker"], 1)
            self.assertEqual(two.profile(123)["marker"], 2)
            self.assertEqual(public.profile(123)["marker"], 3)
            self.assertEqual(one.profile(123)["marker"], 1)
        self.assertEqual(remote.call_count, 3)

    def test_rejected_key_error_never_echoes_key(self):
        client = OpenDota(self.directory.name, api_key=self.key)
        failure = HTTPError("https://example.invalid/" + self.key, 401, self.key, {}, None)
        with patch("coach.client.urlopen", side_effect=failure), self.assertRaises(APIError) as caught:
            client.profile(123)
        self.assertNotIn(self.key, str(caught.exception))
        self.assertIn("set-api-key.bat", str(caught.exception))

    def test_api_key_is_used_for_explicit_parse_request(self):
        client = OpenDota(self.directory.name, api_key=self.key)
        def respond(request, **kwargs):
            self.assertEqual(request.get_method(), "POST")
            self.assertEqual(request.get_header("Authorization"), "Bearer " + self.key)
            return io.BytesIO(b'{"job":{"jobId":123}}')
        with patch("coach.client.urlopen", side_effect=respond):
            self.assertEqual(client.parse(123)["job"]["jobId"], 123)

    def test_real_redirect_does_not_receive_key(self):
        target_calls = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "/target")
                    self.end_headers()
                else:
                    target_calls.append(self.headers.get("Authorization"))
                    self.send_response(200)
                    self.end_headers()
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = Request(f"http://127.0.0.1:{server.server_port}/redirect", headers={"Authorization": "Bearer " + self.key})
            with self.assertRaises(HTTPError) as caught:
                urlopen(request, timeout=2, context=None)
            self.assertEqual(caught.exception.code, 302)
            self.assertEqual(target_calls, [])
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_invalid_local_configuration_has_actionable_startup_error(self):
        from contextlib import redirect_stdout
        with patch("sys.argv", ["server.py"]), patch("server.create_server", side_effect=ConfigError("Invalid local configuration")), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(), 1)
        self.assertIn("set-api-key.bat", output.getvalue())


class KeyHealthTests(unittest.TestCase):
    def test_health_only_exposes_presence(self):
        from urllib.request import urlopen as fetch
        with tempfile.TemporaryDirectory() as directory:
            client = OpenDota(directory, api_key="fictitious-health-test-key")
            server = create_server(0, client=client)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with fetch(f"http://127.0.0.1:{server.server_port}/api/health") as response:
                    raw = response.read()
                health = json.loads(raw)
                self.assertTrue(health["opendota_key_configured"])
                self.assertNotIn(b"fictitious-health-test-key", raw)
                self.assertEqual(set(health), {"app", "status", "version", "opendota_key_configured"})
            finally:
                server.shutdown(); server.server_close(); thread.join()
