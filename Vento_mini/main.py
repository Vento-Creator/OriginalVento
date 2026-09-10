import asyncio
import logging
import sys
import os
from pyrogram import Client, idle
from config import API_ID, API_HASH, BOT_TOKEN, BASE_DIR
from database import init_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("Vento_mini")


async def main():
    logger.info("⚡ Vento Mini ishga tushmoqda...")

    if not BOT_TOKEN or not API_ID or not API_HASH:
        logger.error("❌ API_ID, API_HASH yoki BOT_TOKEN sozlangan emas! .env faylni tekshiring.")
        sys.exit(1)

    # Initialize Database
    await init_db()

    # Create Pyrogram Client Bot with plugins auto-loading
    app = Client(
        "vento_mini_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        workdir=BASE_DIR,
        plugins=dict(root="plugins")
    )

    await app.start()
    bot_me = await app.get_me()
    logger.info(f"✅ Vento Mini Bot muvaffaqiyatli ishga tushdi: @{bot_me.username} ({bot_me.id})")

    await idle()
    await app.stop()
    logger.info("🛑 Vento Mini Bot to'xtatildi.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
