"use strict";
const DEFAULT_SERVER = "http://127.0.0.1:5050";
const $ = (id) => document.getElementById(id);

let server = DEFAULT_SERVER;
let tab = null;
let lastPayload = null;   // what we sent for analysis (reused for comparison)
let lastReport = null;

/* Small DOM helper: page text is untrusted, so nothing is inserted with innerHTML. */
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v; else if (k === "text") el.textContent = v; else el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}

/* ---------- storage ---------- */
const store = {
  get: (key) => new Promise((res) => chrome.storage.local.get(key, (o) => res(o[key]))),
  set: (key, value) => new Promise((res) => chrome.storage.local.set({ [key]: value }, res)),
};

/* ---------- status helpers ---------- */
function showStatus(el, msg, type = "info", fix = "") {
  el.replaceChildren(msg, fix ? h("span", { class: "fix", text: fix }) : "");
  el.className = "status " + type;
}
function hide(el) { el.classList.add("hidden"); }
function show(el) { el.classList.remove("hidden"); }

/* ---------- talking to the backend ---------- */
class BackendError extends Error {
  constructor(message, fix) { super(message); this.fix = fix || ""; }
}

async function api(path, options = {}, timeoutMs = 90000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  let res;
  try {
    res = await fetch(server + path, { ...options, signal: ctrl.signal,
      headers: { "Content-Type": "application/json" } });
  } catch (e) {
    if (e.name === "AbortError") throw new BackendError("The backend took too long to answer.", "Long policies can take up to a minute. Try again.");
    throw new BackendError("Cannot reach the ClauseGuard backend.", "Start it with: python src/dashboard.py   (then open this popup again)");
  } finally {
    clearTimeout(timer);
  }
  let body = null;
  try { body = await res.json(); } catch (e) { /* not JSON */ }
  if (!res.ok) {
    if (body && body.error) throw new BackendError(body.error);
    if (res.status === 403 || res.status === 404 || !body) {
      throw new BackendError(`Something on ${new URL(server).host} answered with HTTP ${res.status}, but it is not ClauseGuard.`,
        "On a Mac, port 5000 is used by AirPlay Receiver. Use port 5050: restart the backend and set the address in settings (the gear icon).");
    }
    throw new BackendError(`The backend returned HTTP ${res.status}.`);
  }
  return body;
}

async function checkConnection() {
  const el = $("conn");
  try {
    const r = await fetch(server + "/api/health", { signal: AbortSignal.timeout(2500) });
    const body = await r.json().catch(() => null);
    if (r.ok && body && body.app === "ClauseGuard") {
      el.textContent = "Connected"; el.className = "conn ok"; return true;
    }
    el.textContent = "Wrong app on this port"; el.className = "conn bad";
    showStatus($("status"), `Something other than ClauseGuard is answering on ${new URL(server).host}.`, "error",
      "On a Mac, port 5000 is used by AirPlay Receiver. Start ClauseGuard on port 5050 and set the address in settings.");
  } catch (e) {
    el.textContent = "Backend not running"; el.className = "conn bad";
    showStatus($("status"), "The ClauseGuard backend is not running.", "error",
      "Start it with: python src/dashboard.py   Then reopen this popup.");
  }
  return false;
}

/* ---------- settings ---------- */
$("settings-btn").onclick = () => $("settings").classList.toggle("hidden");
$("server-save").onclick = async () => {
  let v = $("server").value.trim().replace(/\/+$/, "");
  if (!/^https?:\/\//.test(v)) v = "http://" + v;
  try {
    const u = new URL(v);
    if (!["127.0.0.1", "localhost"].includes(u.hostname)) throw new Error();
    server = u.origin;
  } catch (e) {
    showStatus($("status"), "Use a local address such as http://127.0.0.1:5050.", "error"); show($("status")); return;
  }
  await store.set("server", server);
  $("server").value = server;
  hide($("status"));
  checkConnection();
};

/* ---------- page info ---------- */
const PRIVACY_RE = /privacy|data[- ]policy|data[- ]protection/i;
const TERMS_RE = /terms|conditions|legal|tos\b/i;
function pageKind(t) {
  const probe = `${t.url || ""} ${t.title || ""}`;
  if (PRIVACY_RE.test(probe)) return "privacy policy page";
  if (TERMS_RE.test(probe)) return "terms page";
  return "";
}

/* ---------- analyze ---------- */
function getTab() {
  return new Promise((res) => chrome.tabs.query({ active: true, currentWindow: true }, (t) => res(t[0])));
}
function injectAndExtract(tabId) {
  return new Promise((resolve, reject) => {
    chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] }, () => {
      if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
      chrome.tabs.sendMessage(tabId, { action: "extract_text" }, (response) => {
        if (chrome.runtime.lastError || !response) return reject(new Error("Could not read this page. Refresh it and try again."));
        resolve(response);
      });
    });
  });
}

$("analyze-btn").onclick = async () => {
  const btn = $("analyze-btn");
  btn.disabled = true; hide($("results")); hide($("verdict"));
  try {
    if (!tab || !tab.url || !/^https?:/.test(tab.url)) throw new BackendError("Open a website first, then click ClauseGuard.");
    if (!(await checkConnection())) return;

    showStatus($("status"), "Reading the page…", "info"); show($("status"));
    let payload;
    const looksLikePolicy = pageKind(tab);
    if (looksLikePolicy) {
      const page = await injectAndExtract(tab.id);
      if (!page.text || page.text.length < 200) throw new BackendError("This page has too little text to analyse.");
      payload = { url: tab.url, text: page.text, title: page.title, include_terms: true, add_to_dashboard: true };
    } else {
      // A normal page: let the backend find this site's privacy policy and terms itself.
      payload = { url: tab.url, add_to_dashboard: true };
    }

    showStatus($("status"), looksLikePolicy
      ? "Summarizing the policy and its terms and conditions…"
      : "Finding this site's privacy policy and terms, then summarizing them…", "info");
    let report;
    try {
      report = await api("/api/summarize", { method: "POST", body: JSON.stringify(payload) });
    } catch (e) {
      if (!looksLikePolicy && e instanceof BackendError && !e.fix) {
        // The backend could not fetch the site (blocked or needs JavaScript): use this page's own text instead.
        const page = await injectAndExtract(tab.id);
        if (page.text && page.text.length >= 200) {
          payload = { url: tab.url, text: page.text, title: page.title, include_terms: true, add_to_dashboard: true };
          report = await api("/api/summarize", { method: "POST", body: JSON.stringify(payload) });
        } else throw e;
      } else throw e;
    }
    lastPayload = payload;
    await store.set("cache:" + new URL(tab.url).origin, { report, payload, at: Date.now() });
    hide($("status"));
    render(report, null);
    if (report.on_dashboard) {
      showStatus($("dash-note"), `${report.service_name} is on your dashboard. Summarize another site, then open the dashboard and click Compare.`, "success"); show($("dash-note"));
    }
  } catch (e) {
    showStatus($("status"), e.message, "error", e.fix || "");
    show($("status"));
  } finally {
    btn.disabled = false;
  }
};

/* ---------- render ---------- */
const fmt = (n, d = 0) => Number(n).toFixed(d);

function render(r, cachedAt) {
  lastReport = r;
  show($("results"));
  $("rating").textContent = fmt(r.rating);
  const band = $("band"); band.textContent = r.band; band.className = "band " + r.band.split(" ")[0];
  $("gauge-fill").style.width = r.rating + "%";
  $("tldr").textContent = r.summary.tldr;
  const modeText = r.mode && r.mode.startsWith("MOCK")
    ? "Demo mode: scored with built-in rules. Add a Gemini key on the backend for AI extraction."
    : "Extracted with " + r.mode + ".";
  const srcs = (r.sources || []).filter((s) => s.url).map((s) => s.title).join(" + ");
  $("mode").textContent = [srcs && "Read: " + srcs + ".", cachedAt && "Saved result from " + new Date(cachedAt).toLocaleString() + ".", modeText].filter(Boolean).join(" ");

  $("flags").replaceChildren(
    ...r.summary.red_flags.slice(0, 6).map((f) => h("span", { class: "chip bad", text: f })),
    ...r.summary.good_signs.slice(0, 4).map((f) => h("span", { class: "chip good", text: f })));

  $("points").replaceChildren(...r.summary.key_points.map((k) =>
    h("div", { class: "kp" }, h("h3", { text: k.title }), h("p", { text: k.text }))));

  $("entities").replaceChildren(...(r.entities.length
    ? r.entities.map((e) => h("span", { class: "chip" + (e.weight >= 4 ? " bad" : ""), text: e.name }))
    : [h("span", { class: "hint", text: "None detected." })]));

  $("clauses").replaceChildren(...r.top_clauses.map((c) => h("div", { class: "clause" },
    h("div", { text: c.text.length > 220 ? c.text.slice(0, 218) + "…" : c.text }),
    h("div", { class: "meta", text: `Score ${fmt(c.score)} of 10 · ${c.canonical_entities.join(", ") || "General"}` }))));

  $("analyze-btn").textContent = "Analyze again";
  hide($("save-status")); hide($("dash-note"));
  $("save-btn").disabled = false; $("save-btn").textContent = "Save to portfolio";
}

/* ---------- compare ---------- */
$("compare-btn").onclick = async () => {
  // One or more other sites, separated by commas, spaces or new lines.
  const others = $("other").value.split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean);
  const st = $("compare-status"), btn = $("compare-btn");
  hide($("verdict"));
  if (!others.length) { showStatus(st, "Enter at least one website to compare with.", "error"); show(st); return; }
  if (others.length > 5) { showStatus(st, "You can compare up to 6 websites in total (this one plus 5 others).", "error"); show(st); return; }
  if (!lastReport) return;
  btn.disabled = true;
  showStatus(st, others.length > 1 ? `Reading ${others.length} other policies…` : "Reading the other site's policy…", "info"); show(st);
  try {
    const first = lastPayload || { url: tab.url };
    const data = await api("/api/compare-websites", { method: "POST",
      body: JSON.stringify({ sites: [first, ...others.map((url) => ({ url }))] }) }, 240000);
    hide(st);
    renderVerdict(data);
  } catch (e) {
    showStatus(st, e.message, "error", e.fix || ""); show(st);
  } finally { btn.disabled = false; }
};
$("other").addEventListener("keydown", (e) => { if (e.key === "Enter") $("compare-btn").click(); });

function renderVerdict(d) {
  const v = d.verdict, box = $("verdict");
  const sites = d.sites || [d.a, d.b];
  const conf = { high: "High confidence", medium: "Medium confidence", low: "Low confidence" }[v.confidence];
  const top = new Set(v.winner_indices || []);
  box.replaceChildren(
    h("span", { class: "tag", text: v.winner === "tie" ? "Too close to call" : "Recommended · " + conf }),
    h("h3", { text: v.headline }),
    h("p", { text: v.summary }),
    h("div", { class: "ranking" }, (v.ranking || sites.map((r, i) => ({ index: i, rank: i + 1, service_name: r.service_name, rating: r.rating })))
      .map((r) => h("div", { class: "rk" + (top.has(r.index) ? " top" : "") },
        h("span", { class: "n", text: r.rank }), h("span", { class: "nm", text: r.service_name }),
        h("span", { class: "track" }, h("i", { style: `width:${r.rating}%` })),
        h("b", { text: fmt(r.rating) })))),
    v.reasons.length ? h("ul", {}, v.reasons.slice(0, 4).map((r) => h("li", { text: r }))) : null);
  show(box);
}

/* ---------- actions ---------- */
$("open-dash").onclick = async () => {
  if (!lastReport) return;
  const btn = $("open-dash"), st = $("save-status");
  btn.disabled = true;
  try {
    // Make sure this site is on the dashboard shelf (adding twice just replaces it), then open the dashboard.
    // The dashboard selects the two newest sites by itself, so one click there compares them.
    await api("/api/shelf", { method: "POST", body: JSON.stringify(lastReport) });
    chrome.tabs.create({ url: `${server}/` });
  } catch (e) {
    showStatus(st, e.message, "error", e.fix || ""); show(st);
  } finally { btn.disabled = false; }
};

$("save-btn").onclick = async () => {
  if (!lastReport) return;
  const btn = $("save-btn"), st = $("save-status");
  btn.disabled = true; btn.textContent = "Saving…"; hide(st);
  try {
    await api("/api/save-service", { method: "POST", body: JSON.stringify({
      service_name: lastReport.service_name, category: "Unknown", clauses: lastReport.clauses }) });
    btn.textContent = "Saved";
    showStatus(st, `${lastReport.service_name} was added to your portfolio.`, "success"); show(st);
  } catch (e) {
    btn.disabled = false; btn.textContent = "Try saving again";
    showStatus(st, e.message, "error", e.fix || ""); show(st);
  }
};

/* ---------- start ---------- */
(async function init() {
  server = (await store.get("server")) || DEFAULT_SERVER;
  $("server").value = server;
  tab = await getTab();
  if (tab && tab.url && /^https?:/.test(tab.url)) {
    const u = new URL(tab.url);
    $("site-name").textContent = u.hostname.replace(/^www\./, "");
    $("site-kind").textContent = pageKind(tab);
    $("analyze-hint").textContent = pageKind(tab)
      ? "Reads this page, and its terms and conditions if they are linked."
      : "Finds this site's privacy policy and terms, then summarizes them.";
  } else {
    $("site-name").textContent = "Open a website first";
    $("analyze-btn").disabled = true;
  }
  const ok = await checkConnection();
  if (ok && tab && /^https?:/.test(tab.url)) {
    const cached = await store.get("cache:" + new URL(tab.url).origin);
    if (cached && Date.now() - cached.at < 24 * 3600 * 1000) {
      lastPayload = cached.payload;
      render(cached.report, cached.at);
    }
  }
})();
