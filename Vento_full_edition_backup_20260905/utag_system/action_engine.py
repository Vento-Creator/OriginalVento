"""
Telegram ChatAction engine — status suppression (Hide) model.

ON  = suppress / hide → send ChatAction.CANCEL before dispatch
OFF = default Telegram behavior → do nothing extra
"""
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional, Tuple, Union

from pyrogram import Client
from pyrogram.enums import ChatAction
from pyrogram.errors import FloodWait

logger = logging.getLogger(__name__)

# (settings_key, UI label)
FLAT_ACTION_TOGGLES: List[Tuple[str, str, Optional[ChatAction]]] = [
    ("action_status_typing", "Hide Typing", ChatAction.TYPING),
    ("action_status_playing", "Hide Playing game", ChatAction.PLAYING),
    ("action_status_record_audio", "Hide Recording audio", ChatAction.RECORD_AUDIO),
    ("action_status_upload_media", "Hide Uploading photo/video/document", ChatAction.UPLOAD_PHOTO),
    ("action_status_choose_sticker", "Hide Choosing sticker", ChatAction.CHOOSE_STICKER),
    ("privacy_online_status", "Hide Online status", None),
    ("privacy_mark_as_read", "Hide Read receipts", None),
]

CHAT_ACTION_SUPPRESS_KEYS = {key for key, _, action in FLAT_ACTION_TOGGLES if action is not None}

SETTINGS_KEY_GHOST_READ = "privacy_ghost_read"
SETTINGS_KEY_MARK_AS_READ = "privacy_mark_as_read"
SETTINGS_KEY_ONLINE_STATUS = "privacy_online_status"


def is_suppressed(settings: dict, key: str) -> bool:
    """Return True when Hide/Suppress is ON for a setting."""
    if key == SETTINGS_KEY_MARK_AS_READ:
        if "privacy_hide_read" in settings:
            return bool(settings["privacy_hide_read"])
        if SETTINGS_KEY_MARK_AS_READ in settings:
            # Legacy inverted: mark_as_read True meant read enabled → hide OFF
            return not bool(settings[SETTINGS_KEY_MARK_AS_READ])
        return bool(settings.get(SETTINGS_KEY_GHOST_READ, False))
    return bool(settings.get(key, False))


def set_suppression(settings: dict, key: str, hide_on: bool) -> None:
    settings[key] = hide_on
    if key == SETTINGS_KEY_MARK_AS_READ:
        settings[SETTINGS_KEY_GHOST_READ] = hide_on
        settings[SETTINGS_KEY_MARK_AS_READ] = not hide_on
        settings["privacy_hide_read"] = hide_on


def flip_suppression(settings: dict, key: str) -> None:
    set_suppression(settings, key, not is_suppressed(settings, key))


def get_toggle_by_key(key: str) -> Optional[Tuple[str, str, Optional[ChatAction]]]:
    for item in FLAT_ACTION_TOGGLES:
        if item[0] == key:
            return item
    return None


def toggle_button_label(label: str, hide_on: bool) -> str:
    state = "🟢 ON" if hide_on else "🔴 OFF"
    return f"{label}: {state}"


def any_chat_action_suppressed(settings: dict) -> bool:
    return any(is_suppressed(settings, key) for key in CHAT_ACTION_SUPPRESS_KEYS)


def should_suppress_typing(settings: dict, utag_settings: Optional[dict] = None) -> bool:
    if is_suppressed(settings, "action_status_typing"):
        return True
    if utag_settings is not None and not utag_settings.get("utag_typing_status", True):
        return True
    return False


class ActionEngine:
    """Status suppression via explicit CANCEL only — no background loops."""

    @staticmethod
    async def cancel_chat_action(client: Client, chat_id: int) -> bool:
        try:
            await client.send_chat_action(chat_id, ChatAction.CANCEL)
            return True
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
            try:
                await client.send_chat_action(chat_id, ChatAction.CANCEL)
                return True
            except Exception as exc:
                logger.error("[ActionEngine] CANCEL retry failed chat=%s: %s", chat_id, exc)
                return False
        except Exception as exc:
            logger.error("[ActionEngine] CANCEL failed chat=%s: %s", chat_id, exc)
            return False

    @staticmethod
    async def apply_dispatch_suppression(
        client: Client,
        chat_id: int,
        settings: dict,
        utag_settings: Optional[dict] = None,
    ) -> None:
        """If any Hide toggle is ON (or UTag typing hidden), send CANCEL once."""
        if any_chat_action_suppressed(settings) or should_suppress_typing(settings, utag_settings):
            await ActionEngine.cancel_chat_action(client, chat_id)

    @staticmethod
    async def safe_mark_as_read(
        client: Client,
        chat_id: int,
        settings: dict,
        max_id: int = 0,
    ) -> bool:
        if is_suppressed(settings, SETTINGS_KEY_MARK_AS_READ):
            logger.debug("[ActionEngine] Read receipts hidden: skip mark_as_read chat=%s", chat_id)
            return False
        try:
            await client.read_chat_history(chat_id, max_id=max_id)
            return True
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
            try:
                await client.read_chat_history(chat_id, max_id=max_id)
                return True
            except Exception as exc:
                logger.error("[ActionEngine] read_chat_history retry failed: %s", exc)
                return False
        except Exception as exc:
            logger.error("[ActionEngine] read_chat_history failed: %s", exc)
            return False

    @staticmethod
    async def apply_online_presence(client: Client, settings: dict) -> None:
        try:
            from pyrogram.raw.functions.account import UpdateStatus

            hide_online = is_suppressed(settings, SETTINGS_KEY_ONLINE_STATUS)
            await client.invoke(UpdateStatus(offline=hide_online))
        except Exception as exc:
            logger.error("[ActionEngine] apply_online_presence failed: %s", exc)

    @staticmethod
    async def cancel_on_chats(client: Client, chat_ids: List[int]) -> None:
        for chat_id in chat_ids:
            try:
                await ActionEngine.cancel_chat_action(client, chat_id)
            except Exception as exc:
                logger.debug("[ActionEngine] cancel_on_chats chat=%s: %s", chat_id, exc)

    @staticmethod
    async def on_suppression_enabled(
        client: Client,
        active_chat_ids: List[int],
        user_id: int,
    ) -> None:
        """When Hide is turned ON, immediately CANCEL on active chats."""
        targets = list(set(active_chat_ids + [user_id]))
        await ActionEngine.cancel_on_chats(client, targets)


# Backward-compatible aliases used elsewhere
toggle_on = is_suppressed
flip_toggle = flip_suppression
