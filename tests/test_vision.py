"""Live-vision contracts use a tiny synthetic JPEG and controlled Ollama replies.

No screen is captured, model installed, API key read, or external call made.
"""

import base64
import io
import json
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from coach.analysis import InputError
from coach.client import APIError
from coach.vision import VISION_MODEL, vision_reply


# A real 2x2 JPEG generated once from a solid synthetic color. Pillow is not a
# runtime or test dependency; valid JPEG syntax is kept here for transport checks.
JPEG = (
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/"
    "2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAACAAIDASIAAhEBAxEB/"
    "8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAk"
    "M2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKz"
    "tLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREA"
    "AgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldY"
    "WVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09"
    "fb3+Pn6/9oADAMBAAIRAxEAPwDzeiiivWPPP//Z"
)
NOW = 1000.0
GOOD_REPLY = {
    "screen_status": "game_visible",
    "observation": "Your hero is visible beside an allied creep wave.",
    "advice": "Check the minimap before moving beyond the wave.",
    "uncertainty": "One frame cannot show where missing enemy heroes are.",
}


def payload(**overrides):
    result = {"image": JPEG, "captured_at": NOW, "hero": "Juggernaut", "role": "carry"}
    result.update(overrides)
    return result


def response_body(content=GOOD_REPLY):
    return json.dumps({"message": {"content": json.dumps(content)}}).encode()


def with_dimensions(width, height):
    image = bytearray(base64.b64decode(JPEG))
    marker = image.index(b"\xff\xc0")
    image[marker + 5:marker + 7] = height.to_bytes(2, "big")
    image[marker + 7:marker + 9] = width.to_bytes(2, "big")
    return base64.b64encode(image).decode()


class VisionInputTests(unittest.TestCase):
    def test_rejects_missing_or_non_object_payload(self):
        for value in (None, [], "text", {}, {"captured_at": NOW}, {"image": JPEG}):
            with self.subTest(kind=type(value).__name__), patch("coach.vision.time.time", return_value=NOW), patch("coach.vision.build_opener") as network:
                with self.assertRaises(InputError):
                    vision_reply(value)
                network.assert_not_called()

    def test_rejects_stale_future_and_non_finite_timestamps(self):
        for stamp in (NOW - 16, NOW + 6, None, True, "1000", float("nan"), float("inf")):
            with self.subTest(timestamp=stamp), patch("coach.vision.time.time", return_value=NOW), patch("coach.vision.build_opener") as network:
                with self.assertRaises(InputError):
                    vision_reply(payload(captured_at=stamp))
                network.assert_not_called()

    def test_rejects_invalid_base64_and_non_jpeg_data(self):
        candidates = ("", "not base64!", "data:image/jpeg;base64," + JPEG, JPEG + "\n", base64.b64encode(b"not an image").decode(),
                      base64.b64encode(b"\xff\xd8header only\xff\xd9").decode(), base64.b64encode(base64.b64decode(JPEG)[:-2]).decode())
        for image in candidates:
            with self.subTest(prefix=image[:20]), patch("coach.vision.time.time", return_value=NOW), patch("coach.vision.build_opener") as network:
                with self.assertRaises(InputError):
                    vision_reply(payload(image=image))
                network.assert_not_called()

    def test_rejects_oversized_image_bytes(self):
        image = base64.b64encode(b"\xff\xd8" + b"x" * 2_000_001 + b"\xff\xd9").decode()
        with patch("coach.vision.time.time", return_value=NOW), patch("coach.vision.build_opener") as network:
            with self.assertRaises(InputError):
                vision_reply(payload(image=image))
            network.assert_not_called()

    def test_rejects_excessive_dimensions_and_pixel_count(self):
        for width, height in ((3000, 2), (2048, 2048)):
            with self.subTest(size=(width, height)), patch("coach.vision.time.time", return_value=NOW), patch("coach.vision.build_opener") as network:
                with self.assertRaises(InputError):
                    vision_reply(payload(image=with_dimensions(width, height)))
                network.assert_not_called()

    def test_minimap_uses_its_own_size_limits(self):
        for minimap in (with_dimensions(801, 2), base64.b64encode(b"\xff\xd8" + b"x" * 700_001 + b"\xff\xd9").decode(), 123):
            with self.subTest(kind=type(minimap).__name__), patch("coach.vision.time.time", return_value=NOW), patch("coach.vision.build_opener") as network:
                with self.assertRaises(InputError):
                    vision_reply(payload(minimap=minimap))
                network.assert_not_called()

    def test_rejects_invalid_hero_and_role(self):
        for fields in ({"hero": "x" * 81}, {"hero": []}, {"role": "invisible-enemies"}, {"role": []}):
            with self.subTest(fields=fields), patch("coach.vision.time.time", return_value=NOW), patch("coach.vision.build_opener") as network:
                with self.assertRaises(InputError):
                    vision_reply(payload(**fields))
                network.assert_not_called()


class VisionTransportTests(unittest.TestCase):
    def test_uses_fixed_local_vision_model_with_two_images_and_no_credentials(self):
        captured = []
        class Opener:
            def open(self, request, **kwargs):
                captured.append((request, kwargs))
                return io.BytesIO(response_body())
        with patch("coach.vision.time.time", return_value=NOW), patch("coach.vision.build_opener", return_value=Opener()) as factory:
            result = vision_reply(payload(minimap=JPEG))
        request, kwargs = captured[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/chat")
        self.assertEqual(request.get_method(), "POST")
        self.assertIsNone(request.get_header("Authorization"))
        self.assertEqual(kwargs["timeout"], 60)
        prompt = json.loads(request.data)
        self.assertEqual(prompt["model"], VISION_MODEL)
        self.assertFalse(prompt["stream"])
        self.assertEqual(prompt["options"]["num_ctx"], 4096)
        self.assertLessEqual(prompt["options"]["num_predict"], 300)
        self.assertIsInstance(prompt["format"], dict)
        self.assertEqual(prompt["messages"][-1]["images"], [JPEG, JPEG])
        system = prompt["messages"][0]["content"].lower()
        self.assertIn("visible", system)
        self.assertIn("fog", system)
        self.assertIn("untrusted", system)
        self.assertIn("Juggernaut", prompt["messages"][-1]["content"])
        self.assertEqual(result["model"], VISION_MODEL)
        self.assertEqual(result["captured_at"], NOW)
        self.assertEqual(result["screen_status"], "game_visible")
        self.assertNotIn(JPEG, json.dumps(result))
        self.assertFalse(any(key in result for key in ("image", "images", "minimap", "api_key")))
        self.assertTrue(any(getattr(handler, "proxies", None) == {} for handler in factory.call_args.args))

    def test_optional_minimap_and_hero_are_not_required(self):
        with patch("coach.vision.time.time", return_value=NOW), patch("coach.vision.build_opener") as factory:
            factory.return_value.open.return_value = io.BytesIO(response_body())
            result = vision_reply({"image": JPEG, "captured_at": NOW})
        self.assertEqual(result["screen_status"], "game_visible")
        request = factory.return_value.open.call_args.args[0]
        self.assertEqual(json.loads(request.data)["messages"][-1]["images"], [JPEG])

    def test_extra_fields_cannot_override_model_or_forward_a_key(self):
        with patch("coach.vision.time.time", return_value=NOW), patch("coach.vision.build_opener") as factory:
            factory.return_value.open.return_value = io.BytesIO(response_body())
            vision_reply(payload(model="remote-model-override", url="https://external.invalid/chat", api_key="synthetic-value-must-not-forward"))
        request = factory.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/chat")
        prompt = request.data.decode()
        self.assertNotIn("remote-model-override", prompt)
        self.assertNotIn("external.invalid", prompt)
        self.assertNotIn("synthetic-value-must-not-forward", prompt)

    def test_delayed_result_is_rejected_instead_of_issued_as_live_advice(self):
        with patch("coach.vision.time.time", side_effect=[NOW, NOW + 91]), patch("coach.vision.build_opener") as factory:
            factory.return_value.open.return_value = io.BytesIO(response_body())
            with self.assertRaises(APIError) as caught:
                vision_reply(payload())
        self.assertEqual(caught.exception.status, 409)

    def test_returned_latency_and_capture_age_are_observed(self):
        with patch("coach.vision.time.time", side_effect=[NOW, NOW + 1.25]), patch("coach.vision.build_opener") as factory:
            factory.return_value.open.return_value = io.BytesIO(response_body())
            result = vision_reply(payload())
        self.assertEqual(result["processed_at"], NOW + 1.25)
        self.assertEqual(result["latency_seconds"], 1.25)

    def test_missing_model_and_unavailable_ollama_have_actionable_errors(self):
        for error in (HTTPError("http://localhost/", 404, "missing", {}, None), URLError("offline"), TimeoutError()):
            with self.subTest(error=type(error).__name__), patch("coach.vision.time.time", return_value=NOW), patch("coach.vision.build_opener") as factory:
                factory.return_value.open.side_effect = error
                with self.assertRaises(APIError) as caught:
                    vision_reply(payload())
            self.assertIn("ollama", str(caught.exception).lower())
            self.assertNotIn(JPEG, str(caught.exception))
        with patch("coach.vision.time.time", return_value=NOW), patch("coach.vision.build_opener") as factory:
            factory.return_value.open.side_effect = HTTPError("http://localhost/", 404, "missing", {}, None)
            with self.assertRaises(APIError) as caught:
                vision_reply(payload())
        self.assertIn("ollama pull gemma3:4b", str(caught.exception))

    def test_malformed_empty_and_oversized_model_responses_are_rejected(self):
        candidates = (b"not JSON", b'{}', b'{"message":{"content":"not JSON"}}', b'{"message":{"content":""}}', b"x" * 500_001)
        for response in candidates:
            with self.subTest(prefix=response[:40]), patch("coach.vision.time.time", return_value=NOW), patch("coach.vision.build_opener") as factory:
                factory.return_value.open.return_value = io.BytesIO(response)
                with self.assertRaises(APIError):
                    vision_reply(payload())

    def test_structured_response_requires_known_status_and_bounded_strings(self):
        candidates = ({**GOOD_REPLY, "screen_status": "hidden_enemy_seen"}, {**GOOD_REPLY, "observation": []},
                      {**GOOD_REPLY, "advice": "x" * 501}, {"screen_status": "game_visible"}, [])
        for value in candidates:
            with self.subTest(value_type=type(value).__name__), patch("coach.vision.time.time", return_value=NOW), patch("coach.vision.build_opener") as factory:
                factory.return_value.open.return_value = io.BytesIO(response_body(value))
                with self.assertRaises(APIError):
                    vision_reply(payload())

    def test_non_game_and_unclear_responses_do_not_become_game_visible(self):
        for status in ("unclear", "not_game"):
            reply = {**GOOD_REPLY, "screen_status": status, "advice": "Cannot judge positioning from this frame."}
            with self.subTest(status=status), patch("coach.vision.time.time", return_value=NOW), patch("coach.vision.build_opener") as factory:
                factory.return_value.open.return_value = io.BytesIO(response_body(reply))
                result = vision_reply(payload())
            self.assertEqual(result["screen_status"], status)


if __name__ == "__main__":
    unittest.main()
