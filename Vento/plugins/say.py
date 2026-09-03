from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import Message
from config import is_admin

import time

# "Say" buyrug'i guruh adminligini qayta tekshirmaslik uchun kesh
# {chat_id: {user_id: (is_admin_flag, timestamp)}}
_group_admin_cache = {}
_GROUP_ADMIN_CACHE_TTL = 60  # soniya


async def say_admin_filter(client: Client, _, message: Message):
    """Faqat bot adminlari yoki guruh adminlariga ruxsat beradi."""
    # 1) Bot adminlari (config/bazadagi adminlar)
    if message.from_user and is_admin(message.from_user.id):
        return True

    # 2) Anonim guruh adminlari (Telegram nomidan yozadi)
    if message.sender_chat and message.sender_chat.id == message.chat.id:
        return True
    if message.from_user and message.from_user.id == 1087968824:  # GroupAnonymousBot
        return True

    if not message.from_user:
        return False

    # 3) Guruh adminlari (owner yoki administrator) — kesh bilan
    chat_id = message.chat.id
    user_id = message.from_user.id
    now = time.time()

    chat_cache = _group_admin_cache.setdefault(chat_id, {})
    cached = chat_cache.get(user_id)
    if cached:
        is_grp_admin, ts = cached
        if now - ts < _GROUP_ADMIN_CACHE_TTL:
            return is_grp_admin

    try:
        member = await client.get_chat_member(chat_id, user_id)
        result = member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        result = False

    chat_cache[user_id] = (result, now)
    return result


say_admin_only = filters.create(say_admin_filter)



@Client.on_message(filters.command("say") & filters.group & say_admin_only)
async def say_command_handler(client: Client, message: Message):
    """Handle the /say command in groups to speak as the bot (admins only)."""

    if len(message.command) < 2:
        # Command used without arguments
        return
        
    # Get the arguments part of the message
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return
        
    args_text = parts[1].strip()
    if not args_text:
        return
        
    # Check if it starts with "anon" (case-insensitive)
    lower_args = args_text.lower()
    
    if lower_args.startswith("anon ") or lower_args == "anon":
        # Extract the message after "anon"
        msg_text = args_text[4:].strip()
        if not msg_text:
            return
            
        reply_text = f"Anonim habari - {msg_text}"
    else:
        msg_text = args_text
        user = message.from_user
        
        if not user:
            return
            
        if user.username:
            user_str = f"@{user.username}"
        else:
            name = user.first_name or "Foydalanuvchi"
            user_str = f"[{name}](tg://user?id={user.id})"
            
        reply_text = f"{user_str} - {msg_text}"
        
    # Check if there's a message to reply to
    reply_to_id = message.reply_to_message.id if message.reply_to_message else None
        
    # Attempt to delete the original command message for anonymity/cleanliness
    try:
        await message.delete()
    except Exception:
        pass
        
    # Send the processed message back to the group
    await client.send_message(message.chat.id, reply_text, reply_to_message_id=reply_to_id)
