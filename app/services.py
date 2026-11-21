"""Glue between deterministic core, storage, policy engine and the bank adapter."""
from datetime import datetime, timedelta, timezone

from app import db, sessions
from app.adapters.bank import BankError, bank, with_retry
from app.config import settings
from app.core import data as seed
from app.core.health import health_score, net_position, synergy_cards
from app.core.money import fmt_date, fmt_pct, fmt_som
from app.core.osish import interest, treasury
from app.core.qalqon import detect
from app.core.shifo import debt_overview
from app.security import policy
from app.security.pii import mask_account, mask_card

ACTION_LABELS = {
    "open_deposit": "Depozit ochish",
    "set_card_merchant_limit": "Karta limitini o'rnatish",
    "block_merchant": "To'lovni bloklash",
    "create_standing_order": "Avtomatik jamg'arma",
    "prepay_loan": "Qarzni muddatidan oldin to'lash",
}


class ActionError(ValueError):
    pass


def profiles() -> dict[str, dict]:
    return seed.build_profiles(settings.today())


def user_session(pid: str):
    return sessions.by_uid(pid) if pid.startswith("u-") else None


def profile(pid: str) -> dict:
    s = user_session(pid)
    if s:
        return seed.build_user_profile(s, settings.today())
    p = profiles().get(pid)
    if not p:
        raise KeyError(pid)
    return p


def _main_card_last4(p: dict) -> str:
    acc = p["accounts"][0] if p["accounts"] else {}
    card = next((a["card_number"] for a in p["accounts"] if a.get("card_number")), "")
    return card[-4:] if card else acc.get("last4", "")


def card_display(p: dict) -> str:
    card = next((a["card_number"] for a in p["accounts"] if a.get("card_number")), "")
    if card:
        return mask_card(card)
    return next((a["masked"] for a in p["accounts"] if a.get("masked")), "")


# ------------------------------------------------------------------ consent (users: session only; demo: SQLite)

def consent_get(pid: str) -> dict:
    s = user_session(pid)
    if s:
        return {"granted": s.consent, "granted_at": s.consent_at}
    return db.get_consent(pid)


def consent_set(pid: str, granted: bool) -> dict:
    s = user_session(pid)
    if s:
        s.consent, s.consent_at = granted, (db.now_iso() if granted else None)
        return consent_get(pid)
    return db.set_consent(pid, granted)


def statement(pid: str) -> tuple[list[dict], dict | None]:
    s = user_session(pid)
    if s:
        if s.statement is None:
            return [], None
        return s.statement, {"source": "csv", "statement": s.statement}
    up = db.get_upload(pid)
    if up and up["source"] == "csv" and up["statement"]:
        return up["statement"], up
    return profile(pid)["statement"], up


def qalqon(pid: str) -> dict:
    p = profile(pid)
    stmt, up = statement(pid)
    result = detect(stmt, p["usage"] if not (up and up["source"] == "csv") else {}, settings.today(), _main_card_last4(p))
    resolved = db.resolved_ids(pid)
    realized = 0
    for f in result["findings"]:
        f["resolved"] = f["id"] in resolved
        if f["resolved"]:
            realized += f["monthly_saving"]
    result.update({
        "loaded": up is not None,
        "source": up["source"] if up else None,
        "realized_monthly": realized,
        "realized_yearly": realized * 12,
    })
    return result


def osish(pid: str, buffer_pct: float | None = None) -> dict:
    p = profile(pid)
    deposits = db.active_deposits(pid)
    if p.get("missing"):
        balance = sum(a["balance"] for a in p["accounts"]) - sum(d["amount"] for d in deposits)
        return {"missing": p["missing"], "profile_kind": p["kind"], "balance": balance, "idle_cash": 0,
                "recommendation": None, "deposits": deposits, "instruments": [], "forecast": [], "history": [],
                "hisob": {"formula": "bo'sh pulni hisoblash uchun balans, oylik daromad, oylik kuni va zarur xarajatlar kerak",
                          "inputs": {"yetishmayapti": ", ".join(p["missing"])}, "outputs": {"bo'sh pul": "hisoblanmadi"}}}
    t = treasury(p, settings.today(), buffer_pct, deposits)
    t["deposits"] = deposits
    t["profile_kind"] = p["kind"]
    return t


def shifo(pid: str) -> dict:
    p = profile(pid)
    return debt_overview(p["loans"], p["monthly_income"])


def public_accounts(p: dict) -> list[dict]:
    out = []
    for a in p["accounts"]:
        item = {"id": a["id"], "name": a["name"], "balance": a["balance"]}
        if a.get("card_number"):
            item["number"] = mask_card(a["card_number"])
        if a.get("account_number"):
            item["number"] = mask_account(a["account_number"])
        if a.get("masked"):
            item["number"] = a["masked"]
        out.append(item)
    return out


def home(pid: str) -> dict:
    p = profile(pid)
    q = qalqon(pid)
    t = osish(pid)
    resolved = db.resolved_ids(pid)
    h = health_score(p, q, t, resolved)
    return {
        "profile": {"id": p["id"], "title": p["title"], "kind": p["kind"]},
        "health": h,
        "net": net_position(p, t["deposits"]),
        "accounts": public_accounts(p),
        "deposits": t["deposits"],
        "feed": db.actions_list(pid, limit=12),
        "synergy": synergy_cards(p, q, t, h, resolved),
        "today": settings.today().isoformat(),
    }


def meros(pid: str) -> dict:
    p = profile(pid)
    return {"accounts": public_accounts(p), "loans": [l["name"] for l in p["loans"]],
            "total_assets": sum(a["balance"] for a in p["accounts"])}


# ------------------------------------------------------------------ action lifecycle

def _find_finding(pid: str, finding_id: str) -> dict:
    f = next((f for f in qalqon(pid)["findings"] if f["id"] == finding_id), None)
    if not f:
        raise ActionError(f"Topilma topilmadi: {finding_id}")
    return f


def build_proposal(pid: str, type_: str, params: dict) -> tuple[dict, int]:
    """Deterministically compute what the action will do. Returns (proposal, amount_for_policy)."""
    p = profile(pid)
    today = settings.today()
    if type_ == "open_deposit":
        t = osish(pid)
        ins = next((i for i in t["instruments"] if i["id"] == params.get("instrument_id")), None)
        if not ins:
            raise ActionError("Instrument topilmadi")
        amount = int(params.get("amount") or t["idle_cash"])
        if amount <= 0 or amount > t["idle_cash"]:
            raise ActionError(f"Summa bo'sh puldan ({fmt_som(t['idle_cash'])}) oshmasligi kerak")
        if not ins["eligible"]:
            raise ActionError(f"Bu instrument mos emas: {ins['ineligible_reason']}")
        days = ins["effective_days"]
        earnings = interest(amount, ins["rate"], days)
        return_date = ins["maturity_date"]
        pay = t["next_large_payment"] if p["kind"] == "business" else None
        before = ""
        if pay:
            gap = (datetime.fromisoformat(pay["date"]) - datetime.fromisoformat(return_date)).days
            before = f"to'lovdan {gap} kun oldin qaytariladi ({pay['name']}, {fmt_date(datetime.fromisoformat(pay['date']).date())})"
        proposal = {
            "title": f"{ins['name']} — {fmt_som(amount)}",
            "instrument_id": ins["id"], "instrument_name": ins["name"], "amount": amount, "rate": ins["rate"],
            "days": days, "expected_earnings": earnings, "return_date": return_date,
            "details": [["Summa", fmt_som(amount)], ["Stavka", f"{fmt_pct(ins['rate'])} yillik"],
                        ["Muddat", f"{days} kun"], ["Kutilayotgan daromad", fmt_som(earnings)],
                        ["Avtomatik qaytish", f"{fmt_date(datetime.fromisoformat(return_date).date())}" + (f" — {before}" if before else "")]],
            "formula": f"{fmt_som(amount)} × {fmt_pct(ins['rate'])} × {days} / 365 = {fmt_som(earnings)}",
        }
        return proposal, amount
    if type_ in ("set_card_merchant_limit", "block_merchant"):
        f = _find_finding(pid, params.get("finding_id", ""))
        if type_ == "set_card_merchant_limit":
            limit = int(params.get("monthly_limit", 0))
            if limit < 0:
                raise ActionError("Limit manfiy bo'lishi mumkin emas")
            saving = max(0, f["monthly_cost"] - limit)
            proposal = {
                "title": f"{f['merchant']}: oylik limit {fmt_som(limit)}",
                "finding_id": f["id"], "merchant": f["merchant"], "monthly_limit": limit, "monthly_saving": saving,
                "details": [["Xizmat", f["merchant"]], ["Karta", f"**** {f['card_last4']}"],
                            ["Yangi oylik limit", fmt_som(limit)], ["Hozirgi to'lov", fmt_som(f["monthly_cost"])],
                            ["Oylik tejash", fmt_som(saving)]],
                "formula": f"tejash = max(0, {fmt_som(f['monthly_cost'])} − {fmt_som(limit)}) = {fmt_som(saving)}",
            }
            return proposal, limit
        proposal = {
            "title": f"{f['merchant']}: kelgusi to'lovlarni bloklash",
            "finding_id": f["id"], "merchant": f["merchant"], "monthly_saving": f["monthly_saving"],
            "details": [["Xizmat", f["merchant"]], ["Karta", f"**** {f['card_last4']}"],
                        ["Oylik tejash", fmt_som(f["monthly_saving"])], ["Yillik tejash", fmt_som(f["monthly_saving"] * 12)]],
            "formula": f"{fmt_som(f['monthly_saving'])} × 12 = {fmt_som(f['monthly_saving'] * 12)}",
        }
        return proposal, f["monthly_saving"]
    if type_ == "create_standing_order":
        amount = int(params.get("amount", 0))
        day = int(params.get("day", 6))
        if amount <= 0:
            raise ActionError("Summa musbat bo'lishi kerak")
        proposal = {
            "title": f"Har oy {day}-sanada {fmt_som(amount)} jamg'armaga",
            "amount": amount, "day": day, "purpose": params.get("purpose", "Jamg'arma"),
            "details": [["Summa", f"{fmt_som(amount)} / oy"], ["Sana", f"har oyning {day}-sanasi"],
                        ["Qayerga", "Jamg'arma hisobi"], ["Yiliga", fmt_som(amount * 12)]],
            "formula": f"{fmt_som(amount)} × 12 = {fmt_som(amount * 12)}",
        }
        return proposal, amount
    if type_ == "prepay_loan":
        loan = next((l for l in p["loans"] if l["id"] == params.get("loan_id")), None)
        if not loan:
            raise ActionError("Kredit topilmadi")
        amount = min(int(params.get("amount", 0)), loan["principal"])
        if amount <= 0:
            raise ActionError("Summa musbat bo'lishi kerak")
        saved = interest(amount, loan["rate"], 365)
        proposal = {
            "title": f"{loan['name']}: {fmt_som(amount)} oldindan to'lash",
            "loan_id": loan["id"], "amount": amount,
            "details": [["Kredit", loan["name"]], ["Stavka", fmt_pct(loan["rate"])], ["Summa", fmt_som(amount)],
                        ["Tejalgan foiz (1 yil)", f"~{fmt_som(saved)}"]],
            "formula": f"{fmt_som(amount)} × {fmt_pct(loan['rate'])} × 365/365 = {fmt_som(saved)}",
        }
        return proposal, amount
    raise ActionError(f"Noma'lum amal turi: {type_}")


async def prepare(pid: str, type_: str, params: dict, created_by: str) -> dict:
    proposal, amount = build_proposal(pid, type_, params)
    proposal["label"] = ACTION_LABELS[type_]
    s = db.get_settings(pid)
    decision = policy.decide(type_, amount, s["autonomy"], s["auto_limit"])
    status = "advice" if decision["status"] == "advice" else "proposed"
    action = db.action_create(pid, type_, params, proposal | {"policy": decision["reason"]}, amount,
                              status, decision["mode"], created_by)
    db.audit(pid, created_by, "action.prepared", {"action_id": action["id"], "type": type_, "amount": amount,
                                                 "title": proposal["title"]})
    db.audit(pid, "policy", "policy.decision", {"action_id": action["id"], "autonomy": s["autonomy"],
                                               "limit": s["auto_limit"], "decision": decision["status"]})
    if decision["status"] == "auto_execute":
        action = await execute(action["id"], actor="policy")
    return action


async def execute(action_id: int, actor: str = "user") -> dict:
    a = db.action_get(action_id)
    if not a:
        raise ActionError("Amal topilmadi")
    if a["status"] != "proposed":
        raise ActionError(f"Bu amalni bajarib bo'lmaydi (holati: {a['status']})")
    pid, p, prop = a["profile_id"], profile(a["profile_id"]), a["proposal"]
    # Re-validate against current state (balances may have changed since the proposal)
    try:
        build_proposal(pid, a["type"], a["params"])
    except ActionError as e:
        db.action_update(action_id, status="failed", result={"error": str(e)})
        db.audit(pid, "system", "action.failed", {"action_id": action_id, "error": str(e)})
        raise
    last4 = _main_card_last4(p)
    try:
        if a["type"] == "open_deposit":
            res = await with_retry(bank.open_deposit, p["accounts"][0]["id"], prop["instrument_id"], prop["amount"], prop["return_date"])
        elif a["type"] == "set_card_merchant_limit":
            res = await with_retry(bank.set_card_merchant_limit, last4, prop["merchant"], prop["monthly_limit"])
        elif a["type"] == "block_merchant":
            res = await with_retry(bank.block_merchant, last4, prop["merchant"])
        elif a["type"] == "create_standing_order":
            res = await with_retry(bank.create_standing_order, "main", "save", prop["amount"], prop["day"])
        elif a["type"] == "prepay_loan":
            res = await with_retry(bank.prepay_loan, prop["loan_id"], prop["amount"])
        else:
            raise ActionError("Noma'lum amal")
    except BankError as e:
        a = db.action_update(action_id, status="failed", result={"error": str(e)})
        db.audit(pid, "bank", "action.failed", {"action_id": action_id, "error": str(e)})
        return a
    now = datetime.now(timezone.utc)
    undo_until = (now + timedelta(hours=24)).isoformat(timespec="seconds") if actor == "policy" else None
    a = db.action_update(action_id, status="executed", executed_at=now.isoformat(timespec="seconds"),
                         undo_until=undo_until, result=res)
    if a["type"] in ("set_card_merchant_limit", "block_merchant"):
        db.resolve(pid, prop["finding_id"], action_id)
    db.audit(pid, actor, "action.executed", {"action_id": action_id, "type": a["type"], "bank_ref": res["ref"],
                                            "amount": a["amount"]})
    return a


def reject(action_id: int) -> dict:
    a = db.action_get(action_id)
    if not a or a["status"] not in ("proposed", "advice"):
        raise ActionError("Bu amalni rad etib bo'lmaydi")
    a = db.action_update(action_id, status="rejected")
    db.audit(a["profile_id"], "user", "action.rejected", {"action_id": action_id})
    return a


async def undo(action_id: int) -> dict:
    a = db.action_get(action_id)
    if not a or a["status"] != "executed":
        raise ActionError("Faqat bajarilgan amalni bekor qilish mumkin")
    if not a["undo_until"] or datetime.fromisoformat(a["undo_until"]) < datetime.now(timezone.utc):
        raise ActionError("Bekor qilish muddati (24 soat) o'tgan yoki amal qo'lda tasdiqlangan")
    ref = (a["result"] or {}).get("ref", "")
    try:
        if a["type"] == "open_deposit":
            await with_retry(bank.close_deposit, ref)
        elif a["type"] == "set_card_merchant_limit":
            await with_retry(bank.remove_card_merchant_limit, ref)
        elif a["type"] == "block_merchant":
            await with_retry(bank.unblock_merchant, ref)
    except BankError as e:
        raise ActionError(str(e))
    db.unresolve_by_action(action_id)
    a = db.action_update(action_id, status="undone")
    db.audit(a["profile_id"], "user", "action.undone", {"action_id": action_id})
    return a
