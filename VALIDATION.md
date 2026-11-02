# Verification record — November 2, 2026

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
