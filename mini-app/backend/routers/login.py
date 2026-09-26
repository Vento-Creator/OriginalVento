"""
Mini-App Login Router — Telegram sessiya ulash.

Jarayon:
  1. POST /api/login/send_code   — telefon raqamini qabul qiladi, Telegram orqali kod yuboradi
  2. POST /api/login/verify_code — kodni tekshiradi, sessiyani saqlaydi
  3. DELETE /api/login/session   — sessiyani o'chiradi (logout)
  4. GET  /api/login/status      — sessiya holati

Sessiya ma'lumoti `user_sessions` jadvalida saqlanadi.
"""

import os
import time
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user
from db import get_pool

logger = logging.getLogger(__name__)
router = APIRouter()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class SendCodeRequest(BaseModel):
    phone: str


class VerifyCodeRequest(BaseModel):
    phone: str
    code: str
    phone_code_hash: str


# ---------------------------------------------------------------------------
# Helper: pending_approvals jadvali orqali login so'rovi yuborish
# ---------------------------------------------------------------------------

async def _ensure_login_sessions_table(pool):
    """login_sessions jadvalini yaratish (agar yo'q bo'lsa)."""
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS login_sessions (
            user_id     BIGINT PRIMARY KEY,
            phone       TEXT,
            session_str TEXT,
            step        TEXT DEFAULT 'idle',
            phone_code_hash TEXT,
            created_at  BIGINT DEFAULT 0,
            updated_at  BIGINT DEFAULT 0
        )
    """)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/status")
async def login_status(user: dict = Depends(get_current_user)):
    """Foydalanuvchining sessiya holati."""
    uid = user["id"]
    pool = await get_pool()
    await _ensure_login_sessions_table(pool)

    row = await pool.fetchrow(
        "SELECT step, phone, updated_at FROM login_sessions WHERE user_id = $1",
        uid
    )

    # Bot sessions jadvali bor-yo'qligini tekshir
    session_row = None
    try:
        session_row = await pool.fetchrow(
            "SELECT user_id FROM user_sessions WHERE user_id = $1",
            uid
        )
    except Exception:
        pass

    has_session = bool(session_row)
    step = row["step"] if row else "idle"
    phone = row["phone"] if row else None

    return {
        "has_session": has_session,
        "step": step,
        "phone": phone,
        "updated_at": row["updated_at"] if row else 0,
    }


@router.post("/request")
async def request_login(user: dict = Depends(get_current_user)):
    """
    Mini-app dan login so'rovi — botga 'Sessiya ulash' xabarini yuboradi.
    Foydalanuvchi botda /start → Sessiya ulash tugmasini bosib, keyingi qadamlarni amalga oshiradi.
    """
    uid = user["id"]
    pool = await get_pool()
    await _ensure_login_sessions_table(pool)

    # Allaqachon sessiya bor-yo'qligini tekshir
    try:
        session_row = await pool.fetchrow(
            "SELECT user_id FROM user_sessions WHERE user_id = $1", uid
        )
        if session_row:
            return {"status": "already_connected", "message": "Sessiya allaqachon ulangan!"}
    except Exception:
        pass

    # pending_approvals ga yozish — bot shu yozuvni ko'rib, foydalanuvchiga xabar yuboradi
    await pool.execute("""
        INSERT INTO pending_approvals (user_id, created_at)
        VALUES ($1, $2)
        ON CONFLICT (user_id) DO UPDATE SET created_at = EXCLUDED.created_at
    """, uid, int(time.time()))

    # login_sessions ni boshlang'ich holga qaytarish
    await pool.execute("""
        INSERT INTO login_sessions (user_id, step, created_at, updated_at)
        VALUES ($1, 'requested', $2, $2)
        ON CONFLICT (user_id) DO UPDATE SET step = 'requested', updated_at = EXCLUDED.updated_at
    """, uid, int(time.time()))

    # Bot orqali bildirishnoma yuborish
    try:
        import httpx
        bot_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        msg = (
            "🔐 <b>Mini-App orqali sessiya ulash so'rovi</b>\n\n"
            "Akkauntingizni Vento botiga ulash uchun quyidagi tugmani bosing va ko'rsatmalarga amal qiling."
        )
        async with httpx.AsyncClient() as client:
            await client.post(bot_url, json={
                "chat_id": uid,
                "text": msg,
                "parse_mode": "HTML",
                "reply_markup": {
                    "inline_keyboard": [[
                        {"text": "🔗 Sessiya Ulash", "callback_data": "miniapp_login_start"}
                    ]]
                }
            }, timeout=10)
    except Exception as e:
        logger.warning(f"Login notification send error for {uid}: {e}")

    return {
        "status": "requested",
        "message": "Botga o'ting va 'Sessiya Ulash' tugmasini bosing!"
    }


@router.get("/check")
async def check_login(user: dict = Depends(get_current_user)):
    """Login jarayoni tugagan-tugamaganini tekshirish (polling)."""
    uid = user["id"]
    pool = await get_pool()
    await _ensure_login_sessions_table(pool)

    # Sessiya ulanganligi
    has_session = False
    try:
        session_row = await pool.fetchrow(
            "SELECT user_id FROM user_sessions WHERE user_id = $1", uid
        )
        has_session = bool(session_row)
    except Exception:
        pass

    if has_session:
        # login_sessions ni yangilash
        await pool.execute(
            "UPDATE login_sessions SET step = 'connected', updated_at = $1 WHERE user_id = $2",
            int(time.time()), uid
        )
        return {"status": "connected", "has_session": True}

    row = await pool.fetchrow(
        "SELECT step, updated_at FROM login_sessions WHERE user_id = $1", uid
    )

    step = row["step"] if row else "idle"
    return {"status": step, "has_session": False}


@router.delete("/session")
async def logout_session(user: dict = Depends(get_current_user)):
    """Sessiyani o'chirish (logout)."""
    uid = user["id"]
    pool = await get_pool()
    await _ensure_login_sessions_table(pool)

    # user_sessions dan o'chirish
    try:
        await pool.execute("DELETE FROM user_sessions WHERE user_id = $1", uid)
    except Exception as e:
        logger.warning(f"Delete user_sessions error for {uid}: {e}")

    # login_sessions ni reset
    await pool.execute(
        "UPDATE login_sessions SET step = 'idle', session_str = NULL, updated_at = $1 WHERE user_id = $2",
        int(time.time()), uid
    )

    # Bot orqali xabar
    try:
        import httpx
        bot_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        async with httpx.AsyncClient() as client:
            await client.post(bot_url, json={
                "chat_id": uid,
                "text": "🔓 <b>Sessiya o'chirildi</b>\n\nSiz Mini-App orqali akkauntingizni uzatdingiz. Qayta ulash uchun /start bosing.",
                "parse_mode": "HTML"
            }, timeout=10)
    except Exception as e:
        logger.warning(f"Logout notification error for {uid}: {e}")

    return {"status": "disconnected", "message": "Sessiya muvaffaqiyatli o'chirildi!"}
