"""Optional live-control browser checks, with synthetic capture and fake inference.

Run python -m tests.browser_live_smoke. No actual desktop, Ollama, or API key is
captured or used. Requires the cloud's optional Playwright/Chromium tools.
"""

import json
import threading
import time

from playwright.sync_api import Error, expect, sync_playwright

from coach.vision import _validate_image
from server import create_server
from tests.test_coach import FixtureClient

CAPTURE_STUB = """(() => {
  window.__captureCount = 0;
  window.__captureMode = 'color';
  window.__captureOptions = [];
  window.__spoken = [];
  window.__speechCancels = 0;
  window.SpeechSynthesisUtterance = class { constructor(text) { this.text=text; } };
  Object.defineProperty(window, 'speechSynthesis', {configurable:true, value:{
    getVoices:()=>[{name:'remote fixture',lang:'en-US',localService:false},{name:'local fixture',lang:'en-US',localService:true}],
    addEventListener:()=>{},
    speak:(utterance)=>window.__spoken.push({text:utterance.text,local:utterance.voice.localService}),
    cancel:()=>window.__speechCancels++
  }});
  Object.defineProperty(navigator.mediaDevices, 'getDisplayMedia', {configurable:true, value: async (options) => {
    window.__captureCount++;
    window.__captureOptions.push(options);
    if (window.__captureMode === 'denied') throw new DOMException('Synthetic permission denial', 'NotAllowedError');
    const canvas = document.createElement('canvas');
    canvas.width=1600; canvas.height=900;
    const ctx=canvas.getContext('2d');
    let tick=0;
    const paint=()=> {
      ctx.fillStyle=window.__captureMode==='black'?'#000':'#315b58';
      ctx.fillRect(0,0,1600,900);
      if(window.__captureMode!=='black') {
        ctx.fillStyle='#e5c48e';ctx.fillRect((tick++*7)%1400,100,100,120);
        ctx.fillStyle='#152836';ctx.fillRect(0,680,220,220);
        ctx.fillStyle='#a9efc5';ctx.font='30px sans-serif';ctx.fillText('SYNTHETIC TEST FRAME',300,450);
      }
    };
    paint();
    const timer=setInterval(paint,100);
    const stream=canvas.captureStream(5);
    const originalStop=stream.getVideoTracks()[0].stop.bind(stream.getVideoTracks()[0]);
    stream.getVideoTracks()[0].stop=()=>{clearInterval(timer);originalStop();};
    window.__sharedTrack=stream.getVideoTracks()[0];
    return stream;
  }});
})();"""


def result_for(data):
    return {"model": "synthetic-test-model", "screen_status": "game_visible",
            "observation": "A synthetic test frame was shared.",
            "advice": "Review visible cover. <img src=x onerror=alert(1)>",
            "uncertainty": "Synthetic fixture; not a Dota gameplay judgment.",
            "captured_at": data["captured_at"], "processed_at": time.time(), "latency_seconds": 0.1}


def main():
    server = create_server(0, client=FixtureClient())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    errors, calls, pending = [], [], []
    mode = {"hold": False}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.add_init_script(CAPTURE_STUB)
            page.on("pageerror", lambda error: errors.append(str(error)))
            def infer(route):
                data = route.request.post_data_json
                _validate_image(data["image"])
                if "minimap" in data:
                    _validate_image(data["minimap"], minimap=True)
                calls.append((time.monotonic(), data))
                if mode["hold"]:
                    pending.append((route, data))
                else:
                    route.fulfill(status=200, content_type="application/json", body=json.dumps(result_for(data)))
            page.route("**/api/live/analyze", infer)
            page.goto(base)
            assert page.evaluate("window.__captureCount") == 0
            assert calls == []
            assert page.locator("#live-once").is_disabled()
            assert not page.locator("#live-speak").is_checked()
            page.locator("#live-speak").check()
            page.locator("#live-hero").fill("Juggernaut")
            page.locator("#live-role").select_option("carry")
            page.locator("#live-minimap").select_option("left")
            page.locator("#live-start").click()
            expect(page.locator("#live-status")).to_contain_text("preview is ready")
            assert page.evaluate("window.__captureOptions[0].audio") is False
            assert calls == [], "Selecting a share must not submit frames"
            page.locator("#live-once").click()
            expect(page.locator("#live-result")).to_be_visible()
            assert len(calls) == 1
            assert calls[0][1]["hero"] == "Juggernaut"
            assert "minimap" in calls[0][1]
            assert set(calls[0][1]) == {"image", "minimap", "captured_at", "hero", "role"}
            assert page.locator("#live-result img").count() == 0, "Model text must not become HTML"
            assert page.evaluate("window.__spoken.length") == 1
            assert page.evaluate("window.__spoken[0].local") is True
            expect(page.locator("#live-advice")).to_contain_text("<img")
            assert page.evaluate("Object.keys(localStorage).some(key=>key.includes('live'))") is False

            # Periodic checks start explicitly; their next capture is scheduled
            # after the prior response, never as an overlapping interval.
            page.locator("#live-periodic").click()
            expect(page.locator("#live-status")).to_contain_text("Next snapshot")
            assert len(calls) == 2
            cancel_count = page.evaluate("window.__speechCancels")
            page.wait_for_timeout(15500)
            assert page.evaluate("window.__speechCancels") > cancel_count, "Speech should stop once the frame exceeds its freshness limit"
            page.wait_for_timeout(15000)
            expect(page.locator("#live-status")).to_contain_text("Next snapshot")
            assert len(calls) == 3
            assert calls[2][0] - calls[1][0] >= 29.5
            page.locator("#live-periodic").click()
            expect(page.locator("#live-status")).to_contain_text("paused")

            # Stop works while an inference response is still outstanding.
            mode["hold"] = True
            page.locator("#live-once").click()
            deadline = time.monotonic() + 5
            while not pending and time.monotonic() < deadline:
                page.wait_for_timeout(50)
            assert pending
            assert page.locator("#live-stop").is_enabled()
            cancel_count = page.evaluate("window.__speechCancels")
            page.locator("#live-stop").click()
            assert page.evaluate("window.__speechCancels") > cancel_count
            expect(page.locator("#live-status")).to_contain_text("Sharing stopped")
            assert page.evaluate("window.__sharedTrack.readyState") == "ended"
            assert page.locator("#live-result").is_hidden()
            route, data = pending.pop()
            try:
                route.fulfill(status=200, content_type="application/json", body=json.dumps(result_for(data)))
            except Error:
                pass  # Chromium may already have cancelled the intercepted request.
            page.wait_for_timeout(150)
            assert page.locator("#live-result").is_hidden(), "Late results must not revive a stopped session"
            assert page.locator("#live-once").is_disabled()

            # Browser share cancellation and black frames stay local.
            before = len(calls)
            page.evaluate("window.__captureMode='denied'")
            page.locator("#live-start").click()
            expect(page.locator("#live-error")).to_contain_text("cancelled or denied")
            assert len(calls) == before
            page.evaluate("window.__captureMode='black'")
            page.locator("#live-start").click()
            expect(page.locator("#live-status")).to_contain_text("preview is ready")
            page.locator("#live-once").click()
            expect(page.locator("#live-error")).to_contain_text("nearly black")
            assert len(calls) == before
            page.locator("#live-stop").click()

            # The browser's own Stop sharing control follows the same cleanup.
            page.evaluate("window.__captureMode='color'")
            page.locator("#live-start").click()
            expect(page.locator("#live-status")).to_contain_text("preview is ready")
            page.evaluate("window.__sharedTrack.dispatchEvent(new Event('ended'))")
            expect(page.locator("#live-status")).to_contain_text("browser ended sharing")
            assert page.evaluate("window.__sharedTrack.readyState") == "ended"
            assert page.evaluate("document.querySelector('#live-preview').srcObject") is None
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path="/tmp/dota-ascent-live-mobile.png", full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            assert not errors, errors
            browser.close()
            print("Live browser checks passed: explicit sharing and analysis, JPEG/crop compatibility, no automatic upload, safe text, periodic timing, Stop/in-flight cancellation, late-response rejection, permission denial, black-frame rejection, browser-ended cleanup, mobile layout. Capture/model were synthetic; no native game or model accuracy claim.")
    finally:
        server.shutdown(); server.server_close(); thread.join()


if __name__ == "__main__":
    main()
