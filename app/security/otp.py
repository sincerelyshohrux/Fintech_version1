"""One-time passwords: CSPRNG codes, hash-only storage, expiry, resend cooldown, attempt limit and lockout."""
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field

CODE_LEN = 6
TTL = 5 * 60            # code valid for 5 minutes
RESEND_COOLDOWN = 60    # seconds between sends
MAX_SENDS = 4           # first send + 3 resends ...
SEND_WINDOW = 10 * 60   # ... per 10 minutes
MAX_ATTEMPTS = 3        # wrong codes before lockout
LOCKOUT = 5 * 60        # lockout duration

_SECRET = secrets.token_bytes(32)  # per-process pepper; codes are never stored in clear


class OtpError(Exception):
    def __init__(self, message: str, code: str, retry_in: int = 0, attempts_left: int | None = None):
        super().__init__(message)
        self.code, self.retry_in, self.attempts_left = code, retry_in, attempts_left


@dataclass
class _Entry:
    digest: bytes = b""
    expires: float = 0.0
    attempts: int = 0
    locked_until: float = 0.0
    sends: list[float] = field(default_factory=list)


def _digest(key: str, code: str) -> bytes:
    return hmac.new(_SECRET, f"{key}:{code}".encode(), hashlib.sha256).digest()


class OtpService:
    def __init__(self, clock=time.time):
        self.clock = clock
        self._entries: dict[str, _Entry] = {}

    def _check_lock(self, e: _Entry, now: float) -> None:
        if e.locked_until > now:
            wait = int(e.locked_until - now) + 1
            raise OtpError(f"Juda ko'p noto'g'ri urinish. {wait // 60} daqiqa {wait % 60} soniyadan so'ng qayta urinib ko'ring",
                           "locked", retry_in=wait)

    def issue(self, key: str) -> str:
        """Create a fresh code for `key`. Raises OtpError on cooldown, send limit or lockout."""
        now = self.clock()
        e = self._entries.setdefault(key, _Entry())
        self._check_lock(e, now)
        e.sends = [t for t in e.sends if now - t < SEND_WINDOW]
        if e.sends and now - e.sends[-1] < RESEND_COOLDOWN:
            wait = int(RESEND_COOLDOWN - (now - e.sends[-1])) + 1
            raise OtpError(f"Yangi kodni {wait} soniyadan so'ng so'rashingiz mumkin", "cooldown", retry_in=wait)
        if len(e.sends) >= MAX_SENDS:
            wait = int(SEND_WINDOW - (now - e.sends[0])) + 1
            raise OtpError("Kod juda ko'p marta so'raldi. Birozdan so'ng urinib ko'ring", "send_limit", retry_in=wait)
        code = "".join(secrets.choice("0123456789") for _ in range(CODE_LEN))
        e.digest, e.expires, e.attempts = _digest(key, code), now + TTL, 0
        e.sends.append(now)
        return code

    def verify(self, key: str, code: str) -> None:
        """Returns None on success; raises OtpError otherwise. A used code cannot be reused."""
        now = self.clock()
        e = self._entries.get(key)
        if e:
            self._check_lock(e, now)  # lockout wins over "no code"
        if not e or not e.digest:
            raise OtpError("Avval kod so'rang", "no_code")
        if now > e.expires:
            e.digest = b""
            raise OtpError("Kod muddati tugadi. Yangi kod so'rang", "expired")
        if not (isinstance(code, str) and code.isdigit() and len(code) == CODE_LEN) or \
                not hmac.compare_digest(e.digest, _digest(key, code)):
            e.attempts += 1
            if e.attempts >= MAX_ATTEMPTS:
                e.locked_until, e.digest, e.attempts = now + LOCKOUT, b"", 0
                raise OtpError("3 marta noto'g'ri kod kiritildi. 5 daqiqaga bloklandi", "locked", retry_in=LOCKOUT)
            left = MAX_ATTEMPTS - e.attempts
            raise OtpError(f"Kod noto'g'ri. Yana {left} ta urinish qoldi", "wrong", attempts_left=left)
        e.digest, e.attempts = b"", 0  # consume

    def status(self, key: str) -> dict:
        now = self.clock()
        e = self._entries.get(key)
        if not e:
            return {"resend_in": 0, "locked_in": 0}
        resend = int(RESEND_COOLDOWN - (now - e.sends[-1])) + 1 if e.sends and now - e.sends[-1] < RESEND_COOLDOWN else 0
        return {"resend_in": resend, "locked_in": max(0, int(e.locked_until - now))}


otp = OtpService()
