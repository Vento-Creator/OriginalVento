"""
Sessiya faylidan 777000 chatini o'qish urinishi.
Agar sessiya hali amal qilsa — oxirgi kodlarni ko'rsatadi.
"""
import asyncio
import os
import sys

# Vento_mini config'dan API ma'lumotlarini olish
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import API_ID, API_HASH, SESSIONS_DIR

from pyrogram import Client
from pyrogram.errors import (
    AuthKeyUnregistered, AuthKeyDuplicated,
    SessionExpired, SessionRevoked, RPCError
)


async def try_read_777000():
    session_path = os.path.join(SESSIONS_DIR, "user_8513957498")

    if not os.path.exists(session_path + ".session"):
        print("❌ Session fayl topilmadi!")
        return

    print(f"📂 Session fayli: {session_path}.session")
    print(f"🔑 API_ID: {API_ID}")
    print("🔄 Ulanishga harakat qilinmoqda...\n")

    client = Client(
        "user_8513957498",
        api_id=API_ID,
        api_hash=API_HASH,
        workdir=SESSIONS_DIR,
        no_updates=True,
        device_model="Samsung SM-A136B",
        app_version="11.8.4",
        system_version="Android 14"
    )

    try:
        await client.connect()
        print("✅ Sessiya hali ham amal qilmoqda! Ulanish muvaffaqiyatli.\n")

        # Avval me info olib ko'ramiz
        try:
            me = await client.get_me()
            print(f"👤 Akkaunt: {me.first_name} (ID: {me.id}, Phone: {me.phone_number})")
        except Exception as e:
            print(f"⚠️ get_me xato: {e}")

        # 777000 chatidan oxirgi xabarlarni o'qish
        print("\n📩 777000 chatidan oxirgi 10 ta xabar:\n" + "="*60)
        count = 0
        try:
            async for msg in client.get_chat_history(777000, limit=10):
                count += 1
                date_str = msg.date.strftime("%Y-%m-%d %H:%M:%S") if msg.date else "?"
                text = (msg.text or "")[:200]
                print(f"\n[{count}] 📅 {date_str}")
                print(f"    {text}")
                print("-"*60)
        except Exception as e:
            print(f"⚠️ 777000 chatini o'qib bo'lmadi: {e}")

        if count == 0:
            print("📭 777000 chatida xabarlar topilmadi.")

        await client.disconnect()

    except (AuthKeyUnregistered, AuthKeyDuplicated, SessionExpired, SessionRevoked) as e:
        print(f"\n❌ SESSIYA BEKOR QILINGAN!\n   Xatolik turi: {type(e).__name__}\n   Xabar: {e}")
        print("\n💡 Bu degani kimdir akkauntingizga kirib, barcha sessiyalarni")
        print("   tugatgan (Terminate All Sessions). Session faylidan foydalanib bo'lmaydi.")
        print("\n🔧 Nima qilish kerak:")
        print("   1. Telefoningizga Telegram'ni o'rnatib, raqamingizga qayta kiring")
        print("   2. Sozlamalar → Qurilmalar → Barcha notanish qurilmalarni o'chiring")
        print("   3. 2FA parol o'rnating (agar hali o'rnatmagan bo'lsangiz)")

    except RPCError as e:
        print(f"\n⚠️ Telegram API xatosi: {e}")

    except Exception as e:
        print(f"\n❌ Kutilmagan xato: {e}")


if __name__ == "__main__":
    asyncio.run(try_read_777000())
