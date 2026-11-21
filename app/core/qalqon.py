"""Qalqon: deterministic detection of recurring charges, trials, duplicates, price hikes and unused services."""
import re
import statistics
from collections import defaultdict
from datetime import date

from app.core.money import fmt_som

# Map descriptor keywords to a canonical service (used for cross-channel duplicates and usage signals)
SERVICE_KEYWORDS = [
    ("telegram premium", ["telegram premium"]),
    ("yandex plus", ["yandex plus"]),
    ("megogo", ["megogo"]),
    ("sport zal olimp", ["olimp"]),
    ("1c kassa", ["1c"]),
    ("sms xabarnoma", ["playmobile", "sms xabarnoma"]),
    ("icloud", ["icloud"]),
    ("netflix", ["netflix"]),
    ("spotify", ["spotify"]),
]
# Recurring payments that are normal obligations (telecom, internet, utilities, loans)
ESSENTIAL_KEYWORDS = ["beeline", "ucell", "uzmobile", "mobiuz", "uzonline", "uztelecom", "internet",
                      "kredit", "qarz", "nasiya", "hududgaz", "elektr", "suv", "kamera"]

LEVEL_ORDER = {"past": 0, "o'rta": 1, "yuqori": 2}

RULES = {
    "R1": "Muntazam to'lov (bir xil summa, ~7 yoki ~30 kun oralig'ida)",
    "R2": "Sinov davri pullik obunaga aylangan (≤1 000 so'm, keyin ≥10× katta to'lov)",
    "R3": "Takroriy to'lov (bir xizmat ikki kanal orqali yoki 3 kun ichida ikki marta)",
    "R4": "Narx jimgina oshgan (oldingi medianadan ≥10%)",
    "R5": "Xizmatdan 60 kundan ortiq foydalanilmagan",
}


def normalize(description: str) -> str:
    text = description.lower()
    text = re.sub(r"#?\d{4,}", " ", text)
    text = re.sub(r"\b(toshkent|tashkent|uzb|uz)\b", " ", text)
    text = re.sub(r"[^a-z0-9а-яё'@./ ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def service_of(merchant_key: str) -> str:
    for service, words in SERVICE_KEYWORDS:
        if any(w in merchant_key for w in words):
            return service
    return merchant_key


def _period(intervals: list[int]) -> str | None:
    if intervals and all(26 <= i <= 34 for i in intervals):
        return "oylik"
    if intervals and all(5 <= i <= 9 for i in intervals):
        return "haftalik"
    return None


def _monthly(amount: int, period: str) -> int:
    return round(amount * 52 / 12) if period == "haftalik" else amount


def detect(statement: list[dict], usage: dict[str, str], today: date, card_last4: str = "") -> dict:
    """Return findings for all recurring merchants plus duplicate charges."""
    groups: dict[str, list[dict]] = defaultdict(list)
    display: dict[str, str] = {}
    for t in statement:
        if t["amount"] >= 0:
            continue
        key = normalize(t["description"])
        groups[key].append({"date": date.fromisoformat(t["date"]), "amount": -int(t["amount"])})
        display.setdefault(key, t["description"])

    findings: dict[str, dict] = {}

    for key, charges in groups.items():
        charges.sort(key=lambda c: c["date"])
        flags: list[tuple[str, str, str]] = []  # (rule, level, reason)

        # R3b: exact duplicate charge within 3 days
        for a, b in zip(charges, charges[1:]):
            if a["amount"] == b["amount"] and (b["date"] - a["date"]).days <= 3 and a["amount"] >= 10_000:
                flags.append(("R3", "yuqori", f"{fmt_som(a['amount'])} {(b['date'] - a['date']).days} kun ichida ikki marta yechilgan"))
                break

        paid = charges
        trial = False
        if len(charges) >= 2 and charges[0]["amount"] <= 1_000 and charges[1]["amount"] >= 10 * max(charges[0]["amount"], 1) \
                and 3 <= (charges[1]["date"] - charges[0]["date"]).days <= 31:
            trial = True
            paid = charges[1:]

        intervals = [(b["date"] - a["date"]).days for a, b in zip(paid, paid[1:])]
        period = _period(intervals)
        if not period and not trial and not flags:
            continue

        amounts = [c["amount"] for c in paid]
        prev = amounts[:-1] if len(amounts) >= 3 else amounts
        median_prev = statistics.median(prev)
        last = amounts[-1]
        similar = all(abs(a - median_prev) <= 0.10 * median_prev for a in prev)
        if period and not similar:
            continue  # irregular amounts: everyday spending, not a subscription

        if trial:
            flags.append(("R2", "yuqori", f"{charges[0]['date'].strftime('%d.%m')} kuni {fmt_som(charges[0]['amount'])} sinov, "
                                          f"keyin har oy {fmt_som(paid[0]['amount'])} yechilmoqda"))
        hike_delta = 0
        if len(amounts) >= 3 and last >= 1.10 * median_prev:
            hike = (last - median_prev) / median_prev
            hike_delta = int(last - median_prev)
            flags.append(("R4", "o'rta", f"Narx {fmt_som(median_prev)}dan {fmt_som(last)}ga oshgan (+{round(hike * 100)}%), xabar berilmagan"))

        service = service_of(key)
        last_used = usage.get(service)
        if last_used:
            idle_days = (today - date.fromisoformat(last_used)).days
            if idle_days > 60:
                flags.append(("R5", "yuqori" if idle_days > 90 else "o'rta",
                              f"Oxirgi foydalanish {idle_days} kun oldin, lekin to'lov davom etmoqda"))

        essential = any(w in key for w in ESSENTIAL_KEYWORDS)
        per = period or "oylik"
        monthly = _monthly(last, per)
        findings[key] = {
            "merchant": display[key],
            "merchant_key": key,
            "service": service,
            "amount": last,
            "frequency": per,
            "occurrences": len(charges),
            "last_charge": charges[-1]["date"].isoformat(),
            "monthly_cost": monthly,
            "flags": flags,
            "hike_delta": hike_delta,
            "essential": essential,
            "card_last4": card_last4,
        }

    # R3a: same service paid through two different channels
    by_service: dict[str, list[str]] = defaultdict(list)
    for key, f in findings.items():
        by_service[f["service"]].append(key)
    for service, keys in by_service.items():
        if len(keys) >= 2 and service in {s for s, _ in SERVICE_KEYWORDS}:
            keys.sort(key=lambda k: -findings[k]["monthly_cost"])
            dup = findings[keys[0]]  # the more expensive channel is the one to cancel
            other = findings[keys[1]]
            dup["flags"].append(("R3", "yuqori", f"Xuddi shu xizmat \"{other['merchant']}\" orqali ham to'lanmoqda — ikki marta to'layapsiz"))

    result = []
    for key, f in findings.items():
        rules = [r for r, _, _ in f["flags"]]
        if f["flags"]:
            level = max((lvl for _, lvl, _ in f["flags"]), key=lambda l: LEVEL_ORDER[l])
            reason = "; ".join(reason for _, _, reason in f["flags"])
        else:
            level = "past"
            reason = "Muntazam majburiy to'lov (aloqa, internet, kommunal yoki kredit) — normal" if f["essential"] \
                else "Muntazam to'lov, shubhali belgi topilmadi"
            rules = ["R1"]
        if "R2" in rules or "R3" in rules or "R5" in rules:
            saving = f["monthly_cost"]
        elif "R4" in rules:
            saving = f["hike_delta"]  # the increase: negotiate or switch back to the old plan
        else:
            saving = 0
        result.append({
            "id": re.sub(r"[^a-z0-9]+", "-", f["service"]).strip("-") + "-" + "".join(sorted(set(rules))).lower(),
            "merchant": f["merchant"],
            "service": f["service"],
            "amount": f["amount"],
            "frequency": f["frequency"],
            "occurrences": f["occurrences"],
            "last_charge": f["last_charge"],
            "monthly_cost": f["monthly_cost"],
            "level": level,
            "rules": sorted(set(rules)),
            "reason": reason,
            "monthly_saving": saving,
            "card_last4": f["card_last4"],
        })

    result.sort(key=lambda r: (-LEVEL_ORDER[r["level"]], -r["monthly_saving"], r["merchant"]))
    flagged = [r for r in result if r["level"] != "past"]
    potential = sum(r["monthly_saving"] for r in flagged)
    return {
        "findings": result,
        "flagged_count": len(flagged),
        "potential_monthly": potential,
        "potential_yearly": potential * 12,
        "transactions_analyzed": len(statement),
        "hisob": {
            "formula": "R1: oraliq 30±4 yoki 7±2 kun, summa ±10%; R2: ≤1 000 so'm → 3–31 kunda ≥10×; "
                       "R3: bir xizmat 2 kanalda yoki 3 kunda 2 marta; R4: oxirgi to'lov ≥ mediana × 1,10; R5: foydalanilmagan > 60 kun",
            "inputs": {"tranzaksiyalar": len(statement), "davr": "90 kun"},
            "outputs": {"shubhali topilmalar": len(flagged), "oylik tejash": fmt_som(potential),
                        "yillik tejash": fmt_som(potential * 12)},
        },
    }


def parse_csv(text: str, max_rows: int = 5000) -> list[dict]:
    """Parse CSV with columns date, description, amount. Raises ValueError with an Uzbek message."""
    import csv
    import io

    reader = csv.DictReader(io.StringIO(text))
    cols = {c.strip().lower() for c in (reader.fieldnames or [])}
    if not {"date", "description", "amount"} <= cols:
        raise ValueError("CSV faylda date, description, amount ustunlari bo'lishi kerak")
    rows = []
    for i, row in enumerate(reader, start=2):
        if len(rows) >= max_rows:
            raise ValueError(f"Juda ko'p qator (maksimum {max_rows})")
        row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
        raw_date = row["date"]
        try:
            if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", raw_date):
                dd, mm, yy = raw_date.split(".")
                d = date(int(yy), int(mm), int(dd))
            else:
                d = date.fromisoformat(raw_date[:10])
            amount = int(round(float(row["amount"].replace(" ", "").replace(" ", "").replace(",", "."))))
        except ValueError:
            raise ValueError(f"{i}-qatorda sana yoki summa noto'g'ri: {raw_date!r}, {row.get('amount')!r}")
        if not row["description"]:
            raise ValueError(f"{i}-qatorda description bo'sh")
        rows.append({"date": d.isoformat(), "description": row["description"][:120], "amount": amount})
    if not rows:
        raise ValueError("CSV faylda ma'lumot yo'q")
    rows.sort(key=lambda r: r["date"])
    return rows
