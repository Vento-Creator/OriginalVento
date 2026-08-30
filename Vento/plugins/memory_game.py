"""Memory Card Game plugin for Vento bot.
4x4 board, 8 pairs. Single-player (vs bot) and 1v1 in groups.

Security:
  - Lock after 2nd card tap until reveal/flip-back finishes
  - Server-side session stored in-memory (no client-side state)
"""
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
import random
import time
import logging

logger = logging.getLogger(__name__)

# --- Session store ---
_sessions: dict[str, dict] = {}

# --- Database integration ---
async def _ensure_memory_table():
    """Ensure memory game table exists in database"""
    try:
        from database import get_db_connection
        async with get_db_connection() as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS memory_scores (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    username TEXT,
                    moves INTEGER NOT NULL,
                    time_taken INTEGER NOT NULL,
                    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, chat_id, completed_at)
                )
            ''')
            await db.commit()
            logger.info("Memory game table ensured")
    except Exception as e:
        logger.error(f"Failed to ensure memory table: {e}")

async def _save_score(user_id: int, chat_id: int, username: str, moves: int, time_taken: int):
    """Save memory game score to database"""
    try:
        await _ensure_memory_table()
        from database import get_db_connection
        async with get_db_connection() as db:
            await db.execute('''
                INSERT INTO memory_scores (user_id, chat_id, username, moves, time_taken)
                VALUES ($1, $2, $3, $4, $5)
            ''', user_id, chat_id, username, moves, time_taken)
            await db.commit()
            logger.info(f"Saved memory score: user={user_id}, moves={moves}, time={time_taken}s")
    except Exception as e:
        logger.error(f"Failed to save memory score: {e}")

async def _fetch_leaderboard(chat_id: int, limit: int = 20):
    """Fetch top-20 leaderboard for this chat"""
    try:
        await _ensure_memory_table()
        from database import get_db_connection
        async with get_db_connection() as db:
            async with db.execute('''
                SELECT username, moves, time_taken, completed_at
                FROM memory_scores
                WHERE chat_id = $1
                ORDER BY time_taken ASC, moves ASC
                LIMIT $2
            ''', chat_id, limit) as cursor:
                rows = await cursor.fetchall()
                return [{"username": r[0], "moves": r[1], "time": r[2], "completed_at": r[3]} for r in rows]
    except Exception as e:
        logger.error(f"Failed to fetch leaderboard: {e}")
        return None

def _sid(chat_id: int, user_id: int) -> str:
    return f"{chat_id}:{user_id}"

def _new_board():
    emojis = [
        "🐵",  # monkey
        "🐶",  # dog
        "🐺",  # wolf
        "🐱",  # cat
        "🐭",  # mouse
        "🐹",  # hamster
        "🐰",  # rabbit
        "🐻",  # bear
    ]
    cards = emojis * 2
    random.shuffle(cards)
    return cards

def _keyboard(session: dict, reveal_all: bool = False, show_leaderboard: bool = False):
    rows = []
    for r in range(4):
        row = []
        for c in range(4):
            idx = r * 4 + c
            if reveal_all or idx in session["revealed"]:
                row.append(InlineKeyboardButton(session["board"][idx], callback_data=f"mem|{idx}"))
            else:
                row.append(InlineKeyboardButton("❓", callback_data=f"mem|{idx}"))
        rows.append(row)
    
    # Add menu row
    menu_row = [InlineKeyboardButton("🔙 Menu", callback_data="mem|menu")]
    if show_leaderboard:
        menu_row.append(InlineKeyboardButton("🏆 Reyting", callback_data="mem|leaderboard"))
    rows.append(menu_row)
    
    return InlineKeyboardMarkup(rows)

def _check_complete(sid: str):
    s = _sessions.get(sid)
    if not s:
        return
    if len(s["revealed"]) == 16:
        s["done"] = True

@Client.on_message(filters.command("memory") & filters.group)
async def memory_cmd(client: Client, msg: Message):
    uid = msg.from_user.id
    cid = msg.chat.id
    sid = _sid(cid, uid)
    if sid in _sessions and not _sessions[sid].get("done"):
        await msg.reply("Sizda allaqachon o'yin bor! Uni yakunlang yoki /memory_stop.")
        return
    board = _new_board()
    _sessions[sid] = {
        "board": board,
        "revealed": set(),
        "first": None,
        "locked": False,
        "done": False,
        "uid": uid,
        "started": int(time.time()),
    }
    name = msg.from_user.first_name or "O'yinchi"
    await msg.reply(
        f"Salom {name}✅\nO'yin boshlandi! Kartalarni tanlang.",
        reply_markup=_keyboard(_sessions[sid]),
    )

@Client.on_message(filters.command("memory_stop") & filters.group)
async def memory_stop(client: Client, msg: Message):
    sid = _sid(msg.chat.id, msg.from_user.id)
    _sessions.pop(sid, None)
    await msg.reply("O'yin to'xtatildi.")

@Client.on_message(filters.command("memory_leaderboard") & filters.group)
async def memory_leaderboard(client: Client, msg: Message):
    """Show memory game leaderboard for this chat"""
    chat_id = msg.chat.id
    rows = await _fetch_leaderboard(chat_id)
    
    if not rows:
        await msg.reply(
            "🏆 **Top-20 — Xotira**\n\n"
            "📭 Hozircha reyting bo'sh.\n"
            "Birinchi o'yinni boshlang: `/memory`"
        )
        return
    
    text = "🏆 **Top-20 — Xotira**\n\n"
    for i, row in enumerate(rows, 1):
        username = row["username"] or "Anonim"
        moves = row["moves"]
        time_taken = row["time_taken"]
        text += f"{i}. {username} — {moves} ta harakat, {time_taken} soniya\n"
    
    await msg.reply(text)

@Client.on_callback_query(filters.regex(r"^mem\|(\d+|menu|leaderboard)$"))
async def memory_cb(client: Client, cb: CallbackQuery):
    data = cb.data.split("|")[1]
    uid = cb.from_user.id
    cid = cb.message.chat.id
    
    # Handle leaderboard callback
    if data == "leaderboard":
        rows = await _fetch_leaderboard(cid)
        if not rows:
            await cb.answer("Hozircha reyting bo'sh.", show_alert=True)
            return
        
        text = "🏆 **Top-20 — Xotira**\n\n"
        for i, row in enumerate(rows, 1):
            username = row["username"] or "Anonim"
            moves = row["moves"]
            time_taken = row["time"]
            text += f"{i}. {username} — {moves} ta harakat, {time_taken} soniya\n"
        
        await cb.message.edit_text(text)
        await cb.answer()
        return
    
    sid = _sid(cid, uid)
    session = _sessions.get(sid)

    if not session:
        await cb.answer("O'yin topilmadi. /memory boshlang.")
        return

    if session["uid"] != uid:
        await cb.answer("Bu sizning o'yiningiz emas!")
        return

    if data == "menu":
        _sessions.pop(sid, None)
        await cb.message.delete()
        await cb.answer()
        return

    if session["locked"]:
        await cb.answer("Iltimos, kuting!")
        return

    try:
        idx = int(data)
    except ValueError:
        await cb.answer("Xato.")
        return

    if idx in session["revealed"] or idx == session.get("first"):
        await cb.answer("Allaqachon ochilgan!")
        return

    first = session.get("first")

    if first is None:
        session["first"] = idx
        await cb.answer(session["board"][idx])
        await cb.message.edit_reply_markup(_keyboard(session))
        return

    session["first"] = None
    session["locked"] = True
    first_emoji = session["board"][first]
    second_emoji = session["board"][idx]

    if first_emoji == second_emoji:
        session["revealed"].add(first)
        session["revealed"].add(idx)
        session["locked"] = False
        await cb.answer(f"Topdik! {first_emoji}")
        _check_complete(sid)
        if session.get("done"):
            # Save score to database
            time_taken = int(time.time()) - session["started"]
            username = cb.from_user.username or "Anonim"
            await _save_score(uid, cid, username, len(session["revealed"]), time_taken)
            
            await cb.message.edit_text(
                "🎉 Tabriklaymiz! Siz barcha juftliklarni topdingi!",
                reply_markup=_keyboard(session, show_leaderboard=True),
            )
        else:
            await cb.message.edit_reply_markup(_keyboard(session))
    else:
        await cb.answer(f"Mos kelmadi: {second_emoji}")
        await cb.message.edit_reply_markup(_keyboard(session, reveal_all=True))
        await client.send_chat_action(cid, "typing")
        await __import__("asyncio").sleep(2)
        await cb.message.edit_reply_markup(_keyboard(session))
        session["locked"] = False