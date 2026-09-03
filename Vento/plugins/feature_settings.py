"""
Funksiyalar menyusi (faqat adminlar uchun ko'rinadi va ishlaydi):
- "⚙️ Funksiyalar" tugmasi → boshqaruv paneli (ruxsatnoma kerak).
- /gfeat → global (hamma uchun) yoq/o'chir.
- /feat <user_id> → bitta foydalanuvchi uchun yoq/o'chir.
- /featmgr → owner: adminlarga boshqarish ruxsatnomasini berish/olish.

Qoidalar:
- Boshqarish uchun "feature management" ruxsatnomasi kerak (owner'da doim bor).
- Admin o'zining funksiyalarini o'zgartira olmaydi — uni owner boshqaradi.
- Funksiyalardan foydalanishda faqat OWNER (SUPER_ADMIN_ID) cheklovlardan
  mustasno; adminlar va userlar flaglarga bo'ysunadi.
"""

import logging

from pyrogram import Client, filters, ContinuePropagation, StopPropagation
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import is_admin, SUPER_ADMIN_ID
from feature_flags import (
    FEATURES, gate_feature, is_owner,
    get_user_features, set_user_feature,
    get_global_features, set_global_feature,
    can_manage_features, set_feature_manager, get_feature_managers,
)

logger = logging.getLogger(__name__)

FEATURES_BTN = "⚙️ Funksiyalar"

NO_PERMISSION_TEXT = "⛔️ Sizda funksiyalarni boshqarish uchun ruxsat yo'q."


def _status_emoji(enabled: bool) -> str:
    return "✅" if enabled else "❌"


def _global_keyboard(flags: dict) -> InlineKeyboardMarkup:
    rows = []
    for key, name in FEATURES.items():
        rows.append([InlineKeyboardButton(
            f"{name} — {_status_emoji(flags.get(key, True))}",
            callback_data=f"feat|global|{key}",
        )])
    rows.append([InlineKeyboardButton("🔄 Yangilash", callback_data="feat|global_refresh")])
    return InlineKeyboardMarkup(rows)


_GLOBAL_MENU_TEXT = (
    "🌍 **Global funksiyalar**\n\n"
    "Bu holat BARCHA foydalanuvchilarga ta'sir qiladi.\n"
    "Bitta user uchun: `/feat <user_id>`\n\n"
    "ℹ️ Funksiyalardan foydalanishda faqat owner cheklovlardan mustasno."
)

_USER_PANEL_TEXT = (
    "👤 **Foydalanuvchi funksiyalari**\n\n"
    "ID: `{user_id}`\n\n"
    "Bu holat FAQAT shu foydalanuvchiga ta'sir qiladi (boshqalarga yo'q)."
)

_MGR_HELP_TEXT = (
    "🔐 **Funksiyalar boshqaruvchilari** (owner paneli)\n\n"
    "Ruxsatnoma berish: `/featmgr <admin_id> on`\n"
    "Ruxsatnomani olish: `/featmgr <admin_id> off`\n\n"
    "**Hozirgi ruxsatnomalilar:**\n{list}\n\n"
    "ℹ️ Owner hamma narsani doim boshqara oladi. Admin o'zining "
    "funksiyalarini o'zgartira olmaydi — uni owner boshqaradi."
)


def _user_panel_keyboard(target_uid: int, flags: dict) -> InlineKeyboardMarkup:
    rows = []
    for key, name in FEATURES.items():
        rows.append([InlineKeyboardButton(
            f"{name} — {_status_emoji(flags.get(key, True))}",
            callback_data=f"feat|user|{target_uid}|{key}",
        )])
    rows.append([InlineKeyboardButton("🔄 Yangilash", callback_data=f"feat|user|{target_uid}|_refresh")])
    return InlineKeyboardMarkup(rows)


# ------------------------- "⚙️ Funksiyalar" tugmasi (faqat admin) -------------------------

@Client.on_message(filters.private & filters.text, group=-7)
async def features_menu_command(client: Client, message: Message):
    """'⚙️ Funksiyalar' tugmasi — faqat adminlar uchun."""
    if not message.from_user or (message.text or "").strip() != FEATURES_BTN:
        raise ContinuePropagation

    if not is_admin(message.from_user.id):
        await message.reply_text(NO_PERMISSION_TEXT)
        raise StopPropagation

    if not await can_manage_features(message.from_user.id):
        await message.reply_text(NO_PERMISSION_TEXT)
        raise StopPropagation

    flags = await get_global_features()
    await message.reply_text(_GLOBAL_MENU_TEXT, reply_markup=_global_keyboard(flags))
    raise StopPropagation



# ------------------------- Boshqarish ruxsatnoma tekshiruvi -------------------------

async def _check_manager(cq_or_msg) -> bool:
    """Boshqarish ruxsatnomasini tekshiradi. Ruxsat bo'lmasa 'ruxsat yo'q' javobi beradi."""
    uid = cq_or_msg.from_user.id
    if await can_manage_features(uid):
        return True
    if isinstance(cq_or_msg, CallbackQuery):
        await cq_or_msg.answer(NO_PERMISSION_TEXT, show_alert=True)
    else:
        await cq_or_msg.reply_text(NO_PERMISSION_TEXT)
    return False


def _self_edit_denied(actor_id: int, target_id: int) -> bool:
    """Admin o'zining funksiyalarini o'zgartira olmaydi (owner mustasno)."""
    return actor_id == target_id and not is_owner(actor_id)


# ------------------------- Admin: global UI -------------------------

@Client.on_message(filters.private & filters.command(["gfeat", "globalfeatures"]))
async def global_features_command(client: Client, message: Message):
    """/gfeat — global funksiyalar paneli (ruxsatnoma kerak)."""
    if not is_admin(message.from_user.id):
        return
    if not await _check_manager(message):
        return
    flags = await get_global_features()
    await message.reply_text(_GLOBAL_MENU_TEXT, reply_markup=_global_keyboard(flags))


@Client.on_callback_query(filters.regex(r"^feat\|global\|(\w+)$"))
async def global_feature_toggle_callback(client: Client, cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("⛔️ Faqat adminlar uchun", show_alert=True)
        return
    if not await _check_manager(cq):
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
    if not await _check_manager(cq):
        return
    flags = await get_global_features()
    await cq.message.edit_text(_GLOBAL_MENU_TEXT, reply_markup=_global_keyboard(flags))
    await cq.answer("🔄 Yangilandi")

# ------------------------- Admin: bitta user uchun -------------------------

_USER_PANEL_TEXT = (
    "👤 **Foydalanuvchi funksiyalari** (admin)\n\n"
    "ID: `{user_id}`\n\n"
    "Bu holat FAQAT shu foydalanuvchiga ta'sir qiladi "
    "(boshqalarga yo'q)."
)


def _user_panel_keyboard(target_uid: int, flags: dict) -> InlineKeyboardMarkup:
    rows = []
    for key, name in FEATURES.items():
        rows.append([InlineKeyboardButton(
            f"{name} — {_status_emoji(flags.get(key, True))}",
            callback_data=f"feat|user|{target_uid}|{key}",
        )])
    rows.append([InlineKeyboardButton("🔄 Yangilash", callback_data=f"feat|user|{target_uid}|_refresh")])
    return InlineKeyboardMarkup(rows)


@Client.on_message(filters.private & filters.command("feat"))
async def user_feature_command(client: Client, message: Message):
    """/feat <user_id> — bitta foydalanuvchi funksiyalari (ruxsatnoma kerak)."""
    if not is_admin(message.from_user.id):
        return
    if not await _check_manager(message):
        return

    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
        await message.reply_text(
            "ℹ️ **Foydalanish:** `/feat <user_id>`\n\n"
            "Masalan: `/feat 123456789` — shu user uchun funksiyalar panelini ochadi.\n"
            "(Global boshqarish uchun: `/gfeat`)"
        )
        return

    target_uid = int(parts[1])

    if _self_edit_denied(message.from_user.id, target_uid):
        await message.reply_text(
            "⛔️ O'z funksiyalaringizni o'zingiz o'zgartira olmaysiz.\n"
            "Adminlarning funksiyalarini **owner** boshqaradi."
        )
        return

    flags = await get_user_features(target_uid)
    await message.reply_text(
        _USER_PANEL_TEXT.format(user_id=target_uid),
        reply_markup=_user_panel_keyboard(target_uid, flags),
    )


@Client.on_callback_query(filters.regex(r"^feat\|user\|(-?\d+)\|(\w+)$"))
async def user_feature_toggle_callback(client: Client, cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("⛔️ Faqat adminlar uchun", show_alert=True)
        return
    if not await _check_manager(cq):
        return

    target_uid = int(cq.matches[0].group(1))
    key = cq.matches[0].group(2)

    if _self_edit_denied(cq.from_user.id, target_uid):
        await cq.answer(
            "⛔️ O'z funksiyalaringizni o'zingiz o'zgartira olmaysiz — buni owner qiladi.",
            show_alert=True,
        )
        return

    if key == "_refresh":
        flags = await get_user_features(target_uid)
        await cq.message.edit_text(
            _USER_PANEL_TEXT.format(user_id=target_uid),
            reply_markup=_user_panel_keyboard(target_uid, flags),
        )
        await cq.answer("🔄 Yangilandi")
        return

    if key not in FEATURES:
        await cq.answer("⚠️ Noma'lum funksiya", show_alert=True)
        return

    flags = await get_user_features(target_uid)
    new_value = not flags.get(key, True)
    if await set_user_feature(target_uid, key, new_value):
        flags[key] = new_value
        await cq.message.edit_text(
            _USER_PANEL_TEXT.format(user_id=target_uid),
            reply_markup=_user_panel_keyboard(target_uid, flags),
        )
        await cq.answer(
            f"User {target_uid} — {FEATURES[key]}: "
            f"{'yoqildi' if new_value else 'ochirildi'}"
        )
    else:
        await cq.answer("⚠️ Saqlashda xatolik, qayta urinib ko'ring", show_alert=True)

# ------------------------- Owner: boshqarish ruxsatnomalari -------------------------

@Client.on_message(filters.private & filters.command("featmgr"))
async def feature_manager_command(client: Client, message: Message):
    """/featmgr <admin_id> on|off — faqat owner: adminlarga boshqarish ruxsatnomasi."""
    if not is_owner(message.from_user.id):
        await message.reply_text("⛔️ Bu buyruq faqat **owner** uchun.")
        return

    parts = (message.text or "").split()
    if len(parts) == 1:
        mgrs = await get_feature_managers()
        listing = "\n".join(f"• `{m}`" for m in sorted(mgrs)) if mgrs else "_Hozircha yo'q (faqat owner)._"
        await message.reply_text(_MGR_HELP_TEXT.format(list=listing))
        return

    if len(parts) != 3 or not parts[1].lstrip("-").isdigit() or parts[2] not in ("on", "off"):
        await message.reply_text(
            "ℹ️ **Foydalanish:**\n"
            "`/featmgr <admin_id> on` — ruxsatnoma berish\n"
            "`/featmgr <admin_id> off` — ruxsatnomani olish\n"
            "`/featmgr` — ro'yxatni ko'rish"
        )
        return

    target_uid = int(parts[1])
    enable = parts[2] == "on"

    if is_owner(target_uid):
        await message.reply_text("ℹ️ Owner doim barcha ruxsatnomalarga ega, buni o'zgartirib bo'lmaydi.")
        return

    if not is_admin(target_uid):
        await message.reply_text(
            f"⚠️ `{target_uid}` bot admini emas. Avval uni admin qiling, "
            "keyin ruxsatnoma bering."
        )
        return

    if await set_feature_manager(target_uid, enable):
        await message.reply_text(
            f"✅ `{target_uid}` uchun funksiyalarni boshqarish ruxsatnomasi: "
            f"**{'berildi' if enable else 'olindi'}**"
        )
    else:
        await message.reply_text("⚠️ Saqlashda xatolik, qayta urinib ko'ring.")

# gate_feature shu yerdan ham eksport qilinadi (qulaylik uchun)
__all__ = ["gate_feature", "FEATURES_BTN", "NO_PERMISSION_TEXT"]
