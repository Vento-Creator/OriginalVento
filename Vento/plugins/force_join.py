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

# Tekshiruv amalga oshmaganida (bot kanalga kira olmasa) userlarga ko'rsatiladigan aloqa
ADMIN_CONTACT = "@Nova_OS_Builder_Admin"


async def is_force_join_enabled() -> bool:
    return (await get_bot_setting("force_join_enabled")) != "0"


async def get_force_channels() -> list:
    """[{'id': '-100...', 'name': 'Custom nom'|''}, ...]

    Eski format (oddiy string ro'yxat) ham avtomatik normalize qilinadi.
    name bo'sh bo'lsa — kanalning haqiqiy nomi ishlatiladi.
    """
    raw = await get_bot_setting("force_channels")
    try:
        data = json.loads(raw) if raw else []
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    result = []
    for c in data:
        if isinstance(c, dict) and str(c.get("id", "")).strip():
            result.append({
                "id": str(c["id"]),
                "name": str(c.get("name") or "").strip(),
                "ref": str(c.get("ref") or "").strip(),
            })
        elif str(c).strip():
            result.append({"id": str(c), "name": "", "ref": ""})
    return result


async def set_force_channels(channels: list) -> bool:
    cleaned = [
        {
            "id": str(c["id"]),
            "name": str(c.get("name") or "").strip(),
            "ref": str(c.get("ref") or "").strip(),
        }
        for c in channels
        if str(c.get("id", "")).strip()
    ]
    return await set_bot_setting("force_channels", json.dumps(cleaned))


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
    """('ok', [], '') — hammasiga a'zo; ('join', missing, '') — a'zo bo'lish kerak;
    ('error', [], reason) — tekshiruv amalga oshmadi.

    PEER_ID_INVALID muammosiga qarshi: avval ref (@username) orqali peer'ni
    warm-up qilamiz, keyin get_chat_member'ni qayta urinamiz."""
    channels = await get_force_channels()
    if not channels:
        return "ok", [], ""
    missing = []
    for ch in channels:
        cid = ch["id"]
        ref = (ch.get("ref") or "").strip()
        probe = ref or cid
        is_member = False
        user_missing = False
        try:
            await client.get_chat_member(cid, user_id)
            is_member = True
        except UserNotParticipant:
            user_missing = True
        except Exception as first_err:
            # Peer cache warm-up: @username/ref orqali resolve, keyin retry.
            # Retry-da @username ishlatamiz (IDdan ko'ra ishonchli).
            try:
                chat = await client.get_chat(probe)
            except Exception as warm_err:
                logger.warning(
                    f"force_join: kanal aniqlanmadi ({cid}, probe={probe}): {warm_err}"
                )
                return "error", [], "bot_not_in_channel"
            retry_id = f"@{chat.username}" if getattr(chat, "username", None) else chat.id
            try:
                await client.get_chat_member(retry_id, user_id)
                is_member = True
            except UserNotParticipant:
                user_missing = True
            except Exception as retry_err:
                logger.warning(
                    f"force_join: retry xato ({cid}, retry_id={retry_id}): {retry_err} | "
                    f"birinchi: {first_err}"
                )
                return "error", [], "bot_not_in_channel"

        if is_member:
            continue

        # User a'zo emas — missing ro'yxatga qo'shamiz (maxsus nom ustuvor)
        info = await _get_chat_info(client, probe)
        if info:
            title = ch["name"] or info["title"]
            missing.append({"id": info["id"], "title": title, "url": info["url"]})
        elif ref.startswith("@"):
            missing.append({
                "id": cid,
                "title": ch["name"] or ref,
                "url": f"https://t.me/{ref.lstrip('@')}",
            })
        else:
            # kanal ma'lumoti olinmadi, lekin a'zolik holati aniq — baribir ko'rsatamiz
            missing.append({"id": cid, "title": ch["name"] or cid, "url": ""})
    return "ok", missing, ""


def _build_screen(missing):
    lines = ["📢 **Botdan foydalanish uchun quyidagi kanal(lar)ga a'zo bo'ling:**\n"]
    buttons = []
    for m in missing:
        lines.append(f"• {m['title']}")
        if m.get("url"):
            buttons.append([InlineKeyboardButton(f"📢 {m['title']}", url=m["url"])])
    buttons.append([InlineKeyboardButton("✅ Tekshirish", callback_data="fj_check")])
    return "\n".join(lines), buttons


def _error_screen_for(user_id: int):
    """Tekshiruv amalga oshmadi — admin va oddiy userga turli xabar."""
    try:
        admin = is_admin(user_id)
    except Exception:
        admin = False
    if admin:
        text = (
            "⚠️ **Bot kanalga hali qo'shilmagan!**\n\n"
            "Tekshirilayotgan kanal(lar)ga bot a'zo emas, shuning uchun obuna "
            "tekshirilolmayapti.\n\n"
            "🔧 **Yechim:** Kanalni oching → Botni **admin** sifatida qo'shing → "
            "shundan so'ng ✅ Tekshirish tugmasini bosing."
        )
    else:
        text = f"❌ **Xatolik!** Admin bilan bog'laning: {ADMIN_CONTACT}"
    return text


async def enforce_force_join(client: Client, message: Message) -> bool:
    """/start gate. True = o'tdi; False = ekrani ko'rsatildi (handler to'xtatsin)."""
    try:
        if not await is_force_join_enabled():
            return True
    except Exception:
        return True  # fail-open
    status, missing, reason = await check_user_joined(client, message.from_user.id)
    if status == "ok":
        return True
    if status == "error":
        text = _error_screen_for(message.from_user.id)
        buttons = None
        logger.warning(f"force_join: tekshiruv amalga oshmadi (reason={reason})")
    else:
        text, buttons = _build_screen(missing)
    try:
        if buttons is None:
            await message.reply_text(text)
        else:
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
    status, missing, reason = await check_user_joined(client, uid)
    if status == "error":
        try:
            await cq.message.edit_text(_error_screen_for(uid))
        except Exception:
            pass
        if reason == "bot_not_in_channel":
            try:
                admin = is_admin(uid)
            except Exception:
                admin = False
            if admin:
                await cq.answer(
                    "⚠️ Bot kanalga qo'shilmagan. Botni kanalga admin qilib qo'shing.",
                    show_alert=True,
                )
            else:
                await cq.answer("❌ Tekshiruvda xatolik. Admin bilan bog'laning.", show_alert=True)
        else:
            await cq.answer("❌ Tekshiruvda xatolik. Admin bilan bog'laning.", show_alert=True)
        return
    if status == "ok":
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

    # Bekor qilingan qo'shish oqimlarini tozalash
    user_states.pop(cq.from_user.id, None)

    enabled = await is_force_join_enabled()
    channels = await get_force_channels()
    status_label = "🟢 Yoqilgan" if enabled else "🔴 O'chirilgan"

    # Bot identity — qaysi akkaunt tekshiruvni bajarishi aniq ko'rinsin
    bot_line = ""
    try:
        me = await client.get_me()
        if me:
            bot_label = f"@{me.username}" if me.username else str(me.id)
            bot_line = f"\n🤖 Tekshiruvchi bot: {bot_label} (`{me.id}`)\n"
    except Exception as e:
        logger.warning(f"force_join: get_me xato: {e}")

    lines = [
        "📢 **Majburiy kanal obunasi**\n",
        f"⚙️ Holati: {status_label}",
        f"📋 Kanallar: **{len(channels)}** ta",
        bot_line,
    ]
    if channels:
        for i, ch in enumerate(channels, 1):
            info = await _get_chat_info(client, ch["id"])
            title = ch["name"] or (info["title"] if info else ch["id"])
            lines.append(f"{i}. {title} (`{ch['id']}`)")
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
        [
            InlineKeyboardButton("➕ Kanal qo'shish", callback_data="admin_fj_add"),
            InlineKeyboardButton("🔍 Diagnostika", callback_data="admin_fj_diag"),
        ],
    ]
    for i, ch in enumerate(channels):
        info = await _get_chat_info(client, ch["id"])
        title = ch["name"] or (info["title"] if info else ch["id"])
        buttons.append([InlineKeyboardButton(f"🗑 {title}", callback_data=f"admin_fj_del_{i}")])
    buttons.append([InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")])

    await cq.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
        disable_web_page_preview=True,
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^admin_fj_diag$") & _admin_cb_filter)
async def admin_fj_diag_callback(client: Client, cq):
    """Har bir kanal bo'yicha aniq diagnostika: get_chat, bot a'zoligi, user a'zoligi."""
    if not await _admin_perm_check(cq):
        return

    channels = await get_force_channels()
    lines = ["🔍 **Majburiy obuna diagnostikasi**\n"]
    if not channels:
        lines.append("📭 Kanallar qo'shilmagan.")
    else:
        for ch in channels:
            cid = ch["id"]
            ref = (ch.get("ref") or "").strip()
            probe = ref or cid
            lines.append(f"📌 Kanal: `{cid}`  (resolve: `{probe}`)")

            # 1) get_chat — bot kanalni umuman topa oladimi
            try:
                chat = await client.get_chat(probe)
                tname = f"@{chat.username}" if getattr(chat, "username", None) else "username yo'q"
                lines.append(f"  ✅ get_chat: {chat.title or cid} ({tname})")
            except Exception as e:
                lines.append(f"  ❌ get_chat: **{type(e).__name__}**: {e}")
                lines.append("")
                continue

            # 2) Botning o'zi a'zomi (eng muhimi)
            try:
                m = await client.get_chat_member(chat.id, "me")
                st = getattr(m, "status", "?")
                lines.append(f"  ✅ Bot a'zoligi: `{st}`")
            except UserNotParticipant:
                lines.append("  ❌ **Bot kanalga a'zo EMAS!**")
            except Exception as e:
                lines.append(f"  ❌ Bot a'zoligi: **{type(e).__name__}**: {e}")

            # 3) Siz (admin) a'zomi
            try:
                await client.get_chat_member(chat.id, cq.from_user.id)
                lines.append("  ✅ Siz a'zosiz")
            except UserNotParticipant:
                lines.append("  ❌ Siz a'zo emassiz")
            except Exception as e:
                lines.append(f"  ⚠️ Sizni tekshirish: {type(e).__name__}: {e}")
            lines.append("")

    lines.append("💡 Bot 'a'zo emas' deyapti bo'lsa — WEB logdagi bot akkauntini "
                 "kanalga admin qilib qo'shing.")
    buttons = [[InlineKeyboardButton("🔙 Orqaga", callback_data="admin_force_join")]]

    await cq.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))
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
    if any(c["id"] == str(chat.id) for c in channels):
        await message.reply_text(
            f"⚠️ **Bu kanal allaqachon qo'shilgan:** {chat.title or target}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Orqaga", callback_data="admin_force_join")
            ]])
        )
        return

    # 2-bosqich: maxsus nom so'rash (userlarga shu nom ko'rinadi)
    user_states[uid] = f"admin_fj_add_name|{target}|{chat.id}|{chat.title or target}"
    await message.reply_text(
        f"✅ **Kanal topildi:** {chat.title or target}\n\n"
        "✏️ Endi kanal uchun **maxsus nom** yuboring — aynan shu nom "
        "foydalanuvchilarga inline tugmada ko'rinadi.\n\n"
        "Haqiqiy kanal nomini ishlatish uchun `skip` deb yozing.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_force_join")
        ]])
    )


async def handle_admin_add_name_input(client: Client, message: Message):
    """Kanal qo'shishning 2-bosqichi: maxsus nomni qabul qilish."""
    uid = message.from_user.id
    state = user_states.get(uid)
    if not isinstance(state, str) or not state.startswith("admin_fj_add_name|"):
        user_states.pop(uid, None)
        return
    parts = state.split("|", 3)
    ref = parts[1] if len(parts) > 1 else ""          # asl input (@username/ID)
    channel_id = parts[2] if len(parts) > 2 else ""
    channel_title = parts[3] if len(parts) > 3 else ""
    user_states.pop(uid, None)

    if not channel_id:
        await message.reply_text(
            "❌ Kanal ma'lumoti yo'qolgan. Qaytadan qo'shing.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Orqaga", callback_data="admin_force_join")
            ]])
        )
        return

    raw = (message.text or "").strip()

    def _retry_prompt(text_hint):
        user_states[uid] = state  # holatni saqlab qo'yamiz
        return text_hint

    if not raw:
        await message.reply_text(_retry_prompt(
            "❌ Nom bo'sh bo'lishi mumkin emas. Nom yuboring yoki `skip` yozing."
        ))
        return
    if len(raw) > 64:
        await message.reply_text(_retry_prompt(
            "❌ Nom juda uzun (maks. 64 belgi). Qaytadan yuboring yoki `skip` yozing."
        ))
        return

    name = "" if raw.lower() == "skip" else raw

    channels = await get_force_channels()
    if any(c["id"] == channel_id for c in channels):
        await message.reply_text(
            "⚠️ **Bu kanal allaqachon qo'shilgan.**",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Orqaga", callback_data="admin_force_join")
            ]])
        )
        return

    channels.append({"id": channel_id, "name": name, "ref": ref})
    _chat_info_cache.pop(channel_id, None)
    if not await set_force_channels(channels):
        await message.reply_text(
            "❌ Sozlama saqlashda xatolik.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Orqaga", callback_data="admin_force_join")
            ]])
        )
        return

    # Bot kanalga a'zomi — bo'lmasa ogohlantirish (har qanday xatoda)
    warning = ""
    try:
        await client.get_chat_member(channel_id, "me")
    except Exception:
        warning = (
            "\n⚠️ **Diqqat:** Bot kanalga hali qo'shilmagan yoki kira olmaydi — "
            "bu holda obuna tekshiruvi ishlamaydi. Botni kanalga **admin** "
            "sifatida qo'shing, aks holda userlar xatolik xabarini ko'radi."
        )

    try:
        from database import log_admin_action
        await log_admin_action(uid, "force_join_add_channel", None, channel_id)
    except Exception:
        pass

    display = name or channel_title
    await message.reply_text(
        f"✅ **Kanal qo'shildi!**\n\n"
        f"📢 Nom: {display}\n"
        f"🆔 `{channel_id}`{warning}\n\n"
        f"Jami kanallar: {len(channels)} ta. Majburiy obunani yoqishni unutmang!",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📢 Majburiy obuna sozlamalari", callback_data="admin_force_join")
        ]])
    )