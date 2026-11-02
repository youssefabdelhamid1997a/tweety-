"""Local HTTP routing and concurrency for screenshot coaching, with fake inference."""

import json
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from server import create_server
from tests.test_coach import FixtureClient
from tests.test_vision import JPEG


class LiveHTTPTests(unittest.TestCase):
    def setUp(self):
        self.server = create_server(0, client=FixtureClient())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def call(self, path, data=None, headers=None):
        request = Request(self.base + path, data=json.dumps(data).encode() if data is not None else None,
                          headers=headers or ({"Content-Type": "application/json"} if data is not None else {}))
        return urlopen(request, timeout=8)

    def test_live_route_works_without_match_history_or_api_key(self):
        payload = {"image": JPEG, "hero": "Tusk", "role": "support", "captured_at": time.time()}
        response = {"model": "test-model", "screen_status": "unclear", "observation": "Synthetic test.", "advice": "Check the game window.", "uncertainty": "Test only.", "captured_at": payload["captured_at"], "processed_at": time.time(), "latency_seconds": 0}
        with patch("server.vision_reply", return_value=response) as model:
            with self.call("/api/live/analyze", payload) as result:
                raw = result.read()
        model.assert_called_once_with(payload)
        self.assertEqual(json.loads(raw)["screen_status"], "unclear")
        self.assertNotIn(JPEG.encode(), raw)

    def test_cross_origin_and_invalid_frames_are_rejected(self):
        payload = {"image": JPEG, "captured_at": time.time()}
        with patch("server.vision_reply") as model:
            with self.assertRaises(HTTPError) as caught:
                self.call("/api/live/analyze", payload, {"Content-Type": "application/json", "Origin": "https://external.invalid"})
        self.assertEqual(caught.exception.code, 403)
        model.assert_not_called()
        with patch("coach.vision.build_opener") as local_model:
            with self.assertRaises(HTTPError) as caught:
                self.call("/api/live/analyze", {"image": "not-an-image", "captured_at": time.time()})
        self.assertEqual(caught.exception.code, 400)
        local_model.assert_not_called()

    def test_model_requests_do_not_overlap_or_block_match_history(self):
        entered, release = threading.Event(), threading.Event()
        outcomes = []
        def infer(data):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("Test failed to release inference")
            return {"screen_status": "unclear", "model": "test-model"}
        def first_request():
            try:
                with self.call("/api/live/analyze", {"image": JPEG, "captured_at": time.time()}) as result:
                    outcomes.append(result.status)
            except Exception as error:
                outcomes.append(type(error).__name__)
        with patch("server.vision_reply", side_effect=infer):
            first = threading.Thread(target=first_request)
            first.start()
            try:
                self.assertTrue(entered.wait(3))
                for path, body in [("/api/live/analyze", {"image": JPEG}), ("/api/ask", {"report": {}, "question": "Hi"})]:
                    with self.assertRaises(HTTPError) as caught:
                        self.call(path, body)
                    self.assertEqual(caught.exception.code, 429)
                with self.call("/api/analyze", {"account": "314758455", "limit": 10}) as result:
                    self.assertEqual(json.load(result)["summary"]["matches"], 6)
                with self.call("/api/health") as result:
                    self.assertEqual(json.load(result)["status"], "ok")
            finally:
                release.set(); first.join(timeout=5)
        self.assertEqual(outcomes, [200])

    def test_local_sharing_policy_disallows_camera_and_microphone(self):
        with self.call("/") as result:
            self.assertIn("media-src 'self' blob:", result.headers["Content-Security-Policy"])
            self.assertIn("camera=()", result.headers["Permissions-Policy"])
            self.assertIn("microphone=()", result.headers["Permissions-Policy"])
