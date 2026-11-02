"use strict";

const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const fmt = (value, digits = 0) => typeof value === "number" && Number.isFinite(value) ? value.toLocaleString(undefined, {maximumFractionDigits: digits}) : "—";
const clock = (seconds) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
const date = (stamp) => typeof stamp === "number" ? new Date(stamp * 1000).toLocaleDateString(undefined, {month: "short", day: "numeric", year: "numeric"}) : "Date unavailable";
let report = null;
let review = null;
let isBusy = false;

function message(text, error = false) {
  const target = $(error ? "#error" : "#status");
  target.textContent = text;
  target.hidden = !text;
  if (error && text) target.scrollIntoView({block: "center", behavior: "smooth"});
}

function setBusy(value, text = "") {
  isBusy = value;
  document.querySelectorAll("button, #import-file").forEach((el) => { el.disabled = value; });
  $("#connect-form").setAttribute("aria-busy", String(value));
  $("#status").classList.toggle("loading", value);
  message(text);
}

async function request(path, data) {
  const response = await fetch(path, data === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)});
  let result;
  try { result = await response.json(); } catch { throw new Error("The local server returned an unreadable response. Restart run.bat and try again."); }
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status}).`);
  return result;
}

async function task(text, work) {
  if (isBusy) return;
  message("", true);
  setBusy(true, text);
  try { await work(); }
  catch (error) { message(error.message || "Could not connect to the local app. Keep the Python window open and try again.", true); }
  finally { setBusy(false); }
}

function formData() {
  return {account: $("#account").value.trim(), role: $("#role").value, limit: Number($("#limit").value)};
}

function chart(points, label, suffix = "") {
  const valid = points.filter((p) => Number.isFinite(p.y));
  if (!valid.length) return '<p class="subtle">No numeric observations available for this chart.</p>';
  const width = 850, height = 150, left = 48, right = 22, top = 15, bottom = 28;
  const maximum = Math.max(100, ...valid.map((p) => p.y)) * 1.12;
  const x = (i) => left + i * (width - left - right) / Math.max(points.length - 1, 1);
  const y = (v) => height - bottom - v / maximum * (height - top - bottom);
  const grids = [0, .5, 1].map((fraction) => `<line class="chart-grid" x1="${left}" x2="${width - right}" y1="${y(maximum * fraction)}" y2="${y(maximum * fraction)}"/><text class="chart-axis" x="0" y="${y(maximum * fraction) + 4}">${fmt(maximum * fraction)}</text>`).join("");
  // Separate segments at missing values instead of drawing invented data between them.
  const paths = [];
  let segment = [];
  points.forEach((p, i) => {
    if (Number.isFinite(p.y)) segment.push(`${x(i)},${y(p.y)}`);
    else if (segment.length) { paths.push(segment.join(" ")); segment = []; }
  });
  if (segment.length) paths.push(segment.join(" "));
  const dots = points.map((p, i) => Number.isFinite(p.y) ? `<circle cx="${x(i)}" cy="${y(p.y)}" r="3.3" fill="#a9efc5"><title>${esc(p.label)}: ${fmt(p.y)}${esc(suffix)}</title></circle>` : "").join("");
  return `<svg class="trend-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(label)}"><title>${esc(label)}</title>${grids}${paths.map((p) => `<polyline class="chart-line" points="${p}"/>`).join("")}${dots}<text class="chart-axis" x="${left}" y="${height - 3}">${esc(points[0]?.axis || "Oldest")}</text><text class="chart-axis" x="${width - right}" y="${height - 3}" text-anchor="end">${esc(points.at(-1)?.axis || "Newest")}</text></svg>`;
}

function renderReport(data) {
  report = data;
  $("#ai-answer").textContent = "";
  $("#ai-answer").hidden = true;
  review = null;
  $("#review-output").hidden = true;
  $("#empty-state").hidden = true;
  $("#dashboard").hidden = false;
  const sample = data.source === "demo";
  const badge = $("#source-badge");
  badge.className = `badge ${sample ? "sample" : "live"}`;
  badge.textContent = sample ? "SAMPLE DATA · not your matches" : data.source === "import" ? "Imported match JSON" : "OpenDota · live connection";
  $("#report-title").textContent = `${data.name} / ${sample ? "Sample overview" : "Your match overview"}`;
  $("#report-subtitle").textContent = sample ? "SYNTHETIC DEMONSTRATION · NOT A PERSONAL ANALYSIS" : "YOUR RANKED SNAPSHOT";
  $("#report-meta").textContent = `${data.rank}${data.rank_stars ? ` ${data.rank_stars}★` : ""} · ${data.summary.matches} eligible matches · ${data.role_label} · Generated ${new Date(data.generated_at).toLocaleString()}`;
  $("#warnings").innerHTML = data.warnings.map((w) => `<li>${esc(w)}</li>`).join("");
  $("#notes-summary").textContent = `${sample ? "Sample data — " : ""}Data coverage & limitations (${data.warnings.length} notes)`;
  $("#data-notes").open = sample || !data.summary.matches;
  const s = data.summary;
  const metrics = [
    ["WIN RATE", s.win_rate === null ? "—" : `${fmt(s.win_rate, 1)}<small>%</small>`, `${s.wins} wins / ${s.losses} losses · ${s.known_results} known results`, "↗"],
    ["DEATHS / 10 MIN", fmt(s.deaths_per_10, 1), `Across ${s.death_samples} observed matches`, "◷"],
    ["AVG GOLD / MIN", fmt(s.gold_per_min), `${s.gold_samples} observations · role-dependent`, "◇"],
    ["REPLAY COVERAGE", `${s.parsed}<small> / ${s.matches}</small>`, "Matches with parsed event data", "▤"]
  ];
  $("#metrics").innerHTML = metrics.map(([title, value, note, icon]) => `<article class="metric"><div class="metric-label">${title}<span aria-hidden="true">${icon}</span></div><div class="metric-value">${value}</div><p class="metric-note">${esc(note)}</p></article>`).join("");
  $("#priorities").innerHTML = data.priorities.map((p, i) => `<article class="focus-card"><div class="focus-top"><div class="focus-kicker"><span class="focus-number">FOCUS / 0${i + 1}</span><span class="signal">${esc(p.confidence)}</span></div><h3>${esc(p.title)}</h3><p class="evidence">${esc(p.evidence)}</p><p>${esc(p.action)}</p>${p.match_ids.length ? `<div class="focus-links">Review evidence: ${p.match_ids.map((id) => `<button class="review-link" data-review="${esc(id)}" type="button">#${esc(id)}</button>`).join(" · ")}</div>` : ""}</div><div class="focus-bottom"><span>YOUR NEXT EXERCISE</span><p>${esc(p.target)}</p></div></article>`).join("");
  $("#trend-chart").innerHTML = chart([...data.matches].reverse().map((m) => ({y: m.gold_per_min, label: `${m.hero} · ${date(m.start_time)}`})), "Gold per minute by match, oldest to newest. Exact values are in the match table.", " GPM");
  $("#result-filter").value = "all";
  renderTable();
  renderPractice();
}

function renderTable() {
  if (!report) return;
  const filter = $("#result-filter").value;
  const rows = report.matches.filter((m) => filter === "all" || (filter === "wins" ? m.won === true : m.won === false));
  $("#matches").innerHTML = rows.length ? rows.map((m) => `<tr><td><div class="hero-cell"><span class="hero-avatar" aria-hidden="true">${esc(m.hero.split(" ").map((v) => v[0]).slice(0, 2).join(""))}</span><div><strong>${esc(m.hero)}</strong><small>${esc(date(m.start_time))} · ${clock(m.duration)}</small></div></div></td><td><span class="result ${m.won === false ? "loss" : m.won === null ? "unknown" : ""}">${m.won === null ? "Unknown" : m.won ? "WIN" : "LOSS"}</span></td><td>${fmt(m.kills)} / ${fmt(m.deaths)} / ${fmt(m.assists)}</td><td>${fmt(m.gold_per_min)}</td><td>${fmt(m.last_hits_10)}</td><td><span class="replay-tag ${m.parsed ? "available" : ""}">${m.parsed ? "● Events" : "○ Not loaded"}</span></td><td><button class="review-link" type="button" data-review="${esc(m.match_id)}">Review ↗<span class="sr-only"> match ${esc(m.match_id)}</span></button></td></tr>`).join("") : '<tr><td colspan="7">No matches in this filter.</td></tr>';
  $("#table-note").textContent = `${rows.length} shown · Filters only affect this table. Summary and chart use all ${report.matches.length} eligible matches. — means unavailable, never zero.`;
}

function renderPractice() {
  if (!report) return;
  const exercises = report.priorities.map((p) => ({key: p.key, text: p.target}));
  exercises.push({key: "reflection", text: "After 5 games, compare my notes and choose one habit to keep practicing."});
  $("#practice-list").innerHTML = exercises.map((item) => `<label class="practice-item"><input type="checkbox" data-practice="${esc(item.key)}"><span>${esc(item.text)}</span></label>`).join("");
  document.querySelectorAll("[data-practice]").forEach((input) => {
    const key = `dota-ascent:v1:${report.source === "demo" ? "demo" : report.account_id}:${report.role}:${input.dataset.practice}`;
    try { input.checked = localStorage.getItem(key) === "done"; } catch { /* Storage may be disabled. The checklist still works in memory. */ }
    input.addEventListener("change", () => {
      try { localStorage.setItem(key, input.checked ? "done" : "todo"); } catch { /* No personal data is sent to a server. */ }
    });
  });
}

function renderReview(match, data) {
  review = {match, data};
  const sample = data.source === "demo";
  const panel = $("#review-output");
  const knownRole = match.role === "unknown" ? "Role not inferred" : `Assumed role: ${match.role.replaceAll("_", " ")}`;
  panel.hidden = false;
  const labels = [["K / D / A", `${fmt(match.kills)} / ${fmt(match.deaths)} / ${fmt(match.assists)}`], ["GPM", fmt(match.gold_per_min)], ["LH AT 10", fmt(match.last_hits_10)], ["KILL PARTICIPATION", match.kill_participation === null ? "—" : `${fmt(match.kill_participation, 1)}%`], ["OBS PLACED", fmt(match.obs_placed)]];
  panel.innerHTML = `<div class="review-top"><div><div class="eyebrow">${sample ? "SAMPLE MATCH · NOT YOUR GAME" : data.source === "import" ? "IMPORTED OPENDOTA JSON" : "OPENDOTA MATCH REVIEW"}</div><h3>${esc(match.hero)} <span class="subtle">#${esc(match.match_id)}</span></h3><p>${esc(date(match.start_time))} · ${clock(match.duration)} · ${match.won === null ? "Unknown result" : match.won ? "Win" : "Loss"} · ${esc(knownRole)}</p></div><div class="review-actions">${!sample && data.source !== "import" ? '<button id="refresh-match" class="secondary" type="button">Refresh match</button>' : ""}${!sample ? `<a class="secondary" href="https://www.opendota.com/matches/${esc(match.match_id)}" target="_blank" rel="noopener noreferrer">OpenDota ↗</a>` : ""}</div></div>${!match.parsed ? `<p class="replay-hint">Parsed replay events are not loaded. Summary stats alone cannot provide a replay timeline.${!sample && data.source !== "import" ? ' <button id="parse-match" class="text-button" type="button">Request OpenDota parse →</button>' : ""}</p>` : ""}<dl class="review-stats">${labels.map(([key, value]) => `<div><dt>${key}</dt><dd>${value}</dd></div>`).join("")}</dl><div class="review-content"><div><h4>Gold earned over time · not current net worth</h4>${chart(match.economy.map((p) => ({y: p.gold, label: `${p.minute} min`, axis: `${p.minute} min`})), "Cumulative gold earned over game time.", " gold")}<p class="subtle">LH at 10 uses an exact 10-minute replay sample. — means unavailable.</p></div><div><h4>Selected completed-item purchase events</h4>${match.purchases.length ? `<ol class="item-timeline">${match.purchases.map((p) => `<li><time>${clock(p.time)}</time><span>${esc(p.item)}</span></li>`).join("")}</ol>` : '<p class="subtle">No supported item events loaded. This is not evidence that no items were bought.</p>'}<p class="subtle">Purchase time is not delivery or first-use time. No item is universally mandatory.</p></div></div><div class="review-prompt"><strong>In-game replay checklist</strong><br>1. At 10:00: which creeps did you miss, and why?<br>2. Before each of your first 3 deaths: what threats were visible and what did your team gain?<br>3. After your first major item: did you use the timing for safe farm or a favorable objective?<br><br>These are review prompts. The API does not provide a full judgment of your positioning or decision quality.</div>`;
  if ($("#refresh-match")) $("#refresh-match").addEventListener("click", () => loadSpecific(match.match_id, true, data.account_id, data.role));
  if ($("#parse-match")) $("#parse-match").addEventListener("click", () => task("Sending one replay-parse request to OpenDota…", async () => {
    const result = await request("/api/parse", {match_id: match.match_id});
    $("#parse-match").textContent = "Parse requested";
    $("#parse-match").hidden = true;
    const note = document.createElement("p");
    note.className = "replay-hint";
    note.textContent = result.message;
    panel.prepend(note);
  }));
  panel.scrollIntoView({behavior: "smooth", block: "start"});
}

function loadSpecific(id, refresh = false, account, role) {
  return task(refresh ? "Refreshing this match from OpenDota…" : "Loading this match from OpenDota…", async () => {
    const data = await request("/api/match", {...formData(), ...(account ? {account} : {}), ...(role ? {role} : {}), match_id: id, refresh});
    renderReview(data.matches[0], data);
  });
}

$("#connect-form").addEventListener("submit", (event) => {
  event.preventDefault();
  task("Reading ranked history and up to 5 detailed matches. This may take a minute. Your previous report stays visible until the new one succeeds…", async () => {
    renderReport(await request("/api/analyze", formData()));
    $("#dashboard").scrollIntoView({behavior: "smooth", block: "start"});
  });
});
$("#demo-button").addEventListener("click", () => task("Loading clearly labeled synthetic sample matches…", async () => {
  const role = $("#role").value === "auto" ? "carry" : $("#role").value;
  renderReport(await request(`/api/demo?role=${encodeURIComponent(role)}`));
  $("#dashboard").scrollIntoView({behavior: "smooth", block: "start"});
}));
$("#result-filter").addEventListener("change", renderTable);
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-review]");
  if (button && report) {
    const match = report.matches.find((m) => String(m.match_id) === button.dataset.review);
    if (match) renderReview(match, report);
  }
});
$("#review-form").addEventListener("submit", (event) => {
  event.preventDefault();
  loadSpecific($("#match-id").value.trim());
});
$("#import-file").addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (!file) return;
  task("Reading OpenDota JSON locally…", async () => {
    if (file.size > 8_000_000) throw new Error("Choose a match JSON file smaller than 8 MB.");
    let match;
    try { match = JSON.parse(await file.text()); } catch { throw new Error("This is not valid JSON. Import the full OpenDota /matches/{match_id} response, not a .dem file or an exported coaching report."); }
    const result = await request("/api/import", {...formData(), match});
    renderReview(result.matches[0], result);
  }).finally(() => { event.target.value = ""; });
});
$("#export-button").addEventListener("click", () => {
  if (!report) return;
  const blob = new Blob([JSON.stringify(report, null, 2)], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `dota-ascent-${report.source === "demo" ? "SAMPLE" : report.account_id}-${new Date().toISOString().slice(0, 10)}.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$("#ai-form").addEventListener("submit", (event) => {
  event.preventDefault();
  task("Asking your local Ollama model. On a CPU, the first answer can take up to two minutes…", async () => {
    if (!report) throw new Error("Analyze your matches or load sample data before asking the coach.");
    const result = await request("/api/ask", {report, question: $("#ai-question").value.trim()});
    const answer = $("#ai-answer");
    answer.textContent = `${result.source === "demo" ? "SAMPLE DATA DISCUSSION · NOT YOUR MATCHES\n\n" : ""}LOCAL AI · ${result.model} · Verify against your replay\n\n${result.answer}`;
    answer.hidden = false;
    answer.scrollIntoView({behavior: "smooth", block: "center"});
  });
});
document.querySelectorAll("nav a").forEach((link) => link.addEventListener("click", () => {
  document.querySelectorAll("nav a").forEach((a) => a.classList.remove("active"));
  link.classList.add("active");
}));
