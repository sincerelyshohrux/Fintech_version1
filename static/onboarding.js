/* FinPilot onboarding & auth: phone → SMS OTP → profile → (locked dashboard) → card → card OTP → consent & balance.
   Loaded before app.js; uses its helpers ($, api, esc, som, toast, S) at call time only. */
"use strict";

const OB = { resendTimer: null, lockTimer: null, statementRows: 0, balanceMode: "balance", openCard: false };
const OB_NUM = { phone: 1, otp: 2, profile: 3, card: 5, card_otp: 6, setup: 7 };
const NAME_RE = /^[A-Za-zА-Яа-яЁёЎўҚқҒғҲҳ'ʻʼ’‘`´\- ]{2,30}$/;
const APOS_RE = /['ʻʼ’‘`´]/g;

// ------------------------------------------------------------------ pure helpers (mirrored on the server)
function luhnOk(digits) {
  if (!/^\d{16}$/.test(digits)) return false;
  let sum = 0;
  for (let i = 0; i < 16; i++) {
    let d = +digits[15 - i];
    if (i % 2) { d *= 2; if (d > 9) d -= 9; }
    sum += d;
  }
  return sum % 10 === 0;
}
function cardTypeOf(digits) { return digits.startsWith("8600") ? "uzcard" : digits.startsWith("9860") ? "humo" : null; }
const CARD_LABEL = { uzcard: "UzCard", humo: "Humo" };
function normName(s) { return (s || "").normalize("NFKC").toLowerCase().replace(APOS_RE, "").replace(/[\s-]+/g, " ").trim(); }
function holderMatches(holder, first, last) {
  const a = normName(holder).split(" ").sort().join(" "), b = normName(first + " " + last).split(" ").sort().join(" ");
  return a === b;
}
function formatPhone(raw) {
  let d = (raw || "").replace(/\D/g, "");
  if (d.startsWith("998")) d = d.slice(3);
  d = d.slice(0, 9);
  const parts = [d.slice(0, 2), d.slice(2, 5), d.slice(5, 7), d.slice(7, 9)].filter(Boolean);
  return "+998" + (parts.length ? " " + parts.join(" ") : " ");
}
function moneyIn(el) {
  el.addEventListener("input", () => {
    const d = el.value.replace(/\D/g, "").slice(0, 12);
    el.value = d ? d.replace(/\B(?=(\d{3})+(?!\d))/g, " ") : "";
  });
}
function moneyVal(el) { const d = (el?.value || "").replace(/\D/g, ""); return d ? parseInt(d, 10) : null; }

// ------------------------------------------------------------------ SMS banner (demo mode only)
function showSms(text) {
  if (!text) return;
  const b = $("#smsBanner");
  b.innerHTML = `<div class="head"><span class="ico">✉</span><b>Xabarlar</b> · hozir<span class="demo-tag">DEMO SMS</span></div><div class="body">${esc(text)}</div>`;
  b.classList.add("show");
  clearTimeout(b._h);
  b._h = setTimeout(() => b.classList.remove("show"), 12000);
  b.onclick = () => b.classList.remove("show");
}

// ------------------------------------------------------------------ shell
function obShow(stage, html, overlay = false) {
  clearInterval(OB.resendTimer); clearInterval(OB.lockTimer);
  const w = $("#onboard");
  w.classList.toggle("overlay", overlay);
  w.classList.remove("hidden");
  const n = OB_NUM[stage];
  w.innerHTML = `<div class="ob-card">
    <div class="ob-top"><div class="brand" style="padding:0"><div class="logo">🧭</div><div>FinPilot<small>AI moliyaviy agent</small></div></div>
      <div style="text-align:right"><div class="small muted">${n}/7 qadam</div><div class="ob-steps">${[1, 2, 3, 4, 5, 6, 7].map(i => `<i class="${i <= n ? "on" : ""}"></i>`).join("")}</div></div></div>
    ${html}</div>`;
  const first = w.querySelector("input:not([type=file]):not([type=checkbox])");
  if (first) setTimeout(() => first.focus(), 60);
  return $(".ob-card", w);
}
function obHide() { clearInterval(OB.resendTimer); clearInterval(OB.lockTimer); $("#onboard").classList.add("hidden"); $("#onboard").innerHTML = ""; }
function obErr(card, msg) { const e = $(".ob-err", card); if (e) e.textContent = msg || ""; }
function busy(btn, on, label) {
  if (!btn) return;
  if (on) { btn.dataset.label = btn.innerHTML; btn.disabled = true; btn.innerHTML = `<span class="spinner"></span> ${label || "Kuting…"}`; }
  else { btn.disabled = false; btn.innerHTML = btn.dataset.label || btn.innerHTML; }
}

async function refreshAuth() { S.auth = await api("/api/auth/me"); return S.auth; }

/** Decide what to show from the server-side stage. */
async function obRoute() {
  const st = S.auth.stage;
  if (st === "ready") { obHide(); return startApp(); }
  if (st === "phone") return obPhone();
  if (st === "otp") return obOtp("login");
  if (st === "profile") return obProfile();
  // card / card_otp / setup: the (locked) dashboard is visible behind the overlay
  enterLocked();
  if (st === "card_otp") return obOtp("card");
  if (st === "setup") return obSetup();
  if (OB.openCard) return obCard();
  obHide();
}

// ------------------------------------------------------------------ STEP 1: phone
function obPhone() {
  const c = obShow("phone", `
    <h2>Telefon raqamingiz</h2><p>Kirish uchun raqamingizga 6 xonali tasdiqlash kodi yuboramiz.</p>
    <form id="obForm" novalidate>
      <div class="form-row"><label for="obPhone">Telefon raqami</label>
        <input id="obPhone" inputmode="tel" autocomplete="tel" value="+998 " aria-describedby="obPhoneErr"></div>
      <div class="ob-err" id="obPhoneErr"></div>
      <button class="btn block" id="obSend">Kod yuborish</button>
    </form>
    <div class="ob-alt"><span class="small muted">Hakamlar uchun:</span><button class="ob-link" id="obDemo">Demo profil bilan ko'rish →</button></div>`);
  const inp = $("#obPhone", c);
  inp.addEventListener("input", () => { inp.value = formatPhone(inp.value); obErr(c, ""); });
  $("#obForm", c).onsubmit = async e => {
    e.preventDefault();
    const digits = inp.value.replace(/\D/g, "").slice(3);
    if (digits.length !== 9) return obErr(c, "Raqam +998 XX XXX XX XX formatida bo'lishi kerak");
    const b = $("#obSend", c); busy(b, true, "Yuborilmoqda…");
    try {
      const r = await api("/api/auth/phone", { method: "POST", body: { phone: inp.value } });
      showSms(r.demo_sms);
      S.auth = r.state; OB.resendIn = r.resend_in;
      obRoute();
    } catch (err) { busy(b, false); obErr(c, err.message); }
  };
  $("#obDemo", c).onclick = async () => { S.auth = await api("/api/auth/demo", { method: "POST" }); obRoute(); };
}

// ------------------------------------------------------------------ STEP 2 & 6: OTP
function otpBoxes(wrap, onDone) {
  wrap.innerHTML = Array.from({ length: 6 }, (_, i) =>
    `<input inputmode="numeric" maxlength="1" aria-label="${i + 1}-raqam" ${i === 0 ? 'autocomplete="one-time-code"' : 'autocomplete="off"'}>`).join("");
  const boxes = [...wrap.querySelectorAll("input")];
  const code = () => boxes.map(b => b.value).join("");
  const fill = (digits, from = 0) => {
    digits.split("").forEach((d, k) => { if (boxes[from + k]) boxes[from + k].value = d; });
    const next = boxes.find(b => !b.value) || boxes[5];
    next.focus();
    if (code().length === 6) onDone(code());
  };
  boxes.forEach((b, i) => {
    b.addEventListener("input", () => {
      const d = b.value.replace(/\D/g, "");
      b.value = "";
      if (d) fill(d.slice(0, 6 - i), i);
      wrap.classList.remove("bad");
    });
    b.addEventListener("keydown", e => {
      if (e.key === "Backspace" && !b.value && i > 0) { boxes[i - 1].value = ""; boxes[i - 1].focus(); e.preventDefault(); }
      if (e.key === "ArrowLeft" && i > 0) boxes[i - 1].focus();
      if (e.key === "ArrowRight" && i < 5) boxes[i + 1].focus();
    });
    b.addEventListener("paste", e => { e.preventDefault(); fill((e.clipboardData.getData("text") || "").replace(/\D/g, "").slice(0, 6), 0); });
  });
  return {
    clear() { boxes.forEach(b => (b.value = "")); boxes[0].focus(); },
    disable(on) { boxes.forEach(b => (b.disabled = on)); if (!on) boxes[0].focus(); },
    bad() { wrap.classList.remove("bad"); void wrap.offsetWidth; wrap.classList.add("bad"); },
  };
}

function obOtp(purpose) {
  const card = purpose === "card";
  const stage = card ? "card_otp" : "otp";
  const c = obShow(stage, `
    <h2>${card ? "Kartani tasdiqlang" : "SMS kodni kiriting"}</h2>
    <p>${esc(S.auth.phone_masked || "")} raqamiga yuborilgan 6 xonali ${card ? "karta tasdiqlash kodi" : "kod"}.</p>
    <div class="otp-boxes" id="otpBoxes"></div>
    <div class="ob-err" id="otpErr"></div>
    <div class="ob-alt"><button class="ob-link" id="otpResend" disabled>Qayta yuborish</button>
      <button class="ob-link" id="otpBack">${card ? "← Kartani o'zgartirish" : "← Raqamni o'zgartirish"}</button></div>
    <div class="ob-note blue small">🔐 Bu kodni hech kimga aytmang — FinPilot va bank xodimlari ham uni so'ramaydi.</div>`, card);
  const resend = $("#otpResend", c);
  const startResend = secs => {
    clearInterval(OB.resendTimer);
    let left = secs;
    const tick = () => {
      if (left <= 0) { resend.disabled = false; resend.textContent = "Qayta yuborish"; clearInterval(OB.resendTimer); return; }
      resend.disabled = true; resend.textContent = `Qayta yuborish (${left} s)`; left--;
    };
    tick(); OB.resendTimer = setInterval(tick, 1000);
  };
  const lock = secs => {
    box.disable(true);
    clearInterval(OB.lockTimer);
    let left = secs;
    const tick = () => {
      if (left <= 0) { clearInterval(OB.lockTimer); box.disable(false); obErr(c, "Endi qayta urinishingiz mumkin. Yangi kod so'rang."); resend.disabled = false; resend.textContent = "Qayta yuborish"; return; }
      obErr(c, `3 marta noto'g'ri kod. Bloklandi: ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`); left--;
    };
    tick(); OB.lockTimer = setInterval(tick, 1000);
  };
  const box = otpBoxes($("#otpBoxes", c), async code => {
    box.disable(true);
    try {
      S.auth = await api(card ? "/api/auth/card/otp" : "/api/auth/otp", { method: "POST", body: { code } });
      $("#smsBanner").classList.remove("show");
      if (card) toast("Karta qo'shildi ✓");
      obRoute();
    } catch (err) {
      box.disable(false); box.bad(); box.clear();
      if (err.info && err.info.code === "locked") lock(err.info.retry_in);
      else obErr(c, err.message);
    }
  });
  startResend(OB.resendIn ?? 60);
  OB.resendIn = null;
  resend.onclick = async () => {
    try {
      const r = await api(card ? "/api/auth/card/resend" : "/api/auth/phone/resend", { method: "POST" });
      showSms(r.demo_sms); obErr(c, ""); box.disable(false); box.clear(); startResend(r.resend_in);
      toast("Yangi kod yuborildi");
    } catch (err) {
      obErr(c, err.message);
      if (err.info && err.info.retry_in) startResend(err.info.retry_in);
    }
  };
  $("#otpBack", c).onclick = async () => {
    S.auth = await api(card ? "/api/auth/card/back" : "/api/auth/phone/back", { method: "POST" });
    if (card) OB.openCard = true;
    obRoute();
  };
}

// ------------------------------------------------------------------ STEP 3: profile
function obProfile() {
  const c = obShow("profile", `
    <h2>Tanishib olaylik</h2><p>Ism va familiyangiz karta egasi bilan solishtiriladi.</p>
    <form id="obForm" novalidate>
      <div class="form-row"><label for="obFirst">Ism</label><input id="obFirst" autocomplete="given-name" maxlength="30" placeholder="Masalan: Aziza"></div>
      <div class="form-row"><label for="obLast">Familiya</label><input id="obLast" autocomplete="family-name" maxlength="30" placeholder="Masalan: Karimova"></div>
      <div class="ob-err"></div>
      <button class="btn block" id="obNext">Davom etish</button>
    </form>`);
  $("#obForm", c).onsubmit = async e => {
    e.preventDefault();
    const first = $("#obFirst", c).value.trim().replace(/\s+/g, " "), last = $("#obLast", c).value.trim().replace(/\s+/g, " ");
    if (!NAME_RE.test(first)) return obErr(c, "Ism 2–30 ta harfdan iborat bo'lishi kerak (raqam va belgilarsiz)");
    if (!NAME_RE.test(last)) return obErr(c, "Familiya 2–30 ta harfdan iborat bo'lishi kerak (raqam va belgilarsiz)");
    const b = $("#obNext", c); busy(b, true);
    try { S.auth = await api("/api/auth/profile", { method: "POST", body: { first, last } }); OB.openCard = false; obRoute(); }
    catch (err) { busy(b, false); obErr(c, err.message); }
  };
}

// ------------------------------------------------------------------ STEP 4: locked dashboard
function enterLocked() {
  S.mode = "locked";
  renderTopbar();
  renderNav();
  const u = S.auth.user || {};
  const mods = [
    ["🛡", "Qalqon", "Unutilgan obunalar, sinovdan pullikka o'tish va ikki marta to'lovlarni topadi."],
    ["📈", "O'sish", "Bo'sh turgan pulni xavfsiz omonatga joylab, daromad keltiradi."],
    ["🩺", "Shifo", "Kreditlarning haqiqiy narxini va qaysi birini avval yopishni ko'rsatadi."],
    ["🕊", "Meros", "Favqulodda holatda yaqinlaringiz uchun hisoblar xaritasi."],
  ];
  $("#view").innerHTML = `
    <div class="view-head"><div><h1>Salom, ${esc(u.first || "")}! 👋</h1><p>FinPilot tayyor. Ishni boshlash uchun bitta karta qo'shing — shundan so'ng barcha modullar ochiladi.</p></div></div>
    <div class="cta-card"><div><h2>💳 Kartangizni qo'shing</h2><p class="muted small" style="margin:4px 0 0">UzCard yoki Humo. CVV va PIN so'ralmaydi. Karta raqami serverga yuborilmaydi.</p></div>
      <button class="btn green" id="ctaCard">Kartangizni qo'shing →</button></div>
    <div class="grid g2 locked-grid">${mods.map(([i, t, d]) => `<div class="card"><span class="lock">🔒</span><h2>${i} ${t}</h2><p class="muted small" style="margin:6px 0 0">${d}</p></div>`).join("")}</div>`;
  $("#ctaCard").onclick = () => { OB.openCard = true; obCard(); };
}

// ------------------------------------------------------------------ STEP 5: add card
function obCard() {
  const u = S.auth.user || {};
  const c = obShow("card", `
    <h2>Karta qo'shish</h2><p>Faqat UzCard (8600) va Humo (9860).</p>
    <div class="card-visual" id="cv"><span class="brandmark" id="cvBrand">KARTA</span><div class="chip"></div>
      <div class="num" id="cvNum">•••• •••• •••• ••••</div><div class="meta"><span id="cvName">${esc((u.first + " " + u.last).toUpperCase())}</span><span id="cvExp">MM/YY</span></div></div>
    <form id="obForm" novalidate autocomplete="off">
      <div class="form-row"><label for="cNum">Karta raqami</label><input id="cNum" inputmode="numeric" autocomplete="off" placeholder="0000 0000 0000 0000" maxlength="19"></div>
      <div class="two">
        <div class="form-row"><label for="cExp">Amal qilish muddati</label><input id="cExp" inputmode="numeric" placeholder="MM/YY" maxlength="5"></div>
        <div class="form-row"><label for="cHolder">Karta egasi</label><input id="cHolder" autocomplete="off" placeholder="${esc((u.first + " " + u.last).toUpperCase())}"></div>
      </div>
      <div class="ob-note">🛡 <span>FinPilot hech qachon <b>CVV, PIN</b> yoki parolingizni so'ramaydi. Kimdir ularni so'rasa — bu firibgarlik.</span></div>
      ${S.auth.demo_mode ? `<div class="small muted" style="margin:-6px 0 10px">Demo kartalar: Humo <span class="mono">9860 3500 1234 4825</span> · UzCard <span class="mono">8600 1234 5678 4427</span></div>` : ""}
      <div class="ob-err"></div>
      <div class="two"><button type="button" class="btn ghost" id="cCancel">Keyinroq</button><button class="btn" id="cNext">Tasdiqlash kodi</button></div>
    </form>`, true);
  const num = $("#cNum", c), exp = $("#cExp", c), holder = $("#cHolder", c);
  num.addEventListener("input", () => {
    const d = num.value.replace(/\D/g, "").slice(0, 16);
    num.value = d.replace(/(\d{4})(?=\d)/g, "$1 ");
    const t = cardTypeOf(d);
    $("#cv", c).className = "card-visual " + (t || "");
    $("#cvBrand", c).textContent = t ? CARD_LABEL[t].toUpperCase() : (d.length >= 4 ? "NOMA'LUM" : "KARTA");
    $("#cvNum", c).textContent = (d + "•".repeat(16 - d.length)).replace(/(.{4})(?=.)/g, "$1 ");
    obErr(c, d.length >= 4 && !t ? "Hozircha faqat UzCard va Humo kartalari qo'llab-quvvatlanadi" : "");
  });
  exp.addEventListener("input", () => {
    let d = exp.value.replace(/\D/g, "").slice(0, 4);
    if (d.length === 1 && +d > 1) d = "0" + d;
    exp.value = d.length > 2 ? d.slice(0, 2) + "/" + d.slice(2) : d;
    $("#cvExp", c).textContent = exp.value || "MM/YY";
  });
  holder.addEventListener("input", () => { $("#cvName", c).textContent = holder.value.toUpperCase() || (u.first + " " + u.last).toUpperCase(); });
  $("#cCancel", c).onclick = () => { OB.openCard = false; obHide(); };
  $("#obForm", c).onsubmit = async e => {
    e.preventDefault();
    let digits = num.value.replace(/\D/g, "");
    const type = cardTypeOf(digits);
    if (digits.length !== 16) return obErr(c, "Karta raqami 16 ta raqamdan iborat bo'lishi kerak");
    if (!type) return obErr(c, "Hozircha faqat UzCard va Humo kartalari qo'llab-quvvatlanadi");
    if (!luhnOk(digits)) return obErr(c, "Karta raqami noto'g'ri — raqamlarni tekshiring");
    const m = exp.value.match(/^(\d{2})\/(\d{2})$/);
    if (!m || +m[1] < 1 || +m[1] > 12) return obErr(c, "Muddatni MM/YY formatida kiriting");
    const now = new Date(S.meta.today + "T00:00:00");
    if (2000 + +m[2] < now.getFullYear() || (2000 + +m[2] === now.getFullYear() && +m[1] < now.getMonth() + 1)) return obErr(c, "Karta muddati o'tib ketgan");
    if (!holder.value.trim()) return obErr(c, "Karta egasining ismini kiriting");
    if (!holderMatches(holder.value, u.first, u.last)) return obErr(c, "Karta egasining ismi ro'yxatdan o'tgan ismingizga mos kelmadi");
    const payload = { last4: digits.slice(-4), type, exp_month: +m[1], exp_year: +m[2], holder: holder.value.trim() };
    // Discard the full number immediately: only last4 + type leave the browser
    digits = ""; num.value = ""; $("#cvNum", c).textContent = "•••• •••• •••• " + payload.last4;
    const b = $("#cNext", c); busy(b, true, "Yuborilmoqda…");
    try {
      const r = await api("/api/auth/card", { method: "POST", body: payload });
      showSms(r.demo_sms); S.auth = r.state; OB.resendIn = r.resend_in; OB.openCard = false;
      obRoute();
    } catch (err) { busy(b, false); obErr(c, err.message); }
  };
}

// ------------------------------------------------------------------ STEP 7: consent & balance
function obSetup() {
  const c = obShow("setup", `
    <h2>Rozilik va balans</h2>
    <div class="ob-note blue small" style="display:block">
      <b>FinPilot nimani tahlil qiladi:</b> kartadagi qoldiq, siz yuklagan tranzaksiyalar va kreditlar.
      Ism, karta va telefon AI'ga <b>yuborilmaydi</b> — tokenlar bilan almashtiriladi. Chiqishingiz bilan hammasi o'chiriladi.
      <label style="display:flex;gap:8px;align-items:center;margin-top:8px;font-weight:600"><input type="checkbox" id="sConsent"> Roziman</label></div>
    <div class="choice" role="group"><button type="button" data-m="balance">💰 Joriy qoldiq</button><button type="button" data-m="csv">📄 Ko'chirma (CSV)</button></div>
    <div id="sBalance" class="form-row"><label for="sBal">Kartadagi joriy qoldiq (so'm)</label><input id="sBal" inputmode="numeric" placeholder="Masalan: 4 850 000"></div>
    <div id="sCsv" class="hidden">
      <div class="form-row"><label for="sFile">Bank ko'chirmasi (CSV: date, description, amount)</label><input type="file" id="sFile" accept=".csv,text/csv"></div>
      <div class="small" id="sCsvStatus"><a href="/static/sample_statement.csv" download>Namuna CSV yuklab olish</a></div>
      <div class="form-row" style="margin-top:8px"><label for="sBal2">Joriy qoldiq (ixtiyoriy)</label><input id="sBal2" inputmode="numeric" placeholder="O'sish uchun kerak"></div>
    </div>
    <details style="margin:6px 0 10px"><summary class="small" style="cursor:pointer">O'sish uchun (ixtiyoriy): daromad va xarajatlar</summary>
      <div class="two" style="margin-top:8px"><div class="form-row"><label for="sInc">Oylik daromad</label><input id="sInc" inputmode="numeric" placeholder="9 500 000"></div>
        <div class="form-row"><label for="sDay">Oylik kuni (1–28)</label><input id="sDay" inputmode="numeric" maxlength="2" placeholder="5"></div></div>
      <div class="form-row"><label for="sEss">Oylik zarur xarajatlar</label><input id="sEss" inputmode="numeric" placeholder="5 400 000"></div></details>
    <p class="small" style="margin:0 0 10px">ℹ️ Kartadagi qoldiqni bank bilan avtomatik sinxronlash Open Banking orqali ishlaydi (yo'l xaritasida).</p>
    <div class="ob-err"></div>
    <button class="btn green block" id="sGo">FinPilot'ni ishga tushirish</button>`, true);
  ["#sBal", "#sBal2", "#sInc", "#sEss"].forEach(s => moneyIn($(s, c)));
  const setMode = m => {
    OB.balanceMode = m;
    $$(".choice button", c).forEach(b => b.classList.toggle("active", b.dataset.m === m));
    $("#sBalance", c).classList.toggle("hidden", m !== "balance");
    $("#sCsv", c).classList.toggle("hidden", m !== "csv");
  };
  $$(".choice button", c).forEach(b => (b.onclick = () => setMode(b.dataset.m)));
  setMode(OB.statementRows ? "csv" : OB.balanceMode);
  if (OB.statementRows) $("#sCsvStatus", c).textContent = `✅ ${OB.statementRows} ta tranzaksiya yuklandi`;
  $("#sFile", c).onchange = async e => {
    const f = e.target.files[0]; if (!f) return;
    const fd = new FormData(); fd.append("file", f);
    $("#sCsvStatus", c).innerHTML = `<span class="spinner"></span> Tekshirilmoqda…`;
    try {
      const r = await api("/api/auth/statement", { method: "POST", body: fd });
      OB.statementRows = r.rows; obErr(c, "");
      $("#sCsvStatus", c).textContent = `✅ ${r.rows} ta tranzaksiya yuklandi (faqat sessiya xotirasida)`;
    } catch (err) { $("#sCsvStatus", c).innerHTML = `<a href="/static/sample_statement.csv" download>Namuna CSV yuklab olish</a>`; obErr(c, err.message); }
  };
  $("#sGo", c).onclick = async () => {
    if (!$("#sConsent", c).checked) return obErr(c, "Davom etish uchun rozilik belgisini qo'ying");
    const balance = OB.balanceMode === "balance" ? moneyVal($("#sBal", c)) : moneyVal($("#sBal2", c));
    if (OB.balanceMode === "balance" && balance == null) return obErr(c, "Kartadagi joriy qoldiqni kiriting");
    if (OB.balanceMode === "csv" && !OB.statementRows) return obErr(c, "CSV faylni yuklang yoki \"Joriy qoldiq\"ni tanlang");
    const day = $("#sDay", c).value ? parseInt($("#sDay", c).value, 10) : null;
    if (day != null && (isNaN(day) || day < 1 || day > 28)) return obErr(c, "Oylik kuni 1 dan 28 gacha bo'lishi kerak");
    const b = $("#sGo", c); busy(b, true, "Tayyorlanmoqda…");
    try {
      S.auth = await api("/api/auth/setup", { method: "POST", body: { consent: true, balance, monthly_income: moneyVal($("#sInc", c)), payday: day, essentials: moneyVal($("#sEss", c)) } });
      OB.statementRows = 0;
      toast("Tayyor! Barcha modullar ochildi ✓");
      obRoute();
    } catch (err) { busy(b, false); obErr(c, err.message); }
  };
}

// ------------------------------------------------------------------ logout / wipe
function askLogout() {
  const user = S.mode === "user";
  const box = openModal(`<h2>${user ? "Chiqish va ma'lumotlarni o'chirish" : "Demo rejimidan chiqish"}</h2>
    <p class="muted">${user ? "Karta (oxirgi 4 raqam), balans, ko'chirma, kreditlar, sozlamalar va amallar darhol o'chiriladi. Audit jurnalida faqat niqoblangan yozuvlar qoladi." : "Boshlang'ich ekranga qaytasiz."}</p>
    <div class="modal-actions"><button class="btn ghost" id="lgNo">Bekor</button><button class="btn danger" id="lgYes">${user ? "O'chirish va chiqish" : "Chiqish"}</button></div>`);
  $("#lgNo", box).onclick = closeModal;
  $("#lgYes", box).onclick = async () => { closeModal(); await doLogout(); toast(user ? "Ma'lumotlar o'chirildi" : "Chiqildi"); };
}
async function doLogout() {
  S.auth = await api("/api/auth/logout", { method: "POST" });
  S.mode = null; S.pid = "aziza"; S.conv = {}; S.bufferPct = {};
  OB.openCard = false; OB.statementRows = 0;
  if (S.chart) { S.chart.destroy(); S.chart = null; }
  $("#view").innerHTML = "";
  openChat(false);
  renderTopbar(); renderNav();
  obRoute();
}

// ------------------------------------------------------------------ demo: drive the real onboarding UI
const wait = ms => new Promise(r => setTimeout(r, ms));
async function waitFor(sel, ms = 6000) {
  const t0 = Date.now();
  for (;;) { const el = $(sel); if (el) return el; if (Date.now() - t0 > ms) throw new Error("timeout " + sel); await wait(80); }
}
async function typeSlow(el, text, per = 45) {
  el.focus();
  for (const ch of text) { el.value += ch; el.dispatchEvent(new Event("input", { bubbles: true })); await wait(per); }
}
function smsCode() { const m = ($("#smsBanner").textContent || "").match(/\b(\d{6})\b/); return m && m[1]; }
async function typeOtp() {
  await wait(700);
  const code = smsCode();
  const first = await waitFor("#otpBoxes input");
  first.value = code; first.dispatchEvent(new Event("input", { bubbles: true }));
}
async function autoOnboard() {
  if (S.auth.stage !== "phone") await doLogout();
  const phone = await waitFor("#obPhone");
  phone.value = ""; await typeSlow(phone, "901234567", 70);
  await wait(300); $("#obSend").click();
  await waitFor("#otpBoxes"); await typeOtp();
  await typeSlow(await waitFor("#obFirst"), "Aziza"); await typeSlow($("#obLast"), "Karimova");
  await wait(250); $("#obNext").click();
  (await waitFor("#ctaCard")).click();
  await typeSlow(await waitFor("#cNum"), "9860350012344825", 40);
  await typeSlow($("#cExp"), "1228", 60); await typeSlow($("#cHolder"), "AZIZA KARIMOVA", 30);
  await wait(300); $("#cNext").click();
  await waitFor("#otpBoxes"); await typeOtp();
  const consent = await waitFor("#sConsent");
  consent.checked = true;
  $(".choice [data-m='csv']").click();
  const csv = await (await fetch("/static/sample_statement.csv")).blob();
  const fd = new FormData(); fd.append("file", new File([csv], "kochirma.csv", { type: "text/csv" }));
  const r = await api("/api/auth/statement", { method: "POST", body: fd });
  OB.statementRows = r.rows; $("#sCsvStatus").textContent = `✅ ${r.rows} ta tranzaksiya yuklandi (faqat sessiya xotirasida)`;
  await typeSlow($("#sBal2"), "4850000", 30);
  $("#onboard details").open = true;
  await typeSlow($("#sInc"), "9500000", 25); await typeSlow($("#sDay"), "5", 25); await typeSlow($("#sEss"), "5400000", 25);
  await wait(400); $("#sGo").click();
}
