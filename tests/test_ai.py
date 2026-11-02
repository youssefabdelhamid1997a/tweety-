import io
import json
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from coach.ai import MODEL, coach_reply
from coach.analysis import InputError
from coach.client import APIError
from coach.demo import demo_report


class AITests(unittest.TestCase):
    def test_local_chat_has_bounded_evidence_and_sample_label(self):
        captured = []
        class Opener:
            def open(self, request, **kwargs):
                captured.append(request)
                return io.BytesIO(b'{"message":{"content":"These are sample matches. Practice last hits."}}')
        with patch("coach.ai.build_opener", return_value=Opener()):
            result = coach_reply(demo_report(), "What should I practice?")
        self.assertEqual(result["model"], MODEL)
        self.assertEqual(result["source"], "demo")
        self.assertEqual(captured[0].full_url, "http://127.0.0.1:11434/api/chat")
        body = json.loads(captured[0].data)
        self.assertFalse(body["stream"])
        self.assertIn('"source": "demo"', body["messages"][1]["content"])
        self.assertNotIn("Sample player", body["messages"][1]["content"])
        self.assertIn("do not invent", body["messages"][0]["content"])

    def test_missing_ai_has_clear_installation_error(self):
        for failure in (URLError("offline"), HTTPError("url", 404, "missing", {}, None)):
            with patch("coach.ai.build_opener") as factory:
                factory.return_value.open.side_effect = failure
                with self.assertRaises(APIError) as caught:
                    coach_reply(demo_report(), "How can I improve?")
                self.assertEqual(caught.exception.status, 503)
                self.assertIn("ollama pull", str(caught.exception))

    def test_reject_invalid_chat_input(self):
        for report, question in [(None, "Hi"), ({}, "Hi"), (demo_report(), ""), (demo_report(), "x" * 1001)]:
            with self.assertRaises(InputError):
                coach_reply(report, question)

    def test_unreadable_or_empty_model_response(self):
        for response in (b"garbage", b'{"message":{"content":""}}'):
            with patch("coach.ai.build_opener") as factory:
                factory.return_value.open.return_value = io.BytesIO(response)
                with self.assertRaises(APIError):
                    coach_reply(demo_report(), "What next?")


if __name__ == "__main__":
    unittest.main()
