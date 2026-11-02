"""Optional developer browser checks: python -m tests.browser_smoke.

Needs Playwright + Chromium, neither required to run the actual app.
Uses an explicitly fake upstream client, not a live OpenDota connection.
"""

import json
import threading
from unittest.mock import patch

from playwright.sync_api import expect, sync_playwright

from server import create_server
from tests.test_coach import FixtureClient, match_fixture


def main():
    client = FixtureClient()
    client.details[8000000000] = match_fixture(parsed=False)[1]
    server = create_server(0, client=client)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    errors = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1440, "height": 1100}, device_scale_factor=1)
            page.on("pageerror", lambda error: errors.append(str(error)))
            # The final invalid-account scenario deliberately returns HTTP 400.
            page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" and "400 (Bad Request)" not in msg.text else None)
            page.goto(base)
            assert page.locator("#account").input_value() == "314758455"
            assert page.locator("#dashboard").is_hidden()
            page.locator("#demo-button").click()
            page.wait_for_selector("#dashboard", state="visible")
            assert "SAMPLE DATA" in page.locator("#source-badge").inner_text()
            assert page.locator("#matches tr").count() == 12
            assert page.locator(".focus-card").count() == 3
            page.locator("#ai-question").fill("What should I practice?")
            with patch("server.coach_reply", return_value={"answer": "Practice five lanes. <img src=x onerror=alert(1)>", "model": "test-fixture", "source": "demo"}):
                page.locator("#ai-form button").click()
                expect(page.locator("#ai-answer")).to_contain_text("SAMPLE DATA DISCUSSION")
                assert page.locator("#ai-answer img").count() == 0
            page.screenshot(path="/tmp/dota-ascent-desktop.png", full_page=True)
            page.locator("#result-filter").select_option("wins")
            assert page.locator("#matches tr").count() == 5
            page.locator("#matches [data-review]").first.click()
            assert "SAMPLE MATCH" in page.locator("#review-output").inner_text()
            assert page.locator("#parse-match").count() == 0
            check = page.locator("[data-practice]").first
            check.check()
            with page.expect_download() as downloaded:
                page.locator("#export-button").click()
            download = downloaded.value
            assert "SAMPLE" in download.suggested_filename
            assert json.load(open(download.path()))["source"] == "demo"
            page.reload()
            page.locator("#demo-button").click()
            page.wait_for_selector("#dashboard", state="visible")
            assert page.locator("[data-practice]").first.is_checked()
            page.locator("#role").select_option("carry")
            page.evaluate("window.scrollTo(0, 0)")
            before_analyze = page.evaluate("window.scrollY")
            page.locator("#analyze-button").click()
            expect(page.locator("#report-title")).to_contain_text("Test Player")
            expect(page.locator("#status")).to_contain_text("Loaded 6 ranked matches")
            assert page.evaluate("window.scrollY") == before_analyze, "Analyze unexpectedly jumped down the page"
            assert page.locator("#ai-answer").is_hidden()
            assert page.locator("#matches tr").count() == 6
            assert not page.locator("[data-practice]").first.is_checked()
            page.locator("#matches [data-review]").first.click()
            assert page.locator("#refresh-match").is_visible()
            page.locator("#refresh-match").click()
            expect(page.locator("#connect-form")).to_have_attribute("aria-busy", "false")
            page.locator("#match-id").fill("8000000000")
            page.locator("#review-form button").click()
            expect(page.locator("#review-output")).to_contain_text("#8000000000")
            page.locator("#parse-match").click()
            expect(page.locator("#review-output")).to_contain_text("accepted the parse request")
            assert client.parse_calls == [8000000000]
            page.locator("#import-file").set_input_files({"name": "match.json", "mimeType": "application/json", "buffer": json.dumps(match_fixture(dire=True)[1]).encode()})
            expect(page.locator("#review-output")).to_contain_text("IMPORTED OPENDOTA JSON")
            assert "Loss" in page.locator("#review-output").inner_text()
            page.locator("#account").fill("bad-account")
            page.locator("#analyze-button").click()
            page.wait_for_selector("#error", state="visible")
            assert "friend ID" in page.locator("#error").inner_text()
            assert "Test Player" in page.locator("#report-title").inner_text()
            client.rows = []
            page.locator("#account").fill("314758455")
            page.locator("#analyze-button").click()
            expect(page.locator("#report-meta")).to_contain_text("0 eligible matches")
            expect(page.locator("#warnings")).to_contain_text("No eligible ranked matches")
            assert page.locator("#history-status").is_visible()
            assert page.locator("#dashboard").is_hidden()
            expect(page.locator("#history-status-description")).to_contain_text("friend ID 314758455")
            assert "SAMPLE" not in page.locator("#source-badge").inner_text()
            assert "No numeric observations" in page.locator("#trend-chart").inner_text()
            client.rows = [match_fixture(0)[0]]
            page.locator("#retry-history").click()
            expect(page.locator("#report-meta")).to_contain_text("1 eligible matches")
            assert page.locator("#history-status").is_hidden()
            assert page.locator("#dashboard").is_visible()
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path="/tmp/dota-ascent-mobile.png", full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Mobile page overflows horizontally"
            assert not errors, errors
            browser.close()
            print("Browser checks passed: empty state, sample labels, filters, replay review, live-flow fixtures, parse submission, refresh, import, export, checklist isolation/persistence, AI fixture chat/escaping/reset, error recovery, desktop/mobile layout; no JavaScript or CSP errors.")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    main()
