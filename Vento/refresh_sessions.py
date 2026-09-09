"""
Userbot sessiyalarini refresh qilish scripti
Logout qilmasdan, faqat sessiyani yangilash
Bazalar saqlanadi, ma'lumotlar yo'qolmaydi

Ishlatish:
  python refresh_sessions.py            -> 1 marta (qo'lda) refresh va chiqish
  python refresh_sessions.py --daily    -> Har kuni avtomatik rejim (cheksiz loop)
"""
import asyncio
import os
import sys
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Vento root directoryga o'tish
VENTO_ROOT = Path(__file__).parent
sys.path.insert(0, str(VENTO_ROOT))

from session_manager import get_user_client_slot, get_active_slot, close_user_client_slot
from database import get_all_users, get_user_database_stats
from config import SESSIONS_DIR, API_ID, API_HASH

# Kuniga 1 marta avtomatik yangilash vaqti (UTC). Railway'da env orqali o'zgartirsa bo'ladi:
#   SESSION_REFRESH_HOUR   -> soat   (default: 4  => 04:00 UTC)
#   SESSION_REFRESH_MINUTE -> daqiqa (default: 0)
DAILY_REFRESH_HOUR = int(os.getenv("SESSION_REFRESH_HOUR", "4"))
DAILY_REFRESH_MINUTE = int(os.getenv("SESSION_REFRESH_MINUTE", "0"))

# Bot start qilinganda (deploy'dan keyin ham) 1 marta avtomatik ishga tushirish:
#   SESSION_REFRESH_ON_STARTUP     -> "1"/"0" (default: 1 = yoqilgan)
#   SESSION_REFRESH_STARTUP_DELAY  -> necha soniyadan keyin (default: 120 = 2 daqiqa)
RUN_ON_STARTUP = os.getenv("SESSION_REFRESH_ON_STARTUP", "1").strip().lower() not in ("0", "false", "no")
STARTUP_DELAY = int(os.getenv("SESSION_REFRESH_STARTUP_DELAY", "120"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def refresh_user_session(user_id: int) -> bool:
    """
    Bitta foydalanuvchi sessiyasini refresh qilish

    Returns:
        True muvaffaqiyatli, False xatolik
    """
    try:
        logger.info(f"User {user_id} sessiyasini refresh qilmoqda...")

        # FAOL akkaunt (slot) uchun client olish — cache'da ulangan bo'lsa o'shani,
        # aks holda yangi ulanish ochadi (get_dialogs access-hashlarni yangilaydi)
        slot = get_active_slot(user_id)
        client = await get_user_client_slot(user_id, slot)
        logger.info(f"User {user_id} (slot {slot}) client ulandi")

        # Dialoglarni yuklash (yangi guruhlarga access olish uchun)
        # Eslatma: pyrotgfork 2.2.24 da get_dialogs async generator qaytaradi —
        # await emas, async for bilan o'qiladi.
        try:
            dialog_count = 0
            async for _dialog in client.get_dialogs(limit=100):
                dialog_count += 1
            logger.info(f"User {user_id} uchun {dialog_count} ta dialog yuklandi")
        except Exception as e:
            logger.warning(f"User {user_id} dialoglarni yuklashda xatolik: {e}")

        # Clientni cache'dan olib tashlab disconnect qilamiz (session fayli saqlanadi).
        # Cache'dagi uzilgan client keyingi ishlatishda yangisi bilan almashtiriladi.
        await close_user_client_slot(user_id, slot)
        logger.info(f"User {user_id} sessiyasi muvaffaqiyatli refresh qilindi")

        return True

    except Exception as e:
        logger.error(f"User {user_id} sessiyasini refresh qilishda xatolik: {e}")
        return False

async def refresh_all_sessions():
    """
    Barcha foydalanuvchi sessiyalarini refresh qilish
    """
    logger.info("Barcha userbot sessiyalarini refresh qilish boshlandi...")
    
    # Barcha foydalanuvchilarni olish
    users = await get_all_users()
    logger.info(f"Jami {len(users)} ta foydalanuvchi topildi")
    
    success_count = 0
    fail_count = 0
    
    for user in users:
        user_id = user["user_id"]
        
        # Sessiya fayli borligini tekshirish
        session_file = os.path.join(SESSIONS_DIR, f"user_{user_id}.session")
        if not os.path.exists(session_file):
            logger.warning(f"User {user_id} sessiya fayli topilmadi, o'tkazilmoqda")
            continue
        
        # Sessiyani refresh qilish
        if await refresh_user_session(user_id):
            success_count += 1
        else:
            fail_count += 1
        
        # FloodWaitdan saqlanish uchun kichik kutish
        await asyncio.sleep(2)
    
    logger.info(f"Refresh tugadi: {success_count} ta muvaffaqiyat, {fail_count} ta xatolik")
    
    # Baza statistikasi
    logger.info("Baza statistikasi:")
    for user in users[:5]:  # Birinchi 5 ta user uchun
        user_id = user["user_id"]
        try:
            stats = await get_user_database_stats(user_id)
            logger.info(f"User {user_id}: {stats['group_count']} ta baza, {stats['total_members']} ta a'zo")
        except Exception as e:
            logger.warning(f"User {user_id} statistikasini olishda xatolik: {e}")

async def daily_session_refresh_task():
    """
    Har kuni 1 marta barcha userbot sessiyalarini avtomatik yangilaydigan
    fon jarayoni (kuniga 1 marta).

    Vaqt UTC bo'yicha SESSION_REFRESH_HOUR / SESSION_REFRESH_MINUTE
    environment o'zgaruvchilari orqali sozlanadi (default: 04:00 UTC).

    Bot (main.py) ishga tushganda bu task avtomatik start qilinadi:
      - deploy/bot start qilinganda 1 marta (SESSION_REFRESH_STARTUP_DELAY dan keyin),
      - keyin har kuni rejalashtirilgan vaqtda 1 marta.
    """
    logger.info(
        f"=== Daily Session Refresh Task boshlandi "
        f"(har kuni {DAILY_REFRESH_HOUR:02d}:{DAILY_REFRESH_MINUTE:02d} UTC; "
        f"startda: {'ha' if RUN_ON_STARTUP else 'yoq'}) ==="
    )
    startup_done = False
    while True:
        try:
            now = datetime.now(timezone.utc)

            if RUN_ON_STARTUP and not startup_done:
                # Deploy/bot start qilinganda 1 marta ishga tushirish
                startup_done = True
                logger.info(
                    f"Deploy/start refresh: {STARTUP_DELAY} soniyadan keyin "
                    f"1 marta ishga tushiriladi..."
                )
                await asyncio.sleep(STARTUP_DELAY)
                logger.info("=== Deploy/start sessiya yangilash boshlandi ===")
                await refresh_all_sessions()
                logger.info("=== Deploy/start sessiya yangilash tugadi ===")
                now = datetime.now(timezone.utc)
                # Bugungi jadvalga takror tushmaslik: reja vaqti juda yaqin bo'lsa ertaga surish
                next_run = now.replace(
                    hour=DAILY_REFRESH_HOUR,
                    minute=DAILY_REFRESH_MINUTE,
                    second=0,
                    microsecond=0,
                )
                if next_run <= now:
                    next_run += timedelta(days=1)
                if (next_run - now).total_seconds() < 1800:  # 30 daqiqadan kam bo'lsa
                    next_run += timedelta(days=1)
            else:
                next_run = now.replace(
                    hour=DAILY_REFRESH_HOUR,
                    minute=DAILY_REFRESH_MINUTE,
                    second=0,
                    microsecond=0,
                )
                if next_run <= now:
                    next_run += timedelta(days=1)

            wait_seconds = max(1, int((next_run - now).total_seconds()))
            logger.info(
                f"Keyingi avtomatik sessiya yangilash: {next_run.isoformat()} "
                f"({wait_seconds // 3600} soat {(wait_seconds % 3600) // 60} daqiqa keyin)"
            )
            await asyncio.sleep(wait_seconds)

            logger.info("=== Kunlik sessiya yangilash boshlandi ===")
            await refresh_all_sessions()
            logger.info("=== Kunlik sessiya yangilash tugadi ===")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Daily session refresh xatolik: {e}")
            await asyncio.sleep(3600)

async def main():
    """Asosiy funksiya"""
    logger.info("=== Userbot Session Refresh Script ===")
    logger.info(f"Sessions directory: {SESSIONS_DIR}")
    
    # Environment variables tekshirish
    if not API_ID or not API_HASH:
        logger.error("API_ID yoki API_HASH topilmadi!")
        logger.error("Iltimos, .env faylini tekshiring")
        return
    
    # Barcha sessiyalarni refresh qilish
    await refresh_all_sessions()
    
    logger.info("=== Script tugadi ===")

if __name__ == "__main__":
    # Windows uchun event loop policy
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    if "--daily" in sys.argv[1:]:
        # --daily: har kuni avtomatik rejim (Railway console'da sinash uchun)
        asyncio.run(daily_session_refresh_task())
    else:
        # Oddiy (standalone): 1 marta refresh va chiqish
        asyncio.run(main())