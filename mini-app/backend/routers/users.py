from fastapi import APIRouter, Depends
from auth import get_current_user
from db import get_pool
from sub_status import build_sub_status

router = APIRouter()


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Telegram foydalanuvchi ma'lumotlari + bot DB holati."""
    uid = user["id"]
    pool = await get_pool()

    row = await pool.fetchrow(
        "SELECT expiry_date, is_active, username, first_name FROM users WHERE user_id = $1",
        uid
    )

    banned = await pool.fetchrow(
        "SELECT user_id FROM banned_users WHERE user_id = $1", uid
    )

    free = await pool.fetchrow(
        "SELECT user_id FROM free_users WHERE user_id = $1", uid
    )

    admin_row = await pool.fetchrow(
        """SELECT can_add_admin, can_ban, can_clear_db, can_broadcast, can_manage_users
           FROM admins WHERE admin_id = $1""",
        uid
    )

    expiry = (row["expiry_date"] if row else 0) or 0
    is_active_flag = bool(row["is_active"]) if row else False
    sub = build_sub_status(expiry, bool(free))

    return {
        "id": uid,
        "first_name": user.get("first_name", ""),
        "last_name": user.get("last_name", ""),
        "username": user.get("username", ""),
        "photo_url": user.get("photo_url", ""),
        "language_code": user.get("language_code", "uz"),
        "is_active": is_active_flag,
        "is_banned": bool(banned),
        "is_free": sub["is_free"],
        "has_subscription": sub["has_subscription"],
        "subscription_expiry": sub["expiry_date"],
        "seconds_left": sub["seconds_left"],
        "days_left": sub["days_left"],
        "can_purchase": sub["can_purchase"],
        "is_admin": bool(admin_row),
        "admin_permissions": dict(admin_row) if admin_row else None,
    }
