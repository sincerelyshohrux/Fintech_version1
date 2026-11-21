"""O'sish: deterministic cash forecast, idle-cash calculation and instrument selection."""
from datetime import date, timedelta

from app.core.money import fmt_date, fmt_pct, fmt_som

INFLOW_CONFIDENCE = 0.7  # only 70% of forecast revenue is counted when reserving cash


def interest(amount: int, annual_rate: float, days: int) -> int:
    """Simple interest: amount × rate × days / 365, rounded to whole so'm."""
    return round(amount * annual_rate * days / 365)


def available_balance(profile: dict, deposits: list[dict]) -> int:
    """Liquid balance minus money currently locked in deposits opened through FinPilot."""
    liquid = sum(a["balance"] for a in profile["accounts"])
    locked = sum(d["amount"] for d in deposits)
    return liquid - locked


def _weekday_inflows(profile: dict) -> list[float]:
    hist = profile["history"]
    out = []
    for wd in range(7):
        vals = [h["revenue"] for h in hist if date.fromisoformat(h["date"]).weekday() == wd]
        out.append(sum(vals) / len(vals) if vals else 0.0)
    return out


def _daily_opex(profile: dict) -> float:
    if profile["kind"] == "business":
        return float(profile["opex_daily"])
    return profile["essentials_monthly"] / 30


def forecast(profile: dict, today: date, days: int, deposits: list[dict]) -> list[dict]:
    """Day-by-day balance forecast including scheduled obligations and deposit returns."""
    balance = available_balance(profile, deposits)
    model = profile["income_model"]
    weekday_in = _weekday_inflows(profile) if model["type"] == "daily_weekday" else None
    opex = _daily_opex(profile)
    rows = []
    for i in range(1, days + 1):
        d = today + timedelta(days=i)
        if weekday_in:
            inflow = weekday_in[d.weekday()]
        else:
            inflow = model["amount"] if d.day == model["day"] else 0
        obligations = [o for o in profile["obligations"] if o["date"] == d.isoformat()]
        returns = sum(dep["amount"] + dep["expected_earnings"] for dep in deposits if dep["return_date"] == d.isoformat())
        out = opex + sum(o["amount"] for o in obligations)
        balance = balance + inflow + returns - out
        rows.append({"date": d.isoformat(), "inflow": round(inflow), "opex": round(opex),
                     "obligations": obligations, "returns": returns, "balance": round(balance)})
    return rows


def _next_income_date(profile: dict, today: date) -> date | None:
    model = profile["income_model"]
    if model["type"] != "monthly_salary":
        return None
    d = today + timedelta(days=1)
    while d.day != model["day"]:
        d += timedelta(days=1)
    return d


def treasury(profile: dict, today: date, buffer_pct: float | None, deposits: list[dict]) -> dict:
    """Compute safe idle cash and pick the best instrument that returns in time."""
    buffer_pct = profile["default_buffer_pct"] if buffer_pct is None else max(0.0, min(0.5, buffer_pct))
    fc = forecast(profile, today, 35, deposits)
    balance = available_balance(profile, deposits)
    threshold = profile["large_payment_threshold"]
    upcoming = sorted((o for o in profile["obligations"] if date.fromisoformat(o["date"]) > today),
                      key=lambda o: o["date"])
    next_large = next((o for o in upcoming if o["amount"] >= threshold), None)

    if profile["kind"] == "business":
        horizon_end = date.fromisoformat(next_large["date"]) if next_large else today + timedelta(days=14)
        window = [r for r in fc if r["date"] <= horizon_end.isoformat()]
        obligations_sum = sum(o["amount"] for r in window for o in r["obligations"])
        opex_sum = sum(r["opex"] for r in window)
        inflow_sum = round(sum(r["inflow"] for r in window) * INFLOW_CONFIDENCE)
        need = max(0, obligations_sum + opex_sum - inflow_sum)
        monthly_outflow = round(_daily_opex(profile) * 30 + sum(o["amount"] for o in upcoming
                                if date.fromisoformat(o["date"]) <= today + timedelta(days=30)))
        lock_limit_days = (horizon_end - today).days - 1
        constraint_text = (f"keyingi katta to'lov ({next_large['name']}, {fmt_som(next_large['amount'])}) "
                           f"{fmt_date(horizon_end)} kuni — pul kamida 1 kun oldin qaytishi kerak") if next_large else \
            "14 kun ichida katta to'lov yo'q"
    else:
        income_date = _next_income_date(profile, today)
        horizon_end = income_date - timedelta(days=1)
        window = [r for r in fc if r["date"] <= horizon_end.isoformat()]
        obligations_sum = sum(o["amount"] for r in window for o in r["obligations"])
        opex_sum = sum(r["opex"] for r in window)
        inflow_sum = 0
        need = obligations_sum + opex_sum
        monthly_outflow = profile["essentials_monthly"] + profile["debt_payments_monthly"]
        lock_limit_days = profile["max_lock_days"]
        constraint_text = (f"keyingi ish haqi {fmt_date(income_date)} kuni; ungacha bo'lgan xarajatlar va to'lovlar zaxiraga olindi, "
                           f"ortiqcha pul {lock_limit_days} kungacha joylashtiriladi")

    buffer = round(buffer_pct * monthly_outflow)
    idle_raw = balance - need - buffer
    idle = max(0, idle_raw // 100_000 * 100_000)  # round down to 100 000

    instruments = []
    for ins in profile["instruments"]:
        eff_days = max(1, lock_limit_days) if ins["rollover"] else ins["term_days"]
        reasons = []
        if not ins["rollover"] and ins["term_days"] > lock_limit_days:
            reasons.append(f"muddati ({ins['term_days']} kun) to'lovdan oldin tugamaydi")
        if idle < ins["min_amount"]:
            reasons.append(f"minimal summa {fmt_som(ins['min_amount'])}")
        maturity = today + timedelta(days=eff_days if ins["rollover"] else ins["term_days"])
        instruments.append({
            **ins,
            "eligible": not reasons,
            "ineligible_reason": "; ".join(reasons),
            "effective_days": eff_days,
            "expected_earnings": interest(idle, ins["rate"], eff_days) if idle else 0,
            "maturity_date": maturity.isoformat(),
        })
    eligible = [i for i in instruments if i["eligible"]]
    best = max(eligible, key=lambda i: i["expected_earnings"]) if eligible and idle > 0 else None

    payment_date = next_large["date"] if (next_large and profile["kind"] == "business") else None
    recommendation = None
    if best:
        recommendation = {
            "instrument_id": best["id"],
            "instrument_name": best["name"],
            "amount": idle,
            "rate": best["rate"],
            "days": best["effective_days"],
            "maturity_date": best["maturity_date"],
            "return_date": best["maturity_date"],
            "payment_date": payment_date,
            "expected_earnings": best["expected_earnings"],
        }

    return {
        "balance": balance,
        "buffer_pct": buffer_pct,
        "buffer": buffer,
        "need": need,
        "obligations_in_window": obligations_sum,
        "opex_in_window": opex_sum,
        "inflow_in_window": inflow_sum,
        "idle_cash": idle,
        "monthly_outflow": monthly_outflow,
        "next_large_payment": next_large,
        "lock_limit_days": lock_limit_days,
        "constraint": constraint_text,
        "instruments": instruments,
        "recommendation": recommendation,
        "forecast": fc[:21],
        "history": [{"date": h["date"], "net": h["revenue"] - h["expense"] - h.get("paid", 0)} for h in profile.get("history", [])],
        "hisob": {
            "formula": "bo'sh pul = balans − (oynadagi majburiyatlar + xarajatlar − tushum × 0,7) − bufer; "
                       "bufer = bufer% × oylik chiqim; daromad = summa × stavka × kun / 365",
            "inputs": {
                "balans": fmt_som(balance),
                "majburiyatlar (oynada)": fmt_som(obligations_sum),
                "operatsion xarajat (oynada)": fmt_som(opex_sum),
                "tushum × 0,7 (oynada)": fmt_som(inflow_sum),
                "bufer": f"{fmt_pct(buffer_pct)} × {fmt_som(monthly_outflow)} = {fmt_som(buffer)}",
                "cheklov": constraint_text,
            },
            "outputs": {
                "bo'sh pul": fmt_som(idle),
                "tavsiya": (f"{best['name']}, {fmt_pct(best['rate'])}, {best['effective_days']} kun → "
                            f"{fmt_som(best['expected_earnings'])}") if best else "mos instrument yo'q",
            },
        },
    }
