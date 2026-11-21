/* FinPilot frontend — vanilla JS. All numbers come from the backend's deterministic functions. */
"use strict";

// ------------------------------------------------------------------ state & helpers
const S = {
  meta: null,
  pid: "aziza",
  view: "home",
  mode: null,        // null (onboarding) | "locked" (no card yet) | "user" | "demo"
  auth: null,
  settings: null,
  conv: {},          // chat conversation id per profile
  bufferPct: {},     // O'sish buffer slider per profile
  chart: null,
  demoStep: -1,
};

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const NB = " ";

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function som(n) {
  const v = Math.round(Number(n) || 0);
  const s = Math.abs(v).toString().replace(/\B(?=(\d{3})+(?!\d))/g, NB);
  return (v < 0 ? "-" : "") + s + " so'm";
}
function pct(r) { return (Math.round(r * 1000) / 10).toString().replace(".", ",") + "%"; }
const MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"];
function dateUz(iso) { if (!iso) return ""; const d = new Date(iso.slice(0, 10) + "T00:00:00"); return `${d.getDate()}-${MONTHS[d.getMonth()]}`; }
function timeUz(iso) { if (!iso) return ""; const d = new Date(iso); return d.toLocaleString("uz-UZ", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }); }
const LEVEL_CLASS = { "yuqori": "high", "o'rta": "mid", "past": "low" };
const STATUS_UZ = { proposed: "Tasdiq kutilmoqda", advice: "Faqat maslahat", executed: "Bajarildi", failed: "Xato", rejected: "Rad etildi", undone: "Bekor qilindi" };
const STATUS_CLASS = { proposed: "amber", advice: "gray", executed: "green", failed: "red", rejected: "gray", undone: "gray" };

async function api(path, opts = {}) {
  const init = { method: opts.method || "GET", headers: {} };
  if (opts.body !== undefined) {
    if (opts.body instanceof FormData) init.body = opts.body;
    else { init.body = JSON.stringify(opts.body); init.headers["Content-Type"] = "application/json"; }
  }
  const r = await fetch(path, init);
  let data = null;
  try { data = await r.json(); } catch (e) { /* empty body */ }
  if (!r.ok) {
    const d = data && data.detail;
    const msg = typeof d === "string" ? d : d && d.message ? d.message : Array.isArray(d) ? "Ma'lumot noto'g'ri kiritildi" : `Xato (${r.status})`;
    const err = new Error(msg);
    err.status = r.status;
    err.info = d && typeof d === "object" && !Array.isArray(d) ? d : null;
    if (r.status === 401 && !path.startsWith("/api/auth/") && S.mode && S.mode !== "locked") {
      setTimeout(async () => { await refreshAuth(); S.mode = null; obRoute(); toast("Sessiya tugadi. Qaytadan kiring", 3500); }, 0);
    }
    throw err;
  }
  return data;
}

function toast(msg, ms = 2600) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.remove("show"), ms);
}

// Minimal, safe markdown: **bold**, "- " bullets, "1. " numbered, paragraphs
function md(text) {
  const lines = esc(text).split("\n");
  let html = "", list = null;
  const close = () => { if (list) { html += `</${list}>`; list = null; } };
  for (const raw of lines) {
    const line = raw.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
    let m;
    if ((m = line.match(/^\s*[-•]\s+(.*)/))) { if (list !== "ul") { close(); html += "<ul>"; list = "ul"; } html += `<li>${m[1]}</li>`; }
    else if ((m = line.match(/^\s*\d+[.)]\s+(.*)/))) { if (list !== "ol") { close(); html += "<ol>"; list = "ol"; } html += `<li>${m[1]}</li>`; }
    else if (line.trim() === "") { close(); }
    else { close(); html += `<p>${line}</p>`; }
  }
  close();
  return html;
}

function animateNumber(el, to, fmt = som, ms = 900) {
  if (!el) return;
  const from = Number(el.dataset.v || 0);
  el.dataset.v = to;
  const t0 = performance.now();
  const step = now => {
    const k = Math.min(1, (now - t0) / ms);
    const e = 1 - Math.pow(1 - k, 3);
    el.textContent = fmt(from + (to - from) * e);
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function kv(obj) {
  return `<div class="kv">${Object.entries(obj || {}).map(([k, v]) => `<span>${esc(k)}</span><span>${esc(v)}</span>`).join("")}</div>`;
}
function hisobBlock(h, title = "Hisoblandi") {
  if (!h) return "";
  return `<details class="hisob"><summary>🧮 ${title}: formula va kirish ma'lumotlari</summary>
    <div class="hisob-item"><div class="f">${esc(h.formula)}</div>${kv(h.inputs)}<div style="height:6px"></div>${kv(h.outputs)}</div></details>`;
}

// ------------------------------------------------------------------ navigation
const NAV = [
  { id: "home", ico: "🏠", label: "Bosh sahifa" },
  { id: "qalqon", ico: "🛡", label: "Qalqon" },
  { id: "osish", ico: "📈", label: "O'sish" },
  { id: "shifo", ico: "🩺", label: "Shifo" },
  { id: "meros", ico: "🕊", label: "Meros" },
  { sep: true },
  { id: "audit", ico: "📜", label: "Audit jurnali" },
  { id: "security", ico: "🔒", label: "Xavfsizlik" },
  { id: "how", ico: "🧩", label: "Qanday ishlaydi" },
];
const EMPHASIS = { aziza: "qalqon", salomat: "osish" };
const isUser = () => S.mode === "user";

function renderNav() {
  const locked = S.mode === "locked" || !S.mode;
  const active = id => (!locked && S.view === id) || (locked && id === "home");
  const emph = isUser() ? "qalqon" : EMPHASIS[S.pid];
  const lockTag = '<span class="tag" style="background:var(--surface-2);color:var(--muted)">🔒</span>';
  const html = NAV.map(n => n.sep ? `<div class="nav-sep"></div>` :
    `<button class="nav-btn ${active(n.id) ? "active" : ""} ${locked && n.id !== "home" ? "locked" : ""}" data-view="${n.id}"><span class="ico">${n.ico}</span>${n.label}
     ${locked && n.id !== "home" ? lockTag : !locked && emph === n.id ? '<span class="tag">Tavsiya</span>' : ""}</button>`).join("");
  $("#nav").innerHTML = html;
  $("#tabbar").innerHTML = NAV.filter(n => !n.sep && n.id !== "how").map(n =>
    `<button class="nav-btn ${active(n.id) ? "active" : ""}" data-view="${n.id}"><span class="ico">${n.ico}</span>${n.label.split(" ")[0]}</button>`).join("");
  $$("[data-view]").forEach(b => b.onclick = () => {
    if (S.mode === "locked") { if (b.dataset.view !== "home") toast("Avval kartangizni qo'shing 💳"); return enterLocked(); }
    if (!S.mode) return;
    go(b.dataset.view);
  });
}

async function go(view) {
  S.view = view;
  renderNav();
  const v = $("#view");
  v.innerHTML = `<div class="thinking"><i></i><i></i><i></i></div>`;
  try {
    await VIEWS[view](v);
  } catch (e) {
    if (e.status === 403) { showConsent(); v.innerHTML = `<div class="card empty"><div class="big">🔐</div><p>Davom etish uchun rozilik bering.</p></div>`; }
    else v.innerHTML = `<div class="card"><b>Xato:</b> ${esc(e.message)}</div>`;
  }
  window.scrollTo({ top: 0 });
}

function refresh() { return go(S.view); }

// ------------------------------------------------------------------ top bar
function renderTopbar() {
  const mode = S.mode;
  const personal = mode === "user" || mode === "locked";
  $("#profileSeg").classList.toggle("hidden", mode !== "demo");
  $("#userChip").classList.toggle("hidden", !personal);
  $("#privacyBadge").classList.toggle("hidden", !personal);
  $("#privacyPill").classList.toggle("hidden", !personal);
  $("#autonomyWrap").classList.toggle("hidden", mode !== "user" && mode !== "demo");
  $("#logoutBtn").classList.toggle("hidden", !mode);
  $("#logoutBtn").innerHTML = mode === "demo" ? "⎋ Demo'dan chiqish" : "⎋ Chiqish";
  $("#chatFab").classList.toggle("hidden", mode !== "user" && mode !== "demo");
  if (S.auth && S.auth.user) {
    const u = S.auth.user;
    $("#userChip").innerHTML = `👤 ${esc(u.first)} ${esc(u.last[0])}.${S.auth.card ? ` <span class="card-tag">${esc(S.auth.card.label)}</span>` : ""}`;
  }
  $("#aiStatus").innerHTML = S.meta.ai_enabled
    ? `<span class="pill green">● Jonli AI</span><div class="mt small">${esc(S.meta.model)}</div>`
    : `<span class="pill amber">● Offline demo rejimi</span><div class="mt small">AI kaliti yo'q — javoblar shablon, raqamlar haqiqiy hisob-kitob</div>`;
  if (mode !== "user" && mode !== "demo") { $("#limitWrap").classList.add("hidden"); return; }
  $("#profileSeg").innerHTML = S.meta.profiles.map(p =>
    `<button data-pid="${p.id}" class="${p.id === S.pid ? "active" : ""}">${p.kind === "business" ? "🏪" : "👤"} ${esc(p.title)}</button>`).join("");
  $$("#profileSeg button").forEach(b => b.onclick = () => switchProfile(b.dataset.pid));
  const levels = S.meta.autonomy_levels;
  $("#autonomySeg").innerHTML = Object.entries(levels).map(([k, label]) =>
    `<button data-a="${k}" class="${S.settings && S.settings.autonomy === k ? "active" : ""}">${label}</button>`).join("");
  $$("#autonomySeg button").forEach(b => b.onclick = () => saveSettings(b.dataset.a, S.settings.auto_limit));
  $("#limitWrap").classList.toggle("hidden", !S.settings || S.settings.autonomy !== "auto");
  $("#limitInput").value = S.settings ? String(S.settings.auto_limit).replace(/\B(?=(\d{3})+(?!\d))/g, " ") : "";
}

async function saveSettings(autonomy, limit) {
  S.settings = await api(`/api/settings/${S.pid}`, { method: "PUT", body: { autonomy, auto_limit: Math.max(0, Math.round(limit)) } });
  renderTopbar();
  toast(`Autonomiya: ${S.meta.autonomy_levels[autonomy]}${autonomy === "auto" ? " · limit " + som(S.settings.auto_limit) : ""}`);
}

async function switchProfile(pid) {
  S.pid = pid;
  S.settings = await api(`/api/settings/${pid}`);
  renderTopbar();
  resetChat();
  const consent = await api(`/api/consent/${pid}`);
  if (!consent.granted) showConsent();
  await go(S.view === "home" ? "home" : S.view);
}

// ------------------------------------------------------------------ modal
function openModal(html) {
  const m = $("#modal");
  m.innerHTML = `<div class="modal-box">${html}</div>`;
  m.classList.remove("hidden");
  m.onclick = e => { if (e.target === m && !m.dataset.locked) closeModal(); };
  return $(".modal-box", m);
}
function closeModal() { const m = $("#modal"); m.classList.add("hidden"); m.innerHTML = ""; delete m.dataset.locked; }
document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("#modal").dataset.locked) closeModal(); });

function showConsent() {
  const box = openModal(`
    <h2>🔐 Ma'lumotlardan foydalanishga rozilik</h2>
    <p class="muted">FinPilot quyidagilarni faqat sizga xizmat ko'rsatish uchun tahlil qiladi:</p>
    <ul class="consent-list">
      <li>Oxirgi 90 kunlik karta tranzaksiyalari (obunalarni topish uchun)</li>
      <li>Hisob qoldiqlari va kelgusi to'lovlar (bo'sh pulni hisoblash uchun)</li>
      <li>Kreditlar (qarz yukini baholash uchun)</li>
      <li>AI tahlil: ism, karta, telefon raqamlari AI'ga <b>yuborilmaydi</b> — ular tokenlar bilan almashtiriladi</li>
    </ul>
    <p class="small muted">Har bir amal faqat sizning roziligingiz yoki o'zingiz belgilagan limit ichida bajariladi va audit jurnaliga yoziladi. Rozilikni istalgan payt "Xavfsizlik" bo'limida bekor qilishingiz mumkin.</p>
    <div class="modal-actions"><button class="btn ghost" id="cLater">Keyinroq</button><button class="btn green" id="cOk">Roziman</button></div>`);
  $("#modal").dataset.locked = "1";
  $("#cLater", box).onclick = closeModal;
  $("#cOk", box).onclick = async () => {
    await api(`/api/consent/${S.pid}/grant`, { method: "POST" });
    closeModal();
    toast("Rozilik saqlandi ✓");
    refresh();
  };
}

// ------------------------------------------------------------------ actions (Prepare → Confirm → Execute → Audit)
async function prepareAction(type, params) {
  try {
    const a = await api("/api/actions/prepare", { method: "POST", body: { profile_id: S.pid, type, params } });
    handlePrepared(a);
    return a;
  } catch (e) {
    if (e.status === 403) showConsent(); else toast("⚠️ " + e.message, 3500);
  }
}

function handlePrepared(a) {
  if (a.status === "executed") {
    toast(`⚡ Avtomatik bajarildi: ${a.proposal.title}`, 3500);
    refresh();
  } else if (a.status === "advice") {
    openModal(`<h2>💡 Faqat maslahat</h2><p class="muted">${esc(a.proposal.policy)}</p>
      <div class="action-card"><div class="t">${esc(a.proposal.title)}</div>${kv(Object.fromEntries(a.proposal.details))}</div>
      <p class="small muted">Bajarish uchun yuqoridagi "Autonomiya darajasi"ni "Bir bosishda" ga o'zgartiring.</p>
      <div class="modal-actions"><button class="btn" onclick="closeModal()">Tushunarli</button></div>`);
  } else if (a.status === "proposed") {
    openConfirm(a);
  } else if (a.status === "failed") {
    toast("⚠️ Bank xatosi: " + ((a.result && a.result.error) || ""), 3500);
  }
}

function openConfirm(a) {
  const p = a.proposal;
  const box = openModal(`
    <div class="small muted">${esc(p.label)} · #${a.id}</div>
    <h2>${esc(p.title)}</h2>
    <div class="action-card">${kv(Object.fromEntries(p.details))}<div class="hisob-item"><div class="f">${esc(p.formula)}</div></div></div>
    <p class="small muted">🛡 ${esc(p.policy || "")}</p>
    <div class="modal-actions"><button class="btn ghost" id="mNo">Rad etish</button><button class="btn green" id="mYes">✓ Tasdiqlayman</button></div>`);
  $("#mNo", box).onclick = async () => { await api(`/api/actions/${a.id}/reject`, { method: "POST" }); closeModal(); toast("Rad etildi"); refresh(); };
  $("#mYes", box).onclick = async () => {
    $("#modal").dataset.locked = "1";
    const btn = $("#mYes", box);
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span> Bankka yuborilmoqda…`;
    try {
      const done = await api(`/api/actions/${a.id}/confirm`, { method: "POST" });
      delete $("#modal").dataset.locked;
      if (done.status === "executed") {
        box.innerHTML = `<div class="success"><div class="check">✓</div><h2>Bajarildi</h2>
          <p class="muted">${esc(p.title)}</p><p class="small mono">Bank havolasi: ${esc(done.result.ref)}</p>
          ${p.return_date ? `<p class="small">Pul ${dateUz(p.return_date)} kuni avtomatik qaytadi · daromad <b>${som(p.expected_earnings)}</b></p>` : ""}
          <p class="small muted">Audit jurnaliga yozildi 📜</p></div>
          <div class="modal-actions"><button class="btn" id="mClose">Yopish</button></div>`;
        $("#mClose", box).onclick = () => { closeModal(); refresh(); };
      } else {
        box.innerHTML = `<h2>⚠️ Bajarilmadi</h2><p>${esc((done.result && done.result.error) || "Bank xatosi")}</p>
          <div class="modal-actions"><button class="btn" id="mClose">Yopish</button></div>`;
        $("#mClose", box).onclick = () => { closeModal(); refresh(); };
      }
    } catch (e) {
      delete $("#modal").dataset.locked;
      btn.disabled = false; btn.textContent = "Qayta urinish";
      toast("⚠️ " + e.message, 3500);
    }
  };
}

async function undoAction(id) {
  try { await api(`/api/actions/${id}/undo`, { method: "POST" }); toast("↩︎ Bekor qilindi"); refresh(); }
  catch (e) { toast("⚠️ " + e.message, 3500); }
}

function actionCard(a) {
  const p = a.proposal;
  const canUndo = a.status === "executed" && a.undo_until && new Date(a.undo_until) > new Date();
  return `<div class="action-card" data-action="${a.id}">
    <div style="display:flex;justify-content:space-between;gap:8px;align-items:center">
      <div class="t">${esc(p.title)}</div><span class="pill ${STATUS_CLASS[a.status]}">${STATUS_UZ[a.status]}${a.mode === "auto" ? " · avto" : ""}</span></div>
    ${kv(Object.fromEntries(p.details))}
    <div class="row-actions">
      ${a.status === "proposed" ? `<button class="btn green sm" data-confirm="${a.id}">Tasdiqlash</button>` : ""}
      ${canUndo ? `<button class="btn ghost sm" data-undo="${a.id}">↩︎ Bekor qilish (24 soat)</button>` : ""}
    </div></div>`;
}
document.addEventListener("click", async e => {
  const c = e.target.closest("[data-confirm]");
  if (c) { const a = await api(`/api/actions/${S.pid}`).then(list => list.find(x => x.id == c.dataset.confirm)); if (a) openConfirm(a); }
  const u = e.target.closest("[data-undo]");
  if (u) undoAction(u.dataset.undo);
});

// ------------------------------------------------------------------ AI agent streaming
async function streamAgent(body, on) {
  let r;
  try {
    r = await fetch("/api/agent", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  } catch (e) { on({ type: "error", message: "Serverga ulanib bo'lmadi" }); on({ type: "done" }); return; }
  if (!r.ok) {
    let msg = `Xato (${r.status})`;
    try { msg = (await r.json()).detail || msg; } catch (e) { /* ignore */ }
    if (r.status === 403) showConsent();
    on({ type: "error", message: msg }); on({ type: "done" });
    return;
  }
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) !== -1) {
      const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
      const line = chunk.split("\n").find(l => l.startsWith("data: "));
      if (line) { try { on(JSON.parse(line.slice(6))); } catch (e) { /* skip */ } }
    }
  }
}

/** Renders an AI answer box into `container` and streams the agent into it. */
function aiBox(container, { preset, message, title = "FinPilot tahlili", conversation = false, onDone } = {}) {
  const box = document.createElement("div");
  box.className = "card ai-box";
  box.innerHTML = `<div class="ai-head"><div class="ai-avatar">🧭</div><b>${esc(title)}</b><span class="mode-badge pill gray">…</span></div>
    <div class="thinking"><i></i><i></i><i></i></div><div class="ai-text cursor"></div><div class="ai-actions"></div>
    <details class="hisob hidden"><summary>🧮 Hisoblandi: AI ishlatgan deterministik hisob-kitoblar</summary><div class="tools"></div></details>`;
  container.appendChild(box);
  const textEl = $(".ai-text", box), toolsEl = $(".tools", box), det = $("details.hisob", box);
  let text = "";
  const body = { profile_id: S.pid, preset, message, buffer_pct: S.bufferPct[S.pid] ?? null };
  if (conversation) body.conversation_id = S.conv[S.pid] || null;
  let pending = "", raf = null;
  const flush = () => { raf = null; text += pending; pending = ""; textEl.innerHTML = md(text); };
  streamAgent(body, ev => {
    if (ev.type === "mode") {
      const b = $(".mode-badge", box);
      b.className = "mode-badge pill " + (ev.mode === "live" ? "green" : "amber");
      b.textContent = ev.mode === "live" ? "● Jonli AI" : "● Offline demo rejimi";
      if (conversation && ev.conversation_id) S.conv[S.pid] = ev.conversation_id;
    } else if (ev.type === "text") {
      $(".thinking", box)?.remove();
      pending += ev.text;
      if (!raf) raf = requestAnimationFrame(flush);
    } else if (ev.type === "tool") {
      det.classList.remove("hidden");
      toolsEl.insertAdjacentHTML("beforeend", `<div class="hisob-item"><b>${esc(ev.label)}</b> <span class="mono muted">${esc(ev.name)}(${esc(JSON.stringify(ev.input))})</span>
        <div class="f">${esc(ev.hisob.formula)}</div>${kv(ev.hisob.inputs)}<div style="height:6px"></div>${kv(ev.hisob.outputs)}</div>`);
    } else if (ev.type === "action") {
      $(".ai-actions", box).insertAdjacentHTML("beforeend", actionCard(ev.action));
      if (ev.action.status === "executed") toast("⚡ Avtomatik bajarildi (limit ichida)");
    } else if (ev.type === "error") {
      $(".ai-actions", box).insertAdjacentHTML("beforeend", `<div class="small" style="color:var(--amber);margin-top:8px">⚠️ ${esc(ev.message)}</div>`);
    } else if (ev.type === "done") {
      if (raf) { cancelAnimationFrame(raf); flush(); }
      $(".thinking", box)?.remove();
      textEl.classList.remove("cursor");
      if (onDone) onDone(text, ev);
    }
  });
  return box;
}

// ------------------------------------------------------------------ views
const VIEWS = {};

VIEWS.home = async v => {
  const d = await api(`/api/home/${S.pid}`);
  const h = d.health;
  const C = 2 * Math.PI * 64;
  const color = h.score >= 70 ? "var(--green)" : h.score >= 45 ? "var(--amber)" : "var(--red)";
  v.innerHTML = `
    <div class="view-head"><div><h1>Salom, ${isUser() ? esc(S.auth.user.first) + "!" : S.pid === "aziza" ? "Aziza" : "\"Salomat\" jamoasi"} 👋</h1>
      <p>FinPilot pulingizni himoya qiladi (Qalqon), o'stiradi (O'sish) va qarzni yengillashtiradi (Shifo) — har bir amal sizning roziligingiz bilan.</p></div>
      <button class="btn" id="aiSummaryBtn">✨ FinPilot xulosasi</button></div>
    <div id="aiSummary"></div>
    <div class="grid g3">
      <div class="card" style="grid-column: span 2">
        <div class="card-head"><h2>Moliyaviy salomatlik</h2><span class="pill blue">0–100</span></div>
        <div class="ring-wrap">
          <div class="ring"><svg width="150" height="150"><circle class="track" cx="75" cy="75" r="64" fill="none" stroke-width="13"/>
            <circle class="bar" id="ringBar" cx="75" cy="75" r="64" fill="none" stroke="${color}" stroke-width="13" stroke-linecap="round"
              stroke-dasharray="${C}" stroke-dashoffset="${C}"/></svg>
            <div class="center"><div><b id="scoreNum">0</b><div class="small muted">/ 100</div></div></div></div>
          <div class="parts">${Object.entries(h.parts).map(([k, val]) => `<div class="part"><div class="row"><span>${esc(k)}</span><b class="num">${val}/25</b></div>
            <div class="bar-track"><div class="bar-fill" style="width:0" data-w="${val * 4}"></div></div></div>`).join("")}</div>
        </div>
        ${hisobBlock(h.hisob)}
      </div>
      <div class="card">
        <div class="card-head"><h2>Sof holat</h2></div>
        <div class="kpi"><div class="label">Aktivlar − majburiyatlar</div><div class="value ${d.net.net >= 0 ? "green" : "red"}" id="netVal">0</div></div>
        <div class="kv" style="margin-top:12px"><span>Aktivlar</span><span class="num">${som(d.net.assets)}</span>
          <span>Kreditlar</span><span class="num">${som(d.net.liabilities)}</span>
          <span>Depozitlarda</span><span class="num">${som(d.net.in_deposits)}</span></div>
        <div class="nav-sep"></div>
        ${d.accounts.map(a => `<div style="display:flex;justify-content:space-between;gap:8px;margin:6px 0"><div><div>${esc(a.name)}</div><div class="mono muted">${esc(a.number || "")}</div></div><b class="num">${som(a.balance)}</b></div>`).join("")}
      </div>
    </div>
    <h2 class="mt" style="margin-bottom:10px">🔗 Modullar sinergiyasi</h2>
    <div class="grid g3" id="synergy">${d.synergy.map(c => `
      <div class="card synergy"><div class="flow">${esc(c.from)} → ${esc(c.to)}</div><h3>${esc(c.title)}</h3><p>${esc(c.text)}</p>
        <div class="row-actions"><button class="btn sm" data-syn="${c.id}">Tayyorlash</button></div>
        <details class="hisob"><summary>🧮 Hisoblandi</summary><div class="hisob-item"><div class="f">${esc(c.formula)}</div></div></details></div>`).join("") ||
        `<div class="card muted">Hozircha sinergiya tavsiyalari yo'q — hammasi joyida ✓</div>`}</div>
    <div class="card mt"><div class="card-head"><h2>FinPilot bugun nima qildi</h2><button class="btn ghost sm" onclick="go('audit')">Audit jurnali →</button></div>
      <div class="feed">${d.feed.length ? d.feed.map(a => `<div class="feed-item"><span class="dot ${a.status}"></span><div style="flex:1">
        <div><b>${esc(a.proposal.label)}</b> — ${esc(a.proposal.title)}</div>
        <div class="small muted">${timeUz(a.created_at)} · ${a.created_by === "agent" ? "🧭 FinPilot tayyorladi" : "👤 siz tayyorladingiz"} · <span class="pill ${STATUS_CLASS[a.status]}">${STATUS_UZ[a.status]}${a.mode === "auto" ? " · avto" : ""}</span></div></div>
        ${a.status === "proposed" ? `<button class="btn green sm" data-confirm="${a.id}">Tasdiqlash</button>` : ""}
        ${a.status === "executed" && a.undo_until && new Date(a.undo_until) > new Date() ? `<button class="btn ghost sm" data-undo="${a.id}">↩︎</button>` : ""}</div>`).join("")
        : `<div class="muted small">Hali amal yo'q. Qalqon yoki O'sish bo'limidan boshlang.</div>`}</div></div>`;
  requestAnimationFrame(() => {
    if (!$("#ringBar")) return; // view already changed
    $("#ringBar").style.strokeDashoffset = C * (1 - h.score / 100);
    animateNumber($("#scoreNum"), h.score, n => Math.round(n));
    animateNumber($("#netVal"), d.net.net);
    $$(".bar-fill", v).forEach(b => b.style.width = b.dataset.w + "%");
  });
  $("#aiSummaryBtn").onclick = () => { $("#aiSummary").innerHTML = ""; aiBox($("#aiSummary"), { preset: "home_summary", title: "FinPilot xulosasi" }); };
  $$("[data-syn]").forEach(b => b.onclick = () => {
    const c = d.synergy.find(x => x.id === b.dataset.syn);
    prepareAction(c.action.type, c.action.params);
  });
};

VIEWS.qalqon = async v => {
  const q = await api(`/api/qalqon/${S.pid}`);
  const head = `<div class="view-head"><div><h1>🛡 Qalqon</h1>
    <p>Pul kartadan jimgina ketadi: unutilgan obunalar, sinov davridan keyin pullikka o'tish, ikki marta to'lov va xabarsiz narx oshishi. Qalqon ko'chirmani tahlil qilib, ularni topadi va to'xtatadi.</p></div>
    <div class="row-actions">${isUser() ? `<a class="btn ghost sm" href="/static/sample_statement.csv" download>⬇ Namuna CSV</a>` : `<button class="btn" id="loadBtn">🏦 Bank ko'chirmasini yuklash</button>`}
    <label class="btn ${isUser() ? "" : "ghost"}" for="csvIn">📄 CSV yuklash</label><input type="file" id="csvIn" accept=".csv,text/csv" hidden></div></div>`;
  if (!q.loaded) {
    v.innerHTML = head + `<div class="card empty"><div class="big">🧾</div><h2>Ko'chirma hali yuklanmagan</h2>
      <p class="muted">${isUser() ? "Bankingiz ilovasidan 90 kunlik ko'chirmani CSV qilib yuklang" : "\"Bank ko'chirmasini yuklash\" tugmasi oxirgi 90 kunlik tranzaksiyalarni oladi.<br>Yoki o'zingizning CSV faylingizni yuklang"} (ustunlar: <span class="mono">date, description, amount</span>).${isUser() ? "<br>Ko'chirma faqat sessiya xotirasida turadi va chiqishingiz bilan o'chiriladi." : ""}</p></div>`;
  } else {
    const flagged = q.findings.filter(f => f.level !== "past");
    v.innerHTML = head + `
      <div class="grid g4">
        <div class="card kpi"><div class="label">Oylik tejash imkoniyati</div><div class="value green" id="potM">0</div><div class="sub">yillik: <span id="potY">0</span></div></div>
        <div class="card kpi"><div class="label">Allaqachon tejaldi (oyiga)</div><div class="value green" id="realM">0</div><div class="sub">yillik: <span id="realY">0</span></div></div>
        <div class="card kpi"><div class="label">Shubhali topilmalar</div><div class="value">${flagged.length}</div><div class="sub">${q.findings.length} ta muntazam to'lovdan</div></div>
        <div class="card kpi"><div class="label">Tahlil qilindi</div><div class="value">${q.transactions_analyzed}</div><div class="sub">tranzaksiya · ${q.source === "csv" ? "CSV fayl" : "bank, 90 kun"}</div></div>
      </div>
      <div class="card mt"><div class="card-head"><h2>Topilmalar</h2><button class="btn ghost sm" id="explainBtn">✨ AI tushuntirsin</button></div>
        <div class="table-wrap"><table><thead><tr><th>Xizmat</th><th>Summa</th><th>Davriylik</th><th>Shubha darajasi</th><th>Sabab</th><th>Amallar</th></tr></thead><tbody>
        ${q.findings.map(f => `<tr class="${f.resolved ? "resolved" : ""}" id="f-${esc(f.id)}">
          <td><b>${esc(f.merchant)}</b><div class="mono muted">${f.rules.join(" · ")} · ${f.occurrences} marta</div></td>
          <td class="num">${som(f.amount)}</td><td>${esc(f.frequency)}</td>
          <td><span class="pill ${LEVEL_CLASS[f.level]}">${esc(f.level)}</span></td>
          <td class="small">${esc(f.reason)}${f.monthly_saving ? `<div class="muted">Tejash: <b>${som(f.monthly_saving)}</b>/oy</div>` : ""}</td>
          <td>${f.resolved ? `<span class="pill green">✓ Hal qilindi</span>` : f.level === "past" ? `<span class="muted small">—</span>` :
            `<div class="row-actions"><button class="btn sm" data-letter="${esc(f.id)}">✉️ Bekor qilish xati</button>
             <button class="btn ghost sm" data-limit="${esc(f.id)}">💳 Limit</button>
             <button class="btn danger sm" data-block="${esc(f.id)}">⛔ Bloklash</button></div>`}</td></tr>`).join("")}
        </tbody></table></div>
        ${hisobBlock(q.hisob)}
      </div>
      <div id="qalqonAi" class="mt"></div>`;
    requestAnimationFrame(() => {
      animateNumber($("#potM"), q.potential_monthly); animateNumber($("#potY"), q.potential_yearly);
      animateNumber($("#realM"), q.realized_monthly); animateNumber($("#realY"), q.realized_yearly);
    });
    $("#explainBtn").onclick = () => { $("#qalqonAi").innerHTML = ""; aiBox($("#qalqonAi"), { preset: "qalqon_explain", title: "Qalqon tahlili" }); };
    $$("[data-letter]").forEach(b => b.onclick = () => openLetter(q.findings.find(f => f.id === b.dataset.letter)));
    $$("[data-limit]").forEach(b => b.onclick = () => openLimit(q.findings.find(f => f.id === b.dataset.limit)));
    $$("[data-block]").forEach(b => b.onclick = () => prepareAction("block_merchant", { finding_id: b.dataset.block }));
  }
  if ($("#loadBtn")) $("#loadBtn").onclick = async () => {
    const b = $("#loadBtn"); b.disabled = true; b.innerHTML = `<span class="spinner"></span> Yuklanmoqda…`;
    try { await api(`/api/qalqon/${S.pid}/load-sample`, { method: "POST" }); toast("90 kunlik ko'chirma tahlil qilindi"); refresh(); }
    catch (e) { if (e.status === 403) showConsent(); else toast("⚠️ " + e.message); b.disabled = false; b.textContent = "🏦 Bank ko'chirmasini yuklash"; }
  };
  $("#csvIn").onchange = async e => {
    const f = e.target.files[0]; if (!f) return;
    const fd = new FormData(); fd.append("file", f);
    try { const r = await api(`/api/qalqon/${S.pid}/upload`, { method: "POST", body: fd }); toast(`CSV: ${r.transactions_analyzed} ta tranzaksiya tahlil qilindi`); refresh(); }
    catch (err) { if (err.status === 403) showConsent(); else toast("⚠️ " + err.message, 4000); }
  };
};

function openLetter(f) {
  const box = openModal(`<div class="small muted">Qalqon · ${esc(f.merchant)}</div><h2>✉️ Bekor qilish va qaytarish xati</h2>
    <div id="letterAi"></div>
    <div class="modal-actions"><button class="btn ghost" id="lClose">Yopish</button><button class="btn ghost" id="lMail" disabled>📧 Email sifatida ochish</button><button class="btn" id="lCopy" disabled>📋 Nusxa olish</button></div>`);
  $("#lClose", box).onclick = closeModal;
  aiBox($("#letterAi", box), {
    preset: "letter:" + f.id, title: "FinPilot xat yozmoqda",
    onDone: text => {
      const plain = text.replace(/\*\*/g, "");
      $("#lCopy", box).disabled = false; $("#lMail", box).disabled = false;
      $("#lCopy", box).onclick = async () => { try { await navigator.clipboard.writeText(plain); toast("Nusxa olindi ✓"); } catch (e) { toast("Nusxa olib bo'lmadi"); } };
      const subj = (plain.match(/Mavzu:\s*(.+)/) || [])[1] || "Obunani bekor qilish";
      $("#lMail", box).onclick = () => { location.href = `mailto:?subject=${encodeURIComponent(subj)}&body=${encodeURIComponent(plain)}`; };
    },
  });
}

function openLimit(f) {
  const box = openModal(`<div class="small muted">Qalqon · ${esc(f.merchant)}</div><h2>💳 Karta limitini o'rnatish</h2>
    <p class="muted">Bu xizmat uchun oylik limit belgilang. Limitdan oshgan to'lovlarni bank rad etadi. 0 — butunlay bloklash.</p>
    <div class="form-row"><label for="limVal">Oylik limit (so'm)</label><input id="limVal" class="num" inputmode="numeric" value="${Math.round(f.monthly_cost / 2 / 1000) * 1000}"></div>
    <div class="hisob-item" id="limSim"></div>
    <div class="modal-actions"><button class="btn ghost" id="lmCancel">Bekor</button><button class="btn" id="lmGo">Tayyorlash →</button></div>`);
  const sim = () => {
    const lim = Math.max(0, parseInt(($("#limVal", box).value || "0").replace(/\D/g, ""), 10) || 0);
    const saving = Math.max(0, f.monthly_cost - lim);
    $("#limSim", box).innerHTML = `<div class="f">tejash = max(0, ${som(f.monthly_cost)} − ${som(lim)}) = ${som(saving)}</div>${kv({ "Oylik tejash": som(saving), "Yillik tejash": som(saving * 12) })}`;
    return lim;
  };
  sim();
  $("#limVal", box).oninput = sim;
  $("#lmCancel", box).onclick = closeModal;
  $("#lmGo", box).onclick = async () => { const lim = sim(); closeModal(); await prepareAction("set_card_merchant_limit", { finding_id: f.id, monthly_limit: lim }); };
}

VIEWS.osish = async v => {
  const bp = S.bufferPct[S.pid];
  const t = await api(`/api/osish/${S.pid}${bp != null ? "?buffer_pct=" + bp : ""}`);
  if (t.missing) return osishMissing(v, t);
  const biz = t.profile_kind === "business";
  const rec = t.recommendation;
  v.innerHTML = `
    <div class="view-head"><div><h1>📈 O'sish — ${biz ? "AI G'aznachi" : "aqlli jamg'arma"}</h1>
      <p>${biz ? "Kichik biznes pulini joriy hisobda foizsiz ushlab turadi — ijara, ish haqi va yetkazib beruvchilarga to'lovdan qo'rqib. G'aznachi to'lov jadvalini prognoz qiladi va faqat o'z vaqtida qaytadigan pulni ishlatadi."
        : "Ish haqidan keyin ortib qolgan pul kartada hech narsa ishlamaydi. FinPilot zarur xarajatlar va bufer ajratib, ortiqchasini eng foydali omonatga joylaydi."}</p></div>
      <button class="btn" id="osishAiBtn">✨ AI tushuntirsin</button></div>
    <div class="grid g4">
      <div class="card kpi"><div class="label">Mavjud balans</div><div class="value">${som(t.balance)}</div><div class="sub">${t.deposits.length ? "depozitdagi pul chiqarilgan" : "joriy hisob + kartalar"}</div></div>
      <div class="card kpi"><div class="label">Oldindagi ehtiyoj</div><div class="value">${som(t.need)}</div><div class="sub">majburiyatlar + xarajatlar${biz ? " − tushum×0,7" : ""}</div></div>
      <div class="card kpi"><div class="label">Xavfsizlik buferi</div><div class="value">${som(t.buffer)}</div><div class="sub">${pct(t.buffer_pct)} × oylik chiqim</div></div>
      <div class="card kpi"><div class="label">Xavfsiz bo'sh pul</div><div class="value green" id="idleVal">0</div><div class="sub">joylashtirish mumkin</div></div>
    </div>
    <div class="card mt">
      <div class="card-head"><h2>Balans prognozi</h2>
        <div class="slider-row"><label for="bufRange" class="small muted">Bufer: <b id="bufLbl">${pct(t.buffer_pct)}</b></label>
        <input type="range" id="bufRange" min="0" max="40" step="5" value="${Math.round(t.buffer_pct * 100)}"></div></div>
      <div class="chart-box"><canvas id="cashChart" aria-label="Balans prognozi grafigi"></canvas></div>
      <div class="legend-note"><span><i style="background:#1f5fd1"></i>Tarixiy balans</span><span><i style="background:#6f9bff"></i>Prognoz</span>
        <span><i style="background:#c27a06"></i>Xavfsiz chegara (ehtiyoj + bufer)</span><span><i style="background:rgba(22,163,74,.35)"></i>Bo'sh pul zonasi</span><span>▼ to'lov sanalari</span></div>
      <p class="small"><b>Cheklov:</b> ${esc(t.constraint)}</p>
    </div>
    <div class="grid g2 mt">
      <div class="card ${rec ? "synergy" : ""}" id="recCard">
        <div class="card-head"><h2>Tavsiya</h2>${rec ? `<span class="pill green">eng yuqori daromad</span>` : ""}</div>
        ${rec ? `<h3>${esc(rec.instrument_name)}</h3>
          <div class="kv" style="margin:10px 0"><span>Summa</span><b class="num">${som(rec.amount)}</b><span>Stavka</span><span>${pct(rec.rate)} yillik</span>
            <span>Muddat</span><span>${rec.days} kun</span><span>Kutilayotgan daromad</span><b class="num" style="color:var(--green)">${som(rec.expected_earnings)}</b>
            <span>Avtomatik qaytish</span><span>${dateUz(rec.return_date)}${rec.payment_date ? ` — to'lovdan (${dateUz(rec.payment_date)}) oldin` : ""}</span></div>
          <button class="btn green" id="openDep">🏦 Depozit ochish</button>`
          : `<p class="muted">Hozir joylashtirish uchun xavfsiz bo'sh pul yo'q${t.deposits.length ? " — bo'sh pul allaqachon depozitga joylangan ✓" : ""}.</p>`}
        ${hisobBlock(t.hisob)}
      </div>
      <div class="card"><div class="card-head"><h2>Instrumentlar solishtirmasi</h2><span class="pill gray">demo stavkalar</span></div>
        <div class="table-wrap"><table><thead><tr><th>Instrument</th><th>Stavka</th><th>Muddat</th><th>Daromad</th><th></th></tr></thead><tbody>
        ${t.instruments.map(i => `<tr><td>${esc(i.name)}</td><td>${pct(i.rate)}</td><td>${i.rollover ? "har kuni" : i.term_days + " kun"}</td>
          <td class="num">${i.eligible ? som(i.expected_earnings) : "—"}</td>
          <td>${i.eligible ? `<span class="pill ${rec && rec.instrument_id === i.id ? "green" : "blue"}">${rec && rec.instrument_id === i.id ? "tanlandi" : "mos"}</span>` : `<span class="pill gray" title="${esc(i.ineligible_reason)}">mos emas</span><div class="small muted">${esc(i.ineligible_reason)}</div>`}</td></tr>`).join("")}
        </tbody></table></div></div>
    </div>
    ${t.deposits.length ? `<div class="card mt"><h2>Faol depozitlar</h2>${t.deposits.map(dp => `<div class="feed-item mt"><span class="dot executed"></span><div style="flex:1"><b>${esc(dp.instrument_name)}</b> — ${som(dp.amount)}<div class="small muted">qaytish: ${dateUz(dp.return_date)} · daromad ${som(dp.expected_earnings)}</div></div></div>`).join("")}</div>` : ""}
    <div id="osishAi" class="mt"></div>`;
  requestAnimationFrame(() => animateNumber($("#idleVal"), t.idle_cash));
  drawChart(t);
  let deb;
  $("#bufRange").oninput = e => {
    $("#bufLbl").textContent = e.target.value + "%";
    clearTimeout(deb);
    deb = setTimeout(() => { S.bufferPct[S.pid] = Number(e.target.value) / 100; refresh(); }, 350);
  };
  $("#osishAiBtn").onclick = () => { $("#osishAi").innerHTML = ""; aiBox($("#osishAi"), { preset: "osish_explain", title: "G'aznachi tahlili" }); $("#osishAi").scrollIntoView({ behavior: "smooth" }); };
  if (rec) $("#openDep").onclick = () => prepareAction("open_deposit", { instrument_id: rec.instrument_id, amount: rec.amount });
};

function osishMissing(v, t) {
  const f = (S.auth && S.auth.finance) || {};
  const fmt = n => (n == null ? "" : String(n).replace(/\B(?=(\d{3})+(?!\d))/g, " "));
  v.innerHTML = `<div class="view-head"><div><h1>📈 O'sish — aqlli jamg'arma</h1>
      <p>Bo'sh pulni hisoblash uchun FinPilot taxmin qilmaydi — faqat siz bergan aniq raqamlar bilan ishlaydi.</p></div></div>
    <div class="card" style="max-width:640px"><div class="card-head"><h2>Yetishmayotgan ma'lumotlar</h2><span class="pill amber">${t.missing.length} ta</span></div>
      <p class="muted small">Kerak: <b>${t.missing.map(esc).join(", ")}</b></p>
      <div class="two"><div class="form-row"><label for="fBal">Kartadagi qoldiq</label><input id="fBal" inputmode="numeric" value="${fmt(f.balance)}"></div>
        <div class="form-row"><label for="fInc">Oylik daromad</label><input id="fInc" inputmode="numeric" value="${fmt(f.monthly_income)}"></div>
        <div class="form-row"><label for="fDay">Oylik kuni (1–28)</label><input id="fDay" inputmode="numeric" maxlength="2" value="${f.payday ?? ""}"></div>
        <div class="form-row"><label for="fEss">Oylik zarur xarajatlar</label><input id="fEss" inputmode="numeric" value="${fmt(f.essentials)}"></div></div>
      <div class="ob-err" id="fErr"></div>
      <button class="btn" id="fSave">Saqlash va hisoblash</button>
      <p class="small muted mt">Ma'lumotlar faqat sessiya xotirasida turadi. Productionda bank bilan Open Banking orqali avtomatik keladi.</p></div>`;
  ["#fBal", "#fInc", "#fEss"].forEach(sel => moneyIn($(sel)));
  $("#fSave").onclick = async () => {
    const day = $("#fDay").value ? parseInt($("#fDay").value, 10) : null;
    if (day != null && (isNaN(day) || day < 1 || day > 28)) return ($("#fErr").textContent = "Oylik kuni 1 dan 28 gacha");
    try {
      S.auth = await api("/api/auth/finance", { method: "POST", body: { balance: moneyVal($("#fBal")), monthly_income: moneyVal($("#fInc")), payday: day, essentials: moneyVal($("#fEss")) } });
      toast("Saqlandi"); refresh();
    } catch (e) { $("#fErr").textContent = e.message; }
  };
}

function drawChart(t) {
  const canvas = $("#cashChart");
  if (!window.Chart) { canvas.parentElement.innerHTML = `<p class="muted">Grafik kutubxonasi yuklanmadi (internet yo'q). Raqamlar quyidagi jadvalda.</p>`; return; }
  if (S.chart) S.chart.destroy();
  const css = getComputedStyle(document.documentElement);
  const muted = css.getPropertyValue("--muted").trim(), border = css.getPropertyValue("--border").trim();
  // Reconstruct historical balance backwards from today's balance using daily net flows
  const hist = [];
  let b = t.balance;
  for (let i = t.history.length - 1; i >= 0; i--) { hist.unshift({ date: t.history[i].date, balance: b }); b -= t.history[i].net; }
  const today = { date: S.meta.today, balance: t.balance };
  const labels = [...hist.map(h => h.date), today.date, ...t.forecast.map(f => f.date)];
  const nH = hist.length;
  const histData = [...hist.map(h => h.balance), today.balance, ...t.forecast.map(() => null)];
  const fcData = [...hist.map(() => null), today.balance, ...t.forecast.map(f => f.balance)];
  const floor = t.need + t.buffer;
  const floorData = labels.map((_, i) => (i >= nH ? floor : null));
  const obligations = t.forecast.map(f => f.obligations.length ? f.balance : null);
  const oblNames = t.forecast.map(f => f.obligations.map(o => `${o.name}: ${som(o.amount)}`).join(", "));
  const M = v => (Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(0) + " mln" : Math.round(v / 1000) + " ming");
  S.chart = new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Tarixiy balans", data: histData, borderColor: "#1f5fd1", borderWidth: 2.5, pointRadius: 0, tension: .3 },
        { label: "Xavfsiz chegara", data: floorData, borderColor: "#c27a06", borderWidth: 1.5, borderDash: [4, 4], pointRadius: 0 },
        { label: "Prognoz", data: fcData, borderColor: "#6f9bff", borderWidth: 2.5, borderDash: [7, 5], pointRadius: 0, tension: .3,
          fill: { target: 1, above: "rgba(22,163,74,.18)", below: "rgba(211,59,59,.12)" } },
        { label: "To'lovlar", data: [...hist.map(() => null), null, ...obligations], showLine: false, pointStyle: "triangle", rotation: 180,
          pointRadius: 7, pointBackgroundColor: "#d33b3b", borderColor: "#d33b3b" },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: {
          title: items => dateUz(items[0].label),
          label: ctx => ctx.raw == null ? null : (ctx.datasetIndex === 3 ? "▼ " + oblNames[ctx.dataIndex - nH - 1] : `${ctx.dataset.label}: ${som(ctx.raw)}`),
        } },
      },
      scales: {
        x: { ticks: { color: muted, maxTicksLimit: 9, callback(v) { return dateUz(this.getLabelForValue(v)); } }, grid: { color: border } },
        y: { ticks: { color: muted, callback: v => M(v) }, grid: { color: border } },
      },
    },
  });
}

VIEWS.shifo = async v => {
  const d = await api(`/api/shifo/${S.pid}`);
  v.innerHTML = `<div class="view-head"><div><h1>🩺 Shifo <span class="pill badge-next">Keyingi bosqich</span></h1>
      <p>Qarz salomatligi: har bir kreditning haqiqiy narxi, qarz yuki va qaysi qarzni birinchi yopish foydali ekanini ko'rsatadi.</p></div>
      <button class="btn" id="shifoAiBtn">✨ AI strategiya</button></div>
    <div class="grid g4">
      <div class="card kpi"><div class="label">Jami qarz</div><div class="value">${som(d.total_debt)}</div></div>
      <div class="card kpi"><div class="label">Oylik to'lovlar</div><div class="value">${som(d.monthly_payments)}</div></div>
      <div class="card kpi"><div class="label">Qolgan foiz xarajati</div><div class="value red">${som(d.total_interest)}</div></div>
      <div class="card kpi"><div class="label">Qarz yuki (DTI)</div><div class="value ${d.dti > 0.35 ? "red" : ""}">${pct(d.dti)}</div><div class="sub">${d.dti > 0.35 ? "yuqori" : "me'yorda"} (chegara 35%)</div></div>
    </div>
    <div class="card mt"><h2>Kreditlar</h2><div class="table-wrap"><table><thead><tr><th>Kredit</th><th>Qoldiq</th><th>Stavka</th><th>Qolgan muddat</th><th>Oylik to'lov</th><th>Foiz xarajati</th></tr></thead><tbody>
      ${d.loans.map(l => `<tr><td><b>${esc(l.name)}</b></td><td class="num">${som(l.principal)}</td><td><span class="pill ${l.rate >= 0.3 ? "high" : l.rate > 0 ? "mid" : "low"}">${pct(l.rate)}</span></td>
        <td>${l.months_left} oy</td><td class="num">${som(l.monthly_payment)}</td><td class="num">${som(l.total_interest)}</td></tr>`).join("")}</tbody></table></div>
      <div class="grid g2 mt"><div class="hisob-item"><b>Avalanche</b> (eng qimmatdan): ${d.avalanche_order.map(esc).join(" → ")}</div>
        <div class="hisob-item"><b>Snowball</b> (eng kichikdan): ${d.snowball_order.map(esc).join(" → ")}</div></div>
      ${hisobBlock(d.hisob)}</div>
    ${isUser() ? `<div class="card mt" style="max-width:640px"><h2>Kredit qo'shish</h2>
      <div class="two mt"><div class="form-row"><label for="lName">Nomi</label><input id="lName" maxlength="60" placeholder="Masalan: Istemol krediti"></div>
        <div class="form-row"><label for="lP">Qoldiq (so'm)</label><input id="lP" inputmode="numeric"></div>
        <div class="form-row"><label for="lR">Yillik stavka (%)</label><input id="lR" inputmode="decimal" placeholder="24"></div>
        <div class="form-row"><label for="lM">Qolgan muddat (oy)</label><input id="lM" inputmode="numeric" placeholder="18"></div></div>
      <div class="ob-err" id="lErr"></div><button class="btn sm" id="lAdd">Qo'shish</button></div>` : ""}
    <div id="shifoAi" class="mt"></div>`;
  if (isUser()) {
    moneyIn($("#lP"));
    $("#lAdd").onclick = async () => {
      const body = { name: $("#lName").value.trim(), principal: moneyVal($("#lP")) || 0,
        rate: parseFloat(($("#lR").value || "").replace(",", ".")) / 100, months_left: parseInt($("#lM").value, 10) };
      if (body.name.length < 2 || !body.principal || isNaN(body.rate) || !body.months_left) return ($("#lErr").textContent = "Barcha maydonlarni to'ldiring");
      try { await api(`/api/shifo/${S.pid}/loans`, { method: "POST", body }); toast("Kredit qo'shildi"); refresh(); }
      catch (e) { $("#lErr").textContent = e.message; }
    };
  }
  $("#shifoAiBtn").onclick = () => { $("#shifoAi").innerHTML = ""; aiBox($("#shifoAi"), { preset: "shifo_explain", title: "Shifo strategiyasi" }); };
};

VIEWS.meros = async v => {
  const d = await api(`/api/meros/${S.pid}`);
  S.trusted = S.trusted || {};
  const trusted = S.trusted[S.pid] || null;
  v.innerHTML = `<div class="view-head"><div><h1>🕊 Meros <span class="pill badge-next">Keyingi bosqich</span></h1>
      <p>Favqulodda holatda yaqinlaringiz hisoblaringiz haqida bilmay qolmasligi uchun: ishonchli shaxs, faqat ko'rish huquqi va to'liq audit.</p></div>
      <button class="btn" id="merosAiBtn">✨ AI tushuntirsin</button></div>
    <div class="grid g2">
      <div class="card"><h2>Hisoblar xaritasi</h2>
        ${d.accounts.map(a => `<div style="display:flex;justify-content:space-between;margin:10px 0"><div>${esc(a.name)}<div class="mono muted">${esc(a.number || "")}</div></div><b class="num">${som(a.balance)}</b></div>`).join("")}
        <div class="nav-sep"></div><div class="small muted">Majburiyatlar: ${d.loans.map(esc).join(", ") || "yo'q"}</div></div>
      <div class="card"><h2>Ishonchli shaxs</h2>
        ${trusted ? `<p>✅ <b>${esc(trusted.name)}</b> (${esc(trusted.relation)}) — ${esc(trusted.phone)}</p><p class="small muted">Faqat ko'rish huquqi · pul o'tkaza olmaydi · har bir kirish audit qilinadi</p>
          <button class="btn ghost sm" id="trReset">O'zgartirish</button>` :
        `<div class="form-row"><label>Ism familiya</label><input id="trName" placeholder="Masalan: Dilnoza Karimova"></div>
         <div class="form-row"><label>Qarindoshlik</label><input id="trRel" placeholder="Masalan: opa"></div>
         <div class="form-row"><label>Telefon</label><input id="trPhone" placeholder="+998 ..."></div>
         <button class="btn" id="trSave">Saqlash (demo)</button><p class="small muted">Demo: faqat shu sahifa xotirasida, hech qayerga saqlanmaydi.</p>`}
      </div></div>
    <div id="merosAi" class="mt"></div>`;
  $("#merosAiBtn").onclick = () => { $("#merosAi").innerHTML = ""; aiBox($("#merosAi"), { preset: "meros_explain", title: "Meros" }); };
  const save = $("#trSave");
  if (save) save.onclick = () => {
    const t = { name: $("#trName").value.trim(), relation: $("#trRel").value.trim(), phone: $("#trPhone").value.trim() };
    if (!t.name) return toast("Ismni kiriting");
    S.trusted[S.pid] = t;
    toast("Ishonchli shaxs saqlandi (demo)"); refresh();
  };
  const reset = $("#trReset");
  if (reset) reset.onclick = () => { delete S.trusted[S.pid]; refresh(); };
};

VIEWS.audit = async v => {
  const [rows, ver] = await Promise.all([api(`/api/audit?limit=150`), api(`/api/audit/verify`)]);
  const ACTOR = { user: "👤 foydalanuvchi", agent: "🧭 AI agent", policy: "🛡 siyosat", system: "⚙️ tizim", bank: "🏦 bank" };
  v.innerHTML = `<div class="view-head"><div><h1>📜 Audit jurnali</h1>
      <p>Har bir qadam — tayyorlash, siyosat qarori, tasdiq, bajarish — o'zgartirib bo'lmaydigan zanjirga yoziladi: har yozuv oldingisining SHA-256 xeshini o'z ichiga oladi.</p></div>
      <div class="row-actions"><button class="btn" id="verBtn">🔍 Jurnal butunligini tekshirish</button>
      <button class="btn ghost sm" id="tamperBtn" title="Demo: bitta yozuvni yashirincha o'zgartirish">🧪 Buzib ko'rish (demo)</button>
      <button class="btn ghost sm" id="restoreBtn">♻️ Tiklash</button></div></div>
    <div class="card" id="verCard"><b>${ver.ok ? "✅" : "❌"} ${esc(ver.message)}</b></div>
    <div class="card mt"><div class="table-wrap"><table><thead><tr><th>#</th><th>Vaqt</th><th>Kim</th><th>Hodisa</th><th>Tafsilot</th><th>Xesh</th></tr></thead><tbody>
      ${rows.map(r => `<tr ${ver.broken_id === r.id ? 'style="background:var(--red-soft)"' : ""}><td>${r.id}</td><td class="small">${timeUz(r.ts)}</td><td class="small">${ACTOR[r.actor] || esc(r.actor)}</td>
        <td><span class="mono">${esc(r.event)}</span><div class="small muted">${esc(r.profile_id)}</div></td>
        <td class="small">${esc(JSON.stringify(r.payload)).slice(0, 160)}</td>
        <td class="mono muted" title="prev: ${esc(r.prev_hash)}">${esc(r.hash.slice(0, 10))}…</td></tr>`).join("") || `<tr><td colspan="6" class="muted">Jurnal bo'sh</td></tr>`}
    </tbody></table></div></div>`;
  $("#verBtn").onclick = async () => {
    const r = await api("/api/audit/verify");
    $("#verCard").innerHTML = `<b>${r.ok ? "✅" : "❌"} ${esc(r.message)}</b>`;
    $("#verCard").classList.add("highlight-pulse");
    setTimeout(() => $("#verCard")?.classList.remove("highlight-pulse"), 3300);
  };
  $("#tamperBtn").onclick = async () => { const r = await api("/api/audit/tamper-demo", { method: "POST" }); toast(r.ok ? `#${r.tampered_id} yozuv yashirincha o'zgartirildi — endi tekshiring` : "Jurnal bo'sh"); };
  $("#restoreBtn").onclick = async () => { await api("/api/audit/restore-demo", { method: "POST" }); toast("Asl holat tiklandi"); refresh(); };
};

VIEWS.security = async v => {
  const d = await api(`/api/security/${S.pid}`);
  const items = [
    ["Telefon + SMS kod", "Kirish va karta qo'shish alohida 6 xonali SMS kod bilan tasdiqlanadi. Kod serverda faqat xesh ko'rinishida, 5 daqiqa amal qiladi; 3 marta xato — 5 daqiqa blok."],
    ["CVV va PIN so'ralmaydi", "Karta raqami faqat brauzerda Luhn bilan tekshiriladi va darhol o'chiriladi. Serverga faqat oxirgi 4 raqam, karta turi va egasining ismi boradi."],
    ["Ma'lumotlar saqlanmaydi", "Profil, karta, balans va ko'chirma faqat sessiya xotirasida. \"Chiqish\" ularni darhol o'chiradi; brauzer xotirasiga (localStorage) shaxsiy ma'lumot yozilmaydi."],
    ["PII yashirish", "Ism, karta, telefon, email va hisob raqamlari AI'ga yuborilishidan oldin [ISM_1], [KARTA_1] kabi tokenlarga almashtiriladi va javobda qayta tiklanadi."],
    ["Karta niqoblash", "Kartalar hamma joyda 8600 **** **** 4421 ko'rinishida."],
    ["Rozilik", "Ma'lumotlar faqat rozilikdan keyin tahlil qilinadi; rozilikni istalgan payt bekor qilish mumkin."],
    ["O'zgarmas audit", "Har bir yozuv oldingisining SHA-256 xeshi bilan zanjirlangan; o'zgartirish darhol aniqlanadi."],
    ["Eng kam huquq", "AI faqat o'qiydi va amal TAYYORLAYDI. Bajarish — faqat sizning tasdig'ingiz yoki limit ichidagi siyosat orqali."],
    ["Kalit serverda", "AI API kaliti faqat serverda saqlanadi; /api/agent so'rovlar soni cheklangan; CSV hajmi va ustunlari tekshiriladi."],
  ];
  v.innerHTML = `<div class="view-head"><div><h1>🔒 Xavfsizlik va maxfiylik</h1><p>Moliyaviy ma'lumot — eng sezgir ma'lumot. FinPilot uni qanday himoya qiladi:</p></div></div>
    <div class="grid g2">
      <div class="card"><h2>Himoya choralari</h2><ul class="check-list mt">${items.map(([t, x]) => `<li><span class="ok">✓</span><div><b>${t}</b><div class="small muted">${x}</div></div></li>`).join("")}</ul></div>
      <div class="card"><h2>Rozilik</h2>
        <p>${d.consent.granted ? `✅ Berilgan: ${timeUz(d.consent.granted_at)}` : "❌ Berilmagan"}</p>
        ${d.consent.granted ? `<button class="btn danger sm" id="revoke">Rozilikni bekor qilish</button>` : `<button class="btn sm" id="grant">Rozilik berish</button>`}
        <div class="nav-sep"></div>
        <h2>Audit zanjiri</h2><p>${d.audit.ok ? "✅" : "❌"} ${esc(d.audit.message)}</p>
        <div class="nav-sep"></div>
        <h2>AI rejimi</h2><p>${d.ai_enabled ? "● Jonli AI (Claude)" : "● Offline demo rejimi — AI'ga hech narsa yuborilmaydi"}</p>
        <p class="small muted">SMS: ${d.sms_provider === "eskiz" ? "Eskiz.uz" : "demo (kod ekranda ko'rsatiladi)"}</p></div>
    </div>
    ${d.stored ? `<div class="card mt"><div class="card-head"><h2>🗂 Siz haqingizda nima saqlanyapti?</h2><span class="pill green">faqat sessiya</span></div>
      ${kv({ "Karta": `${d.stored.card.type === "humo" ? "Humo" : "UzCard"} •••• ${d.stored.card.last4} (${d.stored.card.exp})`, "Karta egasi": d.stored.card.holder,
        "To'liq karta raqami": "saqlanmaydi ✓", "CVV / PIN": "hech qachon so'ralmaydi ✓", "Telefon": d.stored.phone,
        "Ko'chirma": d.stored.statement_rows ? d.stored.statement_rows + " ta tranzaksiya" : "yuklanmagan", "Qayerda": d.stored.where })}
      <div class="row-actions mt"><button class="btn danger" id="wipeBtn">🗑 Chiqish / ma'lumotlarni o'chirish</button></div></div>` : ""}
    <div class="card mt"><div class="card-head"><h2>👁 AI'ga nima yuborildi?</h2><span class="pill gray">oxirgi so'rov</span></div>
      ${d.last_payload.length ? `<p class="small muted">Quyida oxirgi AI so'rovida modelga yuborilgan ma'lumot — e'tibor bering: ism, karta va telefon tokenlar bilan almashtirilgan.</p>
        <pre class="payload">${esc(d.last_payload.map(p => `── ${p.role}${p.name ? " · " + p.name : ""} ──\n${p.content}`).join("\n\n"))}</pre>`
        : `<p class="muted">Hali AI so'rovi bo'lmagan. Qalqon'da "Bekor qilish xati"ni bosing va shu yerga qayting.</p>`}</div>`;
  const r = $("#revoke"), g = $("#grant");
  if (r) r.onclick = async () => { await api(`/api/consent/${S.pid}/revoke`, { method: "POST" }); toast("Rozilik bekor qilindi"); refresh(); };
  if (g) g.onclick = async () => { await api(`/api/consent/${S.pid}/grant`, { method: "POST" }); toast("Rozilik berildi"); refresh(); };
  if ($("#wipeBtn")) $("#wipeBtn").onclick = askLogout;
};

VIEWS.how = async v => {
  v.innerHTML = `<div class="view-head"><div><h1>🧩 Qanday ishlaydi</h1><p>Asosiy qoida: <b>raqamlarni kod hisoblaydi, so'zlarni AI yozadi.</b> Shuning uchun AI hech qachon summa yoki stavka "to'qib chiqarmaydi".</p></div></div>
    <div class="card arch"><h2>Arxitektura</h2>
    <svg viewBox="0 0 900 330" role="img" aria-label="Arxitektura sxemasi" font-family="inherit" font-size="13">
      <defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0L10,5L0,10z" fill="currentColor"/></marker></defs>
      <g fill="none" stroke="currentColor" opacity=".35" stroke-width="1.5" marker-end="url(#ar)" style="color:var(--muted)">
        <path d="M170 165 H245"/><path d="M455 120 H535"/><path d="M455 210 H535"/><path d="M745 120 H790"/><path d="M745 215 H790"/><path d="M350 225 V265"/></g>
      ${[[20, 120, 150, 90, "📱 Bank ilovasi", "FinPilot moduli (UI)"], [245, 70, 210, 155, "⚙️ FastAPI backend", "Qalqon · O'sish · Shifo"],
         [535, 70, 210, 95, "🧭 AI agent (Claude)", "tool calling, oqimli javob"], [535, 180, 210, 70, "🧮 Deterministik yadro", "formula + testlar"],
         [790, 80, 100, 80, "🏦 Bank API", "adapter"], [790, 180, 100, 70, "📜 Audit", "SHA-256 zanjir"],
         [245, 265, 210, 50, "🔒 PII · rozilik · siyosat", ""]].map(([x, y, w, h, t, s]) =>
        `<g><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="12" fill="var(--surface-2)" stroke="var(--border)"/>
          <text x="${x + w / 2}" y="${y + h / 2 - (s ? 4 : -4)}" text-anchor="middle" fill="var(--text)" font-weight="700">${t}</text>
          ${s ? `<text x="${x + w / 2}" y="${y + h / 2 + 15}" text-anchor="middle" fill="var(--muted)" font-size="11.5">${s}</text>` : ""}</g>`).join("")}
    </svg></div>
    <div class="grid g3 mt">
      <div class="card"><h2>🤖 Generativ AI — yadro</h2><p class="muted small">Agent savolni tushunadi, kerakli vositalarni (8 ta tool) o'zi tanlaydi, natijani o'zbek tilida tushuntiradi, bekor qilish xatlarini yozadi va amallarni tayyorlaydi. Har javob ostida "Hisoblandi" bloki bor.</p></div>
      <div class="card"><h2>🛡 Ishonch</h2><p class="muted small">Tayyorlash → Tasdiqlash → Bajarish → Audit. Autonomiya darajasini foydalanuvchi o'zi tanlaydi; avtomatik amallar 24 soat ichida bekor qilinadi.</p></div>
      <div class="card"><h2>💼 Biznes-model (B2B2C)</h2><p class="muted small">Banklar FinPilot'ni o'z ilovasiga o'rnatadi: faol foydalanuvchi uchun oylik litsenziya + FinPilot orqali ochilgan depozitlardan ulush. Mijoz uchun bepul. Kengayish: bitta hamkor bank → boshqa banklar va to'lov ilovalari → Markaziy Osiyo.</p></div>
    </div>
    <div class="card mt"><h2>Prototipda nima simulyatsiya qilingan</h2><ul class="small muted">
      <li>Bank API (MockBank: 0,3–0,8 s kechikish, ba'zan xato → qayta urinish). Productionda — hamkor bank API yoki open banking shlyuzi.</li>
      <li>SMS yuborish: demo rejimida kod ekrandagi "SMS" bannerda ko'rsatiladi. <span class="mono">SMS_PROVIDER=eskiz</span> bilan Eskiz.uz adapteri ulanadi.</li>
      <li>Kartadagi balans: qo'lda kiritiladi yoki CSV'dan. Bank bilan avtomatik sinxronlash — Open Banking (yo'l xaritasi).</li>
      <li>Ikki demo profil ma'lumotlari va demo stavkalar.</li><li>Xizmatdan foydalanish signallari (sport zalga oxirgi tashrif va h.k.).</li>
      <li>AI kaliti bo'lmasa — "Offline demo rejimi": raqamlar o'sha hisob-kitobdan, matn shablon (ekranda belgilanadi).</li></ul></div>`;
};

// ------------------------------------------------------------------ chat
const CHIPS = {
  aziza: ["Qaysi obunalarimni bekor qilsam bo'ladi?", "Bo'sh pulimni qayerga qo'yay?", "Qaysi qarzni birinchi yopay?"],
  salomat: ["Dorixonada ortiqcha pul bormi?", "Keyingi 2 haftadagi to'lovlar qanday?", "Kassa dasturiga ikki marta to'layapmanmi?"],
};
function resetChat() {
  S.conv[S.pid] = null;
  $("#chatBody").innerHTML = `<div class="small muted">Salom! Men FinPilot. Moliyangiz haqida so'rang — men hisob-kitob qilib, tushuntirib beraman va kerak bo'lsa amalni tayyorlayman.</div>`;
  $("#chatChips").innerHTML = (CHIPS[S.pid] || CHIPS.aziza).map(c => `<button class="chip">${esc(c)}</button>`).join("");
  $$("#chatChips .chip").forEach(b => b.onclick = () => sendChat(b.textContent));
}
function sendChat(text) {
  text = text.trim();
  if (!text) return;
  $("#chatBody").insertAdjacentHTML("beforeend", `<div class="msg-user">${esc(text)}</div>`);
  const btn = $("#chatForm button"); btn.disabled = true;
  aiBox($("#chatBody"), { message: text, conversation: true, title: "FinPilot", onDone: () => { btn.disabled = false; } });
  const body = $("#chatBody");
  const keep = setInterval(() => { body.scrollTop = body.scrollHeight; }, 200);
  setTimeout(() => clearInterval(keep), 15000);
}
function openChat(open = true) { $("#chat").classList.toggle("open", open); if (open) setTimeout(() => $("#chatInput").focus(), 250); }

// ------------------------------------------------------------------ demo mode (covers every feature; manual or autoplay)
const D = { token: 0, busy: false, auto: false, timer: null };
class DemoCancel extends Error {}
async function dwait(ms) { const t = D.token; await wait(ms); if (t !== D.token) throw new DemoCancel(); }
async function dfind(sel, ms = 8000) {
  const t0 = Date.now(), t = D.token;
  for (;;) {
    if (t !== D.token) throw new DemoCancel();
    const el = $(sel);
    if (el) return el;
    if (Date.now() - t0 > ms) throw new Error("topilmadi: " + sel);
    await wait(100);
  }
}
async function dclick(sel, pause = 450) {
  const el = await dfind(sel);
  el.scrollIntoView({ block: "center", behavior: "smooth" });
  await dwait(pause);
  el.click();
  return el;
}
async function dset(sel, value) { const el = await dfind(sel); el.value = ""; await typeSlow(el, String(value), 35); return el; }
async function waitAi(scopeSel, ms = 30000) {
  await dwait(400);
  const t0 = Date.now();
  while ($(`${scopeSel} .ai-text.cursor`) && Date.now() - t0 < ms) await dwait(200);
  await dwait(300);
}
async function confirmAction(pause = 1800) {
  await dwait(pause);                       // let the audience read the proposal
  await dclick("#mYes", 200);
  await dfind("#mClose", 15000);
  await dwait(1800);
  $("#mClose")?.click();
}
async function dscroll(sel) { const el = await dfind(sel); el.scrollIntoView({ block: "start", behavior: "smooth" }); }

const DEMO = [
  { t: "1. Yangi mijoz ro'yxatdan o'tadi: telefon → SMS kod → ism → Humo karta (CVV va PIN so'ralmaydi, karta raqami serverga ketmaydi) → karta SMS tasdig'i → rozilik va ko'chirma.",
    dur: 2500, run: async () => { await autoOnboard(); for (let i = 0; i < 60 && S.mode !== "user"; i++) await dwait(200); } },
  { t: "2. Kabinet ochildi. \"Xavfsizlik\"da ko'ramiz: serverda faqat karta turi va oxirgi 4 raqam — to'liq raqam ham, CVV ham yo'q. Hammasi faqat sessiyada.",
    dur: 3500, run: async () => { await go("security"); await dscroll("#wipeBtn"); } },
  { t: "3. Tayyor demo profil — Aziza: 90 kunlik ko'chirma va xizmatdan foydalanish signallari. Qalqon tranzaksiyalarni tekshiradi.",
    dur: 3000, run: async () => { await ensureProfile("aziza"); await go("qalqon"); await dclick("#loadBtn"); await dfind("[data-block]"); } },
  { t: "4. 4 ta muammo: sinovdan pullikka o'tgan obuna, ikki kanaldan to'lov, 97 kun ishlatilmagan sport zal, xabarsiz narx oshishi. AI tushuntiradi — har raqam ostida \"Hisoblandi\".",
    dur: 2500, run: async () => { await dclick("#explainBtn"); await dscroll("#qalqonAi"); await waitAi("#qalqonAi"); $("#qalqonAi details.hisob")?.setAttribute("open", ""); } },
  { t: "5. AI Yandex Plus uchun bekor qilish va pulni qaytarish xatini yozadi — faqat ko'chirmadagi faktlar bilan. Nusxa olish yoki email.",
    dur: 1500, run: async () => { await dclick("[data-letter^='yandex']"); await waitAi("#modal"); await dwait(1500); await dclick("#lCopy"); await dwait(1500); closeModal(); } },
  { t: "6. Megogo narxi 39 000 → 49 000 so'mga oshgan. Karta limitini eski narxga qo'yamiz: Tayyorlash → Tasdiqlash → Bank → Audit.",
    dur: 1500, run: async () => { await go("qalqon"); await dclick("[data-limit^='megogo']"); await dset("#limVal", "39000"); await dwait(900); await dclick("#lmGo"); await confirmAction(); } },
  { t: "7. Ishlatilmayotgan sport zal to'lovini bloklaymiz. \"Allaqachon tejaldi\" hisoblagichi o'sadi.",
    dur: 3000, run: async () => { await go("qalqon"); await dclick("[data-block^='sport']"); await confirmAction(); await dwait(600); window.scrollTo({ top: 0, behavior: "smooth" }); } },
  { t: "8. Avtonomiya \"Limit ichida avtomatik\" (500 000 so'm): Telegram dublikatiga limit — FinPilot o'zi bajaradi. Avtomatik amalni 24 soat ichida bekor qilish mumkin.",
    dur: 2500, run: async () => {
      await saveSettings("auto", 500000); await dwait(1200);
      await go("qalqon"); await dclick("[data-limit^='telegram']"); await dset("#limVal", "0"); await dwait(700); await dclick("#lmGo");
      await dwait(2500); await go("home"); await dscroll(".feed"); await dwait(1500);
      await dclick(".feed [data-undo]"); await dwait(1800); await saveSettings("one_click", 500000);
    } },
  { t: "9. Chat: mijoz o'zbek tilida savol beradi — agent kerakli hisob-kitobni o'zi chaqiradi va tushuntiradi.",
    dur: 2500, run: async () => { openChat(true); await dwait(600); await typeSlow($("#chatInput"), "Qaysi qarzimni birinchi yopay?", 25); await dwait(300); $("#chatForm").requestSubmit(); await waitAi("#chatBody"); } },
  { t: "10. Shifo: har bir kreditning haqiqiy narxi va qarz yuki (DTI). AI avalanche va snowball strategiyalarini solishtiradi.",
    dur: 2500, run: async () => { openChat(false); await go("shifo"); await dclick("#shifoAiBtn"); await dscroll("#shifoAi"); await waitAi("#shifoAi"); } },
  { t: "11. Bosh sahifa: moliyaviy salomatlik o'sdi, modullar sinergiyasi va \"FinPilot bugun nima qildi\" lentasi.",
    dur: 2500, run: async () => { await go("home"); await dwait(1200); await dclick("#aiSummaryBtn"); await waitAi("#aiSummary"); await dscroll("#synergy"); } },
  { t: "12. Endi biznes — Dorixona \"Salomat\". AI G'aznachi to'lov jadvalini prognoz qiladi: ish haqi, ijara, yetkazib beruvchilar.",
    dur: 3500, run: async () => { await ensureProfile("salomat"); await go("osish"); await dscroll(".chart-box"); } },
  { t: "13. Xavfsizlik buferini 15% → 30% qilsak, bo'sh pul kamayadi. Xavfni mijozning o'zi boshqaradi.",
    dur: 2000, run: async () => {
      const r = await dfind("#bufRange"); r.value = 30; r.dispatchEvent(new Event("input")); await dwait(2600);
      await dscroll("#idleVal"); await dwait(2200);
      const r2 = await dfind("#bufRange"); r2.value = 15; r2.dispatchEvent(new Event("input")); await dwait(1500);
    } },
  { t: "14. 7 kunlik depozit ish haqidan 2 kun oldin qaytadi. 30 kunlik depozit va obligatsiya mos emas — AI sababini aytadi.",
    dur: 2500, run: async () => { await dclick("#osishAiBtn"); await waitAi("#osishAi"); } },
  { t: "15. Depozit ochish: summa, stavka, qaytish sanasi va daromad — tasdiqlashdan oldin hammasi ko'rinadi.",
    dur: 2000, run: async () => { await dclick("#openDep"); await confirmAction(3000); await dwait(800); } },
  { t: "16. Meros: favqulodda holat uchun ishonchli shaxs — faqat ko'rish huquqi, pul o'tkaza olmaydi.",
    dur: 2500, run: async () => { await ensureProfile("aziza"); await go("meros"); await dset("#trName", "Dilnoza Karimova"); await dset("#trRel", "opa"); await dset("#trPhone", "+998 90 765 43 21"); await dwait(400); await dclick("#trSave"); } },
  { t: "17. Audit jurnali: har bir qadam SHA-256 zanjirida. Yozuvni yashirincha o'zgartirib ko'ramiz — tizim darhol aniqlaydi.",
    dur: 2500, run: async () => {
      await go("audit"); await dclick("#verBtn"); await dwait(2200); await dclick("#tamperBtn"); await dwait(1500);
      await dclick("#verBtn"); await dwait(3200); await dclick("#restoreBtn"); await dwait(1200); await dclick("#verBtn");
    } },
  { t: "18. \"AI'ga nima yuborildi?\" — ism, karta, telefon tokenlar bilan almashtirilgan: [ISM_1], [KARTA_1], [TEL_1].",
    dur: 4000, run: async () => { await go("security"); await dscroll("pre.payload"); } },
  { t: "19. Qanday ishlaydi: arxitektura, \"raqamlarni kod hisoblaydi, so'zlarni AI yozadi\" va B2B2C biznes-model.",
    dur: 4000, run: async () => { await go("how"); } },
  { t: "20. Chiqish — barcha shaxsiy ma'lumotlar o'chiriladi. FinPilot: himoya qiladi, o'stiradi, qarzni yengillashtiradi.",
    dur: 3000, run: async () => { await doLogout(); } },
];
async function enterDemoSession() {
  S.auth = await api("/api/auth/demo", { method: "POST" });
  for (const p of S.meta.profiles) await api(`/api/consent/${p.id}/grant`, { method: "POST" });
  S.mode = "demo";
}
async function ensureProfile(pid) {
  closeModal(); obHide();
  if (S.mode !== "demo") { await enterDemoSession(); S.pid = pid; await startApp(); return; }
  if (S.pid !== pid) await switchProfile(pid);
}
function renderDemo() {
  const bar = $("#demoBar");
  if (S.demoStep < 0) { bar.classList.add("hidden"); return; }
  const s = DEMO[S.demoStep], last = S.demoStep === DEMO.length - 1;
  bar.classList.remove("hidden");
  bar.innerHTML = `<span class="step">${S.demoStep + 1}/${DEMO.length}</span><span class="txt">${esc(s.t.replace(/^\d+\.\s*/, ""))}</span>
    <button class="btn ghost sm" id="dPrev" ${S.demoStep === 0 ? "disabled" : ""} title="Oldingi">←</button>
    <button class="btn ghost sm" id="dAuto" title="Avtomatik o'ynatish (video uchun)">${D.auto ? "⏸ Pauza" : "⏵ Avto"}</button>
    <button class="btn green sm" id="dNext" ${D.busy ? "disabled" : ""}>${D.busy ? '<span class="spinner"></span>' : last ? "Tugatish" : "Keyingi →"}</button>
    <button class="btn ghost sm" id="dExit" title="Demoni to'xtatish">✕</button>`;
  $("#dPrev").onclick = () => runDemo(S.demoStep - 1);
  $("#dNext").onclick = () => (last ? stopDemo() : runDemo(S.demoStep + 1));
  $("#dAuto").onclick = () => { D.auto = !D.auto; renderDemo(); if (D.auto && !D.busy) scheduleNext(); else clearTimeout(D.timer); };
  $("#dExit").onclick = stopDemo;
}
function scheduleNext() {
  clearTimeout(D.timer);
  if (!D.auto || S.demoStep < 0) return;
  D.timer = setTimeout(() => {
    if (S.demoStep === DEMO.length - 1) { D.auto = false; stopDemo(); toast("Demo tugadi ✓"); }
    else runDemo(S.demoStep + 1);
  }, DEMO[S.demoStep].dur || 2500);
}
async function runDemo(i) {
  clearTimeout(D.timer);
  const token = ++D.token;
  S.demoStep = i; D.busy = true;
  renderDemo();
  try { await DEMO[i].run(); }
  catch (e) { if (!(e instanceof DemoCancel)) { console.warn("demo step", i + 1, e); toast("Demo qadami to'liq bajarilmadi — davom eting", 2500); } }
  if (token !== D.token) return;           // a newer step took over
  D.busy = false;
  renderDemo();
  scheduleNext();
}
function startDemo() {
  const box = openModal(`<h2>▶ Demo rejimi</h2><p class="muted">Demo holati tozalanadi (amallar, audit, joriy sessiya). Ssenariy ${DEMO.length} qadamda ilovaning barcha imkoniyatlarini ko'rsatadi: onboarding, Qalqon, avtonomiya, chat, Shifo, O'sish, Meros, audit, xavfsizlik va chiqish.</p>
    <p class="small muted">"Qo'lda" — har qadamni "Keyingi →" bilan o'zingiz o'tkazasiz (jonli taqdimot uchun). "Avtomatik" — hammasi o'zi o'ynaydi (~5 daqiqa, video yozish uchun).</p>
    <div class="modal-actions"><button class="btn ghost" id="dmNo">Bekor</button><button class="btn" id="dmAuto">⏵ Avtomatik</button><button class="btn green" id="dmYes">Qo'lda boshlash</button></div>`);
  $("#dmNo", box).onclick = closeModal;
  const begin = async auto => {
    closeModal();
    D.auto = auto;
    await enterDemoSession();
    await api("/api/demo/reset", { method: "POST" });
    for (const pid of ["aziza", "salomat"]) await api(`/api/settings/${pid}`, { method: "PUT", body: { autonomy: "one_click", auto_limit: 500000 } });
    S.bufferPct = {}; S.trusted = {}; S.pid = "aziza";
    await doLogout();
    runDemo(0);
  };
  $("#dmYes", box).onclick = () => begin(false);
  $("#dmAuto", box).onclick = () => begin(true);
}
function stopDemo() { D.token++; D.busy = false; D.auto = false; clearTimeout(D.timer); S.demoStep = -1; renderDemo(); }

// ------------------------------------------------------------------ boot
async function boot() {
  $("#themeBtn").onclick = () => {
    const cur = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("fp-theme", next); } catch (e) { /* ignore */ }
    if (S.view === "osish") refresh();
  };
  $("#chatFab").onclick = () => openChat(true);
  $("#chatClose").onclick = () => openChat(false);
  $("#chatNew").onclick = resetChat;
  $("#chatForm").onsubmit = e => { e.preventDefault(); const i = $("#chatInput"); sendChat(i.value); i.value = ""; };
  $("#demoBtn").onclick = startDemo;
  $("#logoutBtn").onclick = askLogout;
  $("#limitInput").onchange = e => saveSettings("auto", parseInt(e.target.value.replace(/\D/g, ""), 10) || 0);

  S.meta = await api("/api/meta");
  await refreshAuth();
  renderTopbar();
  renderNav();
  await obRoute();
}

/** Called once the session is "ready" (onboarded user or demo). */
async function startApp() {
  S.mode = S.auth.mode;
  if (S.mode === "user") S.pid = S.auth.pid;
  else if (!S.meta.profiles.some(p => p.id === S.pid)) S.pid = "aziza";
  S.settings = await api(`/api/settings/${S.pid}`);
  renderTopbar();
  resetChat();
  await go("home");
  if (S.mode === "demo") {
    const consent = await api(`/api/consent/${S.pid}`);
    if (!consent.granted) showConsent();
  }
}
boot().catch(e => { $("#view").innerHTML = `<div class="card"><b>Ishga tushmadi:</b> ${esc(e.message)}</div>`; });
