import time
import os
from fastapi import APIRouter, Depends, HTTPException
from auth import get_current_user
from db import get_pool
import httpx

router = APIRouter()


@router.get("/")
async def get_subscription(user: dict = Depends(get_current_user)):
    """Foydalanuvchining obuna holatini qaytaradi."""
    uid = user["id"]
    pool = await get_pool()

    row = await pool.fetchrow(
        "SELECT expiry_date FROM users WHERE user_id = $1", uid
    )

    free = await pool.fetchrow(
        "SELECT user_id FROM free_users WHERE user_id = $1", uid
    )

    # To'lov tarixi
    payments = await pool.fetch(
        """SELECT payment_id, amount, currency, status, created_at, granted_expiry
           FROM payments WHERE user_id = $1 ORDER BY created_at DESC LIMIT 10""",
        uid
    )
    payments = [dict(r) for r in payments]

    now = int(time.time())
    expiry = row["expiry_date"] if row else 0
    days_left = max(0, (expiry - now) // 86400) if expiry and expiry > now else 0

    return {
        "is_free": bool(free),
        "expiry_date": expiry,
        "days_left": days_left,
        "is_active": bool(free) or (expiry > now if expiry else False),
        "payment_history": payments,
    }


@router.get("/history")
async def get_payment_history(user: dict = Depends(get_current_user)):
    """To'lovlar tarixini qaytaradi."""
    uid = user["id"]
    pool = await get_pool()

    payments = await pool.fetch(
        """SELECT payment_id, amount, currency, status, grant_status,
                  created_at, granted_at, granted_expiry
           FROM payments WHERE user_id = $1 ORDER BY created_at DESC""",
        uid
    )

    return {"payments": [dict(r) for r in payments]}


@router.post("/pay")
async def create_invoice(user: dict = Depends(get_current_user)):
    """Telegram Stars orqali invoice link yaratadi."""
    uid = user["id"]
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise HTTPException(status_code=500, detail="BOT_TOKEN environment o'rnatilmagan!")

    url = f"https://api.telegram.org/bot{token}/createInvoiceLink"
    payload = {
        "title": "⭐️ Vento Obuna",
        "description": "Vento botidan 30 kun to'liq foydalanish uchun 100 Telegram Stars to'lang.",
        "payload": f"stars_payment_{uid}",
        "provider_token": "",  # Empty for Telegram Stars
        "currency": "XTR",
        "prices": [{"label": "⭐️ Obuna", "amount": 100}]
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=10)
            res = resp.json()
            if not res.get("ok"):
                raise HTTPException(status_code=400, detail=f"Telegram API xatosi: {res.get('description')}")
            return {"invoice_link": res["result"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Faktura yaratishda xatolik: {str(e)}")

