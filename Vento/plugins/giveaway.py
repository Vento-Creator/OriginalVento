"""
🎁 Giveaway / Konkurs — to'liq multi-bosqichli konkurs tizimi

Wizard (7 bosqich): konkurs nomi → konkurs matni → sovrin → ishtirokchilar
soni → boshlanish vaqti → tugash vaqti → turi (battle / oddiy).

Ikkita rejim:

  • 🥊 BATTLE — bot ulangan akkountdan "Vento Konkurs" kanalini ochadi va
    har bir ishtirokchini kanalga post qiladi. Reaksiya va kommentlar
    hisoblanadi (polling orqali):
        1 reaksiya = 1 ball
        1 komment  = 2 ball
        1 star     = 5 ball
    Bitta user bir necha komment yozsa ham 1 ta hisoblanadi (discussion thread);
    kanal nomidan (anonim admin) yozilgan kommentlar hisoblanmaydi.

  • 🎯 ODDIY — taklif/ovoz havolasi orqali. Bot kanal ochadi (yoki berilgan
    kanalni tozalab) va ishtirokchilar ro'yxatini tugmalar bilan post qiladi.
    Biror ishtirokchi tanlansa botga olib boradi, "ovoz berdingiz" deydi.
    Har kim 1 marta ovoz bera oladi, o'ziga o'zi ovoz berolmaydi.

Boshqaruv: ishtirokchi qo'shish, o'chirish, statistika, template, yakunlash, bekor.
Ma'lumotlar `data/giveaway_data.json` da saqlanadi (restartdan omon qoladi).
"""
import asyncio
import json
import logging
import os
import time
from datetime import datetime

from pyrogram import Client, filters, StopPropagation, ContinuePropagation
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import is_admin as is_bot_admin, DATA_DIR

logger = logging.getLogger(__name__)

DATA_FILE = os.path.join(DATA_DIR, "giveaway_data.json")
DEFAULT_CHANNEL_TITLE = "Vento Konkurs"
BATTLE_POLL_INTERVAL = 15
ADMIN_CACHE_TTL = 60

DEFAULT_TEMPLATE = (
    "**{n}-ishtirokchi**\n"
    "ism: {name}\n"
    "Omad tilaymiz"
)

_wizard = {}          # {user_id: draft}
_contests = {}        # {contest_id: contest}
_poll_tasks = {}      # {contest_id: asyncio.Task}
_admin_cache = {}     # {chat_id: {user_id: (is_admin, ts)}}
_bot_username = None
_PENDING_ADD = {}
_PENDING_TMPL = {}
_PENDING_CHANNEL = {}
_PENDING_DEL = {}


def _now() -> float:
    return time.time()


def _save() -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_contests, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_FILE)
    except Exception as e:
        logger.warning("[GIVEAWAY] Saqlashda xatolik: %s", e)


def _load() -> None:
    global _contests
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                _contests = loaded
    except Exception as e:
        logger.warning("[GIVEAWAY] Yuklashda xatolik: %s", e)


_load()


def _next_id() -> int:
    if not _contests:
        return 1
    return max(int(k) for k in _contests.keys()) + 1


def _get_contest(cid):
    return _contests.get(str(cid))


def _find_active_by_creator(creator_id: int):
    for c in _contests.values():
        if c.get("creator_id") == creator_id and c.get("status") == "active":
            return c
    return None


def _format_time(ts) -> str:
    if not ts:
        return "—"
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "—"


def _parse_time(text: str):
    t = (text or "").strip().lower()
    if not t:
        return None
    if t in ("now", "hozir", "endi"):
        return _now()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(t, fmt).timestamp()
        except ValueError:
            continue
    return None


def _format_duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds} soniya"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        tail = f" {secs} soniya" if secs else ""
        return f"{minutes} daqiqa{tail}"
    hours, mins = divmod(minutes, 60)
    tail = f" {mins} daqiqa" if mins else ""
    return f"{hours} soat{tail}"


def _participant_label(p: dict) -> str:
    if p.get("username"):
        return f"@{p['username']}"
    if p.get("name"):
        if p.get("user_id"):
            return f"[{p['name']}](tg://user?id={p['user_id']})"
        return p["name"]
    return f"`{p['user_id']}`" if p.get("user_id") else "?"


async def _get_bot_username(client: Client) -> str:
    global _bot_username
    if _bot_username:
        return _bot_username
    try:
        me = client.me or await client.get_me()
        _bot_username = me.username or "empire_family_bot"
    except Exception:
        _bot_username = "empire_family_bot"
    return _bot_username


async def _can_manage_giveaway(uid: int) -> tuple[bool, str]:
    """Foydalanuvchi konkurs o'tkaza oladimi va sessiya ulanganmi?"""
    if is_bot_admin(uid):
        from session_manager import has_active_sessions
        if not has_active_sessions(uid):
            return False, (
                "❌ **Akkount belgilanmagan!**\n\n"
                "Konkurs yaratish va kanalda postlarni joylash uchun "
                "botga Telegram akkauntingiz ulangan bo'lishi kerak.\n"
                "Iltimos, **👤 Akkaunt** bo'limidan kiring."
            )
        return True, ""

    try:
        from plugins.menu import _has_session, _has_access
        sess = _has_session(uid)
        acc = await _has_access(uid)
    except Exception:
        from session_manager import has_active_sessions
        sess = has_active_sessions(uid)
        acc = True

    if not sess:
        return False, (
            "❌ **Akkount belgilanmagan!**\n\n"
            "Konkurs yaratish uchun Vento botiga Telegram akkauntingiz ulangan bo'lishi kerak.\n"
            "Iltimos, **👤 Akkaunt** bo'limiga o'tib, akkauntni ulang."
        )

    if not acc:
        return False, "❌ Sizda faol obuna mavjud emas. Obuna sotib oling."

    return True, ""


def _build_panel_keyboard(cid) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Ishtirokchi qo'shish", callback_data=f"gw_add_{cid}")],
        [
            InlineKeyboardButton("📊 Statistika", callback_data=f"gw_stats_{cid}"),
            InlineKeyboardButton("🗑 Ishtirokchi o'chirish", callback_data=f"gw_del_{cid}"),
        ],
        [InlineKeyboardButton("✏️ Ishtirokchi matni", callback_data=f"gw_tmpl_{cid}")],
        [InlineKeyboardButton("🔗 Kanal ulash (oddiy)", callback_data=f"gw_channel_{cid}")],
        [
            InlineKeyboardButton("🏁 Yakunlash", callback_data=f"gw_end_{cid}"),
            InlineKeyboardButton("❌ Bekor qilish", callback_data=f"gw_cancel_{cid}"),
        ],
    ])


def _build_contest_card(c: dict) -> str:
    ctype = "🥊 Battle" if c["ctype"] == "battle" else "🎯 Oddiy"
    p = list(c.get("participants", {}).values())
    lines = [
        "🎁 **KONKURS**",
        "",
        f"📛 **Nomi:** {c['name']}",
        f"🏆 **Sovrin:** {c['prize']}",
        f"🧩 **Turi:** {ctype}",
        f"👥 **Ishtirokchilar:** {len(p)}/{c['max_participants'] or '♾ cheksiz'}",
        f"🕐 **Boshlanishi:** {_format_time(c['start_at'])}",
        f"⏰ **Tugashi:** {_format_time(c['end_at']) or '— (admin)'}",
    ]
    if c.get("channel_link"):
        lines.append(f"📢 **Kanal:** {c['channel_link']}")
    lines.append(f"📊 **Holat:** {c['status']}")
    return "\n".join(lines)


def _render_template(template: str, n: int, name: str, username: str, uid) -> str:
    display = f"@{username}" if username else (name or str(uid or "?"))
    tmpl = template or DEFAULT_TEMPLATE
    res = tmpl.replace("{n}", str(n))
    res = res.replace("{name}", display)
    res = res.replace("{username}", f"@{username}" if username else "")
    res = res.replace("{user_id}", str(uid or ""))
    return res


WIZARD_STEPS = {
    1: "📛 **Konkurs nomini yozing:**",
    2: "📝 **Konkurs matnini yozing** (premium emoji qo'llab-quvvatlanadi).\n\nBo'sh qoldirish uchun: `/skip`",
    3: "🏆 **Sovrinni yozing** (premium emoji va havolalar qo'llab-quvvatlanadi):",
    4: "👥 **Nechta odam qatnashishi mumkin?**\n\nRaqam yozing yoki cheksiz uchun: `/skip`",
    5: "🕐 **Qachon boshlanadi?**\n\nFormat: `YYYY-MM-DD HH:MM` — hozir boshlash uchun: `/skip`",
    6: "⏰ **Qachon tugaydi?**\n\nFormat: `YYYY-MM-DD HH:MM` — admin o'zi yakunlashi uchun: `/skip`",
    7: "🧩 **Konkurs turini tanlang:**",
}


def _send_wizard_step(client: Client, uid: int, draft: dict):
    if draft["step"] > 7:
        asyncio.create_task(_show_wizard_summary(client, uid, draft))
        return

    if draft["step"] == 7:
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🥊 Battle (Reaksiya/Komment)", callback_data="gw_wiz_type_battle"),
                InlineKeyboardButton("🎯 Oddiy (Ovoz berish)", callback_data="gw_wiz_type_oddiy"),
            ],
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="gw_wizard_cancel")],
        ])
    else:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Bekor qilish", callback_data="gw_wizard_cancel"),
        ]])
    asyncio.create_task(_send_private(client, uid, WIZARD_STEPS[draft["step"]], kb))


async def _send_private(client: Client, uid: int, text: str, kb=None):
    try:
        await client.send_message(uid, text, reply_markup=kb)
    except Exception as e:
        logger.warning("[GIVEAWAY] Shaxsiyga yuborilmadi %s: %s", uid, e)


async def _show_wizard_summary(client: Client, uid: int, draft: dict):
    ctype = "🥊 Battle" if draft["ctype"] == "battle" else "🎯 Oddiy"
    text = (
        "📋 **Konkurs xulosasi**\n\n"
        f"📛 **Nomi:** {draft['name']}\n"
        f"📝 **Matn:** {draft['description'] or '—'}\n"
        f"🏆 **Sovrin:** {draft['prize']}\n"
        f"👥 **Ishtirokchilar:** {draft['max_participants'] or '♾ cheksiz'}\n"
        f"🕐 **Boshlanishi:** {_format_time(draft['start_at'])}\n"
        f"⏰ **Tugashi:** {_format_time(draft['end_at']) or '— (admin)'}\n"
        f"🧩 **Turi:** {ctype}\n\n"
        "Tasdiqlaysizmi?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Tasdiqlash", callback_data="gw_wizard_confirm")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="gw_wizard_cancel")],
    ])
    await client.send_message(uid, text, reply_markup=kb)


@Client.on_callback_query(filters.regex("^gw_wizard_cancel$"))
async def wizard_cancel_cb(client: Client, cq: CallbackQuery):
    _wizard.pop(cq.from_user.id, None)
    await cq.message.edit_text("❌ Konkurs yaratish bekor qilindi.")
    await cq.answer()


@Client.on_callback_query(filters.regex("^gw_wiz_type_(battle|oddiy)$"))
async def wizard_type_cb(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    draft = _wizard.get(uid)
    if not draft or draft.get("step") != 7:
        await cq.answer()
        return
    ctype = cq.matches[0].group(1)
    draft["ctype"] = ctype
    draft["step"] += 1
    _wizard[uid] = draft
    await cq.answer()
    await _show_wizard_summary(client, uid, draft)


@Client.on_callback_query(filters.regex("^gw_wizard_confirm$"))
async def wizard_confirm_cb(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    draft = _wizard.pop(uid, None)
    if not draft or not draft.get("name") or not draft.get("prize"):
        await cq.answer("❌ Ma'lumotlar to'liq emas", show_alert=True)
        return

    cid = _next_id()
    c = {
        "id": cid,
        "chat_id": draft["chat_id"],
        "creator_id": draft["creator_id"],
        "name": draft["name"],
        "description": draft.get("description", ""),
        "prize": draft["prize"],
        "max_participants": draft.get("max_participants"),
        "start_at": draft.get("start_at"),
        "end_at": draft.get("end_at"),
        "ctype": draft["ctype"],
        "status": "active",
        "channel_id": None,
        "channel_title": None,
        "channel_link": None,
        "template": DEFAULT_TEMPLATE,
        "participants": {},
        "list_message_id": None,
        "voters": [],
        "created_at": _now(),
    }
    _contests[str(cid)] = c
    _save()

    await cq.message.edit_text(
        "🎁 **Konkurs yaratildi!**\n\n" + _build_contest_card(c),
        reply_markup=_build_panel_keyboard(cid),
    )
    await cq.answer("✅ Konkurs yaratildi")
    logger.info("[GIVEAWAY] Contest #%s created by %s (type=%s)", cid, uid, c["ctype"])


@Client.on_message(filters.private & filters.text, group=-6)
async def wizard_text_handler(client: Client, message: Message):
    uid = message.from_user.id
    draft = _wizard.get(uid)
    if not draft:
        raise ContinuePropagation

    text = (message.text or "").strip()

    if text.startswith("/") and text.lower() not in ("/skip", "/otkazish", "otkazib yuborish"):
        _wizard.pop(uid, None)
        raise ContinuePropagation

    if text.lower() in ("/skip", "/otkazish", "otkazib yuborish"):
        _wizard_skip(client, message, draft)
        raise StopPropagation

    step = draft["step"]
    err = None

    if step == 1:
        if len(text) > 200:
            err = "Nomi juda uzun (maks 200 belgi). Qayta yozing:"
        else:
            draft["name"] = text
    elif step == 2:
        draft["description"] = text
    elif step == 3:
        draft["prize"] = text
    elif step == 4:
        if text.lower() in ("cheksiz", "0", "nol"):
            draft["max_participants"] = None
        else:
            try:
                n = int(text)
                if n <= 0:
                    err = "Ijobiy son yoki /skip yozing:"
                else:
                    draft["max_participants"] = n
            except ValueError:
                err = "Raqam yozing yoki cheksiz uchun /skip:"
    elif step == 5:
        ts = _parse_time(text)
        if ts is None:
            err = "Format noto'g'ri. `YYYY-MM-DD HH:MM` yoki /skip:"
        else:
            draft["start_at"] = ts
    elif step == 6:
        ts = _parse_time(text)
        if ts is None:
            err = "Format noto'g'ri. `YYYY-MM-DD HH:MM` yoki /skip:"
        else:
            draft["end_at"] = ts
    elif step == 7:
        low = text.lower()
        if low in ("battle", "batl", "🥊"):
            draft["ctype"] = "battle"
        elif low in ("oddiy", "normal", "🎯"):
            draft["ctype"] = "oddiy"
        else:
            err = "Iltimos, tugmalardan birini tanlang (battle yoki oddiy):"
    else:
        raise ContinuePropagation

    if err:
        await message.reply_text(err)
        raise StopPropagation

    draft["step"] += 1
    _wizard[uid] = draft
    _send_wizard_step(client, uid, draft)
    raise StopPropagation


def _wizard_skip(client: Client, message: Message, draft: dict):
    step = draft["step"]
    if step == 2:
        draft["description"] = ""
    elif step == 4:
        draft["max_participants"] = None
    elif step == 5:
        draft["start_at"] = _now()
    elif step == 6:
        draft["end_at"] = None
    draft["step"] += 1
    _wizard[message.from_user.id] = draft
    _send_wizard_step(client, message.from_user.id, draft)


@Client.on_message(filters.private & (filters.command("giveaway") | filters.regex("^🎁 Konkurs$")))
async def giveaway_private_cmd(client: Client, message: Message):
    uid = message.from_user.id
    can, reason = await _can_manage_giveaway(uid)
    if not can:
        await message.reply_text(reason)
        return

    active = _find_active_by_creator(uid)
    if active:
        cid = active["id"]
        text = (
            "⚠️ Sizda allaqachon **faol konkurs bor**:\n\n"
            f"📛 **{active['name']}**\n"
            f"🏆 {active['prize']}\n"
            f"🧩 {active['ctype']} | 📊 {len(active.get('participants', {}))} ishtirokchi\n"
        )
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("📜 Boshqaruv paneli", callback_data=f"gw_panel_{cid}"),
                    InlineKeyboardButton("❌ Bekor qilish", callback_data=f"gw_cancel_{cid}"),
                ],
                [InlineKeyboardButton("➕ Yangi konkurs yaratish", callback_data="gw_new")],
            ]
        )
        await message.reply_text(text, reply_markup=kb)
        return

    _wizard[uid] = {
        "creator_id": uid,
        "chat_id": message.chat.id,
        "name": None,
        "description": "",
        "prize": None,
        "max_participants": None,
        "start_at": None,
        "end_at": None,
        "ctype": None,
        "step": 1,
        "created": _now(),
    }
    _send_wizard_step(client, uid, _wizard[uid])


@Client.on_callback_query(filters.regex("^gw_new$"))
async def gw_new_cb(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    _wizard[uid] = {
        "creator_id": uid,
        "chat_id": cq.message.chat.id,
        "name": None,
        "description": "",
        "prize": None,
        "max_participants": None,
        "start_at": None,
        "end_at": None,
        "ctype": None,
        "step": 1,
        "created": _now(),
    }
    await cq.message.edit_text("🎁 **Yangi konkurs yaratish**")
    _send_wizard_step(client, uid, _wizard[uid])
    await cq.answer()


@Client.on_message(filters.command("giveaway") & filters.group)
async def giveaway_group_cmd(client: Client, message: Message):
    bot_username = await _get_bot_username(client)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎁 Konkurs yaratish", url=f"https://t.me/{bot_username}?start=giveaway")],
    ])
    await message.reply_text(
        "🎁 **Konkurs yaratish**\n\n"
        "Konkurs yaratish va boshqarish uchun botga o'ting hamda /giveaway buyrug'ini yuboring.",
        reply_markup=kb,
    )

# ---------------------------------------------------------------------------
# Kanal yaratish / tozalash / ulash
# ---------------------------------------------------------------------------

async def _ensure_channel(c: dict):
    """Kanal yo'q bo'lsa, user akkountdan 'Vento Konkurs' nomli kanal ochadi."""
    if c.get("channel_id"):
        return c["channel_id"], c.get("channel_link")

    from session_manager import get_user_client
    uc = await get_user_client(c["creator_id"])

    try:
        chat = await uc.create_channel(
            DEFAULT_CHANNEL_TITLE,
            about=f"🎁 Konkurs: {c['name']}",
        )
        c["channel_id"] = chat.id
        c["channel_title"] = chat.title
        try:
            link = await uc.export_chat_invite_link(chat.id)
            c["channel_link"] = link
        except Exception:
            c["channel_link"] = f"https://t.me/c/{str(chat.id).replace('-100', '')}"
        _save()
        logger.info("[GIVEAWAY] Kanal yaratildi #%s -> %s", c["id"], chat.id)
        return chat.id, c["channel_link"]
    except Exception as e:
        logger.exception("[GIVEAWAY] Kanal yaratishda xatolik: %s", e)
        err_str = str(e).upper()
        if "CHANNELS_ADMIN" in err_str or "LIMIT" in err_str or "TOO_MUCH" in err_str:
            raise ValueError(
                "Akkauntingizda Telegram kanallari ochish **limiti tugagan!**\n\n"
                "💡 **Nima qilish kerak:** Boshqaruv panelidan **'🔗 Kanal ulash'** tugmasini bosing va "
                "oldin ochilgan kanalingiz linkini yuborib ulang."
            )
        raise ValueError(f"Kanal yaratib bo'lmadi: {e}")


async def _clear_channel(uc, channel_id: int):
    try:
        ids = []
        async for m in uc.get_chat_history(channel_id, limit=200):
            ids.append(m.id)
        if ids:
            await uc.delete_messages(channel_id, ids)
    except Exception as e:
        logger.warning("[GIVEAWAY] Kanal tozalashda xatolik: %s", e)


async def _use_existing_channel(c: dict, link_or_username: str):
    """Oddiy konkurs uchun oldin ochilgan kanalni ulaydi va tozalaydi."""
    from session_manager import get_user_client
    uc = await get_user_client(c["creator_id"])
    target = (link_or_username or "").strip()
    if target.startswith("https://t.me/+"):
        chat = await uc.join_chat(target)
    elif target.startswith("https://t.me/") or target.startswith("@"):
        uname = target.rstrip("/").split("/")[-1].lstrip("@")
        chat = await uc.get_chat(uname)
    else:
        chat = await uc.get_chat(target)
    c["channel_id"] = chat.id
    c["channel_title"] = chat.title
    c["channel_link"] = target
    await _clear_channel(uc, chat.id)
    _save()
    return chat.id, target


async def _post_battle_participant(uc, c: dict, seq: int, p: dict):
    """Battle: ishtirokchiga kanalda alohida post (ball shu post uchun hisoblanadi)."""
    text = _render_template(
        c.get("template", DEFAULT_TEMPLATE), seq, p.get("name"), p.get("username"), p.get("user_id")
    )
    total = p.get("points", 0)
    text += f"\n\n📊 **Jami: {total} ball**"
    msg = await uc.send_message(c["channel_id"], text)
    p["message_id"] = msg.id
    _save()
    return msg.id


async def _build_odd_list_text(c: dict) -> str:
    lines = [
        "🎯 **KONKURS — ODDIY (ovoz/taklif)**",
        "",
        f"📛 **{c['name']}**",
        f"🏆 **Sovrin:** {c['prize']}",
        "",
        "Ishtirokchilar (ovoz berish uchun tugmani bosing):",
    ]
    for seq, p in c.get("participants", {}).items():
        votes = p.get("votes", 0)
        lines.append(f"{seq}. {_participant_label(p)} — {votes} ovoz")
    return "\n".join(lines)


async def _refresh_odd_list(uc, c: dict, bot_username: str = None):
    """Oddiy: kanaldagi ro'yxatni tugmalar bilan yangilaydi."""
    global _bot_username
    if not bot_username:
        bot_username = _bot_username or "empire_family_bot"
    buttons = []
    for seq, p in c.get("participants", {}).items():
        payload = f"vt_{c['id']}_{seq}"
        buttons.append([InlineKeyboardButton(
            _participant_label(p),
            url=f"https://t.me/{bot_username}?start={payload}",
        )])
    kb = InlineKeyboardMarkup(buttons)
    text = await _build_odd_list_text(c)
    if c.get("list_message_id"):
        try:
            await uc.edit_message_text(c["channel_id"], c["list_message_id"], text, reply_markup=kb)
            return c["list_message_id"]
        except Exception:
            pass
    msg = await uc.send_message(c["channel_id"], text, reply_markup=kb)
    c["list_message_id"] = msg.id
    _save()
    return msg.id


async def _resolve_user(uc, ref: str):
    """Username / link / id ni user akkount orqali hal qiladi: (User, None) yoki (None, error)."""
    ref = (ref or "").strip()
    if not ref:
        return None, "Bo'sh qiymat"
    if ref.startswith("https://t.me/") or ref.startswith("t.me/"):
        ref = ref.rstrip("/").split("/")[-1].lstrip("@")
    else:
        ref = ref.lstrip("@")

    try:
        if ref.isdigit():
            user = await uc.get_users(int(ref))
        else:
            user = await uc.get_users(ref)
        return user, None
    except Exception as e:
        return None, f"Foydalanuvchi topilmadi: {e}"


async def _add_participant(c: dict, user, bot_username: str = None) -> dict:
    """Ishtirokchi qo'shadi va kanalga post tashlaydi."""
    from session_manager import get_user_client
    uc = await get_user_client(c["creator_id"])

    maxp = c.get("max_participants")
    if maxp and len(c.get("participants", {})) >= maxp:
        raise ValueError(f"Limitga yetdi ({maxp} ta)")

    seq = len(c.get("participants", {})) + 1
    p = {
        "user_id": getattr(user, "id", None),
        "username": getattr(user, "username", None) or "",
        "name": getattr(user, "first_name", None) or getattr(user, "title", None) or "",
        "message_id": None,
        "points": 0,
        "reactions": 0,
        "comments": 0,
        "stars": 0,
        "votes": 0,
        "added": _now(),
    }
    c.setdefault("participants", {})[str(seq)] = p

    if not c.get("channel_id"):
        await _ensure_channel(c)

    if c["ctype"] == "battle":
        await _post_battle_participant(uc, c, seq, p)
        _start_battle_polling(c)
    else:
        await _refresh_odd_list(uc, c, bot_username)

    _save()
    return p

# ---------------------------------------------------------------------------
# Ishtirokchi qo'shish / o'chirish / template oqimlari
# ---------------------------------------------------------------------------

@Client.on_message(filters.private & (filters.text | filters.forwarded), group=-5)
async def gw_add_text_handler(client: Client, message: Message):
    """Ishtirokchi qo'shish, o'chirish, template va kanal ulash text handleri."""
    uid = message.from_user.id

    # 1) Ishtirokchi qo'shish
    cid = _PENDING_ADD.get(uid)
    if cid:
        c = _get_contest(cid)
        if not c:
            _PENDING_ADD.pop(uid, None)
            raise ContinuePropagation

        user = None
        err = None

        if message.forward_from:
            user = message.forward_from
        elif message.forward_from_chat:
            err = "Kanal yoki guruhdan forward qilingan. Foydalanuvchining o'zidan forward qiling yoki username yozing."
        elif message.text:
            txt = message.text.strip()
            if txt.startswith("/") and txt.lower() in ("/cancel", "/bekor"):
                _PENDING_ADD.pop(uid, None)
                await message.reply_text("❌ Ishtirokchi qo'shish bekor qilindi.")
                raise StopPropagation
            user, err = await _resolve_user_from_private(client, c, txt)

        if err:
            await message.reply_text(f"❌ {err}\n\nQayta yuboring yoki /cancel bosing.")
            raise StopPropagation
        if not user:
            await message.reply_text("❌ Foydalanuvchi ma'lumotlari olinmadi.")
            raise StopPropagation

        # Duplicate tekshiruvi
        if any(p.get("user_id") == user.id for p in c.get("participants", {}).values() if p.get("user_id")):
            await message.reply_text("❌ Bu foydalanuvchi allaqachon **ishtirokchilar ro'yxatida bor**!")
            raise StopPropagation

        try:
            bot_username = await _get_bot_username(client)
            p = await _add_participant(c, user, bot_username)
        except ValueError as e:
            await message.reply_text(f"❌ {e}")
            raise StopPropagation
        except Exception as e:
            await message.reply_text(f"❌ Xatolik: {e}")
            raise StopPropagation

        seq = len(c["participants"])
        await message.reply_text(
            f"✅ **{seq}-ishtirokchi qo'shildi:**\n"
            f"ism: {_participant_label(p)}\n"
            f"Omad tilaymiz! 🎉\n\nKanalga joylandi."
        )
        _PENDING_ADD.pop(uid, None)
        raise StopPropagation

    # 2) Ishtirokchini o'chirish
    cid = _PENDING_DEL.get(uid)
    if cid:
        c = _get_contest(cid)
        if not c:
            _PENDING_DEL.pop(uid, None)
            raise ContinuePropagation
        txt = (message.text or "").strip()
        if txt.startswith("/") and txt.lower() in ("/cancel", "/bekor"):
            _PENDING_DEL.pop(uid, None)
            await message.reply_text("❌ O'chirish bekor qilindi.")
            raise StopPropagation
        if txt.isdigit() and str(int(txt)) in c.get("participants", {}):
            seq_str = str(int(txt))
            removed = c["participants"].pop(seq_str)
            _save()
            _PENDING_DEL.pop(uid, None)
            await message.reply_text(f"✅ **{seq_str}-ishtirokchi ({_participant_label(removed)}) o'chirildi.**")
            raise StopPropagation
        else:
            await message.reply_text("❌ Bunday raqamli ishtirokchi topilmadi. Qayta yuboring yoki /cancel bosing.")
            raise StopPropagation

    # 3) Template o'zgartirish
    cid = _PENDING_TMPL.get(uid)
    if cid:
        c = _get_contest(cid)
        if not c:
            _PENDING_TMPL.pop(uid, None)
            raise ContinuePropagation
        c["template"] = message.text
        _save()
        _PENDING_TMPL.pop(uid, None)
        await message.reply_text(
            "✅ **Ishtirokchi matni yangilandi.**\n\n"
            "Placeholderlar: `{n}`, `{name}`"
        )
        raise StopPropagation

    # 4) Kanal ulash
    cid = _PENDING_CHANNEL.get(uid)
    if cid:
        c = _get_contest(cid)
        if not c:
            _PENDING_CHANNEL.pop(uid, None)
            raise ContinuePropagation
        try:
            await _use_existing_channel(c, message.text)
        except Exception as e:
            await message.reply_text(f"❌ Kanal ulanmadi: {e}")
            raise StopPropagation
        _PENDING_CHANNEL.pop(uid, None)
        await message.reply_text(
            "✅ **Kanal ulandi va tozalandi.**\n\n"
            "Endi ishtirokchilarni qo'shishingiz mumkin."
        )
        raise StopPropagation

    raise ContinuePropagation


async def _resolve_user_from_private(client: Client, c: dict, ref: str):
    from session_manager import get_user_client
    try:
        uc = await get_user_client(c["creator_id"])
    except Exception as e:
        return None, f"User akkount ulanishda xatolik: {e}"
    return await _resolve_user(uc, ref)


@Client.on_callback_query(filters.regex("^gw_add_(\\d+)$"))
async def gw_add_cb(client: Client, cq: CallbackQuery):
    cid = cq.matches[0].group(1)
    c = _get_contest(cid)
    if not c:
        await cq.answer("❌ Konkurs topilmadi", show_alert=True)
        return
    if c["status"] != "active":
        await cq.answer("❌ Konkurs faol emas", show_alert=True)
        return
    _PENDING_ADD[cq.from_user.id] = cid
    await cq.message.edit_text(
        "➕ **Ishtirokchi qo'shish**\n\n"
        "Foydalanuvchining **username / ID** sini yuboring yoki uning **xabarini botga forward qiling**:\n"
        "Masalan: `@username` yoki `123456789`",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Bekor qilish", callback_data=f"gw_panel_{cid}")
        ]]),
    )
    await cq.answer("Ishtirokchi ma'lumotlarini yuboring")


@Client.on_callback_query(filters.regex("^gw_del_(\\d+)$"))
async def gw_del_cb(client: Client, cq: CallbackQuery):
    cid = cq.matches[0].group(1)
    c = _get_contest(cid)
    if not c:
        await cq.answer("❌ Konkurs topilmadi", show_alert=True)
        return
    if not c.get("participants"):
        await cq.answer("❌ Ishtirokchilar yo'q", show_alert=True)
        return
    _PENDING_DEL[cq.from_user.id] = cid
    await cq.message.edit_text(
        "🗑 **Ishtirokchini o'chirish**\n\n"
        "O'chirmoqchi bo'lgan ishtirokchining **tartib raqamini (1, 2, ...)** yuboring:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Bekor qilish", callback_data=f"gw_panel_{cid}")
        ]]),
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^gw_panel_(\\d+)$"))
async def gw_panel_cb(client: Client, cq: CallbackQuery):
    cid = cq.matches[0].group(1)
    c = _get_contest(cid)
    if not c:
        await cq.answer("❌", show_alert=True)
        return
    _PENDING_ADD.pop(cq.from_user.id, None)
    _PENDING_TMPL.pop(cq.from_user.id, None)
    _PENDING_CHANNEL.pop(cq.from_user.id, None)
    _PENDING_DEL.pop(cq.from_user.id, None)
    await cq.message.edit_text(
        "🎁 **Konkurs boshqaruvi**\n\n" + _build_contest_card(c),
        reply_markup=_build_panel_keyboard(cid),
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^gw_stats_(\\d+)$"))
async def gw_stats_cb(client: Client, cq: CallbackQuery):
    cid = cq.matches[0].group(1)
    c = _get_contest(cid)
    if not c:
        await cq.answer("❌", show_alert=True)
        return
    parts = list(c.get("participants", {}).items())
    if not parts:
        await cq.answer("Hali ishtirokchi yo'q", show_alert=True)
        return
    if c["ctype"] == "battle":
        parts.sort(key=lambda kv: kv[1].get("points", 0), reverse=True)
        lines = ["📊 **BATTLE statistika:**", ""]
        for seq, p in parts:
            lines.append(
                f"{seq}. {_participant_label(p)} — {p.get('points', 0)} ball"
                f" (👍{p.get('reactions', 0)} 💬{p.get('comments', 0)} ⭐{p.get('stars', 0)})"
            )
    else:
        parts.sort(key=lambda kv: kv[1].get("votes", 0), reverse=True)
        lines = ["📊 **ODDIY statistika:**", ""]
        for seq, p in parts:
            lines.append(f"{seq}. {_participant_label(p)} — {p.get('votes', 0)} ovoz")
    await cq.answer("\n".join(lines[:25]), show_alert=True)


@Client.on_callback_query(filters.regex("^gw_tmpl_(\\d+)$"))
async def gw_tmpl_cb(client: Client, cq: CallbackQuery):
    cid = cq.matches[0].group(1)
    c = _get_contest(cid)
    if not c:
        await cq.answer("❌", show_alert=True)
        return
    _PENDING_TMPL[cq.from_user.id] = cid
    await cq.message.edit_text(
        "✏️ **Ishtirokchi posti uchun matn**\n\n"
        "Placeholderlar:\n"
        "`{n}` — tartib raqami\n"
        "`{name}` — ism/username\n\n"
        "Joriy matn:\n"
        f"```\n{c.get('template', DEFAULT_TEMPLATE)}\n```\n\n"
        "Yangi matnni yuboring:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Bekor qilish", callback_data=f"gw_panel_{cid}")
        ]]),
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^gw_channel_(\\d+)$"))
async def gw_channel_cb(client: Client, cq: CallbackQuery):
    cid = cq.matches[0].group(1)
    c = _get_contest(cid)
    if not c:
        await cq.answer("❌", show_alert=True)
        return
    _PENDING_CHANNEL[cq.from_user.id] = cid
    await cq.message.edit_text(
        "🔗 **Kanal ulash (oddiy konkurs)**\n\n"
        "Oldin ochilgan kanalning linki yoki username sini yuboring.\n"
        "Bot uni tozalab, yangi konkurs uchun ishlatadi.\n\n"
        "Masalan: `https://t.me/mychannel` yoki `@mychannel`",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Bekor qilish", callback_data=f"gw_panel_{cid}")
        ]]),
    )
    await cq.answer()


async def _finish_contest(c: dict):
    """Konkursni yakunlaydi: g'olibni aniqlaydi va holatni yopadi."""
    if c.get("status") == "ended":
        return None

    task = _poll_tasks.pop(str(c["id"]), None)
    if task:
        try:
            task.cancel()
        except Exception:
            pass

    parts = list(c.get("participants", {}).items())
    if not parts:
        winner = None
    elif c["ctype"] == "battle":
        parts.sort(key=lambda kv: kv[1].get("points", 0), reverse=True)
        winner = parts[0][1]
    else:
        parts.sort(key=lambda kv: kv[1].get("votes", 0), reverse=True)
        winner = parts[0][1]

    c["status"] = "ended"
    _save()
    return winner


@Client.on_callback_query(filters.regex("^gw_end_(\\d+)$"))
async def gw_end_cb(client: Client, cq: CallbackQuery):
    cid = cq.matches[0].group(1)
    c = _get_contest(cid)
    if not c:
        await cq.answer("❌", show_alert=True)
        return
    if c["status"] != "active":
        await cq.answer("❌ Konkurs faol emas", show_alert=True)
        return
    winner = await _finish_contest(c)
    await _publish_final_results(client, cq.message, c, winner)
    await cq.answer("🏁 Yakunlandi")


async def _publish_final_results(client: Client, orig_msg, c: dict, winner: dict | None):
    """Konkurs yakunlandi, natijalar ro'yxati kanalga + panelga xabar sifatida."""
    parts = list(c.get("participants", {}).items())
    key = "points" if c["ctype"] == "battle" else "votes"
    parts.sort(key=lambda kv: kv[1].get(key, 0), reverse=True)

    header = (
        "🎉 **KONKURS YAKUNLANDI!**\n"
        f"📛 **{c['name']}**\n"
        f"🏆 **Sovrin:** {c['prize']}\n\n"
    )

    if not parts:
        result_lines: list[str] = ["🚫 Ishtirokchi bo'lmadi."]
    else:
        result_lines = []
        for i, (seq, p) in enumerate(parts, start=1):
            sc = p.get(key, 0)
            result_lines.append(f"{i}. {_participant_label(p)} — {sc} ball/ovoz")

    if winner:
        score = winner.get(key, 0)
        panel_text = (
            header
            + f"🏆 **G'olib:** {_participant_label(winner)}\n"
            + f"📊 **Natija:** {score} ball/ovoz\n\n"
        )
    else:
        panel_text = header + "🚫 G'olib topilmadi.\n\n"
    panel_text += "\n".join(result_lines)

    if orig_msg:
        try:
            await orig_msg.edit_text(panel_text)
        except Exception:
            pass

    if c.get("channel_id"):
        from session_manager import get_user_client
        try:
            uc = await get_user_client(c["creator_id"])
        except Exception:
            uc = None
        if uc:
            await _send_split_messages(uc, c["channel_id"], header, result_lines, panel_text)


async def _send_split_messages(client: Client, chat_id, header: str, lines: list[str], full: str):
    chunks: list[str] = []
    cur = header
    for line in lines:
        candidate = f"{cur}\n{line}" if cur else line
        if len(candidate) > 1950:
            chunks.append(cur)
            cur = line
        else:
            cur = candidate
    if cur:
        chunks.append(cur)
    for ch in chunks:
        try:
            await client.send_message(chat_id, ch)
        except Exception as e:
            logger.warning("[GIVEAWAY] Natija yuborishda xatolik chat_id=%s: %s", chat_id, e)


@Client.on_callback_query(filters.regex("^gw_cancel_(\\d+)$"))
async def gw_cancel_cb(client: Client, cq: CallbackQuery):
    cid = cq.matches[0].group(1)
    c = _get_contest(cid)
    if not c:
        await cq.answer("❌", show_alert=True)
        return
    task = _poll_tasks.pop(str(cid), None)
    if task:
        try:
            task.cancel()
        except Exception:
            pass
    c["status"] = "cancelled"
    _save()
    await cq.message.edit_text(f"❌ **Konkurs bekor qilindi**\n\n{c['name']}")
    await cq.answer("❌ Bekor qilindi")


# ---------------------------------------------------------------------------
# BATTLE — polling orqali reaksiya/komment ballarini hisoblash
# ---------------------------------------------------------------------------

def _start_battle_polling(c: dict):
    cid = str(c["id"])
    if cid in _poll_tasks:
        return
    _poll_tasks[cid] = asyncio.create_task(_battle_poll_loop(c))


def _reaction_counts(message):
    emoji = stars = 0
    reactions = getattr(message, "reactions", None)
    if reactions is None:
        return emoji, stars
    for r in getattr(reactions, "reactions", []) or []:
        cnt = getattr(r, "count", 0) or 0
        rtype = str(getattr(r, "type", ""))
        if "STAR" in rtype.upper() or "PAID" in rtype.upper():
            stars += cnt
        else:
            emoji += cnt
    return emoji, stars


async def _count_comments(uc, channel_id: int, message_id: int, me_id: int) -> int:
    """Ishtirokchi postiga yozilgan UNIKAL kommenterlar soni (discussion replies orqali)."""
    unique = set()
    try:
        async for m in uc.get_discussion_replies(channel_id, message_id):
            if m.sender_chat is not None:
                continue
            if m.from_user is None or getattr(m.from_user, "is_bot", False):
                continue
            if me_id and m.from_user.id == me_id:
                continue
            unique.add(m.from_user.id)
    except Exception as e:
        logger.debug("[GIVEAWAY] komment hisoblashda xatolik #%s/%s: %s", channel_id, message_id, e)
    return len(unique)


async def _battle_poll_tick(c: dict):
    if c["status"] != "active":
        return
    if c.get("start_at") and _now() < c["start_at"]:
        return

    from session_manager import get_user_client
    try:
        uc = await get_user_client(c["creator_id"])
        me = await uc.get_me()
    except Exception:
        return

    me_id = me.id if me else None
    changed = False

    for seq, p in list(c.get("participants", {}).items()):
        mid = p.get("message_id")
        if not mid:
            continue
        emoji, stars = p.get("reactions", 0), p.get("stars", 0)
        try:
            msg = await uc.get_messages(c["channel_id"], mid)
            emoji, stars = _reaction_counts(msg)
        except Exception:
            pass
        comments = await _count_comments(uc, c["channel_id"], mid, me_id)
        points = emoji + 2 * comments + 5 * stars
        if (emoji, stars, comments, points) != (
            p.get("reactions", 0),
            p.get("stars", 0),
            p.get("comments", 0),
            p.get("points", 0),
        ):
            p["reactions"] = emoji
            p["stars"] = stars
            p["comments"] = comments
            p["points"] = points
            changed = True

            # Post matnini kanalda yangilash
            try:
                new_text = _render_template(
                    c.get("template", DEFAULT_TEMPLATE),
                    int(seq),
                    p.get("name"),
                    p.get("username"),
                    p.get("user_id"),
                )
                new_text += f"\n\n📊 **Jami: {points} ball**"
                await uc.edit_message_text(c["channel_id"], mid, new_text)
            except Exception as e:
                logger.debug("[GIVEAWAY] Post tahrirlanmadi msg_id=%s: %s", mid, e)

    if changed:
        _save()


async def _battle_poll_loop(c: dict):
    cid = str(c["id"])
    try:
        while True:
            try:
                await _battle_poll_tick(c)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.debug("[GIVEAWAY] poll tick xatosi: %s", e)
            if c["status"] != "active":
                break
            await asyncio.sleep(BATTLE_POLL_INTERVAL)
    except asyncio.CancelledError:
        pass
    finally:
        _poll_tasks.pop(cid, None)

# ---------------------------------------------------------------------------
# ODDIY — ovoz berish (taklif havolasi orqali)
# ---------------------------------------------------------------------------

@Client.on_message(filters.command("start") & filters.private, group=-2)
async def giveaway_payload_start(client: Client, message: Message):
    """/start payload — 'giveaway' (wizard) va 'vt_...' (ovoz) ni ishlaydi."""
    parts = (message.text or "").split()
    if len(parts) < 2:
        raise ContinuePropagation
    payload = parts[1]

    if payload == "giveaway":
        await giveaway_private_cmd(client, message)
        raise StopPropagation

    if payload.startswith("vt_"):
        try:
            _, _cid, _seq = payload.split("_", 2)
            await _process_vote(client, message, _cid, int(_seq))
        except (ValueError, IndexError):
            await message.reply_text("❌ Havola noto'g'ri.")
        raise StopPropagation

    raise ContinuePropagation


async def _process_vote(client: Client, message: Message, contest_id, seq: int):
    """ODDIY konkursda ovoz berish."""

    async def _reply(text):
        try:
            await message.reply_text(text)
        except Exception:
            pass

    c = _get_contest(contest_id)
    if not c:
        await _reply("❌ Konkurs topilmadi.")
        return
    if c["ctype"] != "oddiy":
        await _reply("❌ Bu konkurs ovozli emas.")
        return
    if c["status"] != "active":
        await _reply(f"❌ Konkurs holati: **{c['status']}**.")
        return

    now = _now()
    if c.get("start_at") and now < c["start_at"]:
        await _reply("⏳ Konkurs hali **boshlanmagan**.")
        return
    if c.get("end_at") and now > c["end_at"]:
        await _reply("⏰ Konkurs **tugagan**.")
        return

    voter_id = message.from_user.id
    target = c.get("participants", {}).get(str(seq))
    if not target:
        await _reply("❌ Bunday ishtirokchi topilmadi.")
        return

    if target.get("user_id") and target["user_id"] == voter_id:
        await _reply("❌ Siz **o'zingizga** ovoz bera olmaysiz!")
        return

    voters = c.setdefault("voters", [])
    if voter_id in voters:
        await _reply(
            "⚠️ Siz **allaqachon** ovoz bergansiz.\n\n"
            "Ovozni o'zgartirish mumkin emas!"
        )
        return

    voters.append(voter_id)
    target["votes"] = (target.get("votes") or 0) + 1
    _save()

    try:
        from session_manager import get_user_client
        uc = await get_user_client(c["creator_id"])
        bot_username = await _get_bot_username(client)
        await _refresh_odd_list(uc, c, bot_username)
    except Exception as e:
        logger.debug("[GIVEAWAY] Ro'yxat yangilanmadi: %s", e)

    await _reply(
        f"✅ **Ovoz berdingiz!**\n\n"
        f"Uchun: **{_participant_label(target)}**\n"
        f"Jami ovozlar: **{target['votes']}** ta"
    )
    logger.info("[GIVEAWAY] Vote #%s user=%s -> participant=%s", contest_id, voter_id, seq)


# ---------------------------------------------------------------------------
# Bot qayta ishga tushganda va avto-yakunlash taymerlari
# ---------------------------------------------------------------------------

async def _resume_polling_on_startup():
    await asyncio.sleep(5)
    for c in _contests.values():
        if (
            c.get("ctype") == "battle"
            and c.get("status") == "active"
            and c.get("channel_id")
        ):
            _start_battle_polling(c)
            logger.info("[GIVEAWAY] Restart: battle #%s polling qayta boshlandi", c.get("id"))


async def _auto_end_monitor_loop():
    """Vaqti tugagan active konkurslarni avtomatik yakunlaydi."""
    await asyncio.sleep(10)
    while True:
        try:
            now = _now()
            for cid, c in list(_contests.items()):
                if c.get("status") == "active" and c.get("end_at") and now >= c["end_at"]:
                    logger.info("[GIVEAWAY] Auto-ending contest #%s (end_at reached)", cid)
                    winner = await _finish_contest(c)
                    try:
                        from config import bot_client
                        app_cli = bot_client
                        if app_cli:
                            header = f"⏰ **{c['name']}** konkursi tugash vaqti yetgani sababli avtomatik yakunlandi!"
                            parts = list(c.get("participants", {}).items())
                            key = "points" if c["ctype"] == "battle" else "votes"
                            parts.sort(key=lambda kv: kv[1].get(key, 0), reverse=True)
                            res_lines = [f"{i}. {_participant_label(p)} — {p.get(key, 0)}" for i, (seq, p) in enumerate(parts, 1)]
                            if winner:
                                p_text = header + f"\n\n🏆 **G'olib:** {_participant_label(winner)}\n\n" + "\n".join(res_lines)
                            else:
                                p_text = header + "\n\n🚫 G'olib aniqlanmadi.\n\n" + "\n".join(res_lines)
                            await app_cli.send_message(c["creator_id"], p_text)
                            if c.get("channel_id"):
                                from session_manager import get_user_client
                                uc = await get_user_client(c["creator_id"])
                                if uc:
                                    await _send_split_messages(uc, c["channel_id"], header, res_lines, p_text)
                    except Exception as ex:
                        logger.warning("[GIVEAWAY] Auto-end notify failed for #%s: %s", cid, ex)
        except Exception as e:
            logger.error("[GIVEAWAY] Auto-end monitor error: %s", e)
        await asyncio.sleep(30)


try:
    asyncio.get_event_loop().call_later(
        5, lambda: asyncio.ensure_future(_resume_polling_on_startup())
    )
    asyncio.get_event_loop().call_later(
        10, lambda: asyncio.ensure_future(_auto_end_monitor_loop())
    )
except Exception:
    logger.debug("[GIVEAWAY] Startup tasks scheduled via event loop fallback")