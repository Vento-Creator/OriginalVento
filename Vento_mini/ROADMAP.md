# Vento Mini — Rivojlanish Rejasi (ROADMAP)

> Bu faylda hali joriy qilinmagan, keyinroq qo'shiladigan xususiyatlar rejalashtiriladi.
> Har bir g'oya qisqacha tavsif bilan yoziladi; amalga oshirish vaqtida bu yerdan olinadi.

---

## 🔐 Xavfsizlik: Ko'p qurilmali seans himoyasi (Anti-Conflict Guard)

**Holati:** ⏳ Rejalashtirilgan (hozircha amalga oshirilmaydi)

### Muammo
Bitta Telegram akkauntni 2 ta turli qurilma/qurilma-sessiya botga ulagan bo'lishi mumkin.
Agar ikkala qurilma bir vaqtda massiv DM (MassDM) yoki boshqa og'ir jarayon (UTAG, scraper)
boshlab yuborsa — akkauntga juda katta yuklama tushadi. Bu esa:
- Telegram tomonidan `FloodWait` / `PeerFlood` / `spam` blokiga olib kelishi mumkin
- Akkaunt ban yoki cheklanish xavfiga tushadi

### G'oya (yakuniy UX oqimi)

1. **Seans identifikatori** — har bir ulangan qurilma/seansda o'z `device_id` / `session_token` bo'ladi
   (masalan `session_manager.py` da seans yaratilganda generatsiya qilinadi va saqlanadi).

2. **Jarayon boshlanganda ziddiyat tekshiruvi** — MassDM (yoki boshqa og'ir jarayon) boshlanganida:
   - Tekshiriladi: hozir bu akkauntda (yoki botda) **boshqa qurilmadan faol jarayon** bormi?
   - Yo'q bo'lsa → normal boshlanadi.

3. **Ziddiyat aniqlansa → ogohlantirish**:
   - Boshlashga urinayotgan qurilmaga xabar:
     - "⚠️ Bu akkauntda boshqa qurilmada allaqachon **X** jarayoni boshlangani aniqlangan!"
     - Tugma: **"⛔ Jarayonni tugatish"**
   - Ikki tomonlama himoya:
     - Ushbu qurilmadagi jarayonni boshlashdan bosh tortish
     - Yoki "Jarayonni tugatish" tugmasi orqali boshqa qurilmadagi jarayonni kesish

4. **Jarayonni tugatish (buyruq uzatish)**:
   - Foydalanuvchi "⛔ Jarayonni tugatish" bossa →
     - **Asosiy (birinchi) qurilma** xabar oladi: "📢 `Boshqa qurilmadan to'xtatildi`"
     - U yerda ishlab turgan jarayon **darhol to'xtatiladi** (Stop flag yuboriladi)
     - Keyin boshlashga urinayotgan qurilma hozir jarayonni o'zi boshlashi mumkin

5. **Maqsad** — akkauntga ortiqcha yuklama tushmasligi va xavfsizlik.

### Texnik eslatma (keyinchalik amalga oshirishda)
- Jarayon holati saqlanadigan joy: `_active_massdm_jobs` (massdm_service.py) va shunga o'xshash
  boshqa aktiv jarayonlar ro'yxati
- Boshqa qurilma bilan aloqa: bot markaziy server (SQLite DB) orqali "aktiv jarayon" belgisi
  qo'yish orqali amalga oshirilishi mumkin — papka: `Vento_mini/` (database.py)
- Har bir jarayon boshlanganda:
  ```python
  # taxminiy sxema (hozircha faqat reja)
  active = await db.check_active_process(account_slot)
  if active:
      await notify_other_device(...)   # tugma bilan
      # foydalanuvchi "tugatish"ni bossa → stop signal boshqa qurilmaga
  ```
- Eslatma: hozircha bu xususiyat **faqat reja** — kod o'zgartirilmagan.

---

<!-- Kelajakdagi boshqa g'oyalar shu yerga qo'shib boriladi -->