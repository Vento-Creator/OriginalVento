"""Obuna holati — bot DB (users.expiry_date / free_users) asosida.

To'lov qilingan-qilinmagani muhim emas: admin tasdiqlashi grant_subscription
orqali expiry_date qo'yadi, qo'shimcha kunlar esa shu muddatni uzaytiradi.
"""
import time
from typing import Any, Optional


def build_sub_status(expiry: Optional[Any], is_free: bool) -> dict:
    now = int(time.time())
    try:
        expiry_ts = int(expiry or 0)
    except (TypeError, ValueError):
        expiry_ts = 0

    is_free = bool(is_free)
    seconds_left = 0 if is_free else max(0, expiry_ts - now)
    active = is_free or seconds_left > 0

    return {
        "is_free": is_free,
        "expiry_date": expiry_ts,
        "seconds_left": seconds_left,
        "days_left": seconds_left // 86400,
        "is_active": active,
        "has_subscription": active,
        "can_purchase": (not is_free) and (not active),
    }
