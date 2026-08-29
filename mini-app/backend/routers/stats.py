import time
from fastapi import APIRouter, Depends
from auth import get_current_user
from db import get_pool

router = APIRouter()


@router.get("/")
async def get_user_stats(user: dict = Depends(get_current_user)):
    """Foydalanuvchi o'z statistikasini ko'radi."""
    uid = user["id"]
    pool = await get_pool()

    # Faol jarayonlar (utag timers)
    timers = await pool.fetch(
        """SELECT id, chat_id, message_text, interval_minutes, is_active, last_sent, created_at
           FROM utag_timers WHERE user_id = $1 AND is_active = true""",
        uid
    )
    timers = [dict(r) for r in timers]

    # Scraped guruhlar soni
    scraped_groups = (await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM scraped_groups WHERE owner_id = $1", uid
    ))["cnt"]

    # Scraped a'zolar soni
    scraped_members = (await pool.fetchrow(
        """SELECT COUNT(*) as cnt FROM scraped_members sm
           JOIN scraped_groups sg ON sg.group_id = sm.group_id
           WHERE sg.owner_id = $1""",
        uid
    ))["cnt"]

    # To'lovlar soni
    pay_row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt, COALESCE(SUM(amount), 0) as total FROM payments WHERE user_id = $1 AND status = 'paid'",
        uid
    )
    payment_count = pay_row["cnt"] or 0
    stars_spent = pay_row["total"] or 0

    return {
        "active_timers": timers,
        "active_timer_count": len(timers),
        "scraped_groups": scraped_groups,
        "scraped_members": scraped_members,
        "payment_count": payment_count,
        "stars_spent": stars_spent,
    }
