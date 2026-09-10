"""
Admin Panel - Foydalanuvchilar ro'yxati, Ban/Unban boshqaruvi
"""
import logging
import time
from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
)

from database import (
    get_all_registered_user_ids, get_all_users_count, search_users,
    ban_user, unban_user, is_user_banned, get_all_banned_users,
    get_banned_count, get_admin_stats, is_admin,
)

logger = logging.getLogger(__name__)

_admin_states = {}


def _user_label(u: dict) -> str:
    uid = u.get("user_id")
    uname = u.get("username")
    fname = u.get("first_name") or ""
    parts = []
    if fname:
        parts.append(fname)
    if uname:
        parts.append(f"@{uname}")
    parts.append(f"`{uid}`")
    return " ".join(parts)


@Client.on_callback_query(filters.regex("^admin_panel$"))
async def admin_panel_callback(client: Client, cq: CallbackQuery):
    """Admin panel asosiy menyusi."""
    user_id = cq.from_user.id
    if not await is_admin(user_id):
        await cq.answer("❌ Siz admin emassiz!", show_alert=True)
        return

    stats = await get_admin_stats()
    text = (
        "👑 **Admin Panel**\n\n"
        f"👥 Jami foydalanuvchilar: **{stats['total_users']}** ta\n"
        f"🚫 Ban qilinganlar: **{stats['banned']}** ta\n"
        f"👑 Adminlar: **{stats['admins']}** ta\n"
        f"🗂 Bazalar: **{stats['bazas']}** ta\n\n"
        "Quyidagi bo'limlardan birini tanlang:"
    )
    buttons = [
        [InlineKeyboardButton("👥 Foydalanuvchilar ro'yxati", callback_data="admin_users_list:0")],
        [InlineKeyboardButton("🔍 Foydalanuvchi qidirish", callback_data="admin_search_user")],
        [InlineKeyboardButton("🚫 Ban qilinganlar ro'yxati", callback_data="admin_bans_list:0")],
        [InlineKeyboardButton("➕ Ban qilish (ID)", callback_data="admin_ban_id")],
        [InlineKeyboardButton("🏠 Asosiy Menyuga Qaytish", callback_data="menu_main")],
    ]
    await cq.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^admin_users_list:(\d+)$"))
async def admin_users_list_callback(client: Client, cq: CallbackQuery):
    """Foydalanuvchilar ro'yxati (sahifalangan)."""
    user_id = cq.from_user.id
    if not await is_admin(user_id):
        await cq.answer("❌ Siz admin emassiz!", show_alert=True)
        return

    page = int(cq.matches[0].group(1))
    per_page = 20
    total = await get_all_users_count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))

    users = await get_all_registered_user_ids(limit=per_page, offset=page * per_page)

    lines = [f"👥 **Foydalanuvchilar ro'yxati** ({total} ta) — {page + 1}/{total_pages}\n"]
    for u in users:
        lines.append(f"• {_user_label(u)}")

    if not users:
        lines.append("\nHozircha foydalanuvchilar yo'q.")

    buttons = []
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"admin_users_list:{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"admin_users_list:{page + 1}"))
    if nav_row:
        buttons.append(nav_row)
    buttons.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])

    await cq.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))
    await cq.answer()


@Client.on_callback_query(filters.regex("^admin_search_user$"))
async def admin_search_user_callback(client: Client, cq: CallbackQuery):
    """Foydalanuvchi qidirish uchun matn kiritish."""
    user_id = cq.from_user.id
    if not await is_admin(user_id):
        await cq.answer("❌ Siz admin emassiz!", show_alert=True)
        return

    _admin_states[user_id] = "WAIT_SEARCH_QUERY"
    await cq.message.edit_text(
        "🔍 **Foydalanuvchi qidirish**\n\n"
        "Qidirish uchun username, ism yoki Telegram ID yuboring:\n"
        "Masalan: `@username`, `John`, `123456789`\n\n"
        "*(Bekor qilish uchun /start yuboring)*"
    )
    await cq.answer()

@Client.on_callback_query(filters.regex("^admin_ban_id$"))
async def admin_ban_id_callback(client: Client, cq: CallbackQuery):
    """ID orqali ban qilish."""
    user_id = cq.from_user.id
    if not await is_admin(user_id):
        await cq.answer("❌ Siz admin emassiz!", show_alert=True)
        return

    _admin_states[user_id] = "WAIT_BAN_ID"
    await cq.message.edit_text(
        "➕ **Ban qilish (ID orqali)**\n\n"
        "Ban qilmoqchi bo'lgan foydalanuvchining Telegram ID sini yuboring:\n"
        "Masalan: `123456789`\n\n"
        "*(Bekor qilish uchun /start yuboring)*"
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^admin_ban:(\d+)$"))
async def admin_ban_confirm_callback(client: Client, cq: CallbackQuery):
    """Ban qilishni tasdiqlash."""
    user_id = cq.from_user.id
    if not await is_admin(user_id):
        await cq.answer("❌ Siz admin emassiz!", show_alert=True)
        return

    target_id = int(cq.matches[0].group(1))
    if target_id == user_id:
        await cq.answer("❌ O'zingizni ban qila olmaysiz!", show_alert=True)
        return

    _admin_states[user_id] = f"WAIT_BAN_REASON:{target_id}"
    await cq.message.edit_text(
        f"🚫 **Ban qilish tasdiqlash**\n\n"
        f"Maqsad: `{target_id}`\n\n"
        "Agar sabab bo'lsa, yozing (yoki 'tasdiqlash' deb yuboring):"
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^admin_unban:(\d+)$"))
async def admin_unban_callback(client: Client, cq: CallbackQuery):
    """Bandan chiqarish."""
    user_id = cq.from_user.id
    if not await is_admin(user_id):
        await cq.answer("❌ Siz admin emassiz!", show_alert=True)
        return

    target_id = int(cq.matches[0].group(1))
    await unban_user(target_id)
    await cq.answer(f"✅ `{target_id}` ban dan chiqarildi!", show_alert=True)
    await admin_bans_list_page(client, cq, 0)

async def admin_bans_list_page(client: Client, cq: CallbackQuery, page: int):
    """Ban qilinganlar ro'yxati sahifasi."""
    per_page = 20
    total = await get_banned_count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))

    bans = await get_all_banned_users(limit=per_page, offset=page * per_page)

    lines = [f"🚫 **Ban qilinganlar ro'yxati** ({total} ta) — {page + 1}/{total_pages}\n"]
    for b in bans:
        uid = b.get("user_id")
        count = b.get("violation_count", 1)
        reason = b.get("reason") or ""
        banned_at = b.get("banned_at", 0)
        dt = ""
        if banned_at:
            dt = time.strftime("%Y-%m-%d %H:%M", time.localtime(banned_at))
        line = f"• `{uid}` — ⚠️ {count} marta"
        if dt:
            line += f" ({dt})"
        if reason:
            line += f"\n  ↳ _{reason}_"
        lines.append(line)

    if not bans:
        lines.append("\nBan qilinganlar yo'q.")

    buttons = []
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"admin_bans_list:{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"admin_bans_list:{page + 1}"))
    if nav_row:
        buttons.append(nav_row)
    buttons.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])

    await cq.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^admin_bans_list:(\d+)$"))
async def admin_bans_list_callback(client: Client, cq: CallbackQuery):
    """Ban qilinganlar ro'yxati."""
    user_id = cq.from_user.id
    if not await is_admin(user_id):
        await cq.answer("❌ Siz admin emassiz!", show_alert=True)
        return
    page = int(cq.matches[0].group(1))
    await admin_bans_list_page(client, cq, page)


@Client.on_message(filters.private & filters.text & ~filters.command(["start", "menu"]), group=-3)
async def admin_text_handler(client: Client, message):
    """Admin panel uchun matnli kiritishlarni tutish."""
    user_id = message.from_user.id
    if not await is_admin(user_id):
        return

    st = _admin_states.get(user_id)
    text = (message.text or "").strip()

    if text.startswith("/"):
        _admin_states.pop(user_id, None)
        return

    if st == "WAIT_SEARCH_QUERY":
        _admin_states.pop(user_id, None)
        if not text:
            return
        results = await search_users(text, limit=20)
        if not results:
            await message.reply_text(
                f"🔍 Natijalar topilmadi: '{text}'",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]
                ]),
            )
            return
        lines = [f"🔍 **Qidiruv natijalari** ('{text}'):\n"]
        buttons = []
        for u in results:
            uid = u.get("user_id")
            lines.append(f"• {_user_label(u)}")
            ban_label = "🚫 Ban" if not await is_user_banned(uid) else "✅ Unban"
            ban_cb = f"admin_ban:{uid}" if not await is_user_banned(uid) else f"admin_unban:{uid}"
            buttons.append([InlineKeyboardButton(ban_label, callback_data=ban_cb)])
        buttons.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])
        await message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))

    elif st == "WAIT_BAN_ID":
        _admin_states.pop(user_id, None)
        if not text.isdigit():
            await message.reply_text("❌ Noto'g'ri format. Faqat raqam yuboring (masalan: `123456789`).")
            return
        target_id = int(text)
        if target_id == user_id:
            await message.reply_text("❌ O'zingizni ban qila olmaysiz!")
            return
        _admin_states[user_id] = f"WAIT_BAN_REASON:{target_id}"
        await message.reply_text(
            f"🚫 **Ban qilish tasdiqlash**\n\n"
            f"Maqsad: `{target_id}`\n\n"
            "Agar sabab bo'lsa, yozing (yoki 'tasdiqlash' deb yuboring):"
        )

    elif isinstance(st, str) and st.startswith("WAIT_BAN_REASON:"):
        target_id = int(st.split(":")[1])
        _admin_states.pop(user_id, None)
        reason = text if text and text.lower() != "tasdiqlash" else ""
        await ban_user(target_id, banned_by=user_id, reason=reason)
        await message.reply_text(
            f"🚫 `{target_id}` ban qilindi!"
            + (f"\nSabab: {reason}" if reason else ""),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]
            ]),
        )