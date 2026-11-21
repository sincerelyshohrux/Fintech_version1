"""Money and date formatting helpers (Uzbek conventions)."""
from datetime import date

NBSP = " "  # narrow no-break space as thousands separator

MONTHS_UZ = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust",
             "sentabr", "oktabr", "noyabr", "dekabr"]


def fmt_som(amount: float | int) -> str:
    """89000 -> '89 000 so'm'."""
    value = int(round(amount))
    sign = "-" if value < 0 else ""
    digits = f"{abs(value):,}".replace(",", NBSP)
    return f"{sign}{digits} so'm"


def fmt_pct(rate: float) -> str:
    """0.17 -> '17%' , 0.195 -> '19,5%'."""
    pct = rate * 100
    text = f"{pct:.1f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{text}%"


def fmt_date(d: date) -> str:
    return f"{d.day}-{MONTHS_UZ[d.month - 1]}"
