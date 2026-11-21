# FinPilot — Demo Mode Build Prompt

You are a senior front-end engineer. Add a **guided Demo Mode** to the existing FinPilot SPA (FastAPI + vanilla JS, Uzbek UI). The demo must show **every feature of the app, end to end, with real actions** — nothing faked: every click goes through the real UI and real API, every action is really executed and written to the audit log. It is used two ways at the hackathon:

- **Live pitch (manual):** presenter clicks **Keyingi →** after each step and talks.
- **Video recording (autoplay):** the whole scenario plays by itself in ~5 minutes.

All UI text is in Uzbek (Latin). Do not add dependencies. Do not change backend business logic — the demo only drives the existing UI.

---

## 1. Entry point

A **▶ Demo rejimi** button in the top bar opens a modal:

- Title: `▶ Demo rejimi`
- Text: demo state will be reset (actions, audit, current session); the scenario shows all features in N steps.
- Buttons: `Bekor` · `⏵ Avtomatik` · `Qo'lda boshlash` (primary).

On start (both modes):
1. Create a demo session — `POST /api/auth/demo` — and grant consent for each demo profile (`aziza`, `salomat`).
2. `POST /api/demo/reset` (clears actions/audit for demo profiles only; allowed only in a demo session).
3. Reset settings for both profiles: `autonomy: "one_click"`, `auto_limit: 500000`.
4. Clear client state (buffer %, trusted person), set profile `aziza`.
5. Log out (so step 1 starts on a clean onboarding screen), then run step 1.

## 2. Bottom control bar (`#demoBar`)

Fixed at the bottom while the demo runs:

`[3/20]  <step narration text>   [←]  [⏵ Avto | ⏸ Pauza]  [Keyingi → | spinner | Tugatish]  [✕]`

- `←` — re-run previous step (disabled on step 1).
- `⏵ Avto` — toggle autoplay at any moment.
- `Keyingi →` — disabled with a spinner while the current step is running; on the last step it says `Tugatish`.
- `✕` — stop the demo immediately.

The narration text is what the presenter reads aloud — write it for the audience, with the key numbers in it.

## 3. Engine (must be cancel-safe)

```js
const D = { token: 0, busy: false, auto: false, timer: null };
class DemoCancel extends Error {}
```

- Every step run increments `D.token`. All demo helpers capture the token and throw `DemoCancel` if it changed — so pressing `←`, `Keyingi`, or `✕` mid-step aborts the old step cleanly and no two steps ever drive the UI at once.
- Helpers:
  - `dwait(ms)` — cancel-aware sleep.
  - `dfind(sel, ms=8000)` — poll every 100 ms until the element exists; throw on timeout.
  - `dclick(sel, pause)` — find, `scrollIntoView({block:"center", behavior:"smooth"})`, pause so the audience sees it, click.
  - `dset(sel, value)` — clear input and type it character by character (visible typing).
  - `waitAi(scopeSel)` — wait until the streaming AI text in that block stops (`.ai-text.cursor` disappears).
  - `confirmAction(pause)` — wait so the proposal can be read, click `#mYes` (Tasdiqlash), wait for the result modal `#mClose`, show it ~2 s, close.
  - `dscroll(sel)` — smooth scroll to a section. **Do not name it `scrollTo`** (shadows `window.scrollTo`).
- `runDemo(i)`: new token → `busy = true` → render bar → `await DEMO[i].run()` → on non-cancel error: `console.warn` + toast `"Demo qadami to'liq bajarilmadi — davom eting"` (never crash the demo) → if still the current token: `busy = false`, render, `scheduleNext()`.
- `scheduleNext()`: if autoplay is on, after the step's `dur` ms go to the next step; after the last step stop and toast `Demo tugadi ✓`.
- `ensureProfile(pid)`: close any modal/onboarding; if not in demo mode, enter a demo session and start the app; else switch profile if needed.

Each step is `{ t: "<narration>", dur: <ms to linger in autoplay>, run: async () => {...} }`.

## 4. The 20 steps

| # | Feature | What `run` does |
|---|---|---|
| 1 | **Onboarding** | `autoOnboard()`: type a **random** phone `90xxxxxxx` (so rehearsals never hit OTP cooldown/send limits) → send → type the SMS code from the demo banner → name "Aziza Karimova" → card `9860 3500 1234 4825`, `12/28`, `AZIZA KARIMOVA` (no CVV/PIN) → card SMS code → consent ✔, upload `/static/sample_statement.csv`, balance 4 850 000, income 9 500 000, payday 5, essentials 5 400 000 → finish. Wait until mode is `user`. |
| 2 | **Security / privacy** | Go to `security`, scroll to "Siz haqingizda nima saqlanyapti?" (`#wipeBtn`) — only card type + last 4, session only. |
| 3 | **Qalqon load** | `ensureProfile("aziza")`, go `qalqon`, click `#loadBtn`, wait for findings. |
| 4 | **AI explanation** | Click `#explainBtn`, wait for streaming, open the "Hisoblandi" (formula) details. |
| 5 | **AI letter** | Click Yandex Plus "letter" → wait for AI → `#lCopy` → close. |
| 6 | **Card limit** | Megogo limit → type `39000` → Tayyorlash → `confirmAction()`. |
| 7 | **Block payment** | Block the unused gym → `confirmAction()`. |
| 8 | **Autonomy + undo** | Set autonomy `auto` (limit 500 000) → Telegram duplicate limit `0` → executes **without confirmation** → Home feed → click Undo (24 h) → set autonomy back to `one_click`. |
| 9 | **Chat agent** | Open chat, type "Qaysi qarzimni birinchi yopay?", submit, wait for AI. |
| 10 | **Shifo (debt)** | Close chat, go `shifo`, click AI analysis, wait. |
| 11 | **Home synergy** | Go `home`, click AI summary, wait, scroll to `#synergy`. |
| 12 | **O'sish forecast** | `ensureProfile("salomat")` (pharmacy SME), go `osish`, scroll to the chart. |
| 13 | **Safety buffer** | Set `#bufRange` to 30 (dispatch `input`) → show idle money drop → back to 15. |
| 14 | **O'sish AI** | Click AI button — explains why the 7-day deposit fits and 30-day/bond don't. |
| 15 | **Open deposit** | `#openDep` → `confirmAction(3000)` (64.3 mln, rate, return date, income visible before confirm). |
| 16 | **Meros** | `ensureProfile("aziza")`, go `meros`, add trusted person "Dilnoza Karimova", "opa", "+998 90 765 43 21" (view-only rights). |
| 17 | **Audit chain** | Verify ✅ → "Buzib ko'rish" (tamper) → Verify ❌ → Restore → Verify ✅. |
| 18 | **AI payload** | Go `security`, scroll to `pre.payload` — name/card/phone replaced by `[ISM_1]`, `[KARTA_1]`, `[TEL_1]`. |
| 19 | **How it works** | Go `how` — architecture, "raqamlarni kod hisoblaydi, so'zlarni AI yozadi", business model. |
| 20 | **Logout** | `doLogout()` — all personal data wiped (audit stays). |

Suggested `dur`: 1500–4000 ms; longer on steps the audience should read (2, 12, 18, 19).

## 5. Requirements that make it reliable

- **Offline must work.** Without an API key the offline agent must still stream text and must also fill the "AI'ga nima yuborildi?" payload preview (redacted user message + redacted tool JSON), so step 18 is never empty.
- Every element the demo touches needs a stable `id` / `data-*` attribute (`#loadBtn`, `#explainBtn`, `[data-letter^='yandex']`, `[data-limit^='megogo']`, `#limVal`, `#lmGo`, `[data-block^='sport']`, `#mYes`, `#mClose`, `.feed [data-undo]`, `#chatInput`, `#chatForm`, `#shifoAiBtn`, `#aiSummaryBtn`, `#synergy`, `#bufRange`, `#idleVal`, `#osishAiBtn`, `#openDep`, `#trName`, `#trRel`, `#trPhone`, `#trSave`, `#verBtn`, `#tamperBtn`, `#restoreBtn`, `pre.payload`, `#wipeBtn`).
- Rendering code must be null-safe (animations / `requestAnimationFrame` must not crash if the view changed mid-step).
- Toasts and the SMS banner must be hidden with `visibility: hidden` when inactive (no visible edges at the top in the video).
- A failed step shows a toast and the demo continues — it must never freeze on stage.
- Demo state is isolated: demo session sees only `aziza`/`salomat`; real user data is never touched.

## 6. Done when

- Autoplay runs all 20 steps from a fresh page with **zero console errors**.
- After the run the audit log contains: Megogo limit (executed), gym block (executed), Telegram limit (auto-executed by policy → undone), deposit (executed), and the chain verifies ✅.
- `←`, `Keyingi →`, `⏵ Avto`, `✕` work at any moment, including mid-step.
- Running the demo twice in a row works (random phone, reset on start).
