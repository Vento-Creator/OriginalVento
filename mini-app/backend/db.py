"""
Supabase PostgreSQL uchun asinxron database ulanish moduli.
asyncpg kutubxonasidan foydalanadi.
"""
import asyncpg
import os
import logging

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")


async def get_pool():
    """Global connection pool olish."""
    if not hasattr(get_pool, "_pool") or get_pool._pool is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL environment variable o'rnatilmagan!")
        get_pool._pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=30,
            ssl="require",
            statement_cache_size=0
        )
        logger.info("PostgreSQL pool yaratildi")
    return get_pool._pool


async def close_pool():
    """Pool ni yopish."""
    if hasattr(get_pool, "_pool") and get_pool._pool:
        await get_pool._pool.close()
        get_pool._pool = None
        logger.info("PostgreSQL pool yopildi")
