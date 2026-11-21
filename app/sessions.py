"""In-memory sessions. Personal data of onboarded users lives only here (never in SQLite) and is wiped on logout."""
import secrets
import time
from dataclasses import dataclass, field

from app.config import settings

DEMO_PIDS = ("aziza", "salomat")
STAGES = ("phone", "otp", "profile", "card", "card_otp", "setup", "ready")


@dataclass
class Session:
    sid: str
    uid: str
    created: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    mode: str | None = None            # None until onboarding is finished or demo chosen; "user" | "demo"
    stage: str = "phone"
    phone: str | None = None           # 998XXXXXXXXX, set once the OTP is verified
    pending_phone: str | None = None
    first: str | None = None
    last: str | None = None
    card: dict | None = None           # {"last4", "type", "holder", "exp"} — never the full number
    pending_card: dict | None = None
    consent: bool = False
    consent_at: str | None = None
    balance: int | None = None
    monthly_income: int | None = None
    payday: int | None = None
    essentials: int | None = None
    statement: list[dict] | None = None
    statement_name: str | None = None
    loans: list[dict] = field(default_factory=list)

    @property
    def allowed_pids(self) -> tuple[str, ...]:
        if self.mode == "demo":
            return DEMO_PIDS
        if self.mode == "user":
            return (self.uid,)
        return ()


_sessions: dict[str, Session] = {}


def _expired(s: Session) -> bool:
    return time.time() - s.last_seen > settings.session_ttl_minutes * 60


def get(sid: str | None) -> Session | None:
    s = _sessions.get(sid or "")
    if not s:
        return None
    if _expired(s):
        _sessions.pop(s.sid, None)
        return None
    s.last_seen = time.time()
    return s


def create() -> Session:
    s = Session(sid=secrets.token_urlsafe(32), uid="u-" + secrets.token_hex(5))
    _sessions[s.sid] = s
    return s


def by_uid(uid: str) -> Session | None:
    for s in list(_sessions.values()):
        if s.uid == uid and s.mode == "user" and not _expired(s):
            return s
    return None


def destroy(sid: str) -> Session | None:
    return _sessions.pop(sid, None)


def clear_all() -> None:
    _sessions.clear()
