"""
Mini-App Login Handler — Mini-App dan kelgan sessiya ulash so'rovini bot orqali qayta ishlash.

Jarayon:
  1. Mini-App /api/login/request → pending_approvals va login_sessions ga yoziladi + Bot xabar yuboradi
  2. Foydalanuvchi botda "🔗 Sessiya Ulash" tugmasini bosadi
  3. Bot login jarayonini boshlaydi (login_service.start_login_from_miniapp)
  4. Jarayon tugagach mini-app polling orqali biladi (user_sessions jadvalidan)
"""

import logging
import time
import asyncio

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

from database import get_db_connection

logger = logging.getLogger(__name__)


async def _get_login_session_step(user_id: int) -> str:
    """login_sessions jadvalidan step ni olish."""
    try:
        async with get_db_connection() as db:
            cur = await db.execute(
                "SELECT step FROM login_sessions WHERE user_id = ?",
                (user_id,)
            )
            row = await cur.fetchone()
            return row[0] if row else "idle"
    except Exception:
        return "idle"


async def _set_login_session_step(user_id: int, step: str):
    """login_sessions da stepni yangilash."""
    try:
        async with get_db_connection() as db:
            await db.execute(
                """INSERT INTO login_sessions (user_id, step, created_at, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET step = ?, updated_at = ?""",
                (user_id, step, int(time.time()), int(time.time()), step, int(time.time()))
            )
    except Exception as e:
        logger.warning(f"login_sessions update error for {user_id}: {e}")


@Client.on_callback_query(filters.regex("^miniapp_login_start$"))
async def miniapp_login_start_handler(client: Client, cq: CallbackQuery):
    """
    Mini-App dan yuborilgan 'Sessiya Ulash' tugmasi.
    Bot login jarayonini boshlaydi.
    """
    user_id = cq.from_user.id

    await cq.answer()

    # Allaqachon sessiya bor-yo'qligini tekshirish
    from session_manager import has_active_sessions
    if has_active_sessions(user_id):
        await cq.message.edit_text(
            "✅ **Sessiya allaqachon ulangan!**\n\n"
            "Akkauntingiz faol. Mini-App ni yopib qayta oching.",
            parse_mode=ParseMode.MARKDOWN
        )
        await _set_login_session_step(user_id, "connected")
        return

    # Login jarayonini boshlash
    try:
        from login_system import login_service
        # Avvalgi holatni tozalash
        await _set_login_session_step(user_id, "in_progress")

        # Login jarayonini boshlash
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("📱 Login jarayonini boshlash", callback_data="acc_add")],
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="miniapp_login_cancel")]
        ])

        await cq.message.edit_text(
            "🔐 **Sessiya Ulash**\n\n"
            "Mini-App orqali akkauntingizni ulash uchun quyidagi tugmani bosing.\n\n"
            "📋 **Jarayon:**\n"
            "1️⃣ Telefon raqamingizni kiriting\n"
            "2️⃣ SMS kodini kiriting\n"
            "3️⃣ Tayyor! Mini-App avtomatik yangilanadi.\n\n"
            "⚠️ _Jarayonni tark etmang — ma'lumot saqlanmaydi._",
            reply_markup=buttons,
            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:
        logger.error(f"miniapp_login_start error for {user_id}: {e}")
        await cq.message.edit_text(
            "❌ Xatolik yuz berdi. Iltimos, /start bosib qayta urinib ko'ring.",
        )


@Client.on_callback_query(filters.regex("^miniapp_login_cancel$"))
async def miniapp_login_cancel_handler(client: Client, cq: CallbackQuery):
    """Mini-App login jarayonini bekor qilish."""
    user_id = cq.from_user.id
    await _set_login_session_step(user_id, "idle")

    # pending_approvals dan o'chirish
    try:
        async with get_db_connection() as db:
            await db.execute(
                "DELETE FROM pending_approvals WHERE user_id = ?",
                (user_id,)
            )
    except Exception as e:
        logger.warning(f"Delete pending_approvals error for {user_id}: {e}")

    await cq.answer("Bekor qilindi", show_alert=False)
    await cq.message.edit_text(
        "❌ **Sessiya ulash bekor qilindi.**\n\n"
        "Mini-App'dan qaytadan ulash tugmasini bosishingiz mumkin.",
        parse_mode=ParseMode.MARKDOWN
    )
