import copy
import io
import json
import tempfile
import threading
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from unittest.mock import patch

from coach.analysis import InputError, account_id, at_minute, build_report, is_ranked, normalize
from coach.client import APIError, OpenDota
from coach.demo import demo_report
from coach.service import CoachService
from server import create_server

ACCOUNT = 314758455


def match_fixture(i=0, parsed=True, dire=False):
    slot = 128 if dire else 0
    player = {"account_id": ACCOUNT, "player_slot": slot, "hero_id": 8, "kills": 3, "deaths": 12, "assists": 4,
              "gold_per_min": 430, "xp_per_min": 490, "tower_damage": 400, "last_hits": 170, "leaver_status": 0,
              "lane_role": 1}
    if parsed:
        player.update({"times": list(range(0, 2401, 60)), "lh_t": [i * 3 for i in range(41)],
                       "gold_t": [600 + i * 430 for i in range(41)], "obs_placed": 0,
                       "purchase_log": [{"key": "tango", "time": -20}, {"key": "black_king_bar", "time": 1850}]})
    detail = {"match_id": 8000000000 + i, "duration": 2400, "lobby_type": 7, "start_time": 1700000000 + i * 3600,
              "radiant_win": True, "players": [player] + [{"player_slot": slot + j, "kills": 5} for j in range(1, 5)]}
    row = {**player, **{k: v for k, v in detail.items() if k != "players"}}
    # Match history projection does not contain replay arrays or ward placement.
    for key in ("times", "lh_t", "gold_t", "purchase_log", "obs_placed"):
        row.pop(key, None)
    return row, detail


class FixtureClient:
    def __init__(self):
        self.rows, self.details = [], {}
        self.parse_calls = []
        for i in range(6):
            row, detail = match_fixture(i)
            self.rows.append(row)
            self.details[row["match_id"]] = detail

    def matches(self, account, limit):
        return copy.deepcopy(self.rows[:limit])

    def profile(self, account):
        return {"profile": {"personaname": "Test Player"}, "rank_tier": 44}

    def match(self, match):
        if match not in self.details:
            raise APIError("Match not found", 404)
        return copy.deepcopy(self.details[match])

    def refresh_match(self, match):
        return self.match(match)

    def parse(self, match):
        self.parse_calls.append(match)
        return {"job": {"jobId": 1234}}


class IdentityTests(unittest.TestCase):
    def test_real_steam64_conversion(self):
        for value in ("314758455", "76561198275024183", "https://steamcommunity.com/profiles/76561198275024183/", "https://www.opendota.com/players/314758455"):
            self.assertEqual(account_id(value), ACCOUNT)

    def test_invalid_and_unsafe_urls(self):
        for value in ("0", "4294967296", "-2", "1e5", True, "https://evil.com/profiles/76561198275024183", "https://steamcommunity.com.evil.com/profiles/76561198275024183", "https://steamcommunity.com/id/vanity", "http://steamcommunity.com/profiles/76561198275024183"):
            with self.subTest(value=value), self.assertRaises(InputError):
                account_id(value)


class AnalysisTests(unittest.TestCase):
    def test_radiant_and_dire_outcome(self):
        for dire, expected in [(False, True), (True, False)]:
            row, detail = match_fixture(dire=dire)
            self.assertEqual(normalize(row, ACCOUNT, detail)["won"], expected)

    def test_missing_outcomes_do_not_become_losses(self):
        row, _ = match_fixture()
        row.pop("radiant_win")
        result = build_report(ACCOUNT, {}, [row])
        self.assertIsNone(result["summary"]["win_rate"])
        self.assertEqual(result["summary"]["losses"], 0)

    def test_filters_and_deduplication(self):
        row, _ = match_fixture()
        rows = [row, row, {**row, "match_id": 1, "lobby_type": 0}, {**row, "match_id": 2, "duration": 500}, {**row, "match_id": 3, "leaver_status": 2}]
        result = build_report(ACCOUNT, {}, rows)
        self.assertEqual(result["summary"]["matches"], 1)
        self.assertFalse(is_ranked({"lobby_type": 7}))

    def test_missing_fields_not_zero_or_evidence(self):
        row, _ = match_fixture()
        for field in ("deaths", "gold_per_min", "tower_damage"):
            row.pop(field)
        result = build_report(ACCOUNT, {}, [{**row, "match_id": i} for i in range(4)], role="carry")
        self.assertIsNone(result["summary"]["gold_per_min"])
        self.assertIsNone(result["summary"]["deaths_per_10"])
        self.assertEqual([p["key"] for p in result["priorities"]], ["baseline"])

    def test_safe_lane_is_not_automatically_carry(self):
        row, detail = match_fixture()
        self.assertEqual(normalize(row, ACCOUNT, detail)["role"], "unknown")
        detail["players"][0]["lane_role"] = 2
        self.assertEqual(normalize(row, ACCOUNT, detail)["role"], "mid")

    def test_lh_10_uses_time_not_array_index(self):
        self.assertEqual(at_minute({"times": [-60, 0, 600], "lh_t": [0, 0, 42]}, "lh_t", 10), 42)
        self.assertIsNone(at_minute({"times": [0, 540, 660], "lh_t": [0, 30, 40]}, "lh_t", 10))

    def test_support_does_not_get_core_farm_targets(self):
        client = FixtureClient()
        result = build_report(ACCOUNT, {}, client.rows, client.details, role="support")
        self.assertIn("vision", [p["key"] for p in result["priorities"]])
        self.assertNotIn("lane", [p["key"] for p in result["priorities"]])
        self.assertNotIn("objectives", [p["key"] for p in result["priorities"]])

    def test_repeated_core_signals_and_evidence_denominators(self):
        client = FixtureClient()
        result = build_report(ACCOUNT, {}, client.rows, client.details, role="carry")
        cards = {p["key"]: p for p in result["priorities"]}
        self.assertEqual(set(cards), {"survival", "lane", "objectives"})
        self.assertEqual(cards["lane"]["sample"], 6)
        self.assertEqual(cards["lane"]["affected"], 6)

    def test_small_sample_does_not_claim_repeated_pattern(self):
        row, detail = match_fixture()
        result = build_report(ACCOUNT, {}, [row], {row["match_id"]: detail}, role="carry")
        self.assertEqual(result["priorities"][0]["key"], "baseline")

    def test_kill_participation_needs_complete_team(self):
        row, detail = match_fixture()
        result = normalize(row, ACCOUNT, detail)
        self.assertEqual(result["kill_participation"], 30.4)
        detail["players"].pop()
        self.assertIsNone(normalize(row, ACCOUNT, detail)["kill_participation"])

    def test_unparsed_match_has_no_invented_events(self):
        row, detail = match_fixture(parsed=False)
        result = normalize(row, ACCOUNT, detail)
        self.assertFalse(result["parsed"])
        self.assertEqual(result["economy"], [])
        self.assertIsNone(result["last_hits_10"])
        self.assertEqual(result["purchases"], [])

    def test_demo_always_labeled(self):
        result = demo_report()
        self.assertEqual(result["source"], "demo")
        self.assertIn("SAMPLE DATA", result["warnings"][0])
        self.assertEqual(result["summary"]["matches"], 12)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.client = FixtureClient()
        self.service = CoachService(self.client)

    def test_analysis_loads_five_newest_details_only(self):
        result = self.service.analyze({"account": ACCOUNT, "role": "carry"})
        self.assertEqual(result["summary"]["matches"], 6)
        self.assertEqual(result["summary"]["parsed"], 5)
        self.assertEqual(result["matches"][0]["match_id"], 8000000005)

    def test_empty_history_is_not_sample_data(self):
        self.client.rows = []
        result = self.service.analyze({"account": ACCOUNT})
        self.assertEqual(result["source"], "live")
        self.assertEqual(result["summary"]["matches"], 0)
        self.assertIsNone(result["summary"]["win_rate"])
        self.assertTrue(any("No eligible ranked matches" in w for w in result["warnings"]))

    def test_unavailable_replays_preserve_summary(self):
        with patch.object(self.client, "match", side_effect=APIError("Rate limited", 429)):
            result = self.service.analyze({"account": ACCOUNT})
        self.assertEqual(result["summary"]["matches"], 6)
        self.assertEqual(result["summary"]["parsed"], 0)
        self.assertTrue(any("Rate limited" in w for w in result["warnings"]))

    def test_no_silent_sample_fallback(self):
        with patch.object(self.client, "matches", side_effect=APIError("Offline")):
            with self.assertRaises(APIError):
                self.service.analyze({"account": ACCOUNT})

    def test_account_absent_and_nonranked_imports_rejected(self):
        _, detail = match_fixture()
        with self.assertRaises(InputError):
            self.service.review({"account": 999}, imported=detail)
        detail["lobby_type"] = 0
        with self.assertRaises(InputError):
            self.service.review({"account": ACCOUNT}, imported=detail)

    def test_import_contains_exact_player_and_timings(self):
        _, detail = match_fixture(dire=True)
        result = self.service.review({"account": ACCOUNT, "role": "carry"}, imported=detail)
        self.assertEqual(result["source"], "import")
        self.assertFalse(result["matches"][0]["won"])
        self.assertEqual(result["matches"][0]["purchases"][0]["time"], 1850)

    def test_requested_match_id_must_match_response(self):
        with patch.object(self.client, "match", return_value=match_fixture(1)[1]):
            with self.assertRaises(APIError):
                self.service.review({"account": ACCOUNT, "match_id": 8000000000})


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.client = OpenDota(self.directory.name)
        self.sleep = patch("coach.client.time.sleep")
        self.sleep.start()

    def tearDown(self):
        self.sleep.stop()
        self.directory.cleanup()

    def test_query_projection_cache_and_tls(self):
        def respond(request, **kwargs):
            self.assertTrue(request.full_url.startswith("https://api.opendota.com/api/players/"))
            query = parse_qs(urlparse(request.full_url).query)
            self.assertEqual(query["lobby_type"], ["7"])
            self.assertIn("hero_id", query["project"])
            self.assertIn("duration", query["project"])
            self.assertIn("gold_per_min", query["project"])
            self.assertTrue(kwargs["context"].check_hostname)
            return io.BytesIO(b'[]')
        with patch("coach.client.urlopen", side_effect=respond) as remote:
            self.client.matches(ACCOUNT, 20)
            self.client.matches(ACCOUNT, 20)
        self.assertEqual(remote.call_count, 1)

    def test_http_rate_limit_and_network_errors(self):
        for failure, status in [(HTTPError("url", 429, "limited", {}, None), 429), (URLError("offline"), 502),
                                (HTTPError("url", 403, "denied", {}, None), 502)]:
            with self.subTest(status=status), patch("coach.client.urlopen", side_effect=failure), self.assertRaises(APIError) as caught:
                self.client.profile(ACCOUNT)
            self.assertEqual(caught.exception.status, status)

    def test_parse_is_explicit_post_and_invalidates_cache(self):
        methods = []
        def respond(request, **kwargs):
            methods.append(request.get_method())
            return io.BytesIO(b'{"job":{"jobId":123}}' if request.get_method() == "POST" else b'{"match_id":8000000000}')
        with patch("coach.client.urlopen", side_effect=respond):
            self.client.match(8000000000)
            self.client.match(8000000000)
            self.client.parse(8000000000)
            self.client.match(8000000000)
        self.assertEqual(methods, ["GET", "POST", "GET"])

    def test_unconfirmed_parse_is_not_reported_as_success(self):
        with patch("coach.client.urlopen", return_value=io.BytesIO(b'{}')):
            with self.assertRaises(APIError):
                self.client.parse(8000000000)


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = FixtureClient()
        cls.server = create_server(0, client=cls.client)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def call(self, path, data=None, headers=None):
        request = Request(self.base + path, data=json.dumps(data).encode() if data is not None else None,
                          headers=headers or ({"Content-Type": "application/json"} if data is not None else {}))
        return urlopen(request, timeout=5)

    def test_health_and_dashboard(self):
        with self.call("/api/health") as response:
            self.assertEqual(json.load(response)["status"], "ok")
        with self.call("/") as response:
            self.assertIn(b"Dota Ascent", response.read())
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])

    def test_ranked_analysis_over_http(self):
        with self.call("/api/analyze", {"account": "https://steamcommunity.com/profiles/76561198275024183/", "role": "carry", "limit": 10}) as response:
            report = json.load(response)
        self.assertEqual(report["account_id"], ACCOUNT)
        self.assertEqual(report["summary"]["parsed"], 5)
        self.assertEqual(len(report["priorities"]), 3)

    def test_invalid_input_is_actionable(self):
        with self.assertRaises(HTTPError) as caught:
            self.call("/api/analyze", {"account": "bad"})
        self.assertEqual(caught.exception.code, 400)
        self.assertIn("friend ID", json.load(caught.exception)["error"])

    def test_reject_cross_origin_and_dns_rebinding(self):
        for headers in ({"Content-Type": "application/json", "Origin": "https://evil.example"}, {"Content-Type": "application/json", "Host": "evil.example"}):
            with self.assertRaises(HTTPError) as caught:
                self.call("/api/analyze", {"account": ACCOUNT}, headers)
            self.assertEqual(caught.exception.code, 403)

    def test_import_and_parse_over_http(self):
        with self.call("/api/import", {"account": ACCOUNT, "match": match_fixture()[1]}) as response:
            self.assertEqual(json.load(response)["source"], "import")
        with self.call("/api/parse", {"match_id": 8000000000}) as response:
            self.assertEqual(json.load(response)["job_id"], 1234)
        self.assertIn(8000000000, self.client.parse_calls)

    def test_static_traversal_blocked(self):
        with self.assertRaises(HTTPError) as caught:
            self.call("/../server.py")
        self.assertEqual(caught.exception.code, 404)

    def test_invalid_and_oversized_requests(self):
        request = Request(self.base + "/api/import", data=b"{broken", headers={"Content-Type": "application/json"})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        self.assertEqual(caught.exception.code, 400)
        request = Request(self.base + "/api/import", data=b"{}", headers={"Content-Type": "application/json", "Content-Length": "10000001"})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        self.assertEqual(caught.exception.code, 413)


if __name__ == "__main__":
    unittest.main()
