"""
🎁 Giveaway / Konkurs — Guruhda avtomatik konkurs o'tkazish

Adminlar guruhda /giveaway buyrug'i orqali konkurs ochadi, a'zolar
"🎁 Ishtirok etish" tugmasini bosib qatnashadi va g'olib tasodifiy
aniqlanadi.

Buyruqlar:
  /giveaway [sovrin] [daqiqa]   — konkurs ochish (guruh admini / bot admini)
  /giveaway_end                 — g'olibni aniqlash va konkursni tugatish
  /giveaway_cancel              — konkursni bekor qilish

Tugmalar:
  🎁 Ishtirok etish              — qatnashish (hamma)
  🏁 G'olibni aniqlash           — tugatish (admin)
  ❌ Bekor qilish                — bekor qilish (admin)

Eslatma: holat xotirada saqlanadi (bot qayta ishga tushsa jonli konkursslar
yo'qoladi). Server doimiy ishlagani uchun bu v1 uchun yetarli.
"""
import asyncio
import logging
import random
import time

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import is_admin as is_bot_admin

logger = logging.getLogger(__name__)

# {(chat_id, message_id): giveaway} — jonli konkursslar
_giveaways = {}

# Guruh adminligini qayta tekshirmaslik uchun kesh
# {chat_id: {user_id: (is_admin_flag, timestamp)}}
_admin_cache = {}
_ADMIN_CACHE_TTL = 60


def _now() -> float:
    return time.time()


def _format_duration(seconds: float) -> str:
    """Sekundlarni o'qiladigan matnga aylantiradi (masalan: 2 soat 5 daqiqa)."""
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


def _participant_label(user_id: int, name: str, username: str) -> str:
    if username:
        return f"@{username}"
    if name:
        return f"[{name}](tg://user?id={user_id})"
    return f"`{user_id}`"


def _build_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎁 Ishtirok etish", callback_data="gw_join")],
        [
            InlineKeyboardButton("🏁 G'olibni aniqlash", callback_data="gw_end"),
            InlineKeyboardButton("❌ Bekor qilish", callback_data="gw_cancel"),
        ],
    ])


def _build_text(gw: dict) -> str:
    count = len(gw["participants"])
    lines = [
        "🎁 **GIVEAWAY / KONKURS**",
        "",
        f"🏆 **Sovrin:** {gw['prize']}",
        f"👥 **Ishtirokchilar:** {count} ta",
    ]
    if gw["ends_at"]:
        remaining = gw["ends_at"] - _now()
        if remaining > 0:
            lines.append(f"⏰ **Tugashiga:** {_format_duration(remaining)}")
        else:
            lines.append("⏰ **Tugash vaqti yetdi!**")
    else:
        lines.append("⏰ **Tugash:** admin aniqlaydi")
    lines += [
        "",
        "Ishtirok etish uchun quyidagi tugmani bosing 👇",
    ]
    return "\n".join(lines)


async def _is_group_admin(client: Client, chat_id: int, user_id: int) -> bool:
    """Guruh admini (owner yoki administrator) ekanligini kesh bilan tekshiradi."""
    now = _now()
    cache = _admin_cache.setdefault(chat_id, {})
    cached = cache.get(user_id)
    if cached:
        val, ts = cached
        if now - ts < _ADMIN_CACHE_TTL:
            return val
    try:
        member = await client.get_chat_member(chat_id, user_id)
        val = member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        val = False
    cache[user_id] = (val, now)
    return val


async def _is_authorized(client: Client, message: Message) -> bool:
    """Bot admini yoki guruh admini ekanligini tekshiradi."""
    user = message.from_user
    if not user:
        return False
    if is_bot_admin(user.id):
        return True
    # Anonim guruh adminlari (Telegram nomidan yozadi)
    if message.sender_chat and message.sender_chat.id == message.chat.id:
        return True
    if user.id == 1087968824:  # GroupAnonymousBot
        return True
    return await _is_group_admin(client, message.chat.id, user.id)


async def _is_authorized_cb(client: Client, cq: CallbackQuery) -> bool:
    """Callback query uchun admin tekshiruvi (bot admini yoki guruh admini)."""
    user = cq.from_user
    if not user:
        return False
    if is_bot_admin(user.id):
        return True
    return await _is_group_admin(client, cq.message.chat.id, user.id)


def _get_giveaway(chat_id: int, message_id: int):
    return _giveaways.get((chat_id, message_id))


def _find_active_in_chat(chat_id: int):
    for (cid, _mid), gw in list(_giveaways.items()):
        if cid == chat_id and gw["status"] == "active":
            return gw
    return None


async def _edit_message(client: Client, chat_id: int, message_id: int, text: str):
    try:
        await client.edit_message_text(chat_id, message_id, text)
    except Exception as e:
        logger.warning("[GIVEAWAY] Message edit failed chat=%s msg=%s: %s", chat_id, message_id, e)


async def _finish_giveaway(client: Client, gw: dict):
    """G'olibni aniqlaydi, e'lon qiladi va giveaway holatini yopadi."""
    if gw["status"] != "active":
        return
    gw["status"] = "ended"

    if gw.get("auto_end_task"):
        try:
            gw["auto_end_task"].cancel()
        except Exception:
            pass

    participants = list(gw["participants"].values())
    chat_id = gw["chat_id"]
    message_id = gw["message_id"]

    if not participants:
        text = (
            "🎁 **GIVEAWAY / KONKURS tugadi**\n\n"
            f"🏆 **Sovrin:** {gw['prize']}\n\n"
            "😔 Hech kim ishtirok etmadi, g'olib aniqlanmadi."
        )
        await _edit_message(client, chat_id, message_id, text)
        _giveaways.pop((chat_id, message_id), None)
        return

    winner = random.choice(participants)
    winner_label = _participant_label(
        winner["user_id"], winner.get("name", ""), winner.get("username", "")
    )
    text = (
        "🎉 **GIVEAWAY / KONKURS tugadi!**\n\n"
        f"🏆 **Sovrin:** {gw['prize']}\n"
        f"👥 **Ishtirokchilar:** {len(participants)} ta\n\n"
        f"🏆 **G'olib:** {winner_label}\n\n"
        "Tabriklaymiz! 🎊"
    )
    await _edit_message(client, chat_id, message_id, text)
    _giveaways.pop((chat_id, message_id), None)
    logger.info(
        "[GIVEAWAY] Finished chat=%s winner=%s participants=%d",
        chat_id, winner["user_id"], len(participants),
    )


async def _auto_end(client: Client, gw: dict):
    """Berilgan muddat tugagach g'olibni avtomatik aniqlaydi."""
    try:
        delay = gw["ends_at"] - _now()
        if delay > 0:
            await asyncio.sleep(delay)
        if gw["status"] != "active":
            return
        await _finish_giveaway(client, gw)
    except asyncio.CancelledError:
        return
    except Exception as e:
        logger.exception("[GIVEAWAY] Auto-end error: %s", e)


# ---------------------------------------------------------------------------
# Buyruqlar
# ---------------------------------------------------------------------------

@Client.on_message(filters.command(["giveaway", "konkurs"]) & filters.group)
async def giveaway_create(client: Client, message: Message):
    """/giveaway [sovrin] [daqiqa] — yangi konkurs ochish (faqat adminlar)."""
    if not await _is_authorized(client, message):
        await message.reply_text("❌ Faqat guruh admini konkurs ocha oladi")
        return

    if _find_active_in_chat(message.chat.id):
        await message.reply_text(
            "⚠️ Bu guruhda allaqachon faol konkurs bor!\n\n"
            "Avval uni tugating yoki bekor qiling: `/giveaway_end` yoki `/giveaway_cancel`"
        )
        return

    parts = message.text.split()
    prize = "🎁 Noma'lum sovrin"
    duration_min = None

    if len(parts) >= 2:
        # Oxirgi argument son bo'lsa — daqiqadagi muddat, aks holda sovrin matni.
        try:
            duration_min = int(parts[-1])
            rest = " ".join(parts[1:-1]).strip()
        except ValueError:
            duration_min = None
            rest = " ".join(parts[1:]).strip()
        if rest:
            prize = rest

    ends_at = None
    if duration_min and duration_min > 0:
        ends_at = _now() + duration_min * 60

    gw = {
        "chat_id": message.chat.id,
        "message_id": None,
        "prize": prize,
        "creator_id": message.from_user.id,
        "created_at": _now(),
        "ends_at": ends_at,
        "participants": {},
        "status": "active",
        "auto_end_task": None,
    }

    sent = await message.reply_text(_build_text(gw), reply_markup=_build_keyboard())
    gw["message_id"] = sent.id
    _giveaways[(message.chat.id, sent.id)] = gw

    if ends_at:
        gw["auto_end_task"] = asyncio.create_task(_auto_end(client, gw))
        logger.info(
            "[GIVEAWAY] Created chat=%s prize=%r ends_in=%ss",
            message.chat.id, prize, int(duration_min * 60),
        )
    else:
        logger.info("[GIVEAWAY] Created chat=%s prize=%r (manual end)", message.chat.id, prize)

    # Buyruq xabarini guruhdan tozalash (muvaffaqiyatsiz bo'lsa — e'tiborsiz)
    try:
        await message.delete()
    except Exception:
        pass


@Client.on_message(filters.command(["giveaway_end", "konkurs_end"]) & filters.group)
async def giveaway_end_cmd(client: Client, message: Message):
    """/giveaway_end — g'olibni aniqlash (faqat adminlar)."""
    if not await _is_authorized(client, message):
        await message.reply_text("❌ Faqat admin konkursni tugata oladi")
        return

    gw = _find_active_in_chat(message.chat.id)
    if not gw:
        await message.reply_text("⚠️ Bu guruhda faol konkurs yo'q")
        return

    await _finish_giveaway(client, gw)

    try:
        await message.delete()
    except Exception:
        pass


@Client.on_message(filters.command(["giveaway_cancel", "konkurs_cancel"]) & filters.group)
async def giveaway_cancel_cmd(client: Client, message: Message):
    """/giveaway_cancel — konkursni bekor qilish (faqat adminlar)."""
    if not await _is_authorized(client, message):
        await message.reply_text("❌ Faqat admin konkursni bekor qila oladi")
        return

    gw = _find_active_in_chat(message.chat.id)
    if not gw:
        await message.reply_text("⚠️ Bu guruhda faol konkurs yo'q")
        return

    if gw.get("auto_end_task"):
        try:
            gw["auto_end_task"].cancel()
        except Exception:
            pass

    gw["status"] = "cancelled"
    text = "❌ **GIVEAWAY / KONKURS bekor qilindi**\n\n" f"🏆 **Sovrin:** {gw['prize']}"
    await _edit_message(client, gw["chat_id"], gw["message_id"], text)
    _giveaways.pop((gw["chat_id"], gw["message_id"]), None)

    try:
        await message.delete()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Tugmalar
# ---------------------------------------------------------------------------

@Client.on_callback_query(filters.regex("^gw_join$"))
async def giveaway_join(client: Client, cq: CallbackQuery):
    """🎁 Ishtirok etish — foydalanuvchini ishtirokchilar ro'yxatiga qo'shadi."""
    gw = _get_giveaway(cq.message.chat.id, cq.message.id)
    if not gw or gw["status"] != "active":
        await cq.answer("❌ Bu konkurs tugagan", show_alert=True)
        return

    user = cq.from_user
    if not user:
        return

    uid = user.id
    if uid in gw["participants"]:
        await cq.answer("✅ Siz allaqachon ishtirok etyapsiz!")
        return

    gw["participants"][uid] = {
        "user_id": uid,
        "name": user.first_name or "",
        "username": user.username or "",
    }

    try:
        await cq.message.edit_text(_build_text(gw), reply_markup=_build_keyboard())
    except Exception:
        logger.debug("[GIVEAWAY] Count edit failed", exc_info=True)

    await cq.answer("✅ Ishtirok etdingiz! Omad! 🍀")


@Client.on_callback_query(filters.regex("^gw_end$"))
async def giveaway_end_cb(client: Client, cq: CallbackQuery):
    """🏁 G'olibni aniqlash — konkursni tugatadi (faqat adminlar)."""
    if not await _is_authorized_cb(client, cq):
        await cq.answer("❌ Faqat admin tugata oladi", show_alert=True)
        return

    gw = _get_giveaway(cq.message.chat.id, cq.message.id)
    if not gw or gw["status"] != "active":
        await cq.answer("❌ Bu konkurs tugagan", show_alert=True)
        return

    await _finish_giveaway(client, gw)
    await cq.answer("🏆 G'olib aniqlanmoqda...")


@Client.on_callback_query(filters.regex("^gw_cancel$"))
async def giveaway_cancel_cb(client: Client, cq: CallbackQuery):
    """❌ Bekor qilish — konkursni bekor qiladi (faqat adminlar)."""
    if not await _is_authorized_cb(client, cq):
        await cq.answer("❌ Faqat admin bekor qila oladi", show_alert=True)
        return

    gw = _get_giveaway(cq.message.chat.id, cq.message.id)
    if not gw or gw["status"] != "active":
        await cq.answer("❌ Bu konkurs tugagan", show_alert=True)
        return

    if gw.get("auto_end_task"):
        try:
            gw["auto_end_task"].cancel()
        except Exception:
            pass

    gw["status"] = "cancelled"
    text = "❌ **GIVEAWAY / KONKURS bekor qilindi**\n\n" f"🏆 **Sovrin:** {gw['prize']}"
    try:
        await cq.message.edit_text(text)
    except Exception:
        logger.debug("[GIVEAWAY] Cancel edit failed", exc_info=True)
    _giveaways.pop((cq.message.chat.id, cq.message.id), None)
    await cq.answer("❌ Konkurs bekor qilindi")