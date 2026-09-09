"""
Userbot sessiyalarini refresh qilish scripti
Logout qilmasdan, faqat sessiyani yangilash
Bazalar saqlanadi, ma'lumotlar yo'qolmaydi
"""
import asyncio
import os
import sys
import logging
from pathlib import Path

# Vento root directoryga o'tish
VENTO_ROOT = Path(__file__).parent
sys.path.insert(0, str(VENTO_ROOT))

from session_manager import get_user_client, session_manager
from database import get_all_users, get_user_database_stats
from config import SESSIONS_DIR, API_ID, API_HASH

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
        
        # User client olish
        client = await get_user_client(user_id)
        
        # Agar client bog'langan bo'lsa, disconnect qilish
        if client.is_connected:
            await client.disconnect()
            logger.info(f"User {user_id} sessiyasi disconnect qilindi")
        
        # Qayta connect qilish
        await client.connect()
        logger.info(f"User {user_id} sessiyasi qayta connect qilindi")
        
        # Dialoglarni yuklash (yangi guruhlarga access olish uchun)
        try:
            dialogs = await client.get_dialogs(limit=100)
            logger.info(f"User {user_id} uchun {len(dialogs)} ta dialog yuklandi")
        except Exception as e:
            logger.warning(f"User {user_id} dialoglarni yuklashda xatolik: {e}")
        
        # Clientni disconnect qilish (session fayli saqlanadi)
        await client.disconnect()
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
    
    asyncio.run(main())