"""
Funksiyalar menyusi:
- Foydalanuvchi: "⚙️ Funksiyalar" tugmasi → o'z funksiyalarini yoq/o'chir.
- Admin: /gfeat buyrug'i → global (hamma uchun) yoq/o'chir.
"""

import logging

from pyrogram import Client, filters, ContinuePropagation, StopPropagation
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import is_admin
from feature_flags import (
    FEATURES, gate_feature,
    get_user_features, set_user_feature,
    get_global_features, set_global_feature,
)

logger = logging.getLogger(__name__)

FEATURES_BTN = "⚙️ Funksiyalar"


def _status_emoji(enabled: bool) -> str:
    return "✅" if enabled else "❌"


def _user_keyboard(flags: dict) -> InlineKeyboardMarkup:
    rows = []
    for key, name in FEATURES.items():
        rows.append([InlineKeyboardButton(
            f"{name} — {_status_emoji(flags.get(key, True))}",
            callback_data=f"feat|toggle|{key}",
        )])
    rows.append([InlineKeyboardButton("🔙 Bosh menyu", callback_data="menu_main")])
    return InlineKeyboardMarkup(rows)


def _global_keyboard(flags: dict) -> InlineKeyboardMarkup:
    rows = []
    for key, name in FEATURES.items():
        rows.append([InlineKeyboardButton(
            f"{name} — {_status_emoji(flags.get(key, True))}",
            callback_data=f"feat|global|{key}",
        )])
    rows.append([InlineKeyboardButton("🔄 Yangilash", callback_data="feat|global_refresh")])
    return InlineKeyboardMarkup(rows)


_USER_MENU_TEXT = (
    "⚙️ **Funksiyalar**\n\n"
    "Quyidagi funksiyalarni o'zingiz uchun yoqishingiz yoki o'chirishingiz mumkin.\n"
    "O'chirilgan funksiya buyruqlariga bot javob bermaydi."
)

_GLOBAL_MENU_TEXT = (
    "🌍 **Global funksiyalar** (admin)\n\n"
    "Bu yerdagi holat BARCHA foydalanuvchilarga ta'sir qiladi.\n"
    "Adminlar cheklovlardan mustasno."
)

# ------------------------- Foydalanuvchi UI -------------------------

@Client.on_message(filters.private & filters.text, group=-7)
async def features_menu_command(client: Client, message: Message):
    """'⚙️ Funksiyalar' tugmasi / menyuni ochish."""
    if not message.from_user or (message.text or "").strip() != FEATURES_BTN:
        raise ContinuePropagation

    flags = await get_user_features(message.from_user.id)
    await message.reply_text(_USER_MENU_TEXT, reply_markup=_user_keyboard(flags))
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^feat\|toggle\|(\w+)$"))
async def feature_toggle_callback(client: Client, cq: CallbackQuery):
    key = cq.matches[0].group(1)
    if key not in FEATURES:
        await cq.answer("⚠️ Noma'lum funksiya", show_alert=True)
        return

    uid = cq.from_user.id
    flags = await get_user_features(uid)
    new_value = not flags.get(key, True)
    if await set_user_feature(uid, key, new_value):
        flags[key] = new_value
        await cq.message.edit_text(_USER_MENU_TEXT, reply_markup=_user_keyboard(flags))
        await cq.answer(
            f"{FEATURES[key]}: {'yoqildi' if new_value else 'ochirildi'}"
        )
    else:
        await cq.answer("⚠️ Saqlashda xatolik, qayta urinib ko'ring", show_alert=True)

# ------------------------- Admin: global UI -------------------------

@Client.on_message(filters.private & filters.command(["gfeat", "globalfeatures"]))
async def global_features_command(client: Client, message: Message):
    """/gfeat — global funksiyalar paneli (faqat adminlar)."""
    if not is_admin(message.from_user.id):
        return
    flags = await get_global_features()
    await message.reply_text(_GLOBAL_MENU_TEXT, reply_markup=_global_keyboard(flags))


@Client.on_callback_query(filters.regex(r"^feat\|global\|(\w+)$"))
async def global_feature_toggle_callback(client: Client, cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("⛔️ Faqat adminlar uchun", show_alert=True)
        return

    key = cq.matches[0].group(1)
    if key not in FEATURES:
        await cq.answer("⚠️ Noma'lum funksiya", show_alert=True)
        return

    flags = await get_global_features()
    new_value = not flags.get(key, True)
    if await set_global_feature(key, new_value):
        flags[key] = new_value
        await cq.message.edit_text(_GLOBAL_MENU_TEXT, reply_markup=_global_keyboard(flags))
        await cq.answer(
            f"{FEATURES[key]} (global): {'yoqildi' if new_value else 'ochirildi'}"
        )
    else:
        await cq.answer("⚠️ Saqlashda xatolik, qayta urinib ko'ring", show_alert=True)


@Client.on_callback_query(filters.regex(r"^feat\|global_refresh$"))
async def global_feature_refresh_callback(client: Client, cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("⛔️ Faqat adminlar uchun", show_alert=True)
        return
    flags = await get_global_features()
    await cq.message.edit_text(_GLOBAL_MENU_TEXT, reply_markup=_global_keyboard(flags))
    await cq.answer("🔄 Yangilandi")

# gate_feature shu yerdan ham eksport qilinadi (qulaylik uchun)
__all__ = ["gate_feature", "FEATURES_BTN"]
