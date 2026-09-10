import sqlite3
import aiosqlite
import json
import logging
import time
import random
import string
from typing import List, Dict, Optional
from config import DB_PATH
import sqlite3
import aiosqlite
import json
import logging
import time
from typing import List, Dict, Optional
from config import DB_PATH

logger = logging.getLogger(__name__)


async def init_db():
    """Database sxemasini yaratish va tayyorlash."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                date_added INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bazas (
                baza_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT,
                created_at INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS baza_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                baza_id INTEGER,
                username TEXT,
                tg_user_id INTEGER,
                first_name TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                utag_speed REAL DEFAULT 1.5,
                utag_typing INTEGER DEFAULT 1,
                utag_auto_stop INTEGER DEFAULT 0,
                utag_delete_timer INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS utag_timers (
                timer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                text TEXT,
                interval_minutes INTEGER,
                is_active INTEGER DEFAULT 1,
                last_run INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER,
                added_at INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scraped_groups (
                group_id TEXT PRIMARY KEY,
                group_title TEXT,
                date_scraped INTEGER,
                owner_id INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scraped_members (
                user_id INTEGER,
                username TEXT,
                first_name TEXT,
                group_id TEXT,
                PRIMARY KEY (user_id, group_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS banned_users (
                user_id INTEGER PRIMARY KEY,
                violation_count INTEGER DEFAULT 1,
                banned_at INTEGER,
                banned_by INTEGER,
                reason TEXT
            )
        """)
        await db.commit()
    logger.info("Vento_mini database initialize bo'ldi.")


async def register_user(user_id: int, username: str = None, first_name: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (user_id, username, first_name, date_added)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name
        """,
            (user_id, username, first_name, int(time.time())),
        )
        await db.commit()


# --- Baza Management ---

async def create_baza(user_id: int, name: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO bazas (user_id, name, created_at) VALUES (?, ?, ?)",
            (user_id, name, int(time.time())),
        )
        await db.commit()
        return cursor.lastrowid


async def add_baza_members(baza_id: int, members: List[Dict]):
    """members: list of dicts [{'username': ..., 'tg_user_id': ..., 'first_name': ...}]"""
    async with aiosqlite.connect(DB_PATH) as db:
        rows = [
            (
                baza_id,
                m.get("username"),
                m.get("tg_user_id"),
                m.get("first_name"),
            )
            for m in members
        ]
        await db.executemany(
            """
            INSERT INTO baza_members (baza_id, username, tg_user_id, first_name)
            VALUES (?, ?, ?, ?)
        """,
            rows,
        )
        await db.commit()


async def get_user_bazas(user_id: int) -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT b.baza_id, b.name, b.created_at, COUNT(m.id) as count
            FROM bazas b
            LEFT JOIN baza_members m ON b.baza_id = m.baza_id
            WHERE b.user_id = ?
            GROUP BY b.baza_id
            ORDER BY b.baza_id DESC
        """,
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_baza_members(baza_id: int) -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT username, tg_user_id, first_name FROM baza_members WHERE baza_id = ?",
            (baza_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def delete_baza(baza_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM baza_members WHERE baza_id = ?", (baza_id,)
        )
        cursor = await db.execute(
            "DELETE FROM bazas WHERE baza_id = ? AND user_id = ?",
            (baza_id, user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


# --- Settings ---

async def get_user_settings_db(user_id: int) -> Dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT utag_speed, utag_typing, utag_auto_stop, utag_delete_timer FROM user_settings WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return {
                "utag_speed": 1.5,
                "utag_typing": 1,
                "utag_auto_stop": 0,
                "utag_delete_timer": 0,
            }


async def save_user_setting_db(user_id: int, key: str, value):
    valid_keys = [
        "utag_speed",
        "utag_typing",
        "utag_auto_stop",
        "utag_delete_timer",
    ]
    if key not in valid_keys:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"""
            INSERT INTO user_settings (user_id, {key})
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET {key} = excluded.{key}
        """,
            (user_id, value),
        )
        await db.commit()


# --- UTAG Timers ---

async def add_utag_timer(user_id: int, chat_id: int, text: str, interval_minutes: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO utag_timers (user_id, chat_id, text, interval_minutes, is_active, last_run)
            VALUES (?, ?, ?, ?, 1, 0)
        """,
            (user_id, chat_id, text, interval_minutes),
        )
        await db.commit()
        return cursor.lastrowid


async def get_user_timers(user_id: int) -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM utag_timers WHERE user_id = ?", (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def delete_timer_db(timer_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM utag_timers WHERE timer_id = ? AND user_id = ?",
            (timer_id, user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


# --- Admin Management ---

async def is_admin(user_id: int) -> bool:
    from config import ADMIN_IDS
    if user_id in ADMIN_IDS:
        return True
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return bool(row)


async def add_admin_db(user_id: int, added_by: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO admins (user_id, added_by, added_at) VALUES (?, ?, ?)",
            (user_id, added_by, int(time.time()))
        )
        await db.commit()
        return True


async def remove_admin_db(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        await db.commit()
        return cursor.rowcount > 0


async def get_all_admins_db() -> List[Dict]:
    from config import ADMIN_IDS
    admins_dict = {}

# --- Scraped Groups (Bazalar) — original Vento uslubida ---

async def generate_unique_group_id():
    """10 xonali unikal ID (faqat raqam) yaratish"""
    async with aiosqlite.connect(DB_PATH) as db:
        while True:
            new_id = ''.join(random.choices(string.digits, k=10))
            async with db.execute("SELECT 1 FROM scraped_groups WHERE group_id = ?", (new_id,)) as cursor:
                if not await cursor.fetchone():
                    return new_id


async def add_scraped_group(group_id: str, group_title: str, date_scraped: int, owner_id: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO scraped_groups (group_id, group_title, date_scraped, owner_id) VALUES (?, ?, ?, ?)",
            (group_id, group_title, date_scraped, owner_id),
        )
        await db.commit()


async def add_scraped_members_batch(batch: List[tuple]):
    """batch: [(user_id, username, first_name, group_id), ...]"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            """
            INSERT INTO scraped_members (user_id, username, first_name, group_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (user_id, group_id) DO NOTHING
        """,
            batch,
        )
        await db.commit()


async def add_scraped_member(user_id: int, username: str, first_name: str, group_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO scraped_members (user_id, username, first_name, group_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (user_id, group_id) DO NOTHING
        """,
            (user_id, username, first_name, group_id),
        )
        await db.commit()


async def add_manual_members(group_id: str, members: List[Dict]):
    """Qo'lda a'zolar qo'shish"""
    rows = [
        (m.get("user_id"), m.get("username"), m.get("first_name", ""), group_id)
        for m in members
    ]
    await add_scraped_members_batch(rows)


async def get_group_id_by_title(group_title: str, owner_id: int = None):
    """Guruh nomiga (va owner_id ga) qarab bazadagi ID ni qaytaradi (merge uchun)"""
    async with aiosqlite.connect(DB_PATH) as db:
        if owner_id is not None:
            async with db.execute(
                "SELECT group_id FROM scraped_groups WHERE group_title = ? AND owner_id = ?",
                (group_title, owner_id),
            ) as cursor:
                row = await cursor.fetchone()
        else:
            async with db.execute(
                "SELECT group_id FROM scraped_groups WHERE group_title = ?",
                (group_title,),
            ) as cursor:
                row = await cursor.fetchone()
        return row[0] if row else None


async def update_group_date(group_id: str, date_scraped: int):
    """Guruh oxirgi scrape sanasini yangilash"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE scraped_groups SET date_scraped = ? WHERE group_id = ?",
            (date_scraped, group_id),
        )
        await db.commit()


async def get_all_scraped_groups(owner_id: int = None) -> List[Dict]:
    """Guruhlar ro'yxati. owner_id berilsa - faqat o'shaning bazalari."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if owner_id is not None:
            async with db.execute(
                "SELECT group_id, group_title, date_scraped, owner_id FROM scraped_groups WHERE owner_id = ? ORDER BY date_scraped DESC",
                (owner_id,),
            ) as cursor:
                rows = await cursor.fetchall()
        else:
            async with db.execute(
                "SELECT group_id, group_title, date_scraped, owner_id FROM scraped_groups ORDER BY date_scraped DESC"
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_group_info(group_id: str) -> Optional[Dict]:
    """Bitta guruh haqida to'liq ma'lumot"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT group_id, group_title, date_scraped, owner_id FROM scraped_groups WHERE group_id = ?",
            (group_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_group_member_count(group_id: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM scraped_members WHERE group_id = ?", (group_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def get_members_by_group_paginated(group_id: str, offset: int = 0, limit: int = 50) -> List[Dict]:
    """Guruh a'zolarini sahifalab olish"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id, username, first_name FROM scraped_members WHERE group_id = ? LIMIT ? OFFSET ?",
            (group_id, limit, offset),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def delete_scraped_group(group_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM scraped_members WHERE group_id = ?", (group_id,))
        await db.execute("DELETE FROM scraped_groups WHERE group_id = ?", (group_id,))
        await db.commit()


async def clear_group_members(group_id: str) -> int:
    """Bazadagi a'zolarni tozalash (bazaning o'zi qoladi)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM scraped_members WHERE group_id = ?", (group_id,))
        await db.commit()
        return cursor.rowcount or 0
    for aid in ADMIN_IDS:
        admins_dict[aid] = {"user_id": aid, "added_by": 0, "is_env": True}

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id, added_by, added_at FROM admins") as cursor:
            rows = await cursor.fetchall()
            for r in rows:
                aid = r["user_id"]
                if aid not in admins_dict:
                    admins_dict[aid] = {"user_id": aid, "added_by": r["added_by"], "added_at": r["added_at"], "is_env": False}

    return list(admins_dict.values())


# ============================================================
# ADMIN: Foydalanuvchilar ro'yxati, Ban / Unban
# ============================================================


async def get_all_registered_user_ids(limit: int = 50, offset: int = 0):
    """Botga a'zo bo'lgan foydalanuvchilar ro'yxati (sahifalangan)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id, username, first_name, date_added FROM users ORDER BY date_added DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_all_users_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) as cnt FROM users") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def search_users(query: str, limit: int = 20):
    """Foydalanuvchilarni username yoki first_name bo'yicha qidirish."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        like_q = f"%{query}%"
        async with db.execute(
            "SELECT user_id, username, first_name, date_added FROM users "
            "WHERE username LIKE ? OR first_name LIKE ? OR CAST(user_id AS TEXT) LIKE ? "
            "ORDER BY date_added DESC LIMIT ?",
            (like_q, like_q, like_q, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def ban_user(user_id: int, banned_by: int, reason: str = "") -> bool:
    """Foydalanuvchini ban qilish (violation_count oshiriladi)."""
    import time as _time
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT violation_count FROM banned_users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
        count = row[0] if row else 0
        new_count = count + 1
        if count == 0:
            await db.execute(
                "INSERT INTO banned_users (user_id, violation_count, banned_at, banned_by, reason) VALUES (?, ?, ?, ?, ?)",
                (user_id, new_count, int(_time.time()), banned_by, reason),
            )
        else:
            await db.execute(
                "UPDATE banned_users SET violation_count = ?, banned_at = ?, banned_by = ?, reason = ? WHERE user_id = ?",
                (new_count, int(_time.time()), banned_by, reason, user_id),
            )
        await db.commit()
    return True


async def unban_user(user_id: int) -> bool:
    """Foydalanuvchini ban dan chiqarish."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))
        await db.commit()
    return True


async def is_user_banned(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT violation_count FROM banned_users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None


async def get_all_banned_users(limit: int = 50, offset: int = 0):
    """Ban qilingan foydalanuvchilar ro'yxati (sahifalangan)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id, violation_count, banned_at, banned_by, reason FROM banned_users "
            "ORDER BY banned_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_banned_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) as cnt FROM banned_users") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def get_admin_stats() -> dict:
    """Admin panel uchun statistika."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) as cnt FROM users") as cursor:
            total_users = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) as cnt FROM banned_users") as cursor:
            banned = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) as cnt FROM admins") as cursor:
            admins = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) as cnt FROM bazas") as cursor:
            bazas = (await cursor.fetchone())[0]
    return {
        "total_users": total_users,
        "banned": banned,
        "admins": admins,
        "bazas": bazas,
    }

