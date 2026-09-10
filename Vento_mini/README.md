# ⚡ Vento Mini — Shaxsiy va Do'stlar uchun Ixcham Userbot Tizimi

**Vento Mini** — Ortiqcha admin panellari, to'lovlar, chatlar va majburiy obunasiz tayyorlangan g'oyat ixcham va tezkor Telegram Userbot va Bot freymvorki.

---

## ✨ Imkoniyatlar

1. **Multi-Account Tizimi**:
   - Botga bir nechta Telegram akkauntlarini ulash (`Slot 0, 1, 2...`).
   - Akkauntlarni osongina almashtirish, nomlash va o'chirish.
   - Duplikat akkauntlar va chalkashliklarga qarshi himoya.

2. **🔥 Multi-Account MassDM Taqsimot Tizimi (Premium 50 limit)**:
   - Telegram Premium obunachilarining har 12 soatdagi 50 ta odamga xabar yuborish cheklovini hisobga olgan holda:
   - Agar botga 3 ta akkaunt ulangan bo'lsa va siz 150 kishilik baza yuborsangiz, bot **xabarlarni 50 tadan 3 ta akkauntga avtomatik bo'lib yuboradi**!
   - Har bir akkaunt statistikasi live ko'rinib turadi.

3. **📣 UTAG (Guruhlarda tag qilish)**:
   - Guruh a'zolarini ommaviy tag qilish (`/utag Matn`).
   - Tag tezligini va yozish simulyatsiyasini (`typing`) sozlash.
   - Tag xabarlarini avtomatik o'chirish taymeri.
   - Istalgan vaqtda `/stop` bilan to'xtatish.

4. **🔍 Scraper (A'zolarni yig'ish)** — original Vento bilan 1:1:
   - Guruh havolasini yuboring → bot guruhni topadi va **4 ta rejim** taklif qiladi:
     `⚡ Odatiy usulda (tez)`, `💬 Habarlar orqali (sekin)`, `👑 Faqat adminlar`, `👩 Faqat qizlar`.
   - Jonli progress-bar (`[████░░░░░░] 42%`) va **🛑 To'xtatish** tugmasi.
   - Har bir baza **10 xonali unikal Baza ID** bilan saqlanadi (`🗂 Baza ID: 1234567890`).
   - `/add_to_baza [Baza_ID] [username]` bilan qo'shimcha user qo'shish.

5. **📁 Bazalar Boshqaruvi** — original Vento UI'si bilan 1:1:
   - `🗂 Bazalar ro'yxati (N ta) — 1/3` sahifalangan ko'rinish.
   - Baza ichida: `📋 Ro'yxatni ko'rish` (50 ta/sahifa), `➕ User qo'shish`,
     `📨 Xabar yuborish` (to'g'ridan-to'g'ri MassDMga), `🗑 Bazani o'chirish` (tasdiqlash bilan).
   - `🔍 ID orqali qidirish`, `🧹 Bazani tozalash`, `➕ Yangi user(lar) qo'shish`.

6. **📨 MassDM** — original Vento wizard oqimi bilan 1:1:
   - `📁 Bazani tanlang` → `✍️ Xabarni kiriting` → `🚀 Tasdiqlash` → `📊 Yuborilmoqda...` progress.
   - Har bir xabar orasidagi pauza: **10 sekund** (flood himoyasi).
   - Yakunda `✅ Tugatildi` / `⏸️ To'xtatildi` hisoboti va `❌ Xatolik sababini ko'rish`
     (sabablar turlari bilan: 🚫 Blok, 🔐 Maxfiylik, 💎 Premium talab...).
   - **🗑 Habarlarni o'chirish** — MassDM tugagach 2 bosqichli sozlama:
     - `1/2` Ikkala tomon uchun 👥 yoki faqat o'zingiz uchun 🙋 (1 tomonlama);
     - `2/2` Faqat reklama habari 🧹 yoki butun lichka tarixi 💣.
   - **Multi-Account taqsimoti saqlangan**: har bir ulangan Premium akkaunt **50 ta** userga
     xabar yuboradi (3 akkaunt = 150 user), akkaunt SpamBot tekshiruvi bilan avto-tiklanadi.

6. **🤖 SpamBot Avto-Tekshiruv va Apellyatsiya**:
   - Ulangan akkauntlarning `@SpamBot` cheklovini bir tugma bilan avtomatik tekshirish.
   - Cheklov bo'lsa, avtomatik apellyatsiya matnlarini SpamBot ga yuborish.

---

## 🚀 Ishga TushirishYo'riqnomasi

1. `Vento_mini` papkasiga o'ting:
   ```bash
   cd Vento_mini
   ```

2. Kerakli kutubxonalarni o'rnating:
   ```bash
   pip install -r requirements.txt
   ```

3. `.env` faylini yarating va ma'lumotlarni kiriting:
   ```env
   API_ID=1234567
   API_HASH=your_api_hash
   BOT_TOKEN=your_bot_token
   ADMIN_IDS=123456789
   ```

4. Botni ishga tushiring:
   ```bash
   python main.py
   ```
