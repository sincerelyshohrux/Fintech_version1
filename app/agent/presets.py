"""Preset prompts used by buttons in the UI (same agent, same tools as free chat)."""

PRESETS = {
    "home_summary": "Moliyaviy holatimni qisqacha tahlil qil va bugun qilishim kerak bo'lgan eng muhim 3 ta qadamni ayt.",
    "qalqon_explain": "Qalqon natijalarini tushuntir: qaysi to'lovlar shubhali, nima uchun va har biri bo'yicha nima qilishim kerak?",
    "osish_explain": "Bo'sh turgan pulni qayerga va qancha muddatga joylashtirish kerak? Hisob-kitobni va to'lov jadvalini hisobga olib tushuntir.",
    "shifo_explain": "Qarzlarimni qanday tartibda yopish foydaliroq? Avalanche va snowball usullarini mening raqamlarim bilan solishtir.",
    "meros_explain": "Meros moduli men uchun nima qiladi? Favqulodda holatda ishonchli shaxs nimalarga kira oladi va nimalarga kira olmaydi?",
}


def letter_prompt(finding_id: str) -> str:
    return (f"\"{finding_id}\" topilmasi bo'yicha xizmat ko'rsatuvchiga obunani bekor qilish va pulni qaytarish "
            f"so'rovi xatini yoz. Rasmiy, xushmuomala, qisqa. Faqat get_cancellation_facts natijasidagi faktlardan foydalan.")


def resolve_preset(preset: str | None, message: str | None) -> tuple[str, str | None]:
    """Returns (user_message, intent)."""
    if preset:
        if preset.startswith("letter:"):
            return letter_prompt(preset.split(":", 1)[1]), preset
        if preset in PRESETS:
            return PRESETS[preset], preset
    return (message or "").strip(), None
