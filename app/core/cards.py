"""Card and identity validation (pure functions). The full card number is validated in the browser;
the server re-checks everything it receives (last4, type, expiry, holder name)."""
import re
import unicodedata
from datetime import date

CARD_TYPES = {"8600": "uzcard", "9860": "humo"}
CARD_LABELS = {"uzcard": "UzCard", "humo": "Humo"}
APOSTROPHES = "'ʻʼ’‘`´"
NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁёЎўҚқҒғҲҳ'ʻʼ’‘`´\- ]{2,30}$")


def luhn_ok(number: str) -> bool:
    digits = re.sub(r"\D", "", number)
    if len(digits) != 16:
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def card_type(number: str) -> str | None:
    digits = re.sub(r"\D", "", number)
    return CARD_TYPES.get(digits[:4])


def expiry_ok(month: int, year: int, today: date) -> bool:
    """MM/YY must be 01–12 and not in the past (the current month is still valid)."""
    if not (1 <= month <= 12):
        return False
    year = year + 2000 if year < 100 else year
    return (year, month) >= (today.year, today.month) and year <= today.year + 15


def clean_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip())


def name_ok(name: str) -> bool:
    name = clean_name(name)
    return bool(NAME_RE.fullmatch(name)) and any(ch.isalpha() for ch in name)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    for a in APOSTROPHES:
        s = s.replace(a, "")
    return re.sub(r"[\s\-]+", " ", s).strip()


def holder_matches(holder: str, first: str, last: str) -> bool:
    """Case-insensitive, ignores apostrophe variants, extra spaces and word order."""
    return sorted(_norm(holder).split()) == sorted(_norm(f"{first} {last}").split())


def normalize_phone(raw: str) -> str | None:
    """Returns 998XXXXXXXXX or None. Accepts '+998 90 123 45 67', '901234567', etc."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 9:
        digits = "998" + digits
    return digits if re.fullmatch(r"998\d{9}", digits) else None


def mask_phone(phone: str) -> str:
    return f"+998 {phone[3:5]} *** ** {phone[-2:]}" if phone and len(phone) == 12 else "***"


def format_phone(phone: str) -> str:
    return f"+998 {phone[3:5]} {phone[5:8]} {phone[8:10]} {phone[10:12]}"
