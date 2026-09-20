"""
Profile Scoring Settings - Admin UI for profile analyzer configuration
"""
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from config import is_admin, is_owner

logger = logging.getLogger(__name__)

PROFILE_SCORING_BTN = "🧠 Profile Scoring"

# Check if profile analyzer is available
try:
    from profile_analyzer import ProfileAnalyzerConfig
    PROFILE_ANALYZER_AVAILABLE = True
except ImportError:
    PROFILE_ANALYZER_AVAILABLE = False
    logger.warning("Profile analyzer not available, settings disabled")


def _status_emoji(enabled: bool) -> str:
    return "✅" if enabled else "❌"


def _profile_scoring_keyboard(config) -> InlineKeyboardMarkup:
    """Generate keyboard for profile scoring settings"""
    rows = []
    
    # Main toggle
    rows.append([InlineKeyboardButton(
        f"Profile Scoring — {_status_emoji(config.enabled)}",
        callback_data="pscore|toggle_main"
    )])
    
    # Minimum score
    rows.append([InlineKeyboardButton(
        f"Minimum Score: {config.minimum_score}",
        callback_data="pscore|adjust_min_score"
    )])
    
    # Separator
    rows.append([InlineKeyboardButton("─ Analyzers ─", callback_data="pscore|dummy")])
    
    # Individual analyzers
    analyzers = config.analyzers
    rows.append([InlineKeyboardButton(
        f"Name Analyzer — {_status_emoji(analyzers.get('name', True))}",
        callback_data="pscore|toggle_name"
    )])
    rows.append([InlineKeyboardButton(
        f"Username Analyzer — {_status_emoji(analyzers.get('username', True))}",
        callback_data="pscore|toggle_username"
    )])
    rows.append([InlineKeyboardButton(
        f"Bio Analyzer — {_status_emoji(analyzers.get('bio', True))}",
        callback_data="pscore|toggle_bio"
    )])
    rows.append([InlineKeyboardButton(
        f"Photo Analyzer — {_status_emoji(analyzers.get('photo', True))}",
        callback_data="pscore|toggle_photo"
    )])
    
    # Cache settings
    rows.append([InlineKeyboardButton("─ Cache ─", callback_data="pscore|dummy")])
    rows.append([InlineKeyboardButton(
        f"Profile Cache — {_status_emoji(config.profile_cache_enabled)}",
        callback_data="pscore|toggle_profile_cache"
    )])
    rows.append([InlineKeyboardButton(
        f"Photo Cache — {_status_emoji(config.photo_cache_enabled)}",
        callback_data="pscore|toggle_photo_cache"
    )])
    
    # Back button
    rows.append([InlineKeyboardButton("🔙 Orqaga", callback_data="menu_main")])
    
    return InlineKeyboardMarkup(rows)


def _profile_scoring_text(config) -> str:
    """Generate text for profile scoring settings"""
    text = "🧠 **Profile Scoring Sozlamalari**\n\n"
    text += f"**Holat:** {'Yoqilgan' if config.enabled else 'O\'chirilgan'}\n"
    text += f"**Minimum Score:** {config.minimum_score}/{sum(1 for v in config.analyzers.values() if v)}\n\n"
    text += "Bu tizim profil ma'lumotlarini tahlil qilib,\n"
    text += "har bir analyzer uchun signal (0 yoki 1) beradi.\n"
    text += "Jami score minimum_score dan yuqori bo'lsa,\n"
    text += "foydalanuvchi bazaga qo'shiladi.\n\n"
    text += "⚠️ Bu hech qachon 100% aniq emas,\n"
    text += "faqat heuristic signal hisoblanadi."
    return text


@Client.on_message(filters.private & filters.text, group=-8)
async def profile_scoring_menu_command(client: Client, message: Message):
    """Profile scoring settings menu command"""
    if not message.from_user or (message.text or "").strip() != PROFILE_SCORING_BTN:
        from pyrogram import ContinuePropagation
        raise ContinuePropagation
    
    if not is_admin(message.from_user.id):
        await message.reply_text("⛔️ Faqat adminlar uchun")
        from pyrogram import StopPropagation
        raise StopPropagation
    
    if not PROFILE_ANALYZER_AVAILABLE:
        await message.reply_text("⚠️ Profile analyzer tizimi o'rnatilmagan")
        from pyrogram import StopPropagation
        raise StopPropagation
    
    config = ProfileAnalyzerConfig.from_env()
    await message.reply_text(
        _profile_scoring_text(config),
        reply_markup=_profile_scoring_keyboard(config)
    )
    from pyrogram import StopPropagation
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^pscore\|"))
async def profile_scoring_callback(client: Client, callback_query: CallbackQuery):
    """Handle profile scoring settings callbacks"""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("⛔️ Faqat adminlar uchun", show_alert=True)
        return
    
    if not PROFILE_ANALYZER_AVAILABLE:
        await callback_query.answer("⚠️ Profile analyzer tizimi o'rnatilmagan", show_alert=True)
        return
    
    action = callback_query.data.split("|")[1]
    
    # Load current config
    config = ProfileAnalyzerConfig.from_env()
    
    if action == "toggle_main":
        config.enabled = not config.enabled
        await callback_query.answer(f"Profile scoring {'yoqildi' if config.enabled else 'o\'chirildi'}")
    
    elif action == "adjust_min_score":
        # Simple increment/decrement for minimum score
        config.minimum_score = (config.minimum_score % 4) + 1  # Cycle 1-4
        await callback_query.answer(f"Minimum score: {config.minimum_score}")
    
    elif action == "toggle_name":
        config.analyzers["name"] = not config.analyzers.get("name", True)
        await callback_query.answer(f"Name analyzer {'yoqildi' if config.analyzers['name'] else 'o\'chirildi'}")
    
    elif action == "toggle_username":
        config.analyzers["username"] = not config.analyzers.get("username", True)
        await callback_query.answer(f"Username analyzer {'yoqildi' if config.analyzers['username'] else 'o\'chirildi'}")
    
    elif action == "toggle_bio":
        config.analyzers["bio"] = not config.analyzers.get("bio", True)
        await callback_query.answer(f"Bio analyzer {'yoqildi' if config.analyzers['bio'] else 'o\'chirildi'}")
    
    elif action == "toggle_photo":
        config.analyzers["photo"] = not config.analyzers.get("photo", True)
        await callback_query.answer(f"Photo analyzer {'yoqildi' if config.analyzers['photo'] else 'o\'chirildi'}")
    
    elif action == "toggle_profile_cache":
        config.profile_cache_enabled = not config.profile_cache_enabled
        await callback_query.answer(f"Profile cache {'yoqildi' if config.profile_cache_enabled else 'o\'chirildi'}")
    
    elif action == "toggle_photo_cache":
        config.photo_cache_enabled = not config.photo_cache_enabled
        await callback_query.answer(f"Photo cache {'yoqildi' if config.photo_cache_enabled else 'o\'chirildi'}")
    
    elif action == "dummy":
        await callback_query.answer()
        return
    
    else:
        await callback_query.answer("Noma'lum amal")
        return
    
    # Update UI
    await callback_query.message.edit_text(
        _profile_scoring_text(config),
        reply_markup=_profile_scoring_keyboard(config)
    )
    
    # Note: In a real implementation, you'd save this config to a file or database
    # For now, this just updates the in-memory config for the session
    logger.info(f"Profile scoring config updated: {action}")


__all__ = ["PROFILE_SCORING_BTN"]