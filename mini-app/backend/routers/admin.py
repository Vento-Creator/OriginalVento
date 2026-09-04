import time
from fastapi import APIRouter, Depends, HTTPException
from auth import get_current_user
from db import get_pool
from sub_status import build_sub_status

router = APIRouter()


async def _require_admin(user: dict, pool) -> dict:
    """Admin ekanligini tekshiradi, aks holda 403 qaytaradi."""
    uid = user["id"]
    admin = await pool.fetchrow(
        "SELECT * FROM admins WHERE admin_id = $1", uid
    )
    if not admin:
        raise HTTPException(status_code=403, detail="Admin ruxsati yo'q")
    return dict(admin)


@router.get("/users")
async def list_users(
    page: int = 1,
    limit: int = 20,
    user: dict = Depends(get_current_user)
):
    """Barcha foydalanuvchilar ro'yxati (admin only)."""
    pool = await get_pool()
    await _require_admin(user, pool)
    offset = (page - 1) * limit

    rows = await pool.fetch(
        """SELECT u.user_id, u.username, u.first_name, u.expiry_date, u.is_active,
                  k.last_seen, k.language,
                  CASE WHEN b.user_id IS NOT NULL THEN 1 ELSE 0 END as is_banned,
                  CASE WHEN f.user_id IS NOT NULL THEN 1 ELSE 0 END as is_free
           FROM users u
           LEFT JOIN known_users k ON k.user_id = u.user_id
           LEFT JOIN banned_users b ON b.user_id = u.user_id
           LEFT JOIN free_users f ON f.user_id = u.user_id
           ORDER BY u.expiry_date DESC
           LIMIT $1 OFFSET $2""",
        limit, offset
    )
    rows = [dict(r) for r in rows]

    total_row = await pool.fetchrow("SELECT COUNT(*) as cnt FROM users")
    total = total_row["cnt"]

    for r in rows:
        sub = build_sub_status(r.get("expiry_date") or 0, bool(r.get("is_free")))
        r["days_left"] = sub["days_left"]
        r["has_subscription"] = sub["has_subscription"]
        r["seconds_left"] = sub["seconds_left"]
        r["can_purchase"] = sub["can_purchase"]

    return {"users": rows, "total": total, "page": page, "limit": limit}


@router.get("/stats")
async def admin_stats(user: dict = Depends(get_current_user)):
    """Umumiy statistika (admin only)."""
    pool = await get_pool()
    await _require_admin(user, pool)
    now = int(time.time())

    total_users = (await pool.fetchrow("SELECT COUNT(*) as cnt FROM users"))["cnt"]
    active_subs = (await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM users WHERE expiry_date > $1", now
    ))["cnt"]
    free_users = (await pool.fetchrow("SELECT COUNT(*) as cnt FROM free_users"))["cnt"]
    banned = (await pool.fetchrow("SELECT COUNT(*) as cnt FROM banned_users"))["cnt"]
    admins = (await pool.fetchrow("SELECT COUNT(*) as cnt FROM admins"))["cnt"]
    total_payments = (await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM payments WHERE status = 'paid'"
    ))["cnt"]
    total_stars = (await pool.fetchrow(
        "SELECT COALESCE(SUM(amount), 0) as total FROM payments WHERE status = 'paid'"
    ))["total"]

    return {
        "total_users": total_users,
        "active_subscriptions": active_subs,
        "free_users": free_users,
        "banned_users": banned,
        "admin_count": admins,
        "total_payments": total_payments,
        "total_stars_earned": total_stars,
    }


@router.get("/pending")
async def pending_users(user: dict = Depends(get_current_user)):
    """Login qilgan lekin tasdiqlanmagan foydalanuvchilar."""
    pool = await get_pool()
    await _require_admin(user, pool)

    rows = await pool.fetch(
        """SELECT u.user_id, u.username, u.first_name, k.last_seen
           FROM users u
           LEFT JOIN known_users k ON k.user_id = u.user_id
           WHERE u.is_active = 0
           ORDER BY k.last_seen DESC NULLS LAST
           LIMIT 50"""
    )

    return {"pending": [dict(r) for r in rows]}
