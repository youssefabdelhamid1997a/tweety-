"use strict";

// This module never starts capture or model requests on page load.
(() => {
  const q = (selector) => document.querySelector(selector);
  const video = q("#live-preview");
  const MAX_FRAME_BYTES = 2_000_000;
  const MAX_CROP_BYTES = 700_000;
  const RESULT_MAX_AGE = 90;
  const SPEECH_MAX_AGE = 15;
  let stream = null;
  let generation = 0;
  let choosing = false;
  let inFlight = false;
  let periodic = false;
  let timer = null;
  let ageTimer = null;
  let speechTimer = null;
  let controller = null;
  let cancelFrameWait = null;
  let lastCaptureTime = null;
  let resultTime = null;

  function status(text) { q("#live-status").textContent = text; }
  function error(text = "") { q("#live-error").textContent = text; q("#live-error").hidden = !text; }
  function track() { return stream?.getVideoTracks()[0]; }
  function syncControls() {
    const sharing = Boolean(stream && track()?.readyState === "live");
    q("#live-start").disabled = choosing || sharing;
    q("#live-once").disabled = !sharing || inFlight || periodic;
    q("#live-periodic").disabled = !sharing || (inFlight && !periodic);
    q("#live-periodic").textContent = periodic ? "Pause periodic checks" : "Start periodic checks";
    q("#live-stop").disabled = !(sharing || choosing || inFlight);
    q("#live-hero").disabled = inFlight;
    q("#live-role").disabled = inFlight;
    q("#live-minimap").disabled = inFlight;
    q("#live-preview-wrap").hidden = !sharing;
  }

  function cancelSpeech() {
    clearTimeout(speechTimer);
    speechTimer = null;
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  }

  function clearResult() {
    clearInterval(ageTimer);
    ageTimer = null;
    resultTime = null;
    q("#live-result").hidden = true;
    q("#live-result").removeAttribute("data-stale");
    ["#live-observation", "#live-advice", "#live-uncertainty", "#live-result-age", "#live-result-meta"].forEach((selector) => { q(selector).textContent = ""; });
  }

  function pausePeriodic(message) {
    periodic = false;
    clearTimeout(timer);
    timer = null;
    if (message) status(message);
    syncControls();
  }

  function stopSharing(message = "Sharing stopped. No further snapshots will be sent.") {
    generation += 1;
    periodic = false;
    choosing = false;
    inFlight = false;
    clearTimeout(timer);
    timer = null;
    controller?.abort();
    controller = null;
    cancelFrameWait?.();
    cancelFrameWait = null;
    const oldStream = stream;
    stream = null;
    oldStream?.getTracks().forEach((item) => item.stop());
    video.pause();
    video.srcObject = null;
    video.load();
    lastCaptureTime = null;
    q("#live-source").textContent = "";
    clearResult();
    cancelSpeech();
    status(message);
    syncControls();
  }

  async function startSharing() {
    if (choosing || stream) return;
    error();
    if (!navigator.mediaDevices?.getDisplayMedia) {
      error("Screen sharing is unavailable here. Open the coach using its local address in desktop Chrome or Edge, then choose your Dota window.");
      return;
    }
    const mine = ++generation;
    choosing = true;
    clearResult();
    status("Choose the Dota window in your browser's sharing dialog. Sharing alone will not send a snapshot to the model.");
    syncControls();
    let selected = null;
    try {
      selected = await navigator.mediaDevices.getDisplayMedia({video: {displaySurface: "window", frameRate: {ideal: 2, max: 5}}, audio: false, selfBrowserSurface: "exclude"});
      if (mine !== generation) { selected.getTracks().forEach((item) => item.stop()); return; }
      if (!selected.getVideoTracks().length) throw new Error("No screen video track was selected. Choose the Dota window and try again.");
      stream = selected;
      video.srcObject = selected;
      await video.play();
      if (mine !== generation) return;
      track().addEventListener("ended", () => { if (mine === generation) stopSharing("Your browser ended sharing. No further snapshots will be sent."); }, {once: true});
      track().addEventListener("mute", () => {
        if (mine === generation) {
          pausePeriodic("The shared source is paused or unavailable. Restore its window, then request a new check.");
          cancelSpeech();
        }
      });
      q("#live-source").textContent = `Selected source: ${track().label || "screen video"}. Check that the preview shows your Dota window. No audio is captured.`;
      status("Sharing preview is ready. Click Analyze one snapshot, or explicitly start periodic checks. Keep this coach tab open while playing.");
    } catch (failure) {
      if (mine !== generation) return;
      selected?.getTracks().forEach((item) => item.stop());
      stream = null;
      video.srcObject = null;
      const denied = ["NotAllowedError", "AbortError"].includes(failure.name);
      error(denied ? "Screen sharing was cancelled or denied. Nothing was sent. Click Choose Dota window to try again." : failure.message || "The chosen screen could not be shared. Try Dota in borderless window mode and choose its window again.");
      status("Not sharing. No snapshots are being sent.");
    } finally {
      if (mine === generation) { choosing = false; syncControls(); }
    }
  }

  function waitForNewFrame(mine) {
    // The coach must keep working when Dota is in front. Background tabs may
    // suspend compositor callbacks even while the shared MediaStream advances.
    // Track state and currentTime are still checked before each snapshot.
    if (document.hidden || typeof video.requestVideoFrameCallback !== "function") return Promise.resolve();
    const baseline = video.currentTime;
    return new Promise((resolve, reject) => {
      let callback;
      let timeout;
      let settled = false;
      const finish = (failure) => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        if (callback !== undefined) video.cancelVideoFrameCallback?.(callback);
        cancelFrameWait = null;
        failure ? reject(failure) : resolve();
      };
      callback = video.requestVideoFrameCallback(() => mine === generation ? finish() : finish(new DOMException("Sharing stopped", "AbortError")));
      timeout = setTimeout(() => video.currentTime > baseline
        ? finish()
        : finish(new Error("The selected source is not producing fresh frames. Restore the Dota window and try borderless window mode.")), 3000);
      cancelFrameWait = () => finish(new DOMException("Sharing stopped", "AbortError"));
    });
  }

  function jpeg(canvas, maximum) {
    const encoded = canvas.toDataURL("image/jpeg", 0.74).split(",")[1];
    if (!encoded || Math.ceil(encoded.length * 3 / 4) > maximum) throw new Error("The snapshot was unexpectedly large. Choose the Dota window rather than an entire high-resolution desktop.");
    return encoded;
  }

  async function snapshot(mine) {
    if (!track() || track().readyState !== "live" || !track().enabled || track().muted || video.paused) throw new Error("The selected source is paused or unavailable. Restore its window before checking it.");
    await waitForNewFrame(mine);
    if (mine !== generation || !stream) throw new DOMException("Sharing stopped", "AbortError");
    const width = video.videoWidth, height = video.videoHeight;
    if (video.readyState < 2 || !width || !height || track().muted) throw new Error("The source has no usable video frame yet. Keep the Dota window visible and try again.");
    if (lastCaptureTime !== null && video.currentTime <= lastCaptureTime) throw new Error("The selected video frame has not advanced. Restore the Dota window and request a new check.");
    const scale = Math.min(1, 1280 / Math.max(width, height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(width * scale));
    canvas.height = Math.max(1, Math.round(height * scale));
    const context = canvas.getContext("2d", {willReadFrequently: true});
    if (!context) throw new Error("This browser could not prepare a screen snapshot.");
    const sourceTime = video.currentTime;
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const capturedAt = Date.now() / 1000;
    let crop = null;
    try {
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
      let brightest = 0;
      for (let i = 0; i < pixels.length; i += 128) brightest = Math.max(brightest, pixels[i], pixels[i + 1], pixels[i + 2]);
      if (brightest < 12) throw new Error("The preview is nearly black. Switch Dota to borderless window mode, restore its window, and choose the source again.");
      const data = {image: jpeg(canvas, MAX_FRAME_BYTES), captured_at: capturedAt, hero: q("#live-hero").value.trim().slice(0, 80), role: q("#live-role").value};
      const corner = q("#live-minimap").value;
      if (corner !== "off") {
        const size = Math.min(canvas.width, Math.round(canvas.height * 0.25));
        crop = document.createElement("canvas");
        crop.width = crop.height = 512;
        const cropContext = crop.getContext("2d");
        if (!cropContext) throw new Error("This browser could not prepare the optional minimap crop.");
        // Both JPEGs are derived from the exact same retained frame, even if the
        // live video advances while encoding or preparing the optional crop.
        cropContext.drawImage(canvas, corner === "right" ? canvas.width - size : 0, canvas.height - size, size, size, 0, 0, crop.width, crop.height);
        data.minimap = jpeg(crop, MAX_CROP_BYTES);
      }
      lastCaptureTime = sourceTime;
      return data;
    } finally {
      canvas.width = canvas.height = 1;
      if (crop) crop.width = crop.height = 1;
    }
  }

  function updateAge() {
    if (resultTime === null) return;
    const age = Math.max(0, Math.floor(Date.now() / 1000 - resultTime));
    const stale = age > RESULT_MAX_AGE;
    q("#live-result-age").textContent = stale ? "Snapshot expired · request a new check" : `Frame captured ${age} seconds ago`;
    q("#live-result").dataset.stale = String(stale);
    q("#live-result-details").hidden = stale;
    if (stale) cancelSpeech();
  }

  function localVoices() {
    return "speechSynthesis" in window ? window.speechSynthesis.getVoices().filter((voice) => voice.localService === true) : [];
  }

  function updateVoices() {
    const available = localVoices().length > 0;
    q("#live-speak").disabled = !available;
    if (!available) q("#live-speak").checked = false;
    q("#live-speech-note").textContent = available
      ? "A local voice is available. Only game-visible advice from a frame at most 15 seconds old is read aloud."
      : "No installed local voice is available in this browser yet. Text suggestions still work; no remote voice is used.";
  }

  function renderResult(result, capturedAt) {
    if (!result || typeof result !== "object" || !["game_visible", "unclear", "not_game"].includes(result.screen_status)) throw new Error("The local model returned an unexpected result. Please try another snapshot.");
    for (const field of ["observation", "advice", "uncertainty"]) if (typeof result[field] !== "string") throw new Error("The local model returned an incomplete review. Please try again.");
    if (!Number.isFinite(result.captured_at) || Math.abs(result.captured_at - capturedAt) > 1) throw new Error("The returned review did not match the requested snapshot. It was discarded.");
    const age = Date.now() / 1000 - capturedAt;
    if (age > RESULT_MAX_AGE || age < -5) throw new Error("The model's reply arrived too late for this snapshot. It was discarded; try another check when the model is ready.");
    clearInterval(ageTimer);
    resultTime = capturedAt;
    q("#live-result-title").textContent = result.screen_status === "game_visible" ? "Latest snapshot review" : "Screen context is unclear";
    q("#live-result-meta").textContent = `Local model: ${String(result.model || "gemma3:4b").slice(0, 80)} · ${Number.isFinite(result.latency_seconds) ? result.latency_seconds.toFixed(1) + " seconds to process" : "processing time unavailable"} · ${q("#live-minimap").value === "off" ? "full frame only" : "full frame + selected bottom-corner crop"}`;
    q("#live-observation").textContent = result.observation;
    q("#live-advice").textContent = result.advice;
    q("#live-uncertainty").textContent = result.uncertainty;
    q("#live-result").hidden = false;
    updateAge();
    ageTimer = setInterval(updateAge, 1000);
    if (q("#live-speak").checked && result.screen_status === "game_visible" && age <= SPEECH_MAX_AGE) {
      const voices = localVoices();
      const voice = voices.find((candidate) => candidate.lang.toLowerCase().startsWith("en")) || voices[0];
      if (voice && result.advice.trim()) {
        cancelSpeech();
        const utterance = new SpeechSynthesisUtterance(result.advice.slice(0, 500));
        utterance.voice = voice;
        utterance.lang = voice.lang;
        utterance.rate = 1.05;
        window.speechSynthesis.speak(utterance);
        speechTimer = setTimeout(cancelSpeech, Math.max(0, (SPEECH_MAX_AGE - age) * 1000));
      }
    }
  }

  function schedule() {
    clearTimeout(timer);
    if (!periodic || !stream) return;
    const seconds = Math.max(30, Number(q("#live-interval").value) || 30);
    status(`Periodic checks are on. Next snapshot in at least ${seconds} seconds; browser background timing can be slower. Stop sharing ends capture.`);
    timer = setTimeout(() => { timer = null; if (periodic && stream) analyze(); }, seconds * 1000);
  }

  async function analyze() {
    if (inFlight || !stream) return;
    const mine = generation;
    inFlight = true;
    error();
    syncControls();
    status("Preparing a fresh snapshot, then asking local gemma3:4b. A check may take up to a minute; another check will not overlap it.");
    const pending = new AbortController();
    controller = pending;
    const timeout = setTimeout(() => pending.abort(), 75000);
    try {
      const data = await snapshot(mine);
      if (mine !== generation || pending.signal.aborted) return;
      const response = await fetch("/api/live/analyze", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data), signal: pending.signal});
      let result;
      try { result = await response.json(); } catch { throw new Error("The local coach returned an unreadable response. Restart it and try again."); }
      if (mine !== generation || pending.signal.aborted) return;
      if (!response.ok) throw new Error(typeof result.error === "string" ? result.error : `Live review failed (${response.status}).`);
      renderResult(result, data.captured_at);
      status("Snapshot review is ready below. Its capture age is shown; it may not describe the current situation.");
    } catch (failure) {
      if (mine !== generation) return;
      pausePeriodic();
      cancelSpeech();
      error(failure.name === "AbortError" ? "The check timed out. Nothing will be queued automatically. Check Ollama, then try Analyze one snapshot again." : failure.message || "The local screen review could not finish. Check Ollama and try again.");
      status("Sharing preview remains active; periodic checks are paused. You can retry or stop sharing.");
    } finally {
      clearTimeout(timeout);
      if (mine === generation) {
        inFlight = false;
        controller = null;
        syncControls();
        if (periodic) schedule();
      }
    }
  }

  q("#live-start").addEventListener("click", startSharing);
  q("#live-once").addEventListener("click", analyze);
  q("#live-stop").addEventListener("click", () => stopSharing());
  q("#live-periodic").addEventListener("click", () => {
    if (periodic) { pausePeriodic("Periodic checks paused. Sharing preview remains active; no further checks will be scheduled."); cancelSpeech(); return; }
    if (!stream || inFlight) return;
    periodic = true;
    syncControls();
    analyze();
  });
  q("#live-interval").addEventListener("change", () => { if (periodic && !inFlight) schedule(); });
  q("#live-speak").addEventListener("change", () => { if (!q("#live-speak").checked) cancelSpeech(); });
  if ("speechSynthesis" in window) window.speechSynthesis.addEventListener?.("voiceschanged", updateVoices);
  window.addEventListener("pagehide", () => stopSharing("Sharing stopped because this page closed."));
  updateVoices();
  syncControls();
})();
