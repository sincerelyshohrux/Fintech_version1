"""Tools the LLM agent may call. Every number comes from deterministic code; the model only explains.

Least privilege: the agent can read data and PREPARE actions. Execution happens only through the
confirmation endpoint or the autonomy policy engine, never directly from the model.
"""
from app import services
from app.core.money import fmt_som

ACTION_TYPES = ["open_deposit", "set_card_merchant_limit", "block_merchant", "create_standing_order", "prepay_loan"]

TOOLS = [
    {
        "name": "get_financial_snapshot",
        "description": "Get the user's financial health score (with its 4 components), net position, accounts "
                       "(masked), monthly income and active deposits. Call this for general questions about the "
                       "user's financial state.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "detect_subscriptions",
        "description": "Run the Qalqon detector on the last 90 days of bank transactions. Returns recurring charges "
                       "with suspicion level (past/o'rta/yuqori), the rule IDs that fired, reasons and monthly "
                       "savings if acted on. Use for questions about subscriptions, hidden or duplicate charges.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_cancellation_facts",
        "description": "Get the facts needed to write a cancellation and refund request letter for one Qalqon "
                       "finding: merchant, charge dates and amounts, card (masked), customer contact tokens and "
                       "the refund amount to request. Write the letter yourself using ONLY these facts.",
        "input_schema": {"type": "object", "properties": {
            "finding_id": {"type": "string", "description": "Finding id from detect_subscriptions"}},
            "required": ["finding_id"], "additionalProperties": False},
    },
    {
        "name": "forecast_cash",
        "description": "Day-by-day balance forecast including scheduled obligations (rent, salaries, suppliers, loans).",
        "input_schema": {"type": "object", "properties": {
            "days": {"type": "integer", "description": "Number of days to forecast, 1-21"}},
            "required": ["days"], "additionalProperties": False},
    },
    {
        "name": "recommend_instrument",
        "description": "Compute safe idle cash (balance minus obligations and a safety buffer) and pick the best "
                       "deposit/bond whose money returns before the next large payment. Returns all instruments "
                       "with eligibility, expected earnings and the formula.",
        "input_schema": {"type": "object", "properties": {
            "buffer_pct": {"type": "number", "description": "Optional safety buffer share 0-0.5; omit to use the user's setting"}},
            "additionalProperties": False},
    },
    {
        "name": "simulate_card_limit",
        "description": "Simulate a per-merchant monthly card limit for a Qalqon finding and return the monthly saving.",
        "input_schema": {"type": "object", "properties": {
            "finding_id": {"type": "string"},
            "monthly_limit": {"type": "integer", "description": "Limit in so'm, 0 blocks the merchant"}},
            "required": ["finding_id", "monthly_limit"], "additionalProperties": False},
    },
    {
        "name": "get_debt_overview",
        "description": "Loans with monthly annuity payments, total interest cost, debt-to-income ratio, and "
                       "avalanche (highest rate first) vs snowball (smallest balance first) orders.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "prepare_action",
        "description": "Prepare (NOT execute) an action for the user to confirm. The server applies the user's "
                       "autonomy policy. Parameters by type: open_deposit {instrument_id, amount}; "
                       "set_card_merchant_limit {finding_id, monthly_limit}; block_merchant {finding_id}; "
                       "create_standing_order {amount, day}; prepay_loan {loan_id, amount}. Never claim an action "
                       "was executed unless the returned status is 'executed'.",
        "input_schema": {"type": "object", "properties": {
            "type": {"type": "string", "enum": ACTION_TYPES},
            "instrument_id": {"type": "string"},
            "amount": {"type": "integer"},
            "finding_id": {"type": "string"},
            "monthly_limit": {"type": "integer"},
            "loan_id": {"type": "string"},
            "day": {"type": "integer"}},
            "required": ["type"], "additionalProperties": False},
    },
]

for _t in TOOLS:
    _t["eager_input_streaming"] = True  # stream tool inputs; we validate them before running

TOOL_LABELS = {
    "get_financial_snapshot": "Moliyaviy holat",
    "detect_subscriptions": "Qalqon detektori",
    "get_cancellation_facts": "Xat uchun faktlar",
    "forecast_cash": "Pul oqimi prognozi",
    "recommend_instrument": "G'aznachi hisob-kitobi",
    "simulate_card_limit": "Limit simulyatsiyasi",
    "get_debt_overview": "Qarzlar tahlili",
    "prepare_action": "Amal tayyorlash",
}


class ToolInputError(ValueError):
    pass


def _req_str(args: dict, key: str) -> str:
    v = args.get(key)
    if not isinstance(v, str) or not v:
        raise ToolInputError(f"'{key}' must be a non-empty string")
    return v


def _int(args: dict, key: str, lo: int, hi: int, required: bool = True) -> int | None:
    v = args.get(key)
    if v is None and not required:
        return None
    if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
        raise ToolInputError(f"'{key}' must be an integer between {lo} and {hi}")
    return v


async def run_tool(name: str, args: dict, pid: str, ctx: dict) -> dict:
    """Returns {"data": <for the model>, "hisob": <shown in UI>, "action": optional action dict}."""
    if not isinstance(args, dict):
        raise ToolInputError("input must be an object")

    if name == "get_financial_snapshot":
        h = services.home(pid)
        p = services.profile(pid)
        data = {"profile_kind": p["kind"], "health_score": h["health"]["score"], "health_parts": h["health"]["parts"],
                "net_position": h["net"], "accounts": h["accounts"], "monthly_income": p["monthly_income"],
                "active_deposits": h["deposits"], "today": h["today"]}
        return {"data": data, "hisob": h["health"]["hisob"]}

    if name == "detect_subscriptions":
        q = services.qalqon(pid)
        data = {"potential_monthly_saving": q["potential_monthly"], "potential_yearly_saving": q["potential_yearly"],
                "already_saved_monthly": q["realized_monthly"],
                "findings": [{k: f[k] for k in ("id", "merchant", "amount", "frequency", "level", "rules", "reason",
                                                "monthly_saving", "last_charge", "resolved")} for f in q["findings"]],
                "rules_legend": {"R1": "recurring", "R2": "trial converted to paid", "R3": "duplicate",
                                 "R4": "silent price increase", "R5": "unused > 60 days"}}
        return {"data": data, "hisob": q["hisob"]}

    if name == "get_cancellation_facts":
        fid = _req_str(args, "finding_id")
        q = services.qalqon(pid)
        f = next((x for x in q["findings"] if x["id"] == fid), None)
        if not f:
            raise ToolInputError(f"unknown finding_id {fid}; valid: {[x['id'] for x in q['findings'] if x['level'] != 'past']}")
        p = services.profile(pid)
        stmt, _ = services.statement(pid)
        charges = [t for t in stmt if t["amount"] < 0 and t["description"].upper() == f["merchant"].upper()]
        data = {"merchant": f["merchant"], "issue": f["reason"], "rules": f["rules"],
                "charges": [{"date": c["date"], "amount": -c["amount"]} for c in charges[-4:]],
                "refund_amount_to_request": f["amount"] if set(f["rules"]) & {"R2", "R3", "R5"} else f["monthly_saving"],
                "card": services.card_display(p), "customer_name": p["owner_name"], "customer_phone": p["phone"],
                "customer_email": p["email"], "today": ctx["today"]}
        return {"data": data, "hisob": {"formula": "faktlar ko'chirmadan olindi, qaytarish summasi = oxirgi yechilgan to'lov",
                                        "inputs": {"topilma": f["merchant"], "qoidalar": ", ".join(f["rules"])},
                                        "outputs": {"qaytarish so'rovi": fmt_som(data["refund_amount_to_request"]),
                                                    "to'lovlar soni": len(charges)}}}

    if name == "forecast_cash":
        days = _int(args, "days", 1, 21)
        t = services.osish(pid, ctx.get("buffer_pct"))
        if t.get("missing"):
            return {"data": {"missing_inputs": t["missing"],
                             "note": "Not enough data. Ask the user to fill these on the O'sish screen."},
                    "hisob": t["hisob"]}
        rows = [{"date": r["date"], "balance": r["balance"],
                 "obligations": [f"{o['name']} {o['amount']}" for o in r["obligations"]]} for r in t["forecast"][:days]]
        low = min(rows, key=lambda r: r["balance"])
        return {"data": {"start_balance": t["balance"], "days": rows, "lowest": low},
                "hisob": {"formula": "balans(t) = balans(t−1) + tushum(hafta kuni o'rtachasi) − xarajat − majburiyatlar",
                          "inputs": {"boshlang'ich balans": fmt_som(t["balance"]), "kunlar": days},
                          "outputs": {"eng past nuqta": f"{low['date']}: {fmt_som(low['balance'])}"}}}

    if name == "recommend_instrument":
        bp = args.get("buffer_pct")
        if bp is not None and (not isinstance(bp, (int, float)) or not 0 <= bp <= 0.5):
            raise ToolInputError("'buffer_pct' must be between 0 and 0.5")
        t = services.osish(pid, bp if bp is not None else ctx.get("buffer_pct"))
        if t.get("missing"):
            return {"data": {"missing_inputs": t["missing"],
                             "note": "Not enough data. Ask the user to fill these on the O'sish screen."},
                    "hisob": t["hisob"]}
        data = {k: t[k] for k in ("balance", "buffer_pct", "buffer", "need", "idle_cash", "constraint",
                                  "next_large_payment", "recommendation")}
        data["instruments"] = [{k: i[k] for k in ("id", "name", "rate", "term_days", "eligible", "ineligible_reason",
                                                  "expected_earnings", "maturity_date")} for i in t["instruments"]]
        data["active_deposits"] = t["deposits"]
        return {"data": data, "hisob": t["hisob"]}

    if name == "simulate_card_limit":
        fid = _req_str(args, "finding_id")
        limit = _int(args, "monthly_limit", 0, 100_000_000)
        f = next((x for x in services.qalqon(pid)["findings"] if x["id"] == fid), None)
        if not f:
            raise ToolInputError(f"unknown finding_id {fid}")
        saving = max(0, f["monthly_cost"] - limit)
        return {"data": {"merchant": f["merchant"], "current_monthly": f["monthly_cost"], "limit": limit,
                         "monthly_saving": saving, "yearly_saving": saving * 12,
                         "effect": "charges above the limit will be declined by the bank"},
                "hisob": {"formula": "tejash = max(0, joriy oylik − limit)",
                          "inputs": {"joriy": fmt_som(f["monthly_cost"]), "limit": fmt_som(limit)},
                          "outputs": {"oylik": fmt_som(saving), "yillik": fmt_som(saving * 12)}}}

    if name == "get_debt_overview":
        d = services.shifo(pid)
        return {"data": {k: d[k] for k in ("loans", "monthly_payments", "total_debt", "total_interest", "dti",
                                           "avalanche_order", "snowball_order", "most_expensive")},
                "hisob": d["hisob"]}

    if name == "prepare_action":
        type_ = args.get("type")
        if type_ not in ACTION_TYPES:
            raise ToolInputError(f"'type' must be one of {ACTION_TYPES}")
        params = {k: v for k, v in args.items() if k != "type"}
        try:
            action = await services.prepare(pid, type_, params, created_by="agent")
        except services.ActionError as e:
            raise ToolInputError(str(e))
        prop = action["proposal"]
        return {"data": {"action_id": action["id"], "status": action["status"], "title": prop["title"],
                         "policy": prop.get("policy"), "details": prop["details"]},
                "hisob": {"formula": prop["formula"], "inputs": {"amal": prop["label"]},
                          "outputs": {"holat": action["status"]}},
                "action": action}

    raise ToolInputError(f"unknown tool {name}")

