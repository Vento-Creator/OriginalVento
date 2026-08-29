"""
SQLite → Supabase (PostgreSQL) migratsiya skripti.
Hozirgi bot_database.db dagi barcha ma'lumotlarni Supabase ga ko'chiradi.

Ishlatish:
  python migrate_to_supabase.py

Zaruriy o'zgaruvchilar (.env yoki qo'lda):
  DATABASE_URL=postgresql://...   (Supabase connection string)
  SQLITE_PATH=../../Vento/data/database/bot_database.db
"""
import asyncio
import asyncpg
import sqlite3
import os
import sys

# .env dan o'qish
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DATABASE_URL = os.getenv("DATABASE_URL", "")
SQLITE_PATH = os.getenv("SQLITE_PATH", os.path.join(
    os.path.dirname(__file__), "..", "..", "Vento", "data", "database", "bot_database.db"
))

# Ko'chirilishi kerak bo'lgan jadvallar va ularning ustunlari
TABLES = {
    "users": ["user_id", "expiry_date", "warned", "username", "first_name", "is_active"],
    "scraped_groups": ["group_id", "group_title", "date_scraped", "owner_id"],
    "scraped_members": ["user_id", "username", "first_name", "group_id"],
    "stats": ["key", "value"],
    "banned_users": ["user_id", "violation_count"],
    "free_users": ["user_id"],
    "payments": ["payment_id", "user_id", "amount", "currency", "invoice_payload",
                  "status", "grant_status", "granted_expiry", "created_at", "granted_at"],
    "known_users": ["user_id", "username", "first_name", "joined_date", "last_seen", "language"],
    "updates": ["id", "title", "content", "created_at", "created_by"],
    "read_updates": ["user_id", "update_id"],
    "admin_logs": ["id", "admin_id", "action", "target_id", "details", "timestamp"],
    "user_preferences": ["user_id", "disable_update_notifications",
                          "utag_atag_cmd", "utag_stop_cmd", "utag_pause_cmd", "utag_resume_cmd"],
    "user_limits": ["user_id", "last_nakrutka_time"],
    "user_actions": ["id", "user_id", "action", "timestamp"],
    "admins": ["admin_id", "joined_date", "admin_date",
               "can_add_admin", "can_ban", "can_clear_db", "can_broadcast", "can_manage_users"],
    "massdm_progress": ["user_id", "group_id", "last_index", "updated_at"],
    "massdm_settings": ["user_id", "auto_stop_on_high_risk"],
    "massdm_auto_stopped": ["stop_key", "user_id", "group_id", "resume_after",
                             "reason", "message_to_copy_id", "delay_hours", "created_at"],
    "chat_messages": ["id", "sender_id", "receiver_id", "message", "photo_file_id", "timestamp", "is_read"],
    "chat_blocks": ["blocker_id", "blocked_id", "timestamp"],
    "chat_mutes": ["muter_id", "muted_id", "timestamp"],
    "chat_terms_accepted": ["user_id", "accepted_at"],
    "utag_timers": ["id", "user_id", "chat_id", "message_text", "interval_minutes",
                     "repeat_count", "repeat_delay", "is_active", "last_sent", "created_at"],
    "utag_custom_commands": ["user_id", "command", "message", "created_at"],
}


def read_sqlite(table: str, columns: list) -> list:
    """SQLite jadvaldan barcha qatorlarni o'qish."""
    sqlite_path = os.path.normpath(SQLITE_PATH)
    if not os.path.exists(sqlite_path):
        print(f"  ⚠️  SQLite fayl topilmadi: {sqlite_path}")
        return []

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Jadval mavjudligini tekshirish
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    if not cursor.fetchone():
        print(f"  ⚠️  Jadval topilmadi: {table}")
        conn.close()
        return []

    # Mavjud ustunlarni aniqlash
    cursor.execute(f"PRAGMA table_info({table})")
    existing_cols = {info[1] for info in cursor.fetchall()}
    valid_cols = [c for c in columns if c in existing_cols]

    if not valid_cols:
        conn.close()
        return []

    cols_str = ", ".join(valid_cols)
    cursor.execute(f"SELECT {cols_str} FROM {table}")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return rows


async def insert_to_pg(pool, table: str, columns: list, rows: list):
    """PostgreSQL ga ma'lumotlarni yozish."""
    if not rows:
        print(f"  ⏭️  {table}: ma'lumot yo'q, o'tkazildi")
        return

    # Faqat mavjud ustunlarni ishlatish
    valid_cols = [c for c in columns if c in rows[0]]
    if not valid_cols:
        return

    cols_str = ", ".join(valid_cols)
    placeholders = ", ".join(f"${i+1}" for i in range(len(valid_cols)))

    # ON CONFLICT DO NOTHING — takroriy yozuvlarni o'tkazib yuborish
    query = f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

    inserted = 0
    errors = 0
    for row in rows:
        values = []
        for col in valid_cols:
            val = row.get(col)
            if col == "warned" and val is not None:
                val = bool(val)
            values.append(val)
        try:
            await pool.execute(query, *values)
            inserted += 1
        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"    ❌ Xatolik: {e}")

    print(f"  ✅ {table}: {inserted} qator ko'chirildi" + (f" ({errors} xatolik)" if errors else ""))


async def run_schema(pool):
    """schema.sql ni ishga tushirish."""
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    if not os.path.exists(schema_path):
        print("❌ schema.sql topilmadi!")
        return False

    with open(schema_path, "r", encoding="utf-8") as f:
        sql = f.read()

    await pool.execute(sql)
    print("✅ Schema yaratildi (jadvallar)")
    return True


async def migrate():
    """Asosiy migratsiya funksiyasi."""
    if not DATABASE_URL:
        print("❌ DATABASE_URL o'rnatilmagan!")
        print("   .env faylga DATABASE_URL=postgresql://... qo'shing")
        sys.exit(1)

    print(f"📂 SQLite: {os.path.normpath(SQLITE_PATH)}")
    print(f"🌐 PostgreSQL: {DATABASE_URL[:50]}...")
    print()

    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5, ssl="require", statement_cache_size=0)

    # 1. Schema yaratish
    print("=" * 50)
    print("1️⃣  Schema yaratilmoqda...")
    if not await run_schema(pool):
        await pool.close()
        sys.exit(1)

    # 2. Ma'lumotlarni ko'chirish
    print()
    print("=" * 50)
    print("2️⃣  Ma'lumotlar ko'chirilmoqda...")
    print()

    for table, columns in TABLES.items():
        rows = read_sqlite(table, columns)
        await insert_to_pg(pool, table, columns, rows)

    await pool.close()

    print()
    print("=" * 50)
    print("🎉 Migratsiya muvaffaqiyatli yakunlandi!")
    print()
    print("Keyingi qadamlar:")
    print("  1. Supabase dashboard'dan ma'lumotlarni tekshiring")
    print("  2. Backend va Frontendni deploy qiling")


if __name__ == "__main__":
    asyncio.run(migrate())
