from pyrogram import Client, filters
from pyrogram.types import Message

@Client.on_message(filters.command("say") & filters.group)
async def say_command_handler(client: Client, message: Message):
    """Handle the /say command in groups to speak as the bot."""
    
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
