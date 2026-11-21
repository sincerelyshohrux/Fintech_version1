"""Deterministic seed data for the two demo profiles.

All data is mock. A fixed random seed keeps numbers identical between runs for the same "today".
"""
import random
from datetime import date, timedelta

from app.core.shifo import annuity_payment

PROFILE_IDS = ["aziza", "salomat"]


def _add_months_day(today: date, day: int, months_back: int) -> date:
    """Date with given day-of-month, `months_back` months before today's month."""
    y, m = today.year, today.month - months_back
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, min(day, 28))


def _next_day_of_month(today: date, day: int) -> date:
    d = date(today.year, today.month, min(day, 28))
    if d <= today:
        m, y = today.month + 1, today.year
        if m == 13:
            m, y = 1, y + 1
        d = date(y, m, min(day, 28))
    return d


def _txn(d: date, desc: str, amount: int) -> dict:
    return {"date": d.isoformat(), "description": desc, "amount": int(amount)}


# ----------------------------------------------------------------- Aziza (personal)

AZIZA_LOANS = [
    {"id": "mikroqarz", "name": "Mikroqarz — \"Tez Pul\" MKT", "principal": 4_200_000, "rate": 0.42, "months_left": 8},
    {"id": "istemol", "name": "Anorbank iste'mol krediti", "principal": 11_500_000, "rate": 0.24, "months_left": 18},
    {"id": "nasiya", "name": "Uzum Nasiya (muddatli to'lov)", "principal": 2_400_000, "rate": 0.0, "months_left": 6},
]


def _aziza(today: date) -> dict:
    rng = random.Random(42)
    start = today - timedelta(days=90)
    txns: list[dict] = []

    # Salary on the 5th
    for back in range(0, 4):
        d = _add_months_day(today, 5, back)
        if start <= d <= today:
            txns.append(_txn(d, "ISH HAQI - \"DATASOFT\" MCHJ", 9_500_000))

    # Daily life: groceries, taxi, food, marketplace (irregular amounts -> not recurring)
    d = start
    while d <= today:
        if rng.random() < 0.32:
            txns.append(_txn(d, "KORZINKA SUPERMARKET", -rng.randrange(90, 480) * 1000))
        if rng.random() < 0.45:
            txns.append(_txn(d, "YANDEX GO TAXI", -rng.randrange(14, 46) * 1000))
        if rng.random() < 0.15:
            txns.append(_txn(d, "EVOS", -rng.randrange(45, 140) * 1000))
        if rng.random() < 0.06:
            txns.append(_txn(d, "UZUM MARKET", -rng.randrange(80, 650) * 1000))
        d += timedelta(days=1)

    # Legit recurring payments
    payments = {l["id"]: annuity_payment(l["principal"], l["rate"], l["months_left"]) for l in AZIZA_LOANS}
    for back in range(0, 4):
        for day, desc, amt in [(12, "BEELINE UZ MOBIL ALOQA", -65_000),
                               (20, "UZONLINE INTERNET", -150_000),
                               (15, "HUDUDGAZTA'MINOT", -rng.randrange(80, 150) * 1000),
                               (28, "ANORBANK KREDIT TO'LOVI", -payments["istemol"]),
                               (28, "TEZ PUL MKT QARZ TO'LOVI", -payments["mikroqarz"]),
                               (10, "UZUM NASIYA TO'LOVI", -payments["nasiya"])]:
            dd = _add_months_day(today, day, back)
            if start <= dd <= today:
                txns.append(_txn(dd, desc, amt))

    # Finding 1: streaming trial (1 so'm) that silently converted to paid
    txns.append(_txn(today - timedelta(days=80), "YANDEX PLUS OBUNA", -1))
    for back in (66, 36, 6):
        txns.append(_txn(today - timedelta(days=back), "YANDEX PLUS OBUNA", -59_000))

    # Finding 2: the same service paid through two channels (App Store + direct bot)
    for back in (58, 28):
        txns.append(_txn(today - timedelta(days=back), "APPLE.COM/BILL TELEGRAM PREMIUM", -59_000))
    for back in (45, 15):
        txns.append(_txn(today - timedelta(days=back), "TELEGRAM PREMIUM @PREMIUMBOT", -49_000))

    # Finding 3: gym membership, no visits for 3+ months
    for back in (84, 54, 24):
        txns.append(_txn(today - timedelta(days=back), "SPORT ZAL \"OLIMP\" ABONEMENT", -350_000))

    # Finding 4: silent price increase
    for back, amt in ((81, 39_000), (51, 39_000), (21, 49_000)):
        txns.append(_txn(today - timedelta(days=back), "MEGOGO.NET OBUNA", -amt))

    txns.sort(key=lambda t: t["date"])
    debt_payments = sum(payments.values())
    return {
        "id": "aziza",
        "kind": "personal",
        "title": "Aziza — shaxsiy",
        "owner_name": "Aziza Karimova",
        "sensitive_names": ["Aziza Karimova", "Karimova", "Aziza"],
        "phone": "+998 90 123 45 67",
        "email": "aziza.karimova@example.uz",
        "accounts": [
            {"id": "main", "name": "Asosiy karta (Uzcard)", "card_number": "8600 1234 5678 4421", "balance": 4_850_000},
            {"id": "save", "name": "Jamg'arma kartasi (Humo)", "card_number": "9860 3300 1122 7712", "balance": 3_900_000},
        ],
        "loans": AZIZA_LOANS,
        "statement": txns,
        # Activity signals per service (mock "last usage" from partner data / user)
        "usage": {"sport zal olimp": (today - timedelta(days=97)).isoformat(),
                  "yandex plus": (today - timedelta(days=70)).isoformat(),
                  "megogo": (today - timedelta(days=2)).isoformat(),
                  "telegram premium": (today - timedelta(days=0)).isoformat()},
        "income_model": {"type": "monthly_salary", "day": 5, "amount": 9_500_000},
        "monthly_income": 9_500_000,
        "essentials_monthly": 5_400_000,
        "debt_payments_monthly": debt_payments,
        "obligations": [
            {"date": _next_day_of_month(today, 28).isoformat(), "name": "Kredit to'lovlari", "amount": payments["istemol"] + payments["mikroqarz"]},
            {"date": _next_day_of_month(today, 10).isoformat(), "name": "Uzum Nasiya", "amount": payments["nasiya"]},
            {"date": _next_day_of_month(today, 15).isoformat(), "name": "Kommunal to'lovlar", "amount": 320_000},
        ],
        "large_payment_threshold": 1_000_000,
        "instruments": [
            {"id": "jamgarma", "name": "Jamg'arma hisobi (istalgan payt yechish)", "term_days": 1, "rate": 0.14,
             "min_amount": 100_000, "rollover": True, "penalty": "yo'q"},
            {"id": "omonat30", "name": "1 oylik omonat", "term_days": 30, "rate": 0.19, "min_amount": 500_000,
             "rollover": False, "penalty": "foiz yo'qotiladi"},
            {"id": "omonat90", "name": "3 oylik omonat", "term_days": 90, "rate": 0.21, "min_amount": 1_000_000,
             "rollover": False, "penalty": "foiz yo'qotiladi"},
        ],
        "max_lock_days": 31,  # personal: surplus beyond this salary cycle may be locked up to one month
        "default_buffer_pct": 0.15,
    }


# ----------------------------------------------------------------- Pharmacy (business)

WEEKDAY_FACTOR = [1.0, 0.97, 1.0, 1.03, 1.08, 1.18, 0.82]  # Mon..Sun

SALOMAT_LOANS = [
    {"id": "aylanma", "name": "Hamkorbank aylanma krediti", "principal": 60_000_000, "rate": 0.22, "months_left": 14},
]


def _salomat(today: date) -> dict:
    rng = random.Random(7)
    history = []
    for back in range(30, 0, -1):
        d = today - timedelta(days=back)
        revenue = round(7_600_000 * WEEKDAY_FACTOR[d.weekday()] * rng.uniform(0.92, 1.08), -3)
        expense = round(2_300_000 * rng.uniform(0.9, 1.1), -3)
        history.append({"date": d.isoformat(), "revenue": int(revenue), "expense": int(expense), "paid": 0})
    # Last month's large scheduled payments (same schedule as the upcoming obligations)
    for back, amount in ((26, 8_500_000), (21, 24_000_000), (18, 15_000_000), (14, 32_000_000), (12, 8_500_000), (5, 11_000_000)):
        history[30 - back]["paid"] += amount

    start = today - timedelta(days=90)
    txns: list[dict] = []
    d = start
    while d <= today:
        txns.append(_txn(d, "POS TERMINAL TUSHUMI", round(7_600_000 * WEEKDAY_FACTOR[d.weekday()] * rng.uniform(0.92, 1.08), -3)))
        if d.weekday() in (1, 4):
            txns.append(_txn(d, "GRAND PHARM YETKAZIB BERUVCHI", -rng.randrange(6_000, 11_000) * 1000))
        d += timedelta(days=1)
    for back in range(0, 4):
        for day, desc, amt in [(3, "1C:KASSA LITSENZIYA OBUNA", -180_000),
                               (17, "SOFT-SERVIS 1C KASSA", -180_000),
                               (8, "KUZATUV KAMERA BULUT XIZMATI", -95_000),
                               (25, "UZTELECOM INTERNET", -250_000)]:
            dd = _add_months_day(today, day, back)
            if start <= dd <= today:
                txns.append(_txn(dd, desc, amt))
    for back, amt in ((80, 120_000), (50, 120_000), (20, 150_000)):
        txns.append(_txn(today - timedelta(days=back), "PLAYMOBILE SMS XABARNOMA", -amt))
    txns.sort(key=lambda t: t["date"])

    payment = annuity_payment(SALOMAT_LOANS[0]["principal"], SALOMAT_LOANS[0]["rate"], SALOMAT_LOANS[0]["months_left"])
    avg_rev = sum(h["revenue"] for h in history) / len(history)
    return {
        "id": "salomat",
        "kind": "business",
        "title": "Dorixona \"Salomat\" — biznes",
        "owner_name": "Rustam Aliyev",
        "sensitive_names": ["Rustam Aliyev", "Aliyev", "Rustam"],
        "phone": "+998 93 555 12 34",
        "email": "salomat.dorixona@example.uz",
        "accounts": [
            {"id": "main", "name": "Asosiy hisob raqami", "account_number": "20208000904512345001", "balance": 96_400_000},
            {"id": "card", "name": "Korporativ karta (Uzcard)", "card_number": "8600 4900 2210 3318", "balance": 3_200_000},
        ],
        "loans": SALOMAT_LOANS,
        "statement": txns,
        "usage": {},
        "history": history,
        "income_model": {"type": "daily_weekday"},
        "monthly_income": int(avg_rev * 30),
        "opex_daily": int(sum(h["expense"] for h in history) / len(history)),
        "debt_payments_monthly": payment,
        "obligations": [
            {"date": (today + timedelta(days=2)).isoformat(), "name": "Grand Pharm (yetkazib beruvchi)", "amount": 8_500_000},
            {"date": (today + timedelta(days=9)).isoformat(), "name": "Ish haqi (8 xodim)", "amount": 24_000_000},
            {"date": (today + timedelta(days=12)).isoformat(), "name": "Ijara", "amount": 15_000_000},
            {"date": (today + timedelta(days=16)).isoformat(), "name": "Asklepiy Distribution", "amount": 32_000_000},
            {"date": (today + timedelta(days=25)).isoformat(), "name": "Soliq (QQS)", "amount": 11_000_000},
            {"date": (today + timedelta(days=7)).isoformat(), "name": "Aylanma kredit to'lovi", "amount": payment},
        ],
        "large_payment_threshold": 10_000_000,
        "instruments": [
            {"id": "overnight", "name": "Overnayt depozit (har kuni yangilanadi)", "term_days": 1, "rate": 0.12,
             "min_amount": 10_000_000, "rollover": True, "penalty": "yo'q"},
            {"id": "dep7", "name": "7 kunlik depozit", "term_days": 7, "rate": 0.17, "min_amount": 20_000_000,
             "rollover": False, "penalty": "foiz yo'qotiladi"},
            {"id": "dep30", "name": "30 kunlik depozit", "term_days": 30, "rate": 0.20, "min_amount": 20_000_000,
             "rollover": False, "penalty": "foiz yo'qotiladi"},
            {"id": "bond28", "name": "Qisqa muddatli obligatsiya (28 kun)", "term_days": 28, "rate": 0.195,
             "min_amount": 50_000_000, "rollover": False, "penalty": "bozor narxida sotish"},
        ],
        "max_lock_days": None,  # business: must return before the next large payment
        "default_buffer_pct": 0.15,
    }


def build_profiles(today: date) -> dict[str, dict]:
    return {"aziza": _aziza(today), "salomat": _salomat(today)}


# ----------------------------------------------------------------- Onboarded user (built from session data)

USER_INSTRUMENTS = [
    {"id": "jamgarma", "name": "Jamg'arma hisobi (istalgan payt yechish)", "term_days": 1, "rate": 0.14,
     "min_amount": 100_000, "rollover": True, "penalty": "yo'q"},
    {"id": "omonat30", "name": "1 oylik omonat", "term_days": 30, "rate": 0.19, "min_amount": 500_000,
     "rollover": False, "penalty": "foiz yo'qotiladi"},
    {"id": "omonat90", "name": "3 oylik omonat", "term_days": 90, "rate": 0.21, "min_amount": 1_000_000,
     "rollover": False, "penalty": "foiz yo'qotiladi"},
]


def build_user_profile(s, today: date) -> dict:
    """Unified Financial Graph of an onboarded user. Only last4/type of the card are known."""
    label = {"uzcard": "UzCard", "humo": "Humo"}.get((s.card or {}).get("type"), "Karta")
    last4 = (s.card or {}).get("last4", "")
    loans = list(s.loans)
    debt_payments = sum(annuity_payment(l["principal"], l["rate"], l["months_left"]) for l in loans)
    income = s.monthly_income or 0
    return {
        "id": s.uid,
        "kind": "personal",
        "title": f"{s.first} {s.last[:1]}.",
        "owner_name": f"{s.first} {s.last}",
        "sensitive_names": [f"{s.first} {s.last}", f"{s.last} {s.first}", s.first, s.last],
        "phone": f"+998 {s.phone[3:5]} {s.phone[5:8]} {s.phone[8:10]} {s.phone[10:]}" if s.phone else "",
        "email": "",
        "accounts": [{"id": "main", "name": f"{label} karta", "masked": f"{label} •••• {last4}", "last4": last4,
                      "balance": s.balance or 0}],
        "loans": loans,
        "statement": s.statement or [],
        "usage": {},
        "income_model": {"type": "monthly_salary", "day": s.payday or 1, "amount": income},
        "monthly_income": income,
        "essentials_monthly": s.essentials or 0,
        "debt_payments_monthly": debt_payments,
        "obligations": [],
        "large_payment_threshold": 1_000_000,
        "instruments": USER_INSTRUMENTS,
        "max_lock_days": 31,
        "default_buffer_pct": 0.15,
        "missing": [k for k, v in (("balans", s.balance), ("oylik daromad", s.monthly_income),
                                   ("oylik kuni", s.payday), ("zarur xarajatlar", s.essentials)) if v is None],
    }
