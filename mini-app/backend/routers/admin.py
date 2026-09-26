import time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
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
    search: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Barcha foydalanuvchilar ro'yxati (admin only). search= bo'lsa qidirish."""
    pool = await get_pool()
    await _require_admin(user, pool)
    offset = (page - 1) * limit

    if search and search.strip():
        q = f"%{search.strip()}%"
        rows = await pool.fetch(
            """SELECT u.user_id, u.username, u.first_name, u.expiry_date, u.is_active,
                      k.last_seen, k.language,
                      CASE WHEN b.user_id IS NOT NULL THEN 1 ELSE 0 END as is_banned,
                      CASE WHEN f.user_id IS NOT NULL THEN 1 ELSE 0 END as is_free
               FROM users u
               LEFT JOIN known_users k ON k.user_id = u.user_id
               LEFT JOIN banned_users b ON b.user_id = u.user_id
               LEFT JOIN free_users f ON f.user_id = u.user_id
               WHERE u.username ILIKE $1 OR u.first_name ILIKE $1 OR CAST(u.user_id AS TEXT) LIKE $1
               ORDER BY u.expiry_date DESC
               LIMIT $2 OFFSET $3""",
            q, limit, offset
        )
        total_row = await pool.fetchrow(
            """SELECT COUNT(*) as cnt FROM users u
               WHERE u.username ILIKE $1 OR u.first_name ILIKE $1 OR CAST(u.user_id AS TEXT) LIKE $1""",
            q
        )
    else:
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
        total_row = await pool.fetchrow("SELECT COUNT(*) as cnt FROM users")

    rows = [dict(r) for r in rows]
    total = total_row["cnt"]

    for r in rows:
        sub = build_sub_status(r.get("expiry_date") or 0, bool(r.get("is_free")))
        r["days_left"] = sub["days_left"]
        r["has_subscription"] = sub["has_subscription"]
        r["seconds_left"] = sub["seconds_left"]
        r["can_purchase"] = sub["can_purchase"]

    return {"users": rows, "total": total, "page": page, "limit": limit}


# ---------------------------------------------------------------------------
# Obuna boshqaruv endpointlari
# ---------------------------------------------------------------------------

class ExtendSubRequest(BaseModel):
    user_id: int
    days: int  # Musbat bo'lsa uzaytirish, manfiy bo'lsa qisqartirish


class ToggleFreeRequest(BaseModel):
    user_id: int
    is_free: bool


class BanUserRequest(BaseModel):
    user_id: int
    ban: bool


@router.get("/user/{target_id}")
async def get_user_detail(target_id: int, user: dict = Depends(get_current_user)):
    """Bitta foydalanuvchining to'liq ma'lumoti (admin only)."""
    pool = await get_pool()
    await _require_admin(user, pool)

    row = await pool.fetchrow(
        """SELECT u.user_id, u.username, u.first_name, u.expiry_date, u.is_active,
                  k.last_seen, k.language, k.joined_date,
                  CASE WHEN b.user_id IS NOT NULL THEN 1 ELSE 0 END as is_banned,
                  CASE WHEN f.user_id IS NOT NULL THEN 1 ELSE 0 END as is_free
           FROM users u
           LEFT JOIN known_users k ON k.user_id = u.user_id
           LEFT JOIN banned_users b ON b.user_id = u.user_id
           LEFT JOIN free_users f ON f.user_id = u.user_id
           WHERE u.user_id = $1""",
        target_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")

    r = dict(row)
    sub = build_sub_status(r.get("expiry_date") or 0, bool(r.get("is_free")))
    r.update(sub)

    # To'lovlar soni
    payment_count = (await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM payments WHERE user_id = $1 AND status = 'paid'",
        target_id
    ))["cnt"]
    r["payment_count"] = payment_count

    # So'nggi to'lovlar
    payments = await pool.fetch(
        """SELECT payment_id, amount, currency, status, created_at, granted_expiry
           FROM payments WHERE user_id = $1 ORDER BY created_at DESC LIMIT 5""",
        target_id
    )
    r["recent_payments"] = [dict(p) for p in payments]

    return r


@router.post("/extend_sub")
async def extend_subscription(body: ExtendSubRequest, user: dict = Depends(get_current_user)):
    """Foydalanuvchiga obuna kunlari qo'shish yoki kamaytirish (admin only)."""
    pool = await get_pool()
    admin = await _require_admin(user, pool)

    if body.days == 0:
        raise HTTPException(status_code=400, detail="Kunlar soni 0 bo'lishi mumkin emas")
    if abs(body.days) > 365:
        raise HTTPException(status_code=400, detail="Maksimum 365 kun")

    target_id = body.user_id
    now = int(time.time())

    # Hozirgi expiry
    row = await pool.fetchrow("SELECT expiry_date FROM users WHERE user_id = $1", target_id)
    if not row:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")

    current_expiry = row["expiry_date"] or 0
    # Agar muddat o'tgan bo'lsa — hozirgi vaqtdan boshlab uzaytirish
    base = max(current_expiry, now) if body.days > 0 else current_expiry
    new_expiry = base + (body.days * 86400)
    # Manfiy natijadan himoya
    if new_expiry < 0:
        new_expiry = 0

    await pool.execute(
        "UPDATE users SET expiry_date = $1 WHERE user_id = $2",
        new_expiry, target_id
    )

    # Admin log
    await pool.execute(
        """INSERT INTO admin_logs (admin_id, action, target_id, details, timestamp)
           VALUES ($1, $2, $3, $4, $5)""",
        user["id"],
        "extend_sub" if body.days > 0 else "reduce_sub",
        target_id,
        f"{body.days:+d} kun → {new_expiry}",
        now
    )

    sub = build_sub_status(new_expiry, False)
    return {
        "success": True,
        "user_id": target_id,
        "days_added": body.days,
        "new_expiry": new_expiry,
        "days_left": sub["days_left"],
        "has_subscription": sub["has_subscription"]
    }


@router.post("/toggle_free")
async def toggle_free_user(body: ToggleFreeRequest, user: dict = Depends(get_current_user)):
    """Foydalanuvchini bepul qilish / bepuldan olib tashlash (admin only)."""
    pool = await get_pool()
    await _require_admin(user, pool)

    target_id = body.user_id
    now = int(time.time())

    # Foydalanuvchi borligini tekshirish
    exists = await pool.fetchrow("SELECT user_id FROM users WHERE user_id = $1", target_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")

    if body.is_free:
        await pool.execute(
            "INSERT INTO free_users (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
            target_id
        )
    else:
        await pool.execute("DELETE FROM free_users WHERE user_id = $1", target_id)

    # Admin log
    await pool.execute(
        """INSERT INTO admin_logs (admin_id, action, target_id, details, timestamp)
           VALUES ($1, $2, $3, $4, $5)""",
        user["id"],
        "set_free" if body.is_free else "remove_free",
        target_id,
        f"is_free = {body.is_free}",
        now
    )

    return {
        "success": True,
        "user_id": target_id,
        "is_free": body.is_free
    }


@router.post("/ban_user")
async def ban_user(body: BanUserRequest, user: dict = Depends(get_current_user)):
    """Foydalanuvchini ban / unban qilish (admin only)."""
    pool = await get_pool()
    await _require_admin(user, pool)

    target_id = body.user_id
    now = int(time.time())

    if body.ban:
        await pool.execute(
            "INSERT INTO banned_users (user_id, violation_count) VALUES ($1, 1) ON CONFLICT DO NOTHING",
            target_id
        )
    else:
        await pool.execute("DELETE FROM banned_users WHERE user_id = $1", target_id)

    # Admin log
    await pool.execute(
        """INSERT INTO admin_logs (admin_id, action, target_id, details, timestamp)
           VALUES ($1, $2, $3, $4, $5)""",
        user["id"],
        "ban" if body.ban else "unban",
        target_id,
        f"ban = {body.ban}",
        now
    )

    return {
        "success": True,
        "user_id": target_id,
        "is_banned": body.ban
    }


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

