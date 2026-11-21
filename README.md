# FinPilot — AI financial agent inside a bank app

FinPilot **protects** a customer's money (Qalqon), **grows** idle cash (O'sish) and **eases debt** (Shifo).
It finds a problem, explains it in Uzbek, and *prepares* a bank action. The action runs only with the
customer's confirmation, or inside a limit the customer set.

> Core rule: **the code computes the numbers, the AI writes the words.** Every amount comes from
> deterministic, tested Python functions. The AI agent calls them as tools, and the UI shows each
> formula under **"Hisoblandi"**.

## Run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # set ANTHROPIC_API_KEY for live AI (optional)
uvicorn app.main:app --port 8000
```

Open http://localhost:8000. A new user goes through onboarding (phone → SMS code → name → card → card code →
consent & balance). Judges can click **"Demo profil bilan ko'rish"** on the first screen, or **▶ Demo rejimi**
for the guided 7-minute flow (it starts with an automated onboarding).

Windows (PowerShell): `py -m venv .venv`, `.\.venv\Scripts\Activate.ps1`, `pip install -r requirements.txt`,
`Copy-Item .env.example .env`, `uvicorn app.main:app --port 8000`.
Without an API key the app runs in **Offline demo rejimi**: the numbers come from the same functions,
the text comes from templates, and the screen labels it.

Tests: `python -m pytest -q` (38 tests: detection rules, forecast, interest, health score, PII, policy, hash chain,
OTP expiry/lockout/resend limits, Luhn, card type, expiry, holder-name matching, full onboarding → wipe flow).

Demo test cards (pass Luhn): Humo `9860 3500 1234 4825`, UzCard `8600 1234 5678 4427`. Sample statement: `static/sample_statement.csv`.

## Modules

| Module | What it does | Status |
|---|---|---|
| 🔐 Onboarding | Phone (+998 mask) → 6-digit SMS OTP → name → card (Luhn, UzCard/Humo, expiry, holder = registered name, **no CVV/PIN**) → card OTP → consent + balance/CSV. Locked dashboard until a card is added. | full |
| 🛡 Qalqon | 90-day statement → forgotten subscriptions, trial→paid, duplicate charges, silent price hikes, unused services (rules R1–R5). Cancellation letter, card limit, merchant block. | full |
| 📈 O'sish | Cash-flow forecast to the next large payment → safe idle cash → the best deposit that **returns before** the payment. Business (pharmacy) + personal. | full |
| 🩺 Shifo | Real cost of each loan, DTI, avalanche vs snowball. | preview |
| 🕊 Meros | Account map + trusted person (view-only). | preview |
| 🏠 Home | Financial health score 0–100, net position, cross-module synergy cards. | full |

## Architecture

```
Browser (vanilla JS, SSE) ──► FastAPI
                               ├─ app/core/*      deterministic finance (qalqon, osish, shifo, health)
                               ├─ app/agent/*     Claude tool-use loop (8 tools), streaming, offline fallback
                               ├─ app/security/*  PII redaction, autonomy policy, rate limit
                               ├─ app/auth.py     onboarding endpoints, httpOnly session cookie, OTP flow
                               ├─ app/sessions.py in-memory sessions (personal data never hits SQLite)
                               ├─ app/adapters/   BankAPI → MockBank; SmsProvider → DemoSms / Eskiz.uz
                               └─ app/db.py       SQLite: actions, consent, settings, hash-chained audit
```

Action lifecycle: **Prepare → Confirm → Execute → Audit**. Autonomy levels: *Faqat maslahat* (advice only),
*Bir bosishda* (one click), *Limit ichida avtomatik* (auto within limit, allow-listed actions only, undo for 24 h).

## Security

- **Auth:** phone + SMS OTP (CSPRNG code, HMAC-hashed, 5-min expiry, single use, 60 s resend cooldown, max 4 sends / 10 min, 3 wrong → 5-min lockout). Card is confirmed with a second OTP.
- **Card minimization:** the full number is validated (Luhn, type) in the browser and wiped right away; the server receives only last4, type, expiry and holder name. CVV/PIN are never requested.
- **No persistence:** an onboarded user's profile, card, balance, statement and loans live only in server memory for the session; "Chiqish / ma'lumotlarni o'chirish" wipes them (and their settings/actions rows). No personal data in localStorage.
- Every module endpoint is scoped to the session (a user sees only their own profile; a demo session sees only demo profiles).
- PII (names, cards, accounts, phones, e-mails) is replaced with tokens (`[KARTA_1]`, `[ISM_1]`) before anything goes to the LLM and restored in the streamed answer. The **Xavfsizlik** page shows the exact payload that was sent.
- The AI can only *prepare* actions; it has no execute tool.
- Explicit consent before any analysis; can be revoked.
- Append-only audit log with a SHA-256 chain; the verify endpoint detects tampering (demo button included).
- API key stays on the server; agent endpoint is rate-limited; CSV uploads are size- and schema-checked.

## What is mocked

Bank API (MockBank), SMS delivery in `DEMO_MODE` (the code is shown in an on-screen "SMS" banner; set `SMS_PROVIDER=eskiz`
for the Eskiz.uz adapter), balance sync (manual input / CSV — Open Banking is on the roadmap), the two demo profiles,
deposit rates, and service-usage signals (e.g. last gym visit).
In production these come from the partner bank's API / open-banking gateway.

## Business model (B2B2C)

The bank embeds FinPilot in its app: a monthly licence per active user plus a share of deposits opened through FinPilot.
Free for customers. The bank gains deposits, engagement, and lower credit risk.
