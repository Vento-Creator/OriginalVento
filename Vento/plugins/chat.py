from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
)
from database import (
    has_accepted_chat_terms, accept_chat_terms,
    send_chat_message, get_chat_history, get_unread_chat_count,
    mark_chat_messages_read, block_user, unblock_user, is_user_blocked,
    get_blocked_users, mute_user, unmute_user, is_user_muted,
    get_muted_users, get_known_user, get_all_chats_for_owner,
    get_chat_messages_for_owner, delete_chat, has_chat_before
)
from config import user_states, is_admin, is_owner, SUPER_ADMIN_ID
from rate_limiter import check_rate_limit
import logging

logger = logging.getLogger(__name__)


CHAT_STATE_VIEWING_CHATS = "chat_viewing_chats"
CHAT_STATE_VIEWING_MESSAGES = "chat_viewing_messages"
CHAT_STATE_SENDING_MESSAGE = "chat_sending_message"
CHAT_STATE_SEARCHING_USER = "chat_searching_user"


async def get_chat_keyboard(uid: int) -> ReplyKeyboardMarkup:
    """Chat menyusi tugmalari"""
    unread = await get_unread_chat_count(uid)
    badge = f" ({unread})" if unread > 0 else ""
    
    rows = [
        [KeyboardButton(f"💬 Chatlar{badge}")],
        [KeyboardButton("🔙 Bosh menyu")]
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

async def format_timestamp(ts: int) -> str:
    """Timestampni formatlash"""
    import datetime
    dt = datetime.datetime.fromtimestamp(ts)
    return dt.strftime("%H:%M · %d.%m.%Y")


@Client.on_callback_query(filters.regex("^menu_chat$"))
async def menu_chat_callback(client: Client, cq: CallbackQuery):
    """Chat menyusi callback"""
    uid = cq.from_user.id
    
    if not await has_accepted_chat_terms(uid):
        await cq.message.edit_text(
            "📜 **Chat shartlari va qoidalari**\n\n"
            "⚠️ Chatdan foydalanish uchun quyidagi shartlarga rozilik bildirishingiz kerak:\n\n"
            "1. ❌ Odam haqida yomon gapirmang\n"
            "2. ❌ Spam yubormang\n"
            "3. ❌ Noqonuniy kontent yubormang\n"
            "4. ❀ Hurmatli bo'ling\n"
            "5. ❀ Qoidalarga rioqa qiling\n\n"
            "Qoidalarni buzgan foydalanuvchilar chatdan bloklanishi mumkin.\n\n"
            "👇 **Roziman** tugmasini bosish orqali shartlarga rozilik bildirasiz:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Roziman", callback_data="chat_accept_terms")],
                [InlineKeyboardButton("❌ Bekor qilish", callback_data="menu_main")]
            ])
        )
        await cq.answer()
        return
    
    await show_chats_list(client, cq.message, uid)
    await cq.answer()

@Client.on_callback_query(filters.regex("^chat_accept_terms$"))
async def chat_accept_terms_callback(client: Client, cq: CallbackQuery):
    """Chat shartlariga rozilik"""
    uid = cq.from_user.id
    
    await accept_chat_terms(uid)
    
    await cq.answer("✅ Shartlar qabul qilindi!")
    await show_chats_list(client, cq.message, uid)


async def show_chats_list(client: Client, message: Message, uid: int):
    """Chatlar ro'yxatini ko'rsatish"""
    chats = await get_chat_history(uid)
    
    if not chats:
        await message.edit_text(
            "💬 **Chatlar**\n\n"
            "Sizda hali chatlar yo'q.\n\n"
            "Yangi chat boshlash uchun boshqa foydalanuvchining ID sini kiriting:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Yangi chat boshlash", callback_data="chat_new_search")],
                [InlineKeyboardButton("🔙 Bosh menyu", callback_data="menu_main")]
            ])
        )
        return
    
    keyboard = []
    for chat in chats[:10]:  # Show first 10 chats
        other_id = chat["other_user_id"]
        other_user = await get_known_user(other_id)
        if other_user:
            name = other_user.get("first_name", "Foydalanuvchi")
            username = other_user.get("username", "")
            display = f"{name} (@{username})" if username else name
            keyboard.append([InlineKeyboardButton(display, callback_data=f"chat_open_{other_id}")])
    
    keyboard.append([InlineKeyboardButton("➕ Yangi chat boshlash", callback_data="chat_new_search")])
    keyboard.append([InlineKeyboardButton("🚫 Bloklanganlar", callback_data="chat_blocked_list")])
    keyboard.append([InlineKeyboardButton("🔙 Bosh menyu", callback_data="menu_main")])
    
    await message.edit_text(
        "💬 **Chatlar**\n\n"
        "Chatni tanlang:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


@Client.on_callback_query(filters.regex("^chat_new_search$"))
async def chat_new_search_callback(client: Client, cq: CallbackQuery):
    """Yangi chat boshlash - user ID yoki username kiritish"""
    uid = cq.from_user.id
    user_states[uid] = CHAT_STATE_SEARCHING_USER
    
    await cq.message.edit_text(
        "➕ **Yangi chat boshlash**\n\n"
        "Chat boshlash uchun foydalanuvchi ID yoki username kiriting:\n"
        "Masalan: `123456789` yoki `@username`\n\n"
        "💡 ID ni bilmasangiz, foydalanuvchini /user komandasi orqali topishingiz mumkin.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="chat_back")]
        ])
    )
    await cq.answer()

@Client.on_callback_query(filters.regex("^chat_back$"))
async def chat_back_callback(client: Client, cq: CallbackQuery):
    """Chat menyusiga qaytish"""
    uid = cq.from_user.id
    user_states.pop(uid, None)

    await show_chats_list(client, cq.message, uid)
    await cq.answer()

@Client.on_callback_query(filters.regex("^chat_blocked_list$"))
async def chat_blocked_list_callback(client: Client, cq: CallbackQuery):
    """Bloklangan foydalanuvchilar ro'yxati"""
    uid = cq.from_user.id
    blocked_users = await get_blocked_users(uid)

    if not blocked_users:
        await cq.message.edit_text(
            "🚫 **Bloklanganlar**\n\n"
            "Siz hech kimni bloklamagansiz.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Chatlar ro'yxati", callback_data="chat_back")]
            ])
        )
        await cq.answer()
        return

    keyboard = []
    for blocked in blocked_users:
        blocked_id = blocked["blocked_id"]
        blocked_user = await get_known_user(blocked_id)
        if blocked_user:
            name = blocked_user.get("first_name", "Foydalanuvchi")
            username = blocked_user.get("username", "")
            display = f"{name} (@{username})" if username else name
            keyboard.append([InlineKeyboardButton(f"🚫 {display}", callback_data=f"chat_unblock_{blocked_id}")])

    keyboard.append([InlineKeyboardButton("🔙 Chatlar ro'yxati", callback_data="chat_back")])

    await cq.message.edit_text(
        f"🚫 **Bloklanganlar**\n\n"
        f"Jami: {len(blocked_users)} ta",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await cq.answer()

@Client.on_callback_query(filters.regex("^chat_unblock_(\\d+)$"))
async def chat_unblock_callback(client: Client, cq: CallbackQuery):
    """Blokni olib tashlash"""
    uid = cq.from_user.id
    match = cq.data.split("_")
    blocked_id = int(match[2])

    await unblock_user(uid, blocked_id)

    await cq.answer("🔓 Blok ochildi!")
    await chat_blocked_list_callback(client, cq)


@Client.on_callback_query(filters.regex("^chat_open_(\\d+)$"))
async def chat_open_callback(client: Client, cq: CallbackQuery):
    """Chatni ochish va xabalarni ko'rsatish"""
    uid = cq.from_user.id
    match = cq.data.split("_")
    other_id = int(match[2])
    
    if await is_user_blocked(uid, other_id):
        await cq.answer("⛔️ Bu foydalanuvchini bloklagansiz!", show_alert=True)
        return
    
    await mark_chat_messages_read(uid, other_id)
    
    user_states[uid] = CHAT_STATE_VIEWING_MESSAGES
    user_states[f"{uid}_current_chat"] = other_id
    
    await show_chat_messages(client, cq.message, uid, other_id)
    await cq.answer()

async def show_chat_messages(client: Client, message: Message, uid: int, other_id: int):
    """Chat xabarlarni ko'rsatish"""
    messages = await get_chat_history(uid, other_id, limit=50)

    is_first_message = not await has_chat_before(other_id, uid) and messages

    if not messages:
        text = "💬 **Chat**\n\nHali xabarlar yo'q. Birinchi xabarni yuboring!"
    else:
        text_parts = ["💬 **Chat**\n"]
        for msg in messages:
            is_me = msg["sender_id"] == uid
            sender = "Siz" if is_me else "U"
            prefix = "👤" if is_me else "👥"
            msg_text = msg["message"][:100] + "..." if len(msg["message"]) > 100 else msg["message"]
            time_str = await format_timestamp(msg["timestamp"])
            text_parts.append(f"\n{prefix} **{sender}** [{time_str}]\n{msg_text}")
        
        text = "\n".join(text_parts)
    
    other_user = await get_known_user(other_id)
    other_name = other_user.get("first_name", "Foydalanuvchi") if other_user else "Foydalanuvchi"
    
    keyboard = [
        [InlineKeyboardButton("✍️ Xabar yuborish", callback_data=f"chat_send_{other_id}")],
        [InlineKeyboardButton("⚙️ Sozlamalar", callback_data=f"chat_settings_{other_id}")],
        [InlineKeyboardButton("� Chatni o'chirish", callback_data=f"chat_delete_{other_id}")],
        [InlineKeyboardButton("� Chatlar ro'yxati", callback_data="chat_back")]
    ]

    if is_first_message:
        keyboard.insert(0, [InlineKeyboardButton(f"🚫 {other_name} ni bloklash", callback_data=f"chat_block_{other_id}")])
    
    await message.edit_text(
        f"{text}\n\n💬 **Chat bilan:** {other_name}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


@Client.on_callback_query(filters.regex("^chat_send_(\\d+)$"))
async def chat_send_callback(client: Client, cq: CallbackQuery):
    """Xabar yuborish - matn kiritish"""
    uid = cq.from_user.id
    match = cq.data.split("_")
    other_id = int(match[2])
    
    user_states[uid] = CHAT_STATE_SENDING_MESSAGE
    user_states[f"{uid}_current_chat"] = other_id
    
    await cq.message.edit_text(
        "✍️ **Xabar yuborish**\n\n"
        "Xabaringizni yuboring:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Bekor qilish", callback_data=f"chat_back_to_chat")]
        ])
    )
    await cq.answer()

@Client.on_callback_query(filters.regex("^chat_back_to_chat$"))
async def chat_back_to_chat_callback(client: Client, cq: CallbackQuery):
    """Chatga qaytish"""
    uid = cq.from_user.id
    other_id = user_states.get(f"{uid}_current_chat")
    
    if other_id:
        user_states[uid] = CHAT_STATE_VIEWING_MESSAGES
        await show_chat_messages(client, cq.message, uid, other_id)
    else:
        await show_chats_list(client, cq.message, uid)
    
    await cq.answer()


@Client.on_callback_query(filters.regex("^chat_settings_(\\d+)$"))
async def chat_settings_callback(client: Client, cq: CallbackQuery):
    """Chat sozlamalari"""
    uid = cq.from_user.id
    match = cq.data.split("_")
    other_id = int(match[2])

    is_blocked = await is_user_blocked(uid, other_id)
    is_muted = await is_user_muted(uid, other_id)

    block_text = "🔓 Blokni ochish" if is_blocked else "🔒 Bloklash"
    mute_text = "🔊 Ovozni yoqish" if is_muted else "🔇 Ovozsiz qilish"

    keyboard = [
        [InlineKeyboardButton(block_text, callback_data=f"chat_block_{other_id}")],
        [InlineKeyboardButton(mute_text, callback_data=f"chat_mute_{other_id}")],
        [InlineKeyboardButton("🔙 Chatga qaytish", callback_data=f"chat_open_{other_id}")]
    ]

    await cq.message.edit_text(
        "⚙️ **Chat sozlamalari**\n\n"
        "Boshqaruv tugmalarini tanlang:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await cq.answer()

@Client.on_callback_query(filters.regex("^chat_delete_(\\d+)$"))
async def chat_delete_callback(client: Client, cq: CallbackQuery):
    """Chatni o'chirish"""
    uid = cq.from_user.id
    match = cq.data.split("_")
    other_id = int(match[2])

    await cq.message.edit_text(
        "🗑 **Chatni o'chirish**\n\n"
        "Haqiqatan ham bu chatni o'chirmoqchimisiz?\n\n"
        "⚠️ Bu amalni qaytarib bo'lmaydi!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Ha, o'chirish", callback_data=f"chat_delete_confirm_{other_id}")],
            [InlineKeyboardButton("❌ Bekor qilish", callback_data=f"chat_open_{other_id}")]
        ])
    )
    await cq.answer()

@Client.on_callback_query(filters.regex("^chat_delete_confirm_(\\d+)$"))
async def chat_delete_confirm_callback(client: Client, cq: CallbackQuery):
    """Chatni o'chirishni tasdiqlash"""
    uid = cq.from_user.id
    match = cq.data.split("_")
    other_id = int(match[2])

    await delete_chat(uid, other_id)

    await cq.message.edit_text(
        "✅ **Chat o'chirildi!**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Chatlar ro'yxati", callback_data="chat_back")]
        ])
    )
    await cq.answer()

@Client.on_callback_query(filters.regex("^chat_block_(\\d+)$"))
async def chat_block_callback(client: Client, cq: CallbackQuery):
    """Blok/blokni ochish"""
    uid = cq.from_user.id
    match = cq.data.split("_")
    other_id = int(match[2])
    
    if await is_user_blocked(uid, other_id):
        await unblock_user(uid, other_id)
        await cq.answer("🔓 Blok ochildi!")
    else:
        await block_user(uid, other_id)
        await cq.answer("🔒 Foydalanuvchi bloklandi!")
    
    await chat_settings_callback(client, cq)

@Client.on_callback_query(filters.regex("^chat_mute_(\\d+)$"))
async def chat_mute_callback(client: Client, cq: CallbackQuery):
    """Mute/unmute"""
    uid = cq.from_user.id
    match = cq.data.split("_")
    other_id = int(match[2])
    
    if await is_user_muted(uid, other_id):
        await unmute_user(uid, other_id)
        await cq.answer("🔊 Ovoz yoqildi!")
    else:
        await mute_user(uid, other_id)
        await cq.answer("🔇 Ovozsiz qilindi!")
    
    await chat_settings_callback(client, cq)


@Client.on_message(filters.private & filters.text & ~filters.command(["start"]), group=-11)
async def chat_message_handler(client: Client, message: Message):
    """Chat xabarlarni qabul qilish"""
    from config import user_states
    from pyrogram import ContinuePropagation
    
    uid = message.from_user.id
    state = user_states.get(uid)
    text = message.text.strip()
    
    logger.debug(f"[CHAT] uid={uid}, state={state}, text={text}")
    
    if state and (state.startswith("waiting_for_timer_message_") or 
                  state.startswith("waiting_for_timer_interval_") or
                  state.startswith("waiting_for_timer_repeat_") or
                  state.startswith("waiting_for_timer_repeat_delay_") or
                  state.startswith("editing_timer_")):
        raise ContinuePropagation
    
    if state == CHAT_STATE_SEARCHING_USER:
        try:
            input_text = message.text.strip()
            
            if input_text.startswith("@"):
                username = input_text[1:]  # Remove @ symbol
                
                from database import search_users
                found_ids = await search_users(username)
                
                if not found_ids:
                    await message.reply_text(
                        f"⚠️ **Bu foydalanuvchi botda topilmadi!**\n\n"
                        f"Username: `@{username}`\n\n"
                        f"Keling, uni taklif qilamiz!",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("📋 Havolani olish", callback_data=f"chat_invite_username_{username}")],
                            [InlineKeyboardButton("❌ Bekor qilish", callback_data="chat_back")]
                        ])
                    )
                    return
                
                other_id = found_ids[0]
                other_user = await get_known_user(other_id)
                
                if not other_user:
                    await message.reply_text(
                        f"⚠️ **Bu foydalanuvchi botda emas!**\n\n"
                        f"Username: `@{username}`\n\n"
                        f"Keling, uni taklif qilamiz!",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("📋 Havolani olish", callback_data=f"chat_invite_username_{username}")],
                            [InlineKeyboardButton("❌ Bekor qilish", callback_data="chat_back")]
                        ])
                    )
                    return
            else:
                clean_text = input_text
                clean_text = ''.join(c for c in clean_text if c.isdigit() or c == '-')
                if not clean_text or clean_text == '-':
                    raise ValueError()
                other_id = int(clean_text)
                
                other_user = await get_known_user(other_id)
                if not other_user:
                    await message.reply_text(
                        f"⚠️ **Bu foydalanuvchi botda emas!**\n\n"
                        f"ID: `{other_id}`\n\n"
                        f"Keling, uni taklif qilamiz!",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("📋 Havolani olish", callback_data=f"chat_invite_{other_id}")],
                            [InlineKeyboardButton("❌ Bekor qilish", callback_data="chat_back")]
                        ])
                    )
                    return
            
            if other_id == uid:
                await message.reply_text(
                    "❌ O'zingiz bilan chat qila olmaysiz.\n"
                    "Boshqa ID yoki username kiriting:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("❌ Bekor qilish", callback_data="chat_back")]
                    ])
                )
                return
            
            user_states[uid] = CHAT_STATE_VIEWING_MESSAGES
            user_states[f"{uid}_current_chat"] = other_id
            
            other_user = await get_known_user(other_id)
            other_name = other_user.get("first_name", "Foydalanuvchi") if other_user else "Foydalanuvchi"
            username_str = f" (@{other_user.get('username')})" if other_user and other_user.get("username") else ""
            
            await message.reply_text(
                f"💬 **Chat**\n\n"
                f"Chat bilan: **{other_name}**{username_str}\n\n"
                f"Hali xabarlar yo'q. Birinchi xabarni yuboring!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✍️ Xabar yuborish", callback_data=f"chat_send_{other_id}")],
                    [InlineKeyboardButton("⚙️ Sozlamalar", callback_data=f"chat_settings_{other_id}")],
                    [InlineKeyboardButton("🗑 Chatni o'chirish", callback_data=f"chat_delete_{other_id}")],
                    [InlineKeyboardButton("🔙 Chatlar ro'yxati", callback_data="chat_back")]
                ])
            )
            return  # Successfully processed, stop propagation
        except ValueError:
            await message.reply_text(
                "❌ Noto'g'ri format.\n"
                "Faqat raqamli ID yoki @username kiriting.\n"
                "Masalan: `123456789` yoki `@username`",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Bekor qilish", callback_data="chat_back")]
                ])
            )
            return  # Successfully processed error, stop propagation
    
    elif state == CHAT_STATE_SENDING_MESSAGE:
        other_id = user_states.get(f"{uid}_current_chat")
        if not other_id:
            user_states.pop(uid, None)
            raise ContinuePropagation
        
        if await is_user_blocked(uid, other_id):
            await message.reply_text("⛔️ Bu foydalanuvchini bloklagansiz!")
            user_states.pop(uid, None)
            return
        
        if await is_user_blocked(other_id, uid):
            await message.reply_text("⛔️ Bu foydalanuvchi sizni bloklagan!")
            user_states.pop(uid, None)
            return
        
        msg_text = message.text.strip()
        if len(msg_text) < 1:
            await message.reply_text("❌ Xabar bo'sh bo'lishi mumkin emas.")
            return
        
        await send_chat_message(uid, other_id, msg_text)
        
        is_muted = await is_user_muted(other_id, uid)
        
        user_states[uid] = CHAT_STATE_VIEWING_MESSAGES
        
        await message.reply_text(
            "✅ Xabar yuborildi!" + (" (Ovozsiz)" if is_muted else ""),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 Chatga qaytish", callback_data=f"chat_open_{other_id}")]
            ])
        )
        
        if not is_muted:
            try:
                await client.send_message(
                    other_id,
                    f"💬 **Yangi xabar!**\n\n"
                    f"Sizga yangi xabar keldi. Chatni ko'rish uchun \"💬 Chatlar\" tugmasini bosing."
                )
            except:
                pass
        
        return  # Successfully processed, stop propagation
    
    raise ContinuePropagation  # Not in chat state, let other handlers process


@Client.on_callback_query(filters.regex(r"^chat_invite_(\d+)$"))
async def chat_invite_callback(client: Client, cq: CallbackQuery):
    """Taklif havolasini yuborish (ID orqali)"""
    uid = cq.from_user.id
    match = cq.data.split("_")
    target_id = match[2]
    
    invitation_text = (
        "`Salom! Men ajoyib Vento bot foydalanuvchisiman. "
        "Menga qoshiling va birgalikda super imkoniyatlarga erishing! "
        "Mana havola, o'tib login qiling:\n\n"
        "@empire_family_bot\n\n"
        "Sizni kutamiz!`"
    )
    
    await cq.message.reply_text(
        f"📋 **Taklif matni**\n\n"
        f"{invitation_text}\n\n"
        f"💡 Bu matnni nusxalab, {target_id} ID li foydalanuvchiga yuboring.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Chatlar ro'yxati", callback_data="chat_back")]
        ])
    )
    await cq.answer()

@Client.on_callback_query(filters.regex(r"^chat_invite_username_(.+)$"))
async def chat_invite_username_callback(client: Client, cq: CallbackQuery):
    """Taklif havolasini yuborish (username orqali)"""
    uid = cq.from_user.id
    match = cq.data.split("_", 3)  # Split into: chat_invite_username_<username>
    username = match[3]
    
    invitation_text = (
        "Salom! Men ajoyib Vento bot foydalanuvchisiman. "
        "Menga qoshiling va birgalikda super imkoniyatlarga erishing! "
        "Mana havola, o'tib login qiling:\n\n"
        "@empire_family_bot\n\n"
        "Sizni kutamiz!"
    )
    
    await cq.message.reply_text(
        f"📋 **Taklif matni**\n\n"
        f"{invitation_text}\n\n"
        f"💡 Bu matnni nusxalab, @{username} foydalanuvchiga yuboring.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Chatlar ro'yxati", callback_data="chat_back")]
        ])
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^owner_chat_monitor$"))
async def owner_chat_monitor_callback(client: Client, cq: CallbackQuery):
    """Owner uchun barcha chatlarni ko'rish"""
    import time
    start_time = time.time()
    logger.info("[DIAG] HANDLER_START: handler=owner_chat_monitor_callback callback_data=%s", cq.data)
    
    try:
        uid = cq.from_user.id
        
        if not is_owner(uid):
            logger.info("[DIAG] OWNER_CHECK_FAILED: user_id=%d", uid)
            await cq.answer("⛔️ Sizda huquq yo'q!", show_alert=True)
            return
        
        chats = await get_all_chats_for_owner(limit=50)
        
        if not chats:
            await cq.message.edit_text(
                "👁️ **Chat monitoring**\n\n"
                "Hali chatlar yo'q.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Bosh menyu", callback_data="menu_main")]
                ])
            )
            await cq.answer()
            
            duration_ms = (time.time() - start_time) * 1000
            logger.info("[DIAG] HANDLER_END: handler=owner_chat_monitor_callback duration_ms=%.2f (no chats)", duration_ms)
            return
        
        keyboard = []
        for chat in chats[:20]:
            user1 = chat["user1"]
            user2 = chat["user2"]
            msg_count = chat["message_count"]
            time_str = await format_timestamp(chat["last_timestamp"])
            keyboard.append([
                InlineKeyboardButton(
                    f"💬 {user1} ↔ {user2} ({msg_count} msg) [{time_str}]",
                    callback_data=f"owner_view_chat_{user1}_{user2}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 Bosh menyu", callback_data="menu_main")])
        
        await cq.message.edit_text(
            "👁️ **Chat monitoring**\n\n"
            "Barcha chatlar:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await cq.answer()
        
        duration_ms = (time.time() - start_time) * 1000
        logger.info("[DIAG] HANDLER_END: handler=owner_chat_monitor_callback duration_ms=%.2f", duration_ms)
        if duration_ms > 2000:
            logger.warning("[DIAG] HANDLER_SLOW: handler=owner_chat_monitor_callback duration_ms=%.2f", duration_ms)
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error("[DIAG] HANDLER_ERROR: handler=owner_chat_monitor_callback duration_ms=%.2f error=%s", duration_ms, e, exc_info=True)
        raise

@Client.on_callback_query(filters.regex("^owner_view_chat_(\\d+)_(\\d+)$"))
async def owner_view_chat_callback(client: Client, cq: CallbackQuery):
    """Owner uchun ma'lum chatni ko'rish"""
    uid = cq.from_user.id
    
    if not is_owner(uid):
        await cq.answer("⛔️ Sizda huquq yo'q!", show_alert=True)
        return
    
    match = cq.data.split("_")
    user1 = int(match[3])
    user2 = int(match[4])
    
    messages = await get_chat_messages_for_owner(user1, user2, limit=100)
    
    if not messages:
        text = "💬 **Chat**\n\nXabarlar yo'q."
    else:
        text_parts = [f"💬 **Chat: {user1} ↔ {user2}**\n"]
        for msg in messages:
            sender = msg["sender_id"]
            msg_text = msg["message"][:100] + "..." if len(msg["message"]) > 100 else msg["message"]
            time_str = await format_timestamp(msg["timestamp"])
            text_parts.append(f"\n👤 **{sender}** [{time_str}]\n{msg_text}")
        
        text = "\n".join(text_parts)
    
    await cq.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Orqaga", callback_data="owner_chat_monitor")]
        ])
    )
    await cq.answer()
