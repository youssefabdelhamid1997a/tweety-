# Dota Ascent — your personal Dota 2 coach

A local dashboard for **ranked Dota 2**, prepared for friend ID **314758455** (Steam profile `76561198275024183`). Change the account in the app whenever you want.

It connects to OpenDota, looks for patterns worth reviewing, and turns them into a five-game practice plan. Optional **local AI chat with Ollama** can discuss the report. The dashboard works without AI chat, a paid API key, a Steam password, or any Python package installations.

Version **1.0.1** removes the automatic page jump after Analyze, checks fresh match history on every click, and explains empty results beside the button with retry and direct match-ID review options. If ranked history is empty but OpenDota's recent endpoint has eligible ranked games, those games are used with an explicit coverage note. Reopening an already running coach opens its browser again; an unrelated service on the default port causes the launcher to choose another free local port.

## Run on Windows — no programming needed

1. **Install Python** from [python.org](https://www.python.org/downloads/windows/). Use Python **3.10 or newer** (tested with 3.12). Tick **Add Python to PATH** in the installer.
2. Download the project ZIP and **right-click → Extract All**. Open the extracted folder containing `run.bat` and `server.py`. Do not run it inside the ZIP.
3. **Double-click `run.bat`.** A small console window opens, followed by the dashboard in your browser. Keep the console open while using the coach. No `pip`, Node.js, or Git commands are required.
4. In Dota 2, enable **Settings → Social → Expose Public Match Data**. Your account is prefilled in the dashboard. Select the role you played, then click **Analyze my matches**. Public API requests may take about a minute. Choose **Explore sample dashboard** if you just want to see how it works; those matches are invented and clearly labeled.
5. Start with **one** suggested exercise for your next five ranked games. Review the evidence matches and your in-game replays rather than treating a statistic as proof of a mistake.

If the browser does not open, enter the address printed in the console (normally `http://127.0.0.1:8765`). Close the console or press **Ctrl+C** there to stop the app. Double-click `run.bat` to start it again. Clicking Analyze keeps you in place and shows a completion message; the results appear below. An empty response produces a clear explanation instead of a zero-filled dashboard.

### Optional: turn on the AI conversation

The numerical dashboard uses explainable rules. Actual generative AI chat is a separate optional feature:

1. Install [Ollama for Windows](https://ollama.com/download/windows) and start it.
2. Open **Command Prompt** from the Windows Start menu. Copy and paste this one command:

   ```text
   ollama pull llama3.2:3b
   ```

3. Wait for the model download (roughly a few GB; allow several GB of free disk and RAM). Then load a report in Dota Ascent, scroll to **Ask your coach**, and ask a question such as “What should I focus on over my next five games?”

The model runs on your computer at port 11434. Initial CPU answers can be slow; the app allows up to two minutes. A small summary of the loaded report and your question are sent to **local Ollama**, not a cloud AI company. Sample reports remain labeled in the chat. AI text can still be wrong: verify it against the report and replay. The app never silently substitutes a rule-based answer if Ollama is unavailable.

## What the coach can show

- Latest **10, 20, or 30 ranked matches** from OpenDota, with wins/losses, deaths per 10 minutes, GPM, and coverage counts.
- Up to **five newest eligible games** get detailed API fetches. This keeps the free public API workload small. Available parsed events add exact LH at 10, gold-earned timelines, ward placements, selected completed-item purchases, and kill participation when the allied team data is complete.
- A maximum of three **evidence-linked coaching priorities**. Every field has its own usable sample count. Repeated-signal rules need at least three usable matches and two flagged observations.
- A **replay room** for a specific ranked match, an explicit OpenDota parse-request button, and **full OpenDota match JSON import** (up to 8 MB). The account must be identified in the match.
- A role-aware five-game checklist saved in this browser, separately for each account/role and sample mode, plus a report JSON download.
- A practical Archon → Legend → Ancient → Divine learning path. This is a learning framework, **not a prediction or guarantee** of rank gain.

## What “replay analysis” means here

This app consumes **OpenDota's already parsed replay data**. It does **not** open raw `.dem` files, watch video, track your camera, run a Dota replay parser, or automatically prove positioning mistakes. OpenDota may have summary data but no replay events, particularly for old matches whose replay downloads have expired.

Click a match's **Review** button to inspect the data already loaded. For deeper data, use **Refresh match**. If the replay is unparsed, click **Request OpenDota parse**, wait several minutes, then refresh. Requests can fail or remain unparseable; submitting one is not a guarantee. Refreshing a match updates its replay-room view. Click **Analyze my matches** again to rebuild the overview and coaching priorities with the updated cache.

To import data, save the complete JSON response from `https://api.opendota.com/api/matches/YOUR_MATCH_ID` and select **Import JSON**. A coach report export is a different format and cannot be imported as a match. A local import does not fetch OpenDota or submit your file to an AI model. To include it in an AI discussion, first load an overview report; chat always uses the overview currently displayed, not a separately opened replay-room match.

## How the recommendations work

These rules flag **review opportunities**, not proven errors or causes of losses. They are not trained on Divine players and do not claim to benchmark your MMR.

| Review signal | Eligible observations | Starter trigger | What to investigate |
| --- | --- | --- | --- |
| Survival | Matches with known deaths and duration | More than 2 deaths per 10 minutes | Could you avoid the death? Did a support sacrifice actually secure an objective or save? |
| First 10 minutes | Core-role samples with exact replay LH at 10 | Carry/mid below 50; offlane below 40 | Missed attacks, trades, lane equilibrium, matchup and recovery decisions |
| Vision | Support-role samples with observer wards placed | Fewer than 0.8 observers per 10 minutes | Vision for the next objective, ward quality and safety; count alone is insufficient |
| Objective conversion | Core-role games lasting at least 30 minutes | Under 1,000 personal tower damage | Missed safe objectives after won fights; hero/team duties may explain low damage |

The highest fractions of flagged/usable observations are shown first, with usable sample count breaking ties. “Early signal” is a small sample; “Repeated signal” has at least eight usable observations. These are descriptive labels, not statistical confidence intervals. If no rule qualifies, the app asks you to collect a baseline instead of inventing a mistake.

**Role matters.** Safe lane and offlane are lane assignments, not farm positions. Automatic mode only infers mid cautiously from lane data. A manually selected role is an assumption for **every match in that review**; if you played different roles, review individual matches using their actual roles. Farming and tower-damage targets are not applied to support-role matches.

Missing data is shown as `—` and excluded from the corresponding average or check. A real zero is preserved. Unknown results do not become losses. Matches under 10 minutes, non-ranked games, duplicates, and games with an abandon by this account are excluded. Disconnect-only status is retained. GPM is descriptive across the sample, not a universal target. “Gold earned” is not current net worth. Purchase times are not delivery or first-use times.

## Troubleshooting

| What you see | What to do |
| --- | --- |
| Python is missing | Install from python.org, tick **Add Python to PATH**, and reopen `run.bat`. Windows Store aliases can interfere; using the Python installer and its `py` launcher avoids this. |
| No ranked matches | Enable public match data, sign in once at [OpenDota](https://www.opendota.com/players/314758455), then play new ranked matches. Hidden historical matches might not become available. |
| OpenDota cannot be reached / denied | Check Internet access and whether your network allows `https://api.opendota.com`. The app will show the failure; it will not pretend sample data is yours. |
| Rate limit reached | Wait at least a minute before trying again. Don't repeatedly refresh multiple matches. Free API limits can change. |
| Replay fields unavailable | Request parsing for a recent match and refresh later. Old replays may have expired permanently. |
| Nothing happens when asking AI | Install/start Ollama and pull `llama3.2:3b`. The normal dashboard does not need it. Try again after the model has loaded. |
| Another copy is running / port busy | The launcher reopens a verified running coach, or picks another free local port if an unrelated service occupies 8765. Keep the original coach console open. An explicit `--port` never silently changes your requested port. |
| Imported match rejected | Use full OpenDota match JSON for a ranked game over 10 minutes. Your numeric account ID must be visible in its `players` array. |
| Older numbers remain visible | **Analyze my matches** and **Check OpenDota again** bypass this app's profile/history cache. OpenDota may still need time to update its public API. Match details stay cached for 24 hours; **Refresh match** bypasses the selected detail cache. Reanalyze to rebuild the overview. |

The local cache is `.local/opendota.sqlite3`. To clear it, stop the app and delete the `.local` folder. Checklist state is in your browser's local storage. The app is intentionally bound to `127.0.0.1`; do not expose it as a public website.

## Development and verification

Runtime dependencies: **Python standard library only**, 3.10+. From this folder:

```text
python server.py
python -m unittest discover -s tests -v
```

On Windows use `py -3` instead of `python` if needed. Tests use deterministic fixtures and mocked upstream responses; they do not require Internet or an AI model. They exercise coaching rules, HTTP integration, filtering, account ownership, caching, HTTPS requests, limits, and AI adapter behavior. A separate optional developer check, `python -m tests.browser_smoke`, needs Playwright and Chromium; it is not required for users. That browser runner defaults to `/usr/bin/chromium` in the cloud test environment.

All **55 automated tests** and the desktop/mobile browser checks passed for version 1.0.1, including no page jump, fresh-history retry, ranked recent-match fallback, and safe relaunch behavior. See `VALIDATION.md` for the exact live-data checks and what remains unverified. A separate public reference match also verified real replay-field compatibility; it was not treated as your match history.

**Validation boundary:** the app and browser flows were tested on Linux/Python 3.12, including desktop and mobile layouts. Windows batch execution and actual Ollama inference require testing on the user's Windows PC. Live OpenDota access was initially blocked by the cloud network allowlist; it became available after the configuration update. A live check identified **Tweety, Archon II**, but ranked, recent, and unfiltered match-history requests all returned **zero matches**. This verifies connectivity and the empty-history handling; it does not validate your personal gameplay or live replay analysis. Enable public match data, sign in to OpenDota, and let new matches become available. Private history is only one possible cause of an empty result; it has not been proven. The required `api.opendota.com` network rule and startup instructions are saved in the cloud configuration draft; draft saving is separate from publishing the final prepared filesystem. Ordinary Windows use relies on your own Internet connection.

### Files

- `server.py`: loopback-only HTTP server, static app and API routes.
- `coach/client.py`: fixed-host OpenDota requests, HTTPS verification, caching and pacing.
- `coach/analysis.py`: normalization, missing-data handling and explainable coaching.
- `coach/service.py`: player history, five-match enrichment and single-match import/review.
- `coach/ai.py`: optional fixed-localhost Ollama adapter.
- `static/`: responsive interface without CDNs or JavaScript dependencies.
- `tests/`: unit, HTTP and optional browser checks.
- `run.bat`: double-click Windows launcher.

## Data sources and attribution

OpenDota is a third-party service and is not affiliated with this app. API usage is subject to its current availability, quotas and terms. Endpoint shapes were checked against the [official OpenDota source](https://github.com/odota/core). Hero names are bundled from [odota/dotaconstants](https://github.com/odota/dotaconstants), under its MIT license; see `THIRD_PARTY_NOTICES.md`. New heroes without a bundled name appear as their numeric hero ID. Dota 2 and Steam are trademarks of Valve. This is an independent learning tool.
