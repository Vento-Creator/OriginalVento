from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from config import user_states, is_admin, is_owner, SESSIONS_DIR
from session_manager import get_user_client
from database import search_groups, get_group_member_count
import os
import logging

logger = logging.getLogger(__name__)

GROUP_SEARCH_STATE = "group_search_state"


@Client.on_callback_query(filters.regex("^menu_group_search$"))
async def menu_group_search_callback(client: Client, cq: CallbackQuery):
    """Guruh qidirish menyusi"""
    uid = cq.from_user.id
    
    await cq.message.edit_text(
        "🔍 **Global Guruh Qidirish**\n\n"
        "Telegram'dagi **public guruhlar**ni kalit so'z bo'yicha qidirish.\n\n"
        "Guruh nomini yuboring:\n"
        "Masalan: `Mafia`, `Crypto`, `IT`, `O'zbekiston`\n\n"
        "⚠️ Eslatma: Bu Telegram o'zidagi global qidiruv. Faqat public guruhlar topiladi.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="menu_main")]
        ])
    )
    
    user_states[uid] = GROUP_SEARCH_STATE
    await cq.answer()

@Client.on_message(filters.private & filters.text & ~filters.command(["start"]), group=-9)
async def group_search_message_handler(client: Client, message: Message):
    """Guruh qidirish - Telegram global search orqali"""
    from pyrogram import ContinuePropagation
    
    uid = message.from_user.id
    state = user_states.get(uid)
    
    logger.debug(f"[GROUP_SEARCH] Handler called for user {uid}, state: {state}")
    
    if state != GROUP_SEARCH_STATE:
        logger.debug(f"[GROUP_SEARCH] User {uid} not in group search state, skipping")
        raise ContinuePropagation
    
    query = message.text.strip()
    logger.info(f"[GROUP_SEARCH] Searching globally for: {query}")
    
    if len(query) < 2:
        await message.reply_text(
            "❌ Kamida 2 ta belgi kiriting.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Bekor qilish", callback_data="menu_main")]
            ])
        )
        return
    
    try:
        msg = await message.reply_text("🔍 Telegram'da qidirilmoqda...\n\n⏳ Biroz kuting, bu 10-30 soniya vaqt olishi mumkin.")
        
        session_file = os.path.join(SESSIONS_DIR, f"user_{uid}.session")
        if not os.path.exists(session_file):
            await msg.edit_text(
                "❌ Qidirish uchun avval akkauntingizni ulang!\n\n"
                "📱 Akkauntni ulash uchun /start bosing.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Bosh menyu", callback_data="menu_main")]
                ])
            )
            user_states.pop(uid, None)
            return
        
        user_client = await get_user_client(uid)
        
        results = []
        
        try:
            search_method_found = False
            
            if hasattr(user_client, 'search_public_chats'):
                logger.info("[GROUP_SEARCH] Trying search_public_chats")
                try:
                    async for item in user_client.search_public_chats(query):
                        if hasattr(item, 'id') and hasattr(item, 'title'):
                            results.append({
                                "group_id": item.id,
                                "group_title": item.title,
                                "username": getattr(item, 'username', None),
                                "members_count": getattr(item, 'members_count', 0) or 0
                            })
                            if len(results) >= 20:
                                break
                    search_method_found = True
                except Exception as e:
                    logger.warning(f"[GROUP_SEARCH] search_public_chats failed: {e}")
            
            if not search_method_found and hasattr(user_client, 'search_global'):
                logger.info("[GROUP_SEARCH] Trying search_global")
                try:
                    async for item in user_client.search_global(query):
                        if hasattr(item, 'id') and hasattr(item, 'title'):
                            results.append({
                                "group_id": item.id,
                                "group_title": item.title,
                                "username": getattr(item, 'username', None),
                                "members_count": getattr(item, 'members_count', 0) or 0
                            })
                            if len(results) >= 20:
                                break
                    search_method_found = True
                except Exception as e:
                    logger.warning(f"[GROUP_SEARCH] search_global failed: {e}")
            
            if not search_method_found or len(results) == 0:
                logger.info("[GROUP_SEARCH] Using local database search")
                db_results = await search_groups(query, limit=20)
                for group in db_results:
                    results.append({
                        "group_id": group["group_id"],
                        "group_title": group["group_title"],
                        "username": None,
                        "members_count": await get_group_member_count(group["group_id"])
                    })
                
        except Exception as search_error:
            logger.error(f"[GROUP_SEARCH] Search error: {search_error}")
            raise
        
        logger.info(f"[GROUP_SEARCH] Found {len(results)} global results for '{query}'")
        
        user_states.pop(uid, None)
        
        if not results:
            await msg.edit_text(
                f"❌ **'{query}'** bo'yicha hech qanday guruh topilmadi.\n\n"
                "Boshqa kalit so'z bilan qaytadan urinib ko'ring:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Bosh menyu", callback_data="menu_main")]
                ])
            )
            return
        
        text_parts = [f"🔍 **'{query}'** - {len(results)} ta guruh topildi:\n"]
        
        for idx, group in enumerate(results[:10], 1):  # Show max 10
            group_title = group["group_title"]
            group_id = group["group_id"]
            members_count = group.get("members_count", 0)
            username = group.get("username")
            
            if username:
                link = f"https://t.me/{username}"
            elif str(group_id).startswith('-100'):
                link = f"https://t.me/c/{str(group_id).replace('-100', '')}"
            else:
                link = f"https://t.me/{group_title.replace(' ', '_')}"
            
            text_parts.append(
                f"\n{idx}. **{group_title}**\n"
                f"   👥 {members_count} a'zo\n"
                f"   🔗 {link}\n"
                f"   🆔 `{group_id}`"
            )
        
        text = "\n".join(text_parts)
        logger.info(f"[GROUP_SEARCH] Showing {len(results)} results to user {uid}")
        
        await msg.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Bosh menyu", callback_data="menu_main")]
            ])
        )
        
    except Exception as e:
        logger.error(f"[GROUP_SEARCH] Error: {e}")
        user_states.pop(uid, None)
        await message.reply_text(
            f"❌ Qidirishda xatolik yuz berdi: {e}\n\n"
            "Iltimos, qaytadan urinib ko'ring.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Bosh menyu", callback_data="menu_main")]
            ])
        )


@Client.on_callback_query(filters.regex("^admin_all_groups$"))
async def admin_all_groups_callback(client: Client, cq: CallbackQuery):
    """Admin uchun barcha guruhlar"""
    uid = cq.from_user.id
    
    if not is_owner(uid):
        await cq.answer("⛔️ Sizda huquq yo'q!", show_alert=True)
        return
    
    from database import get_all_scraped_groups_admin
    groups = await get_all_scraped_groups_admin()
    
    if not groups:
        await cq.message.edit_text(
            "📊 **Barcha guruhlar**\n\n"
            "Hali guruhlar yo'q.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")]
            ])
        )
        await cq.answer()
        return
    
    keyboard = []
    for group in groups[:20]:  # Show first 20
        group_title = group["group_title"]
        group_id = group["group_id"]
        owner_id = group["owner_id"]
        
        keyboard.append([
            InlineKeyboardButton(
                f"📊 {group_title[:30]}",
                callback_data=f"admin_view_group_{group_id}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")])
    
    await cq.message.edit_text(
        f"📊 **Barcha guruhlar**\n\n"
        f"Jami: {len(groups)} ta guruh\n\n"
        f"Guruhni tanlang:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await cq.answer()

@Client.on_callback_query(filters.regex(r"^admin_view_group_(.+)$"))
async def admin_view_group_callback(client: Client, cq: CallbackQuery):
    """Admin uchun guruh ma'lumotlarini ko'rish"""
    uid = cq.from_user.id
    
    if not is_owner(uid):
        await cq.answer("⛔️ Sizda huquq yo'q!", show_alert=True)
        return
    
    match = cq.data.split("_", 3)
    group_id = match[3]
    
    from database import get_group_info, get_members_by_group_paginated
    
    group_info = await get_group_info(group_id)
    if not group_info:
        await cq.answer("❌ Guruh topilmadi!", show_alert=True)
        return
    
    member_count = await get_group_member_count(group_id)
    group_title = group_info["group_title"]
    owner_id = group_info["owner_id"]
    
    members = await get_members_by_group_paginated(group_id, offset=0, limit=10)
    
    text_parts = [
        f"📊 **Guruh ma'lumotlari**\n\n",
        f"**Nomi:** {group_title}\n",
        f"**ID:** `{group_id}`\n",
        f"**A'zolar soni:** {member_count}\n",
        f"**Owner ID:** {owner_id}\n\n",
        f"**Oxirgi 10 a'zo:**\n"
    ]
    
    for member in members:
        username = member.get("username", "")
        first_name = member.get("first_name", "Noma'lum")
        display = f"@{username}" if username else first_name
        text_parts.append(f"• {display}\n")
    
    if member_count > 10:
        text_parts.append(f"\n... va yana {member_count - 10} ta a'zo")
    
    text = "".join(text_parts)
    
    await cq.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Barcha guruhlar", callback_data="admin_all_groups")]
        ])
    )
    await cq.answer()