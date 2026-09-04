import hashlib
import hmac
import json
import time
import urllib.parse
import os
from typing import Optional
from fastapi import HTTPException, Header

BOT_TOKEN = os.getenv("BOT_TOKEN", "")


def validate_telegram_init_data(init_data: str) -> dict:
    """
    Telegram WebApp initData ni HMAC-SHA256 orqali tasdiqlaydi.
    Returns: parsed user dict
    Raises: HTTPException(401) if invalid
    """
    if os.getenv("DEV_MODE") == "true":
        return {
            "id": 8513957498,
            "first_name": "Diyorbek",
            "last_name": "",
            "username": "Nova_OS_Builder_Admin",
            "language_code": "uz"
        }

    if not init_data:
        raise HTTPException(status_code=401, detail="initData yo'q")

    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        raise HTTPException(status_code=401, detail="initData noto'g'ri format")

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="hash yo'q")

    # Tekshirish uchun data_check_string
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed.items())
    )

    # HMAC key = HMAC-SHA256("WebAppData", bot_token)
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise HTTPException(status_code=401, detail="initData imzosi noto'g'ri")

    # Vaqt tekshiruvi (3 soat)
    auth_date = int(parsed.get("auth_date", 0))
    if time.time() - auth_date > 10800:  # 3 soat
        raise HTTPException(status_code=401, detail="initData muddati o'tgan")

    # User ma'lumotlarini parse qilish
    user_str = parsed.get("user", "{}")
    try:
        user = json.loads(user_str)
    except Exception:
        raise HTTPException(status_code=401, detail="user ma'lumoti noto'g'ri")

    try:
        user["id"] = int(user["id"])
    except (TypeError, ValueError, KeyError):
        raise HTTPException(status_code=401, detail="user id noto'g'ri")

    return user


async def get_current_user(x_init_data: Optional[str] = Header(None)) -> dict:
    """FastAPI Dependency: initData header orqali foydalanuvchini olish."""
    if os.getenv("DEV_MODE") == "true":
        return validate_telegram_init_data("dev_mode")
    if not x_init_data:
        raise HTTPException(status_code=401, detail="X-Init-Data header yo'q")
    return validate_telegram_init_data(x_init_data)
