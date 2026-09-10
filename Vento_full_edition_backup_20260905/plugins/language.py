from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from locales import get_text, get_available_languages
from database import get_known_user, update_user_language, register_known_user
import logging

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("language") | filters.command("lang"))
async def language_command(client: Client, message: Message):
    """Til tanlash command"""
    user_id = message.from_user.id
    
    user = await get_known_user(user_id)
    if not user:
        await register_known_user(
            user_id, 
            message.from_user.username, 
            message.from_user.first_name
        )
        current_lang = "uz"
    else:
        current_lang = user.get("language", "uz")
    
    languages = get_available_languages()
    keyboard = []
    
    for code, name in languages.items():
        emoji = "✅" if code == current_lang else "⚪"
        keyboard.append([InlineKeyboardButton(f"{emoji} {name}", callback_data=f"set_lang_{code}")])
    
    await message.reply_text(
        get_text("language_select", current_lang),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@Client.on_callback_query(filters.regex(r"^set_lang_(\w+)$"))
async def set_language_callback(client: Client, callback_query):
    """Tilni o'rnatish callback - tasdiqlash"""
    lang_code = callback_query.matches[0].group(1)
    user_id = callback_query.from_user.id
    
    await callback_query.answer()
    
    languages = get_available_languages()
    lang_name = languages.get(lang_code, lang_code)
    user = await get_known_user(user_id)
    current_lang = user.get("language", "uz") if user else "uz"
    
    confirm_text = get_text("language_confirm", current_lang).format(lang_name=lang_name)
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Ha", callback_data=f"confirm_lang_{lang_code}"),
            InlineKeyboardButton("❌ Yo'q", callback_data="language")
        ]
    ]
    
    await callback_query.message.edit_text(
        confirm_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


@Client.on_callback_query(filters.regex(r"^confirm_lang_(\w+)$"))
async def confirm_language_callback(client: Client, callback_query):
    """Tilni tasdiqlash va /start yuborish"""
    lang_code = callback_query.matches[0].group(1)
    user_id = callback_query.from_user.id
    
    logger.info("[LANGUAGE] Tasdiqlash: user_id=%s, yangi_til=%s", user_id, lang_code)
    
    try:
        await callback_query.answer()
        
        logger.info("[LANGUAGE] Bazaga yozilmoqda: user_id=%s, lang=%s", user_id, lang_code)
        await update_user_language(user_id, lang_code)
        logger.info("[LANGUAGE] Bazaga yozildi: user_id=%s, lang=%s", user_id, lang_code)
        
        user = await get_known_user(user_id)
        if not user:
            logger.info("[LANGUAGE] Yangi user: user_id=%s", user_id)
            await register_known_user(
                user_id,
                callback_query.from_user.username,
                callback_query.from_user.first_name,
                lang_code
            )
        
        confirmation_msg = get_text("language_set", lang_code)
        logger.info("[LANGUAGE] Xabar tahrirlanmoqda: %s...", confirmation_msg[:50])
        await callback_query.message.edit_text(confirmation_msg)
        logger.info("[LANGUAGE] Xabar tahrirlandi")
        
        start_message = get_text("start", lang_code)
        logger.info("[LANGUAGE] Start xabari yuborilmoqda: %s...", start_message[:50])
        
        from config import is_admin
        keyboard = None
        if is_admin(user_id):
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text("admin_panel", lang_code), callback_data="admin_panel")]
            ])
        
        sent_msg = await callback_query.message.reply_text(
            start_message,
            reply_markup=keyboard
        )
        
        logger.info("[LANGUAGE] Muvaffaqiyatli: user_id=%s, lang=%s, xabar=%s", user_id, lang_code, sent_msg is not None)
        
    except Exception as e:
        logger.exception("[LANGUAGE] XATOLIK: user_id=%s, xato=%s", user_id, e)
        try:
            await callback_query.answer(f"❌ Xatolik: {str(e)[:50]}", show_alert=True)
        except:
            pass
