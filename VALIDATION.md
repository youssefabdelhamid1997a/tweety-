# Verification record — November 2, 2026

## Version 1.1.0 update — November 3, 2026

- **103 automated tests passed**, including 16 vision-adapter tests and four live-route/concurrency checks. These cover valid JPEG framing and dimensions, input/output size bounds, fresh timestamps, stale replies, fixed local model routing, no credentials/image echo, schema validation, model errors, and avoiding overlapping local AI calls while keeping history requests available.
- The existing dashboard Chromium suite passed. A separate live-control browser suite uses synthetic canvas streams and controlled model replies to test explicit sharing, no model request from sharing alone, JPEG/crop compatibility, manual and periodic checks, cancellation while in flight, late-reply suppression, permission denial, black frames, browser-ended sharing, safe text rendering, and a narrow-screen layout.
- Live frames and advice are not written to disk, reports, caches, or browser storage by this feature. No real desktop, game window, API key, or vision model was used in these checks.
- **Unverified on the user's PC:** actual Windows screen picker and game capture, background fullscreen capture, installed local speech voices, Gemma3 output quality, RTX 5060 inference performance, available VRAM/system RAM, and Dota's frame-rate impact. A synthetic UI/transport pass does not establish reliable tactical advice. The release describes periodic snapshot review rather than instant or complete live understanding.

Earlier version verification records follow.

## Version 1.0.2 update — November 3, 2026

- **83 automated tests passed** with no skipped tests. New tests cover environment/local-file precedence, private atomic saves, matching hidden input, refusal to echo a key, local removal, header authentication, public/key-specific cache separation, redacted errors, health metadata containing only credential presence, redirect rejection, and ignoring an older running app after an update.
- The full desktop/mobile Chromium flow passed, including the local-key setup instructions. Optional key setup does not break public-mode analysis, match import/export, replay review, checklist persistence, or local AI rendering.
- Only fictitious credentials were used in tests. A real paid API key was not sent or validated. Actual plan access and whether it changes the public-history response must be verified on the user's PC after local setup.
- The setup prompt is covered with controlled terminal input; native Windows batch execution remains untested. The key file is plain text, not an encrypted vault; this is stated in the prompt and documentation.

Earlier version verification records follow.

## Version 1.0.1 update — November 3, 2026

- **55 automated tests passed**, with none skipped. Includes explicit history refresh replacing a cached empty response, using only eligible ranked matches from the recent endpoint, honest handling of unavailable or unranked recent history, safe running-instance detection, Windows address-in-use simulation, bounded port fallback, and propagation of other startup errors.
- The full Chromium desktop/mobile flow passed. New checks verify that Analyze does not move the page, a visible explanation replaces the zero-filled dashboard when history is empty, and Check OpenDota again displays a newly available match. Existing import/export, replay-room, AI rendering, and checklist checks still pass.
- Fresh public API checks for account 314758455 again returned zero rows from ranked, recent, and unfiltered history. No personal match-loading success is claimed. The fix addresses stale local results and confusing UI behavior; it cannot manufacture missing public API data.
- Native Windows execution remains untested. The launcher and socket behavior are covered by portable tests, including simulated Winsock error 10048.

The earlier 1.0.0 verification record follows.

## Passed in the cloud instance

- **36 automated tests**: `python3 -m unittest discover -s tests -v` on Python 3.12.14. No skipped or expected-failure tests.
- **Chromium desktop and mobile browser checks**: `python3 -m tests.browser_smoke`. Covered the initial state, sample labels, summary cards, filters, match review, parse submission through a controlled upstream, refresh, JSON import/export, per-account checklist persistence, AI rendering with controlled responses, text escaping, invalid-input recovery, empty match history, and 390-pixel layout. No JavaScript or content-security-policy errors. The intentional invalid-input request correctly returned HTTP 400.
- **Production startup**: started `python3 server.py`, verified `/api/health`, and requested the demo report, which returned 12 synthetic matches and three coaching priorities.
- **ZIP integrity and extracted startup**: extracted into a temporary folder with spaces, launched the packaged server from a different working directory, and verified health and the demo analysis.
- **JavaScript and Python syntax**: `node --check static/app.js` and Python compilation.

## Live OpenDota evidence

The network initially denied `api.opendota.com`. After the configuration update, real HTTPS requests succeeded.

- Player `314758455`: OpenDota returned **Tweety, Archon II**. This is the provider's recorded rank, not an independent verification of the current in-game rank.
- Ranked history, recent matches, and a separate unfiltered-history query all returned **zero matches**. Retrying after the public-visibility discussion also returned zero. This does not prove the precise cause. No personal gameplay flaws or progress metrics can be inferred from an empty history.
- Public ranked reference match `1781962623` was fetched and passed through the single-match review workflow for its actual player. Its summary was available but its replay arrays were absent, correctly producing no fabricated timeline.
- Separate public reference match `7490235544` contained real parsed replay data: 46 time/gold/LH samples and 51 purchase events. Normalization extracted **69 LH at 10**, 46 economy points, and three supported completed-item events. This is a non-ranked reference used only to check real event-field compatibility; it was not presented as the user's match or fed into the ranked coaching history.

## Not claimed as verified

- Personal ranked/replay analysis: blocked by the absence of public account history. Enable public match data, sign in to OpenDota, and allow new games to populate; historical hidden games may remain unavailable.
- Native Windows execution: the portable Python application and ZIP were tested on Linux. `run.bat` has Windows CRLF line endings, version checks, and quoted folder handling, but no Windows host was available.
- Actual local AI inference: Ollama and model weights are not installed in this cloud instance. Adapter behavior is tested with controlled responses; a real request without Ollama correctly returns an actionable HTTP 503. The user must install/start Ollama and pull `llama3.2:3b` to use the optional chat.
- Successful OpenDota job processing: parse submission is integration-tested with a controlled upstream; no real parse job was submitted. Job acceptance is not a promise of replay availability.
- Publication or restoration in a new cloud task: network/startup configuration drafts were saved, but a draft save does not itself publish the final filesystem snapshot.
