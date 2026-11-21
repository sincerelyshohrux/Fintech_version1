# FinPilot — 7 daqiqalik taqdimot ssenariysi

Oldindan: `uvicorn app.main:app --port 8000`, brauzerda http://localhost:8000, **▶ Demo rejimi** tugmasi
(holat tozalanadi, rozilik beriladi). Internet/AI kaliti bo'lmasa ham ishlaydi (Offline demo rejimi).

## Demo rejimi — 20 qadam, hamma funksiya

Modalda ikki variant:
- **⏵ Avtomatik** — hammasini o'zi bosib o'tadi (~5 daqiqa). Video yozish uchun eng qulay.
- **Qo'lda boshlash** — har qadam bajariladi, keyin **Keyingi →** bosasiz (taqdimotda gapirib turish uchun).

Pastdagi panel: **←** orqaga · **⏵ Avto** yoqish/o'chirish · **Keyingi →** · **✕** to'xtatish.

| # | Qadam | Ekranda nima bo'ladi |
|---|---|---|
| 1 | Onboarding | Telefon → SMS kod → ism → Humo karta (CVV/PIN yo'q) → karta SMS → rozilik + balans |
| 2 | Xavfsizlik | "Siz haqingizda nima saqlanyapti?" — faqat oxirgi 4 raqam, sessiya davomida |
| 3 | Qalqon | Aziza ko'chirmasi → 4 muammo, oyiga 478 000 so'm |
| 4 | AI tushuntirish | Oqimli javob + "Hisoblandi" formulalar |
| 5 | Xat | Yandex Plus uchun qaytarish xati, nusxa |
| 6 | Limit | Megogo limiti 39 000 → Tasdiqlash → Bajarildi |
| 7 | Bloklash | Sport zal bloklanadi |
| 8 | Avtonomiya | "Avto" rejim: Telegram limiti o'zi bajariladi → bosh sahifada **Bekor qilish** (24 soat) |
| 9 | Chat | "Qaysi qarzimni birinchi yopay?" |
| 10 | Shifo | Qarzlar bo'yicha AI tahlil |
| 11 | Bosh sahifa | AI xulosa + sinergiya |
| 12 | O'sish | Salomat dorixona: tarix + prognoz grafigi |
| 13 | Bufer | 30% → 15% — bo'sh pul qayta hisoblanadi |
| 14 | O'sish AI | Nega 7 kunlik depozit mos, boshqalari yo'q |
| 15 | Depozit | 64,3 mln → Tasdiqlash → Bajarildi |
| 16 | Meros | Ishonchli shaxs qo'shiladi |
| 17 | Audit | Tekshirish ✅ → Buzib ko'rish → ❌ → Tiklash → ✅ |
| 18 | AI payload | AI'ga nima yuborildi — ism/karta tokenlangan |
| 19 | Qanday ishlaydi | Arxitektura va biznes-model |
| 20 | Chiqish | Shaxsiy ma'lumotlar o'chiriladi |

## Jonli taqdimot (7 daqiqa)

| Vaqt | Ekran | Nima deymiz |
|---|---|---|
| 0:00–0:45 | — (slayd) | **Muammo.** Odamlar har oy unutilgan obunalar, sinovdan pullikka o'tgan xizmatlar, ikki marta to'lovlarga pul yo'qotadi. Kichik biznes esa millionlarni joriy hisobda foizsiz ushlab turadi. Banklarda bunga yechim yo'q. |
| 0:45–1:15 | Demo 1: Onboarding | Yangi mijoz: telefon → SMS kod (ekranda "SMS") → ism → Humo karta. **CVV va PIN so'ralmaydi**, karta raqami serverga yuborilmaydi — faqat oxirgi 4 raqam. Karta ikkinchi SMS kod bilan tasdiqlanadi → rozilik → ko'chirma. Modullar ochiladi. |
| 1:15–2:15 | Demo 2–3: Qalqon | Ko'chirma yuklanadi → 4 ta muammo, **oyiga 478 000 so'm, yiliga 5,7 mln**. "AI tushuntirsin" → oqimli javob, ostida **Hisoblandi**: raqamlar koddan, AI faqat tushuntiradi. |
| 2:15–3:00 | Demo 4: Xat | AI Yandex Plus uchun bekor qilish va pulni qaytarish xatini yozadi — faqat ko'chirmadagi faktlar. Nusxa / email. |
| 3:00–3:45 | Demo 5: Bloklash | Sport zal (97 kun ishlatilmagan) → Tayyorlash → Tasdiqlash → bank → **Bajarildi**. Salomatlik ko'rsatkichi oshadi. |
| 3:45–5:00 | Demo 6–8: O'sish (dorixona) | Grafik: tarix + prognoz + to'lov sanalari. Bo'sh pul **64,3 mln**. 7 kunlik depozit ish haqidan oldin qaytadi; 30 kunlik va obligatsiya **mos emas** — AI sababini aytadi. Depozit ochiladi: **+209 636 so'm** bir haftada. Autonomiya darajasini ko'rsatamiz (limit ichida avtomatik, 24 soat bekor qilish). |
| 5:00–5:30 | Demo 9: Bosh sahifa | Sinergiya: Qalqon tejagan pul → O'sish; bo'sh pul → eng qimmat qarzni yopish. |
| 5:30–6:15 | Demo 10–11: Audit + Xavfsizlik | "Buzib ko'rish" → zanjir buzilganini darhol aniqlaydi. "AI'ga nima yuborildi?" — ism, karta tokenlar bilan. "Chiqish" — hamma shaxsiy ma'lumot o'chadi. |
| 6:15–7:00 | Qanday ishlaydi | Arxitektura, **biznes-model**: bank litsenziyasi + depozit ulushi, mijozga bepul. Keyingi qadam: hamkor bank pilot. |

**Hakamlar savollariga tayyor javoblar**
- *AI xato raqam aytsa?* — Aytolmaydi: raqamlar faqat tool natijasidan, har birining formulasi ekranda.
- *Bank ma'lumoti AI'ga ketadimi?* — Shaxsiy ma'lumotlar tokenlashtiriladi; payload ekranda ko'rinadi.
- *Real bankka qanday ulanadi?* — `BankAPI` interfeysi; MockBank o'rniga hamkor bank adapteri.
- *AI o'zi pul o'tkazadimi?* — Yo'q. Faqat tayyorlaydi; bajarish — tasdiq yoki mijoz bergan limit + allowlist.
- *Karta ma'lumotlari qayerda?* — To'liq raqam faqat brauzerda tekshiriladi va o'chiriladi; serverda oxirgi 4 raqam, faqat sessiya davomida. CVV/PIN hech qachon so'ralmaydi.
- *SMS haqiqiy yuboriladimi?* — Demo'da kod ekranda; `SMS_PROVIDER=eskiz` bilan Eskiz.uz orqali yuboriladi (adapter tayyor).
- *Balans bankdan qanday keladi?* — Hozir qo'lda yoki CSV; productionda Open Banking orqali avtomatik.
