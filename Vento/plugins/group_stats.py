"""
📊 Guruh Statistikasi va Top Faollar Tizimi

Xususiyatlar:
  • Guruhdagi barcha xabarlar aktivligi hisoblab boriladi.
  • Bugungi, haftalik va barcha davrlar bo'yicha statistikani ko'rish.
  • /stats, /gstats, /top20 buyruqlari.
  • Adminlar uchun sozlamalar paneli: /statssettings yoki /statset.
  • Sozlamalar: Botlarni ignor qilish, Adminlarni ignor qilish, Min. xabar uzunligi, Top N hajmi.
"""

import asyncio
from datetime import datetime
import logging
import time
from typing import Tuple, List, Dict, Any

from pyrogram import Client, filters, ContinuePropagation
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from database import get_db_connection

logger = logging.getLogger(__name__)

_tables_initialized = False
_db_lock = asyncio.Lock()
_settings_cache: Dict[int, dict] = {}


async def _ensure_stats_tables():
    global _tables_initialized
    if _tables_initialized:
        return
    async with _db_lock:
        if _tables_initialized:
            return
        try:
            async with get_db_connection() as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS group_user_activity (
                        chat_id BIGINT,
                        user_id BIGINT,
                        first_name TEXT,
                        username TEXT,
                        daily_messages INT DEFAULT 0,
                        weekly_messages INT DEFAULT 0,
                        total_messages INT DEFAULT 0,
                        last_msg_date TEXT,
                        last_week_number INT,
                        last_active_time BIGINT,
                        PRIMARY KEY (chat_id, user_id)
                    )
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS group_stats_settings (
                        chat_id BIGINT PRIMARY KEY,
                        is_enabled BOOLEAN DEFAULT TRUE,
                        ignore_bots BOOLEAN DEFAULT TRUE,
                        ignore_admins BOOLEAN DEFAULT FALSE,
                        top_limit INT DEFAULT 20,
                        min_msg_len INT DEFAULT 1
                    )
                """)
                await db.commit()
            _tables_initialized = True
            logger.info("Group activity DB tables initialized.")
        except Exception as e:
            logger.error(f"Group activity DB init error: {e}")


async def get_stats_settings(chat_id: int) -> dict:
    await _ensure_stats_tables()
    if chat_id in _settings_cache:
        return _settings_cache[chat_id]

    async with get_db_connection() as db:
        async with db.execute(
            "SELECT is_enabled, ignore_bots, ignore_admins, top_limit, min_msg_len "
            "FROM group_stats_settings WHERE chat_id = ?",
            (chat_id,)
        ) as cursor:
            row = await cursor.fetchone()

    if row:
        settings = {
            "is_enabled": bool(row[0]),
            "ignore_bots": bool(row[1]),
            "ignore_admins": bool(row[2]),
            "top_limit": int(row[3]),
            "min_msg_len": int(row[4]),
        }
    else:
        settings = {
            "is_enabled": True,
            "ignore_bots": True,
            "ignore_admins": False,
            "top_limit": 20,
            "min_msg_len": 1,
        }

    _settings_cache[chat_id] = settings
    return settings


async def update_stats_settings(chat_id: int, **kwargs):
    current = await get_stats_settings(chat_id)
    current.update(kwargs)
    _settings_cache[chat_id] = current

    async with get_db_connection() as db:
        await db.execute("""
            INSERT INTO group_stats_settings 
            (chat_id, is_enabled, ignore_bots, ignore_admins, top_limit, min_msg_len)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                is_enabled = EXCLUDED.is_enabled,
                ignore_bots = EXCLUDED.ignore_bots,
                ignore_admins = EXCLUDED.ignore_admins,
                top_limit = EXCLUDED.top_limit,
                min_msg_len = EXCLUDED.min_msg_len
        """, (
            chat_id,
            current["is_enabled"],
            current["ignore_bots"],
            current["ignore_admins"],
            current["top_limit"],
            current["min_msg_len"]
        ))
        await db.commit()


async def is_group_admin(client: Client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False


def get_current_date_and_week() -> Tuple[str, int]:
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    year, week_num, _ = now.isocalendar()
    week_id = year * 100 + week_num
    return date_str, week_id


@Client.on_message(filters.group & ~filters.service, group=12)
async def track_group_user_activity(client: Client, message: Message):
    """Guruh xabarlari asosida foydalanuvchilar aktivligini hisoblash"""
    if not message.from_user or not message.chat:
        raise ContinuePropagation

    chat_id = message.chat.id
    user_id = message.from_user.id
    settings = await get_stats_settings(chat_id)

    if not settings["is_enabled"]:
        raise ContinuePropagation

    # Botlarni ignor qilish sozlamasi
    if settings["ignore_bots"] and message.from_user.is_bot:
        raise ContinuePropagation

    # Min. xabar uzunligi sozlamasi
    text_content = (message.text or message.caption or "").strip()
    if len(text_content) < settings["min_msg_len"] and not (
        message.photo or message.video or message.document or message.sticker or message.voice
    ):
        raise ContinuePropagation

    # Adminlarni ignor qilish sozlamasi
    if settings["ignore_admins"]:
        if await is_group_admin(client, chat_id, user_id):
            raise ContinuePropagation

    first_name = message.from_user.first_name or "Foydalanuvchi"
    username = message.from_user.username or ""
    now_ts = int(time.time())

    cur_date, cur_week = get_current_date_and_week()

    try:
        async with get_db_connection() as db:
            async with db.execute(
                "SELECT daily_messages, weekly_messages, total_messages, last_msg_date, last_week_number "
                "FROM group_user_activity WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            ) as cursor:
                row = await cursor.fetchone()

            if row:
                d_msgs, w_msgs, t_msgs, last_date, last_week = row
                
                new_d_msgs = (d_msgs + 1) if last_date == cur_date else 1
                new_w_msgs = (w_msgs + 1) if last_week == cur_week else 1
                new_t_msgs = t_msgs + 1

                await db.execute("""
                    UPDATE group_user_activity
                    SET first_name = ?, username = ?, daily_messages = ?, weekly_messages = ?,
                        total_messages = ?, last_msg_date = ?, last_week_number = ?, last_active_time = ?
                    WHERE chat_id = ? AND user_id = ?
                """, (
                    first_name, username, new_d_msgs, new_w_msgs,
                    new_t_msgs, cur_date, cur_week, now_ts,
                    chat_id, user_id
                ))
            else:
                await db.execute("""
                    INSERT INTO group_user_activity 
                    (chat_id, user_id, first_name, username, daily_messages, weekly_messages, total_messages, last_msg_date, last_week_number, last_active_time)
                    VALUES (?, ?, ?, ?, 1, 1, 1, ?, ?, ?)
                """, (
                    chat_id, user_id, first_name, username, cur_date, cur_week, now_ts
                ))
            await db.commit()
    except Exception as e:
        logger.error(f"Error tracking group activity: {e}")

    raise ContinuePropagation


async def build_stats_data(chat_id: int, mode: str = "week") -> Tuple[str, InlineKeyboardMarkup]:
    """Statistika va Top-N xabari hamda tugmalarini shakllantirish"""
    settings = await get_stats_settings(chat_id)
    top_limit = settings["top_limit"]
    cur_date, cur_week = get_current_date_and_week()

    if mode == "today":
        period_title = f"Bugun ({cur_date})"
        where_clause = "WHERE chat_id = ? AND last_msg_date = ?"
        params = (chat_id, cur_date)
        order_col = "daily_messages"
    elif mode == "all":
        period_title = "Barcha davrlar"
        where_clause = "WHERE chat_id = ?"
        params = (chat_id,)
        order_col = "total_messages"
    else:  # week
        mode = "week"
        period_title = "Shu hafta"
        where_clause = "WHERE chat_id = ? AND last_week_number = ?"
        params = (chat_id, cur_week)
        order_col = "weekly_messages"

    async with get_db_connection() as db:
        # Overall stats
        async with db.execute(
            f"SELECT SUM({order_col}), COUNT(DISTINCT user_id) FROM group_user_activity {where_clause}",
            params
        ) as cursor:
            tot_row = await cursor.fetchone()
            total_msgs = (tot_row[0] if tot_row and tot_row[0] is not None else 0)
            active_users = (tot_row[1] if tot_row and tot_row[1] is not None else 0)

        # Top N users query
        async with db.execute(
            f"SELECT user_id, first_name, username, {order_col} "
            f"FROM group_user_activity {where_clause} AND {order_col} > 0 ORDER BY {order_col} DESC LIMIT ?",
            (*params, top_limit)
        ) as cursor:
            rows = await cursor.fetchall()

    medals = [
        "🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟",
        "1️⃣1️⃣", "1️⃣2️⃣", "1️⃣3️⃣", "1️⃣4️⃣", "1️⃣5️⃣", "1️⃣6️⃣", "1️⃣7️⃣", "1️⃣8️⃣", "1️⃣9️⃣", "2️⃣0️⃣"
    ]

    lines = [
        f"📊 **GURUH STATISTIKASI VA TOP-{top_limit} FAOLLAR**\n",
        f"🗓 **Davr:** {period_title}",
        f"💬 **Jami xabarlar:** `{total_msgs:,}` ta",
        f"👥 **Faol a'zolar:** `{active_users}` kishi\n",
        f"🏆 **TOP-{top_limit} FAOL A'ZOLAR:**"
    ]

    if not rows:
        lines.append("<i>Ushbu davrda hali aktiv a'zolar yo'q.</i>")
    else:
        for idx, r in enumerate(rows):
            u_id, fn, un, count = r
            medal = medals[idx] if idx < len(medals) else f"{idx+1}."
            name = fn or f"User {u_id}"
            if un:
                name_str = f"[{name}](https://t.me/{un})"
            else:
                name_str = f"[{name}](tg://user?id={u_id})"
            lines.append(f"{medal} {name_str} — `{count}` ta xabar")

    lines.append("\n👇 *Davrni tanlash uchun quyidagi tugmalardan foydalaning:*")

    today_btn = "✅ Bugun" if mode == "today" else "📅 Bugun"
    week_btn = "✅ Shu hafta" if mode == "week" else "🗓 Shu hafta"
    all_btn = "✅ Barchasi" if mode == "all" else "📊 Barchasi"

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(today_btn, callback_data="gstats_mode_today"),
            InlineKeyboardButton(week_btn, callback_data="gstats_mode_week"),
            InlineKeyboardButton(all_btn, callback_data="gstats_mode_all"),
        ],
        [
            InlineKeyboardButton("🔄 Yangilash", callback_data=f"gstats_mode_{mode}"),
            InlineKeyboardButton("⚙️ Sozlamalar", callback_data="gstats_open_settings"),
            InlineKeyboardButton("❌ Yopish", callback_data="gstats_close"),
        ]
    ])

    return "\n".join(lines), kb


def build_settings_keyboard(settings: dict) -> InlineKeyboardMarkup:
    status_icon = "🟢 Yoqilgan" if settings["is_enabled"] else "🔴 O'chirilgan"
    bots_icon = "🟢 Ignor qilish" if settings["ignore_bots"] else "🔴 Hisobga olish"
    admins_icon = "🟢 Ignor qilish" if settings["ignore_admins"] else "🔴 Hisobga olish"

    buttons = [
        [
            InlineKeyboardButton(f"Aktivlik Tizimi: {status_icon}", callback_data="statset_toggle_enabled"),
        ],
        [
            InlineKeyboardButton(f"🤖 Botlar: {bots_icon}", callback_data="statset_toggle_bots"),
        ],
        [
            InlineKeyboardButton(f"👑 Adminlar: {admins_icon}", callback_data="statset_toggle_admins"),
        ],
        [
            InlineKeyboardButton(f"🔝 Top hajmi: Top-{settings['top_limit']}", callback_data="statset_change_limit"),
            InlineKeyboardButton(f"📏 Min. belgi: {settings['min_msg_len']} ta", callback_data="statset_change_minlen"),
        ],
        [
            InlineKeyboardButton("🗑 Reytingni tozalash", callback_data="statset_reset_confirm"),
            InlineKeyboardButton("🔙 Qaytish", callback_data="gstats_mode_week"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)


@Client.on_message(filters.command(["statssettings", "statsettings", "statset"]) & filters.group)
async def stats_settings_command(client: Client, message: Message):
    """Guruh aktivlik va reyting sozlamalari (Faqat adminlar)"""
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_group_admin(client, chat_id, user_id):
        await message.reply_text("❌ Bu buyruq faqat guruh adminlari uchun!")
        return

    settings = await get_stats_settings(chat_id)
    kb = build_settings_keyboard(settings)

    text = (
        "⚙️ **GURUH AKTIVLIGI VA REYTING SOZLAMALARI**\n\n"
        "Quyidagi tugmalar orqali aktivlik hisob-kitobini sozlashingiz mumkin:"
    )

    await message.reply_text(text, reply_markup=kb)


@Client.on_callback_query(filters.regex(r"^gstats_"))
async def group_stats_callback(client: Client, cq: CallbackQuery):
    """Guruh statistikasi inline tugmalarini boshqarish"""
    data = cq.data
    chat_id = cq.message.chat.id

    if data == "gstats_close":
        try:
            await cq.message.delete()
        except Exception:
            pass
        return

    if data == "gstats_open_settings":
        if not await is_group_admin(client, chat_id, cq.from_user.id):
            await cq.answer("❌ Faqat guruh adminlari sozlamalarga kirishi mumkin!", show_alert=True)
            return

        settings = await get_stats_settings(chat_id)
        kb = build_settings_keyboard(settings)
        text = (
            "⚙️ **GURUH AKTIVLIGI VA REYTING SOZLAMALARI**\n\n"
            "Quyidagi tugmalar orqali aktivlik hisob-kitobini sozlashingiz mumkin:"
        )
        try:
            await cq.message.edit_text(text, reply_markup=kb)
        except Exception:
            pass
        await cq.answer()
        return

    if data.startswith("gstats_mode_"):
        mode = data.replace("gstats_mode_", "")
        text, kb = await build_stats_data(chat_id, mode=mode)
        try:
            await cq.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
            await cq.answer("Statistika yangilandi!")
        except Exception as e:
            await cq.answer()


@Client.on_callback_query(filters.regex(r"^statset_"))
async def stats_settings_callback(client: Client, cq: CallbackQuery):
    """Sozlamalar paneli callback tugmalari"""
    chat_id = cq.message.chat.id
    user_id = cq.from_user.id

    if not await is_group_admin(client, chat_id, user_id):
        await cq.answer("❌ Faqat guruh adminlari sozlamalarni o'zgartira oladi!", show_alert=True)
        return

    data = cq.data
    settings = await get_stats_settings(chat_id)

    if data == "statset_toggle_enabled":
        new_val = not settings["is_enabled"]
        await update_stats_settings(chat_id, is_enabled=new_val)
        status_txt = "yoqildi" if new_val else "o'chirildi"
        await cq.answer(f"Aktivlik tizimi {status_txt}")

    elif data == "statset_toggle_bots":
        new_val = not settings["ignore_bots"]
        await update_stats_settings(chat_id, ignore_bots=new_val)
        status_txt = "ignor qilinadi" if new_val else "hisobga olinadi"
        await cq.answer(f"Botlar xabari {status_txt}")

    elif data == "statset_toggle_admins":
        new_val = not settings["ignore_admins"]
        await update_stats_settings(chat_id, ignore_admins=new_val)
        status_txt = "ignor qilinadi" if new_val else "hisobga olinadi"
        await cq.answer(f"Adminlar xabari {status_txt}")

    elif data == "statset_change_limit":
        limits = [10, 15, 20, 30, 50]
        cur = settings["top_limit"]
        idx = (limits.index(cur) + 1) % len(limits) if cur in limits else 0
        new_limit = limits[idx]
        await update_stats_settings(chat_id, top_limit=new_limit)
        await cq.answer(f"Top reyting hajmi: Top-{new_limit} qilib belgilandi")

    elif data == "statset_change_minlen":
        lens = [1, 3, 5, 10]
        cur = settings["min_msg_len"]
        idx = (lens.index(cur) + 1) % len(lens) if cur in lens else 0
        new_len = lens[idx]
        await update_stats_settings(chat_id, min_msg_len=new_len)
        await cq.answer(f"Min. xabar uzunligi: {new_len} belgi")

    elif data == "statset_reset_confirm":
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Ha, tozalansin", callback_data="statset_reset_do"),
                InlineKeyboardButton("❌ Bekor qilish", callback_data="statset_reset_cancel"),
            ]
        ])
        await cq.message.edit_text(
            "⚠️ **DIQQAT!**\n\n"
            "Guruhning barcha aktivlik statistikasi va xabarlar sonini 0 ga tushirmoqchimisiz?",
            reply_markup=kb
        )
        await cq.answer()
        return

    elif data == "statset_reset_cancel":
        await cq.answer("Bekor qilindi")

    elif data == "statset_reset_do":
        async with get_db_connection() as db:
            await db.execute("DELETE FROM group_user_activity WHERE chat_id = ?", (chat_id,))
            await db.commit()
        await cq.answer("Guruh statistikasi tozalandi!", show_alert=True)

    # Re-render settings screen
    current_settings = await get_stats_settings(chat_id)
    kb = build_settings_keyboard(current_settings)
    text = (
        "⚙️ **GURUH AKTIVLIGI VA REYTING SOZLAMALARI**\n\n"
        "Quyidagi tugmalar orqali aktivlik hisob-kitobini sozlashingiz mumkin:"
    )
    try:
        await cq.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass
