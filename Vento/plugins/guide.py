from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from config import user_states
import logging

logger = logging.getLogger(__name__)

GUIDE_STATE = "guide_state"

GUIDE_PAGES = [
    """📖 **Vento Bot - Foydalanish Qo'llanmasi**

🤖 **Bot nima?**
Vento Bot - Telegram guruhlaridan a'zolarni yig'ish, ularga xabar yuborish va boshqa samarali vazifalarni bajarish uchun yaratilgan bot.

✅ **Bot imkoniyatlari:**
• Guruhlardan odam yig'ish (Scraper)
• Ko'p xabar yuborish (Mass DM)
• Guruhda mention qilish (Utag)
• Foydalanuvchilar bilan chat
• Guruhlarni qidirish

📋 **Talablar:**
• Telegram akkaunt
• Obuna (pullik yoki bepul)
• Admin tasdiqi

👇 **Davomini o'qish uchun "Oldingi" tugmasini bosing**""",

    """🔍 **SCRAPER - Guruhlardan Odam Yig'ish**

**Nima uchun?**
Guruhdagi barcha a'zolarni yig'ib, bazaga saqlash uchun.

**Qanday ishlaydi?**
1. "🔍 Scraper" tugmasini bosing
2. "▶️ Boshlash" ni tanlang
3. Guruh linkini yuboring:
   • https://t.me/mafia_group
   • @group_username
   • -1001234567890 (ID)

4. Yig'ish turini tanlang:
   • Tez yig'ish - Barcha a'zolar
   • Xabar yuborish - Faqat faol a'zolar

5. Kuting - bot a'zolarni yig'ib boradi

⚠️ **Muhim:**
• Guruh admini bo'lishingiz shart emas
• Guruh ochiq bo'lishi kerak
• 10,000+ a'zoli guruhlar uchun vaqt ketadi

💡 **Natija:** Barcha a'zolar bazaga saqlanadi, keyin Mass DM orqali xabar yuborishingiz mumkin.""",

    """🏷 **UTAG - Guruhda Mention Qilish**

**Nima uchun?**
Guruhda bir vaqtda ko'p foydalanuvchilarni mention qilish (chaqirish) uchun.

**Qanday ishlaydi?**
1. "🏷 Utag" tugmasini bosing
2. "▶️ Boshlash" ni tanlang
3. Guruhni tanlang (bazadan yoki ID orqali)
4. Matnni yozing:
   "Salom! Bugun yangi konkurs!"
5. "Yuborish" tugmasini bosing

Bot bu matnni har bir foydalanuvchi oldidan qo'shib yuboradi:
"Salom! Bugun yangi konkurs! @user1 @user2 @user3..."

⚙️ **Sozlamalar:**
• Tezlik: 2 sekund (default)
• To'xtatish: "stop" (default)

⚠️ **Muhim:**
• Guruhda admin bo'lishingiz KERAK
• FloodWait xatosini oldini olish uchun kechikish qo'shing
• Juda ko'p mention qilish bloklanishiga olib kelishi mumkin""",

    """📨 **MASS DM - Ko'p Xabar Yuborish**

**Nima uchun?**
Bazadagi barcha yoki tanlangan foydalanuvchilarga xabar yuborish uchun.

**Qanday ishlaydi?**
1. "📨 Mass DM" tugmasini bosing
2. "▶️ Boshlash" ni tanlang
3. Guruhni tanlang (kimlarni xabar yuborish)
4. Xabar turini tanlang:
   • Matn - Oddiy xabar
   • Rasm - Rasm + matn
   • Video - Video + matn
5. Xabarni yozing va yuboring

✨ **Xususiyatlar:**
• Har bir foydalanuvchiga alohida xabar
• Jarayonni ko'rish mumkin
• To'xtatish/davom ettirish
• Avtomatik qayta urinish

⚠️ **Muhim:**
• Spam qilishdan saqlaning
• Telegram chegaralariga rioya qiling
• Xabarni oldindan tekshiring

📊 **Chegaralar:**
• Kichik guruhlar: 30 xabar/daqiqa
• Katta guruhlar: 20 xabar/daqiqa""",

    """💬 **CHAT - Foydalanuvchilar bilan Muloqot**

**Nima uchun?**
Bot orqali boshqa foydalanuvchilar bilan bevosita chat qilish.

**Qanday ishlaydi?**
1. "💬 Chatlar" tugmasini bosing
2. "➕ Yangi chat boshlash" ni tanlang
3. Foydalanuvchi ID sini kiriting:
   • ID: 123456789
   • Username: @username
4. Xabar yozing va yuboring

✨ **Xususiyatlar:**
• Shaxsiy chat (boshqalar ko'rmaydi)
• Bloklash/ovozsiz qilish
• Chat tarixini ko'rish

⚠️ **Muhim:**
• Ikki tomon ham botdan ro'yxatdan o'tgan bo'lishi kerak
• Chat shartlariga rozilik berish shart

🔐 **Xavfsizlik:**
• Barcha xabarlar shifrlanadi
• Faqat ikki tomon ko'ra oladi""",

    """🔍 **GURUH QIDIRISH**

**Nima uchun?**
Kerakli guruhlarni topish va ma'lumot olish uchun.

**Qanday ishlaydi?**
1. "🔍 Guruh qidirish" tugmasini bosing
2. "🔍 Qidirishni boshlash" ni tanlang
3. Guruh nomini yozing:
   • Mafia
   • Crypto
   • IT

4. Natijalarni ko'ring:
   • Guruh nomi
   • A'zolar soni
   • Guruh linki
   • Guruh ID si

📊 **Misol natija:**
🔍 Mafia - 4 ta guruh topildi:

1. Empire Mafia🇺🇿
   👥 3089 a'zo
   🔗 https://t.me/Empire_Mafia
   🆔 4401

💡 **Foydalanish:**
Guruh ID sini nusxalab, Scraper yoki Utag da ishlating""",

    """🗂 **BAZALAR - Ma'lumotlarni Boshqarish**

**Nima uchun?**
Yig'ilgan ma'lumotlarni ko'rish va boshqarish uchun.

**Qanday ishlaydi?**
1. "🗂 Bazalar" tugmasini bosing
2. Quyidagi imkoniyatlardan foydalaning:
   • 📋 Barcha bazalar - Barcha guruhlar
   • 🔍 ID orqali qidirish - Foydalanuvchi topish

📊 **Ko'rinish:**
• Guruh nomi
• A'zolar soni
• Yig'ilgan sana
• Owner (kim yig'gan)

💡 **Ma'lumot:**
Har bir guruh uchun alohida baza yaratiladi.
Bazada quyidagilar saqlanadi:
• User ID
• Username
• Ism
• Guruh ID

🔍 **Qidirish:**
Foydalanuvchini ID orqali qidirishingiz mumkin.""",

    """⭐️ **OBUNA VA AKKUNT**

**⭐️ Obuna:**
Botdan foydalanish uchun obuna sotib oling.

💰 **Narxlar:**
• 1-oy: 50 stars(1 martalik!)
• Qolgan oylar uchun: 100 stars

**Qanday sotib olish:**
1. "⭐️ Obuna sotib olish" tugmasini bosing
2. To'lov usulini tanlang
3. Admin bilan bog'laning
4. Tasdiqlanishini kuting

👤 **Akkaunt sozlamalari:**
• Akkaunt ulash - Telegramni ulash
• Akkauntni uzish - Logout

⚠️ **Muhim:**
• Akkauntni uzish ma'lumotlarni o'chiradi
• Qayta tiklab bo'lmaydi

🆓 **Bepul foydalanish:**
Admin tasdiqlashini olsangiz, cheklangan funksiyalar bilan bepul foydalanishingiz mumkin.""",

    """⚙️ **ADMIN PANEL VA XAVFSIZLIK**

**⚙️ Admin Panel (FAQAT ADMINLAR):**
• Foydalanuvchilarni boshqarish
• Bazalarni boshqarish
• Yangilanishlar yuborish
• Statistikalar

**🔒 Xavfsizlik:**
✅ Barcha ma'lumotlar shifrlanadi
✅ Session fayllar xavfsiz
✅ Hech qanday ma'lumot uchinchi shaxslarga berilmaydi

**❌ Qoidalar:**
1. Spam yubormang
2. Boshqalarni bezovta qilmang
3. Noqonuniy kontent yubormang

**🚫 Bloklash:**
Qoidalarni buzgan foydalanuvchilar botdan bloklanadi.
Blokni ochish uchun admin ga murojaat qiling.

**📞 Bog'lanish:**
• Bot ichida: "📞 Bog'lanish"
• Telegram: @Nova_OS_builder_Admin
• Murojaat: 24 soat ichida javob"""

    """❓ **KO'P BERILADIGAN SAVOLLAR**

**1. Guruhda bo'lishim kerakmi?**
Yo'q, lekin Scraper va Utag uchun guruh kerak.

**2. Admin bo'lishim kerakmi?**
• Scraper: Yo'q
• Utag: Ha
• Mass DM: Yo'q

**3. Qancha guruh yig'ish mumkin?**
Cheklov yo'q, lekin katta guruhlar uchun vaqt ketadi.

**4. Xabar chegaralari bormi?**
Ha: 30 xabar/daqiqa (kichik), 20 xabar/daqiqa (katta).

**5. Baza nima?**
Yig'ilgan foydalanuvchilar ma'lumotlari.

**6. Obuna tugasa?**
Yangi obuna sotib olishingiz kerak.

**7. Bepul foydalanish mumkinmi?**
Bu vaziyatga qarab o'zgarishi mumkin, yangilanishlarni kuzatib boring!

**8. Xatolik yuzaga keldi?**
"📞 Bog'lanish" orqali admin ga murojaat qiling.

**9. Bot xavfsizmi?**
Ha, barcha ma'lumotlar himoya qilingan.

**10. Qo'shimcha ma'lumot?**
Yangilanishlar: "📣 Yangiliklar" bo'limi.

---
✅ **Qo'llanma tugadi!**
Omad! 🚀"""
]

TOTAL_PAGES = len(GUIDE_PAGES)


@Client.on_callback_query(filters.regex("^menu_guide$"))
async def menu_guide_callback(client: Client, cq: CallbackQuery):
    """Tezkor tushuncha - Guide boshi"""
    uid = cq.from_user.id
    
    user_states[uid] = GUIDE_STATE
    user_states[f"{uid}_guide_page"] = 0
    
    await show_guide_page(client, cq.message, uid, 0)
    await cq.answer()

async def show_guide_page(client: Client, message: Message, uid: int, page: int):
    """Guide sahifasini ko'rsatish"""
    if page < 0:
        page = 0
    elif page >= TOTAL_PAGES:
        page = TOTAL_PAGES - 1
    
    user_states[f"{uid}_guide_page"] = page
    
    keyboard = []
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Oldingi", callback_data=f"guide_page_{page - 1}"))
    if page < TOTAL_PAGES - 1:
        nav_buttons.append(InlineKeyboardButton("Keyingi ▶️", callback_data=f"guide_page_{page + 1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🔙 Yopish", callback_data="menu_main")])
    
    try:
        await message.edit_text(
            GUIDE_PAGES[page],
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except:
        await message.reply_text(
            GUIDE_PAGES[page],
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

@Client.on_callback_query(filters.regex(r"^guide_page_(\d+)$"))
async def guide_page_callback(client: Client, cq: CallbackQuery):
    """Guide sahifasi o'tish"""
    uid = cq.from_user.id
    
    if user_states.get(uid) != GUIDE_STATE:
        await cq.answer("❌ Qo'llanma yopilgan", show_alert=True)
        return
    
    page = int(cq.data.split("_")[2])
    
    await show_guide_page(client, cq.message, uid, page)
    await cq.answer()

@Client.on_message(filters.private & filters.text & ~filters.command(["start"]), group=-8)
async def guide_message_handler(client: Client, message: Message):
    """Guide message handler - ignore all messages in guide mode"""
    from pyrogram import ContinuePropagation
    
    uid = message.from_user.id
    state = user_states.get(uid)
    
    if state == GUIDE_STATE:
        raise ContinuePropagation  # Guide state doesn't process messages, just ignore
    
    raise ContinuePropagation