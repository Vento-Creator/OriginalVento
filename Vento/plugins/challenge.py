"""
🎯 Challenge / Maqsad Tizimi — Guruhlar uchun kollektiv maqsadlar va bellashuvlar.

Xususiyatlar:
  • Guruh adminlari faoliyat maqsadlarini belgilaydi (masalan: 1 haftada 10 000 ta xabar yoki 100 ta yangi a'zo).
  • Guruhdagi har bir yangi xabar va qo'shilgan a'zolar avtomatik ravishda sanaladi.
  • /challenge, /maqsad, /goals — faol maqsad statusini vizual progress-bar [▓▓▓▓▓░░░░░] bilan ko'rsatish.
  • /setchallenge — interaktiv tugmalar yoki komanda orqali yangi maqsad belgilash.
  • Maqsad 100% ga yetganda guruhga bayramona tabrik bildirishnomasi avtomatik yuboriladi.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Tuple

from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from pyrogram.enums import ChatMemberStatus, ParseMode

from database import get_db_connection
from config import is_owner

logger = logging.getLogger(__name__)

# State tracking for challenge creation step-by-step wizard
_challenge_wizard_state: Dict[int, dict] = {}  # admin_user_id -> {"chat_id": ..., "step": ...}


async def _init_challenge_db():
    """Auto-create tables for group challenges if they do not exist."""
    async with get_db_connection() as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS group_challenges (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                title TEXT NOT NULL,
                challenge_type TEXT NOT NULL,
                target_count INT NOT NULL,
                current_count INT DEFAULT 0,
                start_time BIGINT NOT NULL,
                end_time BIGINT DEFAULT 0,
                is_completed BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                created_by BIGINT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_group_challenges_chat 
            ON group_challenges(chat_id, is_active)
            """
        )


_db_initialized = False

async def ensure_challenge_db():
    global _db_initialized
    if _db_initialized:
        return
    try:
        await _init_challenge_db()
        _db_initialized = True
    except Exception as e:
        logger.warning(f"Challenge DB init error: {e}")


def format_progress_bar(current: int, target: int, length: int = 10) -> Tuple[str, int]:
    """Build progress bar string like [▓▓▓▓▓░░░░░] 50%."""
    if target <= 0:
        return "[" + "░" * length + "]", 0
    
    pct = int((current / target) * 100)
    pct_clamped = min(100, max(0, pct))
    filled_len = int((pct_clamped / 100.0) * length)
    
    bar = "▓" * filled_len + "░" * (length - filled_len)
    return f"[{bar}]", pct_clamped


async def is_group_admin(client: Client, chat_id: int, user_id: int) -> bool:
    """Check if the given user is an admin or creator in the specified group chat."""
    if is_owner(user_id):
        return True
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False


async def get_active_challenge(chat_id: int) -> Optional[dict]:
    """Retrieve active challenge for a given chat."""
    await ensure_challenge_db()
    async with get_db_connection() as db:
        cur = await db.execute(
            """
            SELECT id, chat_id, title, challenge_type, target_count, current_count, 
                   start_time, end_time, is_completed, is_active, created_by
            FROM group_challenges
            WHERE chat_id = ? AND is_active = TRUE
            ORDER BY id DESC LIMIT 1
            """,
            (chat_id,)
        )
        row = await cur.fetchone()
        if not row:
            return None
        
        # PostgreSQL dict / tuple handling
        if isinstance(row, dict):
            return row
        return {
            "id": row[0],
            "chat_id": row[1],
            "title": row[2],
            "challenge_type": row[3],
            "target_count": row[4],
            "current_count": row[5],
            "start_time": row[6],
            "end_time": row[7],
            "is_completed": row[8],
            "is_active": row[9],
            "created_by": row[10],
        }


async def increment_challenge_progress(client: Client, chat_id: int, challenge_type: str, delta: int = 1):
    """Increment progress for active challenge and notify if completed."""
    challenge = await get_active_challenge(chat_id)
    if not challenge or challenge["challenge_type"] != challenge_type:
        return
    
    cid = challenge["id"]
    new_count = challenge["current_count"] + delta
    target = challenge["target_count"]
    
    is_completed = new_count >= target
    
    async with get_db_connection() as db:
        if is_completed:
            await db.execute(
                """
                UPDATE group_challenges
                SET current_count = ?, is_completed = TRUE, is_active = FALSE
                WHERE id = ?
                """,
                (new_count, cid)
            )
        else:
            await db.execute(
                """
                UPDATE group_challenges
                SET current_count = ?
                WHERE id = ?
                """,
                (new_count, cid)
            )

    # If completed, send celebration broadcast in the group chat!
    if is_completed:
        try:
            bar_str, pct = format_progress_bar(new_count, target)
            title = challenge["title"]
            msg = (
                f"🎉 <b>MAQSAD BAJARILDI!</b> 🎯\n\n"
                f"🏆 <b>Challenge</b>: {title}\n"
                f"📊 <b>Natija</b>: {new_count:,} / {target:,} ({pct}%)\n"
                f"📈 <code>{bar_str}</code>\n\n"
                f"✨ Barcha guruh a'zolariga yuqori faolligi uchun rahmat! Yangi maqsad belgilash uchun /setchallenge bosing."
            )
            await client.send_message(chat_id, msg, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.warning(f"Challenge completion broadcast error in chat {chat_id}: {e}")


# ---------------------------------------------------------------------------
# Event Listeners for Automatic Counting
# ---------------------------------------------------------------------------

@Client.on_message(filters.group & ~filters.service, group=10)
async def challenge_message_counter(client: Client, message: Message):
    """Increment active 'messages' challenge counter for the group."""
    if message.chat and message.chat.id:
        # Non-blocking async increment
        asyncio.create_task(increment_challenge_progress(client, message.chat.id, "messages", 1))
    raise ContinuePropagation


@Client.on_message(filters.group & filters.new_chat_members, group=11)
async def challenge_members_counter(client: Client, message: Message):
    """Increment active 'members' challenge counter for new chat members."""
    if message.chat and message.chat.id and message.new_chat_members:
        count = len(message.new_chat_members)
        asyncio.create_task(increment_challenge_progress(client, message.chat.id, "members", count))
    raise ContinuePropagation


# ---------------------------------------------------------------------------
# Commands & Handlers
# ---------------------------------------------------------------------------

@Client.on_message(filters.command(["challenge", "maqsad", "goals"]) & filters.group)
async def view_challenge_command(client: Client, message: Message):
    """View active challenge status in the group."""
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    
    challenge = await get_active_challenge(chat_id)
    if not challenge:
        is_admin = await is_group_admin(client, chat_id, user_id)
        text = (
            "🎯 <b>Guruh Maqsadi (Challenge)</b>\n\n"
            "Hozirda bu guruhda faol maqsad belgilanmagan.\n"
        )
        buttons = []
        if is_admin:
            text += "\n👇 Admin sifatida yangi maqsad yaratishingiz mumkin:"
            buttons.append([InlineKeyboardButton("➕ Yangi Maqsad Yaratish", callback_data=f"ch_new_{chat_id}")])
        buttons.append([InlineKeyboardButton("❌ Yopish", callback_data="ch_close")])
        
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)
        return

    title = challenge["title"]
    curr = challenge["current_count"]
    target = challenge["target_count"]
    ctype = "💬 Xabarlar" if challenge["challenge_type"] == "messages" else "👥 Yangi a'zolar"
    
    bar_str, pct = format_progress_bar(curr, target)
    rem = max(0, target - curr)
    
    text = (
        f"🎯 <b>GURUH MAQSADI (CHALLENGE)</b>\n\n"
        f"📌 <b>Nomi</b>: {title}\n"
        f"🏷 <b>Turi</b>: {ctype}\n"
        f"📊 <b>Progress</b>: {curr:,} / {target:,} ({pct}%)\n"
        f"📈 <code>{bar_str}</code>\n"
        f"⏳ <b>Qolgani</b>: {rem:,}\n\n"
        f"💪 Barchamiz birga faol bo'lib ko'zlangan maqsadga erishamiz!"
    )
    
    buttons = []
    is_admin = await is_group_admin(client, chat_id, user_id)
    if is_admin:
        buttons.append([InlineKeyboardButton("🗑 Maqsadni To'xtatish", callback_data=f"ch_stop_{challenge['id']}")])
    buttons.append([InlineKeyboardButton("🔄 Yangilash", callback_data=f"ch_refresh_{chat_id}")])
    buttons.append([InlineKeyboardButton("❌ Yopish", callback_data="ch_close")])
    
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)


@Client.on_message(filters.command(["setchallenge"]) & filters.group)
async def set_challenge_command(client: Client, message: Message):
    """Command wizard to set a new challenge."""
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    
    if not await is_group_admin(client, chat_id, user_id):
        await message.reply_text("❌ Maqsad belgilash faqat guruh adminlari uchun ruxsat etilgan!")
        return

    # Check command arguments e.g. /setchallenge messages 10000 Haftalik faollik
    args = message.text.split(maxsplit=3)
    if len(args) >= 3:
        ctype = args[1].lower()
        if ctype not in ("messages", "members", "xabar", "azolar"):
            await message.reply_text("❌ Maqsad turi noto'g'ri! <code>messages</code> yoki <code>members</code> deb kiriting.", parse_mode=ParseMode.HTML)
            return
        
        c_type_code = "messages" if ctype in ("messages", "xabar") else "members"
        try:
            target = int(args[2])
            if target <= 0:
                raise ValueError
        except ValueError:
            await message.reply_text("❌ Maqsad miqdori musbat son bo'lishi kerak! Masalan: <code>/setchallenge messages 10000</code>", parse_mode=ParseMode.HTML)
            return
            
        unit_str = "xabar" if c_type_code == "messages" else "a'zo"
        title = args[3] if len(args) == 4 else f"{target:,} ta {unit_str} maqsadi"
        
        # Deactivate any existing active challenge
        async with get_db_connection() as db:
            await db.execute(
                "UPDATE group_challenges SET is_active = FALSE WHERE chat_id = ? AND is_active = TRUE",
                (chat_id,)
            )
            await db.execute(
                """
                INSERT INTO group_challenges (chat_id, title, challenge_type, target_count, current_count, start_time, created_by)
                VALUES (?, ?, ?, ?, 0, ?, ?)
                """,
                (chat_id, title, c_type_code, target, int(time.time()), user_id)
            )
            
        await message.reply_text(
            f"✅ <b>Yangi guruh maqsadi o'rnatildi!</b>\n\n"
            f"🎯 <b>Nomi</b>: {title}\n"
            f"📊 <b>Maqsad</b>: {target:,} ta {unit_str}\n\n"
            f"Ko'rish uchun /challenge deb yozing.",
            parse_mode=ParseMode.HTML
        )
        return

    # If no args, display quick interactive selection keyboard
    buttons = [
        [
            InlineKeyboardButton("💬 10,000 Xabar", callback_data=f"ch_preset_msg_10000_{chat_id}"),
            InlineKeyboardButton("💬 5,000 Xabar", callback_data=f"ch_preset_msg_5000_{chat_id}"),
        ],
        [
            InlineKeyboardButton("👥 100 Yangi A'zo", callback_data=f"ch_preset_mem_100_{chat_id}"),
            InlineKeyboardButton("👥 50 Yangi A'zo", callback_data=f"ch_preset_mem_50_{chat_id}"),
        ],
        [
            InlineKeyboardButton("✏️ Custom Xabar soni", callback_data=f"ch_custom_msg_{chat_id}"),
            InlineKeyboardButton("✏️ Custom A'zo soni", callback_data=f"ch_custom_mem_{chat_id}"),
        ],
        [InlineKeyboardButton("❌ Bekor Qilish", callback_data="ch_close")],
    ]
    
    text = (
        "🎯 <b>Yangi Guruh Maqsadi O'rnatish</b>\n\n"
        "Tayyor shablonlardan birini tanlang yoki o'zingiz raqam kiriting:\n"
        "Buyruq orqali: <code>/setchallenge messages 12345 Haftalik Faollik</code>"
    )
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)


@Client.on_message(filters.group & filters.text & ~filters.service, group=9)
async def challenge_wizard_input(client: Client, message: Message):
    """Handle custom number input for challenge setup wizard."""
    user_id = message.from_user.id if message.from_user else 0
    if user_id not in _challenge_wizard_state:
        raise ContinuePropagation
        
    state = _challenge_wizard_state[user_id]
    if message.chat.id != state.get("chat_id"):
        raise ContinuePropagation

    # Check state TTL (5 minutes)
    if time.time() - state.get("time", 0) > 300:
        _challenge_wizard_state.pop(user_id, None)
        raise ContinuePropagation

    text = message.text.strip()
    if text.lower() in ("/cancel", "cancel", "bekor"):
        _challenge_wizard_state.pop(user_id, None)
        await message.reply_text("❌ Maqsad o'rnatish bekor qilindi.")
        return

    try:
        target_val = int(text)
        if target_val <= 0:
            raise ValueError
    except ValueError:
        await message.reply_text("❌ Iltimos, faqat musbat son kiriting (Masalan: <code>15000</code>).", parse_mode=ParseMode.HTML)
        return

    _challenge_wizard_state.pop(user_id, None)
    ctype = state.get("type", "messages")
    unit_str = "xabar" if ctype == "messages" else "yangi a'zo"
    title = f"{target_val:,} ta {unit_str}"
    cid = message.chat.id

    async with get_db_connection() as db:
        await db.execute(
            "UPDATE group_challenges SET is_active = FALSE WHERE chat_id = ? AND is_active = TRUE",
            (cid,)
        )
        await db.execute(
            """
            INSERT INTO group_challenges (chat_id, title, challenge_type, target_count, current_count, start_time, created_by)
            VALUES (?, ?, ?, ?, 0, ?, ?)
            """,
            (cid, title, ctype, target_val, int(time.time()), user_id)
        )

    bar_str, pct = format_progress_bar(0, target_val)
    ctype_label = "💬 Xabarlar" if ctype == "messages" else "👥 Yangi a'zolar"
    reply_text = (
        f"✅ <b>Yangi guruh maqsadi o'rnatildi!</b>\n\n"
        f"📌 <b>Nomi</b>: {title}\n"
        f"🏷 <b>Turi</b>: {ctype_label}\n"
        f"📊 <b>Progress</b>: 0 / {target_val:,} (0%)\n"
        f"📈 <code>{bar_str}</code>\n\n"
        f"Barchamiz faol bo'lib marraga erishamiz! 💪"
    )
    buttons = [
        [InlineKeyboardButton("🔄 Yangilash", callback_data=f"ch_refresh_{cid}")],
        [InlineKeyboardButton("❌ Yopish", callback_data="ch_close")]
    ]
    await message.reply_text(reply_text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)


# ---------------------------------------------------------------------------
# Callback Queries
# ---------------------------------------------------------------------------

@Client.on_callback_query(filters.regex(r"^ch_"))
async def challenge_callback_handler(client: Client, cq: CallbackQuery):
    data = cq.data
    user_id = cq.from_user.id
    chat_id = cq.message.chat.id if cq.message and cq.message.chat else 0
    
    if data == "ch_close":
        _challenge_wizard_state.pop(user_id, None)
        try:
            await cq.message.delete()
        except Exception:
            pass
        return

    # Direct modal start wizard for admin
    if data.startswith("ch_new_"):
        cid = int(data.split("_")[2])
        if not await is_group_admin(client, cid, user_id):
            await cq.answer("❌ Maqsadlarni faqat guruh adminlari belgilashi mumkin!", show_alert=True)
            return
            
        buttons = [
            [
                InlineKeyboardButton("💬 10,000 Xabar", callback_data=f"ch_preset_msg_10000_{cid}"),
                InlineKeyboardButton("💬 5,000 Xabar", callback_data=f"ch_preset_msg_5000_{cid}"),
            ],
            [
                InlineKeyboardButton("👥 100 Yangi A'zo", callback_data=f"ch_preset_mem_100_{cid}"),
                InlineKeyboardButton("👥 50 Yangi A'zo", callback_data=f"ch_preset_mem_50_{cid}"),
            ],
            [
                InlineKeyboardButton("✏️ Custom Xabar soni", callback_data=f"ch_custom_msg_{cid}"),
                InlineKeyboardButton("✏️ Custom A'zo soni", callback_data=f"ch_custom_mem_{cid}"),
            ],
            [InlineKeyboardButton("❌ Bekor Qilish", callback_data="ch_close")],
        ]
        text = (
            "🎯 <b>Yangi Guruh Maqsadi O'rnatish</b>\n\n"
            "Tayyor shablonlardan birini tanlang yoki o'ziz raqam kiriting:\n"
            "Buyruq orqali: <code>/setchallenge messages 12345</code>"
        )
        try:
            await cq.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.warning(f"edit_text error in ch_new_: {e}")
        return

    # Custom prompt trigger
    if data.startswith("ch_custom_"):
        parts = data.split("_") # ch, custom, type, chat_id
        if len(parts) >= 4:
            ctype_raw = parts[2]
            cid = int(parts[3])
            
            if not await is_group_admin(client, cid, user_id):
                await cq.answer("❌ Maqsadlarni faqat guruh adminlari belgilashi mumkin!", show_alert=True)
                return

            ctype = "messages" if ctype_raw == "msg" else "members"
            _challenge_wizard_state[user_id] = {
                "chat_id": cid,
                "type": ctype,
                "time": time.time()
            }
            
            unit_label = "xabarlar" if ctype == "messages" else "yangi a'zolar"
            text = (
                f"✏️ <b>O'zingiz mos kiritmoqchi bo'lgan maqsad ({unit_label}) sonini guruhga yozing:</b>\n\n"
                f"Masalan: <code>15000</code> yoki <code>250</code>\n"
                f"<i>(Bekor qilish uchun /cancel deb yozing)</i>"
            )
            try:
                await cq.message.edit_text(text, parse_mode=ParseMode.HTML)
            except Exception:
                pass
            await cq.answer()
            return

    # Quick preset challenge setup
    if data.startswith("ch_preset_"):
        parts = data.split("_")  # ch, preset, type, count, chat_id
        if len(parts) >= 5:
            ctype_raw = parts[2]
            target_val = int(parts[3])
            cid = int(parts[4])
            
            if not await is_group_admin(client, cid, user_id):
                await cq.answer("❌ Maqsadlarni faqat guruh adminlari belgilashi mumkin!", show_alert=True)
                return
                
            ctype = "messages" if ctype_raw == "msg" else "members"
            unit_str = "xabar" if ctype == "messages" else "yangi a'zo"
            title = f"{target_val:,} ta {unit_str}"
            
            async with get_db_connection() as db:
                await db.execute(
                    "UPDATE group_challenges SET is_active = FALSE WHERE chat_id = ? AND is_active = TRUE",
                    (cid,)
                )
                await db.execute(
                    """
                    INSERT INTO group_challenges (chat_id, title, challenge_type, target_count, current_count, start_time, created_by)
                    VALUES (?, ?, ?, ?, 0, ?, ?)
                    """,
                    (cid, title, ctype, target_val, int(time.time()), user_id)
                )
            
            await cq.answer("✅ Maqsad o'rnatildi!")
            bar_str, pct = format_progress_bar(0, target_val)
            ctype_label = "💬 Xabarlar" if ctype == "messages" else "👥 Yangi a'zolar"
            text = (
                f"✅ <b>Yangi guruh maqsadi o'rnatildi!</b>\n\n"
                f"📌 <b>Nomi</b>: {title}\n"
                f"🏷 <b>Turi</b>: {ctype_label}\n"
                f"📊 <b>Progress</b>: 0 / {target_val:,} (0%)\n"
                f"📈 <code>{bar_str}</code>\n\n"
                f"Barchamiz faol bo'lib marraga erishamiz! 💪"
            )
            buttons = [
                [InlineKeyboardButton("🔄 Yangilash", callback_data=f"ch_refresh_{cid}")],
                [InlineKeyboardButton("❌ Yopish", callback_data="ch_close")]
            ]
            try:
                await cq.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.warning(f"edit_text error in ch_preset_: {e}")
            return

    # Refresh current challenge status
    if data.startswith("ch_refresh_"):
        cid = int(data.split("_")[2])
        challenge = await get_active_challenge(cid)
        if not challenge:
            await cq.answer("⚠️ Faol maqsad topilmadi!", show_alert=True)
            return
            
        title = challenge["title"]
        curr = challenge["current_count"]
        target = challenge["target_count"]
        ctype = "💬 Xabarlar" if challenge["challenge_type"] == "messages" else "👥 Yangi a'zolar"
        bar_str, pct = format_progress_bar(curr, target)
        rem = max(0, target - curr)
        
        text = (
            f"🎯 <b>GURUH MAQSADI (CHALLENGE)</b>\n\n"
            f"📌 <b>Nomi</b>: {title}\n"
            f"🏷 <b>Turi</b>: {ctype}\n"
            f"📊 <b>Progress</b>: {curr:,} / {target:,} ({pct}%)\n"
            f"📈 <code>{bar_str}</code>\n"
            f"⏳ <b>Qolgani</b>: {rem:,}\n\n"
            f"💪 Barchamiz birga faol bo'lib ko'zlangan maqsadga erishamiz!"
        )
        
        buttons = []
        if await is_group_admin(client, cid, user_id):
            buttons.append([InlineKeyboardButton("🗑 Maqsadni To'xtatish", callback_data=f"ch_stop_{challenge['id']}")])
        buttons.append([InlineKeyboardButton("🔄 Yangilash", callback_data=f"ch_refresh_{cid}")])
        buttons.append([InlineKeyboardButton("❌ Yopish", callback_data="ch_close")])
        
        try:
            await cq.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)
            await cq.answer("🔄 Yangilandi")
        except Exception:
            await cq.answer("O'zgarish yo'q")
        return

    # Stop / Cancel current challenge
    if data.startswith("ch_stop_"):
        chid = int(data.split("_")[2])
        if not await is_group_admin(client, chat_id, user_id):
            await cq.answer("❌ Maqsadni faqat guruh adminlari to'xtatishi mumkin!", show_alert=True)
            return
            
        async with get_db_connection() as db:
            await db.execute(
                "UPDATE group_challenges SET is_active = FALSE WHERE id = ?",
                (chid,)
            )
        await cq.answer("🗑 Maqsad to'xtatildi!", show_alert=True)
        try:
            await cq.message.edit_text("🗑 <b>Guruh maqsadi to'xtatildi.</b> Yangi maqsad uchun /setchallenge kiriting.", parse_mode=ParseMode.HTML)
        except Exception:
            pass
        return

