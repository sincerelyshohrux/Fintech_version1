"""Application settings loaded from .env."""
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    def __init__(self) -> None:
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        self.claude_model = os.getenv("CLAUDE_MODEL", "claude-opus-5-5").strip()
        self.claude_effort = os.getenv("CLAUDE_EFFORT", "low").strip()
        self.database_path = BASE_DIR / os.getenv("DATABASE_PATH", "data/finpilot.db")
        self.mock_bank_failure_rate = float(os.getenv("MOCK_BANK_FAILURE_RATE", "0.1"))
        self.demo_today = os.getenv("DEMO_TODAY", "").strip()
        # DEMO_MODE=true: OTP codes are shown on screen instead of being delivered by SMS
        self.demo_mode = os.getenv("DEMO_MODE", "true").strip().lower() in ("1", "true", "yes")
        self.sms_provider = os.getenv("SMS_PROVIDER", "demo").strip().lower()
        self.eskiz_email = os.getenv("ESKIZ_EMAIL", "").strip()
        self.eskiz_password = os.getenv("ESKIZ_PASSWORD", "").strip()
        self.eskiz_sender = os.getenv("ESKIZ_SENDER", "4546").strip()
        self.session_ttl_minutes = int(os.getenv("SESSION_TTL_MINUTES", "120"))

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    def today(self) -> date:
        return date.fromisoformat(self.demo_today) if self.demo_today else date.today()


settings = Settings()


