"""
Shared UTag helpers — speed, notifications, auto-delete, progress throttling.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from pyrogram import Client
from pyrogram.errors import FloodWait

logger = logging.getLogger(__name__)

UTAG_SPEED_MIN = 0.01
UTAG_SPEED_MAX = 5.0
UTAG_SPEED_DEFAULT = 0.8

SPEED_WARNING = (
    "⚠️ 0.01s-0.5s oralig'idagi yuqori tezlik akkauntingiz Telegram tomonidan "
    "spam/flood limitiga tushish xavfini oshiradi. Barcha mas'uliyat foydalanuvchi zimmasida!"
)

LEGACY_SPEED_MAP = {"slow": 5.0, "normal": 2.5, "fast": 1.0}


def get_utag_speed_seconds(settings: dict) -> float:
    """Resolve tag delay in seconds from user settings (supports legacy presets)."""
    if "utag_speed_seconds" in settings:
        val = float(settings["utag_speed_seconds"])
    else:
        legacy = settings.get("utag_speed", UTAG_SPEED_DEFAULT)
        if isinstance(legacy, (int, float)):
            val = float(legacy)
        else:
            val = LEGACY_SPEED_MAP.get(str(legacy), UTAG_SPEED_DEFAULT)
    return max(UTAG_SPEED_MIN, min(UTAG_SPEED_MAX, round(val, 2)))


def format_speed_label(seconds: float) -> str:
    # 1 decimal for normal values (0.8 -> "0.8s"), 2 decimals only when needed (0.05 -> "0.05s")
    if abs(seconds * 10 - round(seconds * 10)) < 1e-9:
        return f"⏱️ {seconds:.1f}s"
    return f"⏱️ {seconds:.2f}s"


def is_high_speed_risk(seconds: float) -> bool:
    return seconds <= 0.5


async def auto_delete_message(client: Client, chat_id: int, message_id: int, delete_timer: int) -> None:
    if delete_timer <= 0 or not message_id:
        return
    await asyncio.sleep(delete_timer)
    try:
        await client.delete_messages(chat_id, message_id)
    except Exception:
        pass


async def edit_and_auto_delete(
    client: Client,
    chat_id: int,
    message_id: int,
    text: str,
    delete_timer: int,
) -> None:
    """Edit a control message and schedule auto-delete without blocking the caller."""
    try:
        await client.edit_message_text(chat_id, message_id, text)
        if delete_timer > 0:
            asyncio.create_task(auto_delete_message(client, chat_id, message_id, delete_timer))
    except Exception:
        try:
            msg = await client.send_message(chat_id, text)
            if delete_timer > 0:
                asyncio.create_task(auto_delete_message(client, chat_id, msg.id, delete_timer))
        except Exception as exc:
            logger.debug("[UTAG] edit_and_auto_delete fallback failed: %s", exc)


async def send_completion_notification(
    client: Client,
    chat_id: int,
    tagged_count: int,
    delete_timer: int,
    show_completion: bool,
) -> None:
    if not show_completion:
        return
    text = f"VentoTag yakunlandi! Jami: {tagged_count} ta user tag qilindi"
    try:
        msg = await client.send_message(chat_id, text)
        if delete_timer > 0:
            asyncio.create_task(auto_delete_message(client, chat_id, msg.id, delete_timer))
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
        try:
            msg = await client.send_message(chat_id, text)
            if delete_timer > 0:
                asyncio.create_task(auto_delete_message(client, chat_id, msg.id, delete_timer))
        except Exception as exc:
            logger.error("[UTAG] Completion notification retry failed: %s", exc)
    except Exception as exc:
        logger.error("[UTAG] Completion notification failed: %s", exc)


class ProgressThrottler:
    """Throttle queue/UI progress updates when tagging speed is high (<0.8s)."""

    def __init__(self, speed_seconds: float):
        self.high_speed = speed_seconds < 0.8
        self.last_update = 0.0
        self.tags_since_update = 0

    def should_update(self) -> bool:
        if not self.high_speed:
            return True
        now = time.time()
        self.tags_since_update += 1
        if self.tags_since_update >= 5 or (now - self.last_update) >= 3.0:
            self.last_update = now
            self.tags_since_update = 0
            return True
        return False


def get_action_status_label(settings: dict, key: str) -> str:
    return "✅ Yoqilgan" if settings.get(key, False) else "❌ O'chirilgan"
