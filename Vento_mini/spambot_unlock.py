import asyncio
import logging
from pyrogram import Client

logger = logging.getLogger(__name__)

UNLOCK_KEYWORDS = [
    "qush", "erkin", "free", "premium", "unlimited", "no limits",
    "good news", "xushxabar", "no restrictions", "erkinsiz"
]


async def send_and_check_unlock(client: Client, max_attempts: int = 4) -> bool:
    """SpamBot (@spambot) ga /start va xabarlar yuborib, akkauntni avtomatik spamdan chiqarish.
    
    Returns:
        bool: True (akkaunt toza va unlock bo'lsa), False (hali ham cheklangan bo'lsa)
    """
    bot_username = "SpamBot"

    for attempt in range(max_attempts):
        try:
            logger.info(f"SpamBot unlock urinishi {attempt + 1}/{max_attempts}")
            await client.send_message(bot_username, "/start")
            await asyncio.sleep(1.0)
            await client.send_message(bot_username, "/start")
            await asyncio.sleep(1.5)

            async for msg in client.get_chat_history(bot_username, limit=5):
                if msg.from_user and (msg.from_user.username == "SpamBot" or msg.from_user.id == 178220800):
                    if msg.text:
                        text = msg.text.lower()
                        if any(keyword in text for keyword in UNLOCK_KEYWORDS):
                            logger.info(f"Spambot unlocked! Matn: {msg.text[:60]}")
                            return True

            logger.info(f"Spambot attempt {attempt + 1}/{max_attempts} - unlock kalit so'zi topilmadi")
            await asyncio.sleep(1.5)

        except Exception as e:
            logger.warning(f"Spambot unlock xatosi (attempt {attempt + 1}): {e}")
            await asyncio.sleep(1.5)

    return False


async def check_if_locked(client: Client) -> bool:
    """Akkaunt holatini SpamBot tarixdan tekshirish. True = locked, False = unlocked."""
    bot_username = "SpamBot"
    try:
        await client.send_message(bot_username, "/start")
        await asyncio.sleep(1.5)
        async for msg in client.get_chat_history(bot_username, limit=3):
            if msg.from_user and (msg.from_user.username == "SpamBot" or msg.from_user.id == 178220800):
                if msg.text:
                    text = msg.text.lower()
                    if any(keyword in text for keyword in UNLOCK_KEYWORDS):
                        return False
        return True
    except Exception as e:
        logger.warning(f"check_if_locked error: {e}")
        return True
