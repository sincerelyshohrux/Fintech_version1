"""Debt health (Shifo): deterministic loan math."""
from app.core.money import fmt_pct, fmt_som


def annuity_payment(principal: float, annual_rate: float, months: int) -> int:
    """Monthly annuity payment. 0% loans are split evenly."""
    if months <= 0:
        return int(principal)
    if annual_rate == 0:
        return round(principal / months)
    r = annual_rate / 12
    return round(principal * r / (1 - (1 + r) ** -months))


def loan_metrics(loan: dict) -> dict:
    payment = annuity_payment(loan["principal"], loan["rate"], loan["months_left"])
    total_paid = payment * loan["months_left"]
    return {**loan, "monthly_payment": payment, "total_interest": max(0, total_paid - loan["principal"])}


def debt_overview(loans: list[dict], monthly_income: int) -> dict:
    items = [loan_metrics(l) for l in loans]
    monthly = sum(i["monthly_payment"] for i in items)
    total_debt = sum(i["principal"] for i in items)
    total_interest = sum(i["total_interest"] for i in items)
    dti = monthly / monthly_income if monthly_income else 0.0
    avalanche = sorted(items, key=lambda i: -i["rate"])
    snowball = sorted(items, key=lambda i: i["principal"])
    return {
        "loans": items,
        "monthly_payments": monthly,
        "total_debt": total_debt,
        "total_interest": total_interest,
        "dti": round(dti, 4),
        "avalanche_order": [i["name"] for i in avalanche],
        "snowball_order": [i["name"] for i in snowball],
        "most_expensive": avalanche[0]["name"] if avalanche else None,
        "hisob": {
            "formula": "to'lov = P × r / (1 − (1 + r)^−n), r = yillik stavka / 12; DTI = oylik to'lovlar / oylik daromad",
            "inputs": {i["name"]: f"P={fmt_som(i['principal'])}, stavka={fmt_pct(i['rate'])}, n={i['months_left']} oy"
                       for i in items} | {"oylik daromad": fmt_som(monthly_income)},
            "outputs": {"oylik to'lovlar": fmt_som(monthly), "jami foiz xarajati": fmt_som(total_interest),
                        "DTI": fmt_pct(dti)},
        },
    }
