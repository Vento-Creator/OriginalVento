"""
Action Sozlamalari — flat Hide/Suppress toggles (ON = send CANCEL).
"""
from __future__ import annotations

import logging

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import user_settings
from session_manager import get_user_client
from utag_system.action_engine import (
    ActionEngine,
    CHAT_ACTION_SUPPRESS_KEYS,
    FLAT_ACTION_TOGGLES,
    flip_suppression,
    get_toggle_by_key,
    is_suppressed,
    toggle_button_label,
)

logger = logging.getLogger(__name__)


def _ensure_settings(user_id: int) -> dict:
    if user_id not in user_settings:
        user_settings[user_id] = {}
    return user_settings[user_id]


def _edit_cq(cq: CallbackQuery, text: str, buttons: list | None = None):
    if buttons is None:
        return cq.message.edit_text(text)
    return cq.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))


def _get_user_active_chat_ids(user_id: int) -> list[int]:
    try:
        from plugins.utag import _get_user_active_processes

        return list(_get_user_active_processes(user_id))
    except Exception:
        return []


def _build_flat_menu(settings: dict, back: str) -> tuple[str, list]:
    text = (
        "⚙️ **Action Sozlamalari**\n\n"
        "🟢 **ON** = status yashirish (CANCEL yuboriladi)\n"
        "🔴 **OFF** = Telegram standart xatti-harakati\n\n"
        "💡 UTag typing alohida: Utag → Sozlamalar."
    )
    buttons = []
    for key, label, _action in FLAT_ACTION_TOGGLES:
        buttons.append([
            InlineKeyboardButton(
                toggle_button_label(label, is_suppressed(settings, key)),
                callback_data=f"action_flat_toggle_{key}",
            )
        ])
    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data=back)])
    return text, buttons


async def _render_menu(cq: CallbackQuery, settings: dict) -> None:
    back = settings.get("action_status_back", "menu_main")
    text, buttons = _build_flat_menu(settings, back)
    await _edit_cq(cq, text, buttons)


@Client.on_callback_query(filters.regex("^action_status_menu(_account)?$"))
async def action_status_entry(client: Client, cq: CallbackQuery):
    if not cq.from_user:
        return
    user_id = cq.from_user.id
    settings = _ensure_settings(user_id)
    settings["action_status_back"] = "menu_main" if cq.matches[0].group(1) else "utag_settings"
    await _render_menu(cq, settings)
    await cq.answer()


@Client.on_callback_query(filters.regex("^action_flat_toggle_(.+)$"))
async def action_flat_toggle(client: Client, cq: CallbackQuery):
    if not cq.from_user:
        return
    user_id = cq.from_user.id
    key = cq.matches[0].group(1)
    if not get_toggle_by_key(key):
        await cq.answer("Noma'lum sozlama", show_alert=True)
        return

    settings = _ensure_settings(user_id)
    flip_suppression(settings, key)
    hide_on = is_suppressed(settings, key)

    try:
        user_client = await get_user_client(user_id)
        if key == "privacy_online_status":
            await ActionEngine.apply_online_presence(user_client, settings)
        elif hide_on and key in CHAT_ACTION_SUPPRESS_KEYS:
            await ActionEngine.on_suppression_enabled(
                user_client,
                _get_user_active_chat_ids(user_id),
                user_id,
            )
    except Exception as exc:
        logger.warning("[ActionStatus] toggle apply failed user=%s key=%s: %s", user_id, key, exc)

    await _render_menu(cq, settings)
    await cq.answer("✅ Yangilandi")
