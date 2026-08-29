# 🤖 Vento Bot - Foydalanish Qo'llanmasi

## 📋 MUQADDIMA

Vento Bot - bu Telegram guruhlaridan a'zolarni yig'ish, ularga xabar yuborish va boshqa samarali vazifalarni bajarish uchun yaratilgan bot.

### 🎯 Bot nima qila oladi?
- Guruhlardan a'zolarni yig'ish (Scraper)
- Ko'p foydalanuvchilarga xabar yuborish (Mass DM)
- Guruhda a'zolarni mention qilish (Utag)
- Foydalanuvchilar bilan chat qilish
- Guruhlarni qidirish
- Va boshqa ko'plab funksiyalar

---

## 🚀 BOSHLASH

### 1. Botni ishga tushirish

1. Telegramda @empire_family_bot ni toping
2. /start buyrug'ini yuboring
3. Telefon raqamingizni yuboring (xalqaro formatda: +998901234567)
4. Admin tasdiqlashini kuting

### 2. Talablar

Botdan to'liq foydalanish uchun:
- ✅ Telegram akkaunt (sessiya)
- ✅ Obuna (pullik yoki bepul)
- ✅ Admin tasdiqi (agar bepul bo'lsa)

---

## 📱 ASOSIY MENYU

Botning asosiy menyusida quyidagi tugmalar mavjud:

```
🔍 Scraper    - Guruhlardan odam yig'ish
🗂 Bazalar    - Yig'ilgan ma'lumotlarni ko'rish
📨 Mass DM    - Xabar yuborish
🏷 Utag       - Mention qilish
💬 Chatlar    - Foydalanuvchilar bilan chat
🔍 Guruh qidirish - Guruhlarni qidirish
👤 Akkaunt    - Akkaunt sozlamalari
🌐 Til        - Tilni o'zgartirish
```

---

## 🔍 SCRAPER - Guruhlardan Odam Yig'ish

### Nima uchun kerak?
Scraper orqali istalgan guruhdagi barcha a'zolarni yig'ib, bazaga saqlashingiz mumkin.

### Qanday ishlaydi?

1. **"🔍 Scraper"** tugmasini bosing
2. **"▶️ Boshlash"** tugmasini bosing
3. **Guruh linkini yuboring:**
   - Masalan: `https://t.me/mafia_group`
   - Yoki: `@group_username`
   - Yoki: `-1001234567890` (guruh ID)

4. **Yig'ish turini tanlang:**
   - **Tez yig'ish** - Barcha a'zolarni tezda yig'ish
   - **Xabar yuborish** - Faqat oxirgi xabar yuborganlarni yig'ish

5. **Kuting** - Bot a'zolarni yig'ib boradi

### Natija:
- Barcha a'zolar bazaga saqlanadi
- Keyin ularni Mass DM orqali xabar yuborishingiz mumkin

### ⚠️ Muhim:
- Guruhda admin bo'lishingiz shart emas
- Lekin guruh ochiq (public) bo'lishi yoki siz a'zo bo'lishingiz kerak
- Juda katta guruhlar (10,000+) uchun vaqt ketishi mumkin

---

## 🏷 UTAG - Guruhda Mention Qilish

### Nima uchun kerak?
Guruhda bir vaqtda ko'p foydalanuvchilarni mention qilish (chaqirish) uchun.

### Qanday ishlaydi?

1. **"🏷 Utag"** tugmasini bosing
2. **"▶️ Boshlash"** tugmasini bosing
3. **Guruhni tanlang:**
   - Bazadan guruhni tanlang
   - Yoki guruh ID sini kiriting

4. **Matnni yozing:**
   ```
   Masalan: "Salom! Bugun yangi konkurs!"
   ```
   Bot bu matnni har bir foydalanuvchi oldidan qo'shib yuboradi:
   ```
   Salom! Bugun yangi konkurs! @user1 @user2 @user3...
   ```

5. **"Yuborish"** tugmasini bosing

### Sozlamalar:
- **Tezlik:** Necha sekundda bir mention qilish (default: 2 sekund)
- **To'xtatish buyrug'i:** Qaysi so'z bilan to'xtatish (default: "stop")

### ⚠️ Muhim:
- Guruhda admin bo'lishingiz kerak
- FloodWait xatosini oldini olish uchun kechikish qo'shing
- Juda ko'p mention qilish Telegram tomonidan bloklanishiga olib kelishi mumkin

---

## 📨 MASS DM - Ko'p Xabar Yuborish

### Nima uchun kerak?
Bazadagi barcha yoki tanlangan foydalanuvchilarga xabar yuborish.

### Qanday ishlaydi?

1. **"📨 Mass DM"** tugmasini bosing
2. **"▶️ Boshlash"** tugmasini bosing
3. **Guruhni tanlang** (kimlarni xabar yuborishni tanlang)
4. **Xabar turini tanlang:**
   - **Matn** - Oddiy xabar
   - **Rasm** - Rasm + matn
   - **Video** - Video + matn

5. **Xabarni yozing:**
   ```
   Salom! Bizda yangi aksiya!
   ```

6. **"Yuborish"** tugmasini bosing

### Xususiyatlar:
- ✅ Har bir foydalanuvchiga alohida xabar yuboriladi
- ✅ Xabar yuborish jarayonini ko'rish mumkin
- ✅ To'xtatish va davom ettirish imkoniyati
- ✅ Xatolarni avtomatik qayta urinish

### ⚠️ Muhim:
- Spam qilishdan saqlaning
- Telegram chegaralariga rioya qiling
- Xabar tarkibini oldindan tekshiring

---

## 💬 CHAT - Foydalanuvchilar bilan Muloqot

### Nima uchun kerak?
Bot orqali boshqa foydalanuvchilar bilan bevosita chat qilish.

### Qanday ishlaydi?

1. **"💬 Chatlar"** tugmasini bosing
2. **"➕ Yangi chat boshlash"** tugmasini bosing
3. **Foydalanuvchi ID sini kiriting:**
   - ID: `123456789`
   - Yoki username: `@username`

4. **Xabar yozing va yuboring**

### Xususiyatlar:
- ✅ Shaxsiy chat (boshqa foydalanuvchilar ko'rmaydi)
- ✅ Bloklash va ovozsiz qilish imkoniyati
- ✅ Chat tarixini ko'rish

### ⚠️ Muhim:
- Chat qilish uchun ikki tomon ham botdan ro'yxatdan o'tgan bo'lishi kerak
- Shartlarga rioya qilish shart

---

## 🔍 GURUH QIDIRISH

### Nima uchun kerak?
Kerakli guruhlarni topish va ular haqida ma'lumot olish.

### Qanday ishlaydi?

1. **"🔍 Guruh qidirish"** tugmasini bosing
2. **"🔍 Qidirishni boshlash"** tugmasini bosing
3. **Guruh nomini yozing:**
   - Masalan: `Mafia`, `Crypto`, `IT`

4. **Natijalarni ko'ring:**
   - Guruh nomi
   - A'zolar soni
   - Guruh linki
   - Guruh ID si

### Misol:
```
🔍 Mafia - 4 ta guruh topildi:

1. Empire Mafia🇺🇿
   👥 3089 a'zo
   🔗 https://t.me/Empire_Mafia
   🆔 4401

2. True Mafia UZB 🇺🇿
   👥 863 a'zo
   🔗 https://t.me/True_Mafia_UZB
   🆔 0264
```

---

## 🗂 BAZALAR - Ma'lumotlarni Boshqarish

### Nima uchun kerak?
Yig'ilgan ma'lumotlarni ko'rish, qidirish va boshqarish.

### Qanday ishlaydi?

1. **"🗂 Bazalar"** tugmasini bosing
2. **"📋 Barcha bazalar"** - Barcha yig'ilgan guruhlar
3. **"🔍 ID orqali qidirish"** - Ma'lum bir foydalanuvchini topish

### Ko'rinish:
- Guruh nomi
- A'zolar soni
- Yig'ilgan sana
- Owner (kim yig'gan)

---

## ⭐️ OBUNA

### Nima uchun kerak?
Botdan cheksiz foydalanish uchun obuna sotib olish.

### Narxlar:
- **1 oy:** 50,000 so'm
- **3 oy:** 120,000 so'm
- **1 yil:** 400,000 so'm

### Qanday sotib olish:
1. **"⭐️ Obuna sotib olish"** tugmasini bosing
2. To'lov usulini tanlang
3. Admin bilan bog'laning
4. Tasdiqlanishini kuting

### Bepul foydalanish:
- Admin tasdiqlashini oling
- Cheklangan funksiyalar bilan ishlashingiz mumkin

---

## 👤 AKKUNT SOZLAMALARI

### Akkauntni ulash:
1. **"👤 Akkaunt"** tugmasini bosing
2. **"📱 Akkaunt ulash"** tugmasini bosing
3. Telefon raqamingizni yuboring

### Akkauntni uzish:
1. **"👤 Akkaunt"** tugmasini bosing
2. **"🚪 Akkauntni uzish"** tugmasini bosing

### ⚠️ Muhim:
- Akkauntni uzish barcha ma'lumotlarni o'chiradi
- Buni qayta tiklab bo'lmaydi

---

## 🌐 TIL

### Tilni o'zgartirish:
1. **"🌐 Til"** tugmasini bosing
2. O'zbekcha yoki Rus tilini tanlang

### Qo'llab-quvvatlanadigan tillar:
- 🇺🇿 O'zbekcha
- 🇷🇺 Ruscha

---

## 📞 ADMIN BILAN BOG'LANISH

### Qanday bog'lanish mumkin?

1. **"📞 Bog'lanish"** tugmasini bosing
2. **"💬 To'g'ridan to'g'ri bog'lanish"** - Admin profilini ko'rish
3. **"📝 Shablon orqali bog'lanish"** - Murojaat yuborish

### Murojaat yuborish:
1. **"📝 Shablon orqali bog'lanish"** ni tanlang
2. **Sarlavha** yozing (masalan: "Bot ishlamayapti")
3. **Xabar** yozing (batafsil)
4. Rasm yuborishingiz mumkin
5. **"Yuborish"** tugmasini bosing

### Javob:
- Admin 24 soat ichida javob beradi
- Murojaat holatini "📞 Bog'lanish" bo'limidan kuzatishingiz mumkin

---

## ⚙️ ADMIN PANEL (FAQAT ADMINLAR)

### Admin funksiyalari:

#### 1. Foydalanuvchilarni boshqarish
- Barcha foydalanuvchilarni ko'rish
- Obuna berish/olish
- Banned qilish/ochish
- Bepul qilish

#### 2. Bazalarni boshqarish
- Barcha bazalarni ko'rish
- Bazani o'chirish
- A'zolarni qo'lda qo'shish

#### 3. Yangilanishlar
- Yangilik yuborish
- Barcha foydalanuvchilarga xabar yuborish

#### 4. Statistikalar
- Jami foydalanuvchilar
- Faol obunalar
- Banned foydalanuvchilar

---

## ❓ KO'P BERILADIGAN SAVOLLAR

### 1. Botdan foydalanish uchun guruhda bo'lishim kerakmi?
**Javob:** Yo'q, botdan shaxsiy chatda ham foydalanish mumkin. Lekin Scraper va Utag funksiyalarini ishlatish uchun guruh kerak.

### 2. Guruhda admin bo'lishim kerakmi?
**Javob:**
- **Scraper:** Yo'q, oddiy a'zo bo'lishingiz kifoya (guruh ochiq bo'lsa)
- **Utag:** Ha, admin bo'lishingiz kerak
- **Mass DM:** Yo'q, kerak emas

### 3. Qancha guruh yig'ish mumkin?
**Javob:** Cheklov yo'q. Lekin katta guruhlar (10,000+ a'zo) uchun vaqt ketishi mumkin.

### 4. Xabar yuborishda cheklov bormi?
**Javob:** Ha, Telegram chegaralari mavjud:
- Kichik guruhlar: 30 xabar/daqiqa
- Katta guruhlar: 20 xabar/daqiqa
- Bot avtomatik ravishda kechikish qo'shib yuboradi

### 5. Baza nima?
**Javob:** Baza - yig'ilgan foydalanuvchilar ma'lumotlari (ID, username, ism). Har bir guruh uchun alohida baza yaratiladi.

### 6. Baza qanday ishlaydi?
**Javob:**
1. Scraper orqali guruh a'zolarini yig'asiz
2. Barcha ma'lumotlar bazaga saqlanadi
3. Mass DM orqali bazadagilarga xabar yuborasiz

### 7. Obuna tugasa nima bo'ladi?
**Javob:** Obuna tugagandan keyin botni ishlata olmaysiz. Yangi obuna sotib olishingiz kerak.

### 8. Bepul foydalanish mumkinmi?
**Javob:** Ha, admin tasdiqlashini olsangiz, cheklangan funksiyalar bilan bepul foydalanishingiz mumkin.

### 9. Xatolik yuzaga keldi, nima qilish kerak?
**Javob:**
1. "📞 Bog'lanish" orqali admin ga murojaat qiling
2. Xatolik matnini nusxalab oling
3. Qanday qilib xato yuzaga kelganini tushuntiring

### 10. Bot xavfsizmi?
**Javob:** Ha, bot:
- Session fayllarni shifrlaydi
- Ma'lumotlarni himoya qiladi
- Faqat sizga tegishli ma'lumotlarni saqlaydi
- Hech kim sizning ma'lumotlaringizni ko'ra olmaydi

---

## 🛠 XATOLARNI TUZATISH

### Bot javob bermayapti:
1. Internetni tekshiring
2. Botni qayta boshlang: `/start`
3. Agar yordam berilmasa, admin ga murojaat qiling

### "Noto'g'ri amal" xatosi:
1. Tugmani qayta bosing
2. Bir necha soniya kuting
3. Qayta urinib ko'ring

### Scraper ishlamayapti:
1. Guruh linki to'g'ri ekanligini tekshiring
2. Guruh ochiq ekanligini tekshiring
3. Katta guruhlar uchun vaqt ketishini hisobga oling

### Utag ishlamayapti:
1. Guruhda admin ekanligingizni tekshiring
2. Bot guruhda admin ekanligini tekshiring
3. To'xtatish buyrug'ini tekshiring

### Mass DM ishlamayapti:
1. Bazada foydalanuvchilar borligini tekshiring
2. Xabar tarkibini tekshiring
3. Telegram chegaralariga tushgan bo'lishingiz mumkin (kuting)

---

## 📞 YORDAM VA QO'LLAB-QUVVATLASH

### Admin bilan bog'lanish:
- Bot ichida: "📞 Bog'lanish" tugmasi orqali
- Telegram: @admin_username

### Yangilanishlar:
- Bot yangilanishlari haqida "📣 Yangiliklar" orqali xabar olasiz

### Fikr va takliflar:
- Har qanday fikr va takliflarni admin ga yuborishingiz mumkin

---

## 🔒 XAVFSIZLIK

### Ma'lumotlarni himoya qilish:
- ✅ Barcha ma'lumotlar shifrlanadi
- ✅ Session fayllar xavfsiz saqlanadi
- ✅ Hech qanday ma'lumot uchinchi shaxslarga berilmaydi
- ✅ Baza GitHub ga yuklanmaydi (maxfiy)

### Qoidalar:
1. ❌ Spam yubormang
2. ❌ Boshqa foydalanuvchilarni bezovta qilmang
3. ❌ Noqonuniy kontent yubormang
4. ✅ Qoidalarga rioya qiling

### Bloklash:
- Qoidalarni buzgan foydalanuvchilar botdan bloklanadi
- Blokni ochish uchun admin ga murojaat qiling

---

## 📊 STATISTIKA

### Siz ko'ra olasiz:
- Yig'ilgan guruhlar soni
- Jami a'zolar soni
- Yuborilgan xabarlar soni
- Faol obuna muddati

### Admin ko'ra oladi:
- Barcha foydalanuvchilar
- To'lovlar tarixi
- Xatoliklar va loglar
- Bot faoliyati

---

## 🎯 MASLAHATLAR

### Samarali foydalanish:
1. **Kichik guruhlardan boshlang** - Katta guruhlarni yig'ish vaqt ketadi
2. **Bazani toza saqlang** - Keraksiz ma'lumotlarni o'chiring
3. **Xabarlarni oldindan tekshiring** - Xato yubormaslik uchun
4. **Kechikish qo'shing** - FloodWait xatosini oldini olish uchun
5. **Vaqtni tanlang** - Odamlar faol bo'lgan vaqtda xabar yuboring

### Qo'shimcha:
- Bot yangilanadi va yangi funksiyalar qo'shiladi
- Yangilanishlar haqida "📣 Yangiliklar" orqali xabar olasiz
- Har qanday muammo bo'lsa, admin ga murojaat qiling

---

## 📝 YORDAMCHI XATOLAR

### "Guruh topilmadi":
- Guruh linki to'g'ri ekanligini tekshiring
- Guruh ochiq ekanligini tekshiring
- Boshqa so'z bilan qidiring

### "A'zo topilmadi":
- Guruhda a'zolar borligini tekshiring
- Scraper ni qayta ishga tushiring

### "Xabar yuborishda xato":
- Telegram chegaralariga tushgan bo'lishingiz mumkin
- 1-2 soat kuting
- Qayta urinib ko'ring

### "Obuna tugadi":
- Admin ga murojaat qiling
- Yangi obuna sotib oling

---

## 🎉 XULOSA

Vento Bot - bu kuchli va qulay bot bo'lib, u sizga:
- ✅ Vaqt tejaydi
- ✅ Ishingizni osonlashtiradi
- ✅ Ko'p funksiyalar beradi

### Muvaffaqiyatli foydalanish uchun:
1. Qoidalarga rioya qiling
2. Funksiyalarni to'g'ri ishlating
3. Admin bilan aloqada bo'ling
4. Yangilanishlarni kuzating

**Omad! 🚀**

---

## 📞 ALoQA

- **Bot:** @empire_family_bot
- **Admin:** @admin_username
- **Guruh:** @vento_support

**Oxirgi yangilanish:** 2026-07-28