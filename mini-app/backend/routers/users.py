import time
from fastapi import APIRouter, Depends, HTTPException
from auth import get_current_user
from db import get_pool

router = APIRouter()


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Telegram foydalanuvchi ma'lumotlari + bot DB holati."""
    uid = user["id"]
    pool = await get_pool()

    # Obuna holati
    row = await pool.fetchrow(
        "SELECT expiry_date, is_active, username, first_name FROM users WHERE user_id = $1",
        uid
    )

    # Ban holati
    banned = await pool.fetchrow(
        "SELECT user_id FROM banned_users WHERE user_id = $1", uid
    )

    # Free user
    free = await pool.fetchrow(
        "SELECT user_id FROM free_users WHERE user_id = $1", uid
    )

    # Admin
    admin_row = await pool.fetchrow(
        """SELECT can_add_admin, can_ban, can_clear_db, can_broadcast, can_manage_users
           FROM admins WHERE admin_id = $1""",
        uid
    )

    now = int(time.time())

    if row:
        expiry = row["expiry_date"] or 0
        is_active = bool(row["is_active"])
        days_left = max(0, (expiry - now) // 86400) if expiry > now else 0
        has_sub = expiry > now or bool(free)
    else:
        expiry = 0
        is_active = False
        days_left = 0
        has_sub = bool(free)

    return {
        "id": uid,
        "first_name": user.get("first_name", ""),
        "last_name": user.get("last_name", ""),
        "username": user.get("username", ""),
        "photo_url": user.get("photo_url", ""),
        "language_code": user.get("language_code", "uz"),
        "is_active": is_active,
        "is_banned": bool(banned),
        "is_free": bool(free),
        "has_subscription": has_sub,
        "subscription_expiry": expiry,
        "days_left": days_left,
        "is_admin": bool(admin_row),
        "admin_permissions": dict(admin_row) if admin_row else None,
    }
