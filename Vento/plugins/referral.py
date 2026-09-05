"""
Referral (taklif) tizimi — foydalanuvchilar botga do'stlarini taklif qiladi
va bepul obuna kunlarini yutib oladi.

Bonuslar (database.py da konstanta):
    REFERRAL_BONUS_REGISTRATION_DAYS = 1  — taklif qilingan user /start qilganda
    REFERRAL_BONUS_PAYMENT_DAYS      = 3  — taklif qilingan user obuna sotib olganda
"""
from urllib.parse import quote

from pyrogram import Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

import logging

logger = logging.getLogger(__name__)

SHARE_TEXT = "🚀 Vento Bot — Telegram uchun eng qulay ish vositasi. Sinab ko'r:"


async def handle_referral_menu(client: Client, message: Message):
    """'👥 Takliflar' tugmasi bosilganda referral ekranni ko'rsatish."""
    uid = message.from_user.id

    from database import (
        get_referral_count,
        REFERRAL_BONUS_REGISTRATION_DAYS,
        REFERRAL_BONUS_PAYMENT_DAYS,
    )

    count = await get_referral_count(uid)

    bot_username = None
    try:
        me = client.me or await client.get_me()
        bot_username = me.username if me else None
    except Exception as e:
        logger.warning(f"Failed to resolve bot username for referral menu: {e}")

    if bot_username:
        link = f"https://t.me/{bot_username}?start=ref_{uid}"
        share_url = (
            f"https://t.me/share/url?url={quote(link, safe='')}"
            f"&text={quote(SHARE_TEXT)}"
        )
        link_line = f"🔗 **Sizning havolangiz:**\n`{link}`\n\n"
        buttons = [
            [InlineKeyboardButton("📤 Do'stlarga ulashish", url=share_url)],
            [InlineKeyboardButton("🔙 Bosh menyu", callback_data="menu_main")],
        ]
    else:
        link_line = "⚠️ Havola yaratish uchun bot username aniqlanmadi.\n\n"
        buttons = [[InlineKeyboardButton("🔙 Bosh menyu", callback_data="menu_main")]]

    text = (
        "👥 **Taklif tizimi**\n\n"
        "Do'stlaringizni botga taklif qiling va **bepul obuna kunlari** yutib oling!\n\n"
        f"{link_line}"
        f"📊 Taklif qilinganlar: **{count} ta**\n\n"
        "🎁 **Bonuslar:**\n"
        f"• Har bir yangi taklif uchun: **+{REFERRAL_BONUS_REGISTRATION_DAYS} kun**\n"
        f"• Taklif qilgan do'stingiz obuna sotib olsa: **+{REFERRAL_BONUS_PAYMENT_DAYS} kun**\n\n"
        "💡 Havolani do'stlaringizga yuboring — ular botga kirganda siz avtomatik taqdirlanasiz!"
    )

    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
