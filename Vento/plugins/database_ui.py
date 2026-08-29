import asyncio
import time
import random
import os
from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove,
)
from database import (
    get_all_scraped_groups,
    get_group_info,
    get_group_member_count,
    delete_scraped_group,
    add_manual_members,
    get_user_subscription,
    generate_unique_group_id,
    delete_all_scraped_groups,
    is_free_user,
    add_scraped_group,
    get_members_by_group_paginated,
    add_scraped_member,
)
from config import (
    SUPER_ADMIN_ID,
    SECOND_ADMIN_ID,
    SESSIONS_DIR,
    API_ID,
    API_HASH,
    user_states,
    stop_flags,
    is_admin,
)
from datetime import datetime
import os
from session_manager import get_user_client



def _is_admin(uid: int) -> bool:
    return is_admin(uid)


async def _check_access(uid: int) -> bool:
    if _is_admin(uid):
        return True
    if await is_free_user(uid):
        return True
    return (await get_user_subscription(uid)) > 0


async def _check_group_access(uid: int, gid: str) -> bool:
    if _is_admin(uid):
        return True
    group = await get_group_info(gid)
    if not group:
        return False
    return group.get("owner_id") == uid


def _back_btn(label="🔙 Orqaga", data="admin_baza"):
    return InlineKeyboardButton(label, callback_data=data)


def _home_btn():
    return InlineKeyboardButton("🏠 Bosh menyu", callback_data="menu_main")


def _safe_title(group_title, group_id):
    """Nomsiz yoki noto'g'ri nomli bazalar uchun ID ko'rsatish."""
    if not group_title or not group_title.strip():
        return f"ID: {group_id}"
    first_line = group_title.split("\n")[0].strip()[:40]
    if not first_line or first_line == "." or first_line.startswith("(") and first_line.endswith(")"):
        return f"ID: {group_id}"
    return first_line


def _parse_confirm_users_state(state_str: str) -> dict | None:
    """Parse both legacy and new confirm_users state formats.
    
    Legacy: confirm_users|title|count|user1|user2|...
    New:     confirm_users|||title|||count|||user1
    
    Returns:
        {"title": str, "count": int, "targets": list[str]} or None if invalid
    """
    if not isinstance(state_str, str) or not state_str.startswith("confirm_users"):
        return None
    
    # New format: confirm_users|||title|||count|||targets
    if "|||" in state_str:
        parts = state_str.split("|||")
        # parts[0] = "confirm_users"
        if len(parts) < 4:
            return None
        title = parts[1]
        try:
            count = int(parts[2])
        except ValueError:
            return None
        targets_str = parts[3]
        # targets may be single username or multiple joined by |
        targets = targets_str.split("|") if "|" in targets_str else [targets_str]
        return {"title": title, "count": count, "targets": targets}
    
    # Legacy format: confirm_users|title|count|user1|user2|...
    parts = state_str.split("|")
    # parts[0] = "confirm_users", parts[1] = title, parts[2] = count, parts[3:] = targets
    if len(parts) < 4:
        return None
    title = parts[1]
    try:
        count = int(parts[2])
    except ValueError:
        return None
    targets = parts[3:]
    return {"title": title, "count": count, "targets": targets}



PAGE_SIZE = 10


@Client.on_callback_query(filters.regex("^admin_baza$"))
async def admin_baza_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    if not await _check_access(uid):
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return
    await _show_baza_page(cq, uid, 0)
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^admin_baza_page_(\d+)$"))
async def admin_baza_page_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    if not await _check_access(uid):
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return
    try:
        page = int(cq.matches[0].group(1))
    except (ValueError, IndexError, AttributeError):
        await cq.answer("❌ Sahifa raqami noto'g'ri!", show_alert=True)
        return
    await _show_baza_page(cq, uid, page)
    await cq.answer()


async def _show_baza_page(cq: CallbackQuery, uid: int, page: int):
    """Bazalar ro'yxatini sahifa ko'rinishida ko'rsatish."""
    is_admin_flag = _is_admin(uid)
    groups = await get_all_scraped_groups(owner_id=None if is_admin_flag else uid)

    if not groups:
        await cq.message.edit_text(
            "🗂 **Bazalar**\n\n📭 Hech qanday baza yo'q.\nScraper orqali yig'ing.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🔍 Scraperni ochish", callback_data="menu_scraper")],
                    [InlineKeyboardButton("➕ Yangi user(lar) qo'shish", callback_data="baza_new_users_start")],
                    [_home_btn()],
                ]
            ),
        )
        try:
            del_msg = await cq.message.reply_text("⏳", reply_markup=ReplyKeyboardRemove())
            await del_msg.delete()
        except:
            pass
        return

    total = len(groups)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    slice_start = page * PAGE_SIZE
    page_groups = groups[slice_start: slice_start + PAGE_SIZE]

    lines = [f"🗂 **Bazalar ro'yxati** ({total} ta) — {page + 1}/{total_pages}:\n"]
    buttons = []

    for g in page_groups:
        cnt = await get_group_member_count(g["group_id"])
        date_str = datetime.fromtimestamp(g["date_scraped"]).strftime("%d.%m.%Y %H:%M")
        title = _safe_title(g["group_title"], g["group_id"])
        lines.append(
            f"📁 **{title}**\n"
            f"   🆔 `{g['group_id']}` · 👥 {cnt} ta · 📅 {date_str}\n"
        )
        btn_label = f"📁 {title[:28]} ({cnt} ta)"
        buttons.append(
            [InlineKeyboardButton(btn_label, callback_data=f"baza_open_{g['group_id']}")]
        )

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"admin_baza_page_{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"admin_baza_page_{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("🔍 ID orqali qidirish", callback_data="baza_search_id")])
    buttons.append([InlineKeyboardButton("🧹 Bazani tozalash", callback_data="baza_clear_menu")])
    buttons.append([InlineKeyboardButton("➕ Yangi user(lar) qo'shish", callback_data="baza_new_users_start")])
    buttons.append([_home_btn()])

    await cq.message.edit_text(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons)
    )
    try:
        del_msg = await cq.message.reply_text("⏳", reply_markup=ReplyKeyboardRemove())
        await del_msg.delete()
    except:
        pass
    await cq.answer()




@Client.on_callback_query(filters.regex("^baza_search_id$"))
async def baza_search_id_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    if not await _check_access(uid):
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return

    groups = await get_all_scraped_groups()
    if not groups:
        await cq.answer("Baza bo'sh!", show_alert=True)
        return

    user_states[uid] = "waiting_baza_search_id"

    lines = ["🔍 **Baza qidirish / Ochish**\n", "Mavjud bazalar:\n"]
    buttons = []

    for g in groups:
        cnt = await get_group_member_count(g["group_id"])
        date_str = datetime.fromtimestamp(g["date_scraped"]).strftime("%d.%m.%Y %H:%M")
        lines.append(
            f"📁 **Guruh nomi:** {g['group_title']}\n"
            f"👥 **Yig'ilgan userlari:** {cnt} ta\n"
            f"📅 **Oxirgi yig'ilgan sana:** {date_str}\n"
            f"🆔 **ID:** `{g['group_id']}`\n"
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    f"📁 {g['group_title']} ({cnt} ta)",
                    callback_data=f"baza_open_{g['group_id']}",
                )
            ]
        )

    lines.append("Bazalardan birini tanlang yoki 4 xonali ID sini kiriting:")

    buttons.append(
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_baza")]
    )

    await cq.message.edit_text(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons)
    )
    await cq.answer()




@Client.on_callback_query(filters.regex(r"^baza_open_(.+)$"))
async def baza_open_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    if not await _check_access(uid):
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return

    gid = cq.matches[0].group(1)
    if not await _check_group_access(uid, gid):
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return

    group = await get_group_info(gid)
    if not group:
        await cq.answer("Baza topilmadi!", show_alert=True)
        return

    cnt = await get_group_member_count(gid)
    date_str = datetime.fromtimestamp(group["date_scraped"]).strftime("%d.%m.%Y %H:%M")
    safe_title = _safe_title(group['group_title'], gid)

    await cq.message.edit_text(
        f"📁 **{safe_title}**\n\n"
        f"🆔 Baza ID: `{gid}`\n"
        f"👥 A'zolar soni: **{cnt} ta**\n"
        f"📅 Oxirgi yangilanish: {date_str}\n\n"
        "Quyidagi amallardan birini tanlang:",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📋 Ro'yxatni ko'rish", callback_data=f"baza_list_{gid}_0"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "➕ User qo'shish", callback_data=f"baza_add_{gid}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "📨 Xabar yuborish", callback_data=f"baza_send_{gid}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "👥 Guruhga qo'shish (Nakrutka)", callback_data=f"baza_adder_{gid}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🗑 Bazani o'chirish", callback_data=f"baza_del_confirm_{gid}"
                    )
                ],
                [_back_btn("🔙 Bazalar ro'yxati", "admin_baza"), _home_btn()],
            ]
        ),
    )
    await cq.answer()




@Client.on_callback_query(filters.regex(r"^baza_list_(.+)_(\d+)$"))
async def baza_list_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    if not await _check_access(uid):
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return

    gid = cq.matches[0].group(1)
    if not await _check_group_access(uid, gid):
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return
    page = int(cq.matches[0].group(2))
    limit = 50
    offset = page * limit

    members = await get_members_by_group_paginated(gid, offset, limit)
    total = await get_group_member_count(gid)
    group = await get_group_info(gid)

    if not members:
        await cq.answer("Bu sahifada a'zo yo'q.", show_alert=True)
        return

    lines = [
        f"({offset + 1}-{offset + len(members)})\n"
    ]
    for m in members:
        if m["username"]:
            u = f"@{m['username']}"
        else:
            u = f"[{m['user_id']}](tg://user?id={m['user_id']})"
        lines.append(u)

    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                "⬅️ Oldingi", callback_data=f"baza_list_{gid}_{page - 1}"
            )
        )
    if offset + limit < total:
        nav.append(
            InlineKeyboardButton(
                "Keyingi ➡️", callback_data=f"baza_list_{gid}_{page + 1}"
            )
        )

    kb = []
    if nav:
        kb.append(nav)
    kb.append(
        [_back_btn(f"🔙 {group['group_title']}", f"baza_open_{gid}"), _home_btn()]
    )

    await cq.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))
    await cq.answer()




@Client.on_callback_query(filters.regex(r"^baza_add_(.+)$"))
async def baza_add_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    if not await _check_access(uid):
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return

    gid = cq.matches[0].group(1)
    if not await _check_group_access(uid, gid):
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return
    user_states[uid] = f"waiting_baza_add|{gid}"
    await cq.message.edit_text(
        "➕ **User qo'shish**\n\n"
        "Username yoki ID larni yuboring (har birini yangi qatorga):\n\n"
        "Masalan:\n`@username1\n@username2\n123456789`",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "❌ Bekor qilish", callback_data=f"baza_open_{gid}"
                    )
                ]
            ]
        ),
    )
    await cq.answer()




@Client.on_callback_query(filters.regex(r"^baza_send_(.+)$"))
async def baza_send_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    if not await _check_access(uid):
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return

    session_file = os.path.join(SESSIONS_DIR, f"user_{uid}.session")
    if not os.path.exists(session_file):
        await cq.answer("❌ Avval akkauntingizni ulang!", show_alert=True)
        return

    gid = cq.matches[0].group(1)
    if not await _check_group_access(uid, gid):
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return
    user_states[uid] = f"waiting_baza_send|{gid}"
    await cq.message.edit_text(
        "📨 **Xabar yuborish**\n\n"
        "Bazadagi barcha foydalanuvchilarga yuboriladigan xabarni yozing:\n\n"
        "_(Matn, rasm yoki video bo'lishi mumkin)_",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "❌ Bekor qilish", callback_data=f"baza_open_{gid}"
                    )
                ]
            ]
        ),
    )
    await cq.answer()




@Client.on_callback_query(filters.regex(r"^baza_del_confirm_(.+)$"))
async def baza_del_confirm_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    if not await _check_access(uid):
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return

    gid = cq.matches[0].group(1)
    if not await _check_group_access(uid, gid):
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return

    group = await get_group_info(gid)
    if not group:
        await cq.answer("Baza topilmadi!", show_alert=True)
        return

    await cq.message.edit_text(
        f"⚠️ **Ishonchingiz komilmi?**\n\n"
        f"**{group['group_title']}** bazasini va undagi barcha a'zolarni o'chirmoqchisiz?",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Ha, o'chirish", callback_data=f"baza_del_do_{gid}"
                    ),
                    InlineKeyboardButton(
                        "❌ Yo'q, orqaga", callback_data=f"baza_open_{gid}"
                    ),
                ]
            ]
        ),
    )
    await cq.answer()




@Client.on_callback_query(filters.regex(r"^baza_del_do_(.+)$"))
async def baza_del_do_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    if not await _check_access(uid):
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return

    gid = cq.matches[0].group(1)
    if not await _check_group_access(uid, gid):
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return
    await delete_scraped_group(gid)
    await cq.message.edit_text(
        "🗑 Baza muvaffaqiyatli o'chirildi.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📋 Bazalar ro'yxati", callback_data="admin_baza")]]
        ),
    )
    await cq.answer("O'chirildi!", show_alert=True)




@Client.on_callback_query(filters.regex("^baza_clear_menu$"))
async def baza_clear_menu_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    if not await _check_access(uid):
        return

    is_admin_flag = _is_admin(uid)
    groups = await get_all_scraped_groups(owner_id=None if is_admin_flag else uid)
    if not groups:
        await cq.answer("Baza bo'sh!", show_alert=True)
        return

    user_states[uid] = "waiting_baza_clear_id"

    lines = ["🧹 **Bazani tozalash**\n", "Mavjud bazalar:\n"]
    buttons = []

    for g in groups:
        cnt = await get_group_member_count(g["group_id"])
        date_str = datetime.fromtimestamp(g["date_scraped"]).strftime("%d.%m.%Y %H:%M")
        lines.append(
            f"📁 **Guruh nomi:** {g['group_title']}\n"
            f"👥 **Yig'ilgan userlari:** {cnt} ta\n"
            f"📅 **Oxirgi yig'ilgan sana:** {date_str}\n"
            f"🆔 **ID:** `{g['group_id']}`\n"
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    f"🗑 {g['group_title']} ({cnt} ta)",
                    callback_data=f"baza_clear_select_{g['group_id']}",
                )
            ]
        )

    lines.append("Tozalash uchun bazalardan birini tanlang yoki ID sini yozing:")

    buttons.append(
        [
            InlineKeyboardButton(
                "🗑 Barcha bazalarni birdaniga tozalash",
                callback_data="baza_clear_all_confirm",
            )
        ]
    )
    buttons.append([_back_btn("🔙 Orqaga", "admin_baza")])

    await cq.message.edit_text(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons)
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^baza_clear_select_(.+)$"))
async def baza_clear_select_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    if not await _check_access(uid):
        return

    gid = cq.matches[0].group(1)
    if not await _check_group_access(uid, gid):
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return

    group = await get_group_info(gid)
    if not group:
        await cq.answer("Baza topilmadi!", show_alert=True)
        return

    user_states.pop(uid, None)
    await cq.message.edit_text(
        f"⚠️ **Ishonchingiz komilmi?**\n\n"
        f"**{group['group_title']}** bazasini va undagi barcha a'zolarni o'chirmoqchisiz?",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Ha, tozalash", callback_data=f"baza_del_do_{gid}"
                    ),
                    InlineKeyboardButton(
                        "❌ Yo'q, orqaga", callback_data="baza_clear_menu"
                    ),
                ]
            ]
        ),
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^baza_clear_all_confirm$"))
async def baza_clear_all_confirm_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    if not _is_admin(uid):
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return

    await cq.message.edit_text(
        "⚠️ **Diqqat!**\n\n"
        "Chindan ham barcha bazalarni tozalaysizmi? Bu amalni ortga qaytarib bo'lmaydi!",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Ha, tasdiqlayman!", callback_data="baza_clear_all_do"
                    )
                ],
                [InlineKeyboardButton("❌ Yo'q, adashdim", callback_data="menu_main")],
            ]
        ),
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^baza_clear_all_do$"))
async def baza_clear_all_do_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    if not _is_admin(uid):
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return

    await delete_all_scraped_groups()
    await cq.message.edit_text(
        "✅ **Barcha bazalar muvaffaqiyatli tozalandi!**",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🏠 Bosh menyu", callback_data="menu_main")]]
        ),
    )
    await cq.answer("Tozalandi!", show_alert=True)




@Client.on_callback_query(filters.regex("^stop_process$"))
async def stop_process_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    if not await _check_access(uid):
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return
    stop_flags[uid] = True
    await cq.answer("🛑 To'xtatish signali yuborildi.", show_alert=True)




@Client.on_callback_query(filters.regex("^baza_new_manual$"))
async def baza_new_manual_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    if not _is_admin(uid):
        await cq.answer("⛔️ Faqat admin!", show_alert=True)
        return
    user_states[uid] = "waiting_baza_new_manual"
    await cq.message.edit_text(
        "📁 **Yangi baza yaratish**\n\nYangi bazaning nomini yuboring:",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_baza")]]
        ),
    )
    await cq.answer()



@Client.on_callback_query(filters.regex("^baza_new_users_start$"))
async def baza_new_users_start_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    if not await _check_access(uid):
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return
    user_states[uid] = "waiting_baza_name_for_users"
    await cq.message.edit_text(
        "➕ **Yangi user(lar) qo'shish**\n\n"
        "Yangi bazaning nomini yuboring:",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_baza")]]
        ),
    )
    await cq.answer()



@Client.on_callback_query(filters.regex("^baza_confirm_add_yes$"))
async def baza_confirm_add_yes_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    state = user_states.get(uid)
    state_str = state if isinstance(state, str) else (state.get("state") if isinstance(state, dict) else "")
    
    parsed = _parse_confirm_users_state(state_str)
    if not parsed:
        await cq.answer("Sessiya tugagan, qaytadan bosing.", show_alert=True)
        return
    
    await cq.answer()
    
    title = parsed["title"]
    count = parsed["count"]
    user_list = parsed["targets"]
    
    gid = await generate_unique_group_id()
    await add_scraped_group(gid, title, int(time.time()), owner_id=uid)
    added = 0
    failed = 0
    
    session_name = os.path.join(SESSIONS_DIR, f"user_{uid}")
    if os.path.exists(session_name + ".session"):
        try:
            from pyrogram.errors import FloodWait
            
            user_client = await get_user_client(uid)
            try: await cq.message.edit_text(f"🔄 0 / {len(user_list)} ta user tekshirilmoqda...\nIltimos kuting...")
            except: pass
            
            for i, username in enumerate(user_list, 1):
                try:
                    u = await user_client.get_users(username)
                    await add_scraped_member(u.id, u.username, u.first_name, gid)
                    added += 1
                except FloodWait as e:
                    await asyncio.sleep(e.value + 1)
                    try:
                        u = await user_client.get_users(username)
                        await add_scraped_member(u.id, u.username, u.first_name, gid)
                        added += 1
                    except:
                        failed += 1
                except:
                    failed += 1
                
                await asyncio.sleep(0.3)
                if i % 10 == 0:
                    try: await cq.message.edit_text(f"🔄 {i} / {len(user_list)} ta user tekshirilmoqda...\nIltimos kuting...")
                    except: pass
                    await asyncio.sleep(2)
        except Exception as e:
            if "sessiya" in str(e).lower() or "session" in str(e).lower():
                await cq.message.edit_text("❌ Sessiya tugagan, qaytadan bosing. /start")
            else:
                await cq.message.edit_text(f"❌ Xatolik: {e}")
            user_states.pop(uid, None)
            return
    else:
        for username in user_list:
            try:
                await add_scraped_member(0, username, "", gid)
                added += 1
            except:
                failed += 1
    
    user_states.pop(uid, None)
    await cq.message.edit_text(
        f"✅ **Baza yaratildi va userlar qo'shildi!**\n\n"
        f"📁 Baza nomi: **{title}**\n"
        f"🆔 Baza ID: `{gid}`\n"
        f"✅ Qo'shildi: **{added}** ta\n"
        f"❌ Xato: **{failed}** ta",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("📂 Bazani ochish", callback_data=f"baza_open_{gid}"),
                    InlineKeyboardButton("📋 Barcha bazalar", callback_data="admin_baza")
                ]
            ]
        )
    )


@Client.on_callback_query(filters.regex("^baza_confirm_add_no$"))
async def baza_confirm_add_no_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    state = user_states.get(uid)
    state_str = state if isinstance(state, str) else (state.get("state") if isinstance(state, dict) else "")
    
    parsed = _parse_confirm_users_state(state_str)
    if not parsed:
        await cq.answer("Sessiya tugagan, qaytadan bosing.", show_alert=True)
        return
    
    await cq.message.edit_text(
        "⚠️ **Amal bekor qilinyabdi!**\n\n"
        "Kiritgan userlaringiz yo'qolib ketadi. Tasdiqlaysizmi?",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🗑 Tushunaman, bajarish!", callback_data="baza_cancel_confirm_yes"),
                    InlineKeyboardButton("🔄 Davom etish", callback_data="baza_cancel_confirm_no")
                ]
            ]
        )
    )
    await cq.answer()



@Client.on_callback_query(filters.regex("^baza_cancel_confirm_yes$"))
async def baza_cancel_confirm_yes_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    user_states.pop(uid, None)
    await cq.message.edit_text(
        "❌ **Amal bekor qilindi.**\n\n"
        "Kiritgan userlaringiz o'chirildi.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📋 Barcha bazalar", callback_data="admin_baza")]]
        )
    )
    await cq.answer()



@Client.on_callback_query(filters.regex("^baza_cancel_confirm_no$"))
async def baza_cancel_confirm_no_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    state = user_states.get(uid)
    state_str = state if isinstance(state, str) else (state.get("state") if isinstance(state, dict) else "")
    
    parsed = _parse_confirm_users_state(state_str)
    if not parsed:
        await cq.answer("Sessiya tugagan, qaytadan bosing.", show_alert=True)
        return
    
    title = parsed["title"]
    count = parsed["count"]
    
    await cq.message.edit_text(
        f"📋 **{count} ta user**\n\n"
        f"**{count} ta userni bazaga qo'shmoqchimisz?**",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Ha, tasdiqlayman!", callback_data="baza_confirm_add_yes"),
                    InlineKeyboardButton("❌ Yo'q, adashdim!", callback_data="baza_confirm_add_no")
                ]
            ]
        )
    )
    await cq.answer()




@Client.on_message(filters.private & filters.text, group=-2)
async def baza_state_handler(client: Client, message: Message):
    uid = message.from_user.id
    state = user_states.get(uid)
    state_str = state if isinstance(state, str) else (state.get("state") if isinstance(state, dict) else "")

    if not state_str.startswith(
        ("waiting_baza_", "waiting_baza_send|", "waiting_baza_add|", "waiting_users_for_baza|")
    ):
        raise ContinuePropagation

    if state == "waiting_baza_search_id":
        gid = message.text.strip().upper()
        group = await get_group_info(gid)
        if group and group.get("owner_id") != uid and not _is_admin(uid):
            group = None
        user_states.pop(uid, None)
        if not group:
            await message.reply_text(
                f"❌ `{gid}` ID li baza topilmadi.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔍 Qayta qidirish", callback_data="baza_search_id"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "📋 Barcha bazalar", callback_data="admin_baza"
                            )
                        ],
                    ]
                ),
            )
        else:
            cnt = await get_group_member_count(gid)
            date_str = datetime.fromtimestamp(group["date_scraped"]).strftime(
                "%d.%m.%Y %H:%M"
            )
            await message.reply_text(
                f"✅ **Baza topildi!**\n\n"
                f"📁 {group['group_title']}\n"
                f"🆔 `{gid}` · 👥 {cnt} ta · 📅 {date_str}",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "📂 Bazani ochish", callback_data=f"baza_open_{gid}"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "📋 Barcha bazalar", callback_data="admin_baza"
                            )
                        ],
                    ]
                ),
            )
        return

    if state == "waiting_baza_clear_id":
        gid = message.text.strip().upper()
        group = await get_group_info(gid)
        if not group:
            await message.reply_text("❌ Baza topilmadi. Boshqa ID kiriting:")
            return
        if group.get("owner_id") != uid and not _is_admin(uid):
            await message.reply_text("❌ Ruxsat yo'q!")
            return

        user_states.pop(uid, None)
        await message.reply_text(
            f"⚠️ **Ishonchingiz komilmi?**\n\n"
            f"**{group['group_title']}** bazasini va undagi barcha a'zolarni o'chirmoqchisiz?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ Ha, tozalash", callback_data=f"baza_del_do_{gid}"
                        ),
                        InlineKeyboardButton(
                            "❌ Yo'q, orqaga", callback_data="baza_clear_menu"
                        ),
                    ]
                ]
            ),
        )
        return

    if state_str.startswith("waiting_baza_add|"):
        gid = state_str.replace("waiting_baza_add|", "")
        if not await _check_group_access(uid, gid):
            await message.reply_text("❌ Ruxsat yo'q!")
            return
        user_states.pop(uid, None)
        lines = message.text.strip().split()
        targets = [l.strip().lstrip("@") for l in lines if l.strip()]

        session_name = os.path.join(SESSIONS_DIR, f"user_{uid}")
        if not os.path.exists(session_name + ".session"):
            await message.reply_text("❌ Akkauntingiz ulanmagan. Avval /start bosing.")
            return

        msg = await message.reply_text(f"🔄 {len(targets)} ta user tekshirilmoqda...")

        added = 0
        failed = 0

        try:
            from pyrogram.errors import FloodWait
            
            user_client = await get_user_client(uid)
            try: await cq.message.edit_text(f"🔄 0 / {len(targets)} ta user tekshirilmoqda...\nIltimos kuting...")
            except: pass
            
            for i, username in enumerate(targets, 1):
                try:
                    u = await user_client.get_users(username)
                    await add_scraped_member(u.id, u.username, u.first_name, gid)
                    added += 1
                except FloodWait as e:
                    await asyncio.sleep(e.value + 1)
                    try:
                        u = await user_client.get_users(username)
                        await add_scraped_member(u.id, u.username, u.first_name, gid)
                        added += 1
                    except:
                        failed += 1
                except:
                    failed += 1
                
                await asyncio.sleep(0.3)
                if i % 10 == 0:
                    try: await msg.edit_text(f"🔄 {i} / {len(targets)} ta user tekshirilmoqda...\nIltimos kuting...")
                    except: pass
                    await asyncio.sleep(2)
        except Exception as e:
            await msg.edit_text(f"❌ Xatolik: {e}")
            return

        await msg.edit_text(
            f"✅ Natija:\n\n✔️ Qo'shildi: **{added}** ta\n❌ Xato: **{failed}** ta",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "📂 Bazani ko'rish", callback_data=f"baza_open_{gid}"
                        )
                    ],
                ]
            ),
        )
        return

    if state_str.startswith("waiting_baza_send|"):
        gid = state_str.replace("waiting_baza_send|", "")
        if not await _check_group_access(uid, gid):
            await message.reply_text("❌ Ruxsat yo'q!")
            return
        user_states.pop(uid, None)

        session_name = os.path.join(SESSIONS_DIR, f"user_{uid}")
        if not os.path.exists(session_name + ".session"):
            await message.reply_text("❌ Akkauntingiz ulanmagan.")
            return

        from database import get_group_member_count, get_members_by_group_paginated
        from pyrogram.errors import FloodWait

        total_members = await get_group_member_count(gid)
        if total_members == 0:
            await message.reply_text("❌ Bazada a'zo yo'q.")
            return

        stop_flags[uid] = False
        keyboard_stop = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🛑 To'xtatish", callback_data="stop_process")]]
        )
        status = await message.reply_text(
            f"📨 Xabar yuborilmoqda...\n\n⏳ Tayyorlanmoqda...",
            reply_markup=keyboard_stop,
        )

        sent, failed = 0, 0
        failed_consecutively = 0

        try:
            user_client = await get_user_client(uid)

            bot_me = await client.get_me()
            bot_identifier = bot_me.username or bot_me.id

            real_msg_id = None
            async for ch_m in user_client.get_chat_history(bot_identifier, limit=15):
                if ch_m.text and message.text and ch_m.text == message.text:
                    real_msg_id = ch_m.id
                    break
                if ch_m.caption and message.caption and ch_m.caption == message.caption:
                    real_msg_id = ch_m.id
                    break
            if not real_msg_id:
                async for ch_m in user_client.get_chat_history(bot_identifier, limit=1):
                    real_msg_id = ch_m.id

            original_msg = await user_client.get_messages(bot_identifier, real_msg_id)

            offset = 0
            CHUNK = 500
            base_delay = 1.2  # Adaptive — FloodWait kelsa oshadi, normal ketsa tushadi
            
            try:
                from spambot_unlock import send_and_check_unlock
                await status.edit_text("⏳ Tarqatishdan oldin SpamBot orqali akkaunt holati tekshirilmoqda / ochilmoqda...")
                await send_and_check_unlock(user_client, max_attempts=2)
                await status.edit_text("✅ Tekshiruv tugadi. Xabar yuborish jarayoni boshlanmoqda...")
                await asyncio.sleep(1)
            except Exception:
                pass

            while not stop_flags.get(uid):
                members_chunk = await get_members_by_group_paginated(gid, offset, limit=CHUNK)
                if not members_chunk:
                    break

                for m in members_chunk:
                    if stop_flags.get(uid):
                        break

                    username = m.get("username")
                    user_id_target = m["user_id"]
                    is_sent = False
                    sent_msg = None

                    for attempt in ([username, user_id_target] if username else [user_id_target]):
                        if not attempt:
                            continue
                        retries = 0
                        while retries < 3:
                            try:
                                sent_msg = await user_client.copy_message(
                                    chat_id=attempt,
                                    from_chat_id=bot_identifier,
                                    message_id=real_msg_id
                                )
                                is_sent = True
                                break
                            except FloodWait as e:
                                base_delay = min(base_delay * 1.5, 10.0)
                                await asyncio.sleep(e.value + 2)
                                retries += 1
                            except Exception:
                                break  # Bu attempt ishlamadi
                        if is_sent:
                            break  # username ishladi

                    if is_sent:
                        sent += 1
                        failed_consecutively = 0
                        base_delay = max(base_delay * 0.95, 1.2)
                    else:
                        failed += 1
                        failed_consecutively += 1

                    if failed_consecutively > 0 and failed_consecutively % 3 == 0:
                        try:
                            from spambot_unlock import send_and_check_unlock
                            await send_and_check_unlock(user_client, max_attempts=1)
                        except Exception:
                            pass

                    if failed_consecutively >= 5 and sent == 0:
                        try:
                            await message.reply_text(
                                "⚠️ **Diqqat:** Akkauntda cheklov (Spam) bo'lishi mumkin!\n"
                                "Xabarlar yetkazilmayapti."
                            )
                        except: pass
                        failed_consecutively = -9999

                    await asyncio.sleep(base_delay + random.uniform(0, 0.8))

                    processed = sent + failed
                    if processed % 10 == 0:
                        try:
                            pct = min(int(processed / total_members * 100), 100)
                            bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
                            await status.edit_text(
                                f"📨 **Yuborilmoqda...** [{bar}] {pct}%\n\n"
                                f"✅ Yuborildi: {sent}\n"
                                f"❌ Xato: {failed}\n"
                                f"⏱ Tezlik: {base_delay:.1f}s/xabar\n"
                                f"📊 Qolgan: {max(0, total_members - processed)}",
                                reply_markup=keyboard_stop,
                            )
                        except: pass

                    offset += 1  # har user uchun offset +1


        except Exception as e:
            await status.edit_text(f"❌ Xatolik: {e}")
            return

        stop_flags.pop(uid, None)
        await status.edit_text(
            f"✅ **Xabar yuborish yakunlandi!**\n\n"
            f"✔️ Yuborildi: **{sent}** ta\n"
            f"❌ Xato: **{failed}** ta\n"
            f"📊 Jami: **{total_members}** ta",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔙 Bazaga qaytish", callback_data=f"baza_open_{gid}"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🏠 Bosh menyu", callback_data="menu_main"
                        )
                    ],
                ]
            ),
        )
        return

    if state_str.startswith("waiting_adder_target|"):
        gid = state_str.replace("waiting_adder_target|", "")
        if not await _check_group_access(uid, gid):
            await message.reply_text("❌ Ruxsat yo'q!")
            return
        target_group = message.text.strip()
        
        user_states.pop(uid, None)
        
        session_name = os.path.join(SESSIONS_DIR, f"user_{uid}")
        if not os.path.exists(session_name + ".session"):
            await message.reply_text("❌ Akkauntingiz ulanmagan. Avval /start bosing.")
            return
            
        await message.reply_text(
            f"⏳ **Nakrutka tekshirilmoqda...**\n\n"
            f"Nishon: `{target_group}`\n"
            f"Iltimos, kutib turing...",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛑 To'xtatish", callback_data=f"stop_adder_{uid}")]
            ])
        )
        
        from task_supervisor import schedule_guarded
        schedule_guarded("Database Adder Task", run_adder_task(client, message, uid, gid, target_group))
        return

    if state == "waiting_baza_new_manual":
        title = message.text.strip().split("\n")[0].strip()[:40]
        user_states.pop(uid, None)
        gid = await generate_unique_group_id()

        await add_scraped_group(gid, title, int(time.time()))
        await message.reply_text(
            f"✅ Yangi baza yaratildi!\n\n📁 **{title}**\n🆔 `{gid}`",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "📂 Bazani ochish", callback_data=f"baza_open_{gid}"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "📋 Barcha bazalar", callback_data="admin_baza"
                        )
                    ],
                ]
            ),
        )
        return

    if state == "waiting_baza_name_for_users":
        title = message.text.strip().split("\n")[0].strip()[:40]
        if not title:
            await message.reply_text("❌ Baza nomi bo'sh bo'lishi mumkin emas!")
            return
        user_states[uid] = f"waiting_users_for_baza|{title}"
        await message.reply_text(
            f"📁 **Baza nomi: {title}**\n\n"
            "Endi qo'shmoqchi bo'lgan userlarni yuboring.\n\n"
            "Formatlar:\n"
            "• Matn: `@username1\n@username2\n@username3`\n"
            "• Forward: Forward xabar yuboring\n\n"
            "Faqat @username bo'lgan userlarni yuboring!",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_baza")]]
            ),
        )
        return

    if state_str.startswith("waiting_users_for_baza|") and message.text:
        title = state_str.replace("waiting_users_for_baza|", "")
        lines = message.text.strip().split()
        targets = [l.strip().lstrip("@") for l in lines if l.strip()]
        
        if not targets:
            await message.reply_text("❌ Hech qanday user kiritilmadi!")
            return
        
        valid_targets = []
        invalid_targets = []
        for t in targets:
            if t and not t.isdigit() and len(t) > 3 and not any(char in t for char in " "):
                valid_targets.append(t)
            else:
                invalid_targets.append(t)
        
        if not valid_targets:
            await message.reply_text(
                f"❌ Hech qanday to'g'ri username topilmadi!\n\n"
                f"❌ Filtrdan o'tmaganlar ({len(invalid_targets)} ta):\n" + 
                "\n".join([f"• {t}" for t in invalid_targets[:10]]) +
                ("\n..." if len(invalid_targets) > 10 else "") +
                "\n\nFaqat @username formatida kiriting (masalan: @username1)",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_baza")]]
                )
            )
            return
        
        report = f"✅ To'g'ri format: {len(valid_targets)} ta\n"
        if invalid_targets:
            report += f"❌ Filtrdan o'tmagan: {len(invalid_targets)} ta\n\n"
            report += "❌ Filtrdan o'tmaganlar:\n"
            report += "\n".join([f"• {t}" for t in invalid_targets[:10]])
            if len(invalid_targets) > 10:
                report += f"\n... va yana {len(invalid_targets) - 10} ta"
        
        user_states[uid] = f"confirm_users|{title}|{len(valid_targets)}|{'|'.join(valid_targets)}"
        await message.reply_text(
            f"📋 **Userlar tahlili**\n\n{report}\n\n"
            f"**{len(valid_targets)} ta userni bazaga qo'shmoqchimisz?**",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("✅ Ha, tasdiqlayman!", callback_data="baza_confirm_add_yes"),
                        InlineKeyboardButton("❌ Yo'q, adashdim!", callback_data="baza_confirm_add_no")
                    ]
                ]
            ),
        )
        return

    if state_str.startswith("waiting_users_for_baza|") and message.forward_from:
        title = state_str.replace("waiting_users_for_baza|", "")
        
        username = message.forward_from.username
        if not username:
            await message.reply_text(
                "❌ Bu userning username'i yo'q! Faqat @username bor userlarni forward qiling.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_baza")]]
                )
            )
            return
        
        user_states[uid] = f"confirm_users|||{title}|||1|||{username}"
        await message.reply_text(
            f"📋 **User topildi**\n\n"
            f"✅ To'g'ri format: 1 ta\n"
            f"@{username}\n\n"
            f"**1 ta userni bazaga qo'shmoqchimisz?**",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("✅ Ha, tasdiqlayman!", callback_data="baza_confirm_add_yes"),
                        InlineKeyboardButton("❌ Yo'q, adashdim!", callback_data="baza_confirm_add_no")
                    ]
                ]
            ),
        )
        return

    raise ContinuePropagation


@Client.on_callback_query(filters.regex(r"^baza_adder_(.+)$"))
async def baza_adder_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    if not await _check_access(uid):
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return

    gid = cq.matches[0].group(1)
    if not await _check_group_access(uid, gid):
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return

    from database import get_last_nakrutka_time
    from config import is_admin

    last_time = await get_last_nakrutka_time(uid)
    now = int(time.time())
    if now - last_time < 86400 and not is_admin(uid):
        left = 86400 - (now - last_time)
        hours = left // 3600
        mins = (left % 3600) // 60
        await cq.answer(f"⏳ Siz bugun nakrutkadan foydalangansiz!\nKeyingi urinish: {hours} soat, {mins} daqiqadan so'ng.", show_alert=True)
        return

    gid = cq.matches[0].group(1)
    user_states[uid] = f"waiting_adder_target|{gid}"

    await cq.message.edit_text(
        "👥 **Guruhga qo'shish (Nakrutka)**\n\n"
        "Qaysi guruhga odam qo'shmoqchisiz?\n"
        "Guruhning `username` ni (masalan `@Guruhim`) yoki `ID` sini (masalan `-1001234567890`) yuboring:\n\n"
        "_(Diqqat: Guruhga odam qo'shish uchun akkauntingizda ruxsat bo'lishi kerak)_",
        reply_markup=InlineKeyboardMarkup([
            [_back_btn("🔙 Orqaga", f"baza_open_{gid}")]
        ])
    )
    await cq.answer()

@Client.on_callback_query(filters.regex(r"^stop_adder_(.+)$"))
async def stop_adder_callback(client: Client, cq: CallbackQuery):
    target_uid = cq.matches[0].group(1)
    from config import is_admin
    if str(cq.from_user.id) != target_uid and not is_admin(cq.from_user.id):
        await cq.answer("Ruxsat yo'q!", show_alert=True)
        return
        
    from config import stop_flags
    stop_flags[f"adder_{target_uid}"] = True
    await cq.message.edit_text("🛑 To'xtatish buyrug'i berildi. Bir necha soniyada to'xtaydi...")
    await cq.answer()

async def run_adder_task(bot_client: Client, message: Message, uid: int, gid: str, target_group: str):
    from session_manager import get_user_client
    from pyrogram.errors import FloodWait, PeerFlood
    from config import stop_flags
    from database import get_members_by_group
    
    stop_flags[f"adder_{uid}"] = False
    
    try:
        user_client = await get_user_client(uid)
    except Exception as e:
        await message.reply_text(f"❌ Sessiya xatosi: {e}")
        return
        
    members = await get_members_by_group(gid)
    if not members:
        await message.reply_text("❌ Baza bo'sh!")
        return
        
    try:
        target_chat = await user_client.get_chat(target_group)
    except Exception as e:
        await message.reply_text(f"❌ Guruhni topib bo'lmadi yoki kirishga ruxsat yo'q:\n{e}")
        return
        
    status_msg = await message.reply_text(f"✅ Guruh topildi: **{target_chat.title}**.\n⏳ Odam qo'shish boshlanmoqda...")
    
    from database import update_last_nakrutka_time
    await update_last_nakrutka_time(uid, int(time.time()))
    
    added = 0
    failed = 0
    total = len(members)
    
    for i, m in enumerate(members, 1):
        if stop_flags.get(f"adder_{uid}"):
            break
            
        try:
            await user_client.add_chat_members(target_chat.id, [m["user_id"]])
            added += 1
            await asyncio.sleep(2) # Anti-flood delay
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
            try:
                await user_client.add_chat_members(target_chat.id, [m["user_id"]])
                added += 1
            except:
                failed += 1
        except PeerFlood:
            await message.reply_text("⛔️ Telegram akkauntingiz ko'p odam qo'shgani uchun cheklov oldi (PeerFlood). Jarayon to'xtatildi.")
            break
        except Exception:
            failed += 1
            await asyncio.sleep(0.5)
            
        if i % 10 == 0:
            try:
                await status_msg.edit_text(
                    f"⏳ **Jarayonda...** ({i}/{total})\n"
                    f"✅ Qo'shildi: {added}\n❌ Xato: {failed}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🛑 To'xtatish", callback_data=f"stop_adder_{uid}")]
                    ])
                )
            except:
                pass
                
    await message.reply_text(
        f"🏁 **Nakrutka yakunlandi!**\n\n"
        f"📁 Baza ID: `{gid}`\n"
        f"🎯 Nishon: `{target_chat.title}`\n\n"
        f"✅ Qo'shildi: **{added}** ta\n"
        f"❌ Xato/Maxfiylik: **{failed}** ta"
    )
