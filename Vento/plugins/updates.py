from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database import (
    add_update, get_all_updates, get_update_by_id, delete_update,
    mark_update_read, has_user_read_update, get_unread_updates_count,
    get_update_notification_pref, set_update_notification_pref,
    get_all_users, get_all_registered_user_ids
)
from config import SUPER_ADMIN_ID, SECOND_ADMIN_ID, is_admin, user_states
import time
import asyncio
from datetime import datetime


@Client.on_callback_query(filters.regex("^admin_updates$"))
async def admin_updates_menu(client: Client, cq: CallbackQuery):
    """Admin yangilanishlar menyusi"""
    if not is_admin(cq.from_user.id):
        await cq.answer("⛔ Ruxsat yo'q!", show_alert=True)
        return
    
    updates = await get_all_updates()
    
    text = "📣 **Yangilanishlar paneli**\n\n"
    if updates:
        text += f"Jami yangilanishlar: **{len(updates)}** ta\n\n"
        text += "Oxirgi 5 ta:\n"
        for upd in updates[:5]:
            date_str = datetime.fromtimestamp(upd["created_at"]).strftime("%d.%m.%Y %H:%M")
            text += f"• **{upd['title']}** — {date_str}\n"
    else:
        text += "📭 Hozircha hech qanday yangilanish yo'q."
    
    buttons = [
        [InlineKeyboardButton("➕ Yangi yangilanish", callback_data="admin_add_update")],
    ]
    if updates:
        buttons.append([InlineKeyboardButton("📋 Barcha yangilanishlar", callback_data="admin_list_updates_0")])
    buttons.append([InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")])
    
    await cq.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    await cq.answer()


@Client.on_callback_query(filters.regex("^admin_add_update$"))
async def admin_add_update_callback(client: Client, cq: CallbackQuery):
    """Yangi yangilanish qo'shish - sarlavha so'rash"""
    if not is_admin(cq.from_user.id):
        return
    
    user_id = cq.from_user.id
    user_states[user_id] = "waiting_update_title"
    
    await cq.message.edit_text(
        "📝 **Yangi yangilanish qo'shish**\n\n"
        "1-qadam: Yangilanish sarlavhasini yuboring:\n\n"
        "Masalan: `Botga yangi imkoniyat qo'shildi`\n\n"
        "❌ Bekor qilish uchun /cancel yozing.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_updates")]
        ])
    )
    await cq.answer()


@Client.on_message(filters.private & filters.text)
async def update_state_handler(client: Client, message: Message):
    """Yangilanish yozish state handler"""
    user_id = message.from_user.id
    state = user_states.get(user_id)
    
    state_str = state if isinstance(state, str) else (state.get("state") if isinstance(state, dict) else None)
    
    if state_str != "waiting_update_title" and state_str != "waiting_update_content":
        raise ContinuePropagation
    
    if message.text and message.text.startswith("/"):
        if message.text == "/cancel":
            user_states.pop(user_id, None)
            await message.reply_text(
                "❌ Bekor qilindi.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📣 Yangilanishlar paneli", callback_data="admin_updates")],
                    [InlineKeyboardButton("🏠 Bosh menyu", callback_data="menu_main")]
                ])
            )
            return
        raise ContinuePropagation
    
    text = message.text.strip()
    
    if state_str == "waiting_update_title":
        user_states[user_id] = {"state": "waiting_update_content", "title": text}
        
        await message.reply_text(
            "✅ Sarlavha qabul qilindi!\n\n"
            "2-qadam: Endi yangilanish matnini (kontent) yuboring:\n\n"
            "Bu yerda nima o'zgargani, qanday yangiliklar qo'shilgani haqida yozing.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_updates")]
            ])
        )
    
    elif state_str == "waiting_update_content":
        title = user_states[user_id].get("title", "Yangilanish") if isinstance(user_states[user_id], dict) else "Yangilanish"
        
        update_id = await add_update(title, text, user_id)
        
        user_states.pop(user_id, None)
        
        date_str = datetime.fromtimestamp(int(time.time())).strftime("%d.%m.%Y %H:%M")
        
        from task_supervisor import schedule_guarded
        schedule_guarded("Update Notification", send_update_notification(client, update_id, title))
        
        await message.reply_text(
            f"✅ **Yangilanish qo'shildi!**\n\n"
            f"📌 **{title}**\n"
            f"📅 {date_str}\n"
            f"🆔 ID: #{update_id}\n\n"
            f"Foydalanuvchilarga bildirishnoma yuborilmoqda...",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📣 Yangilanishlar paneli", callback_data="admin_updates")],
                [InlineKeyboardButton("🏠 Bosh menyu", callback_data="menu_main")]
            ])
        )
    
    else:
        raise ContinuePropagation


@Client.on_callback_query(filters.regex(r"^admin_list_updates_(\d+)$"))
async def admin_list_updates(client: Client, cq: CallbackQuery):
    """Barcha yangilanishlar ro'yxati (sahifalangan)"""
    if not is_admin(cq.from_user.id):
        return
    
    page = int(cq.matches[0].group(1))
    updates = await get_all_updates()
    
    if not updates:
        await cq.message.edit_text(
            "📭 **Yangilanishlar yo'q.**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Yangi yangilanish", callback_data="admin_add_update")],
                [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_updates")]
            ])
        )
        await cq.answer()
        return
    
    per_page = 5
    total_pages = (len(updates) + per_page - 1) // per_page
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    end = start + per_page
    page_updates = updates[start:end]
    
    lines = ["📋 **Barcha yangilanishlar:**\n"]
    for upd in page_updates:
        date_str = datetime.fromtimestamp(upd["created_at"]).strftime("%d.%m.%Y %H:%M")
        lines.append(f"🆔 #{upd['id']} | **{upd['title']}**\n   📅 {date_str}\n")
    
    lines.append(f"\nSahifa {page + 1}/{total_pages} | Jami: {len(updates)} ta")
    
    buttons = []
    for upd in page_updates:
        buttons.append([
            InlineKeyboardButton(f"📝 {upd['title'][:30]}", callback_data=f"admin_view_update_{upd['id']}")
        ])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"admin_list_updates_{page - 1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ Keyingi", callback_data=f"admin_list_updates_{page + 1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([InlineKeyboardButton("➕ Yangi yangilanish", callback_data="admin_add_update")])
    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="admin_updates")])
    
    await cq.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^admin_view_update_(\d+)$"))
async def admin_view_update(client: Client, cq: CallbackQuery):
    """Admin yangilanishni ko'rish"""
    if not is_admin(cq.from_user.id):
        return
    
    update_id = int(cq.matches[0].group(1))
    update = await get_update_by_id(update_id)
    
    if not update:
        await cq.answer("Yangilanish topilmadi!", show_alert=True)
        return
    
    date_str = datetime.fromtimestamp(update["created_at"]).strftime("%d.%m.%Y %H:%M")
    
    await cq.message.edit_text(
        f"📌 **{update['title']}**\n"
        f"🆔 ID: #{update['id']}\n"
        f"📅 {date_str}\n\n"
        f"{update['content']}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑 O'chirish", callback_data=f"admin_del_update_confirm_{update_id}")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_list_updates_0")]
        ])
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^admin_del_update_confirm_(\d+)$"))
async def admin_del_update_confirm(client: Client, cq: CallbackQuery):
    """Yangilanishni o'chirishni tasdiqlash"""
    if not is_admin(cq.from_user.id):
        return
    
    update_id = int(cq.matches[0].group(1))
    update = await get_update_by_id(update_id)
    
    if not update:
        await cq.answer("Yangilanish topilmadi!", show_alert=True)
        return
    
    await cq.message.edit_text(
        f"⚠️ **{update['title']}** yangilanishini o'chirishni tasdiqlaysizmi?\n\n"
        "Bu amal qaytarib bo'lmaydi!",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Ha, o'chirish", callback_data=f"admin_del_update_do_{update_id}"),
                InlineKeyboardButton("❌ Yo'q", callback_data=f"admin_view_update_{update_id}"),
            ]
        ])
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^admin_del_update_do_(\d+)$"))
async def admin_del_update_do(client: Client, cq: CallbackQuery):
    """Yangilanishni o'chirish"""
    if not is_admin(cq.from_user.id):
        return
    
    update_id = int(cq.matches[0].group(1))
    await delete_update(update_id)
    
    await cq.message.edit_text(
        "🗑 **Yangilanish o'chirildi!**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Barcha yangilanishlar", callback_data="admin_list_updates_0")],
            [InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")]
        ])
    )
    await cq.answer("O'chirildi!", show_alert=True)



async def send_update_notification(client: Client, update_id: int, title: str):
    """Barcha foydalanuvchilarga yangi yangilanish haqida bildirishnoma yuborish"""
    users = await get_all_registered_user_ids()
    
    notification_text = (
        f"📣 **Yangi yangilanish!**\n\n"
        f"📌 {title}\n\n"
        f"Batafsil ko'rish uchun \"📣 Yangiliklar\" tugmasini bosing."
    )
    
    sent_count = 0
    failed_count = 0
    
    for user_id in users:
        try:
            notif_disabled = await get_update_notification_pref(user_id)
            if notif_disabled:
                continue
            
            await client.send_message(
                user_id,
                notification_text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📣 Yangiliklarni ko'rish", callback_data="menu_updates")]
                ])
            )
            sent_count += 1
            
            await asyncio.sleep(0.1)
        except Exception:
            failed_count += 1
            continue
    
    return sent_count, failed_count



@Client.on_callback_query(filters.regex("^menu_updates$"))
async def user_updates_menu(client: Client, cq: CallbackQuery):
    """Foydalanuvchi yangilanishlar menyusi"""
    user_id = cq.from_user.id
    updates = await get_all_updates()
    
    if not updates:
        await cq.message.edit_text(
            "📣 **Yangiliklar**\n\n"
            "📭 Hozircha hech qanday yangilanish yo'q.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Bosh menyu", callback_data="menu_main")]
            ])
        )
        await cq.answer()
        return
    
    lines = ["📣 **Yangiliklar**\n\n"]
    
    for upd in updates[:10]:
        is_read = await has_user_read_update(user_id, upd["id"])
        read_icon = "✅" if is_read else "🆕"
        date_str = datetime.fromtimestamp(upd["created_at"]).strftime("%d.%m.%Y")
        lines.append(f"{read_icon} **{upd['title']}** — {date_str}")
    
    lines.append(f"\nJami: {len(updates)} ta yangilanish")
    
    buttons = []
    for upd in updates[:10]:
        buttons.append([
            InlineKeyboardButton(f"📌 {upd['title'][:35]}", callback_data=f"user_view_update_{upd['id']}")
        ])
    
    notif_disabled = await get_update_notification_pref(user_id)
    notif_status = "❌ O'chirilgan" if notif_disabled else "✅ Yoqilgan"
    
    buttons.append([
        InlineKeyboardButton(f"🔔 Bildirishnoma: {notif_status}", callback_data="user_toggle_notif")
    ])
    buttons.append([InlineKeyboardButton("🔙 Bosh menyu", callback_data="menu_main")])
    
    await cq.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^user_view_update_(\d+)$"))
async def user_view_update(client: Client, cq: CallbackQuery):
    """Foydalanuvchi yangilanishni ko'rish"""
    user_id = cq.from_user.id
    update_id = int(cq.matches[0].group(1))
    update = await get_update_by_id(update_id)
    
    if not update:
        await cq.answer("Yangilanish topilmadi!", show_alert=True)
        return
    
    await mark_update_read(user_id, update_id)
    
    date_str = datetime.fromtimestamp(update["created_at"]).strftime("%d.%m.%Y %H:%M")
    
    oqildi_text = "✅ O'qildi"
    await cq.message.edit_text(
        f"📌 **{update['title']}**\n"
        f"📅 {date_str}\n\n"
        f"{update['content']}\n\n"
        f"_{oqildi_text}_",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Yangiliklar", callback_data="menu_updates")],
            [InlineKeyboardButton("🏠 Bosh menyu", callback_data="menu_main")]
        ])
    )
    await cq.answer()



@Client.on_callback_query(filters.regex("^user_toggle_notif$"))
async def user_toggle_notif(client: Client, cq: CallbackQuery):
    """Yangilanish bildirishnomasini yoqish/o'chirish"""
    user_id = cq.from_user.id
    current = await get_update_notification_pref(user_id)
    
    await set_update_notification_pref(user_id, not current)
    new_status = "❌ O'chirilgan" if not current else "✅ Yoqilgan"
    
    await cq.answer(f"Bildirishnoma {new_status}", show_alert=True)
    
    await cq.message.edit_text(
        cq.message.text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🔔 Bildirishnoma: {new_status}", callback_data="user_toggle_notif")],
            [InlineKeyboardButton("🔙 Bosh menyu", callback_data="menu_main")]
        ])
    )