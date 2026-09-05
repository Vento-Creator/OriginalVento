from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardRemove
from pyrogram.errors import FloodWait
from config import SUPER_ADMIN_ID, SECOND_ADMIN_ID, is_admin, is_owner, OWNER_ID, can_broadcast, can_ban, can_clear_db, can_manage_users, can_add_admin
import config
from locales import get_text
from database import get_known_user
from plugins.utag import TAG_MESSAGES
from database import (
    add_or_update_user, remove_user, get_all_users,
    add_violation, remove_ban,
    add_free_user, remove_free_user, get_all_free_users,
    get_all_scraped_groups_admin, get_group_member_count,
    get_group_info, delete_scraped_group, get_user_info_from_scraped,
    clean_users_without_username, get_admin_stats,
    get_all_registered_user_ids, get_all_admins, get_admin_info,
    add_admin, remove_admin, update_admin_permission, log_admin_action,
    get_all_complaints, get_complaint_by_id, mark_complaint_read, reply_to_complaint, get_complaint_count, get_pending_complaints, get_complaints_by_status
)
import time
import asyncio
import logging
from datetime import datetime
from rate_limiter import check_rate_limit
from spambot_unlock import send_and_check_unlock, check_if_locked
from queue_manager import get_all_active_tasks, terminate_user_task
from config import ADMIN_REPORT_CHAT_ID

logger = logging.getLogger(__name__)


def admin_filter(_, __, message: Message):
    return message.from_user and is_admin(message.from_user.id)

is_admin_filter = filters.create(admin_filter)

def admin_callback_filter(_, __, query: CallbackQuery):
    return query.from_user and is_admin(query.from_user.id)

is_admin_callback_filter = filters.create(admin_callback_filter)


@Client.on_message(filters.command("admin") & filters.private & is_admin_filter)
async def admin_command_handler(client: Client, message: Message):
    user = await get_known_user(message.from_user.id)
    lang = user.get("language", "uz") if user else "uz"
    
    stats = await get_admin_stats()

    text = (
        f"⚙️ **{get_text('admin_panel', lang)}**\n\n"
        f"{get_text('total_users', lang)}: **{stats['total_known']}** ta\n"
        f"{get_text('active_subs', lang)}: **{stats['active_subs']}** ta\n"
        f"{get_text('free_users', lang)}: **{stats['free']}** ta\n"
        f"{get_text('banned_users', lang)}: **{stats['banned']}** ta\n"
        f"{get_text('databases', lang)}: **{stats['databases']}** ta\n\n"
        f"{get_text('select_section', lang)}"
    )

    keyboard = [
        [InlineKeyboardButton(get_text("manage_users", lang), callback_data="adm_users_0")],
        [InlineKeyboardButton(get_text("search_user", lang), callback_data="adm_search")],
        [InlineKeyboardButton(get_text("recent_actions", lang), callback_data="adm_acts_list_0")],
        [InlineKeyboardButton(get_text("statistics", lang), callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Referral", callback_data="admin_referrals")],
        [InlineKeyboardButton("📢 Majburiy obuna", callback_data="admin_force_join")],
        [InlineKeyboardButton(get_text("subscribed_users", lang), callback_data="admin_sub_list")],
        [InlineKeyboardButton(get_text("free_users_list", lang), callback_data="admin_free_list")],
        [InlineKeyboardButton(get_text("banned_list", lang), callback_data="adm_bans")],
        [InlineKeyboardButton(get_text("all_databases", lang), callback_data="admin_all_bazalar")],
        [InlineKeyboardButton(get_text("new_database", lang), callback_data="baza_new_manual")],
        [InlineKeyboardButton(get_text("updates", lang), callback_data="admin_updates")],
        [InlineKeyboardButton(get_text("tag_messages", lang), callback_data="admin_tag_messages")],
        [InlineKeyboardButton("📩 Shikoyatlar", callback_data="admin_complaints")],
        [InlineKeyboardButton("⚡️ Active User Tasks", callback_data="admin_active_tasks_0")],
    ]
    
    if is_owner(message.from_user.id):
        keyboard.append([InlineKeyboardButton("👁️ Chat monitoring", callback_data="owner_chat_monitor")])
        keyboard.append([InlineKeyboardButton(get_text("manage_admins", lang), callback_data="admin_manage_admins")])
    
    keyboard.append([InlineKeyboardButton(get_text("back", lang), callback_data="menu_main")])
    
    keyboard = InlineKeyboardMarkup(keyboard)

    await message.reply_text(text, reply_markup=keyboard)


@Client.on_callback_query(filters.regex("^menu_admin$") & is_admin_callback_filter)
async def admin_panel_callback(client: Client, cq: CallbackQuery):
    try:
        del_msg = await cq.message.reply_text("⏳", reply_markup=ReplyKeyboardRemove())
        await del_msg.delete()
    except:
        pass
    
    user = await get_known_user(cq.from_user.id)
    lang = user.get("language", "uz") if user else "uz"
    
    stats = await get_admin_stats()

    text = (
        f"⚙️ **{get_text('admin_panel', lang)}**\n\n"
        f"{get_text('total_users', lang)}: **{stats['total_known']}** ta\n"
        f"{get_text('active_subs', lang)}: **{stats['active_subs']}** ta\n"
        f"{get_text('free_users', lang)}: **{stats['free']}** ta\n"
        f"{get_text('banned_users', lang)}: **{stats['banned']}** ta\n"
        f"{get_text('databases', lang)}: **{stats['databases']}** ta\n\n"
        f"{get_text('select_section', lang)}"
    )

    keyboard = [
        [InlineKeyboardButton(get_text("manage_users", lang), callback_data="adm_users_0")],
        [InlineKeyboardButton(get_text("search_user", lang), callback_data="adm_search")],
        [InlineKeyboardButton(get_text("recent_actions", lang), callback_data="adm_acts_list_0")],
        [InlineKeyboardButton(get_text("statistics", lang), callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Referral", callback_data="admin_referrals")],
        [InlineKeyboardButton("📢 Majburiy obuna", callback_data="admin_force_join")],
        [InlineKeyboardButton(get_text("subscribed_users", lang), callback_data="admin_sub_list")],
        [InlineKeyboardButton(get_text("free_users_list", lang), callback_data="admin_free_list")],
        [InlineKeyboardButton(get_text("banned_list", lang), callback_data="adm_bans")],
        [InlineKeyboardButton(get_text("all_databases", lang), callback_data="admin_all_bazalar")],
        [InlineKeyboardButton(get_text("new_database", lang), callback_data="baza_new_manual")],
        [InlineKeyboardButton(get_text("updates", lang), callback_data="admin_updates")],
        [InlineKeyboardButton(get_text("tag_messages", lang), callback_data="admin_tag_messages")],
        [InlineKeyboardButton("📩 Shikoyatlar", callback_data="admin_complaints")],
        [InlineKeyboardButton("⚡️ Active User Tasks", callback_data="admin_active_tasks_0")],
    ]
    
    if is_owner(cq.from_user.id):
        keyboard.append([InlineKeyboardButton("👁️ Chat monitoring", callback_data="owner_chat_monitor")])
        keyboard.append([InlineKeyboardButton(get_text("manage_admins", lang), callback_data="admin_manage_admins")])
    
    keyboard.append([InlineKeyboardButton(get_text("back", lang), callback_data="menu_main")])
    
    keyboard = InlineKeyboardMarkup(keyboard)

    await cq.message.edit_text(text, reply_markup=keyboard)
    await cq.answer()


@Client.on_callback_query(filters.regex("^admin_sub_list$") & is_admin_callback_filter)
async def admin_sub_list_callback(client: Client, cq: CallbackQuery):
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Sizda bu amallni bajarish uchun Foydalanuvchilarni boshqarish yo'q!", show_alert=True)
        return
    users = await get_all_users()
    
    if not users:
        await cq.message.edit_text(
            "📋 **Obunali foydalanuvchilar**\n\n📭 Hozircha obunali foydalanuvchi yo'q.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")
            ]])
        )
        await cq.answer()
        return
    
    lines = ["📋 **Obunali foydalanuvchilar ro'yxati:**\n"]
    for i, user in enumerate(users, 1):
        user_id = user["user_id"]
        expiry = user["expiry_date"]
        warned = user["warned"]
        username = user.get("username")
        first_name = user.get("first_name")
        
        if not username and not first_name:
            scraped_info = await get_user_info_from_scraped(user_id)
            if scraped_info:
                username = scraped_info.get("username")
                first_name = scraped_info.get("first_name")
        
        now = int(time.time())
        remaining_days = (expiry - now) // 86400 if expiry > now else 0
        
        if expiry <= now:
            status = "❌ Tugagan"
        elif warned:
            status = "⚠️ Ogohlantirilgan"
        else:
            status = "✅ Faol"
        
        expiry_str = datetime.fromtimestamp(expiry).strftime("%d.%m.%Y %H:%M")
        
        if username:
            user_display = f"@{username}"
        elif first_name:
            user_display = first_name
        else:
            user_display = f"ID: {user_id}"
        
        lines.append(
            f"{i}. {user_display}\n"
            f"   Muddati: {expiry_str}\n"
            f"   Qolgan: {remaining_days} kun\n"
            f"   Holati: {status}\n"
        )
    
    lines.append(f"\n**Jami: {len(users)} ta**")
    
    buttons = []
    for user in users[:15]:
        user_id = user["user_id"]
        username = user.get("username")
        label = f"@{username}" if username else f"ID: {user_id}"
        buttons.append([InlineKeyboardButton(f"👤 {label}", callback_data=f"adm_user_{user_id}")])
    
    buttons.append([InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")])

    await cq.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    await cq.answer()




@Client.on_callback_query(filters.regex("^admin_free_list$") & is_admin_callback_filter)
async def admin_free_list_callback(client: Client, cq: CallbackQuery):
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Sizda bu amallni bajarish uchun Foydalanuvchilarni boshqarish yo'q!", show_alert=True)
        return
    free_users = await get_all_free_users()
    
    if not free_users:
        await cq.message.edit_text(
            "🆓 **Bepul foydalanuvchilar**\n\n📭 Hozircha bepul foydalanuvchi yo'q.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")
            ]])
        )
        await cq.answer()
        return
    
    lines = ["🆓 **Bepul foydalanuvchilar ro'yxati:**"]
    for i, user in enumerate(free_users, 1):
        user_id = user["user_id"]
        username = user.get("username")
        
        if username:
            user_display = f"@{username}"
        else:
            user_display = f"ID: {user_id}"
        
        lines.append(f"{i}. {user_display}")
    
    lines.append(f"**Jami: {len(free_users)} ta**")
    
    buttons = []
    for user in free_users[:15]:
        user_id = user["user_id"]
        username = user.get("username")
        label = f"@{username}" if username else f"ID: {user_id}"
        buttons.append([InlineKeyboardButton(f"👤 {label}", callback_data=f"adm_user_{user_id}")])
    
    buttons.append([InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")])

    await cq.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^admin_all_bazalar$") & is_admin_callback_filter)
async def admin_all_bazalar_callback(client: Client, cq: CallbackQuery):
    groups = await get_all_scraped_groups_admin()

    if not groups:
        await cq.answer("Hech qanday baza yo'q!", show_alert=True)
        return

    by_owner: dict = {}
    for g in groups:
        oid = g["owner_id"]
        if oid not in by_owner:
            by_owner[oid] = []
        by_owner[oid].append(g)

    lines = ["🌐 **Barcha foydalanuvchi bazalari**\n"]
    buttons = []

    for owner_id, owner_groups in by_owner.items():
        owner_label = f"👤 Admin" if is_admin(owner_id) else f"👤 User `{owner_id}`"
        lines.append(f"\n{owner_label}:")
        for g in owner_groups:
            cnt = await get_group_member_count(g["group_id"])
            date_str = datetime.fromtimestamp(g["date_scraped"]).strftime("%d.%m.%Y %H:%M")
            lines.append(
                f"  📁 **{g['group_title']}**\n"
                f"  👥 {cnt} ta · 📅 {date_str} · 🆔 `{g['group_id']}`\n"
            )
            buttons.append([InlineKeyboardButton(
                f"📁 {g['group_title']} ({cnt} ta)",
                callback_data=f"admin_view_baza_{g['group_id']}"
            )])
        if not is_admin(owner_id):
            buttons.append([InlineKeyboardButton(
                f"👤 {owner_label} profili", callback_data=f"adm_user_{owner_id}"
            )])

    buttons.append([InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")])

    await cq.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    await cq.answer()

@Client.on_callback_query(filters.regex(r"^admin_view_baza_(.+)$") & is_admin_callback_filter)
async def admin_view_baza_callback(client: Client, cq: CallbackQuery):
    gid = cq.matches[0].group(1)
    group = await get_group_info(gid)
    if not group:
        await cq.answer("Baza topilmadi!", show_alert=True)
        return

    cnt = await get_group_member_count(gid)
    date_str = datetime.fromtimestamp(group["date_scraped"]).strftime("%d.%m.%Y %H:%M")
    owner_id = group.get("owner_id", 0)
    owner_str = "Admin" if is_admin(owner_id) else f"`{owner_id}`"

    buttons = [
        [InlineKeyboardButton("📋 Ro'yxatni ko'rish", callback_data=f"baza_list_{gid}_0")],
        [InlineKeyboardButton("📨 Xabar yuborish", callback_data=f"baza_send_{gid}")],
        [InlineKeyboardButton("🗑 Bazani o'chirish", callback_data=f"admin_del_baza_confirm_{gid}")],
    ]
    if owner_id and not is_admin(owner_id):
        buttons.append([InlineKeyboardButton("👤 Egasi profili", callback_data=f"adm_user_{owner_id}")])
    buttons.append([InlineKeyboardButton("🔙 Barcha bazalar", callback_data="admin_all_bazalar")])

    await cq.message.edit_text(
        f"📁 **{group['group_title']}**\n\n"
        f"🆔 Baza ID: `{gid}`\n"
        f"👤 Egasi: {owner_str}\n"
        f"👥 A'zolar soni: **{cnt} ta**\n"
        f"📅 Oxirgi yangilanish: {date_str}\n\n"
        "Quyidagi amallardan birini tanlang:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    await cq.answer()

@Client.on_callback_query(filters.regex(r"^admin_del_baza_confirm_(.+)$") & is_admin_callback_filter)
async def admin_del_baza_confirm_callback(client: Client, cq: CallbackQuery):
    if not await can_clear_db(cq.from_user.id):
        await cq.answer("❌ Sizda bu amallni bajarish uchun Bazani tozalash yo'q!", show_alert=True)
        return
    gid = cq.matches[0].group(1)
    group = await get_group_info(gid)
    if not group:
        await cq.answer("Baza topilmadi!", show_alert=True)
        return

    await cq.message.edit_text(
        f"⚠️ **{group['group_title']}** bazasini o'chirishni tasdiqlaysizmi?\n"
        "(Bu amal qaytarib bo'lmaydi!)",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Ha, o'chirish", callback_data=f"admin_del_baza_do_{gid}"),
                InlineKeyboardButton("❌ Yo'q", callback_data=f"admin_view_baza_{gid}"),
            ]
        ])
    )
    await cq.answer()

@Client.on_callback_query(filters.regex(r"^admin_del_baza_do_(.+)$") & is_admin_callback_filter)
async def admin_del_baza_do_callback(client: Client, cq: CallbackQuery):
    if not await can_clear_db(cq.from_user.id):
        await cq.answer("❌ Sizda bu amallni bajarish uchun Bazani tozalash yo'q!", show_alert=True)
        return
    gid = cq.matches[0].group(1)
    await delete_scraped_group(gid)
    await cq.message.edit_text(
        "🗑 Baza o'chirildi.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🌐 Barcha bazalar", callback_data="admin_all_bazalar")
        ]])
    )
    await cq.answer("O'chirildi!", show_alert=True)


@Client.on_message(filters.command("add_member") & is_admin_filter)
async def add_member_handler(client: Client, message: Message):
    user = await get_known_user(message.from_user.id)
    lang = user.get("language", "uz") if user else "uz"
    
    allowed, remaining = check_rate_limit(message.from_user.id, "default")
    if not allowed:
        await message.reply_text(f"⏳ So'rov limitga yetdingiz! Iltimos, biroz kutib turing.")
        return
    
    if not await can_manage_users(message.from_user.id):
        await message.reply_text(get_text("no_manage_users_permission", lang))
        return
    
    try:
        args = message.text.split()
        if len(args) != 3:
            await message.reply_text("Format: `/add_member [user_id] [kun_soni]`")
            return
        target_id = int(args[1])
        days = int(args[2])
        if days <= 0:
            await message.reply_text("Kun soni 0 dan katta bo'lishi kerak.")
            return

        username = None
        first_name = None
        try:
            user_info = await client.get_users(target_id)
            username = user_info.username
            first_name = user_info.first_name
        except:
            pass

        from database import grant_subscription
        from datetime import datetime
        from zoneinfo import ZoneInfo
        new_expiry = await grant_subscription(target_id, days)
        if username or first_name:
            from database import get_db_connection
            async with get_db_connection() as db:
                await db.execute(
                    "UPDATE users SET username = ?, first_name = ? WHERE user_id = ?",
                    (username, first_name, target_id),
                )
                await db.commit()
        stamp = datetime.fromtimestamp(new_expiry, ZoneInfo("Asia/Tashkent")).strftime("%d.%m.%Y %H:%M")
        await message.reply_text(
            f"✅ `{target_id}` ga **{days} kun** qo'shildi.\n"
            f"Tugash vaqti: `{stamp}`"
        )
        
        await log_admin_action(message.from_user.id, "add_subscription", target_id, f"Days: {days}")
        
        try:
            await client.send_message(target_id, f"🎉 Sizga admin tomonidan **{days} kunlik** obuna taqdim etildi!\n/start ni bosing.")
        except:
            pass
    except ValueError:
        await message.reply_text("ID va kun soni faqat raqam bo'lishi kerak!")
    except Exception as e:
        await message.reply_text(f"Xatolik: {e}")


@Client.on_message(filters.command("del_member") & is_admin_filter)
async def del_member_handler(client: Client, message: Message):
    user = await get_known_user(message.from_user.id)
    lang = user.get("language", "uz") if user else "uz"
    
    allowed, remaining = check_rate_limit(message.from_user.id, "default")
    if not allowed:
        await message.reply_text(f"⏳ So'rov limitga yetdingiz! Iltimos, biroz kutib turing.")
        return
    
    if not await can_manage_users(message.from_user.id):
        await message.reply_text(get_text("no_manage_users_permission", lang))
        return
    
    try:
        args = message.text.split()
        if len(args) != 2:
            await message.reply_text("Format: `/del_member [user_id]`")
            return
        target_id = int(args[1])
        await remove_user(target_id)
        await message.reply_text(f"✅ `{target_id}` ning obunasi o'chirildi.")
        
        await log_admin_action(message.from_user.id, "remove_subscription", target_id)
        
        try:
            await client.send_message(target_id, "❌ Obunangiz admin tomonidan o'chirildi.")
        except:
            pass
    except ValueError:
        await message.reply_text("ID faqat raqam bo'lishi kerak!")
    except Exception as e:
        await message.reply_text(f"Xatolik: {e}")


@Client.on_message(filters.command("free") & is_admin_filter)
async def free_handler(client: Client, message: Message):
    user = await get_known_user(message.from_user.id)
    lang = user.get("language", "uz") if user else "uz"
    
    allowed, remaining = check_rate_limit(message.from_user.id, "default")
    if not allowed:
        await message.reply_text(f"⏳ So'rov limitga yetdingiz! Iltimos, biroz kutib turing.")
        return
    
    if not await can_manage_users(message.from_user.id):
        await message.reply_text(get_text("no_manage_users_permission", lang))
        return
    
    try:
        args = message.text.split()
        if len(args) != 2:
            await message.reply_text(
                "Format: `/free [user_id]`\n\n"
                "Bu foydalanuvchi obunasiz, to'lovsiz botdan foydalanishi mumkin bo'ladi.\n"
                "Unga faqat login qilish qoladi."
            )
            return
        target_id = int(args[1])
        await add_free_user(target_id)
        await message.reply_text(
            f"✅ `{target_id}` bepul foydalanuvchilar ro'yxatiga qo'shildi.\n"
            "Endi bu foydalanuvchi obunasiz botdan foydalana oladi."
        )
        
        await log_admin_action(message.from_user.id, "add_free_user", target_id)
        
        try:
            await client.send_message(
                target_id,
                "🎉 **Tabriklaymiz!**\n\n"
                "Siz admin tomonidan bepul (VIP) foydalanuvchi sifatida qo'shildingiz.\n"
                "Endi botdan to'liq foydalanishingiz mumkin! /start"
            )
        except:
            pass
    except ValueError:
        await message.reply_text("ID faqat raqam bo'lishi kerak!")
    except Exception as e:
        await message.reply_text(f"Xatolik: {e}")


@Client.on_message(filters.command("unfree") & is_admin_filter)
async def unfree_handler(client: Client, message: Message):
    user = await get_known_user(message.from_user.id)
    lang = user.get("language", "uz") if user else "uz"
    
    allowed, remaining = check_rate_limit(message.from_user.id, "default")
    if not allowed:
        await message.reply_text(f"⏳ So'rov limitga yetdingiz! Iltimos, biroz kutib turing.")
        return
    
    if not await can_manage_users(message.from_user.id):
        await message.reply_text(get_text("no_manage_users_permission", lang))
        return
    
    try:
        args = message.text.split()
        if len(args) != 2:
            await message.reply_text("Format: `/unfree [user_id]`")
            return
        target_id = int(args[1])
        await remove_free_user(target_id)
        await message.reply_text(f"✅ `{target_id}` bepul ro'yxatdan chiqarildi.")
        
        await log_admin_action(message.from_user.id, "remove_free_user", target_id)
        
        try:
            await client.send_message(
                target_id,
                "ℹ️ Sizning bepul kirish huquqingiz admin tomonidan o'chirildi.\n"
                "Davom etish uchun obuna oling."
            )
        except:
            pass
    except ValueError:
        await message.reply_text("ID faqat raqam bo'lishi kerak!")
    except Exception as e:
        await message.reply_text(f"Xatolik: {e}")


@Client.on_message(filters.command("freelist") & is_admin_filter)
async def freelist_handler(client: Client, message: Message):
    user = await get_known_user(message.from_user.id)
    lang = user.get("language", "uz") if user else "uz"
    
    allowed, remaining = check_rate_limit(message.from_user.id, "default")
    if not allowed:
        await message.reply_text(f"⏳ So'rov limitga yetdingiz! Iltimos, biroz kutib turing.")
        return
    
    if not await can_manage_users(message.from_user.id):
        await message.reply_text(get_text("no_manage_users_permission", lang))
        return
    
    try:
        free_users = await get_all_free_users()
        if not free_users:
            await message.reply_text("🆓 Bepul foydalanuvchilar yo'q.")
            return
        lines = ["🆓 **Bepul foydalanuvchilar ro'yxati:**\n"]
        for i, user in enumerate(free_users, 1):
            user_id = user["user_id"]
            username = user.get("username")
            
            if username:
                user_display = f"@{username}"
            else:
                user_display = f"ID: {user_id}"
            
            lines.append(f"{i}. {user_display}")
        lines.append(f"\n**Jami: {len(free_users)} ta**")
        await message.reply_text("\n".join(lines))
    except Exception as e:
        await message.reply_text(f"Xatolik: {e}")


@Client.on_message(filters.command("ban") & is_admin_filter)
async def ban_handler(client: Client, message: Message):
    user = await get_known_user(message.from_user.id)
    lang = user.get("language", "uz") if user else "uz"
    
    allowed, remaining = check_rate_limit(message.from_user.id, "ban")
    if not allowed:
        await message.reply_text(f"⏳ Ban limitga yetdingiz! Iltimos, biroz kutib turing.")
        return
    
    if not await can_ban(message.from_user.id):
        await message.reply_text(get_text("no_ban_permission", lang))
        return
    
    try:
        args = message.text.split()
        if len(args) != 2:
            await message.reply_text("Format: `/ban [user_id]`")
            return
        target_id = int(args[1])
        new_count = await add_violation(target_id)
        if new_count == 1:
            await message.reply_text(f"✅ `{target_id}` birinchi marta bloklandi.")
            try:
                await client.send_message(target_id, "⚠️ Siz bot qoidalarini buzganingiz uchun ogohlantirildi!")
            except:
                pass
        else:
            await message.reply_text(f"✅ `{target_id}` **{new_count}** marta bloklandi.")
            try:
                keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⚖️ Qonunchilik", callback_data="show_laws")]])
                await client.send_message(
                    target_id,
                    "🚨 **DIQQAT! QATTIQ OGOHLANTIRISH!**\n\n"
                    "Agar davom etsangiz akkountingizdan ayrilasiz.",
                    reply_markup=keyboard
                )
            except:
                pass
        
        await log_admin_action(message.from_user.id, "ban_user", target_id, f"Ban count: {new_count}")
    except Exception as e:
        await message.reply_text(f"Xatolik: {e}")


@Client.on_message(filters.command("unban") & is_admin_filter)
async def unban_handler(client: Client, message: Message):
    user = await get_known_user(message.from_user.id)
    lang = user.get("language", "uz") if user else "uz"
    
    allowed, remaining = check_rate_limit(message.from_user.id, "default")
    if not allowed:
        await message.reply_text(f"⏳ So'rov limitga yetdingiz! Iltimos, biroz kutib turing.")
        return
    
    if not await can_ban(message.from_user.id):
        await message.reply_text(get_text("no_ban_permission", lang))
        return
    
    try:
        args = message.text.split()
        if len(args) != 2:
            await message.reply_text("Format: `/unban [user_id]`")
            return
        target_id = int(args[1])
        await remove_ban(target_id)
        await message.reply_text(f"✅ `{target_id}` blokdan chiqarildi.")
        
        await log_admin_action(message.from_user.id, "unban_user", target_id)
        
        try:
            await client.send_message(target_id, "✅ Blokdan chiqarildingiz! Botdan foydalanishni davom ettirishingiz mumkin.")
        except:
            pass
    except Exception as e:
        await message.reply_text(f"Xatolik: {e}")


@Client.on_message(filters.command("clean_db") & is_admin_filter)
async def clean_db_handler(client: Client, message: Message):
    user = await get_known_user(message.from_user.id)
    lang = user.get("language", "uz") if user else "uz"
    
    allowed, remaining = check_rate_limit(message.from_user.id, "default")
    if not allowed:
        await message.reply_text(f"⏳ So'rov limitga yetdingiz! Iltimos, biroz kutib turing.")
        return
    
    if not await can_clear_db(message.from_user.id):
        await message.reply_text(get_text("no_clear_db_permission", lang))
        return
    
    try:
        await message.reply_text(
            "🧹 **Baza tozalanmoqda...**\n\n"
            "Username'siz barcha userlar o'chirilmoqda...",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Bekor qilish", callback_data="menu_main")
            ]])
        )
        
        deleted_count = await clean_users_without_username()
        
        await log_admin_action(message.from_user.id, "clean_db", None, f"Deleted {deleted_count} users")
        
        await message.reply_text(
            f"✅ **Baza tozalandi!**\n\n"
            f"🗑 O'chirilgan userlar: **{deleted_count}** ta\n\n"
            f"Endi faqat @username bor userlar qoldi.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Bosh menyu", callback_data="menu_main")
            ]])
        )
    except Exception as e:
        await message.reply_text(f"❌ Xatolik: {e}")


@Client.on_callback_query(filters.regex(r"^approve_sub_(?P<uid>\d+)_(?P<days>\d+)$") & is_admin_callback_filter)
async def approve_sub_callback(client: Client, cq: CallbackQuery):
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return
    
    target_id = int(cq.matches[0].group("uid"))
    days = int(cq.matches[0].group("days"))
    from database import grant_subscription
    await grant_subscription(target_id, days)
    await cq.message.edit_text(
        f"{cq.message.text}\n\n✅ **Tasdiqlandi!** `{target_id}` ga {days} kunlik obuna berildi."
    )
    try:
        await client.send_message(target_id, f"🎉 Admin tasdiqladi! Sizga **{days} kunlik** obuna berildi.\n/start")
    except:
        pass
    await cq.answer("Tasdiqlandi!")

@Client.on_callback_query(filters.regex(r"^reject_sub_(?P<uid>\d+)$") & is_admin_callback_filter)
async def reject_sub_callback(client: Client, cq: CallbackQuery):
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return
    
    target_id = int(cq.matches[0].group("uid"))
    await cq.message.edit_text(f"{cq.message.text}\n\n❌ **Rad etildi!**")
    try:
        await client.send_message(target_id, "❌ Obuna so'rovingiz admin tomonidan rad etildi.")
    except:
        pass
    await cq.answer("Rad etildi!")


@Client.on_message(filters.command("broadcast") & is_admin_filter)
async def broadcast_handler(client: Client, message: Message):
    """Barcha ro'yxatdagi foydalanuvchilarga xabar yuborish.
    Foydalanish: /broadcast <matn> — yoki xabar yetkazganga reply qilib /broadcast.
    Matn tayyor bolgach Send/Cancel tasdiq tugmalari chiqariladi."""
    user = await get_known_user(message.from_user.id)
    lang = user.get("language", "uz") if user else "uz"

    allowed, remaining = check_rate_limit(message.from_user.id, "broadcast")
    if not allowed:
        await message.reply_text("⏳ Broadcast limitga yetdingiz! Iltimos, 5 daqiqa so'ng urinib ko'ring.")
        return

    if not await can_broadcast(message.from_user.id):
        await message.reply_text(get_text("no_broadcast_permission", lang))
        return

    from config import user_states

    if message.reply_to_message:
        source_msg_id = message.reply_to_message.id
        text = None
    elif len(message.text.split(maxsplit=1)) > 1:
        source_msg_id = None
        text = message.text.split(maxsplit=1)[1]
    else:
        # Broadcast matn kiritilmagan — avval so'raymiz
        user_states[message.from_user.id] = "broadcast_waiting_text"
        await message.reply_text(
            "📢 **Broadcast xabari**\n\n"
            "Yubormoqchi bo'lgan xabaringizni yozing:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Bekor qilish", callback_data="bc_cancel")
            ]])
        )
        return

    # Send / Cancel tasdiq tuyonal: tugmalar chiqariladi
    user_states[message.from_user.id] = {
        "type": "broadcast_confirm",
        "source_msg_id": source_msg_id,
        "text": text,
        "chat_id": message.chat.id,
    }

    preview = text or "🖼 (reply qilingan xabar)"
    await message.reply_text(
        f"📢 **Broadcastni tasdiqlash**\n\n"
        f"📝 Xabar:\n{preview}\n\n"
        f"👥 Qabul qiluvchilar: hamma ro'yxatdagi foydalanuvchilar (adminlardan tashqari)\n\n"
        f"Yuborishni tasdiqlaysizmi?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Ha, yuborish", callback_data="bc_send")],
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="bc_cancel")]
        ])
    )


@Client.on_callback_query(filters.regex("^bc_send$") & is_admin_callback_filter)
async def bc_send_callback(client: Client, cq: CallbackQuery):
    """Broadcast tasdiqlash — Send tugmasi bosildan ham."""
    if not await can_broadcast(cq.from_user.id):
        await cq.answer("❌ Sizda bu amallni bajarish uchun Broadcast huquqi yo'q!", show_alert=True)
        return

    from config import user_states
    uid = cq.from_user.id
    state = user_states.get(uid)
    if not isinstance(state, dict) or state.get("type") != "broadcast_confirm":
        await cq.answer("❌ Broadcast ma'lumotlari topilmadi! Qaytadan /broadcast bosing.", show_alert=True)
        return
    user_states.pop(uid, None)

    user_ids = await get_all_registered_user_ids()
    if not user_ids:
        await cq.answer("❌ Hech qanday foydalanuvchi topilmadi.", show_alert=True)
        return
    user_ids = [u for u in user_ids if not is_admin(u)]

    await _broadcast_send_all(
        client,
        uid,
        user_ids,
        source_msg_id=state.get("source_msg_id"),
        text=state.get("text"),
        chat_id=state.get("chat_id"),
        status=cq.message,
    )


@Client.on_callback_query(filters.regex("^bc_cancel$") & is_admin_callback_filter)
async def bc_cancel_callback(client: Client, cq: CallbackQuery):
    """Broadcast bekor qilish"""
    from config import user_states
    user_states.pop(cq.from_user.id, None)
    try:
        await cq.message.edit_text("❌ Broadcast bekor qilindi.")
    except Exception:
        pass
    await cq.answer("Bekor qilindi!", show_alert=False)


async def _broadcast_send_all(client, owner_id, user_ids, source_msg_id, text, chat_id, status):
    """Broadcast xabarni barcha foydalanuvchilarga yuborish va natijani ko'rsatish."""
    await status.edit_text("🔓 Spambot unlock qilinmoqda...")
    unlock_success = await send_and_check_unlock(client)
    if unlock_success:
        await status.edit_text("✅ Spambot unlock muvaffaqiyatli!")
    else:
        await status.edit_text("⚠️ Spambot unlock muvaffaqiyatsiz, ammo davom etmoqda...")

    await status.edit_text(
        f"📢 **Broadcast boshlandi...**\n\n"
        f"👥 Jami: {len(user_ids)} ta foydalanuvchi\n"
        f"⏳ Yuborilmoqda..."
    )

    sent = 0
    failed = 0
    blocked = 0
    consecutive_failures = 0
    failed_users = []

    async def _edit_status(msg: str, extra: str = ""):
        try:
            await status.edit_text(msg + (f"\n\n{extra}" if extra else ""))
        except Exception:
            pass

    for i, uid in enumerate(user_ids, 1):
        try:
            if source_msg_id:
                await client.copy_message(chat_id=uid, from_chat_id=chat_id, message_id=source_msg_id)
            else:
                await client.send_message(uid, text)
            sent += 1
            consecutive_failures = 0
        except FloodWait as e:
            await asyncio.sleep(e.value + 2)
            try:
                if source_msg_id:
                    await client.copy_message(chat_id=uid, from_chat_id=chat_id, message_id=source_msg_id)
                else:
                    await client.send_message(uid, text)
                sent += 1
                consecutive_failures = 0
            except Exception:
                failed += 1
                consecutive_failures += 1
                failed_users.append(uid)
        except Exception as e:
            err = str(e).lower()
            if "blocked" in err or "user is deactivated" in err or "chat not found" in err:
                blocked += 1
                consecutive_failures = 0
            else:
                failed += 1
                consecutive_failures += 1
                failed_users.append(uid)

        if i == 10:
            await _edit_status(
                "🔓 **10 ta xabar yuborildi! Auto-unlock qilinmoqda...**",
                f"📊 Yuborildi: {sent} | Xato: {failed} | Blok: {blocked}",
            )
            await send_and_check_unlock(client)
            await _edit_status(
                "✅ **Unlock tugadi! Davom etmoqda...**",
                f"📊 Yuborildi: {sent} | Xato: {failed} | Blok: {blocked}",
            )

        if i == 35:
            await _edit_status(
                "🔓 **35 ta xabar yuborildi! Auto-unlock qilinmoqda...**",
                f"📊 Yuborildi: {sent} | Xato: {failed} | Blok: {blocked}",
            )
            await send_and_check_unlock(client)
            await _edit_status(
                "✅ **Unlock tugadi! Davom etmoqda...**",
                f"📊 Yuborildi: {sent} | Xato: {failed} | Blok: {blocked}",
            )

        if consecutive_failures >= 10:
            await _edit_status(
                "⚠️ **Account locked bo'lishi mumkin! Auto-unlock qilinmoqda...**",
                f"📊 Yuborildi: {sent} | Xato: {failed} | Blok: {blocked}",
            )
            unlock_success = await send_and_check_unlock(client)
            if unlock_success:
                await _edit_status(
                    "✅ **Auto-unlock muvaffaqiyatli! Davom etmoqda...**",
                    f"📊 Yuborildi: {sent} | Xato: {failed} | Blok: {blocked}",
                )
            consecutive_failures = 0

        await asyncio.sleep(0.05)

        if i % 50 == 0:
            try:
                await status.edit_text(
                    f"📢 **Broadcast...**\n\n"
                    f"✅ Yuborildi: {sent}\n🚫 Bloklagan: {blocked}\n❌ Xato: {failed}"
                )
            except Exception:
                pass

    await _edit_status(
        "🔓 **Broadcast tugadi! Oxirgi unlock qilinmoqda...**",
        f"📊 Yuborildi: {sent} | Xato: {failed} | Blok: {blocked}",
    )
    await send_and_check_unlock(client)

    if failed_users:
        from config import user_states
        user_states[owner_id] = {
            "type": "broadcast_retry",
            "failed_users": failed_users,
            "source_msg_id": source_msg_id,
            "text": text,
            "chat_id": chat_id,
        }
        keyboard = [[InlineKeyboardButton("🔄 Xatoga tushganlarga qayta urinish", callback_data="broadcast_retry")]]
    else:
        keyboard = []

    result_text = (
        f"✅ **Broadcast yakunlandi!**\n\n"
        f"✅ Yuborildi: **{sent}** ta\n"
        f"🚫 Botni bloklagan: **{blocked}** ta\n"
        f"❌ Boshqa xato: **{failed}** ta\n"
        f"👥 Jami: **{len(user_ids)}** ta"
    )
    await status.edit_text(
        result_text,
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
    )


@Client.on_callback_query(filters.regex("^broadcast_retry$") & is_admin_callback_filter)
async def broadcast_retry_callback(client: Client, cq: CallbackQuery):
    """Xatoga tushgan userlarga qayta xabar yuborish"""
    if not await can_broadcast(cq.from_user.id):
        await cq.answer("❌ Sizda bu amallni bajarish uchun Broadcast yo'q!", show_alert=True)
        return
    from config import user_states
    
    uid = cq.from_user.id
    state = user_states.get(uid)
    
    if not state or state.get("type") != "broadcast_retry":
        await cq.answer("❌ Retry ma'lumotlari topilmadi!", show_alert=True)
        return
    
    failed_users = state.get("failed_users", [])
    source_msg_id = state.get("source_msg_id")
    text = state.get("text")
    chat_id = state.get("chat_id")
    
    if not failed_users:
        await cq.answer("❌ Xatoga tushgan userlar yo'q!", show_alert=True)
        return
    
    await cq.message.edit_text("🔓 Spambot unlock qilinmoqda...")
    await send_and_check_unlock(client)
    
    status = await cq.message.edit_text(
        f"🔄 **Qayta yuborilmoqda...**\n\n"
        f"👥 Jami: {len(failed_users)} ta user\n"
        f"⏳ Yuborilmoqda..."
    )
    
    sent = 0
    failed = 0
    new_failed_users = []
    
    for retry_uid in failed_users:
        try:
            if source_msg_id:
                await client.copy_message(
                    chat_id=retry_uid,
                    from_chat_id=chat_id,
                    message_id=source_msg_id
                )
            else:
                await client.send_message(retry_uid, text)
            sent += 1
        except Exception as e:
            failed += 1
            new_failed_users.append(retry_uid)
        
        await asyncio.sleep(0.05)
    
    if new_failed_users:
        user_states[uid] = {
            "type": "broadcast_retry",
            "failed_users": new_failed_users,
            "source_msg_id": source_msg_id,
            "text": text,
            "chat_id": chat_id
        }
        retry_button = InlineKeyboardButton("🔄 Yana qayta urinish", callback_data="broadcast_retry")
        keyboard = [[retry_button]]
    else:
        user_states.pop(uid, None)
        keyboard = []
    
    await status.edit_text(
        f"✅ **Qayta yuborish yakunlandi!**\n\n"
        f"✅ Yuborildi: **{sent}** ta\n"
        f"❌ Xato: **{failed}** ta\n"
        f"👥 Jami: **{len(failed_users)}** ta",
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
    )
    
    await cq.answer("Qayta yuborish tugadi!")


def owner_filter(_, __, query: CallbackQuery):
    return query.from_user and is_owner(query.from_user.id)

is_owner_filter = filters.create(owner_filter)

@Client.on_callback_query(filters.regex("^admin_manage_admins$") & is_owner_filter)
async def admin_manage_admins_callback(client: Client, cq: CallbackQuery):
    """Adminlar ro'yxatini ko'rsatish (faqat Owner uchun)"""
    if not is_owner(cq.from_user.id):
        await cq.answer("❌ Bu bo'lim faqat Owner uchun!", show_alert=True)
        return
    
    admins = await get_all_admins()
    
    if not admins:
        await cq.message.edit_text(
            "👑 **Adminlarni boshqarish**\n\n📭 Hozircha admin yo'q.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("➕ Yangi admin qo'shish", callback_data="admin_add_new"),
                InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")
            ]])
        )
        await cq.answer()
        return
    
    lines = ["👑 **Adminlar ro'yxati:**\n"]
    buttons = []
    
    for i, admin in enumerate(admins, 1):
        admin_id = admin["admin_id"]
        admin_date_str = datetime.fromtimestamp(admin["admin_date"]).strftime("%d.%m.%Y")
        
        try:
            tg_user = await client.get_users(admin_id)
            display = f"@{tg_user.username}" if tg_user.username else tg_user.first_name
        except:
            display = f"ID: {admin_id}"
        
        owner_badge = " 👑" if admin_id == OWNER_ID else ""
        lines.append(f"{i}. {display}{owner_badge} — {admin_date_str}")
        buttons.append([InlineKeyboardButton(
            f"👤 {display[:30]}{' 👑' if admin_id == OWNER_ID else ''}", 
            callback_data=f"_admin_view_{admin_id}"
        )])
    
    lines.append(f"\n**Jami: {len(admins)} ta**")
    buttons.append([InlineKeyboardButton("➕ Yangi admin qo'shish", callback_data="admin_add_new")])
    buttons.append([InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")])
    
    await cq.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    await cq.answer()

@Client.on_callback_query(filters.regex(r"^_admin_view_(\d+)$") & is_owner_filter)
async def admin_view_callback(client: Client, cq: CallbackQuery):
    """Admin profilini ko'rsatish (faqat Owner uchun)"""
    if not is_owner(cq.from_user.id):
        await cq.answer("❌ Bu bo'lim faqat Owner uchun!", show_alert=True)
        return
    
    admin_id = int(cq.matches[0].group(1))
    admin_info = await get_admin_info(admin_id)
    
    if not admin_info:
        await cq.answer("Admin topilmadi!", show_alert=True)
        return
    
    try:
        tg_user = await client.get_users(admin_id)
        username = tg_user.username
        first_name = tg_user.first_name
    except:
        username = None
        first_name = None
    
    joined_str = datetime.fromtimestamp(admin_info["joined_date"]).strftime("%d.%m.%Y %H:%M")
    admin_date_str = datetime.fromtimestamp(admin_info["admin_date"]).strftime("%d.%m.%Y %H:%M")
    
    display = f"@{username}" if username else (first_name if first_name else f"ID: {admin_id}")
    owner_badge = " 👑 **Owner**" if admin_id == OWNER_ID else ""
    
    text = (
        f"👑 **Admin profili**{owner_badge}\n\n"
        f"👤 **Ism:** {display}\n"
        f"🆔 **ID:** `{admin_id}`\n"
        f"📅 **Botga qo'shilgan:** {joined_str}\n"
        f"👑 **Admin qilingan:** {admin_date_str}\n\n"
        f"**Huquqlar:**\n"
        f"➕ Yangi admin qo'shish: {'✅ On' if admin_info['can_add_admin'] else '❌ Off'}\n"
        f"⚠️ Ban qilish: {'✅ On' if admin_info['can_ban'] else '❌ Off'}\n"
        f"🧹 Bazani tozalash: {'✅ On' if admin_info['can_clear_db'] else '❌ Off'}\n"
        f"📢 Broadcast: {'✅ On' if admin_info['can_broadcast'] else '❌ Off'}\n"
        f"👥 Foydalanuvchilarni boshqarish: {'✅ On' if admin_info['can_manage_users'] else '❌ Off'}"
    )
    
    buttons = []
    
    if admin_id != OWNER_ID:
        buttons.append([
            InlineKeyboardButton("➕ Admin qo'shish", callback_data=f"_perm_add_{admin_id}"),
            InlineKeyboardButton("⚠️ Ban", callback_data=f"_perm_ban_{admin_id}")
        ])
        buttons.append([
            InlineKeyboardButton("🧹 DB tozalash", callback_data=f"_perm_clear_{admin_id}"),
            InlineKeyboardButton("📢 Broadcast", callback_data=f"_perm_broadcast_{admin_id}")
        ])
        buttons.append([
            InlineKeyboardButton("👥 User boshqarish", callback_data=f"_perm_users_{admin_id}"),
            InlineKeyboardButton("❌ Adminlikdan olish", callback_data=f"_admin_remove_confirm_{admin_id}")
        ])
    else:
        buttons.append([InlineKeyboardButton("🔙 Ro'yxatga qaytish", callback_data="admin_manage_admins")])
    
    buttons.append([InlineKeyboardButton("🔙 Ro'yxatga qaytish", callback_data="admin_manage_admins")])
    
    await cq.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    await cq.answer()

@Client.on_callback_query(filters.regex(r"^_perm_(\w+)_(\d+)$") & is_owner_filter)
async def admin_toggle_permission_callback(client: Client, cq: CallbackQuery):
    """Admin huquqini toggle qilish (faqat Owner uchun)"""
    if not is_owner(cq.from_user.id):
        await cq.answer("❌ Bu bo'lim faqat Owner uchun!", show_alert=True)
        return
    
    permission = cq.matches[0].group(1)
    admin_id = int(cq.matches[0].group(2))
    
    perm_map = {
        "add": "can_add_admin",
        "ban": "can_ban",
        "clear": "can_clear_db",
        "broadcast": "can_broadcast",
        "users": "can_manage_users"
    }
    
    db_perm = perm_map.get(permission)
    if not db_perm:
        await cq.answer("Noto'g'ri huquq!", show_alert=True)
        return
    
    admin_info = await get_admin_info(admin_id)
    if not admin_info:
        await cq.answer("Admin topilmadi!", show_alert=True)
        return
    
    if admin_id == OWNER_ID and db_perm == "can_add_admin":
        await cq.answer("❌ Owner o'ziga o'zi admin qo'shish huquqini o'chira olmaydi!", show_alert=True)
        return
    
    if admin_id == cq.from_user.id:
        await cq.answer("❌ O'zingizning huquqingizni o'chira olmaysiz!", show_alert=True)
        return
    
    current_value = admin_info[db_perm]
    new_value = not current_value
    
    await update_admin_permission(admin_id, db_perm, new_value)
    msg = "✅ Yoqildi" if new_value else "❌ O'chirildi"
    await cq.answer(f"{msg}!", show_alert=True)
    
    await log_admin_action(cq.from_user.id, "toggle_permission", admin_id, f"Permission: {db_perm}, New value: {new_value}")
    
    admin_info = await get_admin_info(admin_id)
    
    try:
        tg_user = await client.get_users(admin_id)
        username = tg_user.username
        first_name = tg_user.first_name
    except:
        username = None
        first_name = None
    
    joined_str = datetime.fromtimestamp(admin_info["joined_date"]).strftime("%d.%m.%Y %H:%M")
    admin_date_str = datetime.fromtimestamp(admin_info["admin_date"]).strftime("%d.%m.%Y %H:%M")
    
    display = f"@{username}" if username else (first_name if first_name else f"ID: {admin_id}")
    
    text = (
        f"👑 **Admin profili**\n\n"
        f"👤 **Ism:** {display}\n"
        f"🆔 **ID:** `{admin_id}`\n"
        f"📅 **Botga qo'shilgan:** {joined_str}\n"
        f"👑 **Admin qilingan:** {admin_date_str}\n\n"
        f"**Huquqlar:**\n"
        f"➕ Yangi admin qo'shish: {'✅ On' if admin_info['can_add_admin'] else '❌ Off'}\n"
        f"⚠️ Ban qilish: {'✅ On' if admin_info['can_ban'] else '❌ Off'}\n"
        f"🧹 Bazani tozalash: {'✅ On' if admin_info['can_clear_db'] else '❌ Off'}\n"
        f"📢 Broadcast: {'✅ On' if admin_info['can_broadcast'] else '❌ Off'}\n"
        f"👥 Foydalanuvchilarni boshqarish: {'✅ On' if admin_info['can_manage_users'] else '❌ Off'}"
    )
    
    buttons = [
        [
            InlineKeyboardButton("➕ Admin qo'shish", callback_data=f"_perm_add_{admin_id}"),
            InlineKeyboardButton("⚠️ Ban", callback_data=f"_perm_ban_{admin_id}")
        ],
        [
            InlineKeyboardButton("🧹 DB tozalash", callback_data=f"_perm_clear_{admin_id}"),
            InlineKeyboardButton("📢 Broadcast", callback_data=f"_perm_broadcast_{admin_id}")
        ],
        [
            InlineKeyboardButton("👥 User boshqarish", callback_data=f"_perm_users_{admin_id}"),
            InlineKeyboardButton("❌ Adminlikdan olish", callback_data=f"_admin_remove_confirm_{admin_id}")
        ],
        [InlineKeyboardButton("🔙 Ro'yxatga qaytish", callback_data="admin_manage_admins")]
    ]
    
    await cq.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^_admin_remove_confirm_(\d+)$") & is_owner_filter)
async def admin_remove_confirm_callback(client: Client, cq: CallbackQuery):
    """Adminlikdan olishni tasdiqlash (faqat Owner uchun)"""
    if not is_owner(cq.from_user.id):
        await cq.answer("❌ Bu bo'lim faqat Owner uchun!", show_alert=True)
        return
    
    admin_id = int(cq.matches[0].group(1))
    
    if admin_id == OWNER_ID:
        await cq.answer("O'zingizni adminlikdan olisha olmaysiz!", show_alert=True)
        return
    
    try:
        tg_user = await client.get_users(admin_id)
        display = f"@{tg_user.username}" if tg_user.username else tg_user.first_name
    except:
        display = f"ID: {admin_id}"
    
    await cq.message.edit_text(
        f"⚠️ **{display}** ni adminlikdan olishni tasdiqlaysizmi?\n"
        "(Bu amal qaytarib bo'lmaydi!)",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Ha, olish", callback_data=f"_admin_remove_do_{admin_id}"),
                InlineKeyboardButton("❌ Yo'q", callback_data=f"_admin_view_{admin_id}"),
            ]
        ])
    )
    await cq.answer()

@Client.on_callback_query(filters.regex(r"^_admin_remove_do_(\d+)$") & is_owner_filter)
async def admin_remove_do_callback(client: Client, cq: CallbackQuery):
    """Adminlikdan olish (faqat Owner uchun)"""
    if not is_owner(cq.from_user.id):
        await cq.answer("❌ Bu bo'lim faqat Owner uchun!", show_alert=True)
        return
    
    admin_id = int(cq.matches[0].group(1))
    
    await remove_admin(admin_id)
    
    await log_admin_action(cq.from_user.id, "remove_admin", admin_id)
    
    await config.load_admin_ids_from_db()
    
    await cq.answer("Adminlikdan olindi!", show_alert=True)
    
    admins = await get_all_admins()
    
    if not admins:
        await cq.message.edit_text(
            "👑 **Adminlarni boshqarish**\n\n📭 Hozircha admin yo'q.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("➕ Yangi admin qo'shish", callback_data="admin_add_new"),
                InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")
            ]])
        )
        return
    
    lines = ["👑 **Adminlar ro'yxati:**\n"]
    buttons = []
    
    for i, admin in enumerate(admins, 1):
        aid = admin["admin_id"]
        admin_date_str = datetime.fromtimestamp(admin["admin_date"]).strftime("%d.%m.%Y")
        
        try:
            tg_user = await client.get_users(aid)
            display = f"@{tg_user.username}" if tg_user.username else tg_user.first_name
        except:
            display = f"ID: {aid}"
        
        owner_badge = " 👑" if aid == OWNER_ID else ""
        lines.append(f"{i}. {display}{owner_badge} — {admin_date_str}")
        buttons.append([InlineKeyboardButton(
            f"👤 {display[:30]}{' 👑' if aid == OWNER_ID else ''}", 
            callback_data=f"_admin_view_{aid}"
        )])
    
    lines.append(f"\n**Jami: {len(admins)} ta**")
    buttons.append([InlineKeyboardButton("➕ Yangi admin qo'shish", callback_data="admin_add_new")])
    buttons.append([InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")])
    
    await cq.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@Client.on_callback_query(filters.regex("^admin_add_new$") & is_owner_filter)
async def admin_add_new_callback(client: Client, cq: CallbackQuery):
    """Yangi admin qo'shish uchun user ID so'rash (faqat Owner uchun)"""
    if not is_owner(cq.from_user.id):
        await cq.answer("❌ Bu bo'lim faqat Owner uchun!", show_alert=True)
        return
    
    from config import user_states
    user_states[cq.from_user.id] = "admin_add_new"
    
    await cq.message.edit_text(
        "➕ **Yangi admin qo'shish**\n\n"
        "User ID yoki @username yuboring:\n"
        "Masalan: `123456789` yoki `@username`",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_manage_admins")
        ]])
    )
    await cq.answer()

@Client.on_message(filters.private & filters.text)
async def admin_add_handler(client: Client, message: Message):
    """Yangi admin qo'shish handler"""
    from config import user_states
    from pyrogram import ContinuePropagation
    uid = message.from_user.id
    
    state = user_states.get(uid)
    if state == "broadcast_waiting_text":
        broadcast_text = message.text.strip()
        if not broadcast_text:
            await message.reply_text(
                "❌ Matn bo'sh bo'lishi mumkin emas! Qaytadan yozing yoki bekor qiling.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Bekor qilish", callback_data="bc_cancel")
                ]])
            )
            return

        # Broadcast matni qabul qilindi — Send/Cancel tasdiq tugmalarini chiqaramiz
        user_states[uid] = {
            "type": "broadcast_confirm",
            "source_msg_id": None,
            "text": broadcast_text,
            "chat_id": message.chat.id,
        }
        await message.reply_text(
            f"📢 **Broadcastni tasdiqlash**\n\n"
            f"📝 Xabar:\n{broadcast_text}\n\n"
            f"👥 Qabul qiluvchilar: hamma ro'yxatdagi foydalanuvchilar (adminlardan tashqari)\n\n"
            f"Yuborishni tasdiqlaysizmi?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Ha, yuborish", callback_data="bc_send")],
                [InlineKeyboardButton("❌ Bekor qilish", callback_data="bc_cancel")]
            ])
        )
        return

    if state == "waiting_for_tag_message":
        user_states.pop(uid, None)
        
        new_message = message.text.strip()
        if not new_message:
            await message.reply_text(
                "❌ Matn bo'sh bo'lishi mumkin emas!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Tag matnlari", callback_data="admin_tag_messages")
                ]])
            )
            return
        
        from plugins.utag import TAG_MESSAGES
        new_id = max(TAG_MESSAGES.keys()) + 1 if TAG_MESSAGES else 1
        TAG_MESSAGES[new_id] = new_message
        
        await message.reply_text(
            f"✅ **Matn qo'shildi!**\n\n"
            f"🆔 ID: **{new_id}**\n"
            f"💬 Matn: {new_message}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Tag matnlari", callback_data="admin_tag_messages")
            ]])
        )
        return
    
    if state == "admin_fj_add_channel":
        user_states.pop(uid, None)
        from plugins.force_join import handle_admin_add_channel_input
        await handle_admin_add_channel_input(client, message)
        return

    if state == "admin_add_new":
        if not is_owner(uid):
            user_states.pop(uid, None)
            await message.reply_text("❌ Bu bo'lim faqat Owner uchun!")
            return
    else:
        raise ContinuePropagation

    import re as _re

    user_states.pop(uid, None)
    raw = (message.text or "").strip()
    lowered = raw.lower()

    # 1-FILTR: Guruh/profil havolalari qabul qilinmaydi
    link_markers = ("t.me/", "telegram.me/", "telegram.dog/", "http://", "https://", "joinchat", "tg://")
    if any(m in lowered for m in link_markers) or lowered.startswith("+"):
        await message.reply_text(
            "❌ **Havola yuborildi!**\n\n"
            "Guruh yoki profil havolasi qabul qilinmaydi.\n"
            "Faqat **user ID** yoki **@username** yuboring:\n"
            "Masalan: `123456789` yoki `@username`",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")
            ]])
        )
        return

    query = raw.lstrip("@").strip()

    if query.isdigit():
        target_id = int(query)
    elif _re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,31}", query):
        # Telegram orqali tekshirish va odam akkounti ekanligini aniqlash
        try:
            resolved = await client.get_users(f"@{query}")
            if isinstance(resolved, list):
                resolved = resolved[0]
        except Exception:
            await message.reply_text(
                f"❌ `@{query}` Telegramda topilmadi yoki bu kanal/guruh.\n"
                "Faqat odam akkountining ID yoki @username yuboring.",
                reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")
            ]])
            )
            return
        if getattr(resolved, "is_bot", False):
            await message.reply_text(
                f"❌ `@{query}` — bu **bot** akkounti!\n"
                "Faqat odam (inson) akkountlarini admin qilish mumkin.",
                reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")
            ]])
            )
            return
        target_id = resolved.id
    else:
        await message.reply_text(
            "❌ **Noto'g'ri format!**\n\n"
            "Faqat **user ID** (`123456789`) yoki **@username** yuboring.\n"
            "Havola (t.me/...) yubormang!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")
            ]])
        )
        return
    
    if is_admin(target_id):
        await message.reply_text(
            f"❌ Bu foydalanuvchi allaqachon admin!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")
            ]])
        )
        return
    
    try:
        tg_user = await client.get_users(target_id)
        if isinstance(tg_user, list):
            tg_user = tg_user[0]
        username = tg_user.username
        first_name = tg_user.first_name
    except Exception:
        await message.reply_text(
            "❌ Foydalanuvchi topilmadi! ID noto'g'ri yoki bu kanal/guruh.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")
            ]])
        )
        return

    if getattr(tg_user, "is_bot", False):
        await message.reply_text(
            f"❌ `{target_id}` — bu **bot** akkounti!\n"
            "Faqat odam (inson) akkountlarini admin qilish mumkin.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")
            ]])
        )
        return
    
    from database import get_known_user, register_known_user
    known = await get_known_user(target_id)
    if known:
        joined_date = known["joined_date"]
    else:
        import time
        joined_date = int(time.time())
        await register_known_user(target_id, username, first_name)
    
    import time
    admin_date = int(time.time())
    await add_admin(target_id, joined_date, admin_date)
    
    await log_admin_action(message.from_user.id, "add_admin", target_id, f"Joined: {joined_date}, Admin date: {admin_date}")
    
    await config.load_admin_ids_from_db()
    
    display = f"@{username}" if username else first_name
    
    await message.reply_text(
        f"✅ **{display}** admin qilindi!\n\n"
        f"🆔 ID: `{target_id}`\n"
        f"👑 Admin qilingan: {datetime.fromtimestamp(admin_date).strftime('%d.%m.%Y %H:%M')}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")
        ]])
    )
    
    try:
        await client.send_message(
            target_id,
            f"🎉 **Tabriklaymiz!**\n\n"
            f"Siz admin tomonidan admin qilindingiz!\n"
            f"Endi admin paneldan foydalanishingiz mumkin."
        )
    except:
        pass



@Client.on_callback_query(filters.regex("^admin_tag_messages$") & is_admin_callback_filter)
async def admin_tag_messages_callback(client: Client, cq: CallbackQuery):
    """Tag matnlari ro'yxatini ko'rsatish"""
    import time
    start_time = time.time()
    logger.info("[DIAG] HANDLER_START: handler=admin_tag_messages_callback callback_data=%s", cq.data)

    try:
        # TAG_MESSAGES yangi backend'da dict bo'lmasdan qolishi mumkin.
        # Hamma holatda xavfsiz ishlash uchun dict() ga aylantiramiz.
        try:
            tags = dict(TAG_MESSAGES)
        except Exception:
            tags = {}

        lines = ["💬 **Tag Matnlari Ro'yxati**\n\n"]

        # Ro'yxat juda uzun qolmasligi uchun 4096 belg chegarasini hisobga olamiz.
        # Oxirgi 50 ta ko'satamiz; qolganlarni jami sonida ko'rsatamiz.
        sorted_ids = sorted(tags.keys())
        MAX_SHOWN = 50
        for msg_id in sorted_ids[:MAX_SHOWN]:
            msg_text = str(tags[msg_id])
            lines.append(f"**{msg_id}.** {msg_text}")
        if len(sorted_ids) > MAX_SHOWN:
            lines.append(f"\n… va yana **{len(sorted_ids) - MAX_SHOWN}** ta matn")
        lines.append(f"\n📊 Jami: **{len(tags)}** ta matn")

        text = "\n".join(lines)

        keyboard = [
            [InlineKeyboardButton("➕ Yangi matn qo'shish", callback_data="admin_tag_add")],
            [InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")]
        ]

        try:
            await cq.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as edit_err:
            # MessageNotModified / ochirilgan xabar kabi kutilgan Telegram xatolarni
            # handler buzilmasdan qabul qilamiz (jiravid nohuj, davom skipp).
            logger.debug("[DIAG] admin_tag_messages edit_text xatolik: %s", edit_err)
        await cq.answer()

        duration_ms = (time.time() - start_time) * 1000
        logger.info("[DIAG] HANDLER_END: handler=admin_tag_messages_callback duration_ms=%.2f", duration_ms)
        if duration_ms > 2000:
            logger.warning("[DIAG] HANDLER_SLOW: handler=admin_tag_messages_callback duration_ms=%.2f", duration_ms)
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error("[DIAG] HANDLER_ERROR: handler=admin_tag_messages_callback duration_ms=%.2f error=%s", duration_ms, e, exc_info=True)
        # Xatoni qayta ko'tarmaymiz — handler buzilmasligi uchun.
        # Callbackni davom o'yno tugash uchun qabul qiymiz.
        try:
            await cq.answer()
        except Exception:
            pass


@Client.on_callback_query(filters.regex("^admin_tag_add$") & is_admin_callback_filter)
async def admin_tag_add_callback(client: Client, cq: CallbackQuery):
    """Yangi tag matn qo'shish uchun"""
    from config import user_states
    
    user_states[cq.from_user.id] = "waiting_for_tag_message"
    
    await cq.message.edit_text(
        "✍️ **Yangi Tag Matn Qo'shish**\n\n"
        "Matnni yuboring:\n"
        "Masalan: salom do'stim",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_tag_messages")]])
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^admin_complaints$") & is_admin_callback_filter)
async def admin_complaints_callback(client: Client, cq: CallbackQuery):
    """Shikoyatlar ro'yxatini ko'rsatish"""
    import time
    start_time = time.time()
    logger.info("[DIAG] HANDLER_START: handler=admin_complaints_callback callback_data=%s", cq.data)
    
    try:
        complaints = await get_all_complaints(limit=20)
        pending_count = await get_complaint_count("pending")
        read_count = await get_complaint_count("read")
        replied_count = await get_complaint_count("replied")
        
        text = (
            f"📩 **Shikoyatlar**\n\n"
            f"⏳ Kutilayotgan: **{pending_count}** ta\n"
            f"📖 O'qilgan: **{read_count}** ta\n"
            f"✅ Javob berilgan: **{replied_count}** ta\n\n"
            f"**Jami: {pending_count + read_count + replied_count}** ta\n\n"
            "Quyidagi bo'limlardan birini tanlang:"
        )
        
        keyboard = [
            [InlineKeyboardButton(f"⏳ Kutilayotgan ({pending_count})", callback_data="complaints_pending_0")],
            [InlineKeyboardButton(f"📖 O'qilgan ({read_count})", callback_data="complaints_read_0")],
            [InlineKeyboardButton(f"✅ Javob berilgan ({replied_count})", callback_data="complaints_replied_0")],
            [InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")],
        ]
        
        await cq.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        await cq.answer()
        
        duration_ms = (time.time() - start_time) * 1000
        logger.info("[DIAG] HANDLER_END: handler=admin_complaints_callback duration_ms=%.2f", duration_ms)
        if duration_ms > 2000:
            logger.warning("[DIAG] HANDLER_SLOW: handler=admin_complaints_callback duration_ms=%.2f", duration_ms)
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error("[DIAG] HANDLER_ERROR: handler=admin_complaints_callback duration_ms=%.2f error=%s", duration_ms, e, exc_info=True)
        raise

@Client.on_callback_query(filters.regex(r"^complaints_(pending|read|replied)_(\d+)$") & is_admin_callback_filter)
async def complaints_list_callback(client: Client, cq: CallbackQuery):
    """Shikoyatlar ro'yxatini ko'rsatish (sahifalab)"""
    status = cq.matches[0].group(1)
    offset = int(cq.matches[0].group(2))
    
    complaints = await get_complaints_by_status(status, limit=10, offset=offset)
    title_map = {
        "pending": "⏳ **Kutilayotgan shikoyatlar**",
        "read": "📖 **O'qilgan shikoyatlar**",
        "replied": "✅ **Javob berilgan shikoyatlar**"
    }
    title = title_map.get(status, f"📋 **Shikoyatlar ro'yxati**")
    
    if not complaints:
        await cq.message.edit_text(
            f"{title}\n\n📭 Hozircha shikoyat yo'q.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Shikoyatlar", callback_data="admin_complaints")]])
        )
        await cq.answer()
        return
    
    lines = [f"{title}\n\n"]
    buttons = []
    
    for complaint in complaints:
        cid = complaint["id"]
        user_id = complaint["user_id"]
        subject = complaint["subject"]
        status_emoji = "⏳" if complaint["status"] == "pending" else "📖" if complaint["status"] == "read" else "✅"
        
        lines.append(f"{status_emoji} **#{cid}** - {subject}\n")
        buttons.append([InlineKeyboardButton(
            f"{status_emoji} #{cid} - {subject[:30]}",
            callback_data=f"complaint_view_{cid}"
        )])
    
    if offset > 0:
        buttons.append([InlineKeyboardButton("◀️ Oldingi", callback_data=f"complaints_{status}_{offset-10}")])
    if len(complaints) == 10:
        buttons.append([InlineKeyboardButton("▶️ Keyingi", callback_data=f"complaints_{status}_{offset+10}")])
    
    buttons.append([InlineKeyboardButton("🔙 Shikoyatlar", callback_data="admin_complaints")])
    
    await cq.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    await cq.answer()

@Client.on_callback_query(filters.regex(r"^complaint_view_(\d+)$") & is_admin_callback_filter)
async def complaint_view_callback(client: Client, cq: CallbackQuery):
    """Bitta shikoyatni ko'rish"""
    complaint_id = int(cq.matches[0].group(1))
    complaint = await get_complaint_by_id(complaint_id)
    
    if not complaint:
        await cq.answer("Shikoyat topilmadi!", show_alert=True)
        return
    
    status_text = {
        "pending": "⏳ Kutilayotgan",
        "read": "📖 O'qilgan",
        "replied": "✅ Javob berilgan"
    }.get(complaint["status"], "❓ Noma'lum")
    
    created_str = datetime.fromtimestamp(complaint["created_at"]).strftime("%d.%m.%Y %H:%M")
    
    text = (
        f"📩 **Shikoyat #{complaint['id']}**\n\n"
        f"👤 **Foydalanuvchi:** {complaint['first_name']}"
        f" (@{complaint['username']})" if complaint['username'] else f"\n👤 **Foydalanuvchi:** {complaint['first_name']}\n"
        f"🆔 **User ID:** `{complaint['user_id']}`\n\n"
        f"📋 **Sarlavha:** {complaint['subject']}\n\n"
        f"💬 **Xabar:**\n{complaint['message']}\n\n"
        f"📊 **Holat:** {status_text}\n"
        f"📅 **Yuborilgan:** {created_str}"
    )
    
    if complaint["status"] == "replied" and complaint["admin_reply"]:
        replied_str = datetime.fromtimestamp(complaint["replied_at"]).strftime("%d.%m.%Y %H:%M")
        text += f"\n\n💬 **Javob:** {complaint['admin_reply']}\n📅 {replied_str}"
    
    buttons = []
    
    if complaint["status"] == "pending":
        buttons.append([InlineKeyboardButton("📖 O'qildi deb belgilash", callback_data=f"complaint_read_{complaint_id}")])
    
    buttons.append([InlineKeyboardButton("💬 Javob yozish", callback_data=f"complaint_reply_{complaint_id}")])
    buttons.append([InlineKeyboardButton("🔙 Shikoyatlar", callback_data="admin_complaints")])
    
    if complaint.get("photo_file_id"):
        try:
            await cq.message.reply_photo(
                complaint["photo_file_id"],
                caption=text,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            await cq.answer()
            return
        except:
            pass
    
    await cq.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    await cq.answer()

@Client.on_callback_query(filters.regex(r"^complaint_read_(\d+)$") & is_admin_callback_filter)
async def complaint_read_callback(client: Client, cq: CallbackQuery):
    """Shikoyatni o'qilgan deb belgilash"""
    complaint_id = int(cq.matches[0].group(1))
    
    await mark_complaint_read(complaint_id)
    
    complaint = await get_complaint_by_id(complaint_id)
    if complaint:
        try:
            await client.send_message(
                complaint["user_id"],
                "✅ **Murojaatingiz haqida Adminlar habar topdi!**\n\n"
                "Tez orada hal qilinadi yoki siz bilan bog'lanishadi."
            )
        except:
            pass
    
    await cq.answer("✅ O'qilgan deb belgilandi!", show_alert=True)
    
    cq.data = f"complaint_view_{complaint_id}"
    await complaint_view_callback(client, cq)

@Client.on_callback_query(filters.regex(r"^complaint_reply_(\d+)$") & is_admin_callback_filter)
async def complaint_reply_callback(client: Client, cq: CallbackQuery):
    """Shikoyatga javob yozish"""
    from config import user_states
    
    complaint_id = int(cq.matches[0].group(1))
    user_states[cq.from_user.id] = f"waiting_complaint_reply|{complaint_id}"
    
    await cq.message.edit_text(
        f"💬 **Shikoyat #{complaint_id} ga javob yozish**\n\n"
        "Javob matnini yuboring:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor qilish", callback_data=f"complaint_view_{complaint_id}")]])
    )
    await cq.answer()

@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def complaint_reply_handler(client: Client, message: Message):
    """Shikoyatga javob yozish handler"""
    from config import user_states
    from pyrogram import ContinuePropagation
    
    uid = message.from_user.id
    state = user_states.get(uid)
    
    if not state or not state.startswith("waiting_complaint_reply|"):
        raise ContinuePropagation
    
    complaint_id = int(state.replace("waiting_complaint_reply|", ""))
    reply_text = message.text.strip()
    
    if len(reply_text) < 5:
        await message.reply_text(
            "❌ Javob kamida 5 ta belgidan iborat bo'lishi kerak.\n"
            "Qaytadan kiriting:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor qilish", callback_data=f"complaint_view_{complaint_id}")]])
        )
        return
    
    await reply_to_complaint(complaint_id, reply_text)
    
    user_states.pop(uid, None)
    
    complaint = await get_complaint_by_id(complaint_id)
    if complaint:
        try:
            await client.send_message(
                complaint["user_id"],
                f"💬 **Sizning shikoyatingizga javob!**\n\n"
                f"📋 **Sarlavha:** {complaint['subject']}\n\n"
                f"💬 **Javob:**\n{reply_text}"
            )
        except:
            pass
    
    await message.reply_text(
        f"✅ **Javob yuborildi!**\n\n"
        f"Shikoyat #{complaint_id} ga javob yozildi va foydalanuvchiga yuborildi.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Shikoyatlar", callback_data="admin_complaints")]])
    )


@Client.on_callback_query(filters.regex(r"^admin_active_tasks_(\d+)$") & is_admin_callback_filter)
async def admin_active_tasks_callback(client: Client, cq: CallbackQuery):
    """Faol user tasklarini ko'rsatish (Admin Control Panel)"""
    page = int(cq.matches[0].group(1))
    per_page = 5
    
    active_tasks = await get_all_active_tasks()
    
    if not active_tasks:
        await cq.message.edit_text(
            "⚡️ **Active User Tasks**\n\n📭 Hozircha faol task yo'q.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")]])
        )
        await cq.answer()
        return
    
    task_list = list(active_tasks.items())
    total_tasks = len(task_list)
    total_pages = max(1, (total_tasks + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    
    start_idx = page * per_page
    end_idx = min(start_idx + per_page, total_tasks)
    page_tasks = task_list[start_idx:end_idx]
    
    lines = [f"⚡️ **Active User Tasks** ({total_tasks} ta)\n"]
    buttons = []
    
    for user_id, task_info in page_tasks:
        task_type = task_info.get("task_type", "unknown")
        target = task_info.get("target", "N/A")
        progress = task_info.get("progress", 0)
        start_time = task_info.get("start_time", 0)
        
        elapsed = int(time.time() - start_time) if start_time else 0
        elapsed_str = f"{elapsed // 60} daqiqa" if elapsed < 3600 else f"{elapsed // 3600} soat"
        
        try:
            tg_user = await client.get_users(user_id)
            user_display = f"@{tg_user.username}" if tg_user.username else tg_user.first_name
        except:
            user_display = f"ID: {user_id}"
        
        lines.append(
            f"👤 **{user_display}**\n"
            f"   📋 Task: {task_type}\n"
            f"   🎯 Target: {target}\n"
            f"   📊 Progress: {progress}\n"
            f"   ⏱ Vaqt: {elapsed_str}\n"
        )
        
        buttons.append([InlineKeyboardButton(
            f"👤 {user_display[:25]} - {task_type}",
            callback_data=f"admin_task_control_{user_id}"
        )])
    
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀️ Oldingi", callback_data=f"admin_active_tasks_{page - 1}"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("▶️ Keyingi", callback_data=f"admin_active_tasks_{page + 1}"))
        if nav:
            buttons.append(nav)
    
    buttons.append([InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")])
    
    await cq.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    await cq.answer()

@Client.on_callback_query(filters.regex(r"^admin_task_control_(\d+)$") & is_admin_callback_filter)
async def admin_task_control_callback(client: Client, cq: CallbackQuery):
    """Task control panel - terminate/pause/ban user"""
    user_id = int(cq.matches[0].group(1))
    
    active_tasks = await get_all_active_tasks()
    task_info = active_tasks.get(user_id)
    
    if not task_info:
        await cq.answer("Bu userda faol task yo'q!", show_alert=True)
        return
    
    task_type = task_info.get("task_type", "unknown")
    target = task_info.get("target", "N/A")
    progress = task_info.get("progress", 0)
    
    try:
        tg_user = await client.get_users(user_id)
        user_display = f"@{tg_user.username}" if tg_user.username else tg_user.first_name
    except:
        user_display = f"ID: {user_id}"
    
    text = (
        f"⚙️ **Task Control Panel**\n\n"
        f"👤 **User:** {user_display}\n"
        f"🆔 **ID:** `{user_id}`\n"
        f"📋 **Task:** {task_type}\n"
        f"🎯 **Target:** {target}\n"
        f"📊 **Progress:** {progress}\n\n"
        f"Quyidagi amallardan birini tanlang:"
    )
    
    buttons = [
        [InlineKeyboardButton("🛑 Terminate Task", callback_data=f"admin_task_terminate_{user_id}")],
        [InlineKeyboardButton("🚫 Terminate & Ban User", callback_data=f"admin_task_terminate_ban_{user_id}")],
        [InlineKeyboardButton("🔙 Active Tasks", callback_data="admin_active_tasks_0")],
    ]
    
    await cq.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    await cq.answer()

@Client.on_callback_query(filters.regex(r"^admin_task_terminate_(\d+)$") & is_admin_callback_filter)
async def admin_task_terminate_callback(client: Client, cq: CallbackQuery):
    """Taskni to'xtatish"""
    if not await can_ban(cq.from_user.id):
        await cq.answer("❌ Sizda bu amallni bajarish uchun Ban qilish yo'q!", show_alert=True)
        return
    user_id = int(cq.matches[0].group(1))
    
    success = await terminate_user_task(user_id, ban_user=False)
    
    if success:
        try:
            await client.send_message(
                user_id,
                "⚠️ **Your active task was forcibly terminated by an Admin.**\n\n"
                "Iltimos, keyinroq qayta urinib ko'ring."
            )
        except:
            pass
        
        await cq.answer("✅ Task to'xtatildi!", show_alert=True)
    else:
        await cq.answer("❌ Task topilmadi yoki allaqachon to'xtatilgan!", show_alert=True)
    
    cq.data = "admin_active_tasks_0"
    await admin_active_tasks_callback(client, cq)

@Client.on_callback_query(filters.regex(r"^admin_task_terminate_ban_(\d+)$") & is_admin_callback_filter)
async def admin_task_terminate_ban_callback(client: Client, cq: CallbackQuery):
    """Taskni to'xtatish va userni ban qilish"""
    if not await can_ban(cq.from_user.id):
        await cq.answer("❌ Sizda bu amallni bajarish uchun Ban qilish yo'q!", show_alert=True)
        return
    user_id = int(cq.matches[0].group(1))
    
    success = await terminate_user_task(user_id, ban_user=True)
    
    if success:
        try:
            await client.send_message(
                user_id,
                "🚫 **Your active task was terminated and your account has been banned by an Admin.**\n\n"
                "Agar shikoyatingiz bo'lsa, admin bilan bog'laning."
            )
        except:
            pass
        
        await cq.answer("✅ Task to'xtatildi va user ban qilindi!", show_alert=True)
    else:
        await cq.answer("❌ Task topilmadi yoki allaqachon to'xtatilgan!", show_alert=True)
    
    cq.data = "admin_active_tasks_0"
    await admin_active_tasks_callback(client, cq)


# ---------------------------------------------------------------------------
# Referral statistikasi (admin dashboard)
# ---------------------------------------------------------------------------

@Client.on_callback_query(filters.regex("^admin_referrals$") & is_admin_callback_filter)
async def admin_referrals_callback(client: Client, cq: CallbackQuery):
    """Admin referral dashboardi: umumiy statistika + top taklifchilar."""
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return

    from database import get_referral_overview, get_top_referrers
    from feature_flags import is_referral_enabled

    enabled = await is_referral_enabled()
    overview = await get_referral_overview()
    top = await get_top_referrers(10)

    status_label = "🟢 Yoqilgan" if enabled else "🔴 O'chirilgan"
    medals = ["🥇", "🥈", "🥉"]
    lines = [
        "👥 **Referral Statistikasi**\n",
        f"⚙️ Holati: {status_label}",
        f"🔗 Jami taklif qilinganlar: **{overview['total_referred']}** ta",
        f"👤 Taklif qilgan foydalanuvchilar: **{overview['distinct_referrers']}** ta",
        f"💎 Obuna olgan takliflar: **{overview['converted']}** ta ({overview['conversion_pct']}%)",
    ]
    buttons = [
        [InlineKeyboardButton(
            "🔴 O'chirish" if enabled else "🟢 Yoqish",
            callback_data="admin_ref_toggle",
        )]
    ]
    if top:
        lines.append("\n🏆 **Eng ko'p taklif qilganlar:**")
        for i, t in enumerate(top):
            medal = medals[i] if i < len(medals) else f"{i + 1}."
            name = f"@{t['username']}" if t['username'] else (t['first_name'] or str(t['referrer_id']))
            lines.append(f"{medal} {name} — {t['invited']} ta taklif, {t['paid']} ta obuna")
            buttons.append([InlineKeyboardButton(
                f"📋 {name} ({t['invited']})",
                callback_data=f"admin_ref_detail_{t['referrer_id']}",
            )])
    else:
        lines.append("\n📭 Hozircha hech kim taklif qilmagan.")

    buttons.append([InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")])

    await cq.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^admin_ref_detail_(\d+)$") & is_admin_callback_filter)
async def admin_ref_detail_callback(client: Client, cq: CallbackQuery):
    """Bir referrer'ning taklif qilganlari ro'yxati (kim kimni, holati bilan)."""
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return

    from database import get_referral_invitees, _get_user_display

    referrer_id = int(cq.matches[0].group(1))
    invitees = await get_referral_invitees(referrer_id, 30)
    r_username, r_first_name = await _get_user_display(referrer_id)
    referrer_label = f"@{r_username}" if r_username else (r_first_name or str(referrer_id))

    lines = [f"👥 **{referrer_label}** (`{referrer_id}`) — taklif qilganlari: **{len(invitees)}** ta\n"]

    converted = 0
    if invitees:
        for inv in invitees:
            uname = f"@{inv['username']}" if inv['username'] else (inv['first_name'] or str(inv['user_id']))
            has_sub = inv['payment_granted'] or inv['has_active_sub']
            if has_sub:
                converted += 1
            status = "💎 Obuna" if has_sub else "⏳ Obunasiz"
            try:
                date_str = datetime.fromtimestamp(inv['created_at']).strftime("%d.%m.%Y")
            except Exception:
                date_str = "?"
            lines.append(f"• {uname} (`{inv['user_id']}`) — {status} — {date_str}")
        pct = round(converted * 100.0 / len(invitees), 1)
        lines.append(f"\n💎 Konversiya: **{converted}/{len(invitees)}** ({pct}%)")
    else:
        lines.append("\n📭 Taklif qilinganlar topilmadi.")

    buttons = [
        [InlineKeyboardButton("🔙 Referral statistika", callback_data="admin_referrals")],
        [InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")],
    ]

    await cq.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))
    await cq.answer()


@Client.on_callback_query(filters.regex("^admin_ref_toggle$") & is_admin_callback_filter)
async def admin_ref_toggle_callback(client: Client, cq: CallbackQuery):
    """Referral tizimini yoqish/o'chirish (bot_settings orqali, butun bot uchun)."""
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return

    from feature_flags import is_referral_enabled, set_bot_setting

    enabled = await is_referral_enabled()
    if not await set_bot_setting("referral_enabled", "0" if enabled else "1"):
        await cq.answer("❌ Sozlama saqlashda xatolik. Qaytadan urinib ko'ring.", show_alert=True)
        return

    try:
        from database import log_admin_action
        await log_admin_action(cq.from_user.id, "referral_toggle", None, f"enabled={not enabled}")
    except Exception:
        pass

    await cq.answer("✅ Taklif tizimi yoqildi" if not enabled else "🔴 Taklif tizimi o'chirildi")
    cq.data = "admin_referrals"
    await admin_referrals_callback(client, cq)
