"""Onboarding & auth: phone → SMS OTP → profile → card (last4 only) → card OTP → consent & balance."""
import logging

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app import db, sessions
from app.adapters.sms import SmsError, send_sms
from app.config import settings
from app.core import cards
from app.security import ratelimit
from app.security.otp import OtpError, otp

log = logging.getLogger("finpilot.auth")
router = APIRouter(prefix="/api/auth")
COOKIE = "fp_sid"


# ------------------------------------------------------------------ session helpers

def current(request: Request) -> sessions.Session | None:
    return sessions.get(request.cookies.get(COOKIE))


def _set_cookie(response: Response, s: sessions.Session) -> None:
    response.set_cookie(COOKIE, s.sid, httponly=True, samesite="strict", max_age=settings.session_ttl_minutes * 60)


def _limit(request: Request) -> None:
    ip = request.client.host if request.client else "anon"
    if not ratelimit.allow(f"auth:{ip}", limit=40, window=60):
        raise HTTPException(429, "Juda ko'p so'rov. Bir daqiqadan so'ng urinib ko'ring.")


def _need(s: sessions.Session | None, *stages: str) -> sessions.Session:
    if not s:
        raise HTTPException(401, "Sessiya topilmadi. Qaytadan boshlang")
    if s.stage not in stages:
        raise HTTPException(409, "Bu qadam hozir mavjud emas. Sahifani yangilang")
    return s


def _otp_http(e: OtpError) -> HTTPException:
    return HTTPException(429 if e.code in ("locked", "cooldown", "send_limit") else 400,
                         {"message": str(e), "code": e.code, "retry_in": e.retry_in, "attempts_left": e.attempts_left})


def state(s: sessions.Session | None) -> dict:
    if not s:
        return {"stage": "phone", "mode": None, "demo_mode": settings.demo_mode}
    out = {"stage": s.stage, "mode": s.mode, "demo_mode": settings.demo_mode, "pid": s.uid if s.mode == "user" else None}
    if s.first:
        out["user"] = {"first": s.first, "last": s.last}
    if s.card:
        label = cards.CARD_LABELS[s.card["type"]]
        out["card"] = {"type": s.card["type"], "label": f"{label} •••• {s.card['last4']}"}
    if s.pending_phone or s.phone:
        out["phone_masked"] = cards.mask_phone(s.phone or s.pending_phone)
    out["finance"] = {"balance": s.balance, "monthly_income": s.monthly_income, "payday": s.payday,
                      "essentials": s.essentials, "statement_rows": len(s.statement) if s.statement else 0}
    return out


async def _send(key: str, phone: str, purpose: str) -> dict:
    try:
        code = otp.issue(key)
    except OtpError as e:
        raise _otp_http(e)
    try:
        res = await send_sms(phone, code, purpose)
    except SmsError as e:
        raise HTTPException(502, str(e))
    out = {"sent": True, "resend_in": 60, "expires_in": 300}
    if settings.demo_mode and res.get("demo_text"):
        out["demo_sms"] = res["demo_text"]  # demo only: shown in the phone-style banner
    return out


# ------------------------------------------------------------------ endpoints

@router.get("/me")
def me(request: Request):
    return state(current(request))


class PhoneIn(BaseModel):
    phone: str = Field(max_length=30)


@router.post("/phone")
async def phone(body: PhoneIn, request: Request, response: Response):
    _limit(request)
    p = cards.normalize_phone(body.phone)
    if not p:
        raise HTTPException(400, "Telefon raqami +998 XX XXX XX XX formatida bo'lishi kerak")
    s = current(request)
    if s and s.mode:  # finished session: start over
        sessions.destroy(s.sid)
        s = None
    if not s:
        s = sessions.create()
        _set_cookie(response, s)
    _need(s, "phone", "otp")
    out = await _send(f"phone:{p}", p, "login")
    s.pending_phone, s.stage = p, "otp"
    db.audit(s.uid, "user", "auth.otp_sent", {"phone": cards.mask_phone(p)})
    return out | {"state": state(s)}


@router.post("/phone/resend")
async def phone_resend(request: Request):
    _limit(request)
    s = _need(current(request), "otp")
    out = await _send(f"phone:{s.pending_phone}", s.pending_phone, "login")
    db.audit(s.uid, "user", "auth.otp_resent", {"phone": cards.mask_phone(s.pending_phone)})
    return out


@router.post("/phone/back")
def phone_back(request: Request):
    s = _need(current(request), "otp")
    s.stage = "phone"
    return state(s)


class CodeIn(BaseModel):
    code: str = Field(max_length=10)


@router.post("/otp")
def verify_otp(body: CodeIn, request: Request):
    _limit(request)
    s = _need(current(request), "otp")
    try:
        otp.verify(f"phone:{s.pending_phone}", body.code.strip())
    except OtpError as e:
        db.audit(s.uid, "user", "auth.otp_failed", {"phone": cards.mask_phone(s.pending_phone), "reason": e.code})
        raise _otp_http(e)
    s.phone, s.stage = s.pending_phone, "profile"
    db.audit(s.uid, "user", "auth.otp_verified", {"phone": cards.mask_phone(s.phone)})
    return state(s)


class ProfileIn(BaseModel):
    first: str = Field(max_length=40)
    last: str = Field(max_length=40)


@router.post("/profile")
def set_profile(body: ProfileIn, request: Request):
    s = _need(current(request), "profile", "card")
    first, last = cards.clean_name(body.first), cards.clean_name(body.last)
    if not cards.name_ok(first):
        raise HTTPException(400, "Ism 2–30 ta harfdan iborat bo'lishi kerak")
    if not cards.name_ok(last):
        raise HTTPException(400, "Familiya 2–30 ta harfdan iborat bo'lishi kerak")
    s.first, s.last, s.stage = first, last, "card"
    db.audit(s.uid, "user", "profile.created", {"initials": f"{first[0]}. {last[0]}."})
    return state(s)


class CardIn(BaseModel):
    last4: str = Field(pattern=r"^\d{4}$")
    type: str = Field(pattern="^(uzcard|humo)$")
    exp_month: int
    exp_year: int
    holder: str = Field(max_length=80)


@router.post("/card")
async def add_card(body: CardIn, request: Request):
    """Receives only last4 + type + expiry + holder; the full number never leaves the browser."""
    _limit(request)
    s = _need(current(request), "card", "card_otp")
    if not cards.expiry_ok(body.exp_month, body.exp_year, settings.today()):
        raise HTTPException(400, "Karta amal qilish muddati noto'g'ri yoki o'tib ketgan")
    if not cards.holder_matches(body.holder, s.first, s.last):
        raise HTTPException(400, "Karta egasining ismi ro'yxatdan o'tgan ismingizga mos kelmadi")
    s.pending_card = {"last4": body.last4, "type": body.type, "holder": cards.clean_name(body.holder).upper(),
                      "exp": f"{body.exp_month:02d}/{body.exp_year % 100:02d}"}
    out = await _send(f"card:{s.uid}", s.phone, "card")
    s.stage = "card_otp"
    db.audit(s.uid, "user", "card.otp_sent", {"card": f"{cards.CARD_LABELS[body.type]} •••• {body.last4}"})
    return out | {"state": state(s)}


@router.post("/card/resend")
async def card_resend(request: Request):
    _limit(request)
    s = _need(current(request), "card_otp")
    return await _send(f"card:{s.uid}", s.phone, "card")


@router.post("/card/back")
def card_back(request: Request):
    s = _need(current(request), "card_otp")
    s.pending_card, s.stage = None, "card"
    return state(s)


@router.post("/card/otp")
def card_otp(body: CodeIn, request: Request):
    _limit(request)
    s = _need(current(request), "card_otp")
    try:
        otp.verify(f"card:{s.uid}", body.code.strip())
    except OtpError as e:
        db.audit(s.uid, "user", "card.otp_failed", {"reason": e.code})
        raise _otp_http(e)
    s.card, s.pending_card, s.stage = s.pending_card, None, "setup"
    db.audit(s.uid, "user", "card.added", {"card": f"{cards.CARD_LABELS[s.card['type']]} •••• {s.card['last4']}"})
    return state(s)


class FinanceIn(BaseModel):
    balance: int | None = Field(default=None, ge=0, le=100_000_000_000)
    monthly_income: int | None = Field(default=None, ge=0, le=10_000_000_000)
    payday: int | None = Field(default=None, ge=1, le=28)
    essentials: int | None = Field(default=None, ge=0, le=10_000_000_000)


class SetupIn(FinanceIn):
    consent: bool


@router.post("/setup")
def setup(body: SetupIn, request: Request):
    s = _need(current(request), "setup")
    if not body.consent:
        raise HTTPException(400, "Davom etish uchun rozilik kerak")
    if body.balance is None and s.statement is None:
        raise HTTPException(400, "Kartadagi qoldiqni kiriting yoki ko'chirma yuklang")
    _apply_finance(s, body)
    s.consent, s.consent_at, s.mode, s.stage = True, db.now_iso(), "user", "ready"
    db.audit(s.uid, "user", "consent.grant", {"scopes": ["balans", "tranzaksiyalar", "kreditlar", "AI tahlil"]})
    db.audit(s.uid, "user", "setup.completed", {"balance_given": s.balance is not None,
                                                "statement_rows": len(s.statement or [])})
    return state(s)


def _apply_finance(s: sessions.Session, body: FinanceIn) -> None:
    for k in ("balance", "monthly_income", "payday", "essentials"):
        v = getattr(body, k)
        if v is not None:
            setattr(s, k, v)


@router.post("/finance")
def update_finance(body: FinanceIn, request: Request):
    s = _need(current(request), "ready")
    if s.mode != "user":
        raise HTTPException(400, "Demo profil ma'lumotlarini o'zgartirib bo'lmaydi")
    _apply_finance(s, body)
    db.audit(s.uid, "user", "finance.updated", {"fields": [k for k, v in body.model_dump().items() if v is not None]})
    return state(s)


@router.post("/demo")
def demo(request: Request, response: Response):
    s = current(request)
    if s and s.mode == "user":
        wipe(s)
        s = None
    if not s:
        s = sessions.create()
        _set_cookie(response, s)
    s.mode, s.stage = "demo", "ready"
    return state(s)


def wipe(s: sessions.Session) -> None:
    from app.agent.agent import last_payload_by_profile
    db.delete_profile_data(s.uid)
    last_payload_by_profile.pop(s.uid, None)
    db.audit(s.uid, "user", "session.wiped", {"note": "foydalanuvchi ma'lumotlari o'chirildi"})
    sessions.destroy(s.sid)


@router.post("/logout")
def logout(request: Request, response: Response):
    s = current(request)
    if s:
        wipe(s)
    response.delete_cookie(COOKIE)
    return state(None)
