"""
Majburiy kanal obunasi (force join) tizimi.

- Admin paneldan kanallar qo'shiladi/olib tashlanadi, xususiyat yoqiladi/o'chiriladi.
- /start da user kanal(lar)ga a'zo bo'lmasa — ulanish ekrani ko'rsatiladi.
- Sozlamalar (bot_settings):
    force_join_enabled — "1"/"0" (default: "0")
    force_channels     — JSON ro'yxat (kanal ID'lari: "-100...")
- Muhim: bot ushbu kanallarda a'zo bo'lishi kerak (aks holda kanal fail-open
  qilinadi — bot kira olmaydigan kanal userlarni bloklab qo'ymasligi uchun).
"""
import json
import logging
import re
import time

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, ChatAdminRequired, ChannelPrivate

from feature_flags import get_bot_setting, set_bot_setting
from config import is_admin, user_states

logger = logging.getLogger(__name__)


def _admin_cb_filter_fn(_, __, query):
    return bool(query.from_user and is_admin(query.from_user.id))


_admin_cb_filter = filters.create(_admin_cb_filter_fn)


# ------------------------- Sozlamalar -------------------------

async def is_force_join_enabled() -> bool:
    return (await get_bot_setting("force_join_enabled")) != "0"


async def get_force_channels() -> list:
    raw = await get_bot_setting("force_channels")
    try:
        data = json.loads(raw) if raw else []
        if isinstance(data, list):
            return [str(c) for c in data if str(c).strip()]
        return []
    except Exception:
        return []


async def set_force_channels(channels: list) -> bool:
    return await set_bot_setting("force_channels", json.dumps([str(c) for c in channels]))


# ------------------------- Kanal ma'lumotlari keshi -------------------------

_chat_info_cache = {}
_CHAT_INFO_TTL = 600.0


async def _get_chat_info(client: Client, channel_id: str):
    """{'id', 'title', 'url'} yoki None (bot kira olmasa). Kesh 10 daqiqa."""
    key = str(channel_id)
    now = time.time()
    cached = _chat_info_cache.get(key)
    if cached and now - cached[1] < _CHAT_INFO_TTL:
        return cached[0]
    try:
        chat = await client.get_chat(channel_id)
        if getattr(chat, "username", None):
            url = f"https://t.me/{chat.username}"
        else:
            url = getattr(chat, "invite_link", None) or ""
        info = {
            "id": chat.id,
            "title": chat.title or chat.username or key,
            "url": url,
        }
        _chat_info_cache[key] = (info, now)
        return info
    except Exception as e:
        logger.warning(f"force_join: kanal ma'lumoti olinmadi ({channel_id}): {e}")
        return None


# ------------------------- Tekshiruv -------------------------

async def check_user_joined(client: Client, user_id: int):
    """(True, []) — hammasiga a'zo; (False, missing) — a'zo bo'lmagan kanallar."""
    channels = await get_force_channels()
    if not channels:
        return True, []
    missing = []
    for ch in channels:
        try:
            await client.get_chat_member(ch, user_id)
        except UserNotParticipant:
            info = await _get_chat_info(client, ch)
            if info:
                missing.append(info)
        except (ChatAdminRequired, ChannelPrivate) as e:
            # fail-open: bot kira olmaydigan kanal userlarni bloklamasin
            logger.warning(f"force_join: kanal tekshirilmadi ({ch}): {e}")
            continue
        except Exception as e:
            logger.warning(f"force_join: tekshiruv xatosi ({ch}): {e}")
            continue
    return (len(missing) == 0), missing


def _build_screen(missing):
    lines = ["📢 **Botdan foydalanish uchun quyidagi kanal(lar)ga a'zo bo'ling:**\n"]
    buttons = []
    for m in missing:
        lines.append(f"• {m['title']}")
        if m.get("url"):
            buttons.append([InlineKeyboardButton(f"📢 {m['title']}", url=m["url"])])
    buttons.append([InlineKeyboardButton("✅ Tekshirish", callback_data="fj_check")])
    return "\n".join(lines), buttons


async def enforce_force_join(client: Client, message: Message) -> bool:
    """/start gate. True = o'tdi; False = ekrani ko'rsatildi (handler to'xtatsin)."""
    try:
        if not await is_force_join_enabled():
            return True
    except Exception:
        return True  # fail-open
    ok, missing = await check_user_joined(client, message.from_user.id)
    if ok:
        return True
    text, buttons = _build_screen(missing)
    try:
        await message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.warning(f"force_join: ekran yuborilmadi: {e}")
    return False


# ------------------------- User: tekshirish tugmasi -------------------------

@Client.on_callback_query(filters.regex("^fj_check$"))
async def fj_check_callback(client: Client, cq):
    uid = cq.from_user.id
    ok, missing = await check_user_joined(client, uid)
    if ok:
        try:
            await cq.message.edit_text("✅ **Rahmat!** Endi botdan to'liq foydalanishingiz mumkin.")
        except Exception:
            pass
        from plugins.menu import get_main_keyboard
        try:
            kb = await get_main_keyboard(uid)
            await cq.message.reply_text("🏠 **Bosh menyu**", reply_markup=kb)
        except Exception as e:
            logger.warning(f"force_join: menyu yuborilmadi: {e}")
        await cq.answer("✅ Tasdiqlandi!")
        return

    text, buttons = _build_screen(missing)
    try:
        await cq.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True,
        )
    except Exception:
        pass
    await cq.answer("❌ Hali ham a'zo bo'lmagansiz. Kanal(lar)ga qo'shilib qayta bosing.", show_alert=True)


# ------------------------- Admin: boshqaruv paneli -------------------------

async def _admin_perm_check(cq) -> bool:
    from config import can_manage_users
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return False
    return True


@Client.on_callback_query(filters.regex("^admin_force_join$") & _admin_cb_filter)
async def admin_force_join_callback(client: Client, cq):
    if not await _admin_perm_check(cq):
        return

    enabled = await is_force_join_enabled()
    channels = await get_force_channels()
    status_label = "🟢 Yoqilgan" if enabled else "🔴 O'chirilgan"

    lines = [
        "📢 **Majburiy kanal obunasi**\n",
        f"⚙️ Holati: {status_label}",
        f"📋 Kanallar: **{len(channels)}** ta\n",
    ]
    if channels:
        for i, ch in enumerate(channels, 1):
            info = await _get_chat_info(client, ch)
            title = info["title"] if info else ch
            lines.append(f"{i}. {title} (`{ch}`)")
        lines.append("")
    else:
        lines.append("📭 Hozircha kanal qo'shilmagan.\n")
    lines.append(
        "⚠️ Bot ushbu kanallarda a'zolarni tekshirish uchun kanalga "
        "qo'shilgan (admin) bo'lishi kerak."
    )

    buttons = [
        [InlineKeyboardButton(
            "🔴 O'chirish" if enabled else "🟢 Yoqish",
            callback_data="admin_fj_toggle",
        )],
        [InlineKeyboardButton("➕ Kanal qo'shish", callback_data="admin_fj_add")],
    ]
    for i, ch in enumerate(channels):
        info = await _get_chat_info(client, ch)
        title = info["title"] if info else ch
        buttons.append([InlineKeyboardButton(f"🗑 {title}", callback_data=f"admin_fj_del_{i}")])
    buttons.append([InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")])

    await cq.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
        disable_web_page_preview=True,
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^admin_fj_toggle$") & _admin_cb_filter)
async def admin_fj_toggle_callback(client: Client, cq):
    if not await _admin_perm_check(cq):
        return

    enabled = await is_force_join_enabled()
    channels = await get_force_channels()
    if not enabled and not channels:
        await cq.answer("❌ Avval kamida bitta kanal qo'shing!", show_alert=True)
        return
    if not await set_bot_setting("force_join_enabled", "0" if enabled else "1"):
        await cq.answer("❌ Sozlama saqlashda xatolik.", show_alert=True)
        return
    try:
        from database import log_admin_action
        await log_admin_action(cq.from_user.id, "force_join_toggle", None, f"enabled={not enabled}")
    except Exception:
        pass
    await cq.answer("✅ Majburiy obuna yoqildi" if not enabled else "🔴 Majburiy obuna o'chirildi")
    cq.data = "admin_force_join"
    await admin_force_join_callback(client, cq)


@Client.on_callback_query(filters.regex("^admin_fj_add$") & _admin_cb_filter)
async def admin_fj_add_callback(client: Client, cq):
    if not await _admin_perm_check(cq):
        return

    user_states[cq.from_user.id] = "admin_fj_add_channel"
    await cq.message.edit_text(
        "➕ **Kanal qo'shish**\n\n"
        "Quyidagilardan birini yuboring:\n"
        "• Kanal @username — `@my_channel`\n"
        "• Havola — `https://t.me/my_channel`\n"
        "• Kanal ID — `-1001234567890`\n"
        "• Yoki kanaldan xabarni **forward** qiling\n\n"
        "⚠️ Private kanal uchun forward yoki ID yuboring.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_force_join")
        ]])
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^admin_fj_del_(\d+)$") & _admin_cb_filter)
async def admin_fj_del_callback(client: Client, cq):
    if not await _admin_perm_check(cq):
        return

    idx = int(cq.matches[0].group(1))
    channels = await get_force_channels()
    if 0 <= idx < len(channels):
        removed = channels.pop(idx)
        await set_force_channels(channels)
        _chat_info_cache.pop(removed, None)
        try:
            from database import log_admin_action
            await log_admin_action(cq.from_user.id, "force_join_del_channel", None, removed)
        except Exception:
            pass
        await cq.answer("🗑 Kanal o'chirildi", show_alert=True)
    else:
        await cq.answer("❌ Kanal topilmadi", show_alert=True)
    cq.data = "admin_force_join"
    await admin_force_join_callback(client, cq)


async def handle_admin_add_channel_input(client: Client, message: Message):
    """Admin kanal qo'shish uchun yuborgan inputni qayta ishlaydi (state holati)."""
    uid = message.from_user.id
    raw = (message.text or "").strip()

    target = None
    if getattr(message, "forward_from_chat", None) and message.forward_from_chat.id:
        target = str(message.forward_from_chat.id)
    elif raw:
        m = re.match(r"^(?:https?://)?t\.me/(.+)$", raw, re.IGNORECASE)
        if m:
            name = m.group(1).strip("/")
            if name.startswith("+"):
                await message.reply_text(
                    "❌ **Private taklif havolasi** qo'llab-quvvatlanmaydi.\n\n"
                    "Private kanal uchun kanaldan xabar **forward** qiling yoki "
                    "kanal **ID**si (-100...) ni yuboring.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Orqaga", callback_data="admin_force_join")
                    ]])
                )
                return
            target = f"@{name}"
        elif raw.startswith("@"):
            target = raw
        elif re.match(r"^-?\d+$", raw):
            target = str(int(raw))
        else:
            target = f"@{raw.lstrip('@')}"

    if not target:
        await message.reply_text(
            "❌ Kanal aniqlanmadi. @username, havola, ID yoki forward yuboring.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Orqaga", callback_data="admin_force_join")
            ]])
        )
        return

    try:
        chat = await client.get_chat(target)
    except Exception as e:
        await message.reply_text(
            f"❌ **Kanal topilmadi yoki bot kira olmaydi.**\n\nXatolik: {e}\n\n"
            "Bot kanalga qo'shilganini tekshirib, qaytadan urinib ko'ring.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Orqaga", callback_data="admin_force_join")
            ]])
        )
        return

    channels = await get_force_channels()
    if str(chat.id) in channels:
        await message.reply_text(
            f"⚠️ **Bu kanal allaqachon qo'shilgan:** {chat.title or target}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Orqaga", callback_data="admin_force_join")
            ]])
        )
        return

    channels.append(str(chat.id))
    _chat_info_cache.pop(str(chat.id), None)
    if not await set_force_channels(channels):
        await message.reply_text(
            "❌ Sozlama saqlashda xatolik.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Orqaga", callback_data="admin_force_join")
            ]])
        )
        return

    # Bot kanalga a'zomi — bo'lmasa ogohlantirish
    warning = ""
    try:
        await client.get_chat_member(chat.id, "me")
    except (UserNotParticipant, ChatAdminRequired, ChannelPrivate):
        warning = (
            "\n⚠️ **Diqqat:** Bot hali kanal a'zosi (admini) emas — aks holda "
            "tekshiruv ishlamaydi. Botni kanalga admin qilib qo'shing."
        )
    except Exception:
        pass

    try:
        from database import log_admin_action
        await log_admin_action(uid, "force_join_add_channel", None, str(chat.id))
    except Exception:
        pass

    await message.reply_text(
        f"✅ **Kanal qo'shildi!**\n\n"
        f"📢 {chat.title or target}\n"
        f"🆔 `{chat.id}`{warning}\n\n"
        f"Jami kanallar: {len(channels)} ta. Majburiy obunani yoqishni unutmang!",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📢 Majburiy obuna sozlamalari", callback_data="admin_force_join")
        ]])
    )