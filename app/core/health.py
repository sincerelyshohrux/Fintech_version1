"""Financial health score, net position and cross-module synergy (all deterministic)."""
from app.core.money import fmt_pct, fmt_som
from app.core.osish import interest
from app.core.shifo import debt_overview


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def health_score(profile: dict, qalqon: dict, treasury: dict, resolved_ids: set[str]) -> dict:
    income = profile["monthly_income"]
    debt = debt_overview(profile["loans"], income)
    if profile["kind"] == "business":
        spend = profile["opex_daily"] * 30 + sum(o["amount"] for o in profile["obligations"])
    else:
        spend = profile["essentials_monthly"] + debt["monthly_payments"] + 900_000  # + discretionary estimate
    waste = sum(f["monthly_saving"] for f in qalqon["findings"]
                if f["level"] != "past" and f["id"] not in resolved_ids)
    liquid = max(1, treasury["balance"])
    savings_rate = (income - spend) / income if income else 0
    idle_ratio = treasury["idle_cash"] / liquid

    parts = {
        "Jamg'arish darajasi": round(25 * _clamp(savings_rate / 0.20)),
        "Obuna isrofi": round(25 * (1 - _clamp((waste / income) / 0.10))) if income else 25,
        "Bo'sh turgan pul": round(25 * (1 - _clamp(idle_ratio / 0.5))),
        "Qarz yuki (DTI)": round(25 * (1 - _clamp(debt["dti"] / 0.5))),
    }
    return {
        "score": sum(parts.values()),
        "parts": parts,
        "hisob": {
            "formula": "har biri 0–25: jamg'arish = 25 × min(1, j/20%); isrof = 25 × (1 − min(1, isrof/daromad / 10%)); "
                       "bo'sh pul = 25 × (1 − min(1, bo'sh/balans / 50%)); DTI = 25 × (1 − min(1, DTI / 50%))",
            "inputs": {"daromad": fmt_som(income), "chiqim": fmt_som(spend), "isrof (oylik)": fmt_som(waste),
                       "bo'sh pul": fmt_som(treasury["idle_cash"]), "balans": fmt_som(liquid), "DTI": fmt_pct(debt["dti"])},
            "outputs": {k: f"{v}/25" for k, v in parts.items()},
        },
        "waste_monthly": waste,
    }


def net_position(profile: dict, deposits: list[dict]) -> dict:
    liquid = sum(a["balance"] for a in profile["accounts"])  # deposits are carved out of these balances
    debt = sum(l["principal"] for l in profile["loans"])
    return {"assets": liquid, "liabilities": debt, "net": liquid - debt,
            "in_deposits": sum(d["amount"] for d in deposits)}


def synergy_cards(profile: dict, qalqon: dict, treasury: dict, health: dict, resolved_ids: set[str]) -> list[dict]:
    cards = []
    unresolved = [f for f in qalqon["findings"] if f["level"] != "past" and f["id"] not in resolved_ids]
    monthly = sum(f["monthly_saving"] for f in unresolved)
    rates = sorted((i for i in profile["instruments"] if not i["rollover"]), key=lambda i: i["term_days"])
    rate = rates[0]["rate"] if rates else 0.15

    if monthly > 0:
        yearly_interest = round(monthly * rate * 6.5)  # monthly contributions: average 6.5 months in deposit
        cards.append({
            "id": "qalqon-osish",
            "from": "🛡 Qalqon", "to": "📈 O'sish",
            "title": f"Qalqon oyiga {fmt_som(monthly)} bo'shatadi",
            "text": f"Shu pulni har oy {fmt_pct(rate)} li omonatga yo'naltirsangiz, yiliga {fmt_som(monthly * 12)} "
                    f"jamg'arma + taxminan {fmt_som(yearly_interest)} foiz.",
            "formula": f"{fmt_som(monthly)} × {fmt_pct(rate)} × 6,5 oy (o'rtacha) = {fmt_som(yearly_interest)}",
            "action": {"type": "create_standing_order", "params": {"amount": monthly, "day": 6,
                                                                    "purpose": "Qalqon tejamasi → jamg'arma"}},
        })

    debt = debt_overview(profile["loans"], profile["monthly_income"])
    paid = [l for l in debt["loans"] if l["rate"] > 0]
    if paid:
        worst = max(paid, key=lambda l: l["rate"])
        rec = treasury.get("recommendation")
        best_rate = rec["rate"] if rec else max((i["rate"] for i in profile["instruments"]), default=0)
        if worst["rate"] > best_rate:
            amount = min(worst["principal"], max(500_000, treasury["idle_cash"] // 2 // 100_000 * 100_000))
            gain = interest(amount, worst["rate"] - best_rate, 365)
            cards.append({
                "id": "osish-shifo",
                "from": "📈 O'sish", "to": "🩺 Shifo",
                "title": f"{worst['name']}: {fmt_pct(worst['rate'])} — depozitdan qimmat",
                "text": f"Eng yaxshi depozit {fmt_pct(best_rate)} beradi, bu qarz esa {fmt_pct(worst['rate'])} oladi. "
                        f"{fmt_som(amount)}ni muddatidan oldin to'lash yiliga ~{fmt_som(gain)} tejaydi.",
                "formula": f"{fmt_som(amount)} × ({fmt_pct(worst['rate'])} − {fmt_pct(best_rate)}) × 365/365 = {fmt_som(gain)}",
                "action": {"type": "prepay_loan", "params": {"loan_id": worst["id"], "amount": amount}},
            })

    gain_pts = 25 - health["parts"]["Obuna isrofi"]
    rec = treasury.get("recommendation")
    if unresolved and gain_pts > 0:
        top = unresolved[0]
        cards.append({
            "id": "qalqon-health",
            "from": "🛡 Qalqon", "to": "❤️ Salomatlik",
            "title": f"Intizom: +{gain_pts} ball moliyaviy salomatlikka",
            "text": f"Shubhali {len(unresolved)} ta to'lovni yopsangiz, \"Obuna isrofi\" ko'rsatkichi 25/25 ga chiqadi. "
                    f"Eng kattasidan boshlang: {top['merchant']} ({fmt_som(top['monthly_saving'])}/oy).",
            "formula": f"isrof {fmt_som(health['waste_monthly'])} → 0; ball {health['parts']['Obuna isrofi']} → 25",
            "action": {"type": "block_merchant", "params": {"finding_id": top["id"]}},
        })
    elif rec:
        yearly = interest(rec["amount"], rec["rate"], 365)
        cards.append({
            "id": "osish-health",
            "from": "📈 O'sish", "to": "❤️ Salomatlik",
            "title": f"{fmt_som(rec['amount'])} bo'sh turibdi",
            "text": f"Bu pul hozir hech narsa ishlamayapti. To'lov jadvaliga mos joylashtirib borilsa, yiliga taxminan "
                    f"{fmt_som(yearly)} qo'shimcha daromad va \"Bo'sh turgan pul\" ko'rsatkichi 25/25.",
            "formula": f"{fmt_som(rec['amount'])} × {fmt_pct(rec['rate'])} × 365/365 = {fmt_som(yearly)}",
            "action": {"type": "open_deposit", "params": {"instrument_id": rec["instrument_id"], "amount": rec["amount"]}},
        })
    return cards[:3]
