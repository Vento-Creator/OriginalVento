"""
🏆 XP / Level Tizimi — Guruh faolligiga qarab a'zolarga XP, level va reyting berish.

Xususiyatlar:
  • Har bir guruh xabari uchun foydalanuvchiga XP beriladi (cooldown bilan anti-spam).
  • Reply qilib '+' yuborilganda:
      - Reply qilingan xabar mazmundorligi va faktual belgilar ("shuning uchun", "demak", "chunki" va h.k.) tekshiriladi.
      - Reply qilingan foydalanuvchiga +2 XP beriladi.
      - '+' bosgan foydalanuvchiga +1 XP beriladi.
      - Bir foydalanuvchi ikkinchisiga har 5 daqiqada faqat 1 marta '+' bera oladi (dinamik cooldown).
  • Avto-Level Up bildirishnomasi:
      - Bot orqali shaxsiy xabarda (PM) batafsil statistika yuboriladi.
      - Agar shaxsiy chatdan yozish imkoni bo'lmasa (bot bloklangan bo'lsa), guruhdagi xabarga maxsus ogohlantirish qo'shib ketiladi:
        "Siz bilan shaxsiy chatda bog'lana olmadik, iltimos botga ulaning va botni bloklamang!"
  • /rank, /level, /xp — o'zining yoki belgilan a'zoning darajasi va statistikasi.
  • /top, /leaderboard — guruhning Top-10 faol a'zolari reytingi.
  • /xpsettings — adminlar uchun guruh sozlamalarini boshqarish.
  • /addxp, /removexp, /setlevel — guruh adminlari tomonidan XP/darajani qo'lda sozlash.
"""

import asyncio
from datetime import datetime
import logging
import math
import random
import time
from typing import Dict, Optional, Tuple

from pyrogram import Client, filters, ContinuePropagation
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from database import get_db_connection
from config import can_manage_xp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Kesh va O'zgaruvchilar
# ---------------------------------------------------------------------------

_cooldown_cache: Dict[Tuple, float] = {}   # Cooldown keshi
_settings_cache: Dict[int, dict] = {}       # chat_id -> settings dict
_tables_initialized = False
_db_lock = asyncio.Lock()

DEFAULT_COOLDOWN = 45  # soniya
DEFAULT_XP_PER_MSG = 10
LEVELUP_ANNOUNCE_DEFAULT = True
XP_ENABLED_DEFAULT = True

# Mazmundorlik va Faktual so'zlar ro'yxati
QUALITY_KEYWORDS = [
    "shuning uchun", "demak", "chunki", "sababi", "aslida", "masalan",
    "muhim", "fakt", "maslahat", "manba", "xulosa", "javob", "fikrimcha",
    "vaziyat", "sababli", "natijada", "haqida", "to'g'ri", "to'g'risida",
    "bo'yicha", "tavsiya", "yechim", "tushuntirish", "asosiysi", "xususan"
]

# Unvonlar ro'yxati: (Min Level, Unvon Nomi, Emoji)
TITLES = [
    (1, "Havaskor", "🥉"),
    (5, "Faol a'zo", "🥈"),
    (10, "Ekspert", "🥇"),
    (15, "Master", "💎"),
    (20, "Afsona", "👑"),
    (30, "Legend", "⚡️"),
    (50, "Geroy", "🌌"),
]

def get_title_info(level: int) -> Tuple[str, str]:
    """Level ga mos unvon nomi va emojisini qaytaradi."""
    title_name = "Havaskor"
    emoji = "🥉"
    for min_lvl, name, em in TITLES:
        if level >= min_lvl:
            title_name = name
            emoji = em
        else:
            break
    return title_name, emoji


def get_next_title_name(level: int) -> str:
    """Keyingi unvon nomini qaytaradi."""
    for min_lvl, name, _ in TITLES:
        if min_lvl > level:
            return name
    return "Geroy"


def calculate_level(xp: int) -> int:
    """XP bo'yicha Level aniqlash.
    Formula: Required XP for Level L = 50 * L * (L + 1)
    """
    if xp <= 0:
        return 1
    val = (-1.0 + math.sqrt(1.0 + 0.08 * xp)) / 2.0
    level = int(math.floor(val)) + 1
    return max(1, level)


def xp_for_level(level: int) -> int:
    """Berilgan darajaga erishish uchun jami kerakli XP"""
    if level <= 1:
        return 0
    lvl = level - 1
    return 50 * lvl * (lvl + 1)


def make_progress_bar(current: int, total: int, length: int = 5) -> str:
    if total <= 0:
        return "░" * length
    fraction = max(0.0, min(1.0, current / total))
    filled = int(round(fraction * length))
    return "█" * filled + "░" * (length - filled)


def is_quality_message(target_msg: Message) -> Tuple[bool, str]:
    """Reply qilingan xabar mazmunli yoki faktual ekanligini aniqlash.
    
    Qoidalar:
      1. Media (rasm, video, hujjat, audio) bo'lsa -> Mazmunli
      2. Fakt/mantiqiy so'zlar ("shuning uchun", "demak", "chunki" va h.k.) mavjud bo'lsa -> Mazmunli
      3. Uzunligi kamida 30 ta belgi bo'lsa -> Mazmunli
    """
    if not target_msg:
        return False, "Xabar topilmadi"

    if target_msg.photo or target_msg.video or target_msg.document or target_msg.audio or target_msg.voice:
        return True, "media"

    text = (target_msg.text or target_msg.caption or "").strip()
    if not text:
        return False, "Matn yo'q"

    text_lower = text.lower()

    for kw in QUALITY_KEYWORDS:
        if kw in text_lower:
            return True, f"fakt_soz ({kw})"

    if len(text) >= 30:
        return True, "uzun_matn"

    return False, "mazmunsiz_qisqa"


# ---------------------------------------------------------------------------
# Bazaviy Jadvallarni Tayyorlash
# ---------------------------------------------------------------------------

async def _ensure_level_tables():
    global _tables_initialized
    if _tables_initialized:
        return
    async with _db_lock:
        if _tables_initialized:
            return
        try:
            async with get_db_connection() as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS group_user_xp (
                        chat_id BIGINT,
                        user_id BIGINT,
                        xp BIGINT DEFAULT 0,
                        level INT DEFAULT 1,
                        messages_count INT DEFAULT 0,
                        last_xp_time BIGINT DEFAULT 0,
                        first_name TEXT,
                        username TEXT,
                        PRIMARY KEY (chat_id, user_id)
                    )
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS group_xp_settings (
                        chat_id BIGINT PRIMARY KEY,
                        is_enabled BOOLEAN DEFAULT TRUE,
                        announce_levelup BOOLEAN DEFAULT TRUE,
                        xp_per_msg INT DEFAULT 10,
                        cooldown_sec INT DEFAULT 45
                    )
                """)
            _tables_initialized = True
            logger.info("Group XP va Level jadvallari tayyorlandi.")
        except Exception as e:
            logger.error(f"Group XP DB init xatosi: {e}")


async def get_group_settings(chat_id: int) -> dict:
    await _ensure_level_tables()
    if chat_id in _settings_cache:
        return _settings_cache[chat_id]

    async with get_db_connection() as db:
        async with db.execute(
            "SELECT is_enabled, announce_levelup, xp_per_msg, cooldown_sec FROM group_xp_settings WHERE chat_id = ?",
            (chat_id,)
        ) as cursor:
            row = await cursor.fetchone()

    if row:
        settings = {
            "is_enabled": bool(row[0]),
            "announce_levelup": bool(row[1]),
            "xp_per_msg": int(row[2]),
            "cooldown_sec": int(row[3]),
        }
    else:
        settings = {
            "is_enabled": XP_ENABLED_DEFAULT,
            "announce_levelup": LEVELUP_ANNOUNCE_DEFAULT,
            "xp_per_msg": DEFAULT_XP_PER_MSG,
            "cooldown_sec": DEFAULT_COOLDOWN,
        }

    _settings_cache[chat_id] = settings
    return settings


async def update_group_settings(chat_id: int, **kwargs):
    current = await get_group_settings(chat_id)
    current.update(kwargs)
    _settings_cache[chat_id] = current

    async with get_db_connection() as db:
        await db.execute("""
            INSERT INTO group_xp_settings (chat_id, is_enabled, announce_levelup, xp_per_msg, cooldown_sec)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT(chat_id) DO UPDATE SET
                is_enabled = EXCLUDED.is_enabled,
                announce_levelup = EXCLUDED.announce_levelup,
                xp_per_msg = EXCLUDED.xp_per_msg,
                cooldown_sec = EXCLUDED.cooldown_sec
        """, (
            chat_id,
            current["is_enabled"],
            current["announce_levelup"],
            current["xp_per_msg"],
            current["cooldown_sec"]
        ))


async def is_group_admin(client: Client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False


async def send_levelup_notifications(client: Client, user, chat_id: int, new_level: int, new_xp: int, settings: dict):
    """Level Up xabarlarini Bot PM va Guruhga yuborish"""
    title_name, emoji = get_title_info(new_level)
    next_title = get_next_title_name(new_level)

    cur_lvl_xp_start = xp_for_level(new_level)
    next_lvl_xp = xp_for_level(new_level + 1)
    
    current_in_lvl = max(0, new_xp - cur_lvl_xp_start)
    needed_in_lvl = max(1, next_lvl_xp - cur_lvl_xp_start)
    progress_bar = make_progress_bar(current_in_lvl, needed_in_lvl, 5)
    percent = int(min(100, (current_in_lvl / needed_in_lvl) * 100))

    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")

    pm_sent = False
    # 1. Shaxsiy bot xabari (PM)
    pm_text = (
        f"Darajangiz oshdi!\n"
        f"Unvon: {title_name}\n"
        f"Erishilgan sana: {now_str}\n"
        f"Hozirgi darajada: [{progress_bar}] {percent}% ({current_in_lvl}/{needed_in_lvl} XP)\n"
        f"Keyingi daraja: {next_lvl_xp} XP({next_title})"
    )
    try:
        await client.send_message(user.id, pm_text)
        pm_sent = True
    except Exception as e:
        logger.debug(f"User {user.id} PM notification failed: {e}")
        pm_sent = False

    # 2. Guruh xabari
    if settings.get("announce_levelup", True):
        if user.username:
            user_mention = f"@{user.username}"
        else:
            first_name = user.first_name or "Foydalanuvchi"
            user_mention = f"[{first_name}](tg://user?id={user.id})"

        group_text = (
            f"Darajangiz oshdi {user_mention}!\n"
            f"Unvon: {title_name}"
        )

        if not pm_sent:
            try:
                me = await client.get_me()
                bot_un = me.username or ""
            except Exception:
                bot_un = ""
            bot_ref = f"@{bot_un}" if bot_un else "botimizga"
            group_text += (
                f"\n\n⚠️ *Siz bilan shaxsiy chatda bog'lana olmadik, iltimos {bot_ref} ulaning va botni bloklamang!*"
            )

        try:
            await client.send_message(chat_id, group_text)
        except Exception as e:
            logger.warning(f"Guruhga Level Up xabarini yuborishda xato: {e}")


# ---------------------------------------------------------------------------
# Guruh Xabarlari Listener (XP va Smart Reply '+' Tizimi)
# ---------------------------------------------------------------------------

@Client.on_message(filters.group & ~filters.bot & ~filters.service, group=10)
async def process_group_xp(client: Client, message: Message):
    """Guruhda xabar yozganda yoki reply qilib '+' yuborganda XP berish"""
    if not message.from_user or not message.chat:
        raise ContinuePropagation

    chat_id = message.chat.id
    user_id = message.from_user.id
    now = time.time()

    settings = await get_group_settings(chat_id)
    if not settings["is_enabled"]:
        raise ContinuePropagation

    text = (message.text or "").strip()

    # -----------------------------------------------------------------------
    # Dynamic Smart Reply '+' rejimi
    # -----------------------------------------------------------------------
    if message.reply_to_message and message.reply_to_message.from_user and (text == "+" or text.startswith("+1") or text.startswith("+rep") or text.startswith("++")):
        target_user = message.reply_to_message.from_user

        # O'ziga o'zi yoki botga + bosish taqiqlanadi
        if target_user.id == user_id or target_user.is_bot:
            raise ContinuePropagation

        # 1. Mazmundorlik filtri (Filtrdan o'tmasa XP berilmaydi)
        is_valuable, reason = is_quality_message(message.reply_to_message)
        if not is_valuable:
            try:
                await message.reply_text(
                    "⚠️ '+' faqat mazmunli yoki faktual xabarlarga beriladi! "
                    "(Masalan: 'shuning uchun', 'demak', 'chunki' kabi fakt belgili yoki rasm/media xabarlarga)."
                )
            except Exception:
                pass
            raise ContinuePropagation

        # 2. Dinamik Cooldown (Bir a'zo ikkinchisiga faqat har 5 daqiqada 1 marta + bera oladi)
        pair_cd_key = (chat_id, user_id, target_user.id, "rep_pair")
        last_pair = _cooldown_cache.get(pair_cd_key, 0)
        if now - last_pair < 300:  # 5 daqiqa
            try:
                await message.reply_text("⚠️ Bir foydalanuvchiga har 5 daqiqada faqat 1 marta '+' berishingiz mumkin.")
            except Exception:
                pass
            raise ContinuePropagation

        _cooldown_cache[pair_cd_key] = now

        # Target ga +2 XP
        async with get_db_connection() as db:
            async with db.execute(
                "SELECT xp, level, messages_count FROM group_user_xp WHERE chat_id = ? AND user_id = ?",
                (chat_id, target_user.id)
            ) as cursor:
                t_row = await cursor.fetchone()

            t_old_xp = t_row[0] if t_row else 0
            t_old_lvl = t_row[1] if t_row else 1
            t_msgs = t_row[2] if t_row else 0

            t_new_xp = t_old_xp + 2
            t_new_lvl = calculate_level(t_new_xp)

            await db.execute("""
                INSERT INTO group_user_xp (chat_id, user_id, xp, level, messages_count, last_xp_time, first_name, username)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                    xp = EXCLUDED.xp,
                    level = EXCLUDED.level,
                    first_name = EXCLUDED.first_name,
                    username = EXCLUDED.username
            """, (chat_id, target_user.id, t_new_xp, t_new_lvl, t_msgs, int(now), target_user.first_name or "", target_user.username or ""))

            # Giver ga +1 XP
            async with db.execute(
                "SELECT xp, level, messages_count FROM group_user_xp WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            ) as cursor:
                g_row = await cursor.fetchone()

            g_old_xp = g_row[0] if g_row else 0
            g_old_lvl = g_row[1] if g_row else 1
            g_msgs = g_row[2] if g_row else 0

            g_new_xp = g_old_xp + 1
            g_new_lvl = calculate_level(g_new_xp)

            await db.execute("""
                INSERT INTO group_user_xp (chat_id, user_id, xp, level, messages_count, last_xp_time, first_name, username)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                    xp = EXCLUDED.xp,
                    level = EXCLUDED.level,
                    messages_count = EXCLUDED.messages_count + 1,
                    first_name = EXCLUDED.first_name,
                    username = EXCLUDED.username
            """, (chat_id, user_id, g_new_xp, g_new_lvl, g_msgs + 1, int(now), message.from_user.first_name or "", message.from_user.username or ""))

        # Target level up bo'lsa
        if t_new_lvl > t_old_lvl:
            await send_levelup_notifications(client, target_user, chat_id, t_new_lvl, t_new_xp, settings)

        # Giver level up bo'lsa
        if g_new_lvl > g_old_lvl:
            await send_levelup_notifications(client, message.from_user, chat_id, g_new_lvl, g_new_xp, settings)

        raise ContinuePropagation

    # -----------------------------------------------------------------------
    # Oddiy xabarlar bo'yicha XP berish
    # -----------------------------------------------------------------------
    cooldown = settings["cooldown_sec"]
    last_time = _cooldown_cache.get((chat_id, user_id), 0)

    if now - last_time < cooldown:
        raise ContinuePropagation

    _cooldown_cache[(chat_id, user_id)] = now

    first_name = message.from_user.first_name or "Foydalanuvchi"
    username = message.from_user.username or ""

    base_xp = settings["xp_per_msg"]
    earned_xp = random.randint(max(5, base_xp - 2), base_xp + 5)

    async with get_db_connection() as db:
        async with db.execute(
            "SELECT xp, level, messages_count FROM group_user_xp WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            old_xp = row[0]
            old_level = row[1]
            old_msgs = row[2]

            new_xp = old_xp + earned_xp
            new_msgs = old_msgs + 1
            new_level = calculate_level(new_xp)

            await db.execute("""
                UPDATE group_user_xp
                SET xp = ?, level = ?, messages_count = ?, last_xp_time = ?, first_name = ?, username = ?
                WHERE chat_id = ? AND user_id = ?
            """, (new_xp, new_level, new_msgs, int(now), first_name, username, chat_id, user_id))
        else:
            old_level = 1
            new_xp = earned_xp
            new_msgs = 1
            new_level = calculate_level(new_xp)

            await db.execute("""
                INSERT INTO group_user_xp (chat_id, user_id, xp, level, messages_count, last_xp_time, first_name, username)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (chat_id, user_id, new_xp, new_level, new_msgs, int(now), first_name, username))

    # Level Up bo'lgan bo'lsa bildirishnoma yuborish
    if new_level > old_level:
        await send_levelup_notifications(client, message.from_user, chat_id, new_level, new_xp, settings)

    raise ContinuePropagation


# ---------------------------------------------------------------------------
# Komandalar: /rank, /level, /xp
# ---------------------------------------------------------------------------

@Client.on_message(filters.command(["rank", "level", "xp"]) & filters.group)
async def rank_command(client: Client, message: Message):
    """Foydalanuvchi darajasi va statistikasi"""
    await _ensure_level_tables()
    chat_id = message.chat.id

    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user
    else:
        target_user = message.from_user

    if not target_user or target_user.is_bot:
        await message.reply_text("❌ Botlar uchun XP va Level hisoblanmaydi.")
        return

    user_id = target_user.id

    async with get_db_connection() as db:
        async with db.execute(
            "SELECT xp, level, messages_count FROM group_user_xp WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()

        async with db.execute(
            "SELECT COUNT(*) + 1 FROM group_user_xp WHERE chat_id = ? AND xp > (SELECT COALESCE(xp, 0) FROM group_user_xp WHERE chat_id = ? AND user_id = ?)",
            (chat_id, chat_id, user_id)
        ) as cursor:
            rank_row = await cursor.fetchone()
            rank_pos = rank_row[0] if rank_row else 1

        async with db.execute(
            "SELECT COUNT(*) FROM group_user_xp WHERE chat_id = ?",
            (chat_id,)
        ) as cursor:
            total_members = (await cursor.fetchone())[0]

    if not row:
        xp = 0
        level = 1
        messages_count = 0
    else:
        xp = row[0]
        level = row[1]
        messages_count = row[2]

    title_name, emoji = get_title_info(level)
    cur_lvl_xp_start = xp_for_level(level)
    next_lvl_xp = xp_for_level(level + 1)
    
    current_in_lvl = max(0, xp - cur_lvl_xp_start)
    needed_in_lvl = max(1, next_lvl_xp - cur_lvl_xp_start)
    progress_bar = make_progress_bar(current_in_lvl, needed_in_lvl, 5)
    percent = int(min(100, (current_in_lvl / needed_in_lvl) * 100))

    if target_user.username:
        u_mention = f"@{target_user.username}"
    else:
        u_mention = f"[{target_user.first_name or 'Foydalanuvchi'}](tg://user?id={target_user.id})"

    reply_text = (
        f"🏆 **FOYDALANUVCHI DARAJA VA STATISTIKASI**\n\n"
        f"👤 **Foydalanuvchi:** {u_mention}\n"
        f"📊 **Daraja:** Level {level} ({emoji} {title_name})\n"
        f"✨ **XP:** `{xp}` / `{next_lvl_xp}` XP\n"
        f"📈 **Progress:** `[{progress_bar}]` **{percent}%** (`{current_in_lvl}`/`{needed_in_lvl}` XP)\n"
        f"💬 **Xabarlar soni:** `{messages_count}` ta\n"
        f"🏅 **Guruhdagi o'rni:** `#{rank_pos}` / {max(1, total_members)}"
    )

    await message.reply_text(reply_text)


# ---------------------------------------------------------------------------
# Komanda: /top, /leaderboard, /top_xp
# ---------------------------------------------------------------------------

@Client.on_message(filters.command(["top", "leaderboard", "top_xp"]) & filters.group)
async def top_command(client: Client, message: Message):
    """Guruhning Top 10 faol a'zolari"""
    await _ensure_level_tables()
    chat_id = message.chat.id

    async with get_db_connection() as db:
        async with db.execute(
            "SELECT user_id, xp, level, messages_count, first_name, username "
            "FROM group_user_xp WHERE chat_id = ? ORDER BY xp DESC LIMIT 10",
            (chat_id,)
        ) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await message.reply_text("📊 Guruhda hali XP yig'gan faol a'zolar yo'q.")
        return

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    lines = ["🏆 **GURUHNING TOP-10 FAOL A'ZOLARI**\n"]

    for idx, row in enumerate(rows):
        u_id, xp, lvl, msgs, fn, un = row
        medal = medals[idx] if idx < len(medals) else f"{idx+1}."
        name = fn or f"User {u_id}"
        if un:
            name_str = f"[{name}](https://t.me/{un})"
        else:
            name_str = f"[{name}](tg://user?id={u_id})"

        t_name, emoji = get_title_info(lvl)
        lines.append(f"{medal} {name_str} — **Lvl {lvl}** ({t_name}) | `{xp}` XP (`{msgs}` xabar)")

    lines.append("\n💡 *Guruhda xabar yozib yoki '+' bosib XP to'plang!*")
    await message.reply_text("\n".join(lines), disable_web_page_preview=True)


# ---------------------------------------------------------------------------
# Admin Komandalari: /xpsettings, /addxp, /removexp, /setlevel
# ---------------------------------------------------------------------------

@Client.on_message(filters.command("xpsettings") & filters.group)
async def xp_settings_command(client: Client, message: Message):
    """Guruh XP va Level sozlamalari (Faqat Adminlar uchun)"""
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_group_admin(client, chat_id, user_id):
        await message.reply_text("❌ Bu buyruq faqat guruh adminlari uchun!")
        return

    settings = await get_group_settings(chat_id)
    kb = build_settings_keyboard(settings)

    text = (
        "⚙️ **GURUH XP VA LEVEL SOZLAMALARI**\n\n"
        "Quyidagi tugmalar orqali XP va Level tizimini guruhga moslab sozlashingiz mumkin:"
    )

    await message.reply_text(text, reply_markup=kb)


def build_settings_keyboard(settings: dict) -> InlineKeyboardMarkup:
    status_icon = "🟢 Yoqilgan" if settings["is_enabled"] else "🔴 O'chirilgan"
    announce_icon = "🔔 Yoqilgan" if settings["announce_levelup"] else "🔕 O'chirilgan"

    buttons = [
        [
            InlineKeyboardButton(f"XP Tizimi: {status_icon}", callback_data="xp_toggle_enabled"),
        ],
        [
            InlineKeyboardButton(f"Level Up Xabari: {announce_icon}", callback_data="xp_toggle_announce"),
        ],
        [
            InlineKeyboardButton(f"⚡️ XP/xabar: {settings['xp_per_msg']} XP", callback_data="xp_change_amount"),
            InlineKeyboardButton(f"⏱ Cooldown: {settings['cooldown_sec']}s", callback_data="xp_change_cd"),
        ],
        [
            InlineKeyboardButton("🔄 Reytingni tozalash", callback_data="xp_reset_confirm"),
            InlineKeyboardButton("❌ Yopish", callback_data="xp_close"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)


@Client.on_callback_query(filters.regex(r"^xp_"))
async def xp_settings_callback(client: Client, cq: CallbackQuery):
    chat_id = cq.message.chat.id
    user_id = cq.from_user.id

    if not await is_group_admin(client, chat_id, user_id):
        await cq.answer("❌ Faqat guruh adminlari sozlamalarni o'zgartira oladi!", show_alert=True)
        return

    data = cq.data
    settings = await get_group_settings(chat_id)

    if data == "xp_toggle_enabled":
        new_val = not settings["is_enabled"]
        await update_group_settings(chat_id, is_enabled=new_val)
        status_txt = "yoqildi" if new_val else "o'chirildi"
        await cq.answer(f"XP tizimi {status_txt}")

    elif data == "xp_toggle_announce":
        new_val = not settings["announce_levelup"]
        await update_group_settings(chat_id, announce_levelup=new_val)
        status_txt = "yoqildi" if new_val else "o'chirildi"
        await cq.answer(f"Level Up xabari {status_txt}")

    elif data == "xp_change_amount":
        amounts = [5, 10, 15, 20, 25]
        cur = settings["xp_per_msg"]
        idx = (amounts.index(cur) + 1) % len(amounts) if cur in amounts else 0
        new_amount = amounts[idx]
        await update_group_settings(chat_id, xp_per_msg=new_amount)
        await cq.answer(f"Xabar uchun XP: {new_amount} XP ga o'zgartirildi")

    elif data == "xp_change_cd":
        cds = [15, 30, 45, 60, 90]
        cur = settings["cooldown_sec"]
        idx = (cds.index(cur) + 1) % len(cds) if cur in cds else 0
        new_cd = cds[idx]
        await update_group_settings(chat_id, cooldown_sec=new_cd)
        await cq.answer(f"Cooldown: {new_cd} soniyaga o'zgartirildi")

    elif data == "xp_reset_confirm":
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Ha, tozalansin", callback_data="xp_reset_do"),
                InlineKeyboardButton("❌ Bekor qilish", callback_data="xp_reset_cancel"),
            ]
        ])
        await cq.message.edit_text(
            "⚠️ **DIQQAT!** Guruhdagi barcha a'zolarning XP va Level ma'lumotlarini nolga tushirishni tasdiqlaysizmi?",
            reply_markup=kb
        )
        return

    elif data == "xp_reset_do":
        async with get_db_connection() as db:
            await db.execute("DELETE FROM group_user_xp WHERE chat_id = ?", (chat_id,))
        await cq.answer("✅ Guruh XP va Level ma'lumotlari tozalandi!", show_alert=True)

    elif data in ("xp_reset_cancel", "xp_close"):
        if data == "xp_close":
            await cq.message.delete()
            return

    updated_settings = await get_group_settings(chat_id)
    kb = build_settings_keyboard(updated_settings)
    try:
        await cq.message.edit_text(
            "⚙️ **GURUH XP VA LEVEL SOZLAMALARI**\n\n"
            "Quyidagi tugmalar orqali XP va Level tizimini guruhga moslab sozlashingiz mumkin:",
            reply_markup=kb
        )
    except Exception:
        pass


@Client.on_message(filters.command(["addxp", "removexp", "setlevel"]) & filters.group)
async def admin_manage_xp(client: Client, message: Message):
    """Adminlar tomonidan XP yoki Levelni qo'lda o'zgartirish"""
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_group_admin(client, chat_id, user_id):
        await message.reply_text("❌ Bu buyruq faqat guruh adminlari uchun!")
        return

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply_text(
            "⚠️ Buyruqdan foydalanish uchun foydalanuvchi xabariga **reply (javob)** qiling:\n"
            "• `/addxp 500` — 500 XP qo'shish\n"
            "• `/removexp 200` — 200 XP olib tashlash\n"
            "• `/setlevel 5` — 5-darajaga o'tkazish"
        )
        return

    args = message.command
    if len(args) < 2 or not args[1].isdigit():
        await message.reply_text("❌ Iltimos, musbat raqam kiriting. Masalan: `/addxp 100`")
        return

    val = int(args[1])
    target_user = message.reply_to_message.from_user
    target_id = target_user.id
    first_name = target_user.first_name or "Foydalanuvchi"
    username = target_user.username or ""

    cmd = args[0].lower()

    async with get_db_connection() as db:
        async with db.execute(
            "SELECT xp, level, messages_count FROM group_user_xp WHERE chat_id = ? AND user_id = ?",
            (chat_id, target_id)
        ) as cursor:
            row = await cursor.fetchone()

        cur_xp = row[0] if row else 0
        cur_msgs = row[2] if row else 0

        if cmd == "addxp":
            new_xp = cur_xp + val
            new_level = calculate_level(new_xp)
            msg_res = f"✅ {target_user.mention} foydalanuvchisiga **+{val} XP** berildi! Yangi daraja: **Lvl {new_level}** ({new_xp} XP)"

        elif cmd == "removexp":
            new_xp = max(0, cur_xp - val)
            new_level = calculate_level(new_xp)
            msg_res = f"✅ {target_user.mention} foydalanuvchisidan **-{val} XP** olib tashlandi. Yangi daraja: **Lvl {new_level}** ({new_xp} XP)"

        elif cmd == "setlevel":
            new_level = max(1, val)
            new_xp = xp_for_level(new_level)
            msg_res = f"✅ {target_user.mention} darajasi **Lvl {new_level}** ga o'zgartirildi ({new_xp} XP)."
        else:
            return

        await db.execute("""
            INSERT INTO group_user_xp (chat_id, user_id, xp, level, messages_count, last_xp_time, first_name, username)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                xp = EXCLUDED.xp,
                level = EXCLUDED.level,
                first_name = EXCLUDED.first_name,
                username = EXCLUDED.username
        """, (chat_id, target_id, new_xp, new_level, cur_msgs, int(time.time()), first_name, username))

    await message.reply_text(msg_res)


# ---------------------------------------------------------------------------
# Bot Adminlari uchun XP Nazorati: /checkxp va Tugmalar
# ---------------------------------------------------------------------------

@Client.on_message(filters.command("checkxp"))
async def checkxp_command(client: Client, message: Message):
    """Bot adminlari uchun XP va darajani tekshirish va boshqarish paneli (/checkxp).
    
    Agar admin da 'can_manage_xp' (XP nazorati huquqi) bo'lmasa, bot unga UMUMAN javob bermaydi.
    """
    sender_id = message.from_user.id if message.from_user else 0
    if not sender_id or not await can_manage_xp(sender_id):
        # Huquqi bo'lmasa — bot mutlaqo jim qoladi (javob bermaydi)
        return

    await _ensure_level_tables()

    # Target foydalanuvchini aniqlash (reply qilingan yoki buyruqda kiritilgan)
    target_user = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user

    if not target_user:
        await message.reply_text(
            "⚠️ Foydalanuvchi ma'lumotlarini ko'rish uchun uning xabariga **reply (javob)** qilib `/checkxp` yuboring!"
        )
        return

    chat_id = message.chat.id
    text, kb = await build_checkxp_panel(chat_id, target_user, sender_id)
    await message.reply_text(text, reply_markup=kb)


async def build_checkxp_panel(chat_id: int, target_user, admin_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    user_id = target_user.id
    async with get_db_connection() as db:
        async with db.execute(
            "SELECT xp, level, messages_count FROM group_user_xp WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()

    if not row:
        xp = 0
        level = 1
        msgs = 0
    else:
        xp = row[0]
        level = row[1]
        msgs = row[2]

    title_name, emoji = get_title_info(level)
    next_title = get_next_title_name(level)

    cur_lvl_xp_start = xp_for_level(level)
    next_lvl_xp = xp_for_level(level + 1)

    current_in_lvl = max(0, xp - cur_lvl_xp_start)
    needed_in_lvl = max(1, next_lvl_xp - cur_lvl_xp_start)
    remaining_to_next = max(0, next_lvl_xp - xp)

    progress_bar = make_progress_bar(current_in_lvl, needed_in_lvl, 5)
    percent = int(min(100, (current_in_lvl / needed_in_lvl) * 100))

    if target_user.username:
        u_mention = f"@{target_user.username}"
    else:
        u_mention = f"[{target_user.first_name or 'Foydalanuvchi'}](tg://user?id={user_id})"

    text = (
        f"⚙️ **XP NAZORATI PANEL**\n\n"
        f"👤 **Foydalanuvchi:** {u_mention}\n"
        f"🆔 **ID:** `{user_id}`\n"
        f"📊 **Daraja:** Level {level} ({emoji} {title_name})\n"
        f"✨ **XP:** `{xp}` / `{next_lvl_xp}` XP\n"
        f"🎖 **Keyingi unvon:** **{next_title}** ({remaining_to_next} XP qoldi)\n"
        f"📈 **Progress:** `[{progress_bar}]` **{percent}%** (`{current_in_lvl}`/`{needed_in_lvl}` XP)\n"
        f"💬 **Xabarlar:** `{msgs}` ta"
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Daraja qo'shish", callback_data=f"xpadmin_add:{user_id}:{admin_id}"),
            InlineKeyboardButton("➖ Daraja olib tashlash", callback_data=f"xpadmin_sub:{user_id}:{admin_id}"),
        ],
        [
            InlineKeyboardButton("💥 Bankrot qilish (0 XP)", callback_data=f"xpadmin_reset:{user_id}:{admin_id}"),
        ],
        [
            InlineKeyboardButton("❌ Yopish", callback_data=f"xpadmin_close:{user_id}:{admin_id}"),
        ]
    ])
    return text, kb


@Client.on_callback_query(filters.regex(r"^xpadmin_(\w+):(\d+):(\d+)$"))
async def checkxp_admin_callback(client: Client, cq: CallbackQuery):
    action = cq.matches[0].group(1)
    target_id = int(cq.matches[0].group(2))
    allowed_admin_id = int(cq.matches[0].group(3))

    # Xavfsizlik tekshiruvi: faqat komanda yuborgan admin bosishi mumkin
    if cq.from_user.id != allowed_admin_id:
        await cq.answer("❌ Bu tugma siz uchun emas!", show_alert=True)
        return

    chat_id = cq.message.chat.id

    if action == "close":
        await cq.message.delete()
        return

    async with get_db_connection() as db:
        async with db.execute(
            "SELECT xp, level, messages_count, first_name, username FROM group_user_xp WHERE chat_id = ? AND user_id = ?",
            (chat_id, target_id)
        ) as cursor:
            row = await cursor.fetchone()

        cur_xp = row[0] if row else 0
        cur_lvl = row[1] if row else 1
        cur_msgs = row[2] if row else 0
        fn = row[3] if row else "Foydalanuvchi"
        un = row[4] if row else ""

        if action == "add":
            new_lvl = cur_lvl + 1
            new_xp = xp_for_level(new_lvl)
            ans_text = f"✅ Daraja {new_lvl} ga oshirildi!"
        elif action == "sub":
            new_lvl = max(1, cur_lvl - 1)
            new_xp = xp_for_level(new_lvl)
            ans_text = f"✅ Daraja {new_lvl} ga tushirildi!"
        elif action == "reset":
            new_lvl = 1
            new_xp = 0
            ans_text = "💥 Foydalanuvchi darajasi va XP ma'lumotlari bankrot qilindi (0 XP)!"
        else:
            return

        await db.execute("""
            INSERT INTO group_user_xp (chat_id, user_id, xp, level, messages_count, last_xp_time, first_name, username)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                xp = EXCLUDED.xp,
                level = EXCLUDED.level,
                first_name = EXCLUDED.first_name,
                username = EXCLUDED.username
        """, (chat_id, target_id, new_xp, new_lvl, cur_msgs, int(time.time()), fn, un))

    try:
        tg_user = await client.get_users(target_id)
    except Exception:
        class DummyUser:
            id = target_id
            first_name = fn
            username = un
        tg_user = DummyUser()

    text, kb = await build_checkxp_panel(chat_id, tg_user, allowed_admin_id)
    try:
        await cq.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass

    await cq.answer(ans_text, show_alert=(action == "reset"))


# ---------------------------------------------------------------------------
# "📊 Darajamni ko'rish" Tugmasi va /myrank Buyrug'i Handler
# ---------------------------------------------------------------------------

@Client.on_message(filters.regex(r"^(📊 Darajamni ko'rish|🏆 Darajam)$") | filters.command(["myrank", "mylevel", "myxp"]))
async def my_rank_handler(client: Client, message: Message):
    """Foydalanuvchining shaxsiy darajasi va statistikasi"""
    await _ensure_level_tables()
    user = message.from_user
    if not user or user.is_bot:
        return

    user_id = user.id
    async with get_db_connection() as db:
        async with db.execute("""
            SELECT SUM(xp), MAX(level), SUM(messages_count), COUNT(DISTINCT chat_id)
            FROM group_user_xp WHERE user_id = ?
        """, (user_id,)) as cursor:
            row = await cursor.fetchone()

    total_xp = int(row[0]) if (row and row[0] is not None) else 0
    max_level = int(row[1]) if (row and row[1] is not None) else 1
    total_msgs = int(row[2]) if (row and row[2] is not None) else 0
    groups_count = int(row[3]) if (row and row[3] is not None) else 0

    calc_level = calculate_level(total_xp)
    effective_level = max(max_level, calc_level)

    title_name, emoji = get_title_info(effective_level)
    next_title = get_next_title_name(effective_level)

    cur_lvl_xp_start = xp_for_level(effective_level)
    next_lvl_xp = xp_for_level(effective_level + 1)
    
    current_in_lvl = max(0, total_xp - cur_lvl_xp_start)
    needed_in_lvl = max(1, next_lvl_xp - cur_lvl_xp_start)
    remaining_to_next = max(0, next_lvl_xp - total_xp)

    progress_bar = make_progress_bar(current_in_lvl, needed_in_lvl, 5)
    percent = int(min(100, (current_in_lvl / needed_in_lvl) * 100))

    if user.username:
        u_mention = f"@{user.username}"
    else:
        u_mention = f"[{user.first_name or 'Foydalanuvchi'}](tg://user?id={user_id})"

    text = (
        f"🏆 **SIZNING DARAJANGIZ VA STATISTIKANGIZ**\n\n"
        f"👤 **Foydalanuvchi:** {u_mention}\n"
        f"🆔 **ID:** `{user_id}`\n"
        f"📊 **Daraja:** Level {effective_level} ({emoji} {title_name})\n"
        f"✨ **Jami XP:** `{total_xp}` / `{next_lvl_xp}` XP\n"
        f"🎖 **Keyingi unvon:** **{next_title}** ({remaining_to_next} XP qoldi)\n"
        f"📈 **Progress:** `[{progress_bar}]` **{percent}%** (`{current_in_lvl}`/`{needed_in_lvl}` XP)\n"
        f"💬 **Jami xabarlar:** `{total_msgs}` ta\n"
        f"👥 **Faol guruhlar:** `{groups_count}` ta"
    )

    await message.reply_text(text)
