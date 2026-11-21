"""Offline demo mode: used when there is no API key or the AI service is unreachable.

The numbers still come from the same deterministic tools; only the wording is templated.
The UI shows an "Offline demo rejimi" badge so this is never presented as live AI.
"""
import asyncio
import re

from app.agent.tools import TOOL_LABELS, run_tool
from app.core.money import fmt_date, fmt_pct, fmt_som
from datetime import date


def _intent(message: str, intent: str | None) -> str:
    if intent:
        return intent
    m = message.lower()
    if re.search(r"xat|bekor qil", m):
        return "letter:"
    if re.search(r"obuna|qalqon|shubhali|yechil|takror", m):
        return "qalqon_explain"
    if re.search(r"depozit|bo'sh|o'sish|joyla|foiz|g'azna|omonat", m):
        return "osish_explain"
    if re.search(r"qarz|kredit|shifo", m):
        return "shifo_explain"
    if re.search(r"meros|ishonchli|favqulod", m):
        return "meros_explain"
    return "home_summary"


async def _tool(name, args, pid, ctx, events):
    out = await run_tool(name, args, pid, ctx)
    events.append({"type": "tool", "name": name, "label": TOOL_LABELS[name], "input": args, "hisob": out["hisob"]})
    return out["data"]


async def offline_answer(pid: str, message: str, intent: str | None, ctx: dict, conv):
    events: list[dict] = []
    kind = _intent(message, intent)
    text = ""

    if kind.startswith("letter:"):
        fid = kind.split(":", 1)[1]
        if not fid:
            q = await _tool("detect_subscriptions", {}, pid, ctx, events)
            flagged = [f for f in q["findings"] if f["level"] != "past" and not f["resolved"]]
            fid = flagged[0]["id"] if flagged else ""
    if kind.startswith("letter:") and not fid:
        text = "Bekor qilish xati uchun shubhali to'lov topilmadi. Avval ko'chirmani yuklang."
    elif kind.startswith("letter:"):
        f = await _tool("get_cancellation_facts", {"finding_id": fid}, pid, ctx, events)
        charges = ", ".join(f"{c['date']} — {fmt_som(c['amount'])}" for c in f["charges"])
        text = (f"**Mavzu: Obunani bekor qilish va {fmt_som(f['refund_amount_to_request'])} qaytarish so'rovi**\n\n"
                f"Hurmatli \"{f['merchant']}\" mijozlarni qo'llab-quvvatlash xizmati,\n\n"
                f"Men, {f['customer_name']}, {f['card']} kartam orqali amalga oshirilgan quyidagi to'lovlar bo'yicha murojaat qilaman: {charges}.\n\n"
                f"Holat: {f['issue']}.\n\n"
                f"Sizdan so'rayman:\n- obunamni darhol bekor qilishingizni;\n"
                f"- oxirgi yechilgan {fmt_som(f['refund_amount_to_request'])} miqdoridagi to'lovni kartamga qaytarishingizni;\n"
                f"- bekor qilinganini yozma ravishda tasdiqlashingizni.\n\n"
                f"Javobingizni {' yoki '.join(x for x in (f['customer_email'], f['customer_phone']) if x) or 'shu manzil'} orqali kutaman.\n\n"
                f"Hurmat bilan,\n{f['customer_name']}\n{date.fromisoformat(f['today']).strftime('%d.%m.%Y')}")
    elif kind == "qalqon_explain":
        q = await _tool("detect_subscriptions", {}, pid, ctx, events)
        flagged = [f for f in q["findings"] if f["level"] != "past"]
        if not q["findings"]:
            text = "Hozircha tahlil qilinadigan muntazam to'lov yo'q. Qalqon bo'limida ko'chirmani (CSV) yuklang."
        lines = [f"Oxirgi 90 kunda **{len(flagged)} ta shubhali to'lov** topildi. Ularni yopsangiz oyiga "
                 f"**{fmt_som(q['potential_monthly_saving'])}**, yiliga **{fmt_som(q['potential_yearly_saving'])}** tejaysiz.\n"]
        for f in flagged:
            status = " ✅ hal qilingan" if f["resolved"] else ""
            lines.append(f"- **{f['merchant']}** ({f['level']}){status}: {f['reason']}. Tejash: {fmt_som(f['monthly_saving'])}/oy.")
        legit = len(q["findings"]) - len(flagged)
        lines.append(f"\n{legit} ta muntazam to'lov (aloqa, internet, kredit) normal deb belgilandi — ularga tegmaymiz.")
        lines.append("Har bir topilma uchun bekor qilish xatini tayyorlashim yoki karta limitini o'rnatishim mumkin.")
        if q["findings"]:
            text = "\n".join(lines)
    elif kind == "osish_explain":
        t = await _tool("recommend_instrument", {}, pid, ctx, events)
        rec = t.get("recommendation")
        if t.get("missing_inputs"):
            text = ("Bo'sh pulni hisoblash uchun ma'lumot yetishmayapti: **" + ", ".join(t["missing_inputs"]) +
                    "**. O'sish bo'limidagi formani to'ldiring — taxmin qilmayman, faqat aniq raqamlar bilan hisoblayman.")
        else:
            text = (f"Hozirgi balans **{fmt_som(t['balance'])}**. Oldindagi majburiyatlar uchun **{fmt_som(t['need'])}** "
                    f"va xavfsizlik buferi **{fmt_som(t['buffer'])}** ({fmt_pct(t['buffer_pct'])}) ajratildi.\n\n"
                    f"Cheklov: {t['constraint']}.\n\n")
            if rec:
                text += (f"Xavfsiz bo'sh pul: **{fmt_som(t['idle_cash'])}**. Eng yaxshi mos variant — **{rec['instrument_name']}**, "
                         f"{fmt_pct(rec['rate'])}, {rec['days']} kun. Kutilayotgan daromad: **{fmt_som(rec['expected_earnings'])}**. "
                         f"Pul {fmt_date(date.fromisoformat(rec['return_date']))} kuni avtomatik qaytadi.\n\n")
                bad = [i for i in t["instruments"] if not i["eligible"]]
                if bad:
                    text += "Mos kelmaganlar: " + "; ".join(f"{i['name']} — {i['ineligible_reason']}" for i in bad) + "."
            else:
                text += "Hozircha joylashtirish uchun xavfsiz bo'sh pul yo'q — barcha mablag' yaqin to'lovlarga kerak."
    elif kind == "shifo_explain":
        d = await _tool("get_debt_overview", {}, pid, ctx, events)
        text = (f"Oylik qarz to'lovlari: **{fmt_som(d['monthly_payments'])}**, qarz yuki (DTI) **{fmt_pct(d['dti'])}**. "
                f"Qolgan muddatda jami foiz xarajati: **{fmt_som(d['total_interest'])}**.\n\n"
                f"- **Avalanche** (eng qimmat stavkadan): {' → '.join(d['avalanche_order'])}. Foizni eng ko'p tejaydi.\n"
                f"- **Snowball** (eng kichik qoldiqdan): {' → '.join(d['snowball_order'])}. Tezroq motivatsiya beradi.\n\n"
                f"Tavsiya: avval **{d['most_expensive']}** ni yoping — u eng qimmat qarz.")
    elif kind == "meros_explain":
        snap = await _tool("get_financial_snapshot", {}, pid, ctx, events)
        text = (f"Meros moduli favqulodda holat uchun: siz tanlagan **ishonchli shaxs** tasdiqlangan hujjat bilan murojaat qilsa, "
                f"bank unga faqat ko'rish huquqini beradi — {len(snap['accounts'])} ta hisob ro'yxati va qarzlar haqida ma'lumot. "
                f"Pul o'tkazish, karta ma'lumotlari va parollar **hech qachon** berilmaydi. Har bir kirish audit jurnaliga yoziladi.\n\n"
                f"Bu modul keyingi bosqichda to'liq ishga tushiriladi.")
    else:
        snap = await _tool("get_financial_snapshot", {}, pid, ctx, events)
        q = await _tool("detect_subscriptions", {}, pid, ctx, events)
        t = await _tool("recommend_instrument", {}, pid, ctx, events)
        weakest = min(snap["health_parts"].items(), key=lambda kv: kv[1])
        rec = t.get("recommendation")
        steps = []
        if q["potential_monthly_saving"]:
            steps.append(f"**Qalqon**: shubhali to'lovlarni yoping — oyiga {fmt_som(q['potential_monthly_saving'])} tejaladi.")
        if rec:
            steps.append(f"**O'sish**: {fmt_som(rec['amount'])} ni {rec['instrument_name'].lower()}ga joylang — "
                         f"{fmt_som(rec['expected_earnings'])} daromad.")
        steps.append(f"**Eng zaif ko'rsatkich** — \"{weakest[0]}\" ({weakest[1]}/25): shundan boshlang.")
        text = (f"Moliyaviy salomatlik: **{snap['health_score']}/100**. Sof holat: **{fmt_som(snap['net_position']['net'])}**.\n\n"
                + "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1)))

    for ev in events:
        yield ev
        await asyncio.sleep(0.15)
    for chunk in re.findall(r"\S+\s*", text):
        yield {"type": "text", "text": chunk}
        await asyncio.sleep(0.018)
    conv.last_payload = [{"role": "offline", "content": "Offline rejim: AI'ga hech narsa yuborilmadi"}]
    yield {"type": "done", "redacted_payload": conv.last_payload}
