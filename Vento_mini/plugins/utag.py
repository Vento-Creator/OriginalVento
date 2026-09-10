import logging
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database import get_user_settings_db, save_user_setting_db, add_utag_timer, get_user_timers, delete_timer_db
from session_manager import get_user_client
from utag_system.utag_service import UtagService, stop_user_utag

from plugins.menu import check_account_guard

logger = logging.getLogger(__name__)

# State for custom timer/speed input: user_id -> {"action": str}
_utag_input_states = {}


@Client.on_callback_query(filters.regex("^utag_menu$"))
async def utag_menu_callback(client: Client, cq: CallbackQuery):
    if not await check_account_guard(cq):
        return
    user_id = cq.from_user.id
    st = await get_user_settings_db(user_id)

    speed = st.get("utag_speed", 1.5)
    typing_sim = "✅ Yoqilgan" if st.get("utag_typing", 1) else "❌ O'chirilgan"
    del_timer = st.get("utag_delete_timer", 0)
    del_text = f"{del_timer} soniya" if del_timer > 0 else "❌ O'chirilgan"

    text = (
        f"📣 **UTAG (Guruhlarda tag qilish) Sozlamalari**\n\n"
        f"⚡ **Tag qilish tezligi:** {speed} soniya\n"
        f"✍️ **Typing (Yozish) simulyatsiyasi:** {typing_sim}\n"
        f"🗑 **Avto-o'chirish taymeri:** {del_text}\n\n"
        f"💡 **Foydalanish:**\n"
        f"Guruhga o'tib `/utag Matn` yoki `@utag Matn` deb yozing.\n"
        f"To'xtatish uchun: `/stop` bosing."
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"⚡ Tezlik: {speed}s", callback_data="utag_set_speed"),
            InlineKeyboardButton(f"✍️ Typing: {typing_sim}", callback_data="utag_toggle_typing")
        ],
        [
            InlineKeyboardButton(f"🗑 Avto-o'chirish: {del_text}", callback_data="utag_set_timer")
        ],
        [
            InlineKeyboardButton("🛑 Hozirgi UTAGni to'xtatish", callback_data="utag_stop_now")
        ],
        [
            InlineKeyboardButton("🏠 Asosiy menyu", callback_data="menu_main")
        ]
    ])

    await cq.message.edit_text(text, reply_markup=kb)
    await cq.answer()


@Client.on_callback_query(filters.regex("^utag_toggle_typing$"))
async def utag_toggle_typing_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id
    st = await get_user_settings_db(user_id)
    curr = st.get("utag_typing", 1)
    new_val = 0 if curr else 1

    await save_user_setting_db(user_id, "utag_typing", new_val)
    await utag_menu_callback(client, cq)


@Client.on_callback_query(filters.regex("^utag_set_speed$"))
async def utag_set_speed_callback(client: Client, cq: CallbackQuery):
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚡ 1 soniya", callback_data="utag_val_speed_1.0"),
            InlineKeyboardButton("⚡ 1.5 soniya", callback_data="utag_val_speed_1.5"),
            InlineKeyboardButton("⚡ 2 soniya", callback_data="utag_val_speed_2.0")
        ],
        [
            InlineKeyboardButton("⚡ 3 soniya", callback_data="utag_val_speed_3.0"),
            InlineKeyboardButton("⚡ 5 soniya", callback_data="utag_val_speed_5.0")
        ],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="utag_menu")]
    ])
    await cq.message.edit_text("⚡ **UTAG tezligini tanlang (soniyalarda):**", reply_markup=kb)
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^utag_val_speed_([\d\.]+)$"))
async def utag_val_speed_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id
    speed = float(cq.matches[0].group(1))

    await save_user_setting_db(user_id, "utag_speed", speed)
    await cq.answer(f"✅ Tezlik {speed}s ga o'rnatildi!")
    await utag_menu_callback(client, cq)


@Client.on_callback_query(filters.regex("^utag_set_timer$"))
async def utag_set_timer_callback(client: Client, cq: CallbackQuery):
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("❌ O'chirish (0s)", callback_data="utag_val_timer_0"),
            InlineKeyboardButton("⏱ 5 soniya", callback_data="utag_val_timer_5"),
            InlineKeyboardButton("⏱ 10 soniya", callback_data="utag_val_timer_10")
        ],
        [
            InlineKeyboardButton("⏱ 30 soniya", callback_data="utag_val_timer_30"),
            InlineKeyboardButton("⏱ 60 soniya", callback_data="utag_val_timer_60")
        ],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="utag_menu")]
    ])
    await cq.message.edit_text("🗑 **Tag xabarlarini avto-o'chirish vaqtini tanlang:**", reply_markup=kb)
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^utag_val_timer_(\d+)$"))
async def utag_val_timer_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id
    seconds = int(cq.matches[0].group(1))

    await save_user_setting_db(user_id, "utag_delete_timer", seconds)
    await cq.answer(f"✅ Avto-o'chirish {seconds}s ga sozlandi!")
    await utag_menu_callback(client, cq)


@Client.on_callback_query(filters.regex("^utag_stop_now$"))
async def utag_stop_now_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id
    stopped = stop_user_utag(user_id)

    if stopped:
        await cq.answer("🛑 UTAG to'xtatildi!", show_alert=True)
    else:
        await cq.answer("ℹ️ Hozirda faol UTAG topilmadi.", show_alert=True)


# Group Stop Command: /stop
@Client.on_message(filters.command(["stop", "cancel"]))
async def handle_stop_command(client: Client, message: Message):
    user_id = message.from_user.id
    if stop_user_utag(user_id):
        await message.reply_text("🛑 **UTAG jarayoni to'xtatildi!**")
    else:
        await message.reply_text("ℹ️ Hozirda faol UTAG jarayoni mavjud emas.")


# Group Tagging Command Trigger: /utag [tag_text]
@Client.on_message(filters.group & filters.command("utag"))
async def handle_utag_command(client: Client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    try:
        user_client = await get_user_client(user_id)
    except Exception as e:
        await message.reply_text(f"❌ Akkaunt ulanmagan yoki xatolik: {e}")
        return

    # Extract tag text
    cmd_args = message.text.split(maxsplit=1)
    tag_text = cmd_args[1] if len(cmd_args) > 1 else ""

    # Collect chat members via Userbot client
    members = []
    try:
        async for m in user_client.get_chat_members(chat_id):
            u = m.user
            if u and not u.is_bot and u.username:
                members.append(u.username)
    except Exception as e:
        logger.error(f"UTAG get_chat_members error: {e}")
        await message.reply_text("❌ Guruh a'zolarini o'qib bo'lmadi.")
        return

    if not members:
        await message.reply_text("📭 Guruhda tag qilinadigan foydalanuvchilar topilmadi.")
        return

    st = await get_user_settings_db(user_id)
    ok, msg_text = await UtagService.start_tagging(
        user_id, chat_id, client, user_client, members, tag_text, st
    )
    await message.reply_text(msg_text)
