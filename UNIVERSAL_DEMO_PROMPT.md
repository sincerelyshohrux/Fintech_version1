# Universal Demo Mode — Build Prompt (for any web project)

> **How to use:** copy everything below the line into your AI coding assistant (Claude Code, Cursor, etc.) while it has access to your project. Fill in the 3 fields in `[brackets]` at the top. The assistant will read your codebase, design the scenario and build the demo.

---

You are a senior front-end engineer. Add a **guided, self-driving Demo Mode** to this project.

**Project:** [project name — one sentence of what it does]
**Audience:** [e.g. hackathon judges / investors / customers]
**Length:** [e.g. 5 minutes autoplay, 7 minute live pitch]
**UI language:** [e.g. Uzbek / English]

## 0. First, study the project (do this before writing code)

1. Read the codebase: routes/views, API endpoints, main user flows, any auth/onboarding, any AI features.
2. List **every user-visible feature**. Mark the 1–3 "wow" features (the ones that win the audience).
3. Find how state is stored and how a clean demo state can be created (seed data, demo user, reset endpoint). If no reset exists, add a safe one that only touches demo data.
4. Propose the scenario (step list) to me **before** implementing, in the table format of section 4.

## 1. Core principle — real, not fake

- The demo drives the **real UI and the real API**: it clicks real buttons, types into real inputs, waits for real responses. No pre-recorded screens, no fake data paths, no `if (demo) showFakeResult()`.
- Every action the demo performs must actually happen (saved in DB, visible in logs/history), so if someone asks "is it real?", you can show them.
- The demo must not touch real user data: use a demo account / demo session / demo dataset.

## 2. Two modes

- **Manual (live pitch):** each step runs, then waits; the presenter clicks **Next →** and talks.
- **Autoplay (video recording):** all steps play by themselves, each lingering `dur` ms.

Entry: a **▶ Demo** button opens a modal: short description (state will be reset, N steps), buttons `Cancel` · `⏵ Autoplay` · `Start manually`.

On start: create/enter demo session → reset demo state → reset settings to defaults → go to the starting screen → run step 1.

## 3. Engine (copy this design)

```js
const D = { token: 0, busy: false, auto: false, timer: null, step: -1 };
class DemoCancel extends Error {}

const sleep = ms => new Promise(r => setTimeout(r, ms));
async function dwait(ms) { const t = D.token; await sleep(ms); if (t !== D.token) throw new DemoCancel(); }

async function dfind(sel, ms = 8000) {           // wait until element exists
  const t0 = Date.now(), t = D.token;
  for (;;) {
    if (t !== D.token) throw new DemoCancel();
    const el = document.querySelector(sel);
    if (el) return el;
    if (Date.now() - t0 > ms) throw new Error("not found: " + sel);
    await sleep(100);
  }
}
async function dclick(sel, pause = 450) {        // show, then click
  const el = await dfind(sel);
  el.scrollIntoView({ block: "center", behavior: "smooth" });
  await dwait(pause);
  el.click();
  return el;
}
async function dtype(sel, text, speed = 35) {    // visible typing
  const el = await dfind(sel); el.value = "";
  for (const ch of String(text)) {
    el.value += ch; el.dispatchEvent(new Event("input", { bubbles: true }));
    await dwait(speed);
  }
  return el;
}
async function dscroll(sel) {                     // never name this scrollTo
  (await dfind(sel)).scrollIntoView({ block: "start", behavior: "smooth" });
}
async function dwaitGone(sel, ms = 30000) {       // e.g. loading spinner / streaming cursor
  const t0 = Date.now();
  while (document.querySelector(sel) && Date.now() - t0 < ms) await dwait(200);
}

async function runDemo(i) {
  clearTimeout(D.timer);
  const token = ++D.token;                        // cancels any running step
  D.step = i; D.busy = true; renderBar();
  try { await DEMO[i].run(); }
  catch (e) {
    if (!(e instanceof DemoCancel)) { console.warn("demo step", i + 1, e); toast("Step incomplete — continuing"); }
  }
  if (token !== D.token) return;                  // a newer step took over
  D.busy = false; renderBar(); scheduleNext();
}
function scheduleNext() {
  clearTimeout(D.timer);
  if (!D.auto || D.step < 0) return;
  D.timer = setTimeout(() => {
    if (D.step === DEMO.length - 1) { stopDemo(); toast("Demo finished ✓"); }
    else runDemo(D.step + 1);
  }, DEMO[D.step].dur || 2500);
}
function stopDemo() { D.token++; D.busy = false; D.auto = false; clearTimeout(D.timer); D.step = -1; renderBar(); }
```

Why the token: pressing ←, Next or ✕ in the middle of a step increments the token; every helper of the old step then throws `DemoCancel` and stops. Two steps never fight over the UI.

## 4. Steps

Each step = `{ t: "narration the presenter reads", dur: ms, run: async () => { ... } }`.

```js
const DEMO = [
  { t: "1. New user signs up in 20 seconds.", dur: 2500,
    run: async () => { await dclick("#signupBtn"); await dtype("#email", "demo@example.com"); await dclick("#submit"); await dfind("#dashboard"); } },
  // ...
];
```

Scenario rules:
- **Story order**, not menu order: problem → onboarding → core value → wow feature → trust/security → how it works → business → exit.
- One idea per step. Narration contains the key **number** ("saves 478 000 per month") — numbers stick.
- Cover **every** feature, but give the wow features the longest `dur`.
- If there is a "confirm" dialog, show it ~2 s before clicking so the audience can read it.
- If there is AI/streaming output, wait for it to finish (`dwaitGone(".streaming")`).
- Show something going wrong and the system catching it (validation, tamper detection, undo) — that is the most convincing moment.
- End on a clean state (logout / reset) so the demo can run again immediately.

Plan table format:

| # | Feature | Narration (what we say) | Actions (what `run` does) | dur |
|---|---|---|---|---|

## 5. Control bar

Fixed at the bottom while running:

`[3/20] narration text   [←]  [⏵ Auto | ⏸ Pause]  [Next → | spinner | Finish]  [✕]`

- `Next` is disabled with a spinner while the step runs.
- `⏵ Auto` toggles autoplay at any moment.
- `✕` stops immediately and returns control to the user.
- Bar must not cover important UI (add bottom padding to the page while visible).

## 6. Reliability checklist (this is what makes it safe on stage)

- **Stable selectors:** add `id` / `data-*` to every element the demo touches. Never select by text or CSS position.
- **Offline fallback:** if the demo depends on an external API (AI, payments, SMS), it must have a demo/offline path that still produces realistic output. No Wi-Fi on stage must not kill the demo.
- **Rate limits / one-time data:** generate fresh values each run (random phone/email, unique ids), so rehearsing 10 times never hits "already exists" or "too many requests".
- **Never freeze:** a failed step shows a toast and the demo continues.
- **Null-safe rendering:** animations / timers must not crash if the view changed mid-step.
- **Visual polish for video:** hidden toasts/banners use `visibility: hidden` (no edges peeking), smooth scrolling, typing speed readable.
- **Isolation:** demo session can only see demo data; reset endpoint refuses to run outside demo.
- **Repeatable:** running the demo twice in a row gives the same result.

## 7. Done when

- Autoplay runs all steps from a fresh page load with **zero console errors**.
- Every action the demo performs is visible afterwards in the real data (DB / history / logs).
- ←, Next, Auto, ✕ work at any moment, including mid-step.
- Works offline (without external API keys).
- Works twice in a row.
- Also write `DEMO_SCRIPT.md`: the step table + what the presenter says + prepared answers to likely questions.
