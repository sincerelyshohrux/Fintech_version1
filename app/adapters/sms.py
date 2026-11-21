"""SMS delivery behind a small interface so a real provider (Eskiz.uz) can be swapped in."""
import logging
import time
from abc import ABC, abstractmethod

import httpx

from app.config import settings

log = logging.getLogger("finpilot.sms")


class SmsError(Exception):
    pass


class SmsProvider(ABC):
    name = "abstract"

    @abstractmethod
    async def send_sms(self, phone: str, text: str) -> dict:
        """Deliver `text` to `phone` (digits only, e.g. 998901234567). Returns provider metadata."""


class DemoSmsProvider(SmsProvider):
    """Delivers nothing. The text is returned so the UI can show it in a phone-style banner (DEMO_MODE only)."""

    name = "demo"

    async def send_sms(self, phone: str, text: str) -> dict:
        log.info("demo sms to ***%s", phone[-2:])
        return {"delivered": False, "provider": self.name, "demo_text": text}


class EskizSmsProvider(SmsProvider):
    """Eskiz.uz adapter (token auth + send). Not exercised in the hackathon demo."""

    name = "eskiz"
    BASE = "https://notify.eskiz.uz/api"

    def __init__(self, email: str, password: str, sender: str):
        self.email, self.password, self.sender = email, password, sender
        self._token: str | None = None
        self._token_at = 0.0

    async def _auth(self, client: httpx.AsyncClient) -> str:
        if self._token and time.time() - self._token_at < 20 * 24 * 3600:
            return self._token
        r = await client.post(f"{self.BASE}/auth/login", data={"email": self.email, "password": self.password})
        if r.status_code != 200:
            raise SmsError("SMS provayderiga ulanib bo'lmadi")
        self._token, self._token_at = r.json()["data"]["token"], time.time()
        return self._token

    async def send_sms(self, phone: str, text: str) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            token = await self._auth(client)
            r = await client.post(f"{self.BASE}/message/sms/send",
                                  headers={"Authorization": f"Bearer {token}"},
                                  data={"mobile_phone": phone, "message": text, "from": self.sender})
        if r.status_code != 200:
            raise SmsError("SMS yuborilmadi, birozdan so'ng qayta urinib ko'ring")
        return {"delivered": True, "provider": self.name, "id": r.json().get("id")}


def build_provider() -> SmsProvider:
    if settings.sms_provider == "eskiz" and settings.eskiz_email and settings.eskiz_password:
        return EskizSmsProvider(settings.eskiz_email, settings.eskiz_password, settings.eskiz_sender)
    return DemoSmsProvider()


sms = build_provider()


async def send_sms(phone: str, code: str, purpose: str) -> dict:
    """Pluggable entry point used by the auth flow."""
    what = "karta tasdiqlash kodi" if purpose == "card" else "tasdiqlash kodi"
    text = f"FinPilot: {what} {code}. Kodni hech kimga aytmang."
    return await sms.send_sms(phone, text)
