# FinPilot — Build Prompt (v3)

You are a senior full-stack engineer and fintech product designer. Build a hackathon-winning, **working** prototype of **FinPilot**, an AI financial agent for Uzbekistan. It will be judged on five criteria (100 points total); every requirement below exists to earn those points, so do not skip the parts marked **[JUDGING]**.

| # | Criterion | Points | How FinPilot wins it |
|---|---|---|---|
| 1 | Problem relevance & value | 25 | Real Uzbek pain points, clear target users (bank + customer + small business), measurable savings in so'm |
| 2 | Innovation & generative AI as the core | 25 | A real LLM agent with tool calling, not scripted text; numbers come from deterministic tools, words come from the model |
| 3 | Working prototype, architecture, data security | 25 | Live demo, real onboarding with phone + SMS OTP, card verification without CVV/PIN, PII redaction, consent, tamper-evident audit log |
| 4 | Business model & bank integration | 15 | B2B2C: embedded module inside bank apps, bank API and SMS provider adapter layers |
| 5 | Presentation (7 minutes) | 10 | Built-in demo mode with a scripted, reliable flow |

---

## 1. PRODUCT

FinPilot is **one AI agent** working on a single **Unified Financial Graph** (user, cards, accounts, transactions, subscriptions, loans, deposits, obligations). It does not only advise: with the user's consent it **prepares and executes** actions through a strict lifecycle:

**Prepare → Confirm → Execute → Audit**

- *Prepare*: the agent builds an action proposal (type, amount, counterparty, reason, computed numbers).
- *Confirm*: the user approves it in a modal, unless the action is within the autonomy limit (see §5).
- *Execute*: the action is sent through the **Bank API Adapter** (mocked, but behind a real interface).
- *Audit*: every step is written to a hash-chained audit log.

**Positioning for judges:** FinPilot is a **white-label module that banks embed in their mobile apps** (B2B2C). The bank gets retention, deposits and lower fraud/default risk; the customer gets money saved and earned.

### Scope (important)
- **Onboarding & auth** (§3): phone → SMS OTP → profile → add card → card OTP → balance/statement. Fully working.
- **Two core modules, fully built and polished:** 🛡 **Qalqon** and 📈 **O'sish**.
- **Two preview modules** (🩺 **Shifo**, 🕊 **Meros**): one screen each, with a working AI explanation of the concept and a clearly labeled "Keyingi bosqich" (next phase) badge. Do not build deep logic for them.
- **Two demo profiles** (Aziza — personal, Dorixona "Salomat" — business) stay available through "Demo profil bilan ko'rish" so the pitch never depends on typing live data.
- Depth beats breadth: two flawless modules score higher than four half-working ones.

---

## 2. ARCHITECTURE

```
Browser (SPA: HTML + CSS + vanilla JS + Chart.js)
   │  card number, expiry, Luhn check stay in the browser; only last4 + type + holder are sent
   │  REST + Server-Sent Events (streaming AI text), session via httpOnly cookie
   ▼
FastAPI backend (Python 3.12+)
   ├── /api/auth/*       → phone OTP, profile, card OTP, session, logout/wipe
   ├── /api/agent        → LLM agent loop (Anthropic SDK, tool calling, streaming)
   ├── /api/qalqon/*     → statement upload & detection
   ├── /api/osish/*      → cash forecast & instrument recommendation
   ├── /api/actions/*    → prepare / confirm / execute
   ├── /api/audit        → audit log (hash chain + verify endpoint)
   ├── core/             → DETERMINISTIC finance functions (pure, unit-tested)
   ├── security/         → OTP service, PII redaction, consent, autonomy policy, rate limits
   ├── adapters/bank.py  → BankAPI interface + MockBank implementation
   ├── adapters/sms.py   → SmsProvider interface + DemoSmsProvider (+ EskizSmsProvider stub)
   └── data/             → seed JSON for 2 demo profiles
```

### Tech stack
- **Backend:** FastAPI, Pydantic v2, Anthropic Python SDK (`anthropic`), SQLite for the audit log and actions, `pytest`.
- **Frontend:** a single `index.html` + `app.js` + `styles.css`, served by FastAPI as static files. Vanilla JS, Chart.js from a CDN. No build step.
- **Config:** `.env` with `ANTHROPIC_API_KEY`, `CLAUDE_MODEL` (default `claude-opus-5-5`), `CLAUDE_EFFORT` (default `low` for fast demo responses), `DEMO_MODE` (default `true`: OTP codes are shown on screen), `SMS_PROVIDER` (`demo` | `eskiz`), `ESKIZ_EMAIL`, `ESKIZ_PASSWORD`.
- **One command to run:** `uvicorn app.main:app --reload`. Include a `README.md` with setup steps for macOS and Windows.

### The AI layer — the heart of criterion 2 **[JUDGING]**
- Use a **real LLM agent with tool calling** (Anthropic Messages API). The model must never invent numbers: every figure it states must come from a tool result.
- Expose the deterministic functions as tools, for example:
  - `get_financial_snapshot()`
  - `detect_subscriptions()`
  - `get_cancellation_facts(finding_id)` → returns facts; **the model writes the letter**
  - `forecast_cash(days)`
  - `recommend_instrument()`
  - `simulate_card_limit(merchant, monthly_limit)`
  - `get_debt_overview()`
  - `prepare_action(type, params)` → returns a proposal; **the model can never execute directly**
- Tools act on the **current session's** Unified Financial Graph (onboarded user or selected demo profile); the model never passes or sees a user ID.
- The agent can be used two ways:
  1. **Chat panel** ("FinPilot'dan so'rang") available on every screen. Free-form questions in Uzbek, e.g. *"Qaysi obunalarimni bekor qilsam bo'ladi?"*, *"Dorixonada ortiqcha pul bormi?"*. Answers stream token by token.
  2. **Inline explanations** under each module result, generated by the same agent.
- Under every AI answer, show an expandable **"Hisoblandi"** block listing each tool call: tool name, inputs, outputs, and the formula used (e.g. `foyda = summa × stavka × kun / 365`). This proves numbers are not hallucinated.
- System prompt rules (write them in the code): answer in Uzbek (Latin script); use only numbers from tool results; format money as `89 000 so'm`; be concise; when proposing an action, always call `prepare_action` instead of claiming it is done; say clearly when information is missing (e.g. no statement uploaded yet) and tell the user which step provides it.
- Handle `stop_reason` values (`refusal`, `max_tokens`) gracefully with a friendly Uzbek message.
- **Offline fallback:** if there is no API key or the network fails, switch to a clearly labeled **"Offline demo rejimi"** that produces templated Uzbek text over the same deterministic tool results. Show the badge honestly; never present templated text as live AI.

### Data security & privacy **[JUDGING]**
Build these for real and show them in a "Xavfsizlik" panel:
1. **Phone + SMS OTP authentication** (§3) with server-side hashed codes, expiry, attempt limits and lockout.
2. **Card data minimization:** the full card number never leaves the browser and is wiped from memory and the input right after validation. The server stores only `last4`, card type and holder name. **CVV and PIN are never requested.** Cards are shown masked everywhere: `Humo •••• 4825`.
3. **No persistence of personal data:** the onboarded user's profile, card, balance and statement live only in server memory for the session (and in browser memory on the client). No `localStorage`/`sessionStorage` for personal data. "Chiqish / ma'lumotlarni o'chirish" wipes both sides immediately. Only the audit log (with masked values) is persisted.
4. **PII redaction before the LLM:** names, phone numbers, card numbers, account IDs and e-mails are replaced with tokens (`[ISM_1]`, `[TEL_1]`, `[KARTA_1]`) before any text is sent to the model, then restored in the UI. Show "AI'ga nima yuborildi?" with the redacted payload.
5. **Consent:** an explicit consent step (§3, step 7) lists what is analyzed; stored for the session and revocable in "Xavfsizlik".
6. **Tamper-evident audit log:** each entry stores `prev_hash` and `hash = sha256(prev_hash + payload)`. Provide `GET /api/audit/verify` and a "Jurnal butunligini tekshirish" button that shows ✅ or the first broken entry. Auth events (OTP sent/verified/locked, card added, logout/wipe) are audited too — with masked phone and card.
7. **Least privilege for the agent:** the LLM can only call read and `prepare_*` tools; `execute` happens only from the confirmation endpoint or the autonomy policy engine, never from the model.
8. The API key lives only on the server. Rate limit `/api/agent` and `/api/auth/*`. Validate uploaded CSV size and columns. Every non-auth endpoint requires a valid session.

### Adapters **[JUDGING: criterion 4]**
- `BankAPI` abstract interface: `open_deposit`, `close_deposit`, `set_card_merchant_limit`, `block_merchant`, `get_transactions`. `MockBank` implementation with realistic latency (300–800 ms) and occasional simulated failures (handled with retry and a clear error).
- `SmsProvider` interface with `send_sms(phone, text)`. `DemoSmsProvider` delivers nothing and lets the UI show the code (only when `DEMO_MODE=true`); `EskizSmsProvider` is a ready stub for Eskiz.uz (token auth + send endpoint) selected by `SMS_PROVIDER=eskiz`.
- README section: *"In production these adapters connect to the partner bank's API / open banking gateway and a licensed SMS provider."*

---

## 3. ONBOARDING & AUTH FLOW **[JUDGING: criterion 3]**

A multi-step onboarding in Uzbek shown before the dashboard. A progress indicator ("1/7") is visible on every step, with a "Orqaga" button where it makes sense. Step 1 also has a secondary link **"Demo profil bilan ko'rish"** that skips onboarding and opens a demo profile (Aziza or Dorixona "Salomat").

**STEP 1 – Phone.** Input with `+998` mask, formatted as `+998 XX XXX XX XX`; validate 9 digits after `+998`. Button **"Kod yuborish"**.

**STEP 2 – SMS OTP.**
- Six digit boxes with auto-advance, backspace to the previous box, and paste of a full code.
- 60-second countdown, then **"Qayta yuborish"** (max 3 resends per 10 minutes).
- Code expires after 5 minutes. After 3 wrong attempts: 5-minute lockout with a visible countdown.
- The server generates the code with a cryptographically secure RNG, stores only its hash with expiry and attempt counter, and compares in constant time.
- Send through the pluggable `SmsProvider` (`sendSms(phone, code)` on the server). **DEMO MODE:** show the code in a phone-style "SMS" notification banner sliding in at the top: *"FinPilot: tasdiqlash kodi 482915. Kodni hech kimga aytmang."* The banner is shown only when `DEMO_MODE=true`.

**STEP 3 – Profile.** First name and last name, both required, 2–30 characters, letters only — allow Uzbek Latin (including `oʻ`, `gʻ` and the `'`, `ʻ`, `’` apostrophes), Cyrillic and a hyphen. Trim spaces; show friendly Uzbek errors.

**STEP 4 – Dashboard, empty state.** Greeting **"Salom, {Ism}!"**. All modules are visible but locked (lock icon and a one-line description of what each will do), with a prominent **"Kartangizni qo'shing"** call to action.

**STEP 5 – Add card.**
- Card number auto-formatted `4-4-4-4`; **Luhn validation**; type detection by prefix: `8600` → UzCard, `9860` → Humo, anything else → friendly error: *"Hozircha faqat UzCard va Humo kartalari qo'llab-quvvatlanadi"*. Show the detected card logo or label live while typing.
- Expiry `MM/YY`: month 01–12, not in the past (the current month is allowed).
- Cardholder name: must match the registered first + last name, case-insensitive, ignoring apostrophe variants, extra spaces and word order (`AZIZA KARIMOVA` = `Karimova Aziza`). Otherwise: *"Karta egasining ismi ro'yxatdan o'tgan ismingizga mos kelmadi"*.
- **Never ask for CVV or PIN.** Show a note: *"FinPilot hech qachon CVV, PIN yoki parolingizni so'ramaydi. Kimdir ularni so'rasa — bu firibgarlik."*
- Demo test cards that pass Luhn: UzCard `8600 1234 5678 4427`, Humo `9860 3500 1234 4825`.

**STEP 6 – Card confirmation.** A second, separate SMS OTP ("Karta tasdiqlash kodi") with the same rules as step 2. After success the browser sends only `{last4, type, holder_name}` to the server, then clears the full number from memory and from the input.

**STEP 7 – Consent and balance.**
- Consent screen: what is analyzed (balance, transactions, loans), that PII is tokenized before AI, and that data is deleted on logout. Button **"Roziman"**.
- Then choose: **"Kartadagi joriy qoldiq"** (manual amount input) or **"Ko'chirma yuklash (CSV)"** with columns `date, description, amount`.
- Optional, one line each: monthly income and payday, monthly essential spending — so O'sish can compute a buffer. If skipped, O'sish shows what it needs instead of guessing.
- One-line note: *"Kartadagi qoldiqni bank bilan avtomatik sinxronlash Open Banking orqali ishlaydi (yo'l xaritasida)."*

**After success:**
- Display the card as `Humo •••• 4825`; unlock all modules; every module reads from the single Unified Financial Graph of the session.
- Each module degrades honestly: Qalqon without a statement shows "Ko'chirma yuklang", O'sish without income data shows the missing inputs.
- Persistent badge **"Ma'lumotlar saqlanmaydi — chiqishingiz bilan o'chiriladi"** and a **"Chiqish / ma'lumotlarni o'chirish"** button that wipes the session on the server and the state in the browser, then returns to step 1.

---

## 4. UI / UX

- **Language:** Uzbek (Latin script) everywhere in the UI. Code and comments in English.
- **Currency:** so'm, formatted with a thin space as thousands separator: `89 000 so'm`. Large values as `12,4 mln so'm` where space is tight.
- **Design:** modern fintech; deep blue primary (#0B3D91 range) with green accents for money gained (#16A34A range) and amber/red for risk. Rounded cards, subtle shadows, smooth micro-animations (counters, ring fill, list entrance, OTP box focus). Light/dark toggle (respects system preference by default). Fully responsive: sidebar on desktop, bottom tabs on mobile; onboarding is a centered phone-width card. No lorem ipsum: all copy is real and in Uzbek.
- **Accessibility:** sufficient contrast in both themes, visible focus states, keyboard-usable buttons, OTP boxes with proper labels and `autocomplete="one-time-code"`.

### Global layout
- **Navigation:** Bosh sahifa, 🛡 Qalqon, 📈 O'sish, 🩺 Shifo, 🕊 Meros, 📜 Audit jurnali, 🔒 Xavfsizlik, 🧩 Qanday ishlaydi.
- **Top bar:**
  - Current user ("Aziza K." + masked card) or demo profile switcher with **"Aziza — shaxsiy"** and **"Dorixona 'Salomat' — biznes"**. Switching changes the data and which modules are emphasized (Qalqon first for Aziza, O'sish first for the pharmacy).
  - **Autonomiya darajasi:** `Faqat maslahat` / `Bir bosishda` / `Limit ichida avtomatik` with a limit input (e.g. 500 000 so'm). The policy engine enforces it server-side.
  - **Demo rejimi** button (see §7) and **Chiqish** button.
- **Home (Bosh sahifa):**
  - Financial health score ring (0–100) computed deterministically from: savings rate, subscription waste, idle cash ratio, debt-to-income. Show the breakdown on click.
  - Net position (assets − liabilities).
  - **"FinPilot bugun nima qildi"** feed of recent agent actions with timestamps and statuses.
  - **3 synergy cards** that connect modules, for example: *"Qalqon oyiga 214 000 so'm bo'shatdi → O'sish uni 30 kunlik depozitga yo'naltirsa, yiliga 41 000 so'm qo'shimcha daromad"*. Each card has a one-click "Tayyorlash" button that goes through the action lifecycle.

---

## 5. AUTONOMY POLICY ENGINE

Deterministic server-side rules:
- `Faqat maslahat`: the agent may only explain; `prepare_action` returns proposals marked "advice only".
- `Bir bosishda`: every action requires the confirmation modal.
- `Limit ichida avtomatik`: actions with amount ≤ limit and type in an allowlist (`set_card_merchant_limit`, `open_deposit` with auto-return) execute automatically and appear in the feed with an **"Bekor qilish" (undo) button for 24 hours**. Everything else still needs confirmation.
- Every decision (auto-executed, confirmed, rejected) is written to the audit log with the policy that applied.

---

## 6. MODULES

### 6.1 🛡 QALQON — hidden subscription & dark-pattern detector

**Problem framing (show on the module header):** money silently leaves cards through forgotten subscriptions, auto-renewed trials, duplicate charges and quiet price increases.

**Input:**
- The CSV statement uploaded in onboarding step 7, or uploaded later on this screen (validated; clear Uzbek error messages).
- For demo profiles: "Bank ko'chirmasini yuklash" loads the profile's mock 90-day statement.

**Detection algorithm (deterministic, unit-tested):**
1. Normalize merchant names (lowercase, strip transaction IDs and city suffixes).
2. **Recurring:** same merchant, amount within ±10 %, interval ≈ 7 days (±2) or ≈ 30 days (±4), at least 2 occurrences.
3. **Trial → paid:** a charge ≤ 1 000 so'm (or 0) followed within 3–31 days by a charge ≥ 10× larger from the same merchant.
4. **Duplicate:** same merchant and amount twice within 3 days, or two different billing channels (e.g. App Store and direct) for the same service.
5. **Price hike:** a recurring charge that increased by ≥ 10 % compared with its previous median.
6. **Unused service:** a recurring charge where the activity signal (mock "last visit / last usage" field) is older than 60 days.

**Output table:** merchant, amount, frequency, "Shubha darajasi" (past / o'rta / yuqori), reason in plain Uzbek, and detection rule ID.

**Seed data (Aziza) must produce at least these findings, using services that are real for Uzbekistan:**
- A **streaming trial that converted to paid** (a 1 so'm trial followed by a full monthly charge).
- A **duplicate subscription** paid both through the App Store and directly.
- A **gym membership unused for 3 months.**
- A **silent price increase** on a recurring service.
- At least one legitimate recurring payment (e.g. mobile operator) correctly marked **past** — this shows the detector is not paranoid.

**Actions per finding:**
- **"Bekor qilish xatini tayyorlash":** the agent writes a polite, ready-to-send cancellation/refund request in Uzbek, using only facts returned by the tool (dates, amounts, last 4 card digits). Copy button + "Email sifatida ochish" (`mailto:`).
- **"Karta limitini o'rnatish":** proposes a per-merchant card limit through the action lifecycle.
- **"Bloklash":** blocks future charges from the merchant through the adapter.

**Savings summary:** "Oylik tejash: X so'm / Yillik: Y so'm" with an animated counter that updates as the user acts on findings.

### 6.2 📈 O'SISH — AI treasury for micro-businesses (and savings for individuals)

**Problem framing:** small businesses keep idle cash on current accounts earning nothing, but fear locking it up before rent, salaries or supplier payments.

**Business profile (Dorixona "Salomat"):** 30 days of daily revenue and expenses with realistic weekday seasonality (including last month's large payments), plus a schedule of upcoming obligations: rent, salaries, supplier payments and taxes with exact dates.

**Deterministic model:**
- Forecast the next 14–21 days of balance: expected inflows = weekday-adjusted average of the last 30 days; outflows = scheduled obligations + average daily operating costs.
- `safety_buffer = buffer_pct × average monthly outflow` (default 15 %, user-adjustable slider).
- `idle_cash = current_balance − (obligations before the next large payment + safety_buffer)`; never negative; rounded down to 100 000 so'm.
- Show every input and formula in the "Hisoblandi" block.

**Chart (Chart.js):** historical balance, forecast balance (dashed), safety line, shaded idle-cash zone, and markers for each obligation date with labels.

**Recommendation engine:**
- Mock instruments, clearly labeled "demo stavkalar": overnight deposit, 7-day deposit, 30-day deposit, short-term bond (rate, minimum amount, maturity).
- Choose the instrument with the highest expected return **whose maturity date is at least 1 day before the next large payment**. If none fits, recommend overnight and explain why.
- `expected_earnings = amount × annual_rate × days / 365`, rounded to whole so'm.
- Comparison table of all instruments with eligible/ineligible status and reasons.

**Action:** "Depozit ochish" → confirmation modal (amount, rate, maturity date, expected earnings, and **"to'lovdan oldin avtomatik qaytariladi"** with the date) → adapter call with loading state → calm success state → audit log entry → feed item on Home.

**Personal variant (Aziza or an onboarded user):** same engine for savings: buffer sized to essential spending until the next payday; idle money (including what Qalqon freed) goes to the best eligible savings instrument.

---

## 7. DEMO MODE **[JUDGING: criteria 3 and 5]**

A "Demo rejimi" button runs a guided, reliable walkthrough with on-screen step hints (the presenter clicks "Keyingi →"):
1. **Onboarding (fast):** phone auto-filled → SMS banner shows the code → code auto-filled → name → Humo test card → card OTP → consent → CSV loaded. Shows security in 40 seconds; "O'tkazib yuborish" skips straight to the Aziza demo profile.
2. Qalqon finds 4 issues → agent explains them → cancellation letter generated live.
3. Block the unused gym or set a merchant limit → audit log entry appears.
4. Switch to Dorixona "Salomat" → O'sish shows idle cash and the chart → agent recommends the 7-day deposit with earnings → open deposit with confirmation.
5. Home: synergy cards + health score improvement.
6. Audit log: "Jurnal butunligini tekshirish" → ✅, then the tamper demo → ❌ broken entry found → restore.
7. Security panel: "AI'ga nima yuborildi?" shows the redacted payload; "Chiqish / ma'lumotlarni o'chirish" wipes everything.

The demo must work in offline mode (templated agent text, labeled) if the internet fails during the presentation.

---

## 8. PREVIEW MODULES (light implementation)

- **🩺 Shifo** — debt health: shows the loans, computes the deterministic debt-to-income ratio and total interest cost, and the agent explains a repayment strategy (avalanche vs. snowball) using tool results. Onboarded users can add a loan manually (name, balance, rate, months left). Badge: "Keyingi bosqich".
- **🕊 Meros** — financial legacy & emergency access: a list of the user's accounts and a "trusted person" setup screen (mock, view-only rights), with the agent explaining what would happen in an emergency. Badge: "Keyingi bosqich".

---

## 9. "QANDAY ISHLAYDI" SCREEN (for judges' questions)

An in-app page with:
- The architecture diagram (as inline SVG) from §2.
- The rule: *"Raqamlarni kod hisoblaydi, so'zlarni AI yozadi"* with a live example.
- The security measures from §2 with status ticks, including the onboarding flow (OTP, no CVV/PIN, data minimization).
- Business model: **B2B2C** — banks pay a license fee per active user per month plus a revenue share on deposits opened through FinPilot; free for end customers inside their bank app. Scaling path: one partner bank → other Uzbek banks and payment apps → Central Asia.
- "What is mocked": bank API, SMS delivery in demo mode, demo rates, usage signals, balance sync (Open Banking roadmap).

---

## 10. QUALITY BAR

- Deterministic functions in `core/` are pure and covered by `pytest` tests: detection rules, forecast, instrument selection, interest, health score, hash chain verification, PII redaction, policy, **OTP (expiry, 3-attempt lockout, resend limit, hash-only storage), Luhn, card type detection, expiry validation, cardholder name matching (case, apostrophes, word order)**, and an API flow test from phone to unlocked dashboard to wipe.
- No console errors; all API errors show friendly Uzbek messages.
- Every number displayed is traceable to a function and its inputs.
- First meaningful screen loads in under 1 second locally; agent responses start streaming in under 3 seconds online.
- `README.md`: setup (macOS and Windows), run, demo script, architecture, security, and a "what is mocked" section (honesty earns trust with judges).

## 11. DELIVERABLES

1. Complete source code with the structure from §2.
2. Seed data for both demo profiles that produces the required findings and recommendations, plus a sample CSV for the onboarding upload.
3. Tests passing with `pytest -q`.
4. `README.md` as described in §10.
5. A `DEMO_SCRIPT.md` with the 7-minute pitch timing: problem (1:00) → solution & users (0:45) → live demo incl. onboarding (2:15) → AI & security (1:00) → business model (1:15) → team & next steps (0:45).
