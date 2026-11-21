"""Autonomy policy engine: decides whether an action needs confirmation or may auto-execute."""
AUTO_ALLOWLIST = {"set_card_merchant_limit", "open_deposit"}
LEVELS = {"advice": "Faqat maslahat", "one_click": "Bir bosishda", "auto": "Limit ichida avtomatik"}


def decide(action_type: str, amount: int, autonomy: str, auto_limit: int) -> dict:
    if autonomy == "advice":
        return {"status": "advice", "mode": "manual",
                "reason": "\"Faqat maslahat\" rejimi: FinPilot faqat tavsiya beradi, bajarmaydi"}
    if autonomy == "auto" and action_type in AUTO_ALLOWLIST and amount <= auto_limit:
        return {"status": "auto_execute", "mode": "auto",
                "reason": f"Limit ichida ({amount:,} ≤ {auto_limit:,}) va ruxsat etilgan amal — avtomatik bajarildi, 24 soat ichida bekor qilish mumkin".replace(",", " ")}
    if autonomy == "auto":
        why = "ruxsat etilmagan amal turi" if action_type not in AUTO_ALLOWLIST else "summa limitdan katta"
        return {"status": "proposed", "mode": "manual", "reason": f"Tasdiq kerak: {why}"}
    return {"status": "proposed", "mode": "manual", "reason": "\"Bir bosishda\" rejimi: tasdiqlashingiz kerak"}
