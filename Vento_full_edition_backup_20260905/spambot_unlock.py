import asyncio
import logging
from pyrogram import Client

logger = logging.getLogger(__name__)

UNLOCK_KEYWORDS = ["qush", "erkin", "free", "premium", "unlimited", "no limits"]

async def send_and_check_unlock(client: Client, max_attempts: int = 5) -> bool:
    """
    Send messages to @spambot and check if unlocked
    
    Args:
        client: Pyrogram client instance
        max_attempts: Maximum number of attempts to unlock
    
    Returns:
        bool: True if unlocked, False otherwise
    """
    for attempt in range(max_attempts):
        try:
            await client.send_message("spambot", "/start")
            await asyncio.sleep(1)
            
            await client.send_message("spambot", "/start")
            await asyncio.sleep(2)
            
            async for message in client.get_chat_history("spambot", limit=5):
                if message.from_user and message.from_user.username == "SpamBot":
                    if message.text:
                        text = message.text.lower()
                        if any(keyword in text for keyword in UNLOCK_KEYWORDS):
                            logger.info("Spambot unlocked! Keyword found: %s", message.text[:50])
                            return True
            
            logger.info("Attempt %d/%d - no unlock keywords found", attempt + 1, max_attempts)
            await asyncio.sleep(2)
            
        except Exception as e:
            logger.warning("Spambot unlock xatosi (attempt %d): %s", attempt + 1, e)
            await asyncio.sleep(2)
    
    return False

async def unlock_with_message(client: Client, message: str = "free", max_attempts: int = 3) -> bool:
    """
    Send specific message to @spambot and check for unlock
    
    Args:
        client: Pyrogram client instance
        message: Message to send
        max_attempts: Maximum number of attempts
    
    Returns:
        bool: True if unlocked, False otherwise
    """
    for attempt in range(max_attempts):
        try:
            await client.send_message("spambot", message)
            await asyncio.sleep(2)
            
            async for msg in client.get_chat_history("spambot", limit=5):
                if msg.from_user and msg.from_user.username == "SpamBot":
                    if msg.text:
                        text = msg.text.lower()
                        if any(keyword in text for keyword in UNLOCK_KEYWORDS):
                            logger.info("Spambot unlocked with message! Keyword found: %s", msg.text[:50])
                            return True
            
            logger.info("Message attempt %d/%d - no unlock keywords found", attempt + 1, max_attempts)
            await asyncio.sleep(2)
            
        except Exception as e:
            logger.warning("Spambot message unlock xatosi (attempt %d): %s", attempt + 1, e)
            await asyncio.sleep(2)
    
    return False

async def check_if_locked(client: Client) -> bool:
    """
    Check if account is currently locked by checking recent spambot messages
    
    Args:
        client: Pyrogram client instance
    
    Returns:
        bool: True if locked, False if unlocked
    """
    try:
        async for message in client.get_chat_history("spambot", limit=3):
            if message.from_user and message.from_user.username == "SpamBot":
                if message.text:
                    text = message.text.lower()
                    if any(keyword in text for keyword in UNLOCK_KEYWORDS):
                        return False
        return True
    except Exception as e:
        logger.warning("Check lock status xatosi: %s", e)
        return True  # Assume locked if we can't check
