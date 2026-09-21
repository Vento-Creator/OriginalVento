"""
Profile Scoring Settings - Admin UI for profile analyzer configuration
"""
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from config import is_admin, is_owner, can_manage_scraper

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
    """Return emoji based on enabled status"""
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
    rows.append([InlineKeyboardButton("─ Analizatorlar ─", callback_data="pscore|dummy")])
    
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
    rows.append([InlineKeyboardButton("─ Kesh Boshqaruvi ─", callback_data="pscore|dummy")])
    rows.append([
        InlineKeyboardButton(
            f"Profile Kesh — {_status_emoji(config.profile_cache_enabled)}",
            callback_data="pscore|toggle_profile_cache"
        ),
        InlineKeyboardButton(
            f"Photo Kesh — {_status_emoji(config.photo_cache_enabled)}",
            callback_data="pscore|toggle_photo_cache"
        )
    ])
    rows.append([InlineKeyboardButton("🧹 Keshni Tozalash", callback_data="pscore|clear_cache")])
    
    # Back button
    rows.append([InlineKeyboardButton("🔙 Orqaga", callback_data="menu_main")])
    
    return InlineKeyboardMarkup(rows)


def _profile_scoring_text(config) -> str:
    """Generate text for profile scoring settings"""
    text = "🧠 **Profile Scoring — Profil Tahlili Sozlamalari**\n\n"
    status = "✅ Yoqilgan" if config.enabled else "❌ O'chirilgan"
    text += f"**Tizim holati:** {status}\n"
    enabled_analyzers = sum(1 for v in config.analyzers.values() if v)
    text += f"**Minimal Ball (Min Score):** `{config.minimum_score}/{enabled_analyzers}`\n\n"
    text += "📋 **Yoqilgan Analizatorlar:**\n"
    text += f"• Ism (Name): {_status_emoji(config.analyzers.get('name', True))}\n"
    text += f"• Username: {_status_emoji(config.analyzers.get('username', True))}\n"
    text += f"• Bio: {_status_emoji(config.analyzers.get('bio', True))}\n"
    text += f"• Rasm (Computer Vision ViT): {_status_emoji(config.analyzers.get('photo', True))}\n\n"
    
    try:
        from profile_analyzer.ml import assets_status
        st = assets_status()
        text += f"⚙️ **ML Model Holati:**\n"
        text += f"• Yuz Detektori (OpenCV DNN): {'✅ Tayyor' if st.get('face_detector') else '⚠️ Yuklanmagan'}\n"
        text += f"• Gender Modeli (HuggingFace ViT): ✅ `{st.get('gender_model_id')}`\n"
        text += f"• Matn ML (TF-IDF): {'✅ Tayyor' if st.get('text_models') else 'ℹ️ Birinchi tahlilda yaratiladi'}\n"
    except Exception:
        pass
        
    return text


@Client.on_message(filters.private & filters.text, group=-8)
async def profile_scoring_menu_command(client: Client, message: Message):
    """Handle profile scoring settings menu command"""
    if not message.from_user or (message.text or "").strip() != PROFILE_SCORING_BTN:
        from pyrogram import ContinuePropagation
        raise ContinuePropagation
    
    if not await can_manage_scraper(message.from_user.id):
        await message.reply_text("⛔️ Sizda scraper sozlamalarini boshqarish huquqi yo'q")
        from pyrogram import StopPropagation
        raise StopPropagation
    
    if not PROFILE_ANALYZER_AVAILABLE:
        await message.reply_text("⚠️ Profile analyzer system not installed")
        from pyrogram import StopPropagation
        raise StopPropagation
    
    config = ProfileAnalyzerConfig.load()
    await message.reply_text(
        _profile_scoring_text(config),
        reply_markup=_profile_scoring_keyboard(config)
    )
    from pyrogram import StopPropagation
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^pscore\|"))
async def profile_scoring_callback(client: Client, callback_query: CallbackQuery):
    """Handle profile scoring settings callbacks"""
    if not await can_manage_scraper(callback_query.from_user.id):
        await callback_query.answer("⛔️ Sizda scraper sozlamalarini boshqarish huquqi yo'q", show_alert=True)
        return
    
    if not PROFILE_ANALYZER_AVAILABLE:
        await callback_query.answer("⚠️ Profile analyzer system not installed", show_alert=True)
        return
    
    action = callback_query.data.split("|")[1]
    
    # Load current persistent config
    config = ProfileAnalyzerConfig.load()
    
    if action == "toggle_main":
        config.enabled = not config.enabled
        status = "Yoqildi" if config.enabled else "O'chirildi"
        await callback_query.answer(f"Profile Scoring {status}")
    
    elif action == "adjust_min_score":
        # Simple increment/decrement for minimum score
        config.minimum_score = (config.minimum_score % 4) + 1  # Cycle 1-4
        await callback_query.answer(f"Min score: {config.minimum_score}")
    
    elif action == "toggle_name":
        config.analyzers["name"] = not config.analyzers.get("name", True)
        status = "Yoqildi" if config.analyzers['name'] else "O'chirildi"
        await callback_query.answer(f"Name analyzer {status}")
    
    elif action == "toggle_username":
        config.analyzers["username"] = not config.analyzers.get("username", True)
        status = "Yoqildi" if config.analyzers['username'] else "O'chirildi"
        await callback_query.answer(f"Username analyzer {status}")
    
    elif action == "toggle_bio":
        config.analyzers["bio"] = not config.analyzers.get("bio", True)
        status = "Yoqildi" if config.analyzers['bio'] else "O'chirildi"
        await callback_query.answer(f"Bio analyzer {status}")
    
    elif action == "toggle_photo":
        config.analyzers["photo"] = not config.analyzers.get("photo", True)
        status = "Yoqildi" if config.analyzers['photo'] else "O'chirildi"
        await callback_query.answer(f"Photo analyzer {status}")
    
    elif action == "toggle_profile_cache":
        config.profile_cache_enabled = not config.profile_cache_enabled
        status = "Yoqildi" if config.profile_cache_enabled else "O'chirildi"
        await callback_query.answer(f"Profile cache {status}")
    
    elif action == "toggle_photo_cache":
        config.photo_cache_enabled = not config.photo_cache_enabled
        status = "Yoqildi" if config.photo_cache_enabled else "O'chirildi"
        await callback_query.answer(f"Photo cache {status}")
    
    elif action == "clear_cache":
        await callback_query.answer()
        confirm_text = (
            "⚠️ **Diqqat! Barcha keshni tozalashni tasdiqlaysizmi?**\n\n"
            "Barcha saqlangan profil va rasm tahlil keshlar (disk va RAMdan) o'chirib tashlanadi.\n"
            "Keyingi scrape jarayonida rasmlar qayta yuklanib, ML orqali tahlil qilinadi."
        )
        confirm_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Ha, tozalansin", callback_data="pscore|confirm_clear_cache"),
                InlineKeyboardButton("❌ Bekor qilish", callback_data="pscore|refresh")
            ]
        ])
        await callback_query.message.edit_text(confirm_text, reply_markup=confirm_keyboard)
        return

    elif action == "confirm_clear_cache":
        try:
            from plugins.scraper import get_profile_analyzer
            pa = await get_profile_analyzer()
            if pa:
                await pa.clear_caches()
                await callback_query.answer("🧹 Barcha keshlar muvaffaqiyatli tozalandi!", show_alert=True)
            else:
                await callback_query.answer("Kesh tozalanmadi (analizator yo'q)", show_alert=True)
        except Exception as e:
            await callback_query.answer(f"Keshni tozalashda xato: {e}", show_alert=True)

    elif action == "refresh":
        await callback_query.answer("Bekor qilindi")

    elif action == "dummy":
        await callback_query.answer()
        return
    
    else:
        await callback_query.answer("Noma'lum amal")
        return
    
    # Save persistent config
    config.save()
    
    # Update UI
    await callback_query.message.edit_text(
        _profile_scoring_text(config),
        reply_markup=_profile_scoring_keyboard(config)
    )
    
    logger.info(f"Profile scoring config updated and saved: action={action}")


__all__ = ["PROFILE_SCORING_BTN"]